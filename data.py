# data.py
import streamlit as st
import gspread
import pandas as pd
import unicodedata
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

def _gc():
    info = st.secrets.get("gcp_service_account", {})
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)

def _open_sheet():
    ss_id = st.secrets.get("sheets", {}).get("spreadsheet_id")
    ss_name = st.secrets.get("sheets", {}).get("spreadsheet_name", "Cuida SP - Database")
    gc = _gc()
    return gc.open_by_key(ss_id) if ss_id else gc.open(ss_name)

def _norm(s: str) -> str:
    # minúsculas, sem acentos, trim e remove duplos espaços
    s0 = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")
    return " ".join(s0.lower().strip().split())

def _resolve_ws(sh, desired: str):
    """Tenta achar a worksheet pelo nome exato e depois por nome normalizado (sem acento)."""
    try:
        return sh.worksheet(desired)
    except Exception:
        want = _norm(desired)
        for ws in sh.worksheets():
            if _norm(ws.title) == want:
                return ws
        raise  # deixa a exceção original subir se não acharmos nada

def _read_ws(ws) -> pd.DataFrame:
    # tenta com a 1ª linha como header
    vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame()
    # se primeira linha tem pelo menos 2 colunas não vazias, consideramos header
    header = vals[0]
    if sum(1 for h in header if h and h.strip()) >= 2:
        df = pd.DataFrame(vals[1:], columns=header)
    else:
        # procurar primeira linha com mais colunas preenchidas e usá-la como header
        best_i, best_nonempty = 0, 0
        for i, row in enumerate(vals[:10]):  # olha as 10 primeiras
            cnt = sum(1 for c in row if c and c.strip())
            if cnt > best_nonempty:
                best_nonempty = cnt
                best_i = i
        header = vals[best_i]
        df = pd.DataFrame(vals[best_i+1:], columns=header)
    # remove colunas completamente vazias
    df = df.loc[:, [c for c in df.columns if c and str(c).strip()]]
    return df

@st.cache_data(ttl=st.secrets.get("app", {}).get("cache_ttl_seconds", 300), show_spinner=True)
def read_all_tables():
    sh = _open_sheet()
    cfg = st.secrets.get("sheets", {})
    ws_map = {
        "voluntarios": cfg.get("vol_ws", "Voluntários"),
        "acoes": cfg.get("acoes_ws", "Ações"),
        "doacoes": cfg.get("doa_ws", "Doações"),
        "enderecos": cfg.get("dim_enderecos_ws", "Dim_enderecos"),
    }
    out = {}
    for key, desired in ws_map.items():
        try:
            ws = _resolve_ws(sh, desired)
            out[key] = _read_ws(ws)
        except Exception as e:
            # Log leve e dataframe vazio
            st.debug(f"[read_all_tables] Falha ao abrir '{desired}': {e}")
            out[key] = pd.DataFrame()
    return out

def enum_options():
    return {
        "posicoes": ["Voluntário", "Coordenador"],
        "status_acao": ["Concluída", "Ativa", "Suspensa"],
        "tipo_doador": ["Pessoa Física", "Pessoa Jurídica"],
        "forma_doacao": ["Pix", "Transferência", "Dinheiro", "Bens", "Outro"],
        "recorrente": ["Sim", "Não"],
    }
