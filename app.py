import streamlit as st
import ui
from auth import ensure_auth, do_logout, show_login, clear_login_styles

if not ensure_auth():
    show_login()
    st.stop()

# 2) Já autenticado? Limpa estilos do login para não “vazarem” no app.
clear_login_styles()

st.set_page_config(
    page_title="Cuida SP Data Hub",
    page_icon="❤️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Autenticação ---
if not ensure_auth():
    show_login()
    st.stop()

# Descobre papel do usuário
user = st.session_state.get("auth_user", {}) or {}
papel = str(user.get("papel", "")).strip().lower()

# Monta lista de páginas (Admin volta!)
pages = ["Dashboard", "Dados Brutos"]
if papel == "admin":
    pages.append("Admin")

# --- Sidebar com logo grande e navegação em blocos ---
page = ui.sidebar_nav(
    items=["Dashboard", "Dados Brutos", "Admin"],  # ou pages=[...]
    logo="logo.png",
    on_logout=lambda: (do_logout(), st.rerun())  # <- essencial
)



# --- Router ---
if page == "Dashboard":
    ui.dashboard_acoes()
elif page == "Dados Brutos":
    ui.dados_brutos()
elif page == "Admin":
    # exige que exista ui.admin()
    ui.admin()
