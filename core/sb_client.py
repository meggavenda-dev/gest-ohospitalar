# core/sb_client.py
import streamlit as st
from supabase import create_client, Client
from postgrest import APIError

def get_clients() -> tuple[Client, Client]:
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        st.error("Configure SUPABASE_URL e SUPABASE_KEY em Secrets para iniciar o app.")
        st.stop()

    supabase: Client = create_client(url, key)

    # Service role (admin) opcional. Se não existir, usa o cliente normal.
    service_key = st.secrets.get("SUPABASE_SERVICE_KEY", "")
    admin_client: Client = create_client(url, service_key) if service_key else supabase

    return supabase, admin_client

def sb_debug_error(e: APIError, prefix="Erro Supabase"):
    st.error(prefix)
    with st.expander("Detalhes técnicos"):
        st.code(
            f"code: {getattr(e,'code',None)}\n"
            f"message: {getattr(e,'message',None)}\n"
            f"details: {getattr(e,'details',None)}\n"
            f"hint: {getattr(e,'hint',None)}",
            language="text",
        )
