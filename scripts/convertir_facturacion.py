"""Conversion OFFLINE de data/raw/Facturacion_Clientes.parquet (ya anonimizado) a
los Parquet recortados que usa la app.

Corre esto UNA vez (o cada vez que se actualice Facturacion_Clientes.parquet) ANTES
de reconstruir la imagen de Docker. Genera:
  - data/interim/compras.parquet    (venta de vehiculos, grano de factura)
  - data/interim/postventa.parquet  (taller/repuestos/accesorizacion, recortado a las 5
    columnas que usa app/tabs/buyer_persona.py)

Por que: parsear la facturacion completa (~778 mil filas de postventa) dentro del
contenedor en cada arranque dispara un pico transitorio de ~2.9GB de RAM (medido),
muy por encima del limite de 512MB de Render. Leer estos Parquet ya recortados en
segmentation/data.py evita ese pico — Parquet es columnar, asi que solo se leen/
materializan las columnas que realmente hacen falta.

IDENTIFICACION_CLIENTE ya viene como hash (string) en Facturacion_Clientes.parquet
-- no se vuelve a tocar aqui, solo se propaga tal cual a compras/postventa.

Requiere el paquete `segmentation` instalado en modo editable (`pip install -e .` desde
la raiz del proyecto, una sola vez, en el env conda SEC).

Correr con el env conda SEC, parado en la raiz del proyecto:
    & "C:\\Users\\MSI\\anaconda3\\envs\\SEC\\python.exe" scripts\\convertir_facturacion.py
"""
import pandas as pd

from segmentation.config import (
    COLS_FACTURA_SIN_USO, COLS_POSTVENTA, RENAME_FACTURACION,
    RUTA_COMPRAS_PARQUET, RUTA_FACTURACION, RUTA_POSTVENTA_PARQUET,
)


def main():
    print(f"Leyendo {RUTA_FACTURACION}...")
    raw = pd.read_parquet(RUTA_FACTURACION)

    es_vehiculo = raw["LINEA_NEGOCIO_DESCRIPCION"] == "VEHICULOS"

    compras = raw[es_vehiculo].rename(columns=RENAME_FACTURACION)
    compras = compras.drop(columns=COLS_FACTURA_SIN_USO, errors="ignore")
    RUTA_COMPRAS_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    compras.to_parquet(RUTA_COMPRAS_PARQUET, index=False)
    print(f"Escrito {RUTA_COMPRAS_PARQUET} — {compras.shape[0]:,} filas x {compras.shape[1]} columnas "
          f"({RUTA_COMPRAS_PARQUET.stat().st_size / 1024:.0f} KB)")

    postventa = raw.loc[~es_vehiculo, COLS_POSTVENTA].copy()
    postventa.to_parquet(RUTA_POSTVENTA_PARQUET, index=False)
    print(f"Escrito {RUTA_POSTVENTA_PARQUET} — {postventa.shape[0]:,} filas x {postventa.shape[1]} columnas "
          f"({RUTA_POSTVENTA_PARQUET.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
