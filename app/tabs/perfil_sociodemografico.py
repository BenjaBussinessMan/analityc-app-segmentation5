"""Tab: Perfil Sociodemografico - vista resumen (pirueta demografica + region + mapa).

Reutiliza graficos ya existentes en el notebook de exploracion (piramide poblacional,
dona de nivel socioeconomico, treemap region/provincia) y en el Dashboard (mapa
coropletico por canton de geografia.py), sin variables de vehiculo.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data import ORDEN_SALARIO, PALETA_TEMA, base_geojson, gen_label, sankey

PALETA = PALETA_TEMA
ORDEN_REGION = ["Sierra", "Costa", "Oriente", "Insular", "Otra / s/d"]


def _barras(serie, orden=None):
    vc = serie.value_counts()
    if orden:
        vc = vc.reindex([o for o in orden if o in vc.index])
    return vc


def render(df, compras, geojson_ec):
    st.subheader("Perfil Sociodemografico")

    ultima_compra = compras.sort_values("FECHA").drop_duplicates("IDENTIFICACION_CLIENTE", keep="last")
    cat_reciente = ultima_compra.set_index("IDENTIFICACION_CLIENTE")["CATEGORIA"]
    df = df.assign(CATEGORIA_RECIENTE=df["IDENTIFICACION"].map(cat_reciente).fillna("Sin compra"))

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Clientes", f"{len(df):,}")
    k2.metric("Edad promedio", f"{df['EDAD'].mean():.0f} años")
    k3.metric("% Instruccion superior", f"{(df['INSTRUCCION'] == 'SUPERIOR').mean() * 100:.0f}%")
    k4.metric("% Casados", f"{(df['ESTADO_CIVIL'] == 'CASADO').mean() * 100:.0f}%")
    k5.metric("Generacion predominante", gen_label(df["GENERACION"].value_counts().idxmax()))

    col1, col2, col3 = st.columns(3)
    with col1:
        piramide = (df.groupby(["RANGO_EDAD", "SEXO"], observed=True).size()
                    .unstack("SEXO", fill_value=0)
                    .reindex(columns=["HOMBRE", "MUJER"], fill_value=0))
        fig_pir = go.Figure()
        fig_pir.add_bar(y=piramide.index.astype(str), x=-piramide["HOMBRE"], name="Hombre",
                        orientation="h", marker_color=PALETA[0])
        fig_pir.add_bar(y=piramide.index.astype(str), x=piramide["MUJER"], name="Mujer",
                        orientation="h", marker_color=PALETA[1])
        fig_pir.update_layout(title="Pirámide poblacional — Edad × Sexo (personas)", barmode="overlay",
                              height=420, bargap=0.15, xaxis_title="Clientes (Hombres a la izquierda)")
        st.plotly_chart(fig_pir, use_container_width=True)
    with col2:
        vc_inst = _barras(df["INSTRUCCION"])
        if vc_inst.empty:
            st.caption("Sin datos de instrucción para esta selección.")
        else:
            fig_inst = px.bar(x=vc_inst.index.astype(str), y=vc_inst.values, title="Instrucción",
                              labels={"x": "", "y": "clientes"}, color_discrete_sequence=PALETA)
            fig_inst.update_layout(showlegend=False, height=420)
            st.plotly_chart(fig_inst, use_container_width=True)
    with col3:
        vc_rango_sal = df["RANGO_SALARIO"].value_counts()
        fig_dona = px.pie(values=vc_rango_sal.values, names=vc_rango_sal.index.astype(str), hole=0.45,
                          title="Nivel socioeconómico — distribución por rango de salario (SBU)",
                          color_discrete_sequence=PALETA)
        fig_dona.update_layout(height=420)
        st.plotly_chart(fig_dona, use_container_width=True)

    col4, col5 = st.columns(2)
    with col4:
        tree_df = df.dropna(subset=["PROVINCIA"]).assign(cnt=1)
        fig_tree = px.treemap(tree_df, path=[px.Constant("Ecuador"), "REGION", "PROVINCIA"], values="cnt",
                              title="Densidad de clientes por región y provincia (personas)")
        fig_tree.update_layout(height=430, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_tree, use_container_width=True)
    with col5:
        variable_mapa = st.radio("Colorear mapa por:", ["N de clientes", "Salario promedio"],
                                 horizontal=True, key="perfil_socio_mapa")

        todos_cantones = sorted({f["properties"]["DPA_DESCAN"] for f in geojson_ec["features"]})
        todos = pd.DataFrame({"CANTON_GEO": todos_cantones})
        agg = (df.dropna(subset=["CANTON_GEO"]).groupby("CANTON_GEO")
               .agg(clientes=("CANTON_GEO", "size"), salario_promedio=("SALARIO", "mean")).reset_index())
        cnt_canton = todos.merge(agg, on="CANTON_GEO", how="left")
        cnt_canton["clientes"] = cnt_canton["clientes"].fillna(0)

        fig_map = go.Figure()
        fig_map.add_trace(base_geojson(geojson_ec, todos_cantones))

        if variable_mapa == "N de clientes":
            con_datos = cnt_canton[cnt_canton["clientes"] > 0].copy()
            con_datos["z"] = np.log1p(con_datos["clientes"])
            max_c = int(cnt_canton["clientes"].max())
            ticks_reales = sorted({v for v in [1, 5, 10, 25, 50, 100, 250, max_c] if 0 < v <= max_c})
            fig_map.add_trace(go.Choropleth(
                geojson=geojson_ec, locations=con_datos["CANTON_GEO"], z=con_datos["z"],
                featureidkey="properties.DPA_DESCAN", colorscale="Blues",
                marker_line_color="white", marker_line_width=0.3,
                customdata=con_datos["clientes"],
                hovertemplate="%{location}<br>Clientes: %{customdata:.0f}<extra></extra>",
                colorbar=dict(title="Clientes", tickvals=np.log1p(ticks_reales), ticktext=[str(v) for v in ticks_reales]),
            ))
        else:
            con_datos = cnt_canton.dropna(subset=["salario_promedio"])
            fig_map.add_trace(go.Choropleth(
                geojson=geojson_ec, locations=con_datos["CANTON_GEO"], z=con_datos["salario_promedio"],
                featureidkey="properties.DPA_DESCAN", colorscale="Viridis",
                marker_line_color="white", marker_line_width=0.3,
                hovertemplate="%{location}<br>Salario promedio: $%{z:.0f}<extra></extra>",
                colorbar=dict(title="USD/mes"),
            ))

        # Vista acotada al Ecuador continental: con fitbounds="geojson" el mapa incluye
        # Galapagos, muy alejado del continente, lo que estira la proporcion geografica
        # real y deja el mapa diminuto con mucho margen en blanco alrededor. Galapagos
        # sigue en los datos/otros graficos (tabla de region, donas) - solo no se ve en
        # este mapa puntual, para que el continente llene el espacio disponible.
        fig_map.update_geos(lonaxis_range=[-81.5, -75.0], lataxis_range=[-5.2, 1.6], visible=False)
        fig_map.update_layout(height=430, margin=dict(l=0, r=0, t=30, b=0),
                              title=f"{variable_mapa} por canton (personas) - en gris, cantones sin clientes")
        st.plotly_chart(fig_map, use_container_width=True)

    st.divider()
    st.markdown("### Region y topografia")
    geo_demo = df.groupby("REGION").agg(
        clientes=("REGION", "size"), edad_promedio=("EDAD", "mean"), salario_promedio=("SALARIO", "mean"),
    )
    geo_veh = compras.groupby("REGION").agg(
        pct_diesel=("COMBUSTIBLE", lambda s: (s == "DIESEL").mean() * 100),
        pct_hibrido=("COMBUSTIBLE", lambda s: (s == "HIBRIDO").mean() * 100),
        pct_electricos=("COMBUSTIBLE", lambda s: (s == "ELECTRICO").mean() * 100),
    )
    geo = geo_demo.join(geo_veh, how="left").round(1).sort_values("clientes", ascending=False)
    st.dataframe(geo, use_container_width=True, key="perfil_socio_region_tabla")

    st.markdown("**Categoria de vehiculo por region**")
    regiones_validas = [r for r in ORDEN_REGION if (compras["REGION"] == r).sum() > 0]
    if regiones_validas:
        n = len(regiones_validas)
        fig_dona_region = make_subplots(
            rows=1, cols=n, specs=[[{"type": "domain"}] * n], subplot_titles=regiones_validas,
        )
        for i, reg in enumerate(regiones_validas, start=1):
            cat_counts = compras.loc[compras["REGION"] == reg, "CATEGORIA"].value_counts()
            fig_dona_region.add_trace(
                go.Pie(labels=cat_counts.index, values=cat_counts.values, hole=0.5,
                       marker=dict(colors=PALETA), name=reg, textinfo="percent",
                       textposition="inside", sort=False),
                row=1, col=i,
            )
        fig_dona_region.update_layout(height=380, showlegend=True, legend_title_text="Categoria")
        st.plotly_chart(fig_dona_region, use_container_width=True, key="perfil_socio_region_dona_categoria")

    c3, c4 = st.columns(2)
    with c3:
        comb_reg = (pd.crosstab(compras["REGION"], compras["COMBUSTIBLE"], normalize="index") * 100).round(1)
        fig_comb_reg = px.bar(comb_reg, barmode="stack", title="Mix de combustible por region",
                              labels={"value": "%", "REGION": ""}, color_discrete_sequence=PALETA)
        fig_comb_reg.update_layout(height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig_comb_reg, use_container_width=True, key="perfil_socio_region_combustible")
    with c4:
        sal_reg = df.copy()
        sal_reg["RANGO_SALARIO"] = sal_reg["RANGO_SALARIO"].astype(str).replace({"nan": "Sin dato"})
        mix_sal = (pd.crosstab(sal_reg["REGION"], sal_reg["RANGO_SALARIO"], normalize="index") * 100).round(1)
        cols_sal = [c for c in ORDEN_SALARIO + ["Sin dato"] if c in mix_sal.columns]
        fig_sal_reg = px.bar(mix_sal[cols_sal], barmode="stack", title="Mix de rango salarial por region",
                             labels={"value": "%", "REGION": ""}, color_discrete_sequence=PALETA)
        fig_sal_reg.update_layout(height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig_sal_reg, use_container_width=True, key="perfil_socio_region_salario")

    st.divider()
    st.markdown("### Cobertura y asignacion de stock: cantones con clientes de altos ingresos")
    st.caption("Pregunta de negocio: donde hay alta concentracion de clientes de altos ingresos que justifique "
               "reforzar concesionario o taller.")
    con_sal = df[df["SALARIO"].notna()]
    if len(con_sal):
        umbral = con_sal["SALARIO"].quantile(0.75)
        st.caption(f"Alto ingreso = salario >= percentil 75 de la seleccion (${umbral:,.0f}/mes).")
        d = df.dropna(subset=["CANTON_GEO"]).copy()
        d["ALTO_INGRESO"] = d["SALARIO"] >= umbral
        cant = (d.groupby("CANTON_GEO")
                .agg(clientes=("CANTON_GEO", "size"), altos_ingresos=("ALTO_INGRESO", "sum"),
                     salario_promedio=("SALARIO", "mean"))
                .sort_values("altos_ingresos", ascending=False).head(12).round(0))
        c7, c8 = st.columns([1, 1])
        with c7:
            st.dataframe(cant, use_container_width=True, key="perfil_socio_cobertura_tabla")
        with c8:
            top = cant.sort_values("altos_ingresos").reset_index()
            fig_ai = px.bar(top, x="altos_ingresos", y="CANTON_GEO", orientation="h",
                            title="Clientes de alto ingreso por canton",
                            labels={"altos_ingresos": "clientes", "CANTON_GEO": ""},
                            color_discrete_sequence=PALETA, hover_data=["clientes", "salario_promedio"])
            fig_ai.update_layout(height=430)
            st.plotly_chart(fig_ai, use_container_width=True, key="perfil_socio_cobertura_bar")

    st.divider()
    st.markdown("### Flujo de compra: sexo, estado civil, rango salarial y categoria")
    df_sk = df.copy()
    df_sk["RANGO_SALARIO"] = df_sk["RANGO_SALARIO"].astype(str)
    fig_sk = sankey(df_sk, ["SEXO", "ESTADO_CIVIL", "RANGO_SALARIO", "CATEGORIA_RECIENTE"],
                    "Flujo de compra por perfil",
                    col_labels=["Sexo", "Estado civil", "Rango salarial (SBU)", "Categoría (última compra)"])
    st.plotly_chart(fig_sk, use_container_width=True, key="perfil_socio_sankey")
