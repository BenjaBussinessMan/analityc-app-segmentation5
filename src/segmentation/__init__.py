"""Paquete compartido de carga/limpieza/segmentación de clientes.

Lo consumen tanto la app Streamlit (`app/`) como el script de conversión
de facturación (`scripts/convertir_facturacion.py`). No depende de Streamlit:
el cacheo (`st.cache_data`) vive en el wrapper fino `app/data.py`, no aquí.
"""
