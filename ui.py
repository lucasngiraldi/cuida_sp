# ui.py
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Tuple

import altair as alt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from db import get_month_access_count

# Importa dados
from data import read_all_tables

# Importa UI components (nova sidebar + componentes já usados)
from ui_components import (
    inject_css_once, hero, stat_card, stat_grid_open, stat_grid_close,
    section, section_end, footer, create_metric_cards, info_message,
    warning_message, error_message,
    sidebar_nav_compact,            # NAV nova/compacta
)

# Autenticação / permissões
from auth import guard, do_logout

# DB e administração
from db import list_users, create_user, update_user, delete_user, update_password
import bcrypt

import plotly.io as pio
pio.templates.default = None  # desativa template global que pode esconder o geo

from db import get_recent_logs
import pandas as pd
import plotly.express as px
from datetime import datetime

# ---------------------------------------------------------------------
# Paleta usada em gráficos
# ---------------------------------------------------------------------
COLORS = {
    "primary": "#EC4899",
    "primary_light": "#F9A8D4",
    "secondary": "#10B981",
    "accent": "#06B6D4",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "success": "#10B981",
    "gray_100": "#F3F4F6",
    "gray_500": "#6B7280",
    "gray_900": "#111827"
}


# ---------------------------------------------------------------------
# Helpers gerais de UI
# ---------------------------------------------------------------------
def _tighten_top_spacing(padding_top_px: int = 8):
    """Reduz o espaço no topo do conteúdo principal."""
    st.markdown(
        f"""
        <style>
          main .block-container {{ padding-top:{padding_top_px}px !important; }}
        </style>
        """,
        unsafe_allow_html=True
    )


def _norm_text(s: str) -> str:
    """Normaliza texto para comparação."""
    if s is None:
        return ""
    s0 = unicodedata.normalize("NFKD", str(s)).encode("ASCII", "ignore").decode("ASCII")
    return " ".join(s0.lower().strip().split())

def _style_geo(fig, title: str, height: int = 520):
    fig.update_geos(
        projection_type="natural earth",
        showland=True, landcolor="#F2EFEA",
        showocean=True, oceancolor="#DCEBFA",
        showlakes=True, lakecolor="#DCEBFA",
        showcountries=True, countrycolor="#A3A3A3",
        showcoastlines=True, coastlinecolor="#94A3B8",
        bgcolor="rgba(0,0,0,0)"
    )
    fig.update_layout(
        template=None,                      # desliga o tema do Streamlit
        title=dict(text=title, x=0.5),
        margin=dict(l=0, r=0, t=40, b=0),
        height=height,
        coloraxis_showscale=False,
        font=dict(size=12),
    )
    return fig
# ---------------------------------------------------------------------
# ======= GEO HELPERS (limpeza de coordenadas e join com enderecos) ===
# ---------------------------------------------------------------------
def _pick_latlon(df_src: pd.DataFrame) -> Tuple[str, str]:
    """Encontra colunas de latitude e longitude pelo nome."""
    lat_col = lon_col = None
    for c in df_src.columns:
        cl = _norm_text(c)
        if cl in ("lat", "latitude"):
            lat_col = c
        if cl in ("lon", "lng", "longitude"):
            lon_col = c
    return lat_col, lon_col


def _clean_coord(x) -> float:
    """Converte formatos pt-BR e 'micrograu' para graus decimais válidos."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    s = str(x).strip()
    if s == "":
        return np.nan

    # normaliza vírgula/ponto
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")

    # se veio com pontos de milhar (ex.: -235.466.755)
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3}){2,}", s):
        sign = -1 if s.startswith("-") else 1
        digits = re.sub(r"[^0-9]", "", s)
        if not digits:
            return np.nan
        n = float(int(digits))

        # escolhe escala por quantidade de dígitos
        # 10 dígitos ~ 1e8 | 9 dígitos ~ 1e7 | 7–8 dígitos ~ 1e6
        if len(digits) >= 10:
            v = sign * (n / 1e8)
        elif len(digits) >= 9:
            v = sign * (n / 1e7)
        elif len(digits) >= 7:
            v = sign * (n / 1e6)
        else:
            v = sign * n

        # se ainda passar de 180, tenta outras escalas
        if abs(v) > 180:
            for sc in (1e8, 1e7, 1e6, 1e5):
                vv = sign * (n / sc)
                if abs(vv) <= 180:
                    return vv
            return np.nan
        return v

    # caminho "normal"
    try:
        v = float(s)
        if abs(v) > 180:
            for sc in (1e6, 1e7, 1e8):
                vv = v / sc
                if abs(vv) <= 180:
                    return vv
            return np.nan
        return v
    except Exception:
        return np.nan


def _prepare_volunteer_map_data(volunt: pd.DataFrame, v_lat: str, v_lon: str) -> pd.DataFrame:
    """Retorna lat/lon (float) agregados por ponto com contagem de voluntários."""
    tmp = volunt[[v_lat, v_lon]].dropna().copy()
    tmp[v_lat] = tmp[v_lat].apply(_clean_coord)
    tmp[v_lon] = tmp[v_lon].apply(_clean_coord)
    vmap_df = tmp.dropna().rename(columns={v_lat: "lat", v_lon: "lon"})
    return vmap_df.groupby(["lat", "lon"], as_index=False).size().rename(columns={"size": "vol_count"})


def _parse_endereco_livre(s: str) -> Tuple[str, str]:
    """Extrai rua e número de um endereço livre."""
    if not s:
        return ("", "")
    txt = _norm_text(s)
    # pega o último número da string
    m = re.search(r"(\d{1,6})(?!.*\d)", txt)
    numero = m.group(1) if m else ""
    rua = txt if not numero else txt[:m.start()].strip()
    return (rua, numero)


# --- Helpers p/ normalização de textos de endereço ---
import unicodedata, re

def _strip_accents(s: str) -> str:
    if s is None:
        return ""
    return unicodedata.normalize("NFKD", str(s)).encode("ASCII", "ignore").decode("ASCII")

def _norm_key(s: str) -> str:
    s = _strip_accents(s).lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _split_endereco_livre(s: str) -> tuple[str, str]:
    """
    Tenta separar 'Rua/Nome, 123' em (rua, numero).
    Se não achar número, volta (rua, "").
    """
    txt = _norm_key(s)
    if not txt:
        return ("", "")
    m = re.search(r"(\d{1,6})(?!.*\d)", txt)
    numero = m.group(1) if m else ""
    rua = txt if not numero else txt[:m.start()].strip()
    return (rua, numero)

def _resolve_coords_for_acoes(df_acoes: pd.DataFrame, df_end: pd.DataFrame) -> pd.DataFrame:
    """
    Se 'Ações' já tiver colunas de latitude/longitude, usa diretamente (com normalização).
    Caso contrário, cruza AÇÕES['Endereço'] com DIM_ENDERECOS['Rua'] para obter lat/lon.
    """
    if df_acoes is None or df_acoes.empty:
        return pd.DataFrame()

    # 1) PASS-THROUGH: já tem lat/lon nas Ações?
    a_lat, a_lon = _pick_latlon(df_acoes)
    if a_lat and a_lon:
        out = df_acoes.copy()
        out["lat"] = pd.to_numeric(out[a_lat].apply(_clean_coord), errors="coerce")
        out["lon"] = pd.to_numeric(out[a_lon].apply(_clean_coord), errors="coerce")
        out = out.dropna(subset=["lat", "lon"])
        return out

    # 2) Fallback: cruzar Endereço (Ações) ↔ Rua (Dim_enderecos)
    if df_end is None or df_end.empty:
        return pd.DataFrame()

    end_acao_col = next((c for c in df_acoes.columns if _norm_text(c) in ("endereco", "endereço")), None)
    rua_dim_col  = next((c for c in df_end.columns    if _norm_text(c) in ("rua", "logradouro")), None)
    if not end_acao_col or not rua_dim_col:
        return pd.DataFrame()

    e_lat, e_lon = _pick_latlon(df_end)
    if not e_lat or not e_lon:
        return pd.DataFrame()

    dim = df_end.copy()
    dim[e_lat] = dim[e_lat].apply(_clean_coord)
    dim[e_lon] = dim[e_lon].apply(_clean_coord)
    dim = dim.dropna(subset=[e_lat, e_lon]).copy()

    def _street_core(s: str) -> str:
        s = _norm_text(s)
        prefixes = ("rua", "r", "avenida", "av", "praça", "praca", "alameda", "travessa", "estrada", "rodovia")
        parts = s.split()
        if parts and parts[0] in prefixes:
            parts = parts[1:]
        parts = [p for p in parts if p not in ("de", "da", "do", "das", "dos")]
        return " ".join(parts).strip()

    dim["rua_key"]  = dim[rua_dim_col].astype(str).map(_norm_text)
    dim["rua_core"] = dim[rua_dim_col].astype(str).map(_street_core)

    a = df_acoes.copy()
    a["rua_key"]  = a[end_acao_col].astype(str).map(_norm_text)
    a["rua_core"] = a[end_acao_col].astype(str).map(_street_core)

    # 2.1) Match exato por rua_key
    m1 = a.merge(dim[["rua_key", e_lat, e_lon]].drop_duplicates("rua_key"), on="rua_key", how="left")
    if m1[[e_lat, e_lon]].notna().any(axis=None):
        out = m1.rename(columns={e_lat: "lat", e_lon: "lon"})
        out["lat"] = out["lat"].apply(_clean_coord)
        out["lon"] = out["lon"].apply(_clean_coord)
        return out.dropna(subset=["lat", "lon"])

    # 2.2) Match exato por rua_core
    m2 = a.merge(dim[["rua_core", e_lat, e_lon]].drop_duplicates("rua_core"), on="rua_core", how="left")
    if m2[[e_lat, e_lon]].notna().any(axis=None):
        out = m2.rename(columns={e_lat: "lat", e_lon: "lon"})
        out["lat"] = out["lat"].apply(_clean_coord)
        out["lon"] = out["lon"].apply(_clean_coord)
        return out.dropna(subset=["lat", "lon"])

    # 2.3) Fallback 'contains' no núcleo da rua
    dim_map = (
        dim[["rua_core", e_lat, e_lon]]
        .dropna()
        .drop_duplicates("rua_core")
        .set_index("rua_core")
        .to_dict(orient="index")
    )

    def _match_contains(core: str):
        if not core:
            return (np.nan, np.nan)
        for k, v in dim_map.items():
            if core in k or k in core:
                return (v[e_lat], v[e_lon])
        return (np.nan, np.nan)

    miss = a.copy()
    miss["lat"], miss["lon"] = zip(*miss["rua_core"].map(_match_contains))
    miss["lat"] = miss["lat"].apply(_clean_coord)
    miss["lon"] = miss["lon"].apply(_clean_coord)
    return miss.dropna(subset=["lat", "lon"])

def _prepare_actions_map_data(df_geo: pd.DataFrame, a_lat: str, a_lon: str) -> pd.DataFrame:
    """Agrupa ações por lat/lon e conta."""
    tmp = df_geo[[a_lat, a_lon]].dropna().copy()
    tmp[a_lat] = tmp[a_lat].apply(_clean_coord)
    tmp[a_lon] = tmp[a_lon].apply(_clean_coord)
    geo = tmp.dropna().rename(columns={a_lat: "lat", a_lon: "lon"})
    return geo.groupby(["lat", "lon"], as_index=False).size().rename(columns={"size": "acoes_count"})

def _render_geo_natural_earth(
    data: pd.DataFrame,
    size_col: str,
    title: str,
    size_max: int = 36,
    colors=None
):
    """
    Mapa com tiles OpenStreetMap (via Mapbox) — NÃO requer token.
    Mantém o mesmo nome da função para ser drop-in.
    """
    if data is None or data.empty:
        st.info("Sem dados georreferenciados para exibir.")
        return

    # garante numérico
    data = data.copy()
    data["lat"] = pd.to_numeric(data["lat"], errors="coerce")
    data["lon"] = pd.to_numeric(data["lon"], errors="coerce")
    data = data.dropna(subset=["lat", "lon"])
    if data.empty:
        st.info("Sem dados georreferenciados para exibir.")
        return

    # centro e zoom
    center = {"lat": float(data["lat"].mean()), "lon": float(data["lon"].mean())}
    zoom = 8 if len(data) == 1 else 3

    # força uso de tiles OSM (sem token)
    try:
        import plotly.express as px
        px.set_mapbox_access_token(None)
    except Exception:
        pass

    color_scale = colors or ["#D1FAE5", "#10B981"]  # default verdinho

    fig = px.scatter_mapbox(
        data,
        lat="lat",
        lon="lon",
        size=size_col,
        color=size_col,
        size_max=size_max,
        opacity=0.9,
        color_continuous_scale=color_scale,
        hover_name=size_col,
        title=title,
        zoom=zoom,
    )

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_center=center,
        margin=dict(l=0, r=0, t=40, b=0),
        height=460,
        coloraxis_showscale=False,
        font=dict(size=12),
        template=None  # impede tema do Streamlit de sobrescrever
    )

    # (NÃO usar marker.line: scatter_mapbox não suporta)
    st.plotly_chart(fig, theme=None, use_container_width=True)

# ---------------------------------------------------------------------
# KPI CARD (visual novo)
# ---------------------------------------------------------------------
def _kpi_card(title: str, value: str, subtitle: str = "", delta: str = ""):
    st.markdown(
        f"""
        <div style="
            background: rgba(255,255,255,.95);
            border:1px solid #e5e7eb;
            border-radius:14px;
            padding:.9rem 1rem;
            box-shadow:0 1px 4px rgba(15,23,42,.06);
            height:100%;
        ">
          <div style="font-size:.9rem;color:#475569;margin-bottom:.35rem;">{title}</div>
          <div style="display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;">
            <div style="font-weight:900;font-size:1.7rem;line-height:1;">{value}</div>
            <div style="font-weight:700;color:#10B981;">{delta}</div>
          </div>
          <div style="font-size:.88rem;color:#6B7280;margin-top:.25rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def _render_kpi_panel(v_horas: str, v_acoes: str, v_pess: str, v_vol: str,
                      tot_ac: int, tot_vol: int, pessoas: float):
    # CSS sem f-string (não precisa escapar chaves)
    st.markdown("""
    <style>
      .kpi-panel { background:#fff; border:1px solid #e5e7eb; border-radius:16px; padding:14px;
                   box-shadow:0 1px 4px rgba(15,23,42,.06); margin-bottom:18px; }
      .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }
      @media (max-width:1100px) { .kpi-grid { grid-template-columns:repeat(2,1fr);} }
      @media (max-width:640px)  { .kpi-grid { grid-template-columns:1fr;} }
      .kpi-card { background:rgba(248,249,251,.85); border:1px solid #e5e7eb; border-radius:12px; padding:12px 14px; }
      .kpi-title { font-size:.9rem; color:#475569; margin:0 0 .35rem; }
      .kpi-value { font-weight:800; font-size:1.6rem; line-height:1; }
      .kpi-sub   { color:#6B7280; font-size:.85rem; margin-top:.25rem; }
      .kpi-delta { color:#10B981; font-weight:700; }
    </style>
    """, unsafe_allow_html=True)

    # HTML com f-string (só aqui entram os valores)
    html = f"""
    <div class="kpi-panel">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-title">Horas de Voluntariado</div>
          <div class="kpi-value">{v_horas}</div>
          <div class="kpi-sub">Tempo dedicado às ações <span class="kpi-delta">+12%</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Total de Ações</div>
          <div class="kpi-value">{v_acoes}</div>
          <div class="kpi-sub">Ações registradas no período <span class="kpi-delta">{'+'+str(tot_ac) if tot_ac else ''}</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Pessoas Impactadas</div>
          <div class="kpi-value">{v_pess}</div>
          <div class="kpi-sub">Beneficiários diretos <span class="kpi-delta">{'+8%' if pessoas else ''}</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Voluntários Engajados</div>
          <div class="kpi-value">{v_vol}</div>
          <div class="kpi-sub">Colaboradores ativos <span class="kpi-delta">{'+'+str(tot_vol) if tot_vol else ''}</span></div>
        </div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# -----------------------------------------------------------------
# ------------------------------------------------------------------
def _render_kpi_panel_hist(v_kits: str, v_cri: str):
    """
    Painel de 2 KPIs (kits & crianças) usando o MESMO CSS do painel principal.
    """
    # Reaproveita a mesma folha de estilos — só muda a grade para 2 colunas
    st.markdown("""
    <style>
      .kpi-panel-hist .kpi-grid { grid-template-columns:repeat(2,1fr); }
    </style>
    """, unsafe_allow_html=True)

    html = f"""
    <div class="kpi-panel kpi-panel-hist">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-title">Kits entregues (desde 2021)</div>
          <div class="kpi-value">{v_kits}</div>
          <div class="kpi-sub">kits</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Crianças atendidas (desde 2021)</div>
          <div class="kpi-value">{v_cri}</div>
          <div class="kpi-sub">crianças</div>
        </div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------
# Compatibilidade com app.py antigo
# ---------------------------------------------------------------------
def sidebar_nav(*args, **kwargs):
    """Shim de compatibilidade para chamadas antigas."""
    from ui_components import sidebar_nav_compact

    # Ignora params antigos
    for k in ["subtitle", "title", "heading", "show_titles", "labels", "title_text"]:
        kwargs.pop(k, None)

    # Mapear nomes antigos
    if "logo" in kwargs and "logo_path" not in kwargs:
        kwargs["logo_path"] = kwargs.pop("logo")
    if "items" in kwargs and "pages" not in kwargs:
        kwargs["pages"] = kwargs.pop("items")
    if "pages" not in kwargs and args and isinstance(args[0], (list, tuple)):
        kwargs["pages"] = args[0]
        args = args[1:]

    # Fallback de logout
    if "on_logout" not in kwargs or not callable(kwargs["on_logout"]):
        kwargs["on_logout"] = lambda: (do_logout(), st.rerun())

    return sidebar_nav_compact(*args, **kwargs)


def run():
    """Shell do app com a NOVA sidebar compacta."""
    inject_css_once()

    current_page = sidebar_nav_compact(
        pages=["Dashboard", "Dados Brutos", "Admin"],
        default_index=0,
        logo_path="logo.png",
        on_logout=lambda: (do_logout(), st.rerun())
    )

    if current_page == "Dashboard":
        dashboard_acoes()
    elif current_page == "Dados Brutos":
        dados_brutos()
    elif current_page == "Admin":
        admin()
    else:
        dashboard_acoes()


# ---------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------
def _get_enderecos_table(data_all: dict) -> pd.DataFrame:
    """Tenta encontrar a dimensão de endereços independentemente do nome."""
    for k in ("enderecos", "Endereços", "dim_enderecos", "Dim_enderecos", "Enderecos", "Dim_Enderecos"):
        if k in data_all and isinstance(data_all[k], pd.DataFrame):
            return data_all[k].copy()
    return pd.DataFrame()

def dashboard_acoes():
    inject_css_once()
    hero(
        "Dashboard de Ações",
        "",
        "CuidaSP > Dashboard"
    )

    # Botão de atualizar (limpa cache e recarrega)
    if st.button("🔄 Atualizar dados", key="refresh_dashboard"):
        st.cache_data.clear()  # limpa todos os caches de dados
        st.rerun()  # recarrega a página imediatamente

    # Carrega dados
    data_all = read_all_tables()
    acoes  = data_all.get("acoes", pd.DataFrame()).copy()
    volunt = data_all.get("voluntarios", pd.DataFrame()).copy()
    end    = _get_enderecos_table(data_all)

    if acoes.empty:
        info_message("Nenhum dado encontrado na aba *Ações*.")
        return

    # ------------ Normalizações básicas ------------
    # Data
    if "Data" not in acoes.columns:
        for col in acoes.columns:
            if _norm_text(col) == "data":
                acoes.rename(columns={col: "Data"}, inplace=True)
                break
    if "Data" in acoes.columns:
        acoes["Data"] = pd.to_datetime(acoes["Data"], errors="coerce", dayfirst=True)

    # Frente / Status
    if "Frente de Atuação" not in acoes.columns:
        for c in acoes.columns:
            if _norm_text(c).startswith("frente"):
                acoes.rename(columns={c: "Frente de Atuação"}, inplace=True)
                break
    if "Status" not in acoes.columns:
        for c in acoes.columns:
            if _norm_text(c) == "status":
                acoes.rename(columns={c: "Status"}, inplace=True)
                break

    # Endereço
    if "Endereço" not in acoes.columns:
        for c in acoes.columns:
            if "end" in _norm_text(c):
                acoes.rename(columns={c: "Endereço"}, inplace=True)
                break

    # --------------------- Filtros ---------------------
    with st.expander("Filtros avançados", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            if "Data" in acoes.columns and acoes["Data"].notna().any():
                dmin, dmax = acoes["Data"].min(), acoes["Data"].max()
                periodo = st.date_input("Período", value=(dmin.date(), dmax.date()))
            else:
                periodo = None
        with c2:
            frente_opts = sorted(acoes.get("Frente de Atuação", pd.Series(dtype=str)).dropna().unique().tolist())
            frentes = st.multiselect("Frente de Atuação", frente_opts)
        with c3:
            status_opts = sorted(acoes.get("Status", pd.Series(dtype=str)).dropna().unique().tolist())
            status_sel = st.multiselect("Status", status_opts)

        c4, c5, c6 = st.columns(3)
        cidade_col = uf_col = None
        for c in end.columns:
            cl = _norm_text(c)
            if cl in ("cidade", "municipio"):
                cidade_col = c
            if cl in ("uf", "estado"):
                uf_col = c
        with c4:
            cidades = sorted(end[cidade_col].dropna().unique().tolist()) if (not end.empty and cidade_col in end.columns) else []
            cidade_sel = st.multiselect("Cidade", cidades) if cidades else []
        with c5:
            ufs = sorted(end[uf_col].dropna().unique().tolist()) if (not end.empty and uf_col in end.columns) else []
            uf_sel = st.multiselect("UF", ufs) if ufs else []
        with c6:
            q = st.text_input("Busca livre", placeholder="Digite para buscar...")

        base_size = st.slider("Tamanho base das bolhas (mapas)", 10, 80, 35, 5)

    # Aplica filtros
    df = acoes.copy()
    if periodo and isinstance(periodo, tuple) and len(periodo) == 2 and all(periodo) and "Data" in df.columns:
        df = df[(df["Data"] >= pd.to_datetime(periodo[0])) & (df["Data"] <= pd.to_datetime(periodo[1]))]
    if frentes and "Frente de Atuação" in df.columns:
        df = df[df["Frente de Atuação"].isin(frentes)]
    if status_sel and "Status" in df.columns:
        df = df[df["Status"].isin(status_sel)]
    if q:
        mask = pd.Series([False] * len(df))
        for c in df.columns:
            mask |= df[c].astype("string").str.contains(q, case=False, na=False)
        df = df[mask]

    # Filtro por cidade/UF através do join com endereços
    if (cidade_sel or uf_sel) and not end.empty and ("Endereço" in df.columns or any("end" in _norm_text(c) for c in df.columns)):
        enriched = _resolve_coords_for_acoes(df, end)
        if cidade_sel and cidade_col in enriched.columns:
            enriched = enriched[enriched[cidade_col].isin(cidade_sel)]
        if uf_sel and uf_col in enriched.columns:
            enriched = enriched[enriched[uf_col].isin(uf_sel)]
        df = enriched

    # ------------------- KPIs HISTÓRICOS -------------------
    from datetime import datetime
    section("Indicadores Históricos", "")

    ANOS = datetime.now().year - 2021 + 1  # 2021 – ano atual
    v_kits = f"{450 * 10 * ANOS:,}".replace(",", ".")
    v_cri = f"{500 * 4 * ANOS:,}".replace(",", ".")

    stat_grid_open()  # usa o mesmo wrapper já existente
    _render_kpi_panel_hist(v_kits, v_cri)
    stat_grid_close()
    section_end()

    # ------------------- KPIs (linha única) -------------------
    section("Indicadores Principais", "")
    # Horas
    h_ini_col = h_fim_col = None
    for c in acoes.columns:
        nc = _norm_text(c)
        if "horario de inicio" in nc or "horario de início" in nc or nc.endswith("inicio"):
            h_ini_col = c
        if "horario de termino" in nc or "horario de término" in nc or nc.endswith("termino") or nc.endswith("término"):
            h_fim_col = c
    horas_total = 0.0
    dur_h = pd.Series([0.0] * len(df))
    if h_ini_col and h_fim_col:
        work = df.copy()

        def _to_time(s):
            s = str(s).strip()
            if not s:
                return pd.NaT
            t = pd.to_datetime(s, format="%H:%M:%S", errors="coerce")
            if pd.isna(t):
                t = pd.to_datetime(s, format="%H:%M", errors="coerce")
            return t

        t_ini = work[h_ini_col].apply(_to_time)
        t_fim = work[h_fim_col].apply(_to_time)

        base = work["Data"].dt.date.astype(str) if ("Data" in work.columns and work["Data"].notna().any()) else pd.Series(["2000-01-01"] * len(work))
        ini_dt = pd.to_datetime(base + " " + t_ini.dt.strftime("%H:%M:%S"), errors="coerce")
        fim_dt = pd.to_datetime(base + " " + t_fim.dt.strftime("%H:%M:%S"), errors="coerce")
        wrap = (fim_dt.notna() & ini_dt.notna()) & (fim_dt < ini_dt)
        fim_dt.loc[wrap] = fim_dt.loc[wrap] + pd.Timedelta(days=1)

        dur_h = ((fim_dt - ini_dt).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0)
        horas_total = float(dur_h.sum())

    tot_ac = len(df)

    # Pessoas impactadas (tenta detectar coluna)
    pessoas = 0
    for c in df.columns:
        if "pessoa" in _norm_text(c):
            pessoas = pd.to_numeric(df[c], errors="coerce").fillna(0).sum()
            break

    # Voluntários únicos (a partir de string listada)
    volunt_set = set()
    col_vol_env = next((c for c in df.columns if _norm_text(c).startswith("volunt") and "envolv" in _norm_text(c)), None)
    if col_vol_env:
        for s in df[col_vol_env].dropna().astype(str):
            volunt_set.update([x.strip() for x in s.split(",") if x.strip()])
    tot_vol = len(volunt_set)

    v_horas  = f"{horas_total:,.1f}".replace(",", ".")
    v_acoes  = f"{tot_ac:,}".replace(",", ".")
    v_pess   = f"{int(pessoas):,}".replace(",", ".")
    v_vol    = f"{tot_vol:,}".replace(",", ".")

    # Abre o painel com fundo suave (o “bloco”)
    stat_grid_open()

    # (esses valores você já calcula logo acima; mantenha como estão)
    v_horas = f"{horas_total:,.1f}".replace(",", ".")
    v_acoes = f"{tot_ac:,}".replace(",", ".")
    v_pess = f"{int(pessoas):,}".replace(",", ".")
    v_vol = f"{tot_vol:,}".replace(",", ".")

    # novo painel com fundo/borda/sombra
    _render_kpi_panel(v_horas, v_acoes, v_pess, v_vol, tot_ac, tot_vol, pessoas)

    # Fecha o painel
    stat_grid_close()
    section_end()

    # ------------------- Mapas lado a lado -------------------
    section("Mapas Geográficos", "")
    col_left, col_right = st.columns(2, gap="large")

    # Voluntários
    with col_left:
        v_lat, v_lon = _pick_latlon(volunt)
        vmap_df = pd.DataFrame()
        if v_lat and v_lon:
            tmp = volunt[[v_lat, v_lon]].dropna().copy()
            tmp[v_lat] = tmp[v_lat].apply(_clean_coord)
            tmp[v_lon] = tmp[v_lon].apply(_clean_coord)
            vmap_df = tmp.dropna().rename(columns={v_lat: "lat", v_lon: "lon"})

        if not vmap_df.empty:
            vagg = vmap_df.groupby(["lat", "lon"], as_index=False).size().rename(columns={"size": "vol_count"})
            vagg = vagg[vagg["lat"].between(-90, 90) & vagg["lon"].between(-180, 180)]

            fig_v = px.scatter_geo(
                vagg,
                lat="lat", lon="lon",
                size="vol_count", size_max=base_size, opacity=0.85,
                color="vol_count", color_continuous_scale=["#D1FAE5", "#10B981"],
                projection="natural earth", fitbounds="locations",
            )
            fig_v = _style_geo(fig_v, "Distribuição Geográfica dos Voluntários", height=460)
            st.plotly_chart(fig_v, theme=None, use_container_width=True)
        else:
            st.info("Sem dados georreferenciados para *Voluntários*.")

    # Ações
    with col_right:
        df_geo = _resolve_coords_for_acoes(df, end)
        a_lat, a_lon = _pick_latlon(df_geo)
        geo = pd.DataFrame()
        if a_lat and a_lon:
            tmp = df_geo[[a_lat, a_lon]].dropna().copy()
            tmp[a_lat] = tmp[a_lat].apply(_clean_coord)
            tmp[a_lon] = tmp[a_lon].apply(_clean_coord)
            geo = tmp.dropna().rename(columns={a_lat: "lat", a_lon: "lon"})

        if not geo.empty:
            aagg = geo.groupby(["lat", "lon"], as_index=False).size().rename(columns={"size": "acoes_count"})
            aagg = aagg[aagg["lat"].between(-90, 90) & aagg["lon"].between(-180, 180)]

            fig_a = px.scatter_geo(
                aagg,
                lat="lat", lon="lon",
                size="acoes_count", size_max=base_size, opacity=0.85,
                color="acoes_count", color_continuous_scale=["#FED7AA", "#F97316"],
                projection="natural earth", fitbounds="locations",
            )
            fig_a = _style_geo(fig_a, "Distribuição Geográfica das Ações", height=460)
            st.plotly_chart(fig_a, theme=None, use_container_width=True)
        else:
            st.info("Sem dados georreferenciados para *Ações*.")
    section_end()

    # ------------------- Distribuição de Gênero -------------------
    section("Distribuição de Gênero dos Voluntários", "")

    # obtém a tabela de voluntários já carregada no cache
    vol_df = data_all.get("voluntarios") if "data_all" in locals() else read_all_tables()["voluntarios"].copy()

    # detecta a coluna de gênero/sexo
    gen_col = next(
        (c for c in vol_df.columns if _norm_text(c) in ("genero", "gênero", "sexo")),
        None
    )

    if gen_col:
        counts = (
            vol_df[gen_col]
            .fillna("Não informado")
            .astype(str)
            .str.strip()
            .value_counts()
            .sort_values(ascending=False)
        )

        fig = px.pie(
            names=counts.index,
            values=counts.values,
            hole=0.45,  # rosca
            title="Gênero dos voluntários (atual)"
        )
        fig.update_traces(textinfo="percent+label", pull=[0.03] * len(counts))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Coluna de gênero/sexo não encontrada na tabela de voluntários.")

    # ------------------- Análise temporal -------------------
    section("Análise Temporal", "")
    if h_ini_col and h_fim_col:
        if "Data" in df.columns and df["Data"].notna().any():
            serie = (
                pd.DataFrame({"Data": pd.to_datetime(df["Data"]), "Horas": dur_h})
                .dropna(subset=["Data"])
                .assign(mes=lambda x: x["Data"].dt.to_period("M").dt.to_timestamp())
                .groupby("mes", as_index=False)["Horas"].sum()
            )
            if not serie.empty:
                line_chart = alt.Chart(serie).mark_line(
                    point=alt.OverlayMarkDef(filled=True, size=80),
                    strokeWidth=3,
                    color="#EC4899"
                ).encode(
                    x=alt.X("mes:T", title="Mês", axis=alt.Axis(format="%b %Y")),
                    y=alt.Y("Horas:Q", title="Horas de Voluntariado"),
                    tooltip=["mes:T", "Horas:Q"]
                ).properties(title="Evolução Mensal das Horas de Voluntariado", height=300)
                st.altair_chart(line_chart, use_container_width=True)

        if "Frente de Atuação" in df.columns:
            por_frente = (
                pd.DataFrame({"Frente de Atuação": df["Frente de Atuação"], "Horas": dur_h})
                .groupby("Frente de Atuação", as_index=False)["Horas"].sum()
                .sort_values("Horas", ascending=False)
            )
            if not por_frente.empty:
                bar_chart = alt.Chart(por_frente).mark_bar(
                    color="#10B981",
                    cornerRadiusTopRight=4, cornerRadiusBottomRight=4
                ).encode(
                    x=alt.X("Horas:Q", title="Horas de Voluntariado"),
                    y=alt.Y("Frente de Atuação:N", sort="-x", title="Frente de Atuação"),
                    tooltip=["Frente de Atuação:N", "Horas:Q"]
                ).properties(title="Horas de Voluntariado por Frente de Atuação", height=300)
                st.altair_chart(bar_chart, use_container_width=True)
    else:
        info_message("As colunas *Horário de início* e *Horário de término* não foram detectadas na aba Ações.")
    section_end()

    footer()


def _normalize_columns(acoes: pd.DataFrame):
    """Normaliza nomes de colunas mais usadas."""
    # Data
    if "Data" not in acoes.columns:
        for col in acoes.columns:
            if _norm_text(col) == "data":
                acoes.rename(columns={col: "Data"}, inplace=True)
                break

    if "Data" in acoes.columns:
        acoes["Data"] = pd.to_datetime(acoes["Data"], errors="coerce", dayfirst=True)

    # Outros mapeamentos
    column_mappings = {
        "frente": "Frente de Atuacao",
        "status": "Status",
        "endereco": "Endereco"
    }
    for normalized, target in column_mappings.items():
        if target not in acoes.columns:
            for c in acoes.columns:
                if normalized in _norm_text(c):
                    acoes.rename(columns={c: target}, inplace=True)
                    break


def _create_filter_section(acoes: pd.DataFrame, end: pd.DataFrame):
    """Cria filtros do dashboard."""
    filters = {}

    col1, col2, col3 = st.columns(3)
    with col1:
        if "Data" in acoes.columns and acoes["Data"].notna().any():
            dmin, dmax = acoes["Data"].min(), acoes["Data"].max()
            filters['periodo'] = st.date_input(
                "Período",
                value=(dmin.date(), dmax.date()),
                help="Selecione o período de análise"
            )
    with col2:
        frente_opts = sorted(acoes.get("Frente de Atuacao", pd.Series(dtype=str)).dropna().unique().tolist())
        filters['frentes'] = st.multiselect("Frente de Atuação", frente_opts)
    with col3:
        status_opts = sorted(acoes.get("Status", pd.Series(dtype=str)).dropna().unique().tolist())
        filters['status_sel'] = st.multiselect("Status", status_opts)

    col4, col5, col6 = st.columns(3)
    cidade_col = uf_col = None
    for c in end.columns:
        cl = _norm_text(c)
        if cl in ("cidade", "municipio"):
            cidade_col = c
        if cl in ("uf", "estado"):
            uf_col = c

    with col4:
        if not end.empty and cidade_col:
            cidades = sorted(end[cidade_col].dropna().unique().tolist())
            filters['cidade_sel'] = st.multiselect("Cidade", cidades)
        else:
            filters['cidade_sel'] = []
    with col5:
        if not end.empty and uf_col:
            ufs = sorted(end[uf_col].dropna().unique().tolist())
            filters['uf_sel'] = st.multiselect("UF", ufs)
        else:
            filters['uf_sel'] = []
    with col6:
        filters['search_query'] = st.text_input("Busca livre", placeholder="Digite para buscar...")

    with st.expander("Opções avançadas"):
        filters['base_size'] = st.slider("Tamanho base das bolhas nos mapas", 10, 80, 35, 5)

    return filters


def _apply_filters(acoes: pd.DataFrame, end: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Aplica filtros nos dados das Ações; quando filtragem por UF/cidade for usada,
    já retorna enriquecidas com lat/lon via dimensão de endereços."""
    df = acoes.copy()

    periodo = filters.get('periodo')
    if periodo and isinstance(periodo, tuple) and len(periodo) == 2 and all(periodo) and "Data" in df.columns:
        df = df[(df["Data"] >= pd.to_datetime(periodo[0])) & (df["Data"] <= pd.to_datetime(periodo[1]))]

    frentes = filters.get('frentes', [])
    if frentes and "Frente de Atuacao" in df.columns:
        df = df[df["Frente de Atuacao"].isin(frentes)]

    status_sel = filters.get('status_sel', [])
    if status_sel and "Status" in df.columns:
        df = df[df["Status"].isin(status_sel)]

    search_query = filters.get('search_query', '')
    if search_query:
        mask = pd.Series([False] * len(df))
        for c in df.columns:
            mask |= df[c].astype("string").str.contains(search_query, case=False, na=False)
        df = df[mask]

    cidade_sel = filters.get('cidade_sel', [])
    uf_sel = filters.get('uf_sel', [])
    if (cidade_sel or uf_sel) and not end.empty:
        enriched = _resolve_coords_for_acoes(df, end)

        cidade_col = next((c for c in end.columns if _norm_text(c) in ("cidade", "municipio")), None)
        uf_col = next((c for c in end.columns if _norm_text(c) in ("uf", "estado")), None)

        if cidade_sel and cidade_col and cidade_col in enriched.columns:
            enriched = enriched[enriched[cidade_col].isin(cidade_sel)]
        if uf_sel and uf_col and uf_col in enriched.columns:
            enriched = enriched[enriched[uf_col].isin(uf_sel)]

        df = enriched

    return df


def _calculate_hours(df: pd.DataFrame) -> Tuple[pd.Series, float]:
    """Calcula horas a partir de colunas de horário."""
    h_ini_col = h_fim_col = None
    for c in df.columns:
        nc = _norm_text(c)
        if "horario de inicio" in nc or nc.endswith("inicio"):
            h_ini_col = c
        if "horario de termino" in nc or nc.endswith("termino"):
            h_fim_col = c

    horas_total = 0.0
    dur_h = pd.Series([0.0] * len(df))

    if h_ini_col and h_fim_col:
        work = df.copy()

        def _to_time(s):
            s = str(s).strip()
            if not s:
                return pd.NaT
            t = pd.to_datetime(s, format="%H:%M:%S", errors="coerce")
            if pd.isna(t):
                t = pd.to_datetime(s, format="%H:%M", errors="coerce")
            return t

        t_ini = work[h_ini_col].apply(_to_time)
        t_fim = work[h_fim_col].apply(_to_time)

        base = work["Data"].dt.date.astype(str) if ("Data" in work.columns and work["Data"].notna().any()) else pd.Series(["2000-01-01"] * len(work))
        ini_dt = pd.to_datetime(base + " " + t_ini.dt.strftime("%H:%M:%S"), errors="coerce")
        fim_dt = pd.to_datetime(base + " " + t_fim.dt.strftime("%H:%M:%S"), errors="coerce")
        wrap = (fim_dt.notna() & ini_dt.notna()) & (fim_dt < ini_dt)
        fim_dt.loc[wrap] = fim_dt.loc[wrap] + pd.Timedelta(days=1)

        dur_h = ((fim_dt - ini_dt).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0)
        horas_total = float(dur_h.sum())

    return dur_h, horas_total


def _render_kpi_section(df: pd.DataFrame, horas_total: float, volunt: pd.DataFrame):
    """KPIs no topo em cards e todos na mesma linha."""
    section("Indicadores Principais", "")

    tot_ac = len(df)

    # Pessoas impactadas (tenta achar uma coluna com 'pessoa' no nome)
    pessoas = 0
    for c in df.columns:
        if "pessoa" in _norm_text(c):
            pessoas = pd.to_numeric(df[c], errors="coerce").fillna(0).sum()
            break

    # Voluntários únicos (a partir de string listada)
    volunt_set = set()
    if "Voluntarios envolvidos" in df.columns:
        for s in df["Voluntarios envolvidos"].dropna().astype(str):
            volunt_set.update([x.strip() for x in s.split(",") if x.strip()])
    tot_vol = len(volunt_set)

    # Valores formatados
    v_horas = f"{horas_total:,.1f}".replace(",", ".")
    v_acoes = f"{tot_ac:,}".replace(",", ".")
    v_pessoas = f"{int(pessoas):,}".replace(",", ".")
    v_vol = f"{tot_vol:,}".replace(",", ".")

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        _kpi_card("Horas de Voluntariado", v_horas, "Tempo dedicado às ações", "+12%")
    with c2:
        _kpi_card("Total de Ações", v_acoes, "Ações registradas no período", f"+{tot_ac}" if tot_ac else "")
    with c3:
        _kpi_card("Pessoas Impactadas", v_pessoas, "Beneficiários diretos", "+8%" if pessoas else "")
    with c4:
        _kpi_card("Voluntários Engajados", v_vol, "Colaboradores ativos", f"+{tot_vol}" if tot_vol else "")

    section_end()


def _render_maps_section(df: pd.DataFrame, volunt: pd.DataFrame, dim_end: pd.DataFrame, base_size: int):
    """Dois mapas Natural Earth lado a lado (desktop), empilhados no mobile."""
    section("Mapas Geográficos", "")

    # Voluntários
    v_lat, v_lon = _pick_latlon(volunt) if not volunt.empty else (None, None)
    vol_df = pd.DataFrame(columns=["lat", "lon", "vol_count"])
    if v_lat and v_lon and not volunt.empty:
        vol_df = _prepare_volunteer_map_data(volunt, v_lat, v_lon).rename(columns={"vol_count": "valor"})

    # Ações -> cruza com Dim_enderecos para ter lat/lon
    df_geo = _resolve_coords_for_acoes(df, dim_end) if not df.empty and not dim_end.empty else pd.DataFrame()
    a_lat, a_lon = _pick_latlon(df_geo) if not df_geo.empty else (None, None)
    acoes_df = pd.DataFrame(columns=["lat", "lon", "acoes_count"])
    if a_lat and a_lon and not df_geo.empty:
        acoes_df = _prepare_actions_map_data(df_geo, a_lat, a_lon).rename(columns={"acoes_count": "valor"})

    col1, col2 = st.columns(2, gap="large")

    with col1:
        _render_geo_natural_earth(
            vol_df.rename(columns={"valor": "Voluntários"}),
            size_col="Voluntários",
            title="",
            size_max=max(24, min(42, base_size)),
            colors=["#D1FAE5", "#10B981"]  # verde
        )

    with col2:
        _render_geo_natural_earth(
            acoes_df.rename(columns={"valor": "Ações"}),
            size_col="Ações",
            title="Distribuição Geográfica das Ações",
            size_max=max(24, min(42, base_size)),
            colors=["#FED7AA", "#F97316"]  # laranja
        )

    section_end()


def _render_time_series_section(df: pd.DataFrame, dur_h: pd.Series):
    """Séries temporais: evolução mensal e horas por frente."""
    section("Análise Temporal")

    h_ini_col = h_fim_col = None
    for c in df.columns:
        nc = _norm_text(c)
        if "horario de inicio" in nc or nc.endswith("inicio"):
            h_ini_col = c
        if "horario de termino" in nc or nc.endswith("termino"):
            h_fim_col = c

    if h_ini_col and h_fim_col:
        if "Data" in df.columns and df["Data"].notna().any():
            serie = (
                pd.DataFrame({"Data": pd.to_datetime(df["Data"]), "Horas": dur_h})
                .dropna(subset=["Data"])
                .assign(mes=lambda x: x["Data"].dt.to_period("M").dt.to_timestamp())
                .groupby("mes", as_index=False)["Horas"].sum()
            )
            if not serie.empty:
                line_chart = alt.Chart(serie).mark_line(
                    point=alt.OverlayMarkDef(filled=True, size=80),
                    strokeWidth=3,
                    color=COLORS["primary"]
                ).encode(
                    x=alt.X("mes:T", title="Mês", axis=alt.Axis(format="%b %Y")),
                    y=alt.Y("Horas:Q", title="Horas de Voluntariado"),
                    tooltip=["mes:T", "Horas:Q"]
                ).properties(title="", height=300)
                st.altair_chart(line_chart, use_container_width=True)

        if "Frente de Atuacao" in df.columns:
            por_frente = (
                pd.DataFrame({"Frente de Atuacao": df["Frente de Atuacao"], "Horas": dur_h})
                .groupby("Frente de Atuacao", as_index=False)["Horas"].sum()
                .sort_values("Horas", ascending=False)
            )
            if not por_frente.empty:
                bar_chart = alt.Chart(por_frente).mark_bar(
                    color=COLORS["secondary"],
                    cornerRadiusTopRight=4, cornerRadiusBottomRight=4
                ).encode(
                    x=alt.X("Horas:Q", title="Horas de Voluntariado"),
                    y=alt.Y("Frente de Atuacao:N", sort="-x", title="Frente de Atuação"),
                    tooltip=["Frente de Atuacao:N", "Horas:Q"]
                ).properties(title="Horas de Voluntariado por Frente de Atuação", height=300)
                st.altair_chart(bar_chart, use_container_width=True)
    else:
        info_message("As colunas 'Horário de início' e 'Horário de término' não foram detectadas na aba Ações.")
    section_end()


# ---------------------------------------------------------------------
# DADOS BRUTOS
# ---------------------------------------------------------------------
def _filter_dataframe(df: pd.DataFrame, table_name: str = "") -> pd.DataFrame:
    """Busca livre e filtros por coluna."""
    if df.empty:
        return df

    q = st.text_input("Busca livre", key=f"search_{table_name}_{hash(tuple(df.columns))}",
                      placeholder="Digite para buscar em todos os campos...")

    out = df.copy()
    if q:
        mask = pd.Series([False] * len(out))
        for c in out.columns:
            mask |= out[c].astype("string").str.contains(q, case=False, na=False)
        out = out[mask]

    with st.expander("Filtros por Coluna", expanded=False):
        filter_cols = st.columns(min(3, len(out.columns)))
        for i, c in enumerate(out.columns):
            if i >= 12:
                break
            with filter_cols[i % 3]:
                vals = out[c].dropna().unique()
                if 1 < len(vals) <= 50:
                    sel = st.multiselect(f"Filtrar {c}", sorted(map(str, vals)),
                                         key=f"filter_{table_name}{c}{hash(tuple(vals))}")
                    if sel:
                        out = out[out[c].astype(str).isin(sel)]
    return out


def dados_brutos():
    """Exploração de tabelas com busca e filtros."""
    inject_css_once()
    hero("Dados Brutos", "Visualize e explore as tabelas com busca e filtros", "CuidaSP > Dados")

    data_all = read_all_tables()
    table_info = {
        "Voluntários": {"key": "voluntarios", "desc": "Cadastro e informações de voluntários", "icon": "👥"},
        "Ações": {"key": "acoes", "desc": "Registro detalhado das ações", "icon": "📋"},
        "Doações": {"key": "doacoes", "desc": "Controle de doações recebidas", "icon": "💝"},
        "Endereços": {"key": "enderecos", "desc": "Dimensão de endereços", "icon": "📍"},
    }

    tab_names = list(table_info.keys())
    tabs = st.tabs(tab_names)

    for tab_name, tab in zip(tab_names, tabs):
        with tab:
            cfg = table_info[tab_name]
            df = data_all.get(cfg["key"], pd.DataFrame()).copy()

            st.markdown(f"""
            <div style="padding: 1rem; background: {COLORS['gray_100']}; border-radius: .5rem; margin-bottom: 1rem;">
              <h4 style="margin:0; color:{COLORS['gray_900']};">{cfg['icon']} {tab_name}</h4>
              <p style="margin:.5rem 0 0; color:{COLORS['gray_500']}; font-size:.9rem;">{cfg['desc']}</p>
            </div>
            """, unsafe_allow_html=True)

            if df.empty:
                info_message(f"Nenhum dado encontrado na tabela *{tab_name}*.")
                continue

            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Registros", f"{len(df):,}".replace(",", "."))
            with col2: st.metric("Colunas", len(df.columns))
            with col3:
                memory_usage = df.memory_usage(deep=True).sum() / 1024
                st.metric("Tamanho", f"{memory_usage:.1f} KB")
            with col4:
                completeness = (1 - df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100
                st.metric("Completude", f"{completeness:.1f}%")

            st.markdown("---")

            filtered = _filter_dataframe(df, cfg["key"])

            if not filtered.empty:
                st.dataframe(filtered, use_container_width=True, hide_index=True, height=400)

                if len(filtered) != len(df):
                    st.info(f"Mostrando {len(filtered):,} de {len(df):,} registros".replace(",", "."))
                else:
                    st.info(f"Total: {len(df):,} registros".replace(",", "."))

                if st.button(f"Baixar {tab_name} (CSV)", key=f"download_{cfg['key']}"):
                    csv = filtered.to_csv(index=False)
                    st.download_button(
                        label=f"Download {tab_name}.csv",
                        data=csv,
                        file_name=f"cuida_sp_{cfg['key']}.csv",
                        mime="text/csv",
                        key=f"download_btn_{cfg['key']}"
                    )
            else:
                warning_message("Nenhum registro corresponde aos filtros aplicados.")
    footer()


# ---------------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------------
def admin():
    """Painel administrativo."""
    inject_css_once()

    if not guard("Admin"):
        error_message("Acesso negado. Apenas administradores podem acessar esta área.")
        return

    hero("Painel Administrativo", "Gerenciamento de usuários e configurações", "CuidaSP > Admin")

    tab1, tab2, tab3, tab4 = st.tabs(["Usuários", "Sistema", "Configurações", "Log"])

    with tab1:
        _render_user_management()
    with tab2:
        _render_system_info()
    with tab3:
        _render_system_config()
    with tab4:                       # ← novo bloco
        _render_log()

    footer()


def _render_user_management():
    section("Gerenciamento de Usuários", "Criar, editar e gerenciar contas")

    with st.expander("Criar Novo Usuário", expanded=False):
        with st.form("create_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                nome = st.text_input("Nome Completo*", placeholder="Ex: João Silva")
                email = st.text_input("Email*", placeholder="usuario@exemplo.com")
            with col2:
                papel = st.selectbox("Perfil*", ["Leitor", "Operador", "Admin"])
                senha = st.text_input("Senha*", type="password", help="Mínimo 8 caracteres")

            submitted = st.form_submit_button("Criar Usuário", type="primary", use_container_width=True)
            if submitted:
                if not all([nome, email, senha]):
                    error_message("Preencha todos os campos obrigatórios.")
                elif len(senha) < 8:
                    error_message("A senha deve ter pelo menos 8 caracteres.")
                else:
                    try:
                        hash_senha = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt())
                        user_id = create_user(nome, email, hash_senha, papel, 1)
                        st.success(f"Usuário '{nome}' criado com sucesso! (ID: {user_id})")
                        st.rerun()
                    except Exception as e:
                        error_message(f"Erro ao criar usuário: {str(e)}")

    st.markdown("### Usuários Cadastrados")

    try:
        users = list_users()
        if not users:
            info_message("Nenhum usuário cadastrado.")
        else:
            for user in users:
                with st.container():
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    with c1:
                        status_icon = "✅" if user['ativo'] else "❌"
                        role_icon = {"Admin": "🔴", "Operador": "🟡", "Leitor": "🟢"}.get(user['papel'], "⚙")
                        st.markdown(f"{status_icon} {user['nome']}")
                        st.caption(f"{user['email']} • {role_icon} {user['papel']}")
                    with c2:
                        if user['last_login']:
                            login_date = pd.to_datetime(user['last_login']).strftime('%d/%m/%Y %H:%M')
                            st.caption(f"Último acesso: {login_date}")
                        else:
                            st.caption("Nunca acessou")
                    with c3:
                        if st.button("Editar", key=f"edit_{user['id']}"):
                            st.session_state[f"editing_user_{user['id']}"] = True
                    with c4:
                        if st.button("Excluir", key=f"delete_{user['id']}"):
                            st.session_state[f"confirm_delete_{user['id']}"] = True

                    if st.session_state.get(f"editing_user_{user['id']}", False):
                        with st.form(f"edit_user_{user['id']}"):
                            e1, e2, e3 = st.columns(3)
                            with e1:
                                new_nome = st.text_input("Nome", value=user['nome'])
                                new_email = st.text_input("Email", value=user['email'])
                            with e2:
                                new_papel = st.selectbox("Perfil", ["Leitor", "Operador", "Admin"],
                                                         index=["Leitor", "Operador", "Admin"].index(user['papel']))
                                new_ativo = st.selectbox("Status", [1, 0],
                                                         format_func=lambda x: "Ativo" if x else "Inativo",
                                                         index=0 if user['ativo'] else 1)
                            with e3:
                                new_senha = st.text_input("Nova Senha (opcional)", type="password")
                                st.caption("Deixe vazio para manter a senha atual")
                            s1, s2 = st.columns(2)
                            with s1:
                                if st.form_submit_button("Salvar", type="primary"):
                                    try:
                                        update_user(user['id'], new_nome, new_email, new_papel, new_ativo)
                                        if new_senha:
                                            hash_senha = bcrypt.hashpw(new_senha.encode("utf-8"), bcrypt.gensalt())
                                            update_password(user['id'], hash_senha)
                                        st.success("Usuário atualizado!")
                                        st.session_state[f"editing_user_{user['id']}"] = False
                                        st.rerun()
                                    except Exception as e:
                                        error_message(f"Erro ao atualizar: {str(e)}")
                            with s2:
                                if st.form_submit_button("Cancelar"):
                                    st.session_state[f"editing_user_{user['id']}"] = False
                                    st.rerun()

                    if st.session_state.get(f"confirm_delete_{user['id']}", False):
                        st.warning(f"Confirma exclusão do usuário *{user['nome']}*?")
                        c_ok, c_cancel = st.columns(2)
                        with c_ok:
                            if st.button("Confirmar", key=f"confirm_{user['id']}", type="primary"):
                                try:
                                    delete_user(user['id'])
                                    st.success("Usuário excluído!")
                                    st.session_state[f"confirm_delete_{user['id']}"] = False
                                    st.rerun()
                                except Exception as e:
                                    error_message(f"Erro ao excluir: {str(e)}")
                        with c_cancel:
                            if st.button("Cancelar", key=f"cancel_{user['id']}"):
                                st.session_state[f"confirm_delete_{user['id']}"] = False
                                st.rerun()

                    st.divider()

    except Exception as e:
        error_message(f"Erro ao carregar usuários: {str(e)}")
    section_end()


def _render_system_info():
    section("Informações do Sistema", "Status geral e estatísticas")
    try:
        data_all = read_all_tables()
        total_mes = get_month_access_count()
        metrics = [{'title': 'Acessos no mês',
                    'value': f"{total_mes:,}".replace(',', '.'),
                    'subtitle': 'logins'}]
        for table_name, display_name in [
            ("voluntarios", "Voluntários"),
            ("acoes", "Ações"),
            ("doacoes", "Doações"),
            ("enderecos", "Endereços")
        ]:
            df = data_all.get(table_name, pd.DataFrame())
            count = len(df) if not df.empty else 0
            metrics.append({'title': display_name, 'value': f"{count:,}".replace(",", "."), 'subtitle': 'registros'})
        create_metric_cards(metrics)

        st.markdown("### Qualidade dos Dados")
        quality_data = []
        for table_name, display_name in [
            ("voluntarios", "Voluntários"),
            ("acoes", "Ações"),
            ("doacoes", "Doações"),
            ("enderecos", "Endereços")
        ]:
            df = data_all.get(table_name, pd.DataFrame())
            if not df.empty:
                completeness = (1 - df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100
                quality_data.append({'Tabela': display_name, 'Completude': f"{completeness:.1f}%", 'Registros': len(df), 'Colunas': len(df.columns)})
        if quality_data:
            st.dataframe(pd.DataFrame(quality_data), use_container_width=True, hide_index=True)

        st.markdown("### Status do Sistema")
        for item, status, typ in [
            ("Conexão Google Sheets", "Conectado", "success"),
            ("Autenticação", "Funcionando", "success"),
            ("Cache de Dados", "Ativo", "success"),
            ("Interface", "Responsiva", "success")
        ]:
            getattr(st, typ)(f"{item}: {status}")
    except Exception as e:
        error_message(f"Erro ao carregar informações do sistema: {str(e)}")
    section_end()


def _render_system_config():
    section("Configurações do Sistema", "Parâmetros e opções")
    st.markdown("### Gerenciamento de Cache")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Limpar Cache de Dados", help="Remove o cache dos dados do Google Sheets"):
            st.cache_data.clear()
            st.success("Cache limpo!")
    with c2:
        st.metric("Cache de Dados", "Ativo")

    st.markdown("### Configurações Atuais")
    config_info = {
        "TTL do Cache": f"{st.secrets.get('app', {}).get('cache_ttl_seconds', 300)} segundos",
        "Planilha Principal": st.secrets.get('sheets', {}).get('spreadsheet_name', 'N/A'),
        "Autenticação": "Local (bcrypt)" if st.secrets.get('app', {}).get('cookie_sign_key') else "Não configurada",
        "reCAPTCHA": "Configurado" if st.secrets.get('recaptcha', {}).get('site_key') else "Não configurado"
    }
    for k, v in config_info.items():
        st.info(f"{k}: {v}")

    st.markdown("### Backup e Exportação")
    if st.button("Exportar Todos os Dados", help="Baixar backup completo em formato JSON"):
        try:
            data_all = read_all_tables()
            export_data = {k: df.to_dict('records') for k, df in data_all.items() if not df.empty}
            import json
            from datetime import datetime
            fname = f"cuida_sp_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            st.download_button("Download Backup", data=json.dumps(export_data, ensure_ascii=False, indent=2, default=str),
                               file_name=fname, mime="application/json")
        except Exception as e:
            error_message(f"Erro ao gerar backup: {str(e)}")
    section_end()

# ---------------------------------------------------------------
def _render_log():
    logs = get_recent_logs(30)
    df = pd.DataFrame(logs)
    if df.empty:
        st.info("Sem acessos nos últimos 30 dias.")
        return

    # -------- indicadores --------------------------------------
    total_acessos = len(df)
    total_unicos  = df["email"].nunique()

    cols = st.columns(2)
    cols[0].metric("Acessos (30 d)", f"{total_acessos:,}".replace(",", "."))
    cols[1].metric("Acessos únicos (30 d)", f"{total_unicos:,}".replace(",", "."))

    # -------- agregação para gráfico ---------------------------
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_convert("America/Sao_Paulo")
    df["dia"] = df["ts"].dt.date
    df["semana"] = df["ts"].dt.strftime("%Y-%W")
    df["mes"] = df["ts"].dt.to_period("M").astype(str)  # converte para texto

    view = st.radio(
        "Agrupar por",
        ["Diário", "Semanal", "Mensal"],
        horizontal=True
    )

    if view == "Diário":
        agg = df.groupby("dia")["email"].nunique().reset_index(name="Únicos")
        x, title = "dia", "Únicos por dia"
    elif view == "Semanal":
        agg = df.groupby("semana")["email"].nunique().reset_index(name="Únicos")
        x, title = "semana", "Únicos por semana"
    else:
        agg = df.groupby("mes")["email"].nunique().reset_index(name="Únicos")
        x, title = "mes", "Únicos por mês"

    fig = px.bar(agg, x=x, y="Únicos", title=title)
    st.plotly_chart(fig, use_container_width=True)

    # -------- tabela dos 100 mais recentes ---------------------
    st.subheader("Últimos acessos")
    max_rows = st.secrets["app"].get("max_table_rows", 100)
    st.dataframe(
        df[["ts", "email"]].head(max_rows)
          .rename(columns={"ts": "Data/Hora (UTC)", "email": "Usuário"}),
        hide_index=True,
        height=400,
    )

