# tabs/importar.py
import streamlit as st
import pandas as pd
from datetime import date

from core.ui import tab_header_with_home, kpi_row, ALWAYS_SELECTED_PROS, pill
from core.crud import get_hospitais
from core.utils import att_norm, att_to_number, to_ddmmyyyy
from core.cache import invalidate_caches
from core.context import sb
from core.sb_client import sb_debug_error
from postgrest import APIError

try:
    from parser import parse_tiss_original
except Exception:
    parse_tiss_original = None

def render():
    tab_header_with_home("📤 Importar arquivo", btn_key_suffix="import")

    st.markdown("<div class='soft-card'>", unsafe_allow_html=True)

    hospitais = get_hospitais()
    hospital = st.selectbox("Hospital para esta importação:", hospitais, key="import_csv_hospital")
    arquivo = st.file_uploader("Selecione o arquivo CSV", key="import_csv_uploader")

    if parse_tiss_original is None:
        st.info("Adicione o arquivo parser.py com parse_tiss_original() para habilitar a importação.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if not arquivo:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    raw_bytes = arquivo.getvalue()
    try:
        csv_text = raw_bytes.decode("latin1")
    except UnicodeDecodeError:
        csv_text = raw_bytes.decode("utf-8-sig", errors="ignore")

    registros = parse_tiss_original(csv_text)
    st.success(f"{len(registros)} registros interpretados!")

    pros = sorted({(r.get("profissional") or "").strip() for r in registros if r.get("profissional")})
    pares = sorted({(r.get("atendimento"), r.get("data")) for r in registros if r.get("atendimento") and r.get("data")})

    kpi_row([
        {"label": "Registros no arquivo", "value": f"{len(registros):,}".replace(",", ".")},
        {"label": "Médicos distintos", "value": f"{len(pros):,}".replace(",", ".")},
        {"label": "Pares (atendimento, data)", "value": f"{len(pares):,}".replace(",", ".")},
    ])

    st.subheader("👨‍⚕️ Seleção de médicos")
    if "import_all_docs" not in st.session_state: st.session_state["import_all_docs"] = True
    if "import_selected_docs" not in st.session_state: st.session_state["import_selected_docs"] = []

    colsel1, colsel2 = st.columns([1, 3])
    with colsel1:
        import_all = st.checkbox("Importar todos os médicos", value=st.session_state["import_all_docs"], key="import_all_docs_chk")
    with colsel2:
        if import_all:
            st.info("Todos os médicos do arquivo serão importados.")
            selected_pros = pros[:]
        else:
            default_pre = sorted([p for p in pros if p in ALWAYS_SELECTED_PROS])
            selected_pros = st.multiselect(
                "Médicos a importar (os da lista fixa sempre serão incluídos na gravação):",
                options=pros,
                default=st.session_state["import_selected_docs"] or default_pre,
                key="import_selected_docs_ms"
            )

    st.session_state["import_all_docs"] = import_all
    st.session_state["import_selected_docs"] = selected_pros

    always_in_file = [p for p in pros if p in ALWAYS_SELECTED_PROS]
    final_pros = sorted(set(selected_pros if not import_all else pros).union(always_in_file))

    registros_filtrados = registros[:] if import_all else [r for r in registros if (r.get("profissional") or "") in final_pros]
    df_preview = pd.DataFrame(registros_filtrados)
    st.subheader("Pré-visualização (DRY RUN) — nada foi gravado ainda")
    st.dataframe(df_preview, use_container_width=True, hide_index=True)

    pares = sorted({(r["atendimento"], r["data"]) for r in registros_filtrados if r.get("atendimento") and r.get("data")})
    st.markdown(
        f"<div>🔎 {len(pares)} par(es) (atendimento, data) após filtros. Regra: {pill('1 auto por internação/dia')}.</div>",
        unsafe_allow_html=True
    )

    colg1, _ = st.columns([1, 4])
    with colg1:
        if st.button("Gravar no banco", type="primary", key="import_csv_gravar"):
            _import_turbo(hospital, registros_filtrados, pares)

    st.markdown("</div>", unsafe_allow_html=True)

def _import_turbo(hospital: str, registros_filtrados: list[dict], pares: list[tuple]):
    total_criados = total_ignorados = total_internacoes = 0

    atts_file = sorted({att for (att, d) in pares if att})
    orig_to_norm = {att: att_norm(att) for att in atts_file}
    norm_set = sorted({v for v in orig_to_norm.values() if v})
    num_set = sorted({att_to_number(att) for att in atts_file if att_to_number(att) is not None})

    existing_map_norm_to_id = {}
    try:
        if norm_set:
            res_int = sb().table("internacoes").select("id, atendimento").in_("atendimento", norm_set).execute()
            for r in (res_int.data or []):
                existing_map_norm_to_id[str(r["atendimento"])] = int(r["id"])
        if num_set:
            res_int_num = sb().table("internacoes").select("id, numero_internacao").in_("numero_internacao", num_set).execute()
            for r in (res_int_num.data or []):
                # normaliza chave a partir do número
                try:
                    k = att_norm(str(int(float(r["numero_internacao"]))))
                except Exception:
                    k = att_norm(str(r["numero_internacao"]))
                existing_map_norm_to_id[k] = int(r["id"])
    except APIError as e:
        sb_debug_error(e, "Falha ao buscar internações existentes.")
        existing_map_norm_to_id = {}

    to_create_int = []
    for att in atts_file:
        na = orig_to_norm.get(att)
        if not na or na in existing_map_norm_to_id:
            continue

        itens_att = [r for r in registros_filtrados if r.get("atendimento") == att]
        paciente = next((x.get("paciente") for x in itens_att if x.get("paciente")), "") if itens_att else ""
        conv_total = next((x.get("convenio") for x in itens_att if x.get("convenio")), "") if itens_att else ""
        data_int = next((x.get("data") for x in itens_att if x.get("data")), None)

        to_create_int.append({
            "hospital": hospital,
            "atendimento": na,
            "paciente": paciente,
            "data_internacao": to_ddmmyyyy(data_int) if data_int else to_ddmmyyyy(date.today()),
            "convenio": conv_total,
            "numero_internacao": att_to_number(att),
        })

    def _chunked_insert(table: str, rows: list, chunk: int = 500):
        for i in range(0, len(rows), chunk):
            sb().table(table).insert(rows[i:i+chunk]).execute()

    if to_create_int:
        try:
            _chunked_insert("internacoes", to_create_int, 500)
            if norm_set:
                res_int2 = sb().table("internacoes").select("id, atendimento").in_("atendimento", norm_set).execute()
                for r in (res_int2.data or []):
                    existing_map_norm_to_id[str(r["atendimento"])] = int(r["id"])
            total_internacoes = len(to_create_int)
            invalidate_caches()
        except APIError as e:
            sb_debug_error(e, "Falha ao criar internações em lote.")

    att_to_id = {att: existing_map_norm_to_id.get(orig_to_norm.get(att)) for att in atts_file}
    target_iids = sorted({iid for iid in att_to_id.values() if iid})

    existing_auto = set()
    try:
        if target_iids:
            res_auto = (
                sb().table("procedimentos")
                .select("internacao_id, data_procedimento, is_manual")
                .in_("internacao_id", target_iids).eq("is_manual", 0)
                .execute()
            )
            for r in (res_auto.data or []):
                iid = int(r["internacao_id"])
                dt = to_ddmmyyyy(r.get("data_procedimento"))
                if iid and dt:
                    existing_auto.add((iid, dt))
    except APIError as e:
        sb_debug_error(e, "Falha ao buscar procedimentos existentes.")

    to_insert_auto = []
    for (att, data_proc) in pares:
        if not att or not data_proc:
            total_ignorados += 1
            continue
        iid = att_to_id.get(att)
        if not iid:
            total_ignorados += 1
            continue

        data_norm = to_ddmmyyyy(data_proc)
        if (iid, data_norm) in existing_auto:
            total_ignorados += 1
            continue

        prof_dia = next((it.get("profissional") for it in registros_filtrados
                         if it.get("atendimento") == att and it.get("data") == data_proc and it.get("profissional")), "")
        aviso_dia = next((it.get("aviso") for it in registros_filtrados
                          if it.get("atendimento") == att and it.get("data") == data_proc and it.get("aviso")), "")

        if not prof_dia:
            total_ignorados += 1
            continue

        to_insert_auto.append({
            "internacao_id": int(iid),
            "data_procedimento": data_norm,
            "profissional": prof_dia,
            "procedimento": "Cirurgia / Procedimento",
            "situacao": "Pendente",
            "observacao": None,
            "is_manual": 0,
            "aviso": aviso_dia or None,
            "grau_participacao": None
        })
        existing_auto.add((iid, data_norm))

    if to_insert_auto:
        try:
            _chunked_insert("procedimentos", to_insert_auto, 500)
            invalidate_caches()
            total_criados = len(to_insert_auto)
        except APIError as e:
            sb_debug_error(e, "Falha ao inserir procedimentos em lote.")

    st.success(
        f"Concluído! Internações criadas: {total_internacoes} | Automáticos criados: {total_criados} | Ignorados: {total_ignorados}"
    )
    st.toast("✅ Importação concluída.", icon="✅")
