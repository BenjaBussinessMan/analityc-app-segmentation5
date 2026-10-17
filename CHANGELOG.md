# Registro de cambios

## 2026-10-16 (2) — Anonimizacion permanente de los datos fuente

Todos los archivos de `data/` se convirtieron a Parquet y se anonimizaron de forma
permanente (no es una mascara de pantalla, es el contenido real de los archivos).
Los originales quedaron respaldados en `backup/` (fuera de git, ver `.gitignore`).

- **Identificaciones** (CEDULA/IDENTIFICACION/RUC/IDENTIFICACION_CLIENTE, en todos
  los archivos): hash SHA-1 determinista sobre el valor numerico canonico — el mismo
  cliente real produce siempre el mismo hash en todo el proyecto, preservando los
  cruces entre facturacion y la base de clientes.
- **Nombres, razon social y direccion exacta**: eliminados (NOMBRES, RAZON_SOCIAL,
  RAZON_SOCIAL RUC, NOMBRES RC, DIRECCION, CALLE/NUMERO/INTERSECCION RUC,
  NOMBRE_CALLE RC, NUMERO_CASA, FECHA_NACIM/FECHA_NACIMIENTO).
- **Telefono/email**: enmascarados con un valor ficticio deterministico (se preserva
  si el cliente tiene o no el canal, no el valor real).
- **Marca y modelo de vehiculo**: reemplazados por etiquetas genericas consistentes
  (`Marca A`, `Modelo A1`, ...) en el catalogo (`CatSegmentosWork`) y en toda la
  facturacion — 235 marcas y 6,486 modelos unicos mapeados.
- `TIPO_PERSONA` (RUC) se precalculo ANTES de borrar `RAZON_SOCIAL RUC` (la regex que
  lo derivaba necesitaba el nombre real) y ahora viene ya calculado en el parquet.
- Conversion a Parquet: `Identificaciones_enriquecimiento VF.xlsx` -> dos archivos
  (`identificaciones_ced.parquet`, `identificaciones_ruc.parquet`); `Facturacion_Clientes.xlsb`
  -> `Facturacion_Clientes.parquet`; `CatSegmentosWork.xlsx` -> `.parquet`;
  `base_clientes.xlsx` -> `.parquet`. `Catalogos.xlsx` se elimino (estaba vacio).
  Los `.xlsx`/`.xlsb` originales se borraron del repo tras verificar la conversion.
- **Excepcion**: `data/raw/listado/listado_clientes_2026_adic.xlsx` esta protegido con
  contrasena — no se pudo abrir, anonimizar ni convertir. Se dejo intacto; necesita la
  contrasena (o un reexport sin cifrar) para procesarlo.
- `src/segmentation/config.py` y `data.py` actualizados a las nuevas rutas/parquet;
  `cargar_ruc()` ya no deriva `TIPO_PERSONA` (lo lee precalculado);
  `scripts/convertir_facturacion.py` lee Parquet en vez de `.xlsb` (con `polars`
  cambiado por `pandas`, mas simple) y ya no re-convierte `IDENTIFICACION_CLIENTE` a
  numerico (ya es el hash en string).
- Verificado extremo a extremo tras el cambio: mismas filas que antes en
  ced/ruc/compras_ced/compras_ruc/compras.parquet/postventa.parquet, mismo
  `TIPO_PERSONA` (168 Juridica / 294 Natural), joins facturacion↔clientes intactos,
  app Streamlit levanta sin errores contra los datos anonimizados.
- **Pendiente de seguridad**: `data/external/CatSegmentosWork.xlsx` y `Catalogos.xlsx`
  (con marca/modelo reales) se habian subido a GitHub en un commit anterior a esta
  anonimizacion — siguen visibles en el historial del repo remoto hasta que se
  reescriba el historial o se elimine/re-cree el repositorio.

## 2026-10-16

Reestructuración completa de carpetas del proyecto, enfocado exclusivamente en la app
Streamlit y el pipeline de datos que la alimenta (se dio de baja el notebook de
exploración, ya cumplido su propósito).

- `Dashboard/` → `app/`. `Dashboard/data.py` se dividió en un paquete compartido
  `src/segmentation/` (`config.py`, `data.py`, `plotting.py`, sin dependencia de
  Streamlit) + un wrapper fino `app/data.py` que agrega `st.cache_data`. Se agregó
  `pyproject.toml` para instalar `src/segmentation` en modo editable (`pip install -e .`)
  y así eliminar el hack de `sys.path.insert(..., "Dashboard")` que usaba
  `convertir_facturacion.py`.
- `Dashboard/Logo-Maresa.png` → `app/assets/Logo-Maresa.png`; `Dashboard/Recursos/` →
  `app/resources/` (renombrado para no chocar con el `Recursos/` de datos, ahora
  `data/external/`).
- `Inputs/` → `data/raw/`, `Recursos/` → `data/external/`, `Entrega/` →
  `data/processed/` (solo sobrevive `Identificaciones_enriquecimiento VF.xlsx`, el
  único archivo que lee la app), y los Parquet generados → `data/interim/`.
- `convertir_facturacion.py` (raíz) → `scripts/convertir_facturacion.py`.
- `Dockerfile` y `docker-compose.yml` actualizados a los nuevos nombres/rutas
  (`app/`, `data/{raw,interim,external,processed}`).
- Se agregó `.gitignore` (no existía) y se inició el repo git — `data/raw`,
  `data/interim` y `data/processed` quedan fuera de git (PII / generados); solo se
  versionan los catálogos pequeños de `data/external`.
- **Eliminado** (sin reemplazo): `AnalisisyPerfilamiento_Previo.ipynb` y todo lo que
  dependía de sus salidas (`generar_insights_negocio.py`,
  `Entrega/analisis_perfilamiento.md`, `Entrega/perfilamiento_clientes.xlsx`,
  `Entrega/respuestas_preguntas_negocio.md`); `Dashboard/auth.py` (login por
  whitelist, ya desconectado); `docs/` original (`Preguntas-Negocio.md`,
  `estructura-dashboard-app.md`, `estructura-notebook-exploracion.md`,
  `Insights/Conclusiones_0909.docx`, `Plantilla_BuyerPersona.pdf` x2);
  `Cotizaciones/` y `EntendimientoCOT.sql` (análisis no relacionado); 4 archivos
  huérfanos/duplicados en la raíz sin uso en código (3 `.xlsx` + un `.csv` de 66MB).

## 2026-09-09

Sesion de trabajo sobre el notebook `AnalisisyPerfilamiento_Previo.ipynb` y el
`Dashboard/` de Streamlit (ambos retirados en la reestructuración del 2026-10-16;
entrada conservada como historial). Cuatro bloques de cambios.

---

### 1. Notebook: variables del vehiculo 100% desde `CatSegmentosWork.xlsx`

- Eliminadas las funciones `motorizacion()`, `motorizacion_catalogo()` y `marca_modelo()`
  del notebook; ya no existe la columna `MOTORIZACION`.
- `con_catalogo()` ahora cruza el `MODELO` del cliente contra el catalogo por una
  clave normalizada (`MODELO_KEY`: colapsa espacios dobles + mayusculas) y trae
  **MARCA, COMBUSTIBLE, HIBRIDACION, CATEGORIA, SEGMENTO, SUBSEGMENTO**.
- Los modelos que no estan en el catalogo quedan como `"SIN INFO"` (1 cliente CED,
  5 RUC; cobertura 99.9% / 98.9%).
- Seccion 4 reescrita para usar solo esas variables (combustible, hibridacion,
  categoria, segmento) en lugar de heuristicos de texto.
- Secciones 5a, 7 y 9 (ficha): `MOTORIZACION` reemplazado por `COMBUSTIBLE`.
- `celda 2`: columnas del catalogo renombradas; se agrega `MODELO_KEY`.
- Outputs del notebook limpiados y re-ejecutados con `nbconvert` (kernel base `python3`).
  Backup del original de 13 MB en el scratchpad de la sesion.

### 2. Dashboard: mismo criterio que el notebook

- `Dashboard/data.py`: sin `marca_modelo()` / `motorizacion()` / `motorizacion_catalogo()`;
  `con_catalogo()` y `cargar_catalogo()` alineados con el notebook (`modelo_key()`,
  `CAT_VARS`, faltante = `"SIN INFO"`).
- `tabs/producto.py` reescrito con las variables del catalogo.
- `tabs/geografia.py` y `tabs/ficha.py`: `COMBUSTIBLE` en vez de `MOTORIZACION`.
- `SEGMENTO_VEHICULO` (carroceria inferida por texto) **eliminado** por completo de
  `data.py` y de todos los tabs; se usa `CATEGORIA` / `SEGMENTO` / `SUBSEGMENTO`.
- `Dashboard/README.md` actualizado.

### 3. Dashboard: rediseno de UI

- **Sin emojis** en ningun texto (titulo, `page_icon`, etiquetas de pestanas, captions).
- **Filtros nuevos** en la barra lateral: Estado civil, Nivel de instruccion,
  Categoria de vehiculo (reemplaza al filtro viejo de "segmento de vehiculo").
  El filtro de Generacion muestra el rango de edad (`format_func=gen_label`).
- **KPIs de mediana -> promedio** en todo el dashboard. Excepcion: Economico muestra
  salario mediano **y** promedio.
- Palabra "catalogo" / "oficial" quitada de los textos visibles.
- **Graficos de porcentaje** con formato `%` (`ticksuffix="%"`, `texttemplate="%{z:.0f}%"`
  en heatmaps).
- **Tablas de registros individuales**: `data.py::tabla_segura()` encripta la
  identificacion (SHA-1 truncado) y elimina columnas de nombres / razon social.
- **Pestana Demografico**: etiquetas de Generacion con el rango de edad entre comillas
  (`Gen X "46-61 años"`); treemap por PROFESION (top 20); diagrama de Sankey
  SEXO -> ESTADO_CIVIL -> RANGO_SALARIO -> CATEGORIA.
- **Pestana Economico**: KPI salario mediano + promedio; cuadro de carga financiera
  ahora por TIPO EMPLEO; tabla de salario y vehiculo por CARGO (top 15); top 15 de
  empresas empleadoras.
- **Pestana Geografia**: mapa coropletico corregido (se cruza contra todos los cantones
  del GeoJSON + `fitbounds="geojson"`, ya se ven las provincias sin datos); mix de
  rango salarial por region; heatmap de preferencia de modelos por region.
- Helpers nuevos en `data.py`: `GEN_RANGO`, `gen_label`, `ORDEN_SALARIO`, `anon_id`,
  `tabla_segura`.

### 4. Dashboard: respuestas a las preguntas de negocio

Analisis de `Preguntas-Negocio.md` (12 preguntas). Cada visual que responde una
lleva `st.caption("Pregunta de negocio: ...")`. Visuales nuevos:

- **Producto**: heatmap MODELO x PERFIL; oportunidades de up-selling (KPIs + tabla
  anonimizada de candidatos: modelo de entrada, salario >= $1.500, riesgo Bajo);
  `cap_comb` enriquecido con % instruccion superior y % casados.
- **Economico**: pre-aprobacion de credito (KPIs A1 + endeudamiento <= 12 meses);
  brecha ingreso vs ticket (gama alta con salario < 3 SBU); morosidad por rango de
  edad y por profesion.
- **Segmentacion**: `resumen_perfil` con estado civil y profesion frecuente.
- **Contactabilidad**: ranking de provincias por volumen absoluto de clientes con
  email + celular; vista consolidada de salud de la base (ingreso, buro, contacto).
- **Clientes con RUC**: seccion comparativa B2B (RUC) vs B2C (cedula) —
  `ruc.render(ruc, ced)`.
- **Geografia**: ranking de cantones por numero de clientes de alto ingreso (p75).

Constantes nuevas en `data.py`: `MODELOS_ENTRADA`, `SEGMENTOS_GAMA_ALTA`.

### Notas / limitaciones (vigentes)

- No hay precio de lista de vehiculos: el "ticket" se aproxima por el segmento.
- Los clientes con RUC no tienen campo de salario; en personas juridicas
  `SUELDO BASICOS` es siempre 0.
- La base es de clientes cerrados (sin prospectos): no es medible el impacto en
  tasa de conversion.
- Streamlit avisa que `use_container_width` quedara deprecado (dic-2025);
  pendiente migrar a `width=`.
- Ambiente: conda `SEC` (`C:\Users\MSI\anaconda3\envs\SEC\python.exe`).
  Correr el dashboard: `python -m streamlit run app/app.py` (antes `Dashboard/app.py`).
