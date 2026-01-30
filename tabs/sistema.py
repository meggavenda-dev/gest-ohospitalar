# tabs/sistema.py
import streamlit as st
from postgrest import APIError

from core.ui import tab_header_with_home, admin_gate
from core.backup import (
    export_tables_to_zip, upload_zip_to_storage, list_backups_from_storage,
    download_backup_from_storage, restore_from_zip, now_ts
)
from core.context import sb
from core.sb_client import sb_debug_error

def render():
    tab_header_with_home("⚙️ Sistema", btn_key_suffix="sistema")
    st.markdown("<div class='soft-card'>", unsafe_allow_html=True)

    if not admin_gate("Backups / Restore / Storage"):
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ============================
    # 🛡️ Backups
    # ============================
    st.markdown("**🛡️ Backups**")
    st.caption("Gere um arquivo .zip contendo JSON e CSV de cada tabela. Opcionalmente, envie ao Supabase Storage.")

    colb1, colb2, colb3 = st.columns([2, 2, 2])

    with colb1:
        if st.button("🧩 Gerar backup (ZIP)", key="btn_gen_backup", type="primary", use_container_width=True):
            with st.spinner("Gerando backup..."):
                zip_bytes = export_tables_to_zip(["hospitals", "internacoes", "procedimentos"])
            fname = f"backup_internacoes_{now_ts()}.zip"
            st.success("Backup gerado!")
            st.download_button("⬇️ Baixar ZIP", data=zip_bytes, file_name=fname, mime="application/zip", use_container_width=True)
            st.session_state["__last_backup_zip"] = (fname, zip_bytes)

    with colb2:
        if st.button("☁️ Enviar último backup ao Storage", key="btn_push_storage", use_container_width=True):
            last = st.session_state.get("__last_backup_zip")
            if not last:
                st.info("Gere um backup primeiro (ou use a seção abaixo para listar/baixar do Storage).")
            else:
                fname, zip_bytes = last
                ok = upload_zip_to_storage(zip_bytes, fname)
                if ok:
                    st.toast(f"Backup enviado: {fname}", icon="☁️")

    with colb3:
        st.write("")

    st.markdown("---")
    st.markdown("**☁️ Backups no Storage**")

    files = list_backups_from_storage(prefix="")
    if "__dl_cache" not in st.session_state:
        st.session_state["__dl_cache"] = {}  # name -> bytes

    if not files:
        st.info("Nenhum backup no Storage (ou bucket vazio).")
    else:
        for f in files[:50]:
            name = f.get("name", "")
            size = (f.get("metadata", {}) or {}).get("size") or f.get("size") or 0
            updated = f.get("updated_at") or f.get("last_modified") or f.get("created_at") or "-"

            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])
            with c1:
                st.markdown(f"**{name}**")
            with c2:
                try:
                    st.caption(f"{(int(size) or 0)/1024:.1f} KB")
                except Exception:
                    st.caption("-")
            with c3:
                st.caption(str(updated))
            with c4:
                if st.button("📥 Carregar", key=f"fetch_{name}"):
                    with st.spinner(f"Baixando {name}..."):
                        content = download_backup_from_storage(name)
                    if content:
                        st.session_state["__dl_cache"][name] = content
                        st.toast("Backup carregado. Pronto para baixar.", icon="✅")
                    else:
                        st.warning("Não foi possível baixar esse arquivo.")
            with c5:
                content = st.session_state["__dl_cache"].get(name)
                st.download_button(
                    "⬇️ Baixar",
                    data=content if content else b"",
                    file_name=name,
                    mime="application/zip",
                    use_container_width=True,
                    disabled=(content is None),
                    key=f"dlbtn_{name}",
                )

    st.markdown("---")
    st.markdown("**♻️ Restaurar de backup (.zip)**")
    up = st.file_uploader("Selecione o arquivo .zip do backup", type=["zip"], key="restore_zip")
    mode = st.radio("Modo de restauração", ["upsert", "replace"], index=0,
                    help="replace apaga tudo e insere do zero (use com cautela).")

    confirm_ok = True
    if mode == "replace":
        st.warning("⚠️ 'replace' irá APAGAR os dados das tabelas antes de restaurar.")
        token = st.text_input("Digite APAGAR para confirmar:", value="", key="confirm_replace")
        confirm_ok = (token.strip().upper() == "APAGAR")

    if st.button("♻️ Restaurar", key="btn_restore", type="primary", disabled=(mode == "replace" and not confirm_ok)):
        if not up:
            st.warning("Selecione um .zip primeiro.")
        else:
            with st.spinner("Restaurando..."):
                rep = restore_from_zip(up.read(), mode=mode)
            if rep.get("status") == "ok":
                st.success("Restauração concluída!")
                for d in rep.get("details", []):
                    st.write("• " + d)
                st.toast("Caches limpos e dados restaurados.", icon="✅")
                st.rerun()
            else:
                st.error("Falha na restauração.")
                for d in rep.get("details", []):
                    st.write("• " + d)

    st.markdown("---")
    st.markdown("**🔌 Conexão Supabase**")
    try:
        _ = sb().table("hospitals").select("id", count="exact").limit(1).execute()
        st.success("Conexão OK.")
    except APIError as e:
        sb_debug_error(e, "Falha ao conectar/consultar Supabase.")

    st.markdown("</div>", unsafe_allow_html=True)
