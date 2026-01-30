# core/context.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from supabase import Client

@dataclass
class AppContext:
    supabase: Client
    admin_client: Client

_ctx: Optional[AppContext] = None

def init_context(supabase: Client, admin_client: Client) -> None:
    global _ctx
    _ctx = AppContext(supabase=supabase, admin_client=admin_client)

def get_ctx() -> AppContext:
    if _ctx is None:
        raise RuntimeError("Contexto não inicializado. Chame init_context() no app.py.")
    return _ctx

def sb() -> Client:
    return get_ctx().supabase

def admin() -> Client:
    return get_ctx().admin_client
