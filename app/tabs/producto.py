"""Tab: Preferencia de producto - MODELO y variables del vehiculo.

MARCA, COMBUSTIBLE, HIBRIDACION, CATEGORIA, SEGMENTO y SUBSEGMENTO se obtienen
buscando el MODELO del cliente en data/external/CatSegmentosWork.parquet. Sin coincidencia -> 'SIN INFO'.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from data import ORDEN_GENERACION, PALETA_TEMA, SEGMENTOS_ENTRADA, gen_label, tabla_segura

PALETA = PALETA_TEMA


def render(df, compras):
    st.subheader("Preferencia de producto - MODELO y vehiculo")
    st.caption(
        f"Cobertura de las variables del vehiculo sobre esta seleccion: "
        f"{compras['EN_CATALOGO'].mean() * 100:.1f}% - el resto queda como SIN INFO. "
        f"Cada fila es una compra (un cliente puede tener varias)."
    )

    col_izq, col_der = st.columns(2)
    with col_izq:
        top_mod = compras["MODELO"].value_counts().head(10).sort_values()
        fig = px.bar(x=top_mod.values, y=top_mod.index, orientation="h",
                     title="Top 10 modelos", labels={"x": "compras", "y": ""},
                     color_discrete_sequence=PALETA)
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)
    with col_der:
        marca = compras["MARCA"].value_counts(normalize=True).mul(100).round(1)
        fig2 = px.bar(marca, title="Distribucion por marca", labels={"value": "%", "index": ""},
                      color_discrete_sequence=PALETA)
        fig2.update_layout(showlegend=False, height=380, yaxis_ticksuffix="%")
        st.plotly_chart(fig2, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        vc = compras["COMBUSTIBLE"].value_counts(normalize=True).mul(100).round(1)
        fig3 = px.bar(vc, title="Combustible", labels={"value": "%", "index": ""},
                      color_discrete_sequence=PALETA)
        fig3.update_layout(showlegend=False, height=320, yaxis_ticksuffix="%")
        st.plotly_chart(fig3, use_container_width=True)
    with col2:
        vc = compras["HIBRIDACION"].value_counts(normalize=True).mul(100).round(1)
        fig4 = px.bar(vc, title="Hibridacion", labels={"value": "%", "index": ""},
                      color_discrete_sequence=PALETA)
        fig4.update_layout(showlegend=False, height=320, yaxis_ticksuffix="%")
        st.plotly_chart(fig4, use_container_width=True)
    with col3:
        vc = compras["CATEGORIA"].value_counts(normalize=True).mul(100).round(1)
        fig5 = px.bar(vc, title="Categoria", labels={"value": "%", "index": ""},
                      color_discrete_sequence=PALETA)
        fig5.update_layout(showlegend=False, height=320, yaxis_ticksuffix="%")
        st.plotly_chart(fig5, use_container_width=True)

    c6, c7 = st.columns(2)
    with c6:
        seg_chart = compras["SEGMENTO"].value_counts().head(12).sort_values()
        fig6 = px.bar(x=seg_chart.values, y=seg_chart.index, orientation="h",
                      title="Segmento del vehiculo", labels={"x": "compras", "y": ""},
                      color_discrete_sequence=PALETA)
        fig6.update_layout(height=420)
        st.plotly_chart(fig6, use_container_width=True)
    with c7:
        sub_chart = compras["SUBSEGMENTO"].value_counts().head(12).sort_values()
        fig6b = px.bar(x=sub_chart.values, y=sub_chart.index, orientation="h",
                       title="Subsegmento del vehiculo", labels={"x": "compras", "y": ""},
                       color_discrete_sequence=PALETA)
        fig6b.update_layout(height=420)
        st.plotly_chart(fig6b, use_container_width=True)

    tab_gen = pd.crosstab(compras["CATEGORIA"], compras["GENERACION"], normalize="columns")
    tab_gen = (tab_gen[[c for c in ORDEN_GENERACION if c in tab_gen.columns]] * 100).round(0)
    tab_gen.columns = [gen_label(c) for c in tab_gen.columns]
    fig7 = px.imshow(tab_gen, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                     title="Mix de categoria de vehiculo por generacion (% por columna)")
    fig7.update_traces(texttemplate="%{z:.0f}%")
    fig7.update_layout(height=360, coloraxis_colorbar_ticksuffix="%")
    st.plotly_chart(fig7, use_container_width=True)

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
    st.plotly_chart(fig_mp, use_container_width=True)

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
    if len(upsell):
        st.dataframe(
            tabla_segura(upsell.sort_values("SALARIO", ascending=False),
                         ["CEDULA", "EDAD", "PROFESION", "SALARIO", "PEOR_CALIFICACION",
                          "MODELO", "PROVINCIA"]),
            use_container_width=True, height=280,
        )

    st.divider()
    st.markdown("### Capacidad adquisitiva y adopcion de tecnologia")
    st.caption("Pregunta de negocio: perfil e ingreso del comprador de vehiculo hibrido vs. combustion.")
    comb_dedup = compras.drop_duplicates(["IDENTIFICACION_CLIENTE", "COMBUSTIBLE"])
    cap_comb = compras.groupby("COMBUSTIBLE").agg(
        n=("COMBUSTIBLE", "size"),
        pct_superior=("INSTRUCCION", lambda s: (s == "SUPERIOR").mean() * 100),
        pct_casado=("ESTADO_CIVIL", lambda s: (s == "CASADO").mean() * 100),
        pct_4x4=("TRACCION", lambda s: (s == "4x4").mean() * 100),
    )
    cap_comb["salario_promedio"] = comb_dedup.groupby("COMBUSTIBLE")["SALARIO"].mean()
    cap_comb["edad_promedio"] = comb_dedup.groupby("COMBUSTIBLE")["EDAD"].mean()
    cap_comb = cap_comb.round(1).sort_values("salario_promedio", ascending=False)
    col4, col5 = st.columns([1, 1])
    with col4:
        st.markdown("**Por combustible**")
        st.dataframe(cap_comb, use_container_width=True)
        fig8 = px.bar(cap_comb["salario_promedio"].dropna(), title="Salario promedio por combustible",
                      labels={"value": "USD/mes", "COMBUSTIBLE": ""}, color_discrete_sequence=PALETA)
        fig8.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig8, use_container_width=True)
    with col5:
        st.markdown("**Por segmento**")
        seg_dedup = compras.drop_duplicates(["IDENTIFICACION_CLIENTE", "SEGMENTO"])
        cap_segmento = compras.groupby("SEGMENTO").agg(n=("SEGMENTO", "size"))
        cap_segmento["salario_promedio"] = seg_dedup.groupby("SEGMENTO")["SALARIO"].mean()
        cap_segmento["edad_promedio"] = seg_dedup.groupby("SEGMENTO")["EDAD"].mean()
        cap_segmento = cap_segmento.round(1).sort_values("n", ascending=False)
        st.dataframe(cap_segmento, use_container_width=True)

    st.markdown("**Distribucion de salarios por modelo (top 12)**")
    modelos_top = compras["MODELO"].value_counts().head(12).index
    box_df = compras[compras["MODELO"].isin(modelos_top) & (compras["SALARIO"] < 12000)]
    box_df = box_df.drop_duplicates(["IDENTIFICACION_CLIENTE", "MODELO"])
    fig9 = px.box(box_df, x="SALARIO", y="MODELO", color="CATEGORIA", points="outliers",
                  labels={"SALARIO": "Salario USD/mes", "MODELO": ""}, color_discrete_sequence=PALETA)
    fig9.update_layout(height=480)
    st.plotly_chart(fig9, use_container_width=True)

    st.divider()
    st.markdown("### Actividad economica y vehiculo")
    prof_top = compras["PROFESION"].value_counts().head(12).index
    heat = (pd.crosstab(compras.loc[compras["PROFESION"].isin(prof_top), "PROFESION"],
                        compras.loc[compras["PROFESION"].isin(prof_top), "CATEGORIA"], normalize="index") * 100).round(0)
    fig10 = px.imshow(heat, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                      title="Categoria de vehiculo por profesion (% por fila)")
    fig10.update_traces(texttemplate="%{z:.0f}%")
    fig10.update_layout(height=440, coloraxis_colorbar_ticksuffix="%")
    st.plotly_chart(fig10, use_container_width=True)

    mix_cat_comb = (pd.crosstab(compras["CATEGORIA"], compras["COMBUSTIBLE"], normalize="index") * 100).round(0)
    fig11 = px.imshow(mix_cat_comb, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                      title="Mix de combustible por categoria de vehiculo (% por fila)")
    fig11.update_traces(texttemplate="%{z:.0f}%")
    fig11.update_layout(height=340, coloraxis_colorbar_ticksuffix="%")
    st.plotly_chart(fig11, use_container_width=True)

    st.caption(
        "El negocio de personas es esencialmente SUV a gasolina o hibrido ligero (MHEV) para "
        "profesionales de clase media; las pick-up (categoria PICK UPS, diesel y 4x4) son un nicho productivo."
    )
