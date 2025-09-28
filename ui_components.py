# ui_components.py
from __future__ import annotations
import streamlit as st
from pathlib import Path

# =========================
# ====== DESIGN SYSTEM ====
# =========================

# CSS base (cores, sombras, radii, tipografia, etc.)
_CSS = """
:root{
  --bg:#ffffff;
  --ink:#0f172a;
  --ink-2:#475569;
  --line:#e5e7eb;

  /* acentos nos tons do logo (azul/verde/laranja) */
  --blue-500:#3B82F6;
  --green-500:#10B981;
  --orange-500:#F97316;

  --panel:#ffffffcc; /* branco suave translúcido */
  --r-lg:16px;

  --sh-sm:0 1px 4px rgba(15,23,42,.06);
  --sh-md:0 6px 14px rgba(15,23,42,.10);
  --sh-lg:0 12px 28px rgba(15,23,42,.15);

  --xs:.25rem; --sm:.5rem; --md:.75rem; --lg:1rem; --xl:1.25rem;
}

/* texto base */
html, body, [class*="css"] {
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, "Helvetica Neue", Arial, "Noto Sans", "Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol" !important;
  color: var(--ink);
}

/* títulos */
h1,h2,h3{ letter-spacing:-.02em; }
h1{ font-weight:900; }
h2{ font-weight:800; }
h3{ font-weight:700; }

/* botões padrão */
.stButton>button{
  border-radius: 12px;
  border:1px solid var(--line);
  background: #fff;
  transition: all .2s ease;
}
.stButton>button:hover{
  transform: translateY(-1px);
  box-shadow: var(--sh-md);
}

/* campos de texto default */
.stTextInput>div>div>input, .stPasswordInput>div>div>input{
  border-radius: 12px !important;
}

/* ===== Sidebar como coluna flex: topo -> conteúdo -> rodapé ===== */
aside[data-testid="stSidebar"] > div {
  height: 100%;
}
.sb-wrap{
  display:flex; flex-direction:column;
  min-height: 100vh;
  gap: .75rem;
}

/* topo: logo centralizado */
.sb-top { display:flex; align-items:center; justify-content:center; padding:1rem 0 .25rem; }
.sb-top img{ display:block; width:88px; height:auto; }

/* navegação */
.nav-blocks{display:flex;flex-direction:column;gap:.5rem;margin:.25rem 0 .5rem;}
.nav-btn.stButton>button{
  display:flex; align-items:center; gap:.55rem; justify-content:center;
  border-radius:14px!important; font-weight:700!important;
  background:var(--panel)!important; color:var(--ink)!important;
  border:1px solid var(--line)!important; transition:all .2s ease!important;
}
.nav-btn.stButton>button:hover{
  transform:translateY(-1px)!important; box-shadow:var(--sh-md)!important;
  border-color: rgba(59,130,246,.35)!important;
}
.nav-btn.active.stButton>button{
  background:linear-gradient(180deg, rgba(59,130,246,.10), rgba(16,185,129,.08))!important;
  border-left:4px solid var(--orange-500)!important;
}

/* resumo rápido */
.sb-summary{
  background:var(--panel); border:1px solid var(--line); border-radius:16px;
  padding:.85rem; box-shadow:var(--sh-sm);
}
.sb-summary .title{
  color:var(--ink-2); text-transform:uppercase; font-size:.8rem; letter-spacing:.08em;
  margin:0 0 .5rem;
}
.sb-summary .grid{ display:grid; grid-template-columns:1fr; gap:.5rem; }
.sb-summary .item{
  display:flex; align-items:center; justify-content:space-between;
  background:rgba(255,255,255,0.03); border:1px solid var(--line); border-radius:.75rem;
  padding:.5rem .6rem;
}
.sb-summary .item .k{ display:flex; align-items:center; gap:.5rem; color:var(--ink-2); font-size:.9rem;}
.sb-summary .item .v{ font-weight:800; }

/* rodapé fixo */
.sb-footer{ margin-top:auto; }
.sb-footer .btn-danger.stButton>button{
  background:rgba(220,38,38,.12)!important; color:#FCA5A5!important; border-color:#7F1D1D!important;
}
.sb-footer .btn-danger.stButton>button:hover{ background:rgba(220,38,38,.2)!important; }

/* ===== Seções (section/hero/cards) ===== */
.section{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:1rem; box-shadow:var(--sh-sm); margin-bottom:1rem;}
.section h3{ margin:.25rem 0 .5rem; }
.hint{ color:var(--ink-2); font-size:.9rem; }

.hero{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1rem 1.25rem;
  box-shadow: var(--sh-sm);
  margin-bottom: 1rem;
}
.hero .crumb{ color: var(--ink-2); font-size: .85rem; margin: 0 0 .25rem; }
.hero h1{ margin:.2rem 0 0; font-weight:900; letter-spacing:-.02em; }
.hero p{ margin:.25rem 0 0; color:var(--ink-2); }

/* cards de métricas */
.kpi-card{
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:14px;
  padding:.85rem;
  box-shadow:var(--sh-sm);
}
.kpi-card .value{ font-weight:900;font-size:1.6rem;line-height:1.2;margin:.15rem 0; }
.kpi-card .subtitle{ color:var(--ink-2); font-size:.9rem; }

/* footer geral */
.footer{
  color:var(--ink-2); font-size:.85rem; margin-top:1rem;
}

/* ===== Força a sidebar a ser flex column (topo->conteúdo->rodapé) ===== */
section[data-testid="stSidebar"] .block-container{
  display:flex !important;
  flex-direction:column !important;
  min-height:100vh !important;
}

/* topo: logo centralizado */
.sb-top{ display:flex; align-items:center; justify-content:center; padding:1rem 0 .25rem; }
.sb-top img{ display:block; width:88px; height:auto; }

/* navegação */
.nav-blocks{ display:flex; flex-direction:column; gap:.5rem; margin:.25rem 0 .5rem; }
.nav-btn.stButton>button{
  display:flex; align-items:center; justify-content:center; gap:.55rem;
  border-radius:14px!important; font-weight:700!important;
  background:var(--panel)!important; color:var(--ink)!important;
  border:1px solid var(--line)!important; transition:all .2s ease!important;
}
.nav-btn.stButton>button:hover{
  transform:translateY(-1px)!important; box-shadow:var(--sh-md)!important;
  border-color:rgba(59,130,246,.35)!important;
}
.nav-btn.active.stButton>button{
  background:linear-gradient(180deg, rgba(59,130,246,.10), rgba(16,185,129,.08))!important;
  border-left:4px solid var(--orange-500)!important;
}

/* resumo rápido: bloco destacado */
.sb-summary{
  background:var(--panel); border:1px solid var(--line); border-radius:16px;
  padding:.85rem; box-shadow:var(--sh-sm);
}
.sb-summary .title{
  color:var(--ink-2); text-transform:uppercase; font-size:.8rem; letter-spacing:.08em;
  margin:0 0 .5rem;
}
.sb-summary .grid{ display:grid; grid-template-columns:1fr; gap:.5rem; }
.sb-summary .item{
  display:flex; align-items:center; justify-content:space-between;
  background:rgba(255,255,255,0.03); border:1px solid var(--line); border-radius:.75rem;
  padding:.5rem .6rem;
}
.sb-summary .item .k{ display:flex; align-items:center; gap:.5rem; color:var(--ink-2); font-size:.9rem;}
.sb-summary .item .v{ font-weight:800; }

/* rodapé no fundo */
.sb-footer{ margin-top:auto; }  /* <- empurra o rodapé para baixo */


"""

_css_injected_key = "_css_injected_once"

def inject_css_once():
    """Injeta o CSS do design system apenas uma vez por sessão."""
    if st.session_state.get(_css_injected_key):
        return
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
    st.session_state[_css_injected_key] = True


# =========================
# ======== HELPERS ========
# =========================

def _logo_guess_path() -> str | None:
    """Tenta encontrar um logo padrão."""
    candidates = [
        Path.cwd() / "logo.png",
        Path.cwd() / "assets" / "logo.png",
        Path(__file__).parent / "logo.png",
        Path("/mnt/data/logo.png"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


# =========================
# === SHIMS DE COMPAT =====
# =========================

def section(title: str, hint: str = ""):
    """Shim de seção usada por telas antigas."""
    inject_css_once()
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown(f"<h3>{title}</h3>", unsafe_allow_html=True)
    if hint:
        st.markdown(f'<div class="hint">{hint}</div>', unsafe_allow_html=True)

def section_end():
    st.markdown("</div>", unsafe_allow_html=True)

def sidebar_list(options, default_index: int = 0, title: str = ""):
    """Shim legado: lista na sidebar (usa radio) — mantido p/ compatibilidade."""
    inject_css_once()
    with st.sidebar:
        return st.radio(
            label=title or "Navegação",
            options=options,
            index=default_index if 0 <= default_index < len(options) else 0,
            label_visibility="collapsed",
        )


# =========================
# ===== SIDEBAR NOVA ======
# =========================

def sidebar_nav_compact(pages: list[str], default_index: int = 0,
                        logo_path: str | None = None, on_logout=None) -> str:
    """
    Sidebar compacta e estável:
    - topo: logo centralizado (via <img> base64)
    - navegação: botões
    - resumo rápido: bloco destacado com valores reais
    - rodapé: 'Sair' sticky no fundo
    Retorna a página ativa.
    """
    import base64
    inject_css_once()
    current = st.session_state.get("nav_current", pages[default_index])

    # === util: transforma imagem em <img> base64 centralizado
    def _logo_img_tag(path: str, width: int = 88) -> str:
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return f'<img src="data:image/png;base64,{b64}" style="display:block;margin:0 auto;" width="{width}" alt="logo" />'
        except Exception:
            return ""

    with st.sidebar:
        # ---- LOGO (centralizado)
        logo_path = logo_path or _logo_guess_path()
        if logo_path:
            st.markdown(_logo_img_tag(logo_path, 88), unsafe_allow_html=True)
        st.write("")  # respiro

        # ---- NAVEGAÇÃO
        icons = {"Dashboard": "📊", "Dados Brutos": "🗂", "Admin": "🛠"}
        for p in pages:
            if st.button(f"{icons.get(p,'•')}  {p}", key=f"nav_{p}", use_container_width=True):
                current = p
        st.write("")

        # ---- RESUMO RÁPIDO (valores reais)
        try:
            import pandas as pd
            from data import read_all_tables
            d = read_all_tables()
            acoes = len(d.get("acoes", pd.DataFrame()))
            volunt = len(d.get("voluntarios", pd.DataFrame()))
        except Exception:
            acoes, volunt = 0, 0

        st.markdown(
            f"""
            <div style="
                background: rgba(255,255,255,.9);
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                padding: .85rem;
                box-shadow: 0 1px 4px rgba(15,23,42,.06);
                ">
              <div style="color:#475569;text-transform:uppercase;font-size:.8rem;letter-spacing:.08em;margin:0 0 .5rem;">
                Resumo rápido
              </div>
              <div style="display:grid;grid-template-columns:1fr;gap:.5rem;">
                <div style="display:flex;align-items:center;justify-content:space-between;
                            background:rgba(255,255,255,0.03);border:1px solid #e5e7eb;
                            border-radius:.6rem;padding:.5rem .6rem;">
                  <div style="display:flex;align-items:center;gap:.5rem;color:#475569;font-size:.9rem;">📋 Ações</div>
                  <div style="font-weight:800;">{acoes}</div>
                </div>
                <div style="display:flex;align-items:center;justify-content:space-between;
                            background:rgba(255,255,255,0.03);border:1px solid #e5e7eb;
                            border-radius:.6rem;padding:.5rem .6rem;">
                  <div style="display:flex;align-items:center;gap:.5rem;color:#475569;font-size:.9rem;">👥 Voluntários</div>
                  <div style="font-weight:800;">{volunt}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # ---- RODAPÉ (sticky embaixo)
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.markdown("<div style='position:sticky; bottom:8px;'>", unsafe_allow_html=True)
        if st.button("Sair", use_container_width=True, key="logout_btn_sidebar"):
            if callable(on_logout):
                on_logout()
            else:
                try:
                    from auth import do_logout
                    do_logout(); st.rerun()
                except Exception:
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.session_state["nav_current"] = current
    return current



# ====== SHIMS: hero, cards, mensagens, footer, stat_grid ======
import streamlit as st

def hero(title: str, subtitle: str = "", breadcrumb: str = ""):
    """Cabeçalho bonito no topo da página."""
    inject_css_once()
    st.markdown("""
    <style>
      .hero{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 1rem 1.25rem;
        box-shadow: var(--sh-sm);
        margin-bottom: 1rem;
      }
      .hero .crumb{ color: var(--ink-2); font-size: .85rem; margin: 0 0 .25rem; }
      .hero h1{ margin:.2rem 0 0; font-weight:900; letter-spacing:-.02em; }
      .hero p{ margin:.25rem 0 0; color:var(--ink-2); }
    </style>
    """, unsafe_allow_html=True)
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    if breadcrumb:
        st.markdown(f'<div class="crumb">{breadcrumb}</div>', unsafe_allow_html=True)
    st.markdown(f"<h1>{title}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<p>{subtitle}</p>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def stat_card(title: str, value: str, subtitle: str = "", delta: str = ""):
    """Card de métrica individual (usado pelo grid)."""
    st.markdown(f"""
    <div class="kpi-card" style="
      background:var(--panel); border:1px solid var(--line); border-radius:14px;
      padding:.85rem; box-shadow:var(--sh-sm);">
      <div style="font-size:.85rem;color:var(--ink-2);">{title}</div>
      <div style="font-weight:900;font-size:1.6rem;line-height:1.2;margin:.15rem 0;">{value}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="color:var(--ink-2);font-size:.9rem;">{subtitle}</span>
        <span style="font-weight:700;color:var(--green-500);">{delta}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def create_metric_cards(metrics: list[dict]):
    """
    Renderiza um grid responsivo de big numbers.
    metrics: [{'title','value','subtitle','delta'}]
    """
    inject_css_once()
    # 3 colunas desktop, 2 tablet, 1 mobile usando st.columns adaptativo
    cols_per_row = 3
    for i in range(0, len(metrics), cols_per_row):
        row = metrics[i:i+cols_per_row]
        cols = st.columns(len(row))
        for c, m in zip(cols, row):
            with c:
                stat_card(
                    title=m.get('title', ''),
                    value=m.get('value', ''),
                    subtitle=m.get('subtitle', ''),
                    delta=m.get('delta', '')
                )


# Grid shims (para compat com código antigo, no-ops seguros)
def stat_grid_open(*args, **kwargs):
    return st.container()

def stat_grid_close():
    pass


# Mensagens padronizadas
def info_message(msg: str):
    st.info(msg)

def warning_message(msg: str):
    st.warning(msg)

def error_message(msg: str):
    st.error(msg)


def footer():
    """Rodapé simples para fechar a página."""
    st.markdown(
        '<div style="color:var(--ink-2);font-size:.85rem;margin-top:1rem;">'
        'Feito com ❤️ pelo CuidaSP Data Hub'
        '</div>',
        unsafe_allow_html=True
    )
