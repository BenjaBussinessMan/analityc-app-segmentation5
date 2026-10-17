"""Tab: Buyer Persona - vista resumen de perfiles de negocio + ficha viva por modelo.

Incluye los componentes iniciales que ya existen en Segmentacion (tabla + bar chart
de "Perfiles de negocio (reglas)") mas una ficha viva por modelo/categoria (radar,
forma de pago, adherencia a postventa) que responde las preguntas de negocio de
Inputs/Preguntas-Negocio.md (seccion Buyer Persona).
"""
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import PALETA_TEMA, SEGMENTOS_ENTRADA, cargar_postventa
from ia_buyer_persona import generar_descripcion_ia, texto_estatico

PALETA = PALETA_TEMA
EJES_RADAR = ["Edad", "Salario", "Apalancamiento", "% Instrucción superior"]


def _bar_horizontal_pct(vc, height, key):
    """Barra horizontal de % a partir de un value_counts(). Con selecciones muy
    chicas (1-2 compradores) la columna puede venir vacia/toda NaN para esa
    seleccion -> value_counts() da una Serie vacia, y px.bar(x=[], y=[]) revienta
    con 'Cannot accept list of column references or list of columns for both x
    and y' (dos listas vacias). Se evita el grafico en ese caso."""
    if vc.empty:
        st.caption("Sin datos para esta selección.")
        return
    fig = px.bar(x=vc.values, y=vc.index.astype(str), orientation="h",
                labels={"x": "%", "y": ""}, color_discrete_sequence=PALETA)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), xaxis_ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True, key=key)


def _md_seguro(texto):
    """Renderiza un texto (estatico o de IA) como parrafos HTML justificados.

    st.markdown interpreta lo que queda entre dos signos "$" como LaTeX (ej.
    "$1,000 ... $2,437" se renderiza como una formula, con los simbolos de dolar
    desapareciendo y el texto en verde) — se escapan primero para evitarlo.

    Se parte el texto en parrafos por linea en blanco (cada tema/seccion del prompt
    ya pide esa separacion) y cada uno se envuelve en <p style="text-align: justify">
    para que se lea mejor que alineado a la izquierda. Como el texto pasa a vivir
    dentro de HTML crudo (unsafe_allow_html), el markdown ya no se interpreta solo —
    se convierten a mano los dos unicos estilos que usan estas funciones: "**negrita**"
    y encabezados "## Titulo"."""
    texto = texto.replace("$", "\\$")
    html_parrafos = []
    for parrafo in texto.split("\n\n"):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if parrafo.startswith("## "):
            html_parrafos.append(f"<p style='margin:0.6em 0 0.2em 0;'><strong>{parrafo[3:]}</strong></p>")
            continue
        parrafo = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", parrafo)
        html_parrafos.append(f"<p style='text-align: justify; margin-bottom: 0.8em;'>{parrafo}</p>")
    st.markdown("\n".join(html_parrafos), unsafe_allow_html=True)


@st.cache_data(show_spinner="Generando insights con IA...", persist="disk")
def _generar_ia_cacheado(marca, modelo, anio, ficha_items):
    """Cachea en disco por (marca, modelo, año, ficha) para no volver a llamar a la
    API si alguien ya consultó exactamente esta combinación antes — sobrevive incluso
    a un reinicio de la app, no solo a la sesión activa."""
    return generar_descripcion_ia(dict(ficha_items), modelo, marca)


def render(df, compras):
    st.subheader("Buyer Persona")

    st.markdown("### Perfiles de negocio (reglas)")
    st.caption("Pregunta de negocio: los 4-5 buyer personas predominantes segun edad, estado civil, ocupacion e ingresos.")
    _moda = lambda s: s.mode().iat[0] if not s.mode().empty else "-"
    resumen_perfil_demo = df.groupby("PERFIL").agg(
        n=("PERFIL", "size"), edad_promedio=("EDAD", "mean"), salario_promedio=("SALARIO", "mean"),
        deuda_usd_prom=("DEUDA_USD_APROX", "mean"), pct_riesgo_alto=("NIVEL_RIESGO", lambda s: (s == "Alto").mean() * 100),
        estado_civil_frecuente=("ESTADO_CIVIL", _moda),
        profesion_frecuente=("PROFESION", _moda),
    )
    resumen_perfil_veh = compras.groupby("PERFIL").agg(
        categoria_frecuente=("CATEGORIA", _moda),
        modelo_frecuente=("MODELO", _moda),
    )
    resumen_perfil = (resumen_perfil_demo.join(resumen_perfil_veh, how="left")
                       .round(1).sort_values("n", ascending=False))

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(resumen_perfil, use_container_width=True)
    with col2:
        fig = px.bar(df["PERFIL"].value_counts(), title="Clientes por perfil de negocio",
                    labels={"value": "clientes", "index": ""}, color_discrete_sequence=PALETA)
        fig.update_layout(showlegend=False, height=380)
        st.plotly_chart(fig, use_container_width=True, key="buyer_persona_clientes_por_perfil")

    st.divider()
    st.markdown("### Qué modelo compra cada perfil de negocio")
    st.caption("Pregunta de negocio: adecuacion del portafolio - quien compra realmente cada modelo.")
    modelos_top = compras["MODELO"].value_counts().head(12).index
    mp = (pd.crosstab(compras.loc[compras["MODELO"].isin(modelos_top), "MODELO"],
                      compras.loc[compras["MODELO"].isin(modelos_top), "PERFIL"], normalize="columns") * 100).round(0)
    fig_mp = px.imshow(mp, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                       title="% de cada perfil que compra el modelo")
    fig_mp.update_traces(texttemplate="%{z:.0f}%")
    fig_mp.update_layout(height=460, coloraxis_colorbar_ticksuffix="%")
    st.plotly_chart(fig_mp, use_container_width=True, key="buyer_persona_modelo_por_perfil")

    st.divider()
    st.markdown("### Oportunidades de up-selling")
    st.caption("Pregunta de negocio: clientes de modelo de entrada con salario y credito para migrar a gama de mayor margen.")
    entrada = compras[compras["SEGMENTO"].isin(SEGMENTOS_ENTRADA)]
    entrada = entrada.drop_duplicates("IDENTIFICACION_CLIENTE")
    upsell = entrada[(entrada["SALARIO"] >= 1500) & (entrada["NIVEL_RIESGO"] == "Bajo")]
    u1, u2, u3 = st.columns(3)
    u1.metric("Clientes con modelo de entrada", f"{len(entrada):,}")
    u2.metric("Candidatos a up-selling", f"{len(upsell):,}",
              help="Salario >= $1.500 y riesgo de buro Bajo")
    u3.metric("Salario promedio del candidato", f"${upsell['SALARIO'].mean():,.0f}" if len(upsell) else "s/d")

    st.divider()
    st.markdown("### Buyer Persona — modelo de vehículo")
    st.caption("Pregunta de negocio: quién es el comprador arquetípico de cada modelo, cómo paga y si vuelve al taller.")

    c_marca, c_modelo, c_anio, c_n = st.columns([1, 1, 1, 0.6])
    marcas = compras["MARCA"].value_counts().index
    if marcas.empty:
        st.info("No hay compras de vehículo para los filtros seleccionados.")
        return
    marca_sel = c_marca.selectbox("Marca", marcas, key="buyer_persona_marca")

    compras_marca = compras[compras["MARCA"] == marca_sel]
    modelos = compras_marca["MODELO"].value_counts().index
    modelo_sel = c_modelo.selectbox("Modelo", modelos, key="buyer_persona_modelo")

    compras_modelo = compras_marca[compras_marca["MODELO"] == modelo_sel]
    anios = sorted(compras_modelo["FECHA"].dt.year.dropna().unique().astype(int), reverse=True)
    anio_sel = c_anio.selectbox("Año", ["Todos"] + anios, key="buyer_persona_anio")

    sub = compras_modelo if anio_sel == "Todos" else compras_modelo[compras_modelo["FECHA"].dt.year == anio_sel]
    n_compradores = sub["IDENTIFICACION_CLIENTE"].nunique()
    c_n.metric("N", f"{n_compradores:,}")
    if n_compradores < 15:
        st.warning(f"Solo {n_compradores} compradores — interpretar con cautela.")

    sub_dedup = sub.drop_duplicates("IDENTIFICACION_CLIENTE")

    def _moda_pct(serie):
        vc = serie.value_counts(normalize=True) * 100
        return (vc.idxmax(), vc.max()) if len(vc) else ("-", 0)

    st.markdown("#### :material/person: Perfil principal")
    with st.container(key="buyer_persona_perfil_principal"):
        st.markdown(
            """
            <style>
            .st-key-buyer_persona_perfil_principal [data-testid="stMetricValue"] { font-size: 1.4rem; }
            .st-key-buyer_persona_perfil_principal [data-testid="stMetricLabel"] { font-size: 0.8rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        p1, p2, p3 = st.columns(3)
        p1.metric("Edad mediana", f"{sub_dedup['EDAD'].median():.0f} años")
        sexo_top, sexo_pct = _moda_pct(sub_dedup["SEXO"])
        p2.metric("Sexo predominante", f"{sexo_top} {sexo_pct:.0f}%")
        civil_top, civil_pct = _moda_pct(sub_dedup["ESTADO_CIVIL"])
        p3.metric("Estado civil", f"{civil_top} {civil_pct:.0f}%")

        p4, p5, p6 = st.columns(3)
        p4.metric("Ingreso estimado (mediana)", f"${sub_dedup['SALARIO'].median():,.0f}")
        inst_top, inst_pct = _moda_pct(sub_dedup["INSTRUCCION"])
        p5.metric("Educación predominante", f"{inst_top} {inst_pct:.0f}%")
        empleo_top, _ = _moda_pct(sub_dedup["TIPO EMPLEO"])
        p6.metric("Ocupación", empleo_top)

    col_demo, col_econ = st.columns(2)
    with col_demo:
        st.markdown("#### :material/monitoring: Perfil demográfico")
        st.caption("Edad")
        edad_vc = sub_dedup["RANGO_EDAD"].value_counts(normalize=True).head(3).mul(100).round(0)
        _bar_horizontal_pct(edad_vc, 180, "buyer_persona_edad_bars")
        st.caption("Sexo")
        sexo_vc = sub_dedup["SEXO"].value_counts(normalize=True).mul(100).round(0)
        _bar_horizontal_pct(sexo_vc, 140, "buyer_persona_sexo_bars")
    with col_econ:
        st.markdown("#### :material/payments: Perfil económico")
        st.caption("Salario / ingreso")
        sal = sub_dedup["SALARIO"]
        e1, e2, e3 = st.columns(3)
        e1.metric("Promedio", f"${sal.mean():,.0f}" if sal.notna().any() else "s/d")
        e2.metric("P25", f"${sal.quantile(0.25):,.0f}" if sal.notna().any() else "s/d")
        e3.metric("P75", f"${sal.quantile(0.75):,.0f}" if sal.notna().any() else "s/d")
        deuda_usd = sub_dedup["DEUDA_USD_APROX"]
        ratio_endeudamiento = sub_dedup["APALANCAMIENTO_MESES"]
        e4, e5 = st.columns(2)
        e4.metric("Deuda promedio", f"${deuda_usd.mean():,.0f}" if deuda_usd.notna().any() else "s/d")
        e5.metric("Ratio de endeudamiento promedio",
                  f"{ratio_endeudamiento.mean():.1f}x salario" if ratio_endeudamiento.notna().any() else "s/d",
                  help="Deuda aproximada / salario mensual")
        st.caption("Deuda bancaria")
        tiene_deuda = sub_dedup["DEUDA_BASICOS"].fillna(0) > 0
        deuda_vc = tiene_deuda.map({True: "Con deuda", False: "Sin deuda"}).value_counts(normalize=True).mul(100).round(0)
        _bar_horizontal_pct(deuda_vc, 140, "buyer_persona_deuda_bars")

    col_ubic, col_prof = st.columns(2)
    with col_ubic:
        st.markdown("#### :material/location_on: Ubicación")
        st.caption("Provincia")
        prov_vc = sub_dedup["PROVINCIA"].value_counts(normalize=True).head(3).mul(100).round(0)
        _bar_horizontal_pct(prov_vc, 180, "buyer_persona_provincia_bars")
        st.caption("Cantón")
        canton_vc = sub_dedup["CANTON"].value_counts(normalize=True).head(2).mul(100).round(0)
        _bar_horizontal_pct(canton_vc, 140, "buyer_persona_canton_bars")
    with col_prof:
        st.markdown("#### :material/work: Perfil profesional")
        st.caption("Tipo de empleo")
        empleo_vc = sub_dedup["TIPO EMPLEO"].value_counts(normalize=True).head(3).mul(100).round(0)
        _bar_horizontal_pct(empleo_vc, 180, "buyer_persona_empleo_bars")
        st.caption("Principales profesiones")
        top_prof = sub_dedup["PROFESION"].value_counts().head(3).index
        st.write(" • ".join(top_prof) if len(top_prof) else "s/d")

    def _atributos(d):
        d = d.drop_duplicates("IDENTIFICACION_CLIENTE")
        return pd.Series({
            "Edad": d["EDAD"].mean(), "Salario": d["SALARIO"].mean(),
            "Apalancamiento": d["APALANCAMIENTO_MESES"].fillna(0).mean(),
            "% Instrucción superior": (d["INSTRUCCION"] == "SUPERIOR").mean() * 100,
        })

    col_radar, col_pago = st.columns(2)
    with col_radar:
        promedio_general = _atributos(compras)
        atributos_sel = _atributos(sub)
        normalizado = (atributos_sel / promedio_general * 100).round(0)
        fig_radar = go.Figure()
        fig_radar.add_scatterpolar(r=normalizado.values, theta=EJES_RADAR, fill="toself", name=str(modelo_sel))
        fig_radar.add_scatterpolar(r=[100, 100, 100, 100], theta=EJES_RADAR, name="Promedio general",
                                   line=dict(dash="dot", color="gray"))
        fig_radar.update_layout(title=f"Atributos del comprador — {modelo_sel} (índice vs. promedio general = 100)",
                                polar=dict(radialaxis=dict(visible=True)), height=420)
        st.plotly_chart(fig_radar, use_container_width=True, key="buyer_persona_radar")
    with col_pago:
        vc_pago = sub["TIPO_FORMA_PAGO_DESCRIPCION"].value_counts(normalize=True) * 100
        fig_pago = px.bar(vc_pago, title=f"Forma de pago — {modelo_sel}",
                          labels={"value": "% de compras", "index": ""}, color_discrete_sequence=PALETA)
        fig_pago.update_layout(showlegend=False, height=420, yaxis_ticksuffix="%")
        st.plotly_chart(fig_pago, use_container_width=True, key="buyer_persona_forma_pago")

    st.markdown("#### Adherencia a postventa")
    postventa = cargar_postventa()
    ids_sel = sub["IDENTIFICACION_CLIENTE"].unique()
    postventa_sel = postventa[postventa["IDENTIFICACION_CLIENTE"].isin(ids_sel)]

    p1, p2 = st.columns(2)
    pct_adherencia = postventa_sel["IDENTIFICACION_CLIENTE"].nunique() / max(n_compradores, 1) * 100
    ticket_promedio = postventa_sel.groupby("NUM_FACTURA")["TOTAL"].sum().mean() if len(postventa_sel) else float("nan")
    p1.metric("% con visita a postventa", f"{pct_adherencia:.0f}%")
    p2.metric("Ticket promedio por factura", f"${ticket_promedio:,.0f}" if pd.notna(ticket_promedio) else "s/d")

    # Datos adicionales de postventa para el texto estatico/IA (gasto total por
    # comprador adherente, servicios mas solicitados, frecuencia de visitas).
    if len(postventa_sel):
        gasto_promedio_comprador = postventa_sel.groupby("IDENTIFICACION_CLIENTE")["TOTAL"].sum().mean()
        frecuencia_visitas = postventa_sel.groupby("IDENTIFICACION_CLIENTE")["NUM_FACTURA"].nunique().mean()
        servicios_top = postventa_sel["SUBLINEA_NEGOCIO_DESCRIPCION"].value_counts().head(3).index.tolist()
    else:
        gasto_promedio_comprador = float("nan")
        frecuencia_visitas = float("nan")
        servicios_top = []

    if len(postventa_sel):
        col_linea, col_sublinea = st.columns(2)
        with col_linea:
            vc_linea = postventa_sel["LINEA_NEGOCIO_DESCRIPCION"].value_counts()
            fig_linea = px.bar(vc_linea, title="Mix por línea de negocio",
                               labels={"value": "facturas", "index": ""}, color_discrete_sequence=PALETA)
            fig_linea.update_layout(showlegend=False, height=340)
            st.plotly_chart(fig_linea, use_container_width=True, key="buyer_persona_postventa_linea")
        with col_sublinea:
            vc_sublinea = postventa_sel["SUBLINEA_NEGOCIO_DESCRIPCION"].value_counts().head(8).sort_values()
            fig_sublinea = px.bar(x=vc_sublinea.values, y=vc_sublinea.index, orientation="h",
                                  title="Top 8 sublínea de negocio (accesorios, prepago, seguros...)",
                                  labels={"x": "facturas", "y": ""}, color_discrete_sequence=PALETA)
            fig_sublinea.update_layout(height=340)
            st.plotly_chart(fig_sublinea, use_container_width=True, key="buyer_persona_postventa_sublinea")
    else:
        st.info("Ningún comprador de esta selección tiene visitas registradas en postventa.")

    st.divider()
    st.markdown("#### :material/forum: Buyer persona sintetizado")

    pago_top_ia, pago_pct_ia = (vc_pago.idxmax(), vc_pago.max()) if len(vc_pago) else ("-", 0)
    prov_top_ia, prov_pct_ia = (prov_vc.index[0], prov_vc.iloc[0]) if len(prov_vc) else ("-", 0)
    edad_mediana = sub_dedup["EDAD"].median() if sub_dedup["EDAD"].notna().any() else None
    salario_mediano = sal.median() if sal.notna().any() else None

    # Valores crudos para el texto estatico (sin formatear a string todavia).
    datos_estatico = {
        "sexo": (sexo_top, sexo_pct) if sexo_top != "-" else (None, None),
        "edad_mediana": edad_mediana,
        "estado_civil": (civil_top, civil_pct) if civil_top != "-" else (None, None),
        "instruccion": (inst_top, inst_pct) if inst_top != "-" else (None, None),
        "salario_mediano": salario_mediano,
        "ocupacion": empleo_top if empleo_top != "-" else None,
        "provincia": (prov_top_ia, prov_pct_ia) if prov_top_ia != "-" else (None, None),
        "forma_pago": (pago_top_ia, pago_pct_ia) if pago_top_ia != "-" else (None, None),
        "pct_adherencia": pct_adherencia,
    }
    _md_seguro(texto_estatico(datos_estatico, modelo_sel, marca_sel))

    # Ficha con los mismos datos (mas los de postventa) en formato texto para el prompt de IA.
    ficha_ia = {
        "Compradores (N)": int(n_compradores),
        "Edad mediana": f"{edad_mediana:.0f} años" if edad_mediana is not None else "s/d",
        "Sexo predominante": f"{sexo_top} ({sexo_pct:.0f}%)" if sexo_top != "-" else "s/d",
        "Estado civil predominante": f"{civil_top} ({civil_pct:.0f}%)" if civil_top != "-" else "s/d",
        "Educacion predominante": f"{inst_top} ({inst_pct:.0f}%)" if inst_top != "-" else "s/d",
        "Ocupacion (tipo de empleo predominante)": empleo_top if empleo_top != "-" else "s/d",
        "Salario mensual mediano": f"${salario_mediano:,.0f}" if salario_mediano is not None else "s/d",
        "Forma de pago mas comun": f"{pago_top_ia} ({pago_pct_ia:.0f}%)" if pago_top_ia != "-" else "s/d",
        "Provincia predominante": f"{prov_top_ia} ({prov_pct_ia:.0f}%)" if prov_top_ia != "-" else "s/d",
        "Adherencia a postventa (taller oficial)": f"{pct_adherencia:.0f}%",
        "Gasto promedio en postventa por comprador": (
            f"${gasto_promedio_comprador:,.0f}" if pd.notna(gasto_promedio_comprador) else "s/d"
        ),
        "Servicios de postventa mas solicitados": ", ".join(servicios_top) if servicios_top else "s/d",
        "Frecuencia de visitas a postventa (promedio por comprador)": (
            f"{frecuencia_visitas:.1f} visitas" if pd.notna(frecuencia_visitas) else "s/d"
        ),
    }

    col_btn, col_warn = st.columns([1, 0.15])
    with col_btn:
        generar = st.button("Generar Insights (IA)", key="buyer_persona_generar_ia")
    with col_warn:
        with st.popover("", icon=":material/warning:"):
            st.caption("Esto es un resumen generado con IA, puede contener errores de interpretación.")

    if generar:
        try:
            texto_ia = _generar_ia_cacheado(marca_sel, modelo_sel, str(anio_sel), tuple(ficha_ia.items()))
            _md_seguro(texto_ia)
        except Exception as e:
            st.error("No se pudo generar los insights con IA. ¿Está configurada la API key de Gemini?")
            with st.expander("Detalle del error"):
                st.code(str(e))
