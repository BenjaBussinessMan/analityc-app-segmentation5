"""Motor de generación de texto para la ficha de "Buyer Persona".

Dos niveles:
- `texto_estatico(...)`: párrafo por plantilla, sin IA ni costo, siempre disponible.
- `generar_descripcion_ia(...)`: insights ampliados. Primero intenta Gemini, luego cae
  a Groq si TODOS los modelos de Gemini están sin cuota/sobrecargados.

Contexto de mercado: se prioriza el documento interno curado por el usuario
(`resources/contexto_mercado.md`, vía `extraer_contexto_local`) sobre la búsqueda web —
es más preciso (sin riesgo de alucinación), más rápido/barato, y funciona igual con
Gemini que con Groq (es solo texto inyectado en el prompt, no una herramienta de
grounding). Si el modelo seleccionado no tiene sección en ese documento, Gemini cae a
grounding con Google Search; Groq simplemente omite la sección (no tiene búsqueda
nativa).

En todos los casos se le pasan SOLO los datos ya calculados por la ficha viva
(app/tabs/buyer_persona.py) — el modelo no inventa cifras internas, solo las
redacta, agrega contexto de mercado (cuando hay disponible) y, al final, infiere un
posible "punto de dolor" de compra que no se puede responder con una fórmula.
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from groq import Groq
from groq import APIStatusError as GroqAPIStatusError

# Carga app/.env (GEMINI_API_KEY, groq_key) al entorno del proceso — streamlit
# no lo hace solo; sin esto, los clientes nunca ven las keys aunque el archivo exista.
load_dotenv(Path(__file__).resolve().parent / ".env")

RUTA_CONTEXTO_MERCADO = Path(__file__).resolve().parent / "resources" / "contexto_mercado.md"

# Cada modelo de esta familia tiene su propia cuota diaria independiente en la API de
# Gemini (confirmado: gemini-3.8-flash agotada no afecta la cuota de gemini-3.6-flash).
# Si el primero devuelve 429 (sin cuota) o 503 (sobrecargado), se reintenta con el
# siguiente de la lista en vez de fallar — multiplica la capacidad diaria efectiva.
# gemini-2.x y anteriores NO se incluyen: están retirados para este proyecto (404
# "no longer available to new users" confirmado contra la API real, sin importar lo
# que muestre el panel de cuotas de AI Studio).
MODELOS_FALLBACK = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]
MODELO_IA = MODELOS_FALLBACK[0]  # se mantiene por compatibilidad/logging
TEMPERATURA = 0.4

# Respaldo final cuando TODOS los modelos de Gemini están sin cuota/sobrecargados.
# Groq no tiene grounding nativo (sin Google Search), por eso usan un prompt aparte
# sin la sección "Contexto de mercado" — pedirsela igual causaria que el modelo
# invente informacion de mercado sin poder buscarla de verdad.
MODELOS_GROQ_FALLBACK = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]

PROMPT_TEMPLATE = """\
Actúa como un especialista en marketing automotriz. A partir de estos datos reales de los \
compradores de un modelo de vehículo, escribe un reporte de 2 secciones (~220-280 palabras en \
total). Dentro de cada sección, organiza el texto en **párrafos separados por tema** (una línea \
en blanco entre párrafos) para que sea fácil de leer — no mezcles todo en un solo bloque.

## Perfil del comprador
- Párrafo 1 — Quién es: arranca la frase así, mencionando marca y modelo explícitamente ("El \
comprador típico del {marca} {modelo} es..."), con su situación demográfica y económica (edad, \
estado civil, educación, ocupación, ingreso, ubicación) y cómo paga.
- Párrafo 2 — Relación con postventa: adherencia al taller oficial, gasto, servicios más \
solicitados y frecuencia de visita.
- Párrafo 3 — Motivación inferida: una frase infiriendo su posible motivación o "punto de dolor" \
principal al comprar este vehículo (ej. estatus profesional, economía de combustible, transporte \
familiar, trabajo pesado), dejando explícito que es una inferencia razonable a partir del perfil \
y no un dato medido directamente.

No inventes cifras que no estén en los datos de abajo para esta sección. Si un dato no aparece, \
no lo menciones.

## Contexto de mercado
Usa búsqueda web para agregar un párrafo breve (párrafo aparte) con información pública real \
sobre el {marca} {modelo}: posicionamiento, segmento, principales competidores y percepción \
general en el mercado. Deja explícito que esta sección viene de información pública de mercado, \
no de la base de clientes de la empresa.

Datos del comprador típico de {modelo} ({marca}):
{datos}
"""

# Version sin la seccion "Contexto de mercado" para motores sin busqueda web (Groq).
PROMPT_TEMPLATE_SIN_GROUNDING = """\
Actúa como un especialista en marketing automotriz. A partir de estos datos reales de los \
compradores de un modelo de vehículo, redacta un reporte (~150-180 palabras) organizado en \
**párrafos separados por tema** (una línea en blanco entre párrafos, no un solo bloque):

- Párrafo 1 — Quién es: arranca la frase así, mencionando marca y modelo explícitamente ("El \
comprador típico del {marca} {modelo} es..."), con su situación demográfica y económica (edad, \
estado civil, educación, ocupación, ingreso, ubicación) y cómo paga.
- Párrafo 2 — Relación con postventa: adherencia al taller oficial, gasto, servicios más \
solicitados y frecuencia de visita.
- Párrafo 3 — Motivación inferida: una frase infiriendo su posible motivación o "punto de dolor" \
principal al comprar este vehículo (ej. estatus profesional, economía de combustible, transporte \
familiar, trabajo pesado), dejando explícito que es una inferencia razonable a partir del perfil \
y no un dato medido directamente.

No inventes cifras que no estén en los datos de abajo, y no agregues información externa sobre \
el mercado del vehículo (no tienes acceso a búsqueda web en este momento).

Datos del comprador típico de {modelo} ({marca}):
{datos}
"""

# Version con contexto de mercado inyectado desde el documento local curado (en vez de
# pedirle al modelo que busque en la web) — usable tanto por Gemini como por Groq,
# porque es solo texto dentro del prompt, no una herramienta de grounding.
PROMPT_TEMPLATE_CONTEXTO_LOCAL = """\
Actúa como un especialista en marketing automotriz. A partir de estos datos reales de los \
compradores de un modelo de vehículo, escribe un reporte de 2 secciones (~220-280 palabras en \
total). Dentro de cada sección, organiza el texto en **párrafos separados por tema** (una línea \
en blanco entre párrafos) para que sea fácil de leer — no mezcles todo en un solo bloque.

## Perfil del comprador
- Párrafo 1 — Quién es: arranca la frase así, mencionando marca y modelo explícitamente ("El \
comprador típico del {marca} {modelo} es..."), con su situación demográfica y económica (edad, \
estado civil, educación, ocupación, ingreso, ubicación) y cómo paga.
- Párrafo 2 — Relación con postventa: adherencia al taller oficial, gasto, servicios más \
solicitados y frecuencia de visita.
- Párrafo 3 — Motivación inferida: una frase infiriendo su posible motivación o "punto de dolor" \
principal al comprar este vehículo, dejando explícito que es una inferencia razonable a partir \
del perfil y no un dato medido directamente.

No inventes cifras que no estén en los datos de abajo para esta sección. Si un dato no aparece, \
no lo menciones.

## Contexto de mercado
Usa EXCLUSIVAMENTE el siguiente documento interno (no busques en la web, no agregues \
nada que no esté en él) para escribir un párrafo breve sobre el posicionamiento del {marca} \
{modelo}, sus competidores y el arquetipo de comprador que describe el mercado para este modelo. \
Deja explícito que esta sección viene de un análisis interno de mercado, no de la base de \
clientes de la empresa.

Documento interno de contexto de mercado:
\"\"\"
{contexto_local}
\"\"\"

Datos del comprador típico de {modelo} ({marca}):
{datos}
"""

NOTA_SIN_GROUNDING = (
    "\n\n_(Generado con un modelo de respaldo sin acceso a búsqueda web — no incluye "
    "contexto de mercado.)_"
)

NOTA_RESPALDO = "\n\n_(Generado con un modelo de respaldo — Gemini no disponible en este momento.)_"


def extraer_contexto_local(modelo: str, marca: str = "", ruta: Path = RUTA_CONTEXTO_MERCADO) -> str | None:
    """Busca en resources/contexto_mercado.md la sección que corresponde al modelo
    seleccionado y devuelve su texto (encabezado + Contexto de Mercado + Arquetipo +
    Drivers de Compra), o None si no hay sección para ese modelo en el documento.

    El documento mezcla encabezados Setext ("4\\. Marca Modelo A1" + línea de
    guiones) para modelos individuales con encabezados ATX ("### 3.1. Marca Modelo
    A1 Entry") para variantes dentro de una "gama" — se detectan ambos patrones.
    """
    if not ruta.exists():
        return None
    texto = ruta.read_text(encoding="utf-8")

    lineas = texto.split("\n")
    headings = []
    offset = 0
    for i, linea in enumerate(lineas):
        es_setext = (
            i + 1 < len(lineas)
            and re.match(r"^-{3,}\s*$", lineas[i + 1])
            and re.match(r"^\d+\\?\.\s+\S", linea)
        )
        es_atx_variante = re.match(r"^#{3,4}\s+\d+\.\d+\.\s+\S", linea)
        if es_setext or es_atx_variante:
            titulo = linea.lstrip("#").strip()
            titulo = re.sub(r"^\d+(\\?\.|\.\d+\\?\.)\s+", "", titulo)
            headings.append((offset, titulo))
        offset += len(linea) + 1

    def normaliza(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", s.upper())

    clave = normaliza(f"{marca} {modelo}")
    marca_norm = normaliza(marca)

    def token_en_clave(tok: str) -> bool:
        # Evita falsos positivos como "CX3" calzando dentro de "CX30": si el token
        # mezcla letras y dígitos (ej. "CX3"/"CX30"), se exige que no haya un dígito
        # extra pegado al lado que termina/empieza en dígito. Un token puramente
        # numérico (ej. "25" de un motor "2.5") NO lleva ese borde: en los códigos de
        # modelo reales suele quedar pegado a OTRO número sin relación (ej. "5P" de
        # "5 puertas" junto a "2.5" dan "255P") y el borde estricto lo rompería.
        tiene_letra = any(c.isalpha() for c in tok)
        prefijo = r"(?<!\d)" if tiene_letra and tok[0].isdigit() else ""
        sufijo = r"(?!\d)" if tiene_letra and tok[-1].isdigit() else ""
        return re.search(f"{prefijo}{re.escape(tok)}{sufijo}", clave) is not None

    def alternativa_en_clave(tokens: list) -> bool:
        # Caso especial: la alternativa completa es un solo token numérico corto (ej.
        # "2"/"3" de "Marca 2"/"Marca 3" — el modelo ES un número). Un "2"/"3" suelto
        # calzaría dentro de cualquier "4X2"/"4X4" de drivetrain, así que para este
        # caso puntual se exige que venga pegado al nombre de la marca ("MARCA2"),
        # como aparece en el dato real.
        if len(tokens) == 1 and tokens[0].isdigit() and len(tokens[0]) <= 2:
            tok = tokens[0]
            return re.search(rf"{re.escape(marca_norm)}{re.escape(tok)}(?!\d)", clave) is not None
        return all(token_en_clave(tok) for tok in tokens)

    mejor = None
    for pos, titulo in headings:
        # Quita notas entre paréntesis (ej. "(Sedán / Hatchback)", "(AWD)") que no son
        # parte del código de modelo, y separa nombres alternativos unidos por "/"
        # (ej. "CX-5 (Estándar) / CX-5 Core" son dos formas de nombrar la misma fila) —
        # basta con que UNA alternativa calce completa en la clave del modelo.
        titulo_sin_parentesis = re.sub(r"\([^)]*\)", "", titulo).replace("Marca", "")
        alternativas = [
            [normaliza(tok) for tok in alt.split() if normaliza(tok)]
            for alt in titulo_sin_parentesis.split("/")
        ]
        alternativas = [toks for toks in alternativas if toks]
        for tokens in alternativas:
            if alternativa_en_clave(tokens):
                especificidad = sum(len(t) for t in tokens)
                if mejor is None or especificidad > mejor[1]:
                    mejor = (pos, especificidad)

    if mejor is None:
        return None

    pos_inicio = mejor[0]
    pos_fin = len(texto)
    for pos, _ in headings:
        if pos > pos_inicio:
            pos_fin = pos
            break
    return texto[pos_inicio:pos_fin].strip()


def construir_resumen_datos(ficha: dict) -> str:
    """Arma el bloque de texto con los datos ya calculados de la ficha viva, sin inventar nada:
    omite valores vacíos/"s/d" para que el modelo no comente sobre datos faltantes."""
    lineas = [f"- {etiqueta}: {valor}" for etiqueta, valor in ficha.items()
              if valor not in (None, "", "s/d")]
    return "\n".join(lineas)


def _generar_con_gemini(ficha: dict, modelo: str, marca: str) -> str:
    """Recorre MODELOS_FALLBACK (Gemini) en orden: si un modelo devuelve 429 (sin
    cuota) o 503 (sobrecargado) prueba el siguiente; cualquier otro error (400,
    401/403, etc.) se relanza de inmediato porque probar otro modelo no lo arregla.

    Si el modelo de vehículo seleccionado tiene sección en el documento interno
    (resources/contexto_mercado.md), se usa ese contexto en vez de grounding con
    Google Search: es más preciso y permite desactivar el "thinking" (no hace falta
    que el modelo decida cuándo buscar). Si no hay sección para ese modelo, se cae a
    grounding con búsqueda web real, que sí necesita el thinking por defecto."""
    cliente = genai.Client()
    datos = construir_resumen_datos(ficha)
    contexto_local = extraer_contexto_local(modelo, marca)

    if contexto_local:
        prompt = PROMPT_TEMPLATE_CONTEXTO_LOCAL.format(
            modelo=modelo, marca=marca, datos=datos, contexto_local=contexto_local,
        )
        config = types.GenerateContentConfig(
            temperature=TEMPERATURA,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
    else:
        prompt = PROMPT_TEMPLATE.format(modelo=modelo, marca=marca, datos=datos)
        config = types.GenerateContentConfig(
            temperature=TEMPERATURA,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )

    ultimo_error = None
    for nombre_modelo in MODELOS_FALLBACK:
        try:
            respuesta = cliente.models.generate_content(
                model=nombre_modelo, contents=prompt, config=config,
            )
            return respuesta.text
        except errors.APIError as e:
            if e.code in (429, 503):
                ultimo_error = e
                continue
            raise
    raise ultimo_error


def _generar_con_groq(ficha: dict, modelo: str, marca: str) -> str:
    """Respaldo vía Groq (modelos open-source), usado cuando TODA la familia Gemini
    está sin cuota/sobrecargada. Recorre MODELOS_GROQ_FALLBACK con el mismo criterio
    de reintento que Gemini.

    Groq no tiene grounding nativo (sin Google Search), pero sí puede recibir el
    documento interno de contexto de mercado como texto del prompt igual que Gemini
    — si el modelo seleccionado tiene sección ahí, el reporte incluye contexto de
    mercado también en este camino de respaldo; si no, se omite esa sección.

    Los modelos `gpt-oss` son "razonadores": a veces gastan todo el presupuesto de
    tokens pensando y no les queda espacio para la respuesta final (visto en pruebas:
    content vacío con finish_reason="stop", nada que ver con un error HTTP). Por eso
    se sube max_completion_tokens con margen y, si aun así el contenido viene vacío,
    se prueba el siguiente modelo en vez de devolver un resultado vacío."""
    groq_key = os.environ.get("GROQ_API_KEY") or os.environ.get("groq_key")
    cliente = Groq(api_key=groq_key)
    datos = construir_resumen_datos(ficha)
    contexto_local = extraer_contexto_local(modelo, marca)

    if contexto_local:
        prompt = PROMPT_TEMPLATE_CONTEXTO_LOCAL.format(
            modelo=modelo, marca=marca, datos=datos, contexto_local=contexto_local,
        )
    else:
        prompt = PROMPT_TEMPLATE_SIN_GROUNDING.format(modelo=modelo, marca=marca, datos=datos)

    ultimo_error = None
    for nombre_modelo in MODELOS_GROQ_FALLBACK:
        try:
            respuesta = cliente.chat.completions.create(
                model=nombre_modelo,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURA,
                max_completion_tokens=6000,
            )
            choice = respuesta.choices[0]
            contenido = (choice.message.content or "").strip()
            if not contenido:
                ultimo_error = RuntimeError(f"{nombre_modelo} devolvió contenido vacío")
                continue
            if choice.finish_reason == "length":
                # Se cortó a mitad de frase (razonamiento + respuesta superó el
                # presupuesto de tokens) — no sirve un resultado incompleto.
                ultimo_error = RuntimeError(f"{nombre_modelo} devolvió contenido truncado")
                continue
            nota = NOTA_SIN_GROUNDING if not contexto_local else NOTA_RESPALDO
            return contenido + nota
        except GroqAPIStatusError as e:
            if e.status_code in (429, 503):
                ultimo_error = e
                continue
            raise
    raise ultimo_error


def generar_descripcion_ia(ficha: dict, modelo: str, marca: str) -> str:
    """Genera el reporte ampliado (perfil + contexto de mercado si hay grounding
    disponible). Intenta primero toda la familia Gemini (con búsqueda web real); si
    TODAS las variantes de Gemini están sin cuota/sobrecargadas, cae a Groq (sin
    contexto de mercado, pero sigue redactando el perfil del comprador)."""
    try:
        return _generar_con_gemini(ficha, modelo, marca)
    except errors.APIError:
        return _generar_con_groq(ficha, modelo, marca)


def texto_estatico(datos: dict, modelo: str, marca: str) -> str:
    """Párrafo por plantilla (sin IA, sin costo, siempre disponible) a partir de los
    mismos valores crudos ya calculados por la ficha viva. Omite cláusulas cuyo dato
    sea "-"/None (selección sin ese dato)."""
    partes = [f"El comprador típico del **{marca} {modelo}** es"]

    sexo_top, sexo_pct = datos.get("sexo", (None, None))
    if sexo_top:
        partes[-1] += f" {sexo_top.lower()} ({sexo_pct:.0f}%),"

    edad = datos.get("edad_mediana")
    if edad is not None:
        partes[-1] += f" de {edad:.0f} años,"

    civil_top, civil_pct = datos.get("estado_civil", (None, None))
    if civil_top:
        partes[-1] += f" {civil_top.lower()},"

    inst_top, inst_pct = datos.get("instruccion", (None, None))
    salario = datos.get("salario_mediano")
    frase_2 = []
    if inst_top:
        frase_2.append(f"con educación {inst_top.lower()} ({inst_pct:.0f}%)")
    if salario is not None:
        frase_2.append(f"e ingreso mediano de ${salario:,.0f}/mes")
    if frase_2:
        partes.append(" ".join(frase_2) + ".")

    empleo = datos.get("ocupacion")
    prov_top, prov_pct = datos.get("provincia", (None, None))
    pago_top, pago_pct = datos.get("forma_pago", (None, None))
    frase_3 = []
    if empleo:
        frase_3.append(f"Trabaja principalmente como {empleo.lower()}")
    if prov_top:
        frase_3.append(f"reside sobre todo en {prov_top} ({prov_pct:.0f}%)")
    if pago_top:
        frase_3.append(f"y suele financiar la compra {pago_top.lower()} ({pago_pct:.0f}%)")
    if frase_3:
        partes.append(", ".join(frase_3) + ".")

    parrafo_perfil = " ".join(partes)

    adherencia = datos.get("pct_adherencia")
    if adherencia is None:
        return parrafo_perfil

    fidelidad = "Tiene alta fidelidad" if adherencia >= 50 else "Tiene baja fidelidad"
    parrafo_postventa = f"{fidelidad} al taller oficial ({adherencia:.0f}% de adherencia a postventa)."
    return f"{parrafo_perfil}\n\n{parrafo_postventa}"
