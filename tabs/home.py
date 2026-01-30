import streamlit as st
import pandas as pd
from datetime import date, datetime
from core.ui import kpi_row, pill
from core.crud import home_fetch_base_df, get_hospitais

def render():
    st.subheader("🏠 Tela Inicial")

    if "home_status" not in st.session_state:
        st.session_state["home_status"] = None

    hoje = date.today()
    ini_mes = hoje.replace(day=1)

    colf1, colf2 = st.columns([2,3])
    with colf1:
        filtro_hosp_home = st.selectbox("Hospital", ["Todos"] + get_hospitais(), index=0, key="home_f_hosp")
    with colf2:
        st.write(" ")
        st.caption("Períodos (opcionais)")

    # ... restante do código da home ...
