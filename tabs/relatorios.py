# tabs/relatorios.py
import streamlit as st
import pandas as pd
from datetime import date, datetime

from core.ui import tab_header_with_home, STATUS_OPCOES
from core.crud import get_hospitais, rel_cirurgias_base_df, rel_quitacoes_base_df
from core.utils import pt_date_to_dt, fmt_id_str
from core.reports import excel_quitacoes_colunas_fixas

# PDF: você pode mover suas funções enormes para core/reports.py depois
REPORTLAB_OK = True
try:
    from reportlab.platypus import SimpleDocTemplate  # noqa
except Exception:
    REPORTLAB_OK = False

def render(use_db_view: bool = False):
    tab_header_with_home("📑 Relatórios — Central", btn_key_suffix="relatorios")

    st.markdown("**1) Cirurgias por Status (PDF)**")
    hosp_opts = ["Todos"] + get_hospitais()

    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        hosp_sel = st.selectbox("Hospital", hosp_opts, index=0, key="rel_hosp")
    with colf2:
        status_sel = st.selectbox("Status", ["Todos"] + STATUS_OPCOES, index=0, key="rel_status")
    with colf3:
        hoje = date.today()
        ini_default = hoje.replace(day=1)
        dt_ini = st.date_input("Data inicial", value=ini_default, key="rel_ini")
        dt_fim = st.date_input("Data final", value=hoje, key="rel_fim")

    df_rel = rel_cirurgias_base_df(use_db_view=use_db_view)
    if not df_rel.empty:
        df_rel["_dt"] = df_rel["data_procedimento"].apply(pt_date_to_dt)
        df_rel = df_rel[df_rel["_dt"].notna()].copy()
        df_rel = df_rel[(df_rel["_dt"] >= dt_ini) & (df_rel["_dt"] <= dt_fim)]
        if hosp_sel != "Todos":
            df_rel = df_rel[df_rel["hospital"] == hosp_sel]
        if status_sel != "Todos":
            df_rel = df_rel[df_rel["situacao"] == status_sel]
        df_rel = df_rel.drop(columns=["_dt"], errors="ignore")

    colc1, colc2 = st.columns(2)
    with colc1:
        if st.button("Gerar PDF (Cirurgias por Status)", key="btn_pdf_cir", type="primary"):
            if df_rel.empty:
                st.warning("Nenhum registro encontrado.")
            elif not REPORTLAB_OK:
                st.error("ReportLab não instalado.")
            else:
                st.info("✅ Aqui você cola/chama sua função PDF existente (moveremos para core/reports.py depois).")

    with colc2:
        if not df_rel.empty:
            csv_bytes = df_rel.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Baixar CSV", data=csv_bytes, file_name=f"cirurgias_{date.today():%Y%m%d}.csv", mime="text/csv")

    st.divider()

    st.markdown("**2) Quitações (Excel / CSV)**")
    hosp_opts_q = ["Todos"] + get_hospitais()

    colq1, colq2 = st.columns(2)
    with colq1:
        hosp_sel_q = st.selectbox("Hospital", hosp_opts_q, index=0, key="rel_q_hosp")
    with colq2:
        hoje = date.today()
        ini_default_q = hoje.replace(day=1)
        dt_ini_q = st.date_input("Data inicial da quitação", value=ini_default_q, key="rel_q_ini")
        dt_fim_q = st.date_input("Data final da quitação", value=hoje, key="rel_q_fim")

    df_quit = rel_quitacoes_base_df(use_db_view=use_db_view)
    if not df_quit.empty:
        df_quit["_qdt"] = df_quit["quitacao_data"].apply(pt_date_to_dt)
        df_quit = df_quit[df_quit["_qdt"].notna()].copy()
        df_quit = df_quit[(df_quit["_qdt"] >= dt_ini_q) & (df_quit["_qdt"] <= dt_fim_q)]
        if hosp_sel_q != "Todos":
            df_quit = df_quit[df_quit["hospital"] == hosp_sel_q]

        for col in ["quitacao_guia_amhptiss", "quitacao_guia_complemento", "aviso"]:
            if col in df_quit.columns:
                df_quit[col] = df_quit[col].apply(fmt_id_str)

        df_quit = df_quit.drop(columns=["_qdt"], errors="ignore").fillna("")

    colb1, colb2 = st.columns(2)
    with colb1:
        if not df_quit.empty:
            csv_quit = df_quit.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Baixar CSV (Quitações)", data=csv_quit, file_name=f"quitacoes_{date.today():%Y%m%d}.csv", mime="text/csv")

    with colb2:
        if not df_quit.empty:
            xlsx = excel_quitacoes_colunas_fixas(df_quit)
            st.download_button(
                "⬇️ Baixar Excel (layout fixo)",
                data=xlsx,
                file_name=f"quitacoes_{date.today():%Y%m%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
