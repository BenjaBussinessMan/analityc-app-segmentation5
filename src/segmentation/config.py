"""Rutas y constantes compartidas por toda la app y el pipeline de datos.

Única fuente de verdad: antes `Dashboard/data.py` tenía su propia copia de
`SBU`/rutas y el notebook (ya retirado) otra, "sincronizadas a mano". Ahora
todo lo que necesite una ruta o una constante de negocio importa de aquí.
"""
import re
from pathlib import Path

# ------------------------------------------------------------------
# Rutas (ancladas a la raíz del proyecto, dos niveles arriba de este archivo:
# <raiz>/src/segmentation/config.py)
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

RUTA_CED_PARQUET = PROCESSED_DIR / "identificaciones_ced.parquet"
RUTA_RUC_PARQUET = PROCESSED_DIR / "identificaciones_ruc.parquet"
RUTA_GEOJSON = EXTERNAL_DIR / "ecuador.geojson"
RUTA_CATALOGO = EXTERNAL_DIR / "CatSegmentosWork.parquet"
RUTA_FACTURACION = RAW_DIR / "Facturacion_Clientes.parquet"
RUTA_COMPRAS_PARQUET = INTERIM_DIR / "compras.parquet"
RUTA_POSTVENTA_PARQUET = INTERIM_DIR / "postventa.parquet"

# ------------------------------------------------------------------
# Constantes de negocio
# ------------------------------------------------------------------
SBU = 482  # Salario Básico Unificado de referencia

ORDEN_GENERACION = ["Gen Z", "Millennial", "Gen X", "Baby Boomer", "Silent"]
ORDEN_RIESGO = ["Bajo", "Medio", "Alto", "Sin historial"]
ORDEN_LOCALIDAD = ["Capital provincial", "Cantón urbano secundario", "Cantón rural / disperso", "Sin dato"]
ORDEN_PORTE = ["Sin dato / 0", "Micro (~1 SBU)", "Pequena (2-3 SBU)", "Mediana+ (4+ SBU)"]
ORDEN_SALARIO = ["<1 SBU", "1-2 SBU", "2-3 SBU", "3-6 SBU", "6+ SBU"]

# Segmentos de entrada (para up-selling) y de gama alta (para brecha ingreso/ticket),
# por SEGMENTO del catalogo -- no por nombre de marca/modelo (que ya es generico).
SEGMENTOS_ENTRADA = {"A HB", "A SD", "B HB", "B SD", "B SUV"}
SEGMENTOS_GAMA_ALTA = {"D SUV", "E SUV", "PREMIUM SUV", "FULL SIZE PICK UPS"}

# Rango de edad (año 2026) al que corresponde cada generación, según generacion().
GEN_RANGO = {
    "Gen Z": "<=29 años", "Millennial": "30-45 años", "Gen X": "46-61 años",
    "Baby Boomer": "62-80 años", "Silent": ">=81 años", "Desconocida": "s/d",
}


def gen_label(g):
    """'Gen X' -> 'Gen X "46-61 años"' para las etiquetas de los gráficos."""
    r = GEN_RANGO.get(g)
    return f'{g} "{r}"' if r else str(g)


# Columnas que nunca se muestran en tablas (identidad / nombres) y las que se encriptan.
COLS_NOMBRE = {"NOMBRES", "RAZON_SOCIAL RUC", "NOMBRES RC", "REPRESENTANTE"}
COLS_ID = {"CEDULA", "IDENTIFICACION", "RUC"}

# Variables del vehículo que se traen buscando el MODELO en data/external/CatSegmentosWork.parquet.
CAT_VARS = ["MARCA_CAT", "COMBUSTIBLE", "HIBRIDACION", "CATEGORIA", "SEGMENTO", "SUBSEGMENTO"]

ORDEN_CALIF = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "D", "E"]
RANK_CALIF = {c: i for i, c in enumerate(ORDEN_CALIF)}
RIESGO_MAP = {"A1": "Bajo", "A2": "Bajo", "A3": "Bajo",
              "B1": "Medio", "B2": "Medio",
              "C1": "Alto", "C2": "Alto", "D": "Alto", "E": "Alto"}

ALIAS_CANTON = {
    "EL EMPALME": "EMPALME",
    "FRANCISCO DE ORELLANA": "ORELLANA",
    "GENERAL VILLAMIL (PLAYAS)": "PLAYAS",
    "PELILEO": "SAN PEDRO DE PELILEO",
    "PILLARO": "SANTIAGO DE PILLARO",
    "SANTO DOMINGO DE LOS COLORADOS": "SANTO DOMINGO",
    "YAGUACHI": "SAN JACINTO DE YAGUACHI",
    "SAN MIGUEL DE LOS BA": "SAN MIGUEL DE LOS BANCOS",
}

SIERRA = ("PICHINCHA", "AZUAY", "TUNGURAHUA", "IMBABURA", "COTOPAXI", "LOJA", "CHIMBORAZO",
          "CARCHI", "BOLIVAR", "CANAR")
COSTA = ("GUAYAS", "MANABI", "EL ORO", "LOS RIOS", "ESMERALDAS", "SANTA ELENA", "STO DGO", "SANTO DOMINGO")
ORIENTE = ("SUCUMBIOS", "ORELLANA", "NAPO", "PASTAZA", "MORONA", "ZAMORA")

PATRON_JURIDICA = re.compile(
    r"\b(S\.?A\.?S?|C\.?A\.?|CIA|LTDA|C\.?L\.?|COMPA[NÑ]|CORP|FUNDACION|ASOCIACION|COOP|E\.?P\.?|S\.?C\.?C)\b",
    re.I,
)

# ------------------------------------------------------------------
# Facturacion_Clientes.parquet (version anonimizada de la facturacion cruda) trae
# columnas que se renombran con sufijo _FACTURA para no chocar con las homonimas de
# ced/ruc al cruzar mas adelante. MODELO y CILINDRADA SI se usan (se quedan); el
# resto de RENAME_FACTURACION son columnas muertas (ningun tab las lee) que
# cargar_compras() descarta apenas se renombran. NOMBRES/RAZON_SOCIAL/DIRECCION/
# FECHA_NACIMIENTO ya no existen en el parquet (se eliminaron al anonimizar), por
# eso tampoco aparecen aqui -- rename()/drop(errors="ignore") toleran columnas
# ausentes sin error.
# ------------------------------------------------------------------
RENAME_FACTURACION = {
    "TIPO_CLIENTE": "TIPO_CLIENTE_FACTURA",
    "TIPO_DOCUMENTO": "TIPO_DOCUMENTO_FACTURA",
    "ESTADO_CIVIL": "ESTADO_CIVIL_FACTURA",
    "FECHA_CREACION": "FECHA_CREACION_FACTURA",
    "PARROQUIA": "PARROQUIA_FACTURA",
    "CIUDAD": "CIUDAD_FACTURA",
    "PROVINCIA": "PROVINCIA_FACTURA",
    "PAIS": "PAIS_FACTURA",
    "MARCA": "MARCA_CRUDA_FACTURA",        # evita choque con la MARCA que trae el catalogo
    "COMBUSTIBLE": "COMBUSTIBLE_FACTURA",  # evita choque con el COMBUSTIBLE que trae el catalogo
    "MODELO_DESCRIPCION": "MODELO",
    "CILINDRAJE_TECNICO": "CILINDRADA",    # dato real de facturacion, reemplaza el regex de antes
}
COLS_FACTURA_SIN_USO = [v for v in RENAME_FACTURACION.values() if v not in ("MODELO", "CILINDRADA")]

# Unicas columnas de postventa que lee app/tabs/buyer_persona.py (de ~55 originales).
COLS_POSTVENTA = ["IDENTIFICACION_CLIENTE", "NUM_FACTURA", "TOTAL",
                  "LINEA_NEGOCIO_DESCRIPCION", "SUBLINEA_NEGOCIO_DESCRIPCION"]
