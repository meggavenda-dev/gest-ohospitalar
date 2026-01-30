# tabs/home.py
import streamlit as st
import pandas as pd
from datetime import date, datetime

from core.ui import kpi_row
from core.crud import get_hospitais, home_fetch_base_df
from core.utils import pt_date_to_dt

def render(use_db_view: bool = False):
    st.subheader("🏠 Tela Inicial")

    if "home_status" not in st.session_state:
        st.session_state["home_status"] = None

    hoje = date.today()
    ini_mes = hoje.replace(day=1)

    colf1, colf2 = st.columns([2, 3])
    with colf1:
        filtro_hosp_home = st.selectbox("Hospital", ["Todos"] + get_hospitais(), index=0, key="home_f_hosp")
    with colf2:
        st.write(" ")
        st.caption("Períodos (opcionais)")

    cbox1, cbox2 = st.columns(2)
    with cbox1:
        use_int_range = st.checkbox("Filtrar por data da internação", key="home_use_int_range", value=False)
    with cbox2:
        use_proc_range = st.checkbox("Filtrar por data do procedimento", key="home_use_proc_range", value=False)

    if use_int_range or use_proc_range:
        cold1, cold2, cold3, cold4 = st.columns(4)
        with cold1:
            int_ini = st.date_input("Internação — início", value=st.session_state.get("home_f_int_ini", ini_mes), key="home_f_int_ini")
        with cold2:
            int_fim = st.date_input("Internação — fim", value=st.session_state.get("home_f_int_fim", hoje), key="home_f_int_fim")
        with cold3:
            proc_ini = st.date_input("Procedimento — início", value=st.session_state.get("home_f_proc_ini", ini_mes), key="home_f_proc_ini")
        with cold4:
            proc_fim = st.date_input("Procedimento — fim", value=st.session_state.get("home_f_proc_fim", hoje), key="home_f_proc_fim")

    df_all = home_fetch_base_df(use_db_view=use_db_view)

    if df_all.empty:
        df_f = df_all.copy()
    else:
        df_all["_int_dt"] = df_all["data_internacao"].apply(pt_date_to_dt)
        df_all["_proc_dt"] = df_all["data_procedimento"].apply(pt_date_to_dt)

        mask = pd.Series([True] * len(df_all), index=df_all.index)

        if filtro_hosp_home != "Todos":
            mask &= (df_all["hospital"] == filtro_hosp_home)

        if use_int_range:
            mask &= df_all["_int_dt"].notna()
            mask &= (df_all["_int_dt"] >= st.session_state["home_f_int_ini"])
            mask &= (df_all["_int_dt"] <= st.session_state["home_f_int_fim"])

        if use_proc_range:
            mask &= df_all["_proc_dt"].notna()
            mask &= (df_all["_proc_dt"] >= st.session_state["home_f_proc_ini"])
            mask &= (df_all["_proc_dt"] <= st.session_state["home_f_proc_fim"])

        df_f = df_all[mask].copy()

    def _count_status(df: pd.DataFrame, status: str) -> int:
        if df is None or df.empty or "situacao" not in df.columns:
            return 0
        return int((df["situacao"] == status).sum())

    tot_pendente = _count_status(df_f, "Pendente")
    tot_finalizado = _count_status(df_f, "Finalizado")
    tot_nao_cobrar = _count_status(df_f, "Não Cobrar")

    kpi_row([
        {"label": "Pendentes", "value": str(tot_pendente), "hint": "Todos os procedimentos"},
        {"label": "Finalizadas", "value": str(tot_finalizado), "hint": "Todos os procedimentos"},
        {"label": "Não Cobrar", "value": str(tot_nao_cobrar), "hint": "Todos os procedimentos"},
    ], extra_class="center")

    st.caption("✅ Home modularizada. Se quiser, eu colo aqui a versão 100% idêntica à sua atual (com a lista clicável e goto-tab).")
