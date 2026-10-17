"""Carga y enriquecimiento de datos de clientes (personas CED + RUC) y de sus
compras/postventa de vehículo.

Puro: sin `st.cache_data` ni ninguna dependencia de Streamlit, para que tanto
la app (`app/data.py`, que sí cachea estas funciones) como
`scripts/convertir_facturacion.py` puedan importarlo sin necesitar un entorno
Streamlit activo.
"""
import hashlib
import json

import numpy as np
import pandas as pd
import polars as pl

from segmentation.config import (
    CAT_VARS, COLS_ID, COLS_NOMBRE, ORDEN_PORTE, RANK_CALIF,
    RIESGO_MAP, RUTA_CATALOGO, RUTA_CED_PARQUET, RUTA_COMPRAS_PARQUET, RUTA_GEOJSON,
    RUTA_POSTVENTA_PARQUET, RUTA_RUC_PARQUET, SBU, SIERRA, COSTA, ORIENTE, ALIAS_CANTON,
)


# ------------------------------------------------------------------
# Utilidades de limpieza / variables derivadas
# ------------------------------------------------------------------
def a_numero(s):
    return pd.to_numeric(s, errors="coerce")


def parse_calificacion(x):
    """(n_operaciones, peor_calificacion) desde un texto tipo 'A1, A1 / C1'."""
    if pd.isna(x):
        return (0, np.nan)
    tokens = [t.strip().upper() for t in str(x).replace("/", ",").split(",") if t.strip()]
    validos = [t for t in tokens if t in RANK_CALIF]
    peor = max(validos, key=lambda t: RANK_CALIF[t]) if validos else np.nan
    return (len(tokens), peor)


def generacion(edad):
    if pd.isna(edad):
        return "Desconocida"
    anio = 2026 - int(edad)
    if anio >= 1997:
        return "Gen Z"
    if anio >= 1981:
        return "Millennial"
    if anio >= 1965:
        return "Gen X"
    if anio >= 1946:
        return "Baby Boomer"
    return "Silent"


def modelo_key(serie: pd.Series) -> pd.Series:
    """Clave normalizada de MODELO para el cruce con el catálogo (colapsa espacios, mayúsculas)."""
    return serie.astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.upper()


def con_catalogo(df: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    """Trae las variables del vehículo — MARCA, COMBUSTIBLE, HIBRIDACION, CATEGORIA,
    SEGMENTO, SUBSEGMENTO — buscando el MODELO del cliente. Sin coincidencia -> 'SIN INFO'."""
    out = df.copy()
    out["MODELO_KEY"] = modelo_key(out["MODELO"])
    out = out.merge(catalogo[["MODELO_KEY"] + CAT_VARS], on="MODELO_KEY", how="left")
    out = out.drop(columns="MODELO_KEY")
    out["EN_CATALOGO"] = out["COMBUSTIBLE"].notna()
    out[CAT_VARS] = out[CAT_VARS].fillna("SIN INFO")
    out["MARCA"] = out.pop("MARCA_CAT")
    return out


def traccion(m):
    return "4x4" if "4X4" in str(m).upper() else "4x2"


def region(prov):
    p = str(prov).upper().replace("Ð", "N").replace("ð", "N")
    if p.startswith("GALAPAGOS"):
        return "Insular"
    if any(p.startswith(s) for s in SIERRA):
        return "Sierra"
    if any(p.startswith(s) for s in COSTA):
        return "Costa"
    if any(p.startswith(s) for s in ORIENTE):
        return "Oriente"
    return "Otra / s/d"


def _norm_canton(s):
    if pd.isna(s):
        return np.nan
    return str(s).upper().strip().replace("Ð", "Ñ")


def canton_geojson(s):
    n = _norm_canton(s)
    if pd.isna(n):
        return np.nan
    return ALIAS_CANTON.get(n, n)


def _tipo_localidad(serie_canton, capitales):
    counts = serie_canton.value_counts()

    def _clasif(c):
        if pd.isna(c):
            return "Sin dato"
        if c in capitales:
            return "Capital provincial"
        return "Cantón urbano secundario" if counts.get(c, 0) >= 15 else "Cantón rural / disperso"

    return serie_canton.map(_clasif)


def anon_id(valor):
    """Encripta una identificación para poder mostrarla en tabla sin exponerla."""
    if pd.isna(valor):
        return "s/d"
    return hashlib.sha1(str(valor).encode("utf-8")).hexdigest()[:10].upper()


def tabla_segura(df: pd.DataFrame, columnas) -> pd.DataFrame:
    """Devuelve `df[columnas]` sin columnas de nombres y con la identificación encriptada."""
    cols = [c for c in columnas if c.upper() not in COLS_NOMBRE]
    out = df.loc[:, cols].copy()
    for c in list(out.columns):
        if c.upper() in COLS_ID:
            out[c] = out[c].map(anon_id)
            out = out.rename(columns={c: "ID_ENCRIPTADO"})
    return out


# ------------------------------------------------------------------
# Perfiles de negocio
# ------------------------------------------------------------------
def perfil_persona(r):
    edad, sal, inst = r["EDAD"], r["SALARIO"], r["INSTRUCCION"]
    if r["NIVEL_RIESGO"] == "Alto":
        return "Riesgo crediticio"
    if pd.notna(sal) and sal >= 3000:
        return "Alto ingreso / Premium"
    if edad <= 32 and inst in ("SUPERIOR", "BACHILLERATO"):
        return "Joven profesional"
    if edad >= 60:
        return "Senior / Jubilado"
    if r["TIPO EMPLEO"] == "EMPLEADO PUBLICO" or r["ES_FFAA_POLICIA"]:
        return "Sector publico / FF.AA."
    if inst == "SUPERIOR" and (pd.isna(sal) or sal >= 900):
        return "Profesional consolidado"
    if pd.isna(sal):
        return "Ingreso no verificable"
    return "Asalariado medio"


def perfil_ruc(r):
    if r["TIPO_PERSONA"] == "Persona Juridica":
        return "Empresa mediana / flota" if r["PORTE"] == "Mediana+ (4+ SBU)" else "Empresa micro-pequena"
    if pd.notna(r["DEUDA_BASICOS"]) and r["DEUDA_BASICOS"] >= 100:
        return "Negocio personal apalancado"
    return "Profesional independiente / negocio propio"


# ------------------------------------------------------------------
# Carga (sin cachear — el wrapper de Streamlit en app/data.py decide qué cachear)
# ------------------------------------------------------------------
def cargar_geojson() -> dict:
    with open(RUTA_GEOJSON, encoding="utf-8") as f:
        return json.load(f)


def cargar_catalogo() -> pd.DataFrame:
    # columnas ya normalizadas al anonimizar: MARCA_CAT | MODELO | COMBUSTIBLE |
    # HIBRIDACION | CATEGORIA | SEGMENTO | SUBSEGMENTO (ver backup/ para el original).
    catalogo = pd.read_parquet(RUTA_CATALOGO)
    catalogo["MODELO_KEY"] = modelo_key(catalogo["MODELO"])
    return catalogo.drop_duplicates(subset="MODELO_KEY", keep="first")


def cargar_ced(geojson: dict) -> pd.DataFrame:
    ced = pd.read_parquet(RUTA_CED_PARQUET)

    ced["DEUDA_BASICOS"] = a_numero(ced["DEUDA BANCOS BASICOS"])
    ced["DEUDA_USD_APROX"] = ced["DEUDA_BASICOS"] * SBU
    ced[["N_OPERACIONES_BURO", "PEOR_CALIFICACION"]] = ced["CALIFICACION"].apply(
        lambda x: pd.Series(parse_calificacion(x))
    )
    ced["NIVEL_RIESGO"] = ced["PEOR_CALIFICACION"].map(RIESGO_MAP).fillna("Sin historial")
    ced["GENERACION"] = ced["EDAD"].apply(generacion)
    ced["RANGO_EDAD"] = pd.cut(ced["EDAD"], [0, 25, 35, 45, 55, 65, 120],
                               labels=["<=25", "26-35", "36-45", "46-55", "56-65", "65+"])
    ced["TIENE_SALARIO_FORMAL"] = ced["SALARIO"].notna()
    ced["RANGO_SALARIO"] = pd.cut(ced["SALARIO"], [0, 460, 900, 1500, 3000, 1e9],
                                  labels=["<1 SBU", "1-2 SBU", "2-3 SBU", "3-6 SBU", "6+ SBU"])
    ced["APALANCAMIENTO_MESES"] = ced["DEUDA_USD_APROX"] / ced["SALARIO"]
    ced["TIENE_DISCAPACIDAD"] = ced["CIUDADANO"].str.contains("DISCAPACID", na=False)
    ced["ES_FFAA_POLICIA"] = ced["CIUDADANO"].str.contains("MILITAR|POLICIA", na=False)
    ced["ES_EXTRANJERO"] = ced["CIUDADANO"].str.contains("EXTRANJERO", na=False) | ced["NACIONALIDAD"].ne("ECUATORIANA")
    ced["REGION"] = ced["PROVINCIA"].apply(region)

    capitales = {f["properties"]["DPA_DESCAN"] for f in geojson["features"] if f["properties"]["DPA_CANTON"][-2:] == "01"}
    cantones_geo = {f["properties"]["DPA_DESCAN"] for f in geojson["features"]}
    ced["CANTON_GEO"] = ced["CANTON"].apply(canton_geojson)
    ced["TIPO_LOCALIDAD"] = _tipo_localidad(ced["CANTON_GEO"], capitales)
    ced["EN_GEOJSON"] = ced["CANTON_GEO"].isin(cantones_geo)

    ced["TIENE_EMAIL"] = ced["EMAIL"].notna()
    ced["TIENE_CELULAR"] = ced[["CELULAR", "CELULAR2"]].notna().any(axis=1)
    ced["TIENE_FIJO"] = ced["TEL_AFI"].notna()
    ced["N_CANALES"] = ced[["TIENE_EMAIL", "TIENE_CELULAR", "TIENE_FIJO"]].sum(axis=1)
    ced["CONTACTO_OMNICANAL"] = ced["N_CANALES"].eq(3)

    ced["PERFIL"] = ced.apply(perfil_persona, axis=1)

    return ced


def cargar_ruc(geojson: dict) -> pd.DataFrame:
    ruc = pd.read_parquet(RUTA_RUC_PARQUET)

    # TIPO_PERSONA ya viene precalculado en el parquet: se derivaba de RAZON_SOCIAL RUC
    # (regex de patron societario), pero ese nombre real ya no se conserva en los
    # datos fuente (anonimizados) -- se calculo una sola vez, antes de anonimizar.
    ruc["DEUDA_BASICOS"] = a_numero(ruc["DEUDA BANCOS BASICOS"])
    ruc["DEUDA_USD_APROX"] = ruc["DEUDA_BASICOS"] * SBU
    ruc["SUELDO_USD_APROX"] = a_numero(ruc["SUELDO BASICOS"]) * SBU
    ruc["PORTE"] = pd.cut(a_numero(ruc["SUELDO BASICOS"]), [-1, 0, 1, 3, 1e9],
                          labels=ORDEN_PORTE)
    ruc["REGION"] = ruc["PROVINCIA RUC"].apply(region)

    capitales = {f["properties"]["DPA_DESCAN"] for f in geojson["features"] if f["properties"]["DPA_CANTON"][-2:] == "01"}
    cantones_geo = {f["properties"]["DPA_DESCAN"] for f in geojson["features"]}
    ruc["CANTON_GEO"] = ruc["CANTON RUC"].apply(canton_geojson)
    ruc["TIPO_LOCALIDAD"] = _tipo_localidad(ruc["CANTON_GEO"], capitales)
    ruc["EN_GEOJSON"] = ruc["CANTON_GEO"].isin(cantones_geo)

    ruc["RUC_ACTIVO"] = ruc["ESTADO_RUC"].eq("ACTIVO")
    ruc["TIENE_EMAIL"] = ruc[["EMAIL RUC", "EMAIL"]].notna().any(axis=1)
    ruc["TIENE_CELULAR"] = ruc[["CELULAR", "CELULAR2"]].notna().any(axis=1)
    ruc["TIENE_FIJO"] = ruc[["TELEFONO RUC", "TEL_AFI"]].notna().any(axis=1)
    ruc["N_CANALES"] = ruc[["TIENE_EMAIL", "TIENE_CELULAR", "TIENE_FIJO"]].sum(axis=1)
    ruc["CONTACTO_OMNICANAL"] = ruc["N_CANALES"].eq(3)

    ruc["PERFIL"] = ruc.apply(perfil_ruc, axis=1)
    return ruc


def cargar_compras(catalogo: pd.DataFrame) -> pd.DataFrame:
    """Compras de vehículo a nivel de factura (relación N:1 con el cliente), desde
    data/interim/compras.parquet (pre-generado de Facturacion_Clientes.parquet, ver
    scripts/convertir_facturacion.py). Reemplaza el MODELO que antes venía en la base
    de clientes (ya no existe ahí): MARCA/COMBUSTIBLE/CATEGORIA/etc. se obtienen igual
    que antes cruzando el MODELO contra el catálogo oficial (con_catalogo)."""
    compras = pl.read_parquet(RUTA_COMPRAS_PARQUET).to_pandas()
    compras["TRACCION"] = compras["MODELO"].apply(traccion)
    compras = con_catalogo(compras, catalogo)  # -> COMBUSTIBLE, HIBRIDACION, CATEGORIA, SEGMENTO, SUBSEGMENTO, EN_CATALOGO
    # MARCA se toma de la propia facturacion (MARCA_DESCRIPCION, dato real de la venta) en
    # vez de la marca que infiere con_catalogo() por cruce de MODELO contra el catalogo —
    # esta ultima se descarta (sobrescrita aqui) porque puede no coincidir con la venta real.
    compras["MARCA"] = compras["MARCA_DESCRIPCION"]
    return compras


def cargar_postventa() -> pd.DataFrame:
    """Postventa (taller/repuestos/accesorización) a nivel de factura, desde
    data/interim/postventa.parquet (pre-generado de Facturacion_Clientes.parquet) — todo lo
    que NO es venta de vehículo, ya recortado a las 5 columnas que usa
    app/tabs/buyer_persona.py."""
    postventa = pl.read_parquet(RUTA_POSTVENTA_PARQUET).to_pandas()
    postventa["LINEA_NEGOCIO_DESCRIPCION"] = postventa["LINEA_NEGOCIO_DESCRIPCION"].astype("category")
    postventa["SUBLINEA_NEGOCIO_DESCRIPCION"] = postventa["SUBLINEA_NEGOCIO_DESCRIPCION"].astype("category")
    return postventa


def construir_compras(ced: pd.DataFrame, ruc: pd.DataFrame, compras: pd.DataFrame):
    """Une las compras (grano de factura) con los clientes (N:1) y pega a ced/ruc un
    resumen liviano (N_VEHICULOS_COMPRADOS, FECHA_ULTIMA_COMPRA_VEHICULO)."""
    compras_ced = compras.merge(ced, left_on="IDENTIFICACION_CLIENTE", right_on="IDENTIFICACION", how="inner")
    compras_ruc = compras.merge(ruc, left_on="IDENTIFICACION_CLIENTE", right_on="IDENTIFICACION", how="inner")

    resumen_ced = (compras_ced.groupby("IDENTIFICACION")
                   .agg(N_VEHICULOS_COMPRADOS=("NUM_FACTURA", "nunique"),
                        FECHA_ULTIMA_COMPRA_VEHICULO=("FECHA", "max"))
                   .reset_index())
    ced = ced.merge(resumen_ced, on="IDENTIFICACION", how="left")
    ced["N_VEHICULOS_COMPRADOS"] = ced["N_VEHICULOS_COMPRADOS"].fillna(0).astype(int)

    resumen_ruc = (compras_ruc.groupby("IDENTIFICACION")
                   .agg(N_VEHICULOS_COMPRADOS=("NUM_FACTURA", "nunique"),
                        FECHA_ULTIMA_COMPRA_VEHICULO=("FECHA", "max"))
                   .reset_index())
    ruc = ruc.merge(resumen_ruc, on="IDENTIFICACION", how="left")
    ruc["N_VEHICULOS_COMPRADOS"] = ruc["N_VEHICULOS_COMPRADOS"].fillna(0).astype(int)

    return ced, ruc, compras_ced, compras_ruc


def cargar_datos():
    """Punto de entrada único (sin cache): devuelve (ced, ruc, compras_ced, compras_ruc,
    geojson) ya perfilados. La app usa en su lugar el wrapper cacheado de `app/data.py`,
    que llama estas mismas funciones por capas para que Streamlit cachee cada una."""
    geojson_ec = cargar_geojson()
    catalogo = cargar_catalogo()
    ced = cargar_ced(geojson_ec)
    ruc = cargar_ruc(geojson_ec)
    compras_vehiculos = cargar_compras(catalogo)
    ced, ruc, compras_ced, compras_ruc = construir_compras(ced, ruc, compras_vehiculos)
    return ced, ruc, compras_ced, compras_ruc, geojson_ec


def _fmt(v, money=False):
    if pd.isna(v):
        return "s/d"
    return f"${v:,.0f}" if money else str(v)
