from __future__ import annotations

import base64
import bcrypt
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

import requests
import streamlit as st

from db import init_db, get_user_by_email, record_login  # create_user opcional
from ui_components import inject_css_once

# =========================
# ====== CONFIGURAÇÃO =====
# =========================

COOKIE_NAME = "cuida_sp_auth"
COOKIE_COMPONENT_KEY = "cookie_mgr_component"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
REMEMBER_DAYS = 14

# Secrets
RECAPTCHA_SITE_KEY = st.secrets.get("recaptcha", {}).get("site_key", "")
RECAPTCHA_SECRET = st.secrets.get("recaptcha", {}).get("secret_key", "")
COOKIE_SIGN_KEY = st.secrets.get("app", {}).get("cookie_sign_key", "")

# Cookie manager opcional (fallback seguro)
try:
    import extra_streamlit_components as stx
except Exception:
    stx = None


# =========================
# ====== UTILITÁRIOS ======
# =========================
# Fundo da tela de login (aplica só via CSS, sem mexer no layout)
def _apply_login_background():
    from pathlib import Path
    import base64

    # tenta o caminho que você passou + alternativas comuns
    candidates = [
        Path(r"C:\Users\Lucas\PycharmProjects\Cuidados project\Foto_auth.jpg"),
        Path.cwd() / "Foto_auth.jpg",
        Path.cwd() / "assets" / "Foto_auth.jpg",
        Path(__file__).parent / "Foto_auth.jpg",
        Path("/mnt/data/Foto_auth.jpg"),
    ]
    img_path = next((p for p in candidates if p.exists()), None)
    if not img_path:
        return  # silencioso se não achar

    mime = "image/jpeg"  # é .jpg
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    # aplica no container principal do Streamlit
    st.markdown(
        f"""
        <style>
        div[data-testid="stAppViewContainer"] {{
            background: linear-gradient(rgba(0,0,0,1), rgba(255,255,255,0.3)),
                        url("data:{mime};base64,{b64}");
            background-repeat: no-repeat;
            background-position: center center;
            background-attachment: fixed;
            background-size: cover;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("""
    <style>
    /* ====== Textos brancos ====== */
    html, body, [class*="css"] h1, h2, h3, h4, h5, h6, p, label, span, div, .stMarkdown, .stText, .stCheckbox label {
        color: #fff !important;
    }

    /* Placeholder dos inputs */
    input::placeholder {
        color: rgba(255,255,255,0.7) !important;
    }

    /* Bordas e fundo dos inputs mais escuras para contraste */
    .stTextInput>div>div>input, .stPasswordInput>div>div>input {
        background-color: rgba(0,0,0,0.35) !important;
        border: 1px solid rgba(255,255,255,0.4) !important;
        color: #fff !important;
    }

    /* Checkboxes */
    .stCheckbox input[type=checkbox] {
        accent-color: #fff !important;
    }

    /* Botão principal vermelho continua igual, mas texto branco */
    .stButton>button {
        color: #fff !important;
    }

    /* ====== Barra superior preta ====== */
    header[data-testid="stHeader"] {
        background-color: #000 !important;
    }
    header[data-testid="stHeader"] * {
        color: #fff !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _cookie_mgr():
    """Obtém/cria o gerenciador de cookies (se disponível)."""
    if not stx:
        return None
    if "_cookie_mgr" not in st.session_state:
        st.session_state["_cookie_mgr"] = stx.CookieManager(key=COOKIE_COMPONENT_KEY)
    return st.session_state["_cookie_mgr"]


def _sign_payload(data: dict) -> str:
    """Assina o payload (HMAC-SHA256) para cookie."""
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if not COOKIE_SIGN_KEY:
        # Sem chave -> não assina (apenas base64) — ainda funciona, mas sem integridade.
        return base64.urlsafe_b64encode(raw).decode("utf-8")
    mac = hmac.new(COOKIE_SIGN_KEY.encode("utf-8"), raw, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(raw + b"." + mac).decode("utf-8")
    return token


def _verify_payload(token: str) -> Optional[dict]:
    """Verifica e decodifica o payload assinado do cookie."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8"))
        if not COOKIE_SIGN_KEY:
            return json.loads(raw.decode("utf-8"))
        raw_msg, mac = raw.rsplit(b".", 1)
        expected = hmac.new(COOKIE_SIGN_KEY.encode("utf-8"), raw_msg, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            return None
        return json.loads(raw_msg.decode("utf-8"))
    except Exception:
        return None


def _persist_cookie(user_data: dict):
    """Persiste cookie 'lembrar por 14 dias' (se possível)."""
    mgr = _cookie_mgr()
    if not mgr:
        return  # fallback silencioso
    payload = {
        "email": user_data.get("email"),
        "nome": user_data.get("nome"),
        "papel": user_data.get("papel"),
        "iat": int(time.time()),
        "exp": int(time.time() + REMEMBER_DAYS * 24 * 3600),
    }
    token = _sign_payload(payload)
    mgr.set(COOKIE_NAME, token, expires_at=datetime.now(timezone.utc) + timedelta(days=REMEMBER_DAYS), key="persist_cookie")


def _bootstrap_from_cookie() -> Optional[dict]:
    """Tenta autenticar a sessão a partir do cookie persistido."""
    mgr = _cookie_mgr()
    if not mgr:
        return None
    token = mgr.get(COOKIE_NAME) or ""
    if not token:
        return None
    data = _verify_payload(token)
    if not data:
        return None
    if int(time.time()) >= int(data.get("exp", 0)):
        try:
            mgr.delete(COOKIE_NAME)
        except Exception:
            pass
        return None
    # Revalidação leve (apenas checa se usuário ainda existe/ativo)
    u = get_user_by_email(data.get("email", ""))
    if not u or not u.get("ativo", 1):
        return None
    return {"email": u["email"], "nome": u["nome"], "papel": u["papel"]}


def _clear_cookie():
    mgr = _cookie_mgr()
    if mgr:
        try:
            mgr.delete(COOKIE_NAME)
        except Exception:
            pass


def do_logout():
    st.session_state.pop("auth_user", None)
    _clear_cookie()


# ===== Rate limiting (invisível ao usuário)

def _rate_bucket():
    b = st.session_state.get("_login_bucket")
    if not b:
        b = {"count": 0, "reset_at": time.time() + LOGIN_WINDOW_SECONDS}
        st.session_state["_login_bucket"] = b
    return b


def _rate_limit_ok() -> bool:
    b = _rate_bucket()
    now = time.time()
    if now > b["reset_at"]:
        b["count"] = 0
        b["reset_at"] = now + LOGIN_WINDOW_SECONDS
    return b["count"] < MAX_LOGIN_ATTEMPTS


def _rate_register_fail():
    b = _rate_bucket()
    b["count"] += 1


# ===== reCAPTCHA (sem exibir nada técnico)

def _render_recaptcha() -> Optional[str]:
    """Retorna token do reCAPTCHA. Se não houver site_key, retorna 'dev-ok'."""
    if not RECAPTCHA_SITE_KEY:
        return "dev-ok"
    try:
        from streamlit_recaptcha import st_recaptcha
        return st_recaptcha(RECAPTCHA_SITE_KEY, key="recaptcha_login")
    except Exception:
        # Fallback simples para dev
        ok = st.checkbox("Sou humano", key="fallback_captcha")
        return "fallback-yes" if ok else None


def _verify_recaptcha(token: Optional[str]) -> bool:
    if not RECAPTCHA_SITE_KEY:
        return True
    if not token:
        return False
    if token == "fallback-yes":
        return True
    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": RECAPTCHA_SECRET, "response": token},
            timeout=8,
        )
        ok = r.json().get("success", False)
        return bool(ok)
    except Exception:
        return False


# ===========================
# ===== UI: TELA DE LOGIN ===
# ===========================

def _find_logo_path() -> Optional[str]:
    """Tenta localizar a logo em caminhos comuns."""
    candidates = [
        Path(__file__).parent / "logo.png",
        Path.cwd() / "logo.png",
        Path.cwd() / "assets" / "logo.png",
        Path("/mnt/data/logo.png"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _login_form_card() -> Optional[dict]:
    # CSS do card
    st.markdown("""
    <style>
      .login-card{
        background:var(--panel);
        border:1px solid var(--line);
        border-radius:1rem;
        padding:1.25rem 1.25rem 1rem;
        box-shadow:var(--sh-lg);
        max-width:520px;
        width:100%;
        margin:0 auto;
      }
      .login-title{
        font-weight:900;font-size:1.2rem;text-align:center;margin:.2rem 0 .15rem;letter-spacing:-.02em;
      }
      .login-note{color:var(--ink-2);text-align:center;margin:0 0 .9rem;font-size:.95rem;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">Entrar</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-note">Acesse sua conta</div>', unsafe_allow_html=True)

    if not _rate_limit_ok():
        st.error("Muitas tentativas. Tente novamente em alguns minutos.")
        st.markdown('</div>', unsafe_allow_html=True)
        return None

    with st.form("login_form_minimal", clear_on_submit=False):
        email = st.text_input("E-mail", placeholder="seu.email@exemplo.com")
        senha = st.text_input("Senha", type="password", placeholder="••••••••")
        remember = st.checkbox("Lembrar por 14 dias", value=False)

        token = _render_recaptcha()
        ok = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if ok:
            if not email or not senha:
                st.error("Preencha e-mail e senha.")
                st.markdown('</div>', unsafe_allow_html=True)
                return None

            if not _verify_recaptcha(token):
                st.error("Verificação falhou. Tente novamente.")
                _rate_register_fail()
                st.markdown('</div>', unsafe_allow_html=True)
                return None

            user = get_user_by_email(email)
            if not user or not bcrypt.checkpw(senha.encode("utf-8"), user["hash_senha"]):
                st.error("E-mail ou senha incorretos.")
                _rate_register_fail()
                st.markdown('</div>', unsafe_allow_html=True)
                return None

            if not user.get("ativo", 1):
                st.error("Conta inativa. Contate o administrador.")
                st.markdown('</div>', unsafe_allow_html=True)
                return None

            record_login(email)
            st.markdown('</div>', unsafe_allow_html=True)
            return {"email": user["email"], "nome": user["nome"], "papel": user["papel"], "remember": remember}

    st.markdown('</div>', unsafe_allow_html=True)
    return None


def show_login():
    """
    Tela de login:
      - Fundo com foto (_apply_login_background)
      - Único bloco translúcido envolvendo as duas colunas
      - Esquerda: logo + título + subtítulo (centralizados)
      - Direita: formulário de login
    """
    inject_css_once()
    _apply_login_background()

    st.markdown("""
    <style>
      :root{
        --login-block-height: 50vh;     /* altura mínima do bloco */
        --login-block-pt: 2rem;      /* 🔧 padding-top do bloco */
        --login-block-pb: 2rem;      /* 🔧 padding-bottom do bloco */
}
      }

      /* ocupa a viewport e centraliza verticalmente */
      section.main > div.block-container{
        min-height:100vh;
        display:flex;
        flex-direction:column;
        justify-content:center;
        padding-top:1rem !important;
        padding-bottom:1rem !important;
      }

      /* header preto */
      header[data-testid="stHeader"]{ background:#000 !important; }
      header[data-testid="stHeader"] *{ color:#fff !important; }

      /* bloco translúcido = contêiner das colunas */
      div[data-testid="stHorizontalBlock"]{
        display:flex !important;
        align-items:center !important;
        justify-content:center !important;
        gap:2.25rem !important;

        width:100%;
        max-width:1200px;
        margin:0 auto;
        padding: var(--login-block-pt) 2.5rem var(--login-block-pb); /* ⬅️ controla o topo/fundo */
        min-height:var(--login-block-height);
        box-sizing:border-box;

        background: rgba(137,137,137,0.45);
        border-radius:1.25rem;
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      }

      @media (max-width: 900px){
        div[data-testid="stHorizontalBlock"]{
          flex-direction:column !important;
          gap:1.25rem !important;
          padding:1.25rem;
          min-height:auto;
        }
      }

      /* coluna esquerda */
      .login-left-wrap{
        display:flex; flex-direction:column;
        align-items:center; justify-content:center;
        text-align:center;
        width:100%;
      }
      .login-left-wrap h1{
        margin:.5rem 0 0;
        font-size:2.2rem; font-weight:900; letter-spacing:-.02em;
        color:#fff;
      }
      .login-left-wrap p{
        margin:.35rem 0 0; color:#000; font-size:1rem;
      }
      .login-left-wrap .logo-holder img{
        display:block; max-width:160px; height:auto;
      }

      /* inputs e botões dentro do bloco */
      .stTextInput>div>div>input, .stPasswordInput>div>div>input{
        background-color: rgba(255,255,255,0.15) !important;
        border: 1px solid rgba(255,255,255,0.45) !important;
        color:#000 !important;
      }
      input::placeholder{ color:rgba(0,0,0,0.8) !important; }
      .stCheckbox input[type=checkbox]{ accent-color:#fff !important; }
      .stButton>button{ color:#fff !important; }
    </style>
    """, unsafe_allow_html=True)

    # ===== colunas =====
    col_left, col_right = st.columns([1, 1], gap="large")

    # esquerda: logo + textos
    with col_left:
        logo_path = _find_logo_path()
        if logo_path:
            import base64 as _b64
            with open(logo_path, "rb") as _f:
                b64img = _b64.b64encode(_f.read()).decode("utf-8")
            st.markdown(
                f"""
                <div class="login-left-wrap">
                  <div class="logo-holder">
                    <img src="data:image/png;base64,{b64img}" alt="CuidaSP" />
                  </div>
                  <h1>CuidaSP Data Hub</h1>
                  <p>Impacto social + dados, com simplicidade.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                """
                <div class="login-left-wrap">
                  <div class="logo-holder">🟢</div>
                  <h1>CuidaSP Data Hub</h1>
                  <p>Impacto social + dados, com simplicidade.</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # direita: formulário
    with col_right:
        user_data = _login_form_card()

    # pós-login
    if user_data:
        st.session_state["auth_user"] = {k:user_data[k] for k in ("email","nome","papel")}
        if user_data.get("remember"):
            _persist_cookie(st.session_state["auth_user"])
        st.rerun()

def ensure_auth() -> bool:
    """Garante que o usuário está autenticado (cookie -> sessão)."""
    init_db()
    if "auth_user" not in st.session_state:
        cookie_user = _bootstrap_from_cookie()
        if cookie_user:
            st.session_state["auth_user"] = cookie_user
    return bool(st.session_state.get("auth_user"))

# ===========================
# ====== COMPAT: GUARD ======
# ===========================
def guard(require_login: bool = True):
    """
    Compat layer p/ código legado.
    - Se não houver sessão autenticada, mostra o login e interrompe a execução (st.stop()).
    - Retorna o dicionário do usuário autenticado (ou None se require_login=False e não logado).
    """
    if require_login:
        if not ensure_auth():
            show_login()
            st.stop()
        return st.session_state.get("auth_user")
    else:
        # Apenas tenta carregar cookie -> sessão, sem bloquear a página
        ensure_auth()
        return st.session_state.get("auth_user")

def clear_login_styles():
    """Remove o fundo e o bloco translúcido do login quando já estiver autenticado."""
    st.markdown("""
    <style>
      /* tira imagem de fundo e volta ao padrão */
      div[data-testid="stAppViewContainer"]{
        background-image:none !important;
        background: var(--bg, #ffffff) !important;
      }
      /* zera qualquer estilização do container de colunas aplicada no login */
      div[data-testid="stHorizontalBlock"]{
        background: transparent !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        padding: 0 !important;
        min-height: auto !important;
        margin: 0 !important;
        gap: initial !important;
      }
      /* volta cores de inputs/labels ao padrão do app (se você quiser manter escuro, remova) */
      .stTextInput>div>div>input, .stPasswordInput>div>div>input{
        background-color: initial !important;
        border: 1px solid var(--line, #e5e7eb) !important;
        color: inherit !important;
      }
      input::placeholder{ color: inherit !important; }
      label{ color: inherit !important; }
    </style>
    """, unsafe_allow_html=True)
