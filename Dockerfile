# Dashboard de Perfilamiento de Clientes - imagen de la app Streamlit.
#
# Los datos de clientes que trae esta imagen ya estan anonimizados (identificaciones
# encriptadas con hash SHA-1, nombres/razon social/direccion eliminados, telefono/
# email enmascarados, marca/modelo de vehiculo reemplazados por etiquetas genericas
# -- ver backup/ en el repo local para los originales, fuera de git). Aun asi se
# copian UNICAMENTE los archivos que segmentation/config.py apunta de verdad
# (RUTA_CED_PARQUET/RUTA_RUC_PARQUET/RUTA_GEOJSON/RUTA_CATALOGO/
# RUTA_COMPRAS_PARQUET/RUTA_POSTVENTA_PARQUET) -- no las carpetas completas, para no
# incluir archivos que la app no usa.
#
# IMPORTANTE: compras.parquet y postventa.parquet se generan OFFLINE a partir de
# data/raw/Facturacion_Clientes.parquet corriendo scripts/convertir_facturacion.py
# (raiz del proyecto) ANTES de este build -- la facturacion completa (~778mil filas de
# postventa) ya NO se parsea dentro del contenedor: hacerlo en runtime disparaba un
# pico de ~2.9GB de RAM (medido), muy por encima del limite de 512MB de Render. Si
# Facturacion_Clientes.parquet se actualiza, hay que volver a correr ese script antes
# de reconstruir esta imagen.
#
# Multi-stage build: builder stage instala dependencias; runtime stage es minimal.
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies only in builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install requirements
COPY app/requirements.txt ./app/requirements.txt
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --no-compile --upgrade pip setuptools && \
    /opt/venv/bin/pip install --no-cache-dir --no-compile -r app/requirements.txt

# Paquete compartido (src/segmentation), instalado en modo EDITABLE dentro del venv
# del builder (antes de adelgazarlo). Editable y no otra cosa a proposito:
# segmentation/config.py deriva PROJECT_ROOT de su propia ubicacion en disco
# (Path(__file__).resolve().parents[2]) -- una instalacion no-editable copiaria el
# paquete dentro de site-packages y esa cuenta de "sube 2 niveles" dejaria de
# apuntar a /app. El modo editable deja el import resuelto hacia el ./src/ real,
# que se vuelve a copiar en el stage de runtime mas abajo con el mismo WORKDIR /app
# -- por eso la ruta registrada en el finder editable sigue siendo valida ahi.
COPY pyproject.toml ./pyproject.toml
COPY src/ ./src/
RUN /opt/venv/bin/pip install --no-cache-dir --no-compile --no-deps -e .

# Adelgazar el venv antes de copiarlo a la imagen final (no afecta como corre la
# app, solo quita bytes que nunca se usan en runtime):
# - pip/setuptools: no se vuelve a instalar nada dentro del contenedor.
# - carpetas test*/tests de cada paquete (pandas, scipy, numpy, pyarrow...): son
#   la suite de pruebas de esas librerias, no codigo que la app importe.
# - simbolos de depuracion de las .so compiladas (pandas/numpy/scipy/pyarrow):
#   "strip" los quita sin tocar el codigo que se ejecuta.
RUN rm -rf /opt/venv/lib/python3.12/site-packages/pip \
           /opt/venv/lib/python3.12/site-packages/setuptools \
           /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.12/site-packages/setuptools-*.dist-info \
           /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.* && \
    find /opt/venv -type d \( -name test -o -name tests \) -exec rm -rf {} + && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + && \
    find /opt/venv -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true

# Runtime stage: slim base + venv from builder
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies only (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set PATH to use venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1

# El finder de la instalacion editable (generado en el builder) apunta a ./src/
# bajo este mismo WORKDIR (/app) -- hay que volver a copiarlo aqui para que
# "import segmentation" resuelva en runtime.
COPY src/ ./src/

# Copy application code
COPY app/ ./app/

# Datos de clientes (ya anonimizados): solo los archivos que segmentation/config.py
# lee (ver nota de privacidad arriba).
COPY data/processed/identificaciones_ced.parquet ./data/processed/identificaciones_ced.parquet
COPY data/processed/identificaciones_ruc.parquet ./data/processed/identificaciones_ruc.parquet
COPY data/external/ecuador.geojson ./data/external/ecuador.geojson
COPY data/external/CatSegmentosWork.parquet ./data/external/CatSegmentosWork.parquet
COPY data/interim/compras.parquet ./data/interim/compras.parquet
COPY data/interim/postventa.parquet ./data/interim/postventa.parquet

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app/app.py", \
    "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
