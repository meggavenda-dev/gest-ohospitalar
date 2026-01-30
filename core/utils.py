# core/utils.py
from __future__ import annotations
import re
import pandas as pd
from datetime import date, datetime
from typing import Optional

def pt_date_to_dt(s) -> Optional[date]:
    s = str(s).strip() if s is not None else ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def to_ddmmyyyy(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    d = pt_date_to_dt(value)
    return d.strftime("%d/%m/%Y") if d else str(value)

def to_float_or_none(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def format_currency_br(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "R$ 0,00"
    try:
        v = float(v)
        s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except Exception:
        return f"R$ {v}"

def att_norm(v) -> str:
    """Somente dígitos, sem zeros à esquerda. Retorna '0' se vazio."""
    s = re.sub(r"\D", "", str(v or ""))
    s = s.lstrip("0")
    return s if s else "0"

def att_to_number(v):
    """Compatível com schema atual (float)."""
    s = re.sub(r"\D", "", str(v or ""))
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None

def fmt_id_str(x) -> str:
    """Remove '.0', notação científica; preserva strings não numéricas."""
    if x is None:
        return ""
    s = str(x).strip()
    if s == "":
        return ""
    try:
        f = float(s)
        if abs(f - int(f)) < 1e-9:
            return str(int(f))
        return ("{0}".format(f)).replace(",", ".")
    except Exception:
        return s

def safe_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_on: str,
    right_on: str,
    how: str = "left",
    suffixes=("", "_right"),
) -> pd.DataFrame:
    if not isinstance(left, pd.DataFrame) or left.empty:
        return left if isinstance(left, pd.DataFrame) else pd.DataFrame()

    if not isinstance(right, pd.DataFrame) or right.empty or (right_on not in right.columns):
        right = pd.DataFrame(columns=[right_on])

    if left_on not in left.columns:
        return left

    try:
        return left.merge(right, left_on=left_on, right_on=right_on, how=how, suffixes=suffixes)
    except KeyError:
        return left

def to_bool(x) -> bool:
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in ("1", "true", "yes", "y", "on")
