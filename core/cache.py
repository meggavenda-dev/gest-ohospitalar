import streamlit as st

TTL_LONG  = 300
TTL_MED   = 180
TTL_SHORT = 120

def invalidate_caches():
    try:
        st.cache_data.clear()
    except Exception:
        pass
