# tabs/quitacao.py
import streamlit as st
import pandas as pd

from core.ui import tab_header_with_home
from core.crud import get_hospitais, quitacao_pendentes_base_df, quitar_procedimento
from core.utils import to_ddmmyyyy, to_float_or_none, fmt_id_str

def render(use_db_view: bool = False):
    tab_header_with_home("💼 Quitação de Cirurgias", btn_key_suffix="quitacao")

    st.markdown("<div class='soft-card'>", unsafe_allow_html=True)
    hosp_opts = ["Todos"] + get_hospitais()
    hosp_sel = st.selectbox("Hospital", hosp_opts, index=0, key="quit_hosp")
    st.markdown("</div>", unsafe_allow_html=True)

    df_quit = quitacao_pendentes_base_df(use_db_view=use_db_view)

    if hosp_sel != "Todos" and not df_quit.empty:
        df_quit = df_quit[df_quit["hospital"] == hosp_sel]

    if df_quit.empty:
        st.info("Não há cirurgias com status 'Enviado para pagamento' para quitação.")
        return

    for col in ["quitacao_guia_amhptiss", "quitacao_guia_complemento"]:
        if col in df_quit.columns:
            df_quit[col] = df_quit[col].apply(fmt_id_str)

    st.markdown("Preencha os dados e clique em **Gravar quitação(ões)**. Ao gravar, status vira **Finalizado**.")
    edited = st.data_editor(
        df_quit, key="editor_quit", use_container_width=True, hide_index=True,
        column_config={
            "id": st.column_config.Column("ID", disabled=True),
            "hospital": st.column_config.Column("Hospital", disabled=True),
            "atendimento": st.column_config.Column("Atendimento", disabled=True),
            "paciente": st.column_config.Column("Paciente", disabled=True),
            "convenio": st.column_config.Column("Convênio", disabled=True),
            "data_procedimento": st.column_config.Column("Data Procedimento", disabled=True),
            "profissional": st.column_config.Column("Profissional", disabled=True),
            "aviso": st.column_config.Column("Aviso", disabled=True),
            "situacao": st.column_config.Column("Situação", disabled=True),
            "quitacao_data": st.column_config.DateColumn("Data da quitação", format="DD/MM/YYYY"),
            "quitacao_guia_amhptiss": st.column_config.TextColumn("Guia AMHPTISS"),
            "quitacao_valor_amhptiss": st.column_config.NumberColumn("Valor Guia AMHPTISS", format="R$ %.2f"),
            "quitacao_guia_complemento": st.column_config.TextColumn("Guia Complemento"),
            "quitacao_valor_complemento": st.column_config.NumberColumn("Valor Guia Complemento", format="R$ %.2f"),
            "quitacao_observacao": st.column_config.TextColumn("Observações da quitação"),
        }
    )

    if st.button("💾 Gravar quitação(ões)", type="primary", key="btn_save_quit"):
        cols_chk = [
            "quitacao_data","quitacao_guia_amhptiss","quitacao_valor_amhptiss",
            "quitacao_guia_complemento","quitacao_valor_complemento","quitacao_observacao",
        ]
        compare = df_quit[["id"] + cols_chk].merge(edited[["id"] + cols_chk], on="id", suffixes=("_old", "_new"))

        atualizados = faltando_data = 0
        for _, row in compare.iterrows():
            changed = any(str(row[c + "_old"] or "") != str(row[c + "_new"] or "") for c in cols_chk)
            if not changed:
                continue

            data_q = to_ddmmyyyy(row["quitacao_data_new"])
            if not data_q:
                faltando_data += 1
                continue

            guia_amhp = (row["quitacao_guia_amhptiss_new"] or None)
            v_amhp = to_float_or_none(row["quitacao_valor_amhptiss_new"])
            guia_comp = (row["quitacao_guia_complemento_new"] or None)
            v_comp = to_float_or_none(row["quitacao_valor_complemento_new"])
            obs_q = (row["quitacao_observacao_new"] or None)

            quitar_procedimento(
                proc_id=int(row["id"]),
                data_quitacao=data_q,
                guia_amhptiss=guia_amhp,
                valor_amhptiss=v_amhp,
                guia_complemento=guia_comp,
                valor_complemento=v_comp,
                quitacao_observacao=obs_q
            )
            atualizados += 1

        if faltando_data > 0 and atualizados == 0:
            st.warning("Nenhuma quitação gravada. Preencha a **Data da quitação**.")
        elif faltando_data > 0 and atualizados > 0:
            st.toast(f"{atualizados} quitação(ões) gravada(s). {faltando_data} ignorada(s) sem data.", icon="✅")
            st.rerun()
        else:
            st.toast(f"{atualizados} quitação(ões) gravada(s).", icon="✅")
            st.rerun()
