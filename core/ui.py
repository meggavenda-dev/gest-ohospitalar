# core/ui.py
from __future__ import annotations
import streamlit as st
import json
import streamlit.components.v1 as components

STATUS_OPCOES = [
    "Pendente",
    "Não Cobrar",
    "Enviado para pagamento",
    "Aguardando Digitação - AMHP",
    "Finalizado",
]
PROCEDIMENTO_OPCOES = ["Cirurgia / Procedimento", "Parecer"]
GRAU_PARTICIPACAO_OPCOES = ["Cirurgião", "1 Auxiliar", "2 Auxiliar", "3 Auxiliar", "Clínico"]
ALWAYS_SELECTED_PROS = {"JOSE.ADORNO", "CASSIO CESAR", "FERNANDO AND", "SIMAO.MATOS"}

def inject_css():
    st.markdown("""
    <style>
    /* COLE AQUI O SEU CSS ATUAL (sem entidades HTML escapadas) */
    </style>
    """, unsafe_allow_html=True)

def pill(situacao: str) -> str:
    s = (situacao or "").strip()
    cls = "pill"
    if s == "Pendente": cls += " pill-pendente"
    elif s == "Não Cobrar": cls += " pill-nc"
    elif s == "Enviado para pagamento": cls += " pill-enviado"
    elif s == "Aguardando Digitação - AMHP": cls += " pill-digitacao"
    elif s == "Finalizado": cls += " pill-ok"
    return f"<span class='{cls}'>{s or '-'}</span>"

def kpi_row(items, extra_class: str = ""):
    st.markdown(f"<div class='kpi-wrap {extra_class}'>", unsafe_allow_html=True)
    for it in items:
        st.markdown(
            f"""
            <div class='kpi big'>
              <div class='label'>{it.get('label','')}</div>
              <div class='value'>{it.get('value','')}</div>
              { '<div class="hint">'+it.get('hint','')+'</div>' if it.get('hint') else '' }
            </div>
            """,
            unsafe_allow_html=True
        )
    st.markdown("</div>", unsafe_allow_html=True)

def app_header(title: str, subtitle: str = ""):
    st.markdown(
        f"""
        <div class="app-header">
            <div class="title">🏥 {title}</div>
            <div class="sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def tab_header_with_home(title: str, home_label: str = "🏠 Início", btn_key_suffix: str = ""):
    col_t1, col_t2 = st.columns([8, 2])
    with col_t1:
        st.subheader(title)
    with col_t2:
        if st.button(home_label, key=f"btn_go_home_{btn_key_suffix}", use_container_width=True):
            st.session_state["goto_tab_label"] = "🏠 Início"
            st.session_state["__goto_nonce"] = st.session_state.get("__goto_nonce", 0) + 1
            st.rerun()

def switch_to_tab_by_label(tab_label: str):
    nonce = int(st.session_state.get("__goto_nonce", 0))
    js = """
    <script>
    // nonce: __NONCE__
    (function(){
      const target = __TAB_LABEL__;
      const norm = (s) => (s || "").replace(/\\s+/g, " ").trim();
      let attempts = 0;
      const maxAttempts = 20;
      const timer = setInterval(() => {
        attempts++;
        const tabs = window.parent.document.querySelectorAll('button[role="tab"]');
        for (const t of tabs) {
          const txt = norm(t.textContent || t.innerText);
          if (txt.includes(norm(target))) { t.click(); clearInterval(timer); return; }
        }
        if (attempts >= maxAttempts) { clearInterval(timer); }
      }, 100);
    })();
    </script>
    """
    js = js.replace("__TAB_LABEL__", json.dumps(tab_label))
    js = js.replace("__NONCE__", str(nonce))
    components.html(js, height=0, width=0)

def admin_gate(label="Área administrativa") -> bool:
    """Gate simples por PIN em secrets. Retorna True quando liberado nesta sessão."""
    if st.session_state.get("__admin_ok"):
        return True

    admin_pin = str(st.secrets.get("ADMIN_PIN", "")).strip()
    if not admin_pin:
        st.warning("ADMIN_PIN não configurado em Secrets. Configure para proteger a área Sistema.")
        return False

    with st.expander(f"🔐 {label}", expanded=False):
        pin = st.text_input("PIN de administrador", type="password", key="__admin_pin")
        if st.button("Desbloquear", key="__admin_unlock", type="primary", use_container_width=True):
            if pin == admin_pin:
                st.session_state["__admin_ok"] = True
                st.toast("Admin desbloqueado nesta sessão.", icon="✅")
                st.rerun()
            else:
                st.error("PIN incorreto.")
    return False
