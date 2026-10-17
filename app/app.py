"""
Dashboard de Perfilamiento de Clientes - prototipo Streamlit.

Interfaz de una sola pagina con pestanas agrupadas por concepto de analisis.

Ejecutar con:
    streamlit run app/app.py
"""
from pathlib import Path

import streamlit as st

from data import cargar_datos
from tabs import (buyer_persona, conductual, contactabilidad, economico, geografia,
                   perfil_sociodemografico, ruc, producto)

st.set_page_config(page_title="Perfilamiento de Clientes - Dashboard Empresarial", layout="wide")

st.markdown(
    """
    <style>
    /* ---- Paleta general: fondo lila-gris claro, tarjetas blancas, sidebar pizarra oscura ---- */
    .stApp { background-color: #EEF1F7; }
    [data-testid="stHeader"] { background-color: rgba(0,0,0,0); }

    h1, h2, h3, h4 { color: #2E3348 !important; }
    p, span, label, .stMarkdown, .stCaption { color: #2E3348; }

    /* ---- Sidebar: angosta y en gris pizarra oscuro, texto claro ---- */
    section[data-testid="stSidebar"] { width: 230px !important; background-color: #424A60; }
    section[data-testid="stSidebar"] > div { width: 230px !important; }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] .stCaption {
        color: #E8ECF3 !important;
    }

    /* ---- Metricas (KPIs) como tarjetas blancas con sombra ---- */
    [data-testid="stMetric"] {
        background-color: #FFFFFF;
        border-radius: 14px;
        padding: 14px 16px;
        box-shadow: 0 2px 10px rgba(46, 51, 72, 0.08);
    }
    [data-testid="stMetricValue"] { color: #2F8FFF; font-weight: 700; }
    [data-testid="stMetricLabel"] { color: #8A93A8; }

    /* ---- Graficos de Plotly envueltos en tarjeta blanca con sombra ---- */
    [data-testid="stPlotlyChart"] {
        background-color: #FFFFFF;
        border-radius: 14px;
        padding: 10px;
        box-shadow: 0 2px 10px rgba(46, 51, 72, 0.08);
    }

    /* ---- Tablas con bordes redondeados ---- */
    [data-testid="stDataFrame"] {
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 2px 10px rgba(46, 51, 72, 0.08);
    }

    /* ---- Expanders como tarjetas ---- */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF;
        border-radius: 14px;
        box-shadow: 0 2px 10px rgba(46, 51, 72, 0.06);
        border: none;
    }

    /* ---- Pestanas: mas separadas, con un separador vertical entre cada una,
       y subrayado de acento en la tab activa ---- */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab-list"] button[data-baseweb="tab"] { padding: 8px 24px; }
    .stTabs [data-baseweb="tab-list"] button[data-baseweb="tab"]:not(:last-child) {
        border-right: 1px solid #AEB6CC;
    }
    .stTabs [aria-selected="true"] { color: #2F8FFF !important; font-weight: 600; }
    .stTabs [data-baseweb="tab-highlight"] { background-color: #2F8FFF !important; }

    hr { border-color: #D7DCE8 !important; }

    input[type="radio"], input[type="checkbox"] { accent-color: #2F8FFF; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Perfilamiento de Clientes - Dashboard Empresarial")
st.caption(
    "Prototipo1"
    "(personas naturales y clientes con RUC)."
)

with st.spinner("Cargando datos..."):
    ced, ruc_df, compras_ced, compras_ruc, geojson_ec = cargar_datos()

# ------------------------------------------------------------------
# Filtros globales (aplican a las pestanas basadas en personas / CED)
# ------------------------------------------------------------------
st.sidebar.image(str(Path(__file__).resolve().parent / "assets" / "Logo.png"))
st.sidebar.header("Filtros - personas (CED)")

f_provincia = st.sidebar.multiselect("Provincia", sorted(ced["PROVINCIA"].dropna().unique()))
f_sexo = st.sidebar.multiselect("Sexo", sorted(ced["SEXO"].dropna().unique()))
f_civil = st.sidebar.multiselect("Estado civil", sorted(ced["ESTADO_CIVIL"].dropna().unique()))
f_instr = st.sidebar.multiselect("Nivel de instruccion", sorted(ced["INSTRUCCION"].dropna().unique()))
f_categoria = st.sidebar.multiselect("Categoria de vehiculo", sorted(compras_ced["CATEGORIA"].dropna().unique()))
f_marca = st.sidebar.multiselect("Marca", sorted(compras_ced["MARCA"].dropna().unique()))

df_ced = ced.copy()
if f_provincia:
    df_ced = df_ced[df_ced["PROVINCIA"].isin(f_provincia)]
if f_sexo:
    df_ced = df_ced[df_ced["SEXO"].isin(f_sexo)]
if f_civil:
    df_ced = df_ced[df_ced["ESTADO_CIVIL"].isin(f_civil)]
if f_instr:
    df_ced = df_ced[df_ced["INSTRUCCION"].isin(f_instr)]
if f_categoria:
    ids_categoria = compras_ced.loc[compras_ced["CATEGORIA"].isin(f_categoria), "IDENTIFICACION"].unique()
    df_ced = df_ced[df_ced["IDENTIFICACION"].isin(ids_categoria)]
if f_marca:
    ids_marca = compras_ced.loc[compras_ced["MARCA"].isin(f_marca), "IDENTIFICACION"].unique()
    df_ced = df_ced[df_ced["IDENTIFICACION"].isin(ids_marca)]

df_compras_ced = compras_ced[compras_ced["IDENTIFICACION"].isin(df_ced["IDENTIFICACION"])]

st.sidebar.caption(f"{len(df_ced):,} / {len(ced):,} personas seleccionadas")
st.sidebar.caption(f"{len(ruc_df):,} clientes con RUC (filtros propios en su pestana)")

with st.sidebar.expander("Info: prototipo"):
    st.write(
        "Los filtros de esta barra aplican a las pestanas visibles de personas naturales "
        "(Perfil Sociodemografico, Conductual, Buyer Persona)."
    )

if df_ced.empty:
    st.warning("No hay personas que cumplan los filtros seleccionados. Ajusta los filtros en la barra lateral.")
    st.stop()

# ------------------------------------------------------------------
# Pestanas
# ------------------------------------------------------------------
# Todas las pestanas existen aqui (con su nombre y su logica de render), pero solo se
# muestran las que estan en TABS_VISIBLES - las demas quedan ocultas, no eliminadas,
# para poder volver a activarlas facilmente mas adelante.
TODAS_LAS_TABS = [
    ("Perfil Sociodemografico", lambda: perfil_sociodemografico.render(df_ced, df_compras_ced, geojson_ec)),
    ("Conductual", lambda: conductual.render(df_ced, df_compras_ced)),
    ("Buyer Persona", lambda: buyer_persona.render(df_ced, df_compras_ced)),
    ("Economico y crediticio", lambda: economico.render(df_ced, df_compras_ced)),
    ("Producto", lambda: producto.render(df_ced, df_compras_ced)),
    ("Geografia y localidad", lambda: geografia.render(df_ced, df_compras_ced, geojson_ec)),
    ("Clientes con RUC", lambda: ruc.render(ruc_df, compras_ruc, ced, compras_ced)),
    ("Contactabilidad", lambda: contactabilidad.render(df_ced, ruc_df)),
]

TABS_VISIBLES = {"Perfil Sociodemografico", "Conductual", "Buyer Persona"}

tabs_activas = [(nombre, fn) for nombre, fn in TODAS_LAS_TABS if nombre in TABS_VISIBLES]
for (nombre, fn), tab in zip(tabs_activas, st.tabs([nombre for nombre, _ in tabs_activas])):
    with tab:
        fn()
