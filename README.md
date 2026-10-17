# Perfilamiento de Clientes — de un Excel desordenado a una app de producción

Este repositorio es, antes que nada, un ejercicio de portafolio: quiero mostrar no
solo que puedo hacer análisis de datos, sino que puedo convertir ese análisis en un
**producto** — algo que otra persona pueda instalar, correr, desplegar y mantener sin
tener que entender primero toda mi cabeza. Lo escribo en primera persona y con bastante
detalle a propósito: la idea es que este README funcione también como una guía de cómo
pensar la construcción de una app analítica de este tipo, no solo como documentación
de referencia.

La app es un dashboard de **perfilamiento de clientes y buyer persona** para una red de
concesionarios automotrices: quién les compra, con qué capacidad de pago, qué modelo
prefiere cada perfil, y una ficha de "comprador típico" redactada con IA. Los datos
reales de clientes y de marca/modelo están completamente anonimizados (lo explico más
abajo, es una de las partes que más tiempo me tomó y de las que estoy más orgulloso).

## 1. De dónde partí

Cuando empecé, tenía tres cosas sueltas, cada una en su propio desorden:

1. **Un Excel de identificaciones** con dos hojas: personas naturales (cédula) y
   clientes con RUC — demografía, salario, calificación de buró, provincia/cantón.
2. **Un archivo de facturación** (`.xlsb`, ~815 mil filas) con cada venta de vehículo y
   cada visita a postventa, mezclado todo en la misma tabla: nombre del cliente,
   dirección, modelo comprado, forma de pago, ticket de taller, todo junto.
3. **Un catálogo de vehículos** (marca, modelo, combustible, categoría, segmento) para
   poder cruzar el modelo que aparecía en la facturación con sus atributos.

Y los tenía organizados en carpetas con nombres como `Inputs/`, `Recursos/`, `Entrega/`
— nombres que describían *para quién* era el archivo en un momento dado, no *qué tipo
de dato* era ni *quién lo consumía*. Ese es el primer problema que quise resolver antes
de escribir una sola línea de análisis: **si la estructura de carpetas no comunica
nada, cada persona que entre al proyecto (incluido yo mismo en tres meses) tiene que
releer todo para entender qué es cada cosa.**

## 2. La primera decisión de arquitectura: separar app, lógica y datos

Lo que había al principio era un prototipo de notebook más una carpeta `Dashboard/`
con todo mezclado: la app de Streamlit, la limpieza de datos, las constantes de
negocio y hasta el login, todo en un mismo `data.py` de más de 500 líneas. Funcionaba,
pero tenía un problema de diseño que quería evitar en un proyecto que uso como
portafolio: **la lógica de negocio estaba atada a Streamlit**. No podía reutilizar la
limpieza de datos desde un script aparte sin arrastrar `import streamlit` con ella, y
cada vez que el notebook de exploración necesitaba la misma lógica, la copiaba a mano
— literalmente tenía un comentario en el código que decía "sincronizado a mano con el
notebook", que es la clase de frase que sé, por experiencia, que termina en un bug el
día que alguien actualiza un lado y se olvida del otro.

Así que reestructuré todo alrededor de una idea simple: **separar qué hace la app de
cómo la app lo muestra**.

```
.
├── app/                     # SOLO interfaz: Streamlit, filtros, gráficos
│   ├── app.py                 # entrypoint: filtros globales + st.tabs()
│   ├── data.py                 # wrapper que le agrega cache de Streamlit a segmentation.data
│   ├── ia_buyer_persona.py    # generación de texto de la ficha (Gemini -> Groq de respaldo)
│   ├── assets/                # estáticos (logo)
│   └── tabs/                  # una pestaña por concepto de análisis
├── src/segmentation/        # SOLO lógica: rutas, constantes, limpieza, derivación
│   ├── config.py               # PROJECT_ROOT, rutas de datos, SBU, órdenes de categorías, etc.
│   ├── data.py                  # cargar_datos(), perfiles de negocio, limpieza (sin Streamlit)
│   └── plotting.py             # tema Plotly compartido + Sankey/mapa coroplético
├── scripts/
│   └── convertir_facturacion.py  # pipeline offline: factura cruda -> parquet servible
└── data/
    ├── raw/                    # fuente, nunca se sobreescribe por código
    ├── interim/                # generado por el pipeline (compras/postventa .parquet)
    ├── external/                # catálogos de referencia (vehículos, geojson de cantones)
    └── processed/               # el entregable final que lee la app
```

`src/segmentation/` es un **paquete Python instalable** (tiene su propio
`pyproject.toml`, se instala con `pip install -e .`), no una carpeta que importo con
trucos de `sys.path`. Esa es la enseñanza que más quiero dejar aquí: en el prototipo
original, un script de conversión de datos necesitaba usar código de la app y lo
resolvía con `sys.path.insert(0, ".../Dashboard")` antes de importar — funciona, pero
es frágil y confuso (¿por qué un script de la raíz del proyecto depende de la carpeta
interna de otra cosa?). Convertir esa carpeta en un paquete de verdad significa que
tanto la app como cualquier script —incluidos los que escriba a futuro— hacen
`import segmentation` igual que harían `import pandas`, sin que les importe desde
dónde los estoy corriendo.

La carpeta `data/` sigue una convención bastante estándar en ciencia de datos
(inspirada en *cookiecutter-data-science*): `raw` es intocable, `interim` es lo que mi
propio pipeline genera a partir de `raw`, `external` es información de referencia que
no generé yo (el catálogo de vehículos), y `processed` es lo que la app realmente
consume. Separar estas cuatro etapas no es decoración: significa que si algo sale mal
en `processed`, sé exactamente qué pipeline tengo que volver a correr para
reproducirlo, sin tocar la fuente original.

## 3. El pipeline de datos: por qué no proceso todo en caliente

El archivo de facturación crudo tiene ~815 mil filas (778 mil solo de postventa). Mi
primer instinto fue, simplemente, leerlo cada vez que la app arranca. Probándolo me di
cuenta de que parsear ese `.xlsb` completo disparaba un pico transitorio de **~2.9GB de
RAM** — muy por encima de los 512MB que ofrece un plan gratuito de hosting como Render,
que es donde quiero poder desplegar esto sin pagar. Ese fue un momento de aprendizaje
importante: *medir* antes de optimizar. Si no hubiera corrido esa prueba, no habría sabido que el problema era real y de ese tamaño.

La solución fue separar la conversión del consumo: `scripts/convertir_facturacion.py`
corre **una vez, fuera de la app** (en mi máquina, con mi conda env), lee el crudo con
`polars` (más liviano que pandas para un archivo de ese tamaño), se queda solo con las
~45 columnas que realmente uso, y escribe dos Parquet ya recortados:
`data/interim/compras.parquet` (venta de vehículos) y `data/interim/postventa.parquet`
(taller/repuestos). La app en producción nunca toca el archivo crudo — solo lee esos
dos Parquet, que son columnares y livianos. Si la facturación se actualiza, corro el
script de nuevo y listo; no es parte del arranque de la app.

## 4. Ingeniería de variables: lo que convierte datos crudos en un perfil

Las columnas que vienen de los archivos fuente no sirven para segmentar directamente
— hay que derivar variables de negocio a partir de ellas. Algunas de las que calculo
en `segmentation/data.py`:

- **Nivel de riesgo**: la calificación de buró viene como texto libre tipo
  `"A1, A1 / C1"` (varias operaciones separadas por coma o barra). La parseo, extraigo
  la peor calificación de cada cliente y la mapeo a un nivel (`Bajo/Medio/Alto/Sin
  historial`) que sí es útil para segmentar.
- **Generación / rango de edad**: a partir del año de nacimiento, para poder agrupar
  por cohortes (Gen Z, Millennial, Gen X...) en vez de trabajar con 70 valores de edad
  distintos.
- **Región y tipo de localidad**: cruzo provincia/cantón contra un GeoJSON para saber
  si un cliente vive en una capital provincial, un cantón urbano secundario o uno
  rural/disperso — eso después alimenta el mapa coroplético.
- **Tipo de persona (RUC)**: si la razón social matchea un patrón de sociedad (S.A.,
  Cía. Ltda., etc.) la clasifico como persona jurídica; si no, como persona natural con
  RUC. (Ojo con esta — vuelvo sobre ella en la sección de privacidad, porque fue la
  variable que más dolores de cabeza me dio cuando anonimicé los datos.)
- **Variables de vehículo por cruce de catálogo**: la marca/modelo no vive en la base
  de clientes, vive en la facturación (a nivel de *compra*, no de cliente — un cliente
  puede tener varias). Para traer combustible/categoría/segmento, normalizo el string
  del modelo (mayúsculas, espacios colapsados) y lo cruzo contra el catálogo oficial;
  si no hay coincidencia, queda como `"SIN INFO"` en vez de romper el pipeline.

La regla que seguí en todo este trabajo: **cada variable derivada vive en una función
con nombre, no inline dentro de un notebook**. Eso es lo que me permitió, después,
mover todo este código de un notebook a un paquete sin tener que reescribirlo.

## 5. El problema de privacidad que no podía ignorar

Esto es, honestamente, la parte del proyecto de la que estoy más orgulloso, porque no
estaba en el plan original — me la encontré a mitad de camino y tuve que resolverla en serio, no con un parche.

Los archivos fuente tenían cédulas, nombres, direcciones, teléfonos y correos reales
de clientes — y, en el catálogo, nombres reales de marca y modelo. Como este repo es
público (portafolio), eso es exactamente el tipo de dato que **no puede** terminar en
un historial de git ni en una imagen de Docker que alguien más pueda inspeccionar. Mi
objetivo no era "ocultarlo en la pantalla" (eso ya lo hacía la app, encriptando la
identificación antes de mostrarla en una tabla) sino **anonimizar el dato en el
archivo fuente**, de forma permanente, antes de que llegara a cualquier lado.

Las reglas que me impuse:

- **Identificaciones** (cédula, RUC, identificación de cliente en facturación): hash
  SHA-1 determinista sobre el valor numérico *canonicalizado* (sin ceros a la
  izquierda, sin el `.0` que le pega pandas a un float). "Determinista" es la palabra
  clave: el mismo cliente real tiene que producir el mismo hash en **todos** los
  archivos, porque si no, el cruce entre la facturación y la base de clientes
  (`IDENTIFICACION_CLIENTE` contra `IDENTIFICACION`) se rompe. Un hash aleatorio por
  archivo hubiera sido más "seguro" en teoría pero inútil en la práctica — habría
  anonimizado los datos destruyendo la razón por la que los junto.
- **Nombres, razón social, dirección exacta**: directamente eliminados. No hay ningún
  análisis en la app que necesite el nombre real de alguien — si no se usa, no se
  guarda, es la forma más simple de evitar una fuga.
- **Teléfono y email**: no los elimino, los *enmascaro* con un valor ficticio pero
  determinista, porque la app sí usa si un cliente **tiene o no** cada canal de
  contacto (`TIENE_EMAIL`, `TIENE_CELULAR`) para la pestaña de contactabilidad. Si
  borraba la columna entera, esa pestaña se rompía; reemplazar el valor por uno falso
  mantiene la señal (tiene canal / no tiene) sin exponer el dato real.
- **Marca y modelo de vehículo**: reemplazados por etiquetas genéricas consistentes
  (`Marca A`, `Modelo A1`...) construidas con un mapeo — no al azar por fila, sino una
  tabla fija: el mismo modelo real siempre se convierte en la misma etiqueta, en todos
  los archivos (facturación y catálogo), para que el cruce entre ambos siga
  funcionando exactamente igual que antes.

Lo que más me obligó a pensar fue una dependencia escondida: la variable `TIPO_PERSONA`
(persona jurídica vs. natural) se calculaba leyendo el nombre real de la razón social
con una expresión regular. Si borraba el nombre *antes* de calcular esa variable,
perdía la variable. La solución fue de orden de operaciones, no de código complicado:
**calcular la variable derivada mientras el dato real todavía existe, guardar solo el
resultado, y recién después borrar el dato real.** Es un patrón que me parece
generalizable: antes de eliminar un campo sensible, preguntarse qué se deriva de él
río abajo.

Por último, convertí todos los archivos de Excel/`.xlsb` a Parquet (más chico, más
rápido de leer, sin fórmulas ni metadata de Office escondida) y borré los originales
del repositorio — con un respaldo local fuera de git, por si alguna vez necesito
re-derivar algo. Y como el catálogo con nombres reales de marca ya había llegado a
subirse a GitHub en un commit anterior, no bastaba con corregirlo hacia adelante:
**reescribí el historial de git** (un commit nuevo, limpio, con `force-push`) para que
esa versión con datos reales no quedara accesible ni en el historial. La lección ahí
es que "ya lo corregí en el commit de hoy" no es lo mismo que "ya no está expuesto" —
git recuerda todo lo que no le digas explícitamente que olvide.

## 6. La capa de visualización: Streamlit + un tema de Plotly compartido

La app tiene filtros globales en la barra lateral (provincia, sexo, estado civil,
categoría de vehículo, marca) que se aplican a las pestañas de personas naturales, y
una pestaña de "Clientes con RUC" con sus propios filtros porque el negocio B2B es
distinto al B2C. Cada pestaña vive en su propio archivo bajo `app/tabs/`, recibe los
dataframes ya filtrados como parámetro y nunca lee un archivo directamente — eso es a
propósito: si una pestaña necesitara leer datos por su cuenta, dejaría de ser pura
presentación y volvería a mezclar capas.

Para que los gráficos se vean consistentes entre pestañas, definí una sola paleta de
colores y una plantilla de Plotly en `segmentation/plotting.py`, registrada como
template global (`pio.templates.default`) — así ninguna pestaña define su propia
paleta, todas heredan la misma.

Un detalle de diseño que me gusta: la app tiene **más pestañas programadas de las que
muestra**. `TODAS_LAS_TABS` en `app.py` define ocho análisis distintos (sociodemográfico,
conductual, buyer persona, económico, producto, geografía, RUC, contactabilidad), pero
`TABS_VISIBLES` solo activa tres. Las demás quedan escritas, probadas y listas — ocultas,
no borradas — para poder ampliar el dashboard sin reescribir nada el día que alguien
pida ver más.

## 7. Buyer Persona con IA: cuando el dato no alcanza para contar la historia

Mi parte favorita del proyecto. Para cada modelo de vehículo, la app calcula una ficha
con estadísticas (edad, salario, forma de pago, adherencia a postventa) — eso es dato
puro, sin IA. Pero un número no cuenta una historia; para eso agregué una capa de
generación de texto con IA que redacta un perfil de comprador en lenguaje natural,
citando **únicamente** los datos ya calculados (no deja que el modelo invente cifras).

El diseño tiene dos niveles de respaldo, porque dependo de un servicio externo y no
quiero que la app se caiga si ese servicio no responde:

1. **Gemini** primero, recorriendo varios modelos de la misma familia en orden — si
   uno devuelve "sin cuota" (429) o "sobrecargado" (503), reintento con el siguiente en
   vez de fallar directo (cada modelo de Gemini tiene su propia cuota diaria
   independiente, así que esto multiplica la capacidad efectiva sin costo extra).
2. Si **toda** la familia de Gemini falla, caigo a **Groq** (modelos open-source) como
   respaldo final.
3. Y si alguien no quiere (o no puede) pagar por IA en absoluto, existe
   `texto_estatico()`: un párrafo armado con plantillas de texto simple, sin costo, que
   siempre está disponible usando los mismos datos ya calculados.

Además, cacheo el resultado por combinación exacta de marca/modelo/año en disco
(`st.cache_data(persist="disk")`) — si dos personas piden el mismo perfil, la segunda
no vuelve a pagar la llamada a la API.

## 8. Errores que cometí (y lo que aprendí de cada uno)

Prefiero dejar esto explícito en vez de pretender que todo salió bien a la primera:

- **Un gráfico que explotaba al filtrar por una marca específica.** Cuando un modelo
  tenía solo 1 o 2 compradores y a ninguno le faltaba, por ejemplo, el dato de "tipo de
  empleo", el `value_counts()` devolvía una serie vacía, y Plotly Express rechaza un
  `px.bar(x=[], y=[])` con dos listas vacías ("Cannot accept list of column references
  or list of columns for both x and y") — un mensaje de error que no deja nada claro
  qué pasó. La lección: **cualquier gráfico construido a partir de un filtro de
  usuario tiene que asumir que, en el peor caso, la selección queda vacía**, y probarlo
  con ese caso, no solo con el caso feliz.
- **Un `pip install` editable que dejaba de funcionar dentro de Docker.** Mi paquete
  compartido calcula su propia raíz de proyecto mirando dónde vive su propio archivo
  en disco (`Path(__file__).resolve().parents[2]`). Eso funciona perfecto en modo
  editable (el import apunta al código fuente real), pero si lo instalaba *normal*
  dentro de la imagen, pip copia el paquete a `site-packages` y esa cuenta de "sube dos
  niveles" deja de apuntar a `/app`. La solución fue instalar en modo editable también
  dentro del contenedor, y asegurarme de copiar el código fuente en el mismo path
  relativo tanto en la etapa de build como en la de runtime de la imagen.
- **Cambios que no se reflejaban aunque el archivo sí había cambiado.** Streamlit
  recarga en caliente los archivos que vigila dentro de la carpeta de la app, pero no
  un paquete instalado como `segmentation` — así que después de editar código ahí, la
  app seguía corriendo con la versión vieja en memoria hasta que reinicié el proceso
  entero. Aprendizaje operativo más que de código: *no todo lo que cambia en disco se
  refleja solo porque el servidor sigue corriendo*.

## 9. Empaquetado y despliegue

El `Dockerfile` usa build multi-etapa: una etapa instala dependencias y el paquete
propio dentro de un entorno virtual; la segunda copia solo ese entorno ya armado a una
imagen base liviana (`python:3.12-slim`), sin las herramientas de compilación que ya
no hacen falta en producción. Antes de copiar el entorno a la imagen final, lo
"adelgazo": quito `pip`/`setuptools` (ya no se vuelve a instalar nada dentro del
contenedor), las carpetas de tests de cada librería, y los símbolos de depuración de
los binarios compilados (`strip`). Nada de esto cambia cómo corre la app — solo reduce
cuántos MB hay que descargar para desplegarla.

El contenedor **sí** trae horneados los datos ya anonimizados (es una decisión
deliberada: así puedo desplegarlo en un servicio sin soporte de volúmenes persistentes,
como el plan gratuito de Render), pero solo copia los archivos exactos que el código
necesita, no carpetas completas — así evito llevar accidentalmente algo que no debería
estar ahí.

Para desarrollo local, `docker-compose.yml` monta `data/` como volumen de solo lectura,
para poder probar con una copia de datos más reciente sin reconstruir la imagen cada
vez. La imagen final la subo a Docker Hub y desde ahí se despliega en Render como
"Existing Image" — sin que Render tenga que reconstruir nada, solo hacer `pull` y
correr.

## 10. Cómo correrlo

```powershell
# una sola vez, en el env conda, parado en la raíz del proyecto:
python -m pip install -e .

# cada vez que quieras levantar la app:
python -m streamlit run app/app.py
```

Antes de la primera corrida, copia `.env.example` a `app/.env` y completa las claves
de `gemini_api_key` / `groq_key` (usadas por la pestaña Buyer Persona; la app funciona
igual sin ellas, solo sin el texto generado por IA).

Si necesitas regenerar los datos intermedios de facturación:

```powershell
python scripts\convertir_facturacion.py
```

Y para la imagen de Docker:

```bash
docker build -t analytic-dashboard-marcas:latest .
docker-compose up
```

## 11. Stack técnico

| Capa | Herramienta | Por qué |
|---|---|---|
| Interfaz | Streamlit | Prototipo a producto rápido, sin escribir HTML/JS a mano |
| Gráficos | Plotly Express | Interactivo, tema compartido, funciona bien dentro de Streamlit |
| Datos | pandas + polars | pandas para la lógica de negocio; polars para leer el archivo crudo más pesado sin que se dispare el consumo de memoria |
| Empaquetado | `pyproject.toml` + `pip install -e .` | Lógica compartida real, no copy-paste entre notebook y app |
| IA generativa | Gemini (primario) + Groq (respaldo) | Dos proveedores para no depender de la disponibilidad de uno solo |
| Contenedores | Docker multi-stage | Imagen final liviana, pensada para hosting con poca RAM |
| Privacidad | hash SHA-1 determinista + mapeos de anonimización | Útil para análisis, inofensivo si se filtra |

## 12. Qué me falta / qué haría distinto

- Migrar `use_container_width` (que Streamlit va a deprecar) a `width=`.
- Agregar un botón de descarga del análisis (Excel/PDF) directo desde la interfaz.
- El archivo `data/raw/listado/listado_clientes_2026_adic.xlsx` quedó protegido con
  contraseña y no pude procesarlo — sigue intacto, a la espera de esa contraseña o de
  un reexport sin cifrar.
- Si volviera a empezar, escribiría las pruebas de los casos límite (como el de la
  serie vacía en Plotly) *antes* de encontrarlos en producción, no después.
