# core/backup.py
from __future__ import annotations
import io, json, zipfile, hashlib
import pandas as pd
import streamlit as st
from datetime import datetime
from typing import List, Dict, Any
from postgrest import APIError

from core.context import sb, admin
from core.sb_client import sb_debug_error
from core.cache import invalidate_caches
from core.utils import to_ddmmyyyy, att_norm, att_to_number

BUCKET = st.secrets.get("STORAGE_BACKUP_BUCKET", "backups")

def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _fetch_all_rows(table: str, cols: str = "*", page_size: int = 1000,
                    filters: Dict[str, Any] = None, client=None) -> List[Dict[str, Any]]:
    client = client or sb()
    rows, start = [], 0
    while True:
        q = client.table(table).select(cols).range(start, start + page_size - 1)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        res = q.execute()
        chunk = res.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows

def export_tables_to_zip(tables: List[str]) -> bytes:
    """Gera ZIP com meta.json + {t}.json + {t}.csv. Usa admin() para não sofrer RLS."""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "generated_at": datetime.now().isoformat(),
            "tables": tables,
            "app": "internacoes_supabase",
            "version": "v1",
        }
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

        for t in tables:
            data = _fetch_all_rows(t, "*", client=admin())
            df = pd.DataFrame(data)
            zf.writestr(f"{t}.json", json.dumps(data, ensure_ascii=False, indent=2))
            zf.writestr(f"{t}.csv", df.to_csv(index=False).encode("utf-8-sig") if not df.empty else b"")
    return mem.getvalue()

def upload_zip_to_storage(zip_bytes: bytes, filename: str) -> bool:
    """Envia ZIP ao bucket (admin client)."""
    try:
        admin().storage.from_(BUCKET).upload(
            filename,
            zip_bytes,
            {"content-type": "application/zip", "upsert": True}
        )
        return True
    except Exception as e:
        st.error(f"Falha ao enviar ao Storage: {e}")
        return False

def list_backups_from_storage(prefix: str = "", limit: int = 1000, offset: int = 0) -> list[dict]:
    """Lista .zip do bucket, ordena desc por data quando disponível."""
    try:
        options = {
            "limit": limit,
            "offset": offset,
            "sortBy": {"column": "updated_at", "order": "desc"},
        }
        res = admin().storage.from_(BUCKET).list(path=prefix or "", options=options)
        files = [f for f in res if isinstance(f, dict) and f.get("name", "").lower().endswith(".zip")]

        def _when(x: dict):
            return x.get("updated_at") or x.get("last_modified") or x.get("created_at") or ""
        files.sort(key=_when, reverse=True)
        return files
    except Exception as e:
        st.error(f"Falha ao listar backups no Storage: {e}")
        return []

def download_backup_from_storage(name: str) -> bytes:
    try:
        return admin().storage.from_(BUCKET).download(name)
    except Exception as e:
        st.error(f"Falha no download do Storage: {e}")
        return b""

def _json_from_zip(zf: zipfile.ZipFile, name: str):
    try:
        with zf.open(name) as f:
            return json.loads(f.read().decode("utf-8"))
    except KeyError:
        return None

def restore_from_zip(zip_bytes: bytes, mode: str = "upsert") -> Dict[str, Any]:
    """
    Restaura JSON do ZIP.
    mode:
      - upsert: insere/atualiza por id
      - replace: apaga tudo e reinsere (CUIDADO)
    Ordem: hospitals -> internacoes -> procedimentos
    """
    report = {"status": "ok", "details": []}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
            meta = _json_from_zip(zf, "meta.json") or {}
            tables = meta.get("tables") or ["hospitals", "internacoes", "procedimentos"]

            data_map = {}
            for t in tables:
                arr = _json_from_zip(zf, f"{t}.json")
                if arr is None:
                    arr = []
                data_map[t] = arr or []

            ordered = [t for t in ["hospitals", "internacoes", "procedimentos"] if t in data_map]

            # replace: apaga filhos antes
            if mode == "replace":
                for t in reversed(ordered):
                    try:
                        # delete-all "seguro" por id>0
                        admin().table(t).delete().gt("id", 0).execute()
                        report["details"].append(f"{t}: apagado")
                    except APIError as e:
                        report["status"] = "error"
                        report["details"].append(f"{t}: falha ao apagar - {getattr(e,'message',e)}")
                        return report

            def _chunked_upsert(table: str, rows: List[Dict[str, Any]], chunk: int = 500) -> int:
                if not rows:
                    return 0
                total = 0
                for i in range(0, len(rows), chunk):
                    batch = rows[i:i+chunk]
                    try:
                        admin().table(table).upsert(batch, on_conflict="id").execute()
                        total += len(batch)
                    except APIError as e:
                        report["status"] = "error"
                        report["details"].append(f"{table}: falha no upsert - {getattr(e,'message',e)}")
                        return total
                return total

            if "hospitals" in ordered:
                c = _chunked_upsert("hospitals", data_map["hospitals"])
                report["details"].append(f"hospitals: {c} registro(s) restaurado(s).")

            if "internacoes" in ordered:
                rows = data_map["internacoes"]
                for r in rows:
                    if "data_internacao" in r:
                        r["data_internacao"] = to_ddmmyyyy(r["data_internacao"])
                    if "atendimento" in r:
                        r["atendimento"] = att_norm(r["atendimento"])
                    if "numero_internacao" in r:
                        r["numero_internacao"] = att_to_number(r["numero_internacao"])
                c = _chunked_upsert("internacoes", rows)
                report["details"].append(f"internacoes: {c} registro(s) restaurado(s).")

            if "procedimentos" in ordered:
                rows = data_map["procedimentos"]
                for r in rows:
                    if "data_procedimento" in r:
                        r["data_procedimento"] = to_ddmmyyyy(r["data_procedimento"])
                    r["procedimento"] = r.get("procedimento") or "Cirurgia / Procedimento"
                    r["situacao"] = r.get("situacao") or "Pendente"
                    if "is_manual" in r:
                        try:
                            r["is_manual"] = int(r["is_manual"] or 0)
                        except Exception:
                            r["is_manual"] = 0
                c = _chunked_upsert("procedimentos", rows)
                report["details"].append(f"procedimentos: {c} registro(s) restaurado(s).")

            invalidate_caches()
            return report

    except zipfile.BadZipFile:
        return {"status": "error", "details": ["Arquivo ZIP inválido."]}
    except Exception as e:
        return {"status": "error", "details": [f"Exceção: {e}"]}
