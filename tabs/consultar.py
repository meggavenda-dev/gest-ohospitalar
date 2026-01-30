# tabs/consultar.py
import streamlit as st
import pandas as pd
from datetime import date, datetime

from core.ui import tab_header_with_home, STATUS_OPCOES, PROCEDIMENTO_OPCOES, GRAU_PARTICIPACAO_OPCOES, pill
from core.crud import (
    get_hospitais, get_internacao_by_atendimento, atualizar_internacao, deletar_internacao,
    atualizar_procedimento, deletar_procedimento, criar_procedimento,
    listar_profissionais_cache, get_procedimentos, reverter_quitacao
)
from core.utils import pt_date_to_dt, to_ddmmyyyy, fmt_id_str, format_currency_br
from core.context import sb
from core.sb_client import sb_debug_error
from postgrest import APIError

def render():
    tab_header_with_home("🔍 Consultar Internação", btn_key_suffix="consulta")

    st.markdown("<div class='soft-card'>", unsafe_allow_html=True)
    hlist = ["Todos"] + get_hospitais()
    filtro_hosp = st.selectbox("Filtrar hospital (consulta):", hlist, key="consulta_f_hosp")
    codigo = st.text_input("Digite o atendimento para consultar:", key="consulta_codigo", placeholder="Ex.: 0007064233 ou 7064233")
    st.markdown("</div>", unsafe_allow_html=True)

    if not codigo:
        return

    df_int = get_internacao_by_atendimento(codigo)
    if filtro_hosp != "Todos" and not df_int.empty and "hospital" in df_int.columns:
        df_int = df_int[df_int["hospital"] == filtro_hosp]

    if df_int.empty:
        st.warning("Nenhuma internação encontrada.")
        return

    st.subheader("Dados da internação")
    st.dataframe(df_int, use_container_width=True, hide_index=True)

    internacao_id = int(df_int["id"].iloc[0])

    # data internação robusta
    data_internacao_str = df_int.get("data_internacao", pd.Series([""])).iloc[0]
    dt_internacao = pt_date_to_dt(data_internacao_str) or date.today()

    # ===== Edição internação =====
    st.subheader("✏️ Editar dados da internação")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        novo_paciente = st.text_input("Paciente:", value=df_int["paciente"].iloc[0] or "", key=f"edit_pac_{internacao_id}")
    with c2:
        novo_convenio = st.text_input("Convênio:", value=df_int["convenio"].iloc[0] or "", key=f"edit_conv_{internacao_id}")
    with c3:
        nova_data = st.date_input("Data da internação:", value=dt_internacao, key=f"edit_dt_{internacao_id}")
    with c4:
        todos_hospitais = get_hospitais(include_inactive=True)
        atual = df_int["hospital"].iloc[0]
        idx = todos_hospitais.index(atual) if atual in todos_hospitais else 0
        novo_hospital = st.selectbox("Hospital:", todos_hospitais, index=idx, key=f"edit_hosp_{internacao_id}")

    if st.button("💾 Salvar alterações da internação", type="primary", key=f"btn_save_int_{internacao_id}"):
        atualizar_internacao(
            internacao_id,
            paciente=novo_paciente,
            convenio=novo_convenio,
            data_internacao=nova_data,
            hospital=novo_hospital,
        )
        st.toast("Dados da internação atualizados!", icon="✅")
        st.rerun()

    # ===== Excluir internação =====
    with st.expander("🗑️ Excluir esta internação"):
        st.warning("Esta ação apagará a internação e TODOS os procedimentos vinculados.")
        confirm_txt = st.text_input("Digite APAGAR para confirmar", key=f"confirm_del_int_{internacao_id}")
        if st.button("Excluir internação", key=f"btn_del_int_{internacao_id}", type="primary"):
            if confirm_txt.strip().upper() == "APAGAR":
                ok = deletar_internacao(internacao_id)
                if ok:
                    st.toast("🗑️ Internação excluída.", icon="✅")
                    st.rerun()
            else:
                st.info("Confirmação inválida. Digite APAGAR.")

    # ===== Procedimentos =====
    try:
        res_p = sb().table("procedimentos").select(
            "id, data_procedimento, profissional, procedimento, situacao, observacao, aviso, grau_participacao, "
            "quitacao_data, quitacao_guia_amhptiss, quitacao_valor_amhptiss, quitacao_guia_complemento, quitacao_valor_complemento, quitacao_observacao"
        ).eq("internacao_id", internacao_id).execute()
        df_proc = pd.DataFrame(res_p.data or [])
    except APIError as e:
        sb_debug_error(e, "Falha ao carregar procedimentos.")
        df_proc = pd.DataFrame()

    if df_proc.empty:
        st.subheader("Procedimentos")
        st.info("Esta internação ainda não possui procedimentos cadastrados.")
        return

    # normaliza aviso para exibição
    if "aviso" in df_proc.columns:
        df_proc["aviso"] = df_proc["aviso"].apply(fmt_id_str)

    st.subheader("Procedimentos — Editáveis")
    edited = st.data_editor(
        df_proc,
        key=f"editor_proc_{internacao_id}",
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.Column("ID", disabled=True),
            "data_procedimento": st.column_config.Column("Data", disabled=True),
            "profissional": st.column_config.Column("Profissional", disabled=True),
            "aviso": st.column_config.TextColumn("Aviso"),
            "grau_participacao": st.column_config.SelectboxColumn("Grau", options=[""] + GRAU_PARTICIPACAO_OPCOES),
            "procedimento": st.column_config.SelectboxColumn("Tipo", options=PROCEDIMENTO_OPCOES),
            "situacao": st.column_config.SelectboxColumn("Situação", options=STATUS_OPCOES),
            "observacao": st.column_config.TextColumn("Observações"),
        }
    )

    if st.button("💾 Salvar alterações", type="primary", key=f"btn_save_proc_{internacao_id}"):
        # Atualiza por linha (simples e seguro)
        for _, r in edited.iterrows():
            atualizar_procedimento(
                proc_id=int(r["id"]),
                procedimento=r.get("procedimento"),
                situacao=r.get("situacao"),
                observacao=r.get("observacao"),
                grau_participacao=(r.get("grau_participacao") or None),
                aviso=(r.get("aviso") or None),
            )
        st.toast("Procedimentos atualizados.", icon="✅")
        st.rerun()

    with st.expander("🗑️ Excluir procedimento"):
        for _, r in df_proc.iterrows():
            pid = int(r["id"])
            cols = st.columns([6, 2])
            with cols[0]:
                st.markdown(f"**ID {pid}** — {r.get('data_procedimento','-')} — {r.get('profissional','-')} — {pill(r.get('situacao'))}", unsafe_allow_html=True)
            with cols[1]:
                if st.button("Excluir", key=f"del_proc_{internacao_id}_{pid}"):
                    if deletar_procedimento(pid):
                        st.toast("Procedimento excluído.", icon="🗑️")
                        st.rerun()

    # ===== Quitações (Finalizados) =====
    st.divider()
    st.subheader("🔎 Quitações desta internação (somente Finalizados)")
    finalizados = df_proc[df_proc["situacao"] == "Finalizado"] if "situacao" in df_proc.columns else pd.DataFrame()
    if finalizados.empty:
        st.info("Não há procedimentos finalizados nesta internação.")
        return

    for _, r in finalizados.iterrows():
        cols = st.columns([2, 3, 3, 2])
        with cols[0]:
            st.write(f"Data: {r.get('data_procedimento','-')}")
        with cols[1]:
            st.write(f"Prof: {r.get('profissional','-')}")
        with cols[2]:
            st.write(f"Aviso: {fmt_id_str(r.get('aviso')) or '-'}")
        with cols[3]:
            if st.button("Ver quitação", key=f"verquit_{int(r['id'])}"):
                st.session_state["show_quit_id"] = int(r["id"])

    pid = st.session_state.get("show_quit_id")
    if pid:
        q = df_proc[df_proc["id"] == pid].iloc[0]
        guia_amhp = fmt_id_str(q.get("quitacao_guia_amhptiss"))
        guia_comp = fmt_id_str(q.get("quitacao_guia_complemento"))
        total = float(q.get("quitacao_valor_amhptiss") or 0) + float(q.get("quitacao_valor_complemento") or 0)

        st.markdown("---")
        st.markdown("### 🧾 Detalhes da quitação")
        st.write(f"Guia AMHPTISS: {guia_amhp or '-'} | Guia Compl.: {guia_comp or '-'}")
        st.write(f"Total quitado: **{format_currency_br(total)}**")
        st.write(q.get("quitacao_observacao") or "-")

        cols = st.columns(2)
        with cols[0]:
            if st.button("Fechar", key="fechar_quit"):
                st.session_state["show_quit_id"] = None
                st.rerun()
        with cols[1]:
            if st.button("↩️ Reverter quitação", key=f"rev_{pid}", type="secondary"):
                reverter_quitacao(pid)
                st.session_state["show_quit_id"] = None
                st.toast("Quitação revertida.", icon="↩️")
                st.rerun()
