# core/crud.py
from __future__ import annotations
import streamlit as st
import pandas as pd
from postgrest import APIError

from core.cache import TTL_LONG, TTL_MED, TTL_SHORT, invalidate_caches
from core.context import sb
from core.sb_client import sb_debug_error
from core.utils import to_ddmmyyyy, att_norm, att_to_number, safe_merge, pt_date_to_dt

@st.cache_data(ttl=TTL_LONG, show_spinner=False)
def get_hospitais(include_inactive: bool = False) -> list[str]:
    try:
        q = sb().table("hospitals").select("name, active")
        if not include_inactive:
            q = q.eq("active", 1)
        res = q.order("name").execute()
        return [r["name"] for r in (res.data or [])]
    except APIError as e:
        sb_debug_error(e, "Falha ao buscar hospitais.")
        return []

def get_internacao_by_atendimento(att):
    """Busca por atendimento normalizado e fallback por numero_internacao."""
    try:
        an = att_norm(att)
        res = sb().table("internacoes").select("*").eq("atendimento", an).execute()
        df = pd.DataFrame(res.data or [])
        if not df.empty:
            return df

        num = att_to_number(att)
        if num is not None:
            res2 = sb().table("internacoes").select("*").eq("numero_internacao", num).execute()
            return pd.DataFrame(res2.data or [])
        return pd.DataFrame()
    except APIError as e:
        sb_debug_error(e, "Falha ao consultar internação.")
        return pd.DataFrame()

def criar_internacao(hospital, atendimento, paciente, data, convenio):
    payload = {
        "hospital": hospital,
        "atendimento": att_norm(atendimento),
        "paciente": paciente,
        "data_internacao": to_ddmmyyyy(data),
        "convenio": convenio,
        "numero_internacao": att_to_number(atendimento)
    }
    try:
        res = sb().table("internacoes").insert(payload).execute()
        row = (res.data or [{}])[0]
        invalidate_caches()
        return int(row.get("id")) if row.get("id") is not None else None
    except APIError as e:
        sb_debug_error(e, "Falha ao criar internação.")
        return None

def atualizar_internacao(internacao_id, **kwargs):
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    if "data_internacao" in update_data:
        update_data["data_internacao"] = to_ddmmyyyy(update_data["data_internacao"])
    try:
        sb().table("internacoes").update(update_data).eq("id", int(internacao_id)).execute()
        invalidate_caches()
    except APIError as e:
        sb_debug_error(e, "Falha ao atualizar internação.")

def deletar_internacao(internacao_id: int) -> bool:
    """Exclui internação e filhos, com checagens pré/pós (compatível supabase-py)."""
    try:
        iid = int(internacao_id)

        pre_int = sb().table("internacoes").select("id").eq("id", iid).limit(1).execute()
        if not (pre_int.data or []):
            st.info("A internação já não existe (nada a excluir).")
            return True

        pre_procs = sb().table("procedimentos").select("id").eq("internacao_id", iid).execute()
        if len(pre_procs.data or []) > 0:
            sb().table("procedimentos").delete().eq("internacao_id", iid).execute()

            chk = sb().table("procedimentos").select("id").eq("internacao_id", iid).limit(1).execute()
            if chk.data:
                st.error("❌ Não foi possível excluir todos os procedimentos. Verifique RLS/Policies/FKs.")
                return False

        sb().table("internacoes").delete().eq("id", iid).execute()

        pos = sb().table("internacoes").select("id").eq("id", iid).limit(1).execute()
        ok = len(pos.data or []) == 0
        if ok:
            invalidate_caches()
            return True
        st.error("❌ Não foi possível excluir a internação. Verifique RLS/Policies/FKs.")
        return False

    except APIError as e:
        sb_debug_error(e, "Falha ao deletar internação.")
        return False

def criar_procedimento(internacao_id, data_proc, profissional, procedimento,
                       situacao="Pendente", observacao=None, is_manual=0,
                       aviso=None, grau_participacao=None):
    payload = {
        "internacao_id": int(internacao_id),
        "data_procedimento": to_ddmmyyyy(data_proc),
        "profissional": profissional,
        "procedimento": procedimento,
        "situacao": situacao or "Pendente",
        "observacao": observacao,
        "is_manual": int(is_manual or 0),
        "aviso": aviso,
        "grau_participacao": grau_participacao,
    }
    try:
        res = sb().table("procedimentos").insert(payload).execute()
        data = res.data or []
        invalidate_caches()
        if not data:
            return None
        return int(data[0].get("id")) if data[0].get("id") is not None else True
    except APIError as e:
        sb_debug_error(e, "Falha ao criar procedimento.")
        return None

def atualizar_procedimento(proc_id, procedimento=None, situacao=None,
                           observacao=None, grau_participacao=None, aviso=None):
    update_data = {}
    if procedimento is not None: update_data["procedimento"] = procedimento
    if situacao is not None: update_data["situacao"] = situacao
    if observacao is not None: update_data["observacao"] = observacao
    if grau_participacao is not None: update_data["grau_participacao"] = grau_participacao
    if aviso is not None: update_data["aviso"] = aviso
    if not update_data:
        return
    try:
        sb().table("procedimentos").update(update_data).eq("id", int(proc_id)).execute()
        invalidate_caches()
    except APIError as e:
        sb_debug_error(e, "Falha ao atualizar procedimento.")

def deletar_procedimento(proc_id: int) -> bool:
    try:
        pre = sb().table("procedimentos").select("id").eq("id", int(proc_id)).limit(1).execute()
        if not (pre.data or []):
            st.info("Registro já não existe (nada a excluir).")
            return True

        sb().table("procedimentos").delete().eq("id", int(proc_id)).execute()

        pos = sb().table("procedimentos").select("id").eq("id", int(proc_id)).limit(1).execute()
        ok = len(pos.data or []) == 0
        if ok:
            invalidate_caches()
            return True
        st.error("❌ Não foi possível excluir. Verifique RLS/Policies ou vínculos (FK).")
        return False

    except APIError as e:
        sb_debug_error(e, "Falha ao deletar procedimento.")
        return False

def quitar_procedimento(proc_id, data_quitacao=None, guia_amhptiss=None, valor_amhptiss=None,
                        guia_complemento=None, valor_complemento=None, quitacao_observacao=None):
    update_data = {
        "quitacao_data": to_ddmmyyyy(data_quitacao) if data_quitacao else None,
        "quitacao_guia_amhptiss": guia_amhptiss,
        "quitacao_valor_amhptiss": valor_amhptiss,
        "quitacao_guia_complemento": guia_complemento,
        "quitacao_valor_complemento": valor_complemento,
        "quitacao_observacao": quitacao_observacao,
        "situacao": "Finalizado",
    }
    update_data = {k: v for k, v in update_data.items() if v is not None or k == "situacao"}
    try:
        sb().table("procedimentos").update(update_data).eq("id", int(proc_id)).execute()
        invalidate_caches()
    except APIError as e:
        sb_debug_error(e, "Falha ao quitar procedimento.")

def reverter_quitacao(proc_id: int):
    update_data = {
        "quitacao_data": None,
        "quitacao_guia_amhptiss": None,
        "quitacao_valor_amhptiss": None,
        "quitacao_guia_complemento": None,
        "quitacao_valor_complemento": None,
        "quitacao_observacao": None,
        "situacao": "Enviado para pagamento",
    }
    try:
        sb().table("procedimentos").update(update_data).eq("id", int(proc_id)).execute()
        invalidate_caches()
    except APIError as e:
        sb_debug_error(e, "Falha ao reverter quitação.")

@st.cache_data(ttl=TTL_SHORT, show_spinner=False)
def get_procedimentos(internacao_id):
    try:
        res = sb().table("procedimentos").select("*").eq("internacao_id", int(internacao_id)).execute()
        return pd.DataFrame(res.data or [])
    except APIError as e:
        sb_debug_error(e, "Falha ao listar procedimentos.")
        return pd.DataFrame()

@st.cache_data(ttl=TTL_MED, show_spinner=False)
def listar_profissionais_cache() -> list[str]:
    try:
        res = sb().table("procedimentos").select("profissional").execute()
        df = pd.DataFrame(res.data or [])
        if "profissional" not in df.columns:
            return []
        return sorted({str(x).strip() for x in df["profissional"].dropna() if str(x).strip()})
    except APIError:
        return []

@st.cache_data(ttl=TTL_MED, show_spinner=False)
def home_fetch_base_df(use_db_view: bool = False) -> pd.DataFrame:
    """Base Procedimentos + Internações para Home."""
    if use_db_view:
        try:
            res = sb().table("vw_procedimentos_internacoes").select(
                "procedimento_id, internacao_id, data_procedimento, procedimento, profissional, situacao, aviso, grau_participacao, "
                "atendimento, paciente, hospital, convenio, data_internacao"
            ).execute()
            df = pd.DataFrame(res.data or [])
            if "procedimento_id" in df.columns and "id" not in df.columns:
                df = df.rename(columns={"procedimento_id": "id"})
            return df
        except APIError:
            pass

    try:
        res_p = sb().table("procedimentos").select(
            "id, internacao_id, data_procedimento, procedimento, profissional, situacao, aviso, grau_participacao"
        ).execute()
        df_p = pd.DataFrame(res_p.data or [])
        if df_p.empty:
            return pd.DataFrame()

        ids = sorted(set(int(x) for x in df_p["internacao_id"].dropna().tolist()))
        res_i = sb().table("internacoes").select("id, atendimento, paciente, hospital, convenio, data_internacao").in_("id", ids).execute() if ids else None
        df_i = pd.DataFrame(res_i.data or []) if res_i else pd.DataFrame()

        return safe_merge(
            df_p,
            df_i[["id","atendimento","paciente","hospital","convenio","data_internacao"]] if not df_i.empty else df_i,
            left_on="internacao_id",
            right_on="id",
            how="left",
            suffixes=("", "_int"),
        )
    except APIError as e:
        sb_debug_error(e, "Falha ao carregar dados para a Home.")
        return pd.DataFrame()

@st.cache_data(ttl=TTL_MED, show_spinner=False)
def rel_cirurgias_base_df(use_db_view: bool = False) -> pd.DataFrame:
    if use_db_view:
        try:
            res = sb().table("vw_procedimentos_internacoes").select(
                "procedimento_id, internacao_id, data_procedimento, aviso, profissional, procedimento, grau_participacao, situacao, "
                "hospital, atendimento, paciente, convenio"
            ).in_("procedimento", ["Cirurgia / Procedimento", "Parecer"]).execute()
            df = pd.DataFrame(res.data or [])
            if "procedimento_id" in df.columns and "id" not in df.columns:
                df = df.rename(columns={"procedimento_id": "id"})
            return df
        except APIError:
            pass

    try:
        resp = sb().table("procedimentos").select(
            "internacao_id, data_procedimento, aviso, profissional, procedimento, grau_participacao, situacao"
        ).in_("procedimento", ["Cirurgia / Procedimento", "Parecer"]).execute()
        dfp = pd.DataFrame(resp.data or [])
        if dfp.empty:
            return pd.DataFrame()
        ids = sorted(set(int(x) for x in dfp["internacao_id"].dropna().tolist()))
        resi = sb().table("internacoes").select("id, hospital, atendimento, paciente, convenio").in_("id", ids).execute() if ids else None
        dfi = pd.DataFrame(resi.data or []) if resi else pd.DataFrame()
        return safe_merge(dfp, dfi, left_on="internacao_id", right_on="id", how="left")
    except APIError as e:
        sb_debug_error(e, "Falha ao carregar dados para Relatório.")
        return pd.DataFrame()

@st.cache_data(ttl=TTL_MED, show_spinner=False)
def rel_quitacoes_base_df(use_db_view: bool = False) -> pd.DataFrame:
    if use_db_view:
        try:
            res = sb().table("vw_procedimentos_internacoes").select(
                "procedimento_id, internacao_id, data_procedimento, profissional, grau_participacao, situacao, "
                "quitacao_data, quitacao_guia_amhptiss, quitacao_guia_complemento, "
                "quitacao_valor_amhptiss, quitacao_valor_complemento, "
                "hospital, atendimento, paciente, convenio"
            ).not_.is_("quitacao_data", None).eq("procedimento", "Cirurgia / Procedimento").execute()
            df = pd.DataFrame(res.data or [])
            if "procedimento_id" in df.columns and "id" not in df.columns:
                df = df.rename(columns={"procedimento_id": "id"})
            return df
        except APIError:
            pass

    try:
        resp = sb().table("procedimentos").select(
            "internacao_id, data_procedimento, profissional, grau_participacao, situacao, "
            "quitacao_data, quitacao_guia_amhptiss, quitacao_guia_complemento, "
            "quitacao_valor_amhptiss, quitacao_valor_complemento"
        ).eq("procedimento", "Cirurgia / Procedimento").not_.is_("quitacao_data", None).execute()
        dfp = pd.DataFrame(resp.data or [])
        if dfp.empty:
            return pd.DataFrame()
        ids = sorted(set(int(x) for x in dfp["internacao_id"].dropna().tolist()))
        resi = sb().table("internacoes").select("id, hospital, atendimento, paciente, convenio").in_("id", ids).execute() if ids else None
        dfi = pd.DataFrame(resi.data or []) if resi else pd.DataFrame()
        return safe_merge(dfp, dfi, left_on="internacao_id", right_on="id", how="left")
    except APIError as e:
        sb_debug_error(e, "Falha ao carregar dados de quitações.")
        return pd.DataFrame()

@st.cache_data(ttl=TTL_MED, show_spinner=False)
def quitacao_pendentes_base_df(use_db_view: bool = False) -> pd.DataFrame:
    tipos = ["Cirurgia / Procedimento", "Parecer"]
    if use_db_view:
        try:
            res = sb().table("vw_procedimentos_internacoes").select(
                "procedimento_id, internacao_id, data_procedimento, profissional, aviso, situacao, procedimento, "
                "quitacao_data, quitacao_guia_amhptiss, quitacao_valor_amhptiss, "
                "quitacao_guia_complemento, quitacao_valor_complemento, quitacao_observacao, "
                "hospital, atendimento, paciente, convenio"
            ).in_("procedimento", tipos).eq("situacao", "Enviado para pagamento").execute()
            df = pd.DataFrame(res.data or [])
            if "procedimento_id" in df.columns and "id" not in df.columns:
                df = df.rename(columns={"procedimento_id": "id"})
            return df
        except APIError:
            pass

    try:
        resp = sb().table("procedimentos").select(
            "id, internacao_id, data_procedimento, profissional, aviso, situacao, procedimento, "
            "quitacao_data, quitacao_guia_amhptiss, quitacao_valor_amhptiss, "
            "quitacao_guia_complemento, quitacao_valor_complemento, quitacao_observacao"
        ).in_("procedimento", tipos).eq("situacao", "Enviado para pagamento").execute()
        dfp = pd.DataFrame(resp.data or [])
        if dfp.empty:
            return pd.DataFrame()
        ids = sorted(set(int(x) for x in dfp["internacao_id"].dropna().tolist()))
        resi = sb().table("internacoes").select("id, hospital, atendimento, paciente, convenio").in_("id", ids).execute() if ids else None
        dfi = pd.DataFrame(resi.data or []) if resi else pd.DataFrame()
        return safe_merge(dfp, dfi, left_on="internacao_id", right_on="id", how="left", suffixes=("", "_int"))
    except APIError as e:
        sb_debug_error(e, "Falha ao carregar pendências de quitação.")
        return pd.DataFrame()
