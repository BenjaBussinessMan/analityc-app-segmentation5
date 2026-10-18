# Perfilamiento de Clientes — guía para construir una app analítica en producción

Este repositorio es un ejercicio de portafolio: quiero mostrar que un análisis de
datos se puede convertir en un **producto** — algo que otra persona pueda instalar,
correr, desplegar y mantener sin tener que entender primero toda mi cabeza. Lo escribo
en primera persona y con bastante detalle a propósito: la idea es que este README
funcione también como una guía de cómo pensar la construcción de una app analítica de
este tipo (no solo como documentación de referencia de este proyecto puntual).

La app es un dashboard de **perfilamiento de clientes y buyer persona** para una red de
concesionarios automotrices: quién compra, con qué capacidad de pago, qué producto
prefiere cada perfil, y una ficha de "comprador típico" redactada con IA a partir de
esos datos. Los datos de clientes y de producto están completamente anonimizados —
explico cómo y por qué en la sección de privacidad.

## 1. El punto de partida: conocer el negocio

Antes de escribir una sola línea de pipeline, hice un análisis estadístico y
exploratorio sobre los datos disponibles: qué variables existían, qué tan completas
estaban, y sobre todo, **qué pregunta de negocio tenía que responder cada una**. Sin
ese paso, es muy fácil terminar con un dashboard lleno de gráficos bonitos que no le
sirven a nadie para decidir nada. De ese análisis salieron las variables que realmente
importan para este caso — riesgo crediticio, capacidad de pago, preferencia de
producto, canal de contacto — y esas son las que terminaron viviendo en el pipeline que
describo abajo. Esa decisión temprana (qué incluir y qué no) condiciona toda la
arquitectura que viene después, así que vale la pena tratarla como parte del diseño
técnico, no como un paso previo descartable.

## 2. Fuentes de datos

La app está pensada para alimentarse de datos que, en una empresa real, normalmente
viven repartidos en varios sistemas:

- **Datos de clientes**: demografía, información financiera y de riesgo (salario,
  calificación de buró), ubicación — típicamente exportados desde el sistema de
  gestión de clientes o un data warehouse interno.
- **Datos transaccionales**: ventas y servicio postventa, a nivel de factura — el tipo
  de información que vive en un ERP o en el sistema de ventas de la empresa.
- **Catálogos de referencia**: atributos de producto (en este caso, de vehículo:
  marca, modelo, combustible, categoría, segmento) para poder enriquecer cada
  transacción con información que no viene en la venta misma.
- **Datos geográficos de referencia pública** (un GeoJSON de división territorial) para
  los mapas.

El pipeline de datos (ver más abajo) es agnóstico al origen exacto — puede ser un
export de un sistema legacy, una consulta a un ERP, una tabla de un data warehouse o
una API interna — lo único que le importa es que el dato llegue a `data/raw/` en
formato tabular. Esa es una decisión de diseño a propósito: separar "de dónde viene el
dato" de "qué hago con el dato" para que cambiar la fuente de origen no implique
reescribir el resto del pipeline.

## 3. Arquitectura: separar interfaz, lógica y datos

La estructura del proyecto está organizada alrededor de una idea simple: **separar qué
hace la app de cómo la app lo muestra**, y separar ambas cosas de los datos.

```
.
├── app/                     # SOLO interfaz: Streamlit, filtros, gráficos
│   ├── app.py                 # entrypoint: filtros globales + st.tabs()
│   ├── data.py                 # wrapper que le agrega cache de Streamlit a segmentation.data
│   ├── ia_buyer_persona.py    # generación de texto de la ficha (Gemini -> Groq de respaldo)
│   ├── assets/                # estáticos (logo)
│   └── tabs/                  # una pestaña por concepto de análisis
├── src/segmentation/        # SOLO lógica: rutas, constantes, limpieza, derivación
│   ├── config.py               # PROJECT_ROOT, rutas de datos, constantes de negocio, órdenes de categorías, etc.
│   ├── data.py                  # cargar_datos(), perfiles de negocio, limpieza (sin Streamlit)
│   └── plotting.py             # tema Plotly compartido + Sankey/mapa coroplético
├── scripts/
│   └── convertir_facturacion.py  # pipeline offline: transaccional crudo -> parquet servible
└── data/
    ├── raw/                    # fuente, tal como llega del sistema de origen; nunca se sobreescribe por código
    ├── interim/                # generado por el pipeline (ventas/postventa recortados)
    ├── external/                # catálogos de referencia (producto, geojson de ubicación)
    └── processed/               # el entregable final que lee la app
```

La pieza central de esta separación es `src/segmentation/`: un **paquete Python
instalable** (tiene su propio `pyproject.toml`, se instala con `pip install -e .`), no
una carpeta que se importa con trucos de `sys.path`. La razón de fondo: si la lógica de
limpieza y derivación de variables vive atada a Streamlit (por ejemplo, mezclada en el
mismo archivo que la interfaz), cualquier otro consumidor de esos datos — un script de
pipeline, un notebook de exploración, un test — termina copiando ese código a mano o
recurriendo a hacks de `sys.path` para importarlo desde fuera de la carpeta de la app.
Empaquetar la lógica como una librería normal evita ese problema por diseño: tanto la
app como cualquier script hacen `import segmentation`, igual que harían `import
pandas`, sin que les importe desde dónde se están ejecutando.

La carpeta `data/` sigue una convención bastante estándar en ciencia de datos
(inspirada en *cookiecutter-data-science*): `raw` es intocable, `interim` es lo que el
pipeline propio genera a partir de `raw`, `external` es información de referencia que
no se genera dentro del proyecto (el catálogo de producto), y `processed` es lo que la
app realmente consume. Separar estas cuatro etapas no es decoración: permite saber
exactamente qué pipeline hay que volver a correr si algo sale mal en `processed`, sin
tener que tocar la fuente original.

## 4. El pipeline de datos: de la fuente cruda a algo servible

Los datos transaccionales (ventas + postventa) llegan en un volumen considerable
(cientos de miles de filas). Procesar ese volumen completo en cada arranque de la app
es un error común y costoso: dispara picos de memoria que no se notan en una máquina de
desarrollo pero sí tumban una app en un hosting con poca RAM (por ejemplo, el plan
gratuito de Render, limitado a 512MB). La solución de diseño es separar la
**conversión** del **consumo**:

`scripts/convertir_facturacion.py` corre **una sola vez, fuera de la app** (o cada vez
que se actualiza la fuente): lee el dato transaccional crudo con `polars` (más liviano
que pandas para archivos grandes), se queda solo con las columnas que realmente hacen
falta, y escribe dos Parquet ya recortados en `data/interim/` — uno para ventas, otro
para postventa. La app en producción nunca toca el dato crudo: solo lee esos Parquet,
que son columnares y livianos. Si la fuente se actualiza, se corre el script de nuevo;
la conversión no es parte del arranque de la app.

## 5. Ingeniería de variables: lo que convierte datos crudos en un perfil

Las columnas que llegan de las fuentes no sirven para segmentar directamente — hay que
derivar variables de negocio a partir de ellas. Algunas de las que calcula
`segmentation/data.py`:

- **Nivel de riesgo**: la calificación de crédito viene como texto libre con varias
  operaciones separadas por coma o barra (ej. `"A1, A1 / C1"`). Se parsea, se extrae la
  peor calificación de cada cliente y se mapea a un nivel (`Bajo/Medio/Alto/Sin
  historial`) que sí es útil para segmentar.
- **Generación / rango de edad**: a partir del año de nacimiento, para poder agrupar
  por cohortes (Gen Z, Millennial, Gen X...) en vez de trabajar con decenas de valores
  de edad distintos.
- **Región y tipo de localidad**: se cruza provincia/cantón contra un GeoJSON para
  saber si un cliente vive en una capital provincial, un cantón urbano secundario o uno
  rural/disperso — eso alimenta el mapa coroplético.
- **Tipo de persona (natural vs. jurídica)**: se clasifica según si la razón social
  matchea un patrón de sociedad (S.A., Cía. Ltda., etc.). Esta variable merece una nota
  aparte más abajo, en privacidad, porque depende de un campo que termina
  anonimizado.
- **Atributos de producto por cruce de catálogo**: la marca/modelo no vive en la base
  de clientes, vive en la transacción (a nivel de *compra*, no de cliente — un cliente
  puede tener varias). Para traer combustible/categoría/segmento, se normaliza el
  string del modelo (mayúsculas, espacios colapsados) y se cruza contra el catálogo de
  referencia; sin coincidencia, queda marcado como información faltante en vez de
  romper el pipeline.

La regla general: **cada variable derivada vive en una función con nombre**, no inline
en medio de un notebook de exploración. Eso es lo que permite mover esta lógica a un
paquete reutilizable sin tener que reescribirla.

## 6. Privacidad y anonimización por diseño

Como este repositorio es público (es un portafolio), cualquier dataset con información
real de clientes necesita una etapa de anonimización **antes** de llegar a
`data/processed/` — no alcanza con ocultar el dato en pantalla, hay que anonimizarlo en
el archivo fuente, de forma permanente. Las reglas que aplica el pipeline:

- **Identificaciones** (cédula, RUC, identificador de cliente en las transacciones):
  hash determinista (SHA-1) sobre el valor numérico *canonicalizado* (sin ceros a la
  izquierda, sin el `.0` que agregan algunos formatos numéricos). "Determinista" es la
  palabra clave: el mismo cliente real tiene que producir el mismo hash en **todos**
  los archivos, porque si no, el cruce entre las transacciones y la base de clientes se
  rompe. Un hash aleatorio por archivo sería más "seguro" en teoría pero inútil en la
  práctica — anonimizaría los datos destruyendo la razón por la que se cruzan.
- **Nombres, razón social, dirección exacta**: eliminados por completo. Ningún
  análisis de la app necesita el nombre real de alguien — si no se usa, no se guarda,
  es la forma más simple de evitar una fuga.
- **Teléfono y email**: no se eliminan, se *enmascaran* con un valor ficticio pero
  determinista, porque la app sí usa si un cliente **tiene o no** cada canal de
  contacto (para la pestaña de contactabilidad). Si se borrara la columna entera, esa
  pestaña perdería su insumo; reemplazar el valor por uno falso conserva la señal
  (tiene canal / no tiene) sin exponer el dato real.
- **Marca y modelo de producto**: reemplazados por etiquetas genéricas consistentes
  (`Marca A`, `Modelo A1`...) a partir de un mapeo fijo, no al azar por fila: el mismo
  producto real siempre se convierte en la misma etiqueta, en todos los archivos, para
  que el cruce entre transacciones y catálogo siga funcionando igual.

Un detalle de diseño importante acá: la variable `TIPO_PERSONA` (natural vs. jurídica)
se deriva leyendo el nombre real de la razón social con una expresión regular. Si se
elimina el nombre *antes* de calcular esa variable, se pierde la variable. La solución
es de orden de operaciones: **calcular la variable derivada mientras el dato real
todavía existe, guardar solo el resultado, y recién después anonimizar el dato
real.** Es un patrón generalizable a cualquier pipeline de anonimización: antes de
eliminar un campo sensible, hay que preguntarse qué se deriva de él río abajo, y mover
ese cálculo antes del paso de anonimización.

Todos los archivos de `data/` quedan en formato Parquet, ya anonimizados, listos para
usarse sin ningún paso manual adicional.

## 7. La capa de visualización: Streamlit + un tema de Plotly compartido

La app tiene filtros globales en la barra lateral (ubicación, sexo, estado civil,
categoría de producto, marca) que se aplican a las pestañas de personas naturales, y
una pestaña de clientes con RUC con sus propios filtros, porque el negocio B2B se
comporta distinto al B2C. Cada pestaña vive en su propio archivo bajo `app/tabs/`,
recibe los dataframes ya filtrados como parámetro y nunca lee un archivo directamente
— esa restricción es a propósito: si una pestaña necesitara leer datos por su cuenta,
dejaría de ser pura presentación y volvería a mezclar capas.

Para que los gráficos se vean consistentes entre pestañas, hay una sola paleta de
colores y una plantilla de Plotly definida en `segmentation/plotting.py`, registrada
como template global (`pio.templates.default`) — así ninguna pestaña define su propia
paleta, todas heredan la misma.

Un detalle de diseño que me gusta: la app tiene **más pestañas programadas de las que
muestra**. `TODAS_LAS_TABS` en `app.py` define ocho análisis distintos
(sociodemográfico, conductual, buyer persona, económico, producto, geografía, RUC,
contactabilidad), pero `TABS_VISIBLES` solo activa tres. Las demás quedan escritas,
probadas y listas — ocultas, no eliminadas — para poder ampliar el dashboard sin
reescribir nada el día que alguien pida ver más.

## 8. Buyer Persona con IA: cuando el dato no alcanza para contar la historia

Para cada producto, la app calcula una ficha con estadísticas (edad, ingreso, forma de
pago, adherencia a postventa) — eso es dato puro, sin IA. Pero un número no cuenta una
historia; para eso hay una capa de generación de texto con IA que redacta un perfil de
comprador en lenguaje natural, citando **únicamente** los datos ya calculados (el
modelo no tiene permiso de inventar cifras).

El diseño tiene dos niveles de respaldo, porque depende de un servicio externo y la app
no debería caerse si ese servicio no responde:

1. **Gemini** primero, recorriendo varios modelos de la misma familia en orden — si uno
   devuelve "sin cuota" (429) o "sobrecargado" (503), se reintenta con el siguiente en
   vez de fallar directo (cada modelo de Gemini tiene su propia cuota diaria
   independiente, lo que multiplica la capacidad efectiva sin costo extra).
2. Si **toda** la familia de Gemini falla, se cae a **Groq** (modelos open-source) como
   respaldo final.
3. Y si no se quiere (o no se puede) pagar por IA en absoluto, existe
   `texto_estatico()`: un párrafo armado con plantillas de texto simple, sin costo, que
   siempre está disponible usando los mismos datos ya calculados.

Además, el resultado se cachea por combinación exacta de producto/período en disco
(`st.cache_data(persist="disk")`) — si dos personas piden el mismo perfil, la segunda
no vuelve a pagar la llamada a la API.

## 9. Consideraciones técnicas al construir algo así

Algunos puntos que conviene resolver desde el diseño, no después de que fallen en
producción:

- **Cualquier gráfico construido a partir de un filtro de usuario tiene que asumir que,
  en el peor caso, la selección queda vacía.** Un `value_counts()` sobre una selección
  muy chica puede devolver una serie vacía, y varias librerías de gráficos (Plotly
  Express incluida) no manejan bien recibir dos listas vacías para los ejes `x`/`y` —
  conviene poner una guarda explícita y mostrar un mensaje en vez de dejar que explote.
- **Un paquete compartido que calcula su propia raíz de proyecto a partir de su
  ubicación en disco** (`Path(__file__).resolve().parents[N]`) solo funciona así si se
  instala en modo editable — una instalación normal copia el paquete a otra carpeta
  (`site-packages`) y esa cuenta de "sube N niveles" deja de apuntar a donde debería.
  Si ese paquete se empaqueta dentro de una imagen de Docker, hay que instalarlo en modo
  editable también ahí, y copiar el código fuente en el mismo path relativo tanto en la
  etapa de build como en la de runtime de la imagen.
- **El hot-reload de Streamlit solo cubre los archivos de la carpeta de la app**, no un
  paquete instalado por separado. Si se edita código dentro del paquete compartido
  mientras la app está corriendo, hace falta reiniciar el proceso completo para que el
  cambio se refleje — el auto-reload no alcanza a detectarlo.

## 10. Empaquetado y despliegue

El `Dockerfile` usa build multi-etapa: una etapa instala dependencias y el paquete
propio dentro de un entorno virtual; la segunda copia solo ese entorno ya armado a una
imagen base liviana (`python:3.12-slim`), sin las herramientas de compilación que ya no
hacen falta en producción. Antes de copiar el entorno a la imagen final, se "adelgaza":
se quitan `pip`/`setuptools` (ya no se vuelve a instalar nada dentro del contenedor),
las carpetas de tests de cada librería, y los símbolos de depuración de los binarios
compilados (`strip`). Nada de esto cambia cómo corre la app — solo reduce cuántos MB
hay que descargar para desplegarla.

El contenedor **sí** trae horneados los datos ya anonimizados (es una decisión
deliberada: así se puede desplegar en un servicio sin soporte de volúmenes
persistentes, como el plan gratuito de Render), pero solo copia los archivos exactos
que el código necesita, no carpetas completas — así se evita llevar accidentalmente
algo que no debería estar ahí.

Para desarrollo local, `docker-compose.yml` monta `data/` como volumen de solo lectura,
para poder probar con una copia de datos más reciente sin reconstruir la imagen cada
vez. La imagen final se sube a un registro de contenedores (Docker Hub) y desde ahí se
despliega como "Existing Image" en el servicio de hosting — sin que ese servicio tenga
que reconstruir nada, solo hacer `pull` y correr.

## 11. Cómo correrlo

```powershell
# una sola vez, en el entorno de Python, parado en la raíz del proyecto:
python -m pip install -e .

# cada vez que se quiera levantar la app:
python -m streamlit run app/app.py
```

Antes de la primera corrida, copia `.env.example` a `app/.env` y completa las claves
de `gemini_api_key` / `groq_key` (usadas por la pestaña Buyer Persona; la app funciona
igual sin ellas, solo sin el texto generado por IA).

Si hace falta regenerar los datos intermedios de transacciones:

```powershell
python scripts\convertir_facturacion.py
```

Y para la imagen de Docker:

```bash
docker build -t analytic-dashboard-marcas:latest .
docker-compose up
```

## 12. Stack técnico

| Capa | Herramienta | Por qué |
|---|---|---|
| Interfaz | Streamlit | Prototipo a producto rápido, sin escribir HTML/JS a mano |
| Gráficos | Plotly Express | Interactivo, tema compartido, funciona bien dentro de Streamlit |
| Datos | pandas + polars | pandas para la lógica de negocio; polars para leer archivos crudos pesados sin que se dispare el consumo de memoria |
| Empaquetado | `pyproject.toml` + `pip install -e .` | Lógica compartida real entre la app y los scripts, sin duplicar código |
| IA generativa | Gemini (primario) + Groq (respaldo) | Dos proveedores para no depender de la disponibilidad de uno solo |
| Contenedores | Docker multi-stage | Imagen final liviana, pensada para hosting con poca RAM |
| Privacidad | hash determinista + mapeos de anonimización | Útil para análisis, inofensivo si se filtra |

## 13. Qué sigue

- Migrar `use_container_width` (que Streamlit va a deprecar) a `width=`.
- Agregar un botón de descarga del análisis directo desde la interfaz.
- Escribir pruebas automatizadas para los casos límite de filtrado (selecciones vacías)
  antes de que vuelvan a aparecer en producción.
