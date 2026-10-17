# Perfilamiento de Clientes

Dashboard Streamlit de perfilamiento y buyer persona para clientes de una red de
concesionarios automotrices (personas naturales y clientes con RUC), con su propio
pipeline de datos y despliegue en Docker.

## Estructura

```
.
├── app/                     # App Streamlit
│   ├── app.py                 # entrypoint: filtros globales + st.tabs()
│   ├── data.py                 # wrapper que cachea (st.cache_data) la carga de segmentation.data
│   ├── ia_buyer_persona.py    # generación de texto de la ficha (Gemini -> Groq de respaldo)
│   ├── assets/                # estáticos (logo)
│   ├── resources/             # contexto de mercado curado a mano (IA)
│   └── tabs/                  # una pestaña por concepto de análisis
├── src/segmentation/        # paquete compartido: rutas, constantes y lógica de carga/derivación
│   ├── config.py               # PROJECT_ROOT, rutas de datos, SBU, órdenes de categorías, etc.
│   ├── data.py                  # cargar_datos(), perfiles de negocio, limpieza (sin Streamlit)
│   └── plotting.py             # tema Plotly compartido + Sankey/mapa coroplético
├── scripts/
│   └── convertir_facturacion.py  # conversión offline xlsb -> parquet (ver más abajo)
└── data/
    ├── raw/                    # fuente: Facturacion_Clientes.parquet, listados (nunca se sobreescribe)
    ├── interim/                # generado por convertir_facturacion.py (compras/postventa .parquet)
    ├── external/                # catálogos de referencia (vehículos: CatSegmentosWork.parquet, geojson de cantones)
    └── processed/               # entregable final que lee la app (identificaciones_ced.parquet / identificaciones_ruc.parquet)
```

**Todos los archivos de `data/` son Parquet** (no Excel/xlsb) y ya vienen **anonimizados**:
identificaciones encriptadas (hash SHA-1 determinista, el mismo valor real siempre
produce el mismo hash para que los cruces entre archivos sigan funcionando), nombres/
razón social/dirección eliminados, teléfono/email enmascarados (se preserva si existe
o no, no el valor real), y marca/modelo de vehículo reemplazados por etiquetas
genéricas consistentes (`Marca A`, `Modelo A1`, ...). Los originales con datos reales
quedan solo en `backup/` (fuera de git, ver `.gitignore`) para auditoría.

`src/segmentation/` es la única fuente de verdad para rutas, constantes de negocio
(`SBU`, órdenes de categorías) y la lógica de limpieza/derivación/segmentación — tanto
`app/` como `scripts/convertir_facturacion.py` importan de ahí en vez de duplicar código.

## Cómo correr la app

```powershell
# una sola vez, en el env conda SEC, parado en la raíz del proyecto:
& "C:\Users\MSI\anaconda3\envs\SEC\python.exe" -m pip install -e .

# cada vez que quieras levantar la app:
& "C:\Users\MSI\anaconda3\envs\SEC\python.exe" -m streamlit run app/app.py
```

El primer comando instala `src/segmentation` en modo editable para que tanto `app/`
como `scripts/` puedan hacer `import segmentation` sin hacks de `sys.path`.

Antes de la primera corrida, copia `.env.example` a `app/.env` y completa las claves
de `gemini_api_key` / `groq_key` (usadas por la pestaña Buyer Persona).

## Pipeline de datos

`data/interim/compras.parquet` y `data/interim/postventa.parquet` **no se generan en
cada arranque** de la app — se generan offline, una vez (o cada vez que se actualice
`data/raw/Facturacion_Clientes.parquet`), corriendo:

```powershell
& "C:\Users\MSI\anaconda3\envs\SEC\python.exe" scripts\convertir_facturacion.py
```

Parsear la facturación completa (~778 mil filas de postventa) en cada arranque dispara
un pico transitorio de ~2.9GB de RAM, muy por encima del límite de 512MB de hosting
tipo Render — por eso la app solo lee los Parquet ya recortados.

## Variables del vehículo

Viven a nivel de **compra**, no de cliente (un cliente puede tener varias). `MARCA`,
`COMBUSTIBLE`, `HIBRIDACION`, `CATEGORIA`, `SEGMENTO` y `SUBSEGMENTO` se obtienen
buscando el `MODELO` de cada compra en `data/external/CatSegmentosWork.parquet`; sin
coincidencia quedan como `SIN INFO`. `TRACCION` se infiere por texto del modelo;
`CILINDRADA` viene como dato real de facturación. `MARCA`/`MODELO` son etiquetas
genéricas (ver Privacidad), no los nombres reales de marca/modelo.

## Privacidad

Los datos en `data/` ya están anonimizados de forma permanente (no es una mascara en
pantalla, es el contenido real de los archivos):

- **Identificaciones** (cédula/RUC, en cualquier archivo): hash SHA-1 determinista
  sobre el valor numérico canónico — el mismo cliente real produce siempre el mismo
  hash en todos los archivos, para que los cruces (`IDENTIFICACION_CLIENTE` de
  facturación con `IDENTIFICACION` de la base de clientes) sigan funcionando.
- **Nombres, razón social y dirección exacta**: eliminados por completo (no hacen
  falta para nada del análisis).
- **Teléfono y email**: reemplazados por un valor ficticio determinista — se conserva
  si el cliente tiene o no ese canal (`TIENE_EMAIL`/`TIENE_CELULAR`), no el valor real.
- **Marca y modelo de vehículo**: reemplazados por etiquetas genéricas consistentes
  (`Marca A`, `Modelo A1`, ...) — el mismo vehículo real siempre recibe la misma
  etiqueta, en todos los archivos, para no romper el cruce facturación↔catálogo.

Además, al mostrar registros individuales en la interfaz, la identificación (ya
hasheada) se vuelve a encriptar para pantalla (`segmentation.data.anon_id` /
`tabla_segura`) y no se muestran columnas de nombres.

Los archivos **originales sin anonimizar** (con datos reales) quedan únicamente en
`backup/` en este equipo — esa carpeta está en `.gitignore` y nunca debe subirse a
ningún repositorio ni compartirse. Una excepción: `data/raw/listado/listado_clientes_2026_adic.xlsx`
está protegido con contraseña y no se pudo abrir ni anonimizar — se dejó intacto (sin
convertir a Parquet) hasta que alguien aporte la contraseña o lo reexporte sin cifrar.

## Docker

```bash
docker build -t analytic-dashboard-marcas:latest .
docker-compose up
```

`docker-compose.yml` monta `./data/{raw,interim,external,processed}` como volúmenes de
solo lectura para desarrollo local (sobrescriben los datos horneados en la imagen sin
reconstruirla); si despliegas a un servicio sin soporte de volúmenes, la app usa los
datos horneados igual.

## Filtros

- Barra lateral (personas CED): provincia, sexo, estado civil, nivel de instrucción,
  categoría de vehículo y marca (filtra por clientes con al menos una compra que
  cumpla el filtro).
- La pestaña Clientes con RUC tiene sus propios filtros.

## Pendiente

- Migrar `use_container_width` (deprecado en Streamlit) a `width=`.
- Botón de descarga del Excel/informe desde la interfaz.
