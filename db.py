# db.py  (backend YAML criptografado no Google Drive)
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import base64, copy, bcrypt, streamlit as st

from yaml_store import download_users_doc, upload_users_doc

_STORE: Dict[str, Any] = {"users": []}
_LOADED = False

from yaml_store import download_yaml_optional
_LOG_CFG = download_yaml_optional(
    st.secrets["app"].get("log_yaml_file_id"),
    {"retention_days": 30, "max_table_rows": 100}
)
_RETENTION_DAYS = _LOG_CFG["retention_days"]

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
    _STORE.setdefault("access_logs", [])  # lista de dicionários
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
    """
    Persistência segura:
    - Baixa o doc atual do Drive
    - Mescla access_logs (dedupe por email+ts)
    - (Opcional) mantém users/metrics do _STORE como fonte principal
    - Sobe de volta
    """
    global _STORE

    try:
        remote = download_users_doc()

        # --- merge access_logs (não deixar sobrescrever) ---
        remote_logs = remote.get("access_logs", []) or []
        local_logs  = _STORE.get("access_logs", []) or []

        merged = {}
        for r in remote_logs:
            ts = r.get("ts")
            em = _norm_email(r.get("email"))
            if ts and em:
                merged[(em, ts)] = {"email": em, "ts": ts}
        for r in local_logs:
            ts = r.get("ts")
            em = _norm_email(r.get("email"))
            if ts and em:
                merged[(em, ts)] = {"email": em, "ts": ts}

        remote["access_logs"] = sorted(merged.values(), key=lambda x: x["ts"], reverse=True)

        # --- mantém users do _STORE (admin pode ter alterado usuários) ---
        remote["users"] = _STORE.get("users", remote.get("users", []))

        # --- mantém metrics do _STORE; se quiser, dá pra recalcular depois ---
        remote["metrics"] = _STORE.get("metrics", remote.get("metrics", {"monthly_accesses": {}}))

        upload_users_doc(remote)

        # sincroniza memória com o que foi salvo
        _STORE = remote

    except Exception:
        # fallback antigo
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
    """
    • Registra o login do usuário.
    • Atualiza o campo last_login na lista 'users'.
    • Acrescenta um registro em 'access_logs' e elimina logins
      mais antigos que RETENTION_DAYS.
    • Incrementa o contador mensal em metrics.monthly_accesses.
    """
    _ensure_loaded()                                     # garante _STORE em memória

    # ------------------------------------------------------------------
    # 1) LOG detalhado de acesso (lista access_logs)
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    _STORE.setdefault("access_logs", []).append({
        "email": email,
        "ts": now.isoformat()           # carimbo ISO-8601 em UTC
    })

    # — prune automático (mantém só os últimos N dias) -----------------
    cutoff = now - timedelta(days=_RETENTION_DAYS)       # _RETENTION_DAYS vem do yaml
    _STORE["access_logs"] = [
        row for row in _STORE["access_logs"]
        if datetime.fromisoformat(row["ts"]) >= cutoff
    ]

    # ------------------------------------------------------------------
    # 2) Atualiza last_login do próprio usuário
    # ------------------------------------------------------------------
    idx = _find_idx_by_email(email)
    if idx != -1:
        _STORE["users"][idx]["last_login"] = now.isoformat()

    # ------------------------------------------------------------------
    # 3) Incrementa acumulador mensal
    # ------------------------------------------------------------------
    month_key = now.strftime("%Y-%m")                    # ex.: '2025-11'
    m = _STORE.setdefault("metrics", {}).setdefault("monthly_accesses", {})
    m[month_key] = m.get(month_key, 0) + 1

    # ------------------------------------------------------------------
    # 4) Persiste tudo de volta ao YAML (Google Drive ou local)
    # ------------------------------------------------------------------
    _persist()

def _prune_access_logs():
    """
    Mantém apenas registros dentro da janela de retenção configurada.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
    _STORE["access_logs"] = [
        row for row in _STORE["access_logs"]
        if datetime.fromisoformat(row["ts"]) >= cutoff
    ]

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

def get_recent_logs(days: int = 30):
    """
    Devolve lista de dicts {email, ts} dentro do período solicitado,
    ordenada do mais novo para o mais antigo.
    """
    _ensure_loaded()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    logs = [
        row for row in _STORE["access_logs"]
        if datetime.fromisoformat(row["ts"]) >= cutoff
    ]
    return sorted(logs, key=lambda r: r["ts"], reverse=True)
