"""Tab: Perfil Conductual - estado civil, cargos, empresas, capacidad economica y producto.

Reutiliza graficos ya existentes en el notebook de exploracion (pie de estado civil,
top cargos, treemap de empresas) y en el Dashboard (bloque de capacidad economica de
economico.py, y las secciones "Preferencia de producto" y "Capacidad adquisitiva y
adopcion de tecnologia" de producto.py, que se mantienen igual en esa tab).
"""
import pandas as pd
import plotly.express as px
import streamlit as st
from plotly.subplots import make_subplots

from data import ORDEN_RIESGO, PALETA_TEMA

PALETA = PALETA_TEMA


def render(df, compras):
    st.subheader("Perfil Conductual")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Salario mediano", f"${df['SALARIO'].median():,.0f}")
    k2.metric("Salario promedio", f"${df['SALARIO'].mean():,.0f}")
    k3.metric("% con salario IESS", f"{df['SALARIO'].notna().mean() * 100:.0f}%")
    k4.metric("Deuda promedio (SBU)", f"{df['DEUDA_BASICOS'].mean():.0f}")
    k5.metric("% riesgo Alto", f"{(df['NIVEL_RIESGO'] == 'Alto').mean() * 100:.0f}%")

    col1, col2, col3 = st.columns(3)
    with col1:
        vc_ec = df["ESTADO_CIVIL"].value_counts()
        fig_ec = px.pie(values=vc_ec.values, names=vc_ec.index, title="Estado civil",
                        color_discrete_sequence=PALETA)
        fig_ec.update_layout(height=420)
        st.plotly_chart(fig_ec, use_container_width=True, key="conductual_estado_civil")
    with col2:
        top_cargo = df["CARGO"].value_counts().head(15).sort_values()
        if top_cargo.empty:
            st.caption("Sin datos de cargo para esta selección.")
        else:
            fig_cargo = px.bar(x=top_cargo.values, y=top_cargo.index, orientation="h",
                               title="Top 15 cargos", labels={"x": "clientes", "y": ""},
                               color_discrete_sequence=PALETA)
            fig_cargo.update_layout(height=420)
            st.plotly_chart(fig_cargo, use_container_width=True, key="conductual_top_cargos")
    with col3:
        top_empresa = df["EMPRESA"].value_counts().head(20)
        fig_emp = px.treemap(names=top_empresa.index, parents=[""] * len(top_empresa),
                             values=top_empresa.values, title="Principales empresas / empleadores")
        fig_emp.update_layout(height=420, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_emp, use_container_width=True, key="conductual_empresas")

    st.divider()
    st.markdown("### Capacidad económica — personas")
    fig = make_subplots(rows=1, cols=3, subplot_titles=(
        "Salario formal declarado (IESS)", "Deuda bancaria (en SBU)", "Nivel de riesgo (buro)"))
    fig.add_histogram(x=df.loc[df["SALARIO"] < 8000, "SALARIO"], nbinsx=40, marker_color=PALETA[0], row=1, col=1)
    fig.add_histogram(x=df.loc[df["DEUDA_BASICOS"] < 400, "DEUDA_BASICOS"], nbinsx=40, marker_color=PALETA[2], row=1, col=2)
    vc = df["NIVEL_RIESGO"].value_counts().reindex(ORDEN_RIESGO).dropna()
    fig.add_bar(x=vc.index, y=vc.values, marker_color=PALETA[3], row=1, col=3)
    fig.update_layout(height=380, showlegend=False)
    st.plotly_chart(fig, use_container_width=True, key="conductual_capacidad_economica")

    st.divider()
    st.markdown("## Preferencia de producto - MODELO y vehiculo")
    st.caption(
        f"Cobertura de las variables del vehiculo sobre esta seleccion: "
        f"{compras['EN_CATALOGO'].mean() * 100:.1f}% - el resto queda como SIN INFO. "
        f"Cada fila es una compra (un cliente puede tener varias)."
    )

    col_izq, col_der = st.columns(2)
    with col_izq:
        top_mod = compras["MODELO"].value_counts().head(10).sort_values()
        if top_mod.empty:
            st.caption("Sin compras de vehículo para esta selección.")
        else:
            fig_mod = px.bar(x=top_mod.values, y=top_mod.index, orientation="h",
                             title="Top 10 modelos", labels={"x": "compras", "y": ""},
                             color_discrete_sequence=PALETA)
            fig_mod.update_layout(height=380)
            st.plotly_chart(fig_mod, use_container_width=True, key="conductual_producto_top_modelos")
    with col_der:
        marca = compras["MARCA"].value_counts(normalize=True).mul(100).round(1)
        fig_marca = px.bar(marca, title="Distribucion por marca", labels={"value": "%", "index": ""},
                           color_discrete_sequence=PALETA)
        fig_marca.update_layout(showlegend=False, height=380, yaxis_ticksuffix="%")
        st.plotly_chart(fig_marca, use_container_width=True, key="conductual_producto_marca")

    col1, col2, col3 = st.columns(3)
    with col1:
        vc = compras["COMBUSTIBLE"].value_counts(normalize=True).mul(100).round(1)
        fig_comb = px.bar(vc, title="Combustible", labels={"value": "%", "index": ""},
                          color_discrete_sequence=PALETA)
        fig_comb.update_layout(showlegend=False, height=320, yaxis_ticksuffix="%")
        st.plotly_chart(fig_comb, use_container_width=True, key="conductual_producto_combustible")
    with col2:
        vc = compras["HIBRIDACION"].value_counts(normalize=True).mul(100).round(1)
        fig_hib = px.bar(vc, title="Hibridacion", labels={"value": "%", "index": ""},
                         color_discrete_sequence=PALETA)
        fig_hib.update_layout(showlegend=False, height=320, yaxis_ticksuffix="%")
        st.plotly_chart(fig_hib, use_container_width=True, key="conductual_producto_hibridacion")
    with col3:
        vc = compras["CATEGORIA"].value_counts(normalize=True).mul(100).round(1)
        fig_cat = px.bar(vc, title="Categoria", labels={"value": "%", "index": ""},
                         color_discrete_sequence=PALETA)
        fig_cat.update_layout(showlegend=False, height=320, yaxis_ticksuffix="%")
        st.plotly_chart(fig_cat, use_container_width=True, key="conductual_producto_categoria")

    c6, c7 = st.columns(2)
    with c6:
        seg_chart = compras["SEGMENTO"].value_counts().head(12).sort_values()
        if seg_chart.empty:
            st.caption("Sin datos de segmento para esta selección.")
        else:
            fig_seg = px.bar(x=seg_chart.values, y=seg_chart.index, orientation="h",
                             title="Segmento del vehiculo", labels={"x": "compras", "y": ""},
                             color_discrete_sequence=PALETA)
            fig_seg.update_layout(height=420)
            st.plotly_chart(fig_seg, use_container_width=True, key="conductual_producto_segmento")
    with c7:
        sub_chart = compras["SUBSEGMENTO"].value_counts().head(12).sort_values()
        if sub_chart.empty:
            st.caption("Sin datos de subsegmento para esta selección.")
        else:
            fig_subseg = px.bar(x=sub_chart.values, y=sub_chart.index, orientation="h",
                                title="Subsegmento del vehiculo", labels={"x": "compras", "y": ""},
                                color_discrete_sequence=PALETA)
            fig_subseg.update_layout(height=420)
            st.plotly_chart(fig_subseg, use_container_width=True, key="conductual_producto_subsegmento")

    # A diferencia de la version en Producto (que usa GENERACION), aqui se usa RANGO_EDAD.
    tab_edad = (pd.crosstab(compras["CATEGORIA"], compras["RANGO_EDAD"], normalize="columns") * 100).round(0)
    fig_heat_edad = px.imshow(tab_edad, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                              title="Mix de categoria de vehiculo por rango de edad (% por columna)")
    fig_heat_edad.update_traces(texttemplate="%{z:.0f}%")
    fig_heat_edad.update_layout(height=360, coloraxis_colorbar_ticksuffix="%")
    st.plotly_chart(fig_heat_edad, use_container_width=True, key="conductual_producto_heatmap_edad")

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
        st.dataframe(cap_comb, use_container_width=True, key="conductual_cap_comb_tabla")
        fig_cap_comb = px.bar(cap_comb["salario_promedio"].dropna(), title="Salario promedio por combustible",
                              labels={"value": "USD/mes", "COMBUSTIBLE": ""}, color_discrete_sequence=PALETA)
        fig_cap_comb.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig_cap_comb, use_container_width=True, key="conductual_cap_comb_salario")
    with col5:
        st.markdown("**Por segmento**")
        seg_dedup = compras.drop_duplicates(["IDENTIFICACION_CLIENTE", "SEGMENTO"])
        cap_segmento = compras.groupby("SEGMENTO").agg(n=("SEGMENTO", "size"))
        cap_segmento["salario_promedio"] = seg_dedup.groupby("SEGMENTO")["SALARIO"].mean()
        cap_segmento["edad_promedio"] = seg_dedup.groupby("SEGMENTO")["EDAD"].mean()
        cap_segmento = cap_segmento.round(1).sort_values("n", ascending=False)
        st.dataframe(cap_segmento, use_container_width=True, key="conductual_cap_segmento_tabla")

    st.markdown("**Distribucion de salarios por modelo (top 12)**")
    modelos_top = compras["MODELO"].value_counts().head(12).index
    box_df = compras[compras["MODELO"].isin(modelos_top) & (compras["SALARIO"] < 12000)]
    box_df = box_df.drop_duplicates(["IDENTIFICACION_CLIENTE", "MODELO"])
    fig_box = px.box(box_df, x="SALARIO", y="MODELO", color="CATEGORIA", points="outliers",
                     labels={"SALARIO": "Salario USD/mes", "MODELO": ""}, color_discrete_sequence=PALETA)
    fig_box.update_layout(height=480)
    st.plotly_chart(fig_box, use_container_width=True, key="conductual_cap_boxplot_salario")
