"""Wrapper de Streamlit sobre el paquete `segmentation`: añade `st.cache_data`
a las funciones de carga y re-exporta las constantes/helpers que usan las tabs
(`from data import ...`), para no tener que tocar cada tab.

La lógica real de limpieza/derivación/segmentación vive en `segmentation.data`
(sin dependencia de Streamlit, también usada por `scripts/convertir_facturacion.py`).
"""
import streamlit as st

from segmentation.config import (  # noqa: F401 (re-exportadas para las tabs)
    GEN_RANGO, ORDEN_GENERACION, ORDEN_LOCALIDAD, ORDEN_PORTE,
    ORDEN_RIESGO, ORDEN_SALARIO, SBU, SEGMENTOS_ENTRADA, SEGMENTOS_GAMA_ALTA, gen_label,
)
from segmentation.plotting import (  # noqa: F401
    COLOR_SIN_DATOS, COLOR_TEXTO, PALETA_TEMA, base_geojson, sankey,
)
from segmentation.data import (  # noqa: F401
    anon_id, construir_compras, tabla_segura,
)
from segmentation.data import cargar_catalogo as _cargar_catalogo
from segmentation.data import cargar_ced as _cargar_ced
from segmentation.data import cargar_compras as _cargar_compras
from segmentation.data import cargar_geojson as _cargar_geojson
from segmentation.data import cargar_postventa as _cargar_postventa
from segmentation.data import cargar_ruc as _cargar_ruc

cargar_geojson = st.cache_data(show_spinner="Cargando GeoJSON de cantones...")(_cargar_geojson)
cargar_catalogo = st.cache_data(show_spinner="Cargando variables de vehículo por modelo...")(_cargar_catalogo)
cargar_ced = st.cache_data(show_spinner="Cargando y perfilando personas naturales (CED)...")(_cargar_ced)
cargar_ruc = st.cache_data(show_spinner="Cargando y perfilando clientes con RUC...")(_cargar_ruc)
cargar_compras = st.cache_data(show_spinner="Cargando facturación de vehículos...")(_cargar_compras)
cargar_postventa = st.cache_data(show_spinner="Cargando postventa (taller/repuestos/accesorización)...")(_cargar_postventa)


@st.cache_data(show_spinner="Cargando datos...")
def cargar_datos():
    """Punto de entrada único: devuelve (ced, ruc, compras_ced, compras_ruc, geojson) ya
    perfilados, apoyándose en las versiones cacheadas de arriba (cada capa se cachea por
    separado, igual que antes)."""
    geojson_ec = cargar_geojson()
    catalogo = cargar_catalogo()
    ced = cargar_ced(geojson_ec)
    ruc = cargar_ruc(geojson_ec)
    compras_vehiculos = cargar_compras(catalogo)
    ced, ruc, compras_ced, compras_ruc = construir_compras(ced, ruc, compras_vehiculos)
    return ced, ruc, compras_ced, compras_ruc, geojson_ec
