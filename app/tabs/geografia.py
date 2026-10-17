"""Tab: Analisis geografico - region, tipos de localidad y mapa coropletico."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data import ORDEN_LOCALIDAD, ORDEN_SALARIO, PALETA_TEMA, base_geojson

PALETA = PALETA_TEMA
ORDEN_REGION = ["Sierra", "Costa", "Oriente", "Insular", "Otra / s/d"]


def render(df, compras, geojson_ec):
    st.subheader("Analisis geografico y configuracion del vehiculo")

    # ---------------- Region ----------------
    st.markdown("### Region y topografia")
    geo_demo = df.groupby("REGION").agg(
        clientes=("REGION", "size"), edad_promedio=("EDAD", "mean"), salario_promedio=("SALARIO", "mean"),
    )
    geo_veh = compras.groupby("REGION").agg(
        pct_4x4=("TRACCION", lambda s: (s == "4x4").mean() * 100),
        cilindrada_promedio=("CILINDRADA", "mean"),
        pct_diesel=("COMBUSTIBLE", lambda s: (s == "DIESEL").mean() * 100),
        pct_hibrido=("COMBUSTIBLE", lambda s: (s == "HIBRIDO").mean() * 100),
    )
    geo = geo_demo.join(geo_veh, how="left").round(1).sort_values("clientes", ascending=False)
    st.dataframe(geo, use_container_width=True)

    st.markdown("**Categoria de vehiculo por region**")
    regiones_validas = [r for r in ORDEN_REGION if (compras["REGION"] == r).sum() > 0]
    if regiones_validas:
        n = len(regiones_validas)
        fig_dona = make_subplots(
            rows=1, cols=n, specs=[[{"type": "domain"}] * n], subplot_titles=regiones_validas,
        )
        for i, reg in enumerate(regiones_validas, start=1):
            cat_counts = compras.loc[compras["REGION"] == reg, "CATEGORIA"].value_counts()
            fig_dona.add_trace(
                go.Pie(labels=cat_counts.index, values=cat_counts.values, hole=0.5,
                       marker=dict(colors=PALETA), name=reg, textinfo="percent",
                       textposition="inside", sort=False),
                row=1, col=i,
            )
        fig_dona.update_layout(height=380, showlegend=True, legend_title_text="Categoria")
        st.plotly_chart(fig_dona, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        comb_reg = (pd.crosstab(compras["REGION"], compras["COMBUSTIBLE"], normalize="index") * 100).round(1)
        fig3 = px.bar(comb_reg, barmode="stack", title="Mix de combustible por region",
                      labels={"value": "%", "REGION": ""}, color_discrete_sequence=PALETA)
        fig3.update_layout(height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig3, use_container_width=True)
    with c4:
        sal_reg = df.copy()
        sal_reg["RANGO_SALARIO"] = sal_reg["RANGO_SALARIO"].astype(str).replace({"nan": "Sin dato"})
        mix_sal = (pd.crosstab(sal_reg["REGION"], sal_reg["RANGO_SALARIO"], normalize="index") * 100).round(1)
        cols_sal = [c for c in ORDEN_SALARIO + ["Sin dato"] if c in mix_sal.columns]
        fig_sal = px.bar(mix_sal[cols_sal], barmode="stack", title="Mix de rango salarial por region",
                         labels={"value": "%", "REGION": ""}, color_discrete_sequence=PALETA)
        fig_sal.update_layout(height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig_sal, use_container_width=True)

    st.markdown("### Preferencia de modelos por region (Costa vs. Sierra vs. Oriente)")
    st.caption("Pregunta de negocio: que modelos y tipo de traccion (4x4 vs 4x2) penetran mas en Sierra vs. Costa.")
    modelos_top = compras["MODELO"].value_counts().head(10).index
    pref = (pd.crosstab(compras.loc[compras["MODELO"].isin(modelos_top), "MODELO"],
                        compras.loc[compras["MODELO"].isin(modelos_top), "REGION"], normalize="columns") * 100).round(1)
    pref = pref[[c for c in ORDEN_REGION if c in pref.columns]]
    fig_pref = px.imshow(pref, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                         title="% de compradores de cada modelo dentro de la region")
    fig_pref.update_traces(texttemplate="%{z:.0f}%")
    fig_pref.update_layout(height=430, coloraxis_colorbar_ticksuffix="%")
    st.plotly_chart(fig_pref, use_container_width=True)

    st.divider()

    # ---------------- Tipos de localidad + mapa ----------------
    st.markdown("### Tipos de localidad (mapa coropletico por canton)")
    st.caption(f"Cobertura del cruce canton-GeoJSON: {df['EN_GEOJSON'].mean() * 100:.0f}% de los clientes filtrados.")

    variable_mapa = st.radio("Colorear mapa por:", ["N de clientes", "Salario promedio"], horizontal=True)

    todos_cantones = sorted({f["properties"]["DPA_DESCAN"] for f in geojson_ec["features"]})
    todos = pd.DataFrame({"CANTON_GEO": todos_cantones})
    agg = (df.dropna(subset=["CANTON_GEO"]).groupby("CANTON_GEO")
           .agg(clientes=("CANTON_GEO", "size"), salario_promedio=("SALARIO", "mean")).reset_index())
    cnt_canton = todos.merge(agg, on="CANTON_GEO", how="left")
    cnt_canton["clientes"] = cnt_canton["clientes"].fillna(0)

    # Capa base gris con TODOS los cantones del GeoJSON: garantiza que se vean
    # siempre el contorno completo del pais y todas las provincias, tengan o no
    # clientes (antes, con salario promedio, las provincias sin datos quedaban
    # totalmente en blanco y "desaparecian" del mapa).
    fig_map = go.Figure()
    fig_map.add_trace(base_geojson(geojson_ec, todos_cantones))

    if variable_mapa == "N de clientes":
        # Escala logaritmica: el conteo esta muy concentrado en 2-3 cantones
        # (Quito, Guayaquil...) y en lineal el resto del mapa se ve casi blanco,
        # como si solo existiera una region con datos.
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

    fig_map.update_geos(fitbounds="geojson", visible=False)
    fig_map.update_layout(height=580, margin=dict(l=0, r=0, t=40, b=0),
                          title=f"{variable_mapa} por canton (personas) - en gris, cantones sin clientes")
    st.plotly_chart(fig_map, use_container_width=True)

    resumen_loc_demo = df.groupby("TIPO_LOCALIDAD").agg(
        n=("TIPO_LOCALIDAD", "size"), edad_promedio=("EDAD", "mean"), salario_promedio=("SALARIO", "mean"),
        deuda_basicos_prom=("DEUDA_BASICOS", "mean"),
        pct_riesgo_alto=("NIVEL_RIESGO", lambda s: (s == "Alto").mean() * 100),
    )
    resumen_loc_veh = compras.groupby("TIPO_LOCALIDAD").agg(
        pct_4x4=("TRACCION", lambda s: (s == "4x4").mean() * 100),
        categoria_frecuente=("CATEGORIA", lambda s: s.mode().iat[0] if not s.mode().empty else "-"),
    )
    resumen_loc = (resumen_loc_demo.join(resumen_loc_veh, how="left")
                   .round(1).reindex(ORDEN_LOCALIDAD).dropna(how="all"))

    col5, col6 = st.columns([1, 1])
    with col5:
        st.dataframe(resumen_loc, use_container_width=True)
    with col6:
        mix_loc = (pd.crosstab(compras["TIPO_LOCALIDAD"], compras["CATEGORIA"], normalize="index")
                   .reindex(ORDEN_LOCALIDAD).dropna(how="all") * 100).round(1)
        fig4 = px.bar(mix_loc, barmode="stack", title="Categoria de vehiculo por tipo de localidad",
                      labels={"value": "%", "TIPO_LOCALIDAD": ""}, color_discrete_sequence=PALETA)
        fig4.update_layout(height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig4, use_container_width=True)

    st.caption(
        "Fuera de las capitales de provincia (donde domina el SUV urbano), los cantones rurales y "
        "dispersos muestran mayor preferencia por pick-up y 4x4 con menor ingreso formal declarado."
    )

    st.divider()
    st.markdown("### Modelo preferido por canton")
    st.caption("Pregunta de negocio: por canton, que modelos son los mas comprados.")

    cantones_con_datos = compras["CANTON_GEO"].value_counts()
    cantones_con_datos = cantones_con_datos[cantones_con_datos >= 3].sort_values(ascending=False)
    if len(cantones_con_datos):
        canton_sel = st.selectbox(
            "Canton", cantones_con_datos.index,
            format_func=lambda c: f"{c} ({cantones_con_datos[c]} compras)",
        )
        sub_canton = compras[compras["CANTON_GEO"] == canton_sel]
        top_modelos_canton = sub_canton["MODELO"].value_counts().head(8).sort_values()
        fig_modelo_canton = px.bar(
            x=top_modelos_canton.values, y=top_modelos_canton.index, orientation="h",
            title=f"Modelos mas comprados en {canton_sel} (n={len(sub_canton)})",
            labels={"x": "compras", "y": ""}, color_discrete_sequence=PALETA,
        )
        fig_modelo_canton.update_layout(height=340)
        st.plotly_chart(fig_modelo_canton, use_container_width=True)

        top_cantones = compras["CANTON_GEO"].value_counts().head(12).index
        top_modelos_general = compras["MODELO"].value_counts().head(10).index
        sub = compras[compras["CANTON_GEO"].isin(top_cantones) & compras["MODELO"].isin(top_modelos_general)]
        heat_cm = (pd.crosstab(sub["CANTON_GEO"], sub["MODELO"], normalize="index") * 100).round(0)
        heat_cm = heat_cm.reindex(top_cantones).dropna(how="all")
        fig_heat_cm = px.imshow(heat_cm, text_auto=".0f", color_continuous_scale="Blues", aspect="auto",
                                title="Mix de modelo por canton (top 12 cantones x top 10 modelos)")
        fig_heat_cm.update_traces(texttemplate="%{z:.0f}%")
        fig_heat_cm.update_layout(height=460, coloraxis_colorbar_ticksuffix="%")
        st.plotly_chart(fig_heat_cm, use_container_width=True)
    else:
        st.info("No hay suficientes cantones con datos para este analisis con los filtros actuales.")

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
            st.dataframe(cant, use_container_width=True)
        with c8:
            top = cant.sort_values("altos_ingresos").reset_index()
            fig_ai = px.bar(top, x="altos_ingresos", y="CANTON_GEO", orientation="h",
                            title="Clientes de alto ingreso por canton",
                            labels={"altos_ingresos": "clientes", "CANTON_GEO": ""},
                            color_discrete_sequence=PALETA, hover_data=["clientes", "salario_promedio"])
            fig_ai.update_layout(height=430)
            st.plotly_chart(fig_ai, use_container_width=True)
