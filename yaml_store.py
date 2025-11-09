import io, yaml, os
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from crypto import encrypt_text, decrypt_text

SCOPES = ["https://www.googleapis.com/auth/drive"]

def _get_secrets():
    # tenta st.secrets; se não existir (ex.: script CLI), tenta .streamlit/secrets.toml
    try:
        return dict(st.secrets)
    except Exception:
        try:
            import toml
            p = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
            return toml.load(p) if os.path.exists(p) else {}
        except Exception:
            return {}

def _drive():
    sec = _get_secrets()
    info = dict(sec.get("gcp_service_account", {}))
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

def _file_id() -> str:
    sec = _get_secrets()
    return sec.get("app", {}).get("users_yaml_file_id")

def _download_raw() -> bytes:
    service = _drive()
    req = service.files().get_media(fileId=_file_id())
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()

def _upload_raw(data: bytes):
    service = _drive()
    buf = io.BytesIO(data)
    media = MediaIoBaseUpload(buf, mimetype="application/octet-stream", resumable=True)
    service.files().update(fileId=_file_id(), media_body=media).execute()

def download_users_doc() -> dict:
    raw = _download_raw()
    if not raw:
        return {"users": []}

    candidates = []

    # 1) tenta decriptar (conteúdo esperado)
    try:
        txt = decrypt_text(raw)       # retorna str
        candidates.append(txt)
    except Exception:
        pass

    # 2) tenta interpretar como texto puro (caso o arquivo esteja em plaintext)
    try:
        candidates.append(raw.decode("utf-8", errors="ignore"))
    except Exception:
        pass

    # tenta carregar qualquer candidato como YAML e garantir dict
    for txt in candidates:
        try:
            data = yaml.safe_load(txt)
            if isinstance(data, dict):
                data.setdefault("users", [])
                return data
        except Exception:
            continue

    # fallback final: estrutura vazia válida
    return {"users": []}

def upload_users_doc(doc: dict):
    txt = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    blob = encrypt_text(txt)  # sempre criptografado no Drive
    _upload_raw(blob)

def download_yaml_optional(file_id: str | None, default: dict):
    """
    Lê um YAML pelo file_id; se faltar ou der erro, devolve `default`.
    """
    if not file_id:
        return default
    try:
        return download_yaml(file_id)
    except Exception:
        return default
