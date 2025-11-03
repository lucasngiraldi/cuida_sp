# db.py  (backend YAML criptografado no Google Drive)
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import base64, copy, bcrypt, streamlit as st

from yaml_store import download_users_doc, upload_users_doc

_STORE: Dict[str, Any] = {"users": []}
_LOADED = False

def _utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _norm_email(e: str) -> str:
    return (e or "").strip().lower()

def _next_id() -> int:
    return (max([u.get("id", 0) for u in _STORE["users"]] or [0]) + 1)

def _find_idx_by_email(email: str) -> int:
    e = _norm_email(email)
    for i, u in enumerate(_STORE["users"]):
        if _norm_email(u.get("email")) == e:
            return i
    return -1

def _ensure_loaded():
    global _LOADED, _STORE
    if _LOADED: return
    _STORE = download_users_doc()
    for u in _STORE["users"]:
        u.setdefault("id", _next_id())
        u["email"] = _norm_email(u.get("email"))
        u.setdefault("nome", "")
        u.setdefault("papel", "Leitor")
        u.setdefault("ativo", 1)
        u.setdefault("last_login", None)
        # normaliza campo do hash como string base64
        if isinstance(u.get("hash_senha"), (bytes, bytearray)):
            u["hash_senha"] = base64.b64encode(u["hash_senha"]).decode()
    # seções auxiliares ---------------------------------------------
    if "metrics" not in _STORE:
        _STORE["metrics"] = {"monthly_accesses": {}}
    _LOADED = True

def init_db():
    """Carrega para memória e faz bootstrap de admin (se fornecido em secrets)."""
    _ensure_loaded()
    # bootstrap admin opcional
    adm = st.secrets.get("admin", {})
    email = _norm_email(adm.get("email", ""))
    pwd   = adm.get("password")
    nome  = adm.get("name", "Admin")
    papel = adm.get("role", "Admin")
    if email and pwd and _find_idx_by_email(email) == -1:
        try:
            h = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt())
            create_user(nome, email, h, papel, 1)
        except Exception:
            pass

def _persist():
    upload_users_doc(_STORE)

def create_user(nome: str, email: str, hash_senha: bytes | str,
                papel: str = "Leitor", ativo: int = 1) -> int:
    _ensure_loaded()
    if _find_idx_by_email(email) != -1:
        raise ValueError("E-mail já cadastrado.")
    if isinstance(hash_senha, (bytes, bytearray)):
        hash_b64 = base64.b64encode(hash_senha).decode()
    else:
        hash_b64 = str(hash_senha)
    uid = _next_id()
    _STORE["users"].append({
        "id": uid,
        "nome": nome,
        "email": _norm_email(email),
        "hash_senha": hash_b64,            # armazenado como base64
        "papel": papel,
        "ativo": int(ativo),
        "last_login": None,
        "created_at": _utcnow(),
    })
    _persist()
    return uid

def get_user_by_email(email: str) -> Optional[Dict]:
    _ensure_loaded()
    i = _find_idx_by_email(email)
    if i == -1:
        return None
    u = copy.deepcopy(_STORE["users"][i])
    # devolve hash como bytes (compatível com bcrypt.checkpw do auth.py)
    try:
        u["hash_senha"] = base64.b64decode(u.get("hash_senha") or "")
    except Exception:
        u["hash_senha"] = b""
    return {
        "id": u["id"], "nome": u["nome"], "email": u["email"],
        "hash_senha": u["hash_senha"], "papel": u["papel"],
        "ativo": u["ativo"], "last_login": u.get("last_login"),
    }

def record_login(email: str):
    _ensure_loaded()

    # 1) atualiza “last_login” do usuário ---------------------------
    idx = _find_idx_by_email(email)
    if idx != -1:
        _STORE["users"][idx]["last_login"] = _utcnow()

    # 2) incrementa contador mensal --------------------------------
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")   # ex.: 2025-11
    m = _STORE.setdefault("metrics", {}).setdefault("monthly_accesses", {})
    m[month_key] = m.get(month_key, 0) + 1

    _persist()

def get_month_access_count(year: int | None = None,
                           month: int | None = None) -> int:
    """
    Devolve a quantidade de logins no mês indicado (UTC).
    Se ano/mês não forem informados, usa o mês atual.
    """
    _ensure_loaded()
    now = datetime.now(timezone.utc)
    key = f"{year or now.year}-{(month or now.month):02d}"
    return _STORE.get("metrics", {}).get("monthly_accesses", {}).get(key, 0)


def list_users() -> List[Dict]:
    _ensure_loaded()
    out = []
    for u in sorted(_STORE["users"], key=lambda x: x.get("id", 0), reverse=True):
        out.append({
            "id": u["id"], "nome": u["nome"], "email": u["email"],
            "papel": u["papel"], "ativo": u["ativo"], "last_login": u.get("last_login"),
        })
    return out

def update_user(uid: int, nome: str, email: str, papel: str, ativo: int):
    _ensure_loaded()
    # checa conflito de e-mail
    e = _norm_email(email)
    for u in _STORE["users"]:
        if u["id"] != uid and _norm_email(u["email"]) == e:
            raise ValueError("E-mail já em uso por outro usuário.")
    for u in _STORE["users"]:
        if u["id"] == uid:
            u["nome"] = nome
            u["email"] = e
            u["papel"] = papel
            u["ativo"] = int(ativo)
            _persist()
            return

def update_password(uid: int, hash_senha: bytes | str):
    _ensure_loaded()
    if isinstance(hash_senha, (bytes, bytearray)):
        hash_b64 = base64.b64encode(hash_senha).decode()
    else:
        hash_b64 = str(hash_senha)
    for u in _STORE["users"]:
        if u["id"] == uid:
            u["hash_senha"] = hash_b64
            _persist()
            return

def delete_user(uid: int):
    _ensure_loaded()
    _STORE["users"] = [u for u in _STORE["users"] if u["id"] != uid]
    _persist()
