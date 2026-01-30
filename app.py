# app.py
import streamlit as st

from core.sb_client import get_clients
from core.context import init_context
from core.ui import inject_css, app_header, switch_to_tab_by_label
from core.utils import to_bool
from tabs import home, importar, consultar, relatorios, quitacao, sistema

st.set_page_config(page_title="Gestão de Internações", page_icon="🏥", layout="wide")
inject_css()
app_header("Sistema de Internações — Supabase", "Importação, edição, quitação e relatórios (banco em nuvem)")

supabase, admin_client = get_clients()
init_context(supabase, admin_client)

USE_DB_VIEW = to_bool(st.secrets.get("USE_DB_VIEW", False))

tabs_ui = st.tabs([
    "🏠 Início",
    "📤 Importar Arquivo",
    "🔍 Consultar Internação",
    "📑 Relatórios",
    "💼 Quitação",
    "⚙️ Sistema",
])

with tabs_ui[0]:
    home.render(use_db_view=USE_DB_VIEW)
with tabs_ui[1]:
    importar.render()
with tabs_ui[2]:
    consultar.render()
with tabs_ui[3]:
    relatorios.render(use_db_view=USE_DB_VIEW)
with tabs_ui[4]:
    quitacao.render(use_db_view=USE_DB_VIEW)
with tabs_ui[5]:
    sistema.render()

# ---- Troca de aba programática ----
if st.session_state.get("goto_tab_label"):
    switch_to_tab_by_label(st.session_state["goto_tab_label"])
    st.session_state["goto_tab_label"] = None
