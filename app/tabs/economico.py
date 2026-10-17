"""Tab: Perfil economico y crediticio (personas naturales)."""
import pandas as pd
import plotly.express as px
import streamlit as st
from plotly.subplots import make_subplots

from data import ORDEN_RIESGO, PALETA_TEMA, SBU, SEGMENTOS_GAMA_ALTA

PALETA = PALETA_TEMA


def _moda(s):
    return s.mode().iat[0] if not s.mode().empty else "-"


def render(df, compras):
    st.subheader("Perfil economico y crediticio - personas naturales")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Salario mediano", f"${df['SALARIO'].median():,.0f}")
    k2.metric("Salario promedio", f"${df['SALARIO'].mean():,.0f}")
    k3.metric("% con salario IESS", f"{df['SALARIO'].notna().mean() * 100:.0f}%")
    k4.metric("Deuda promedio (SBU)", f"{df['DEUDA_BASICOS'].mean():.0f}")
    k5.metric("% riesgo Alto", f"{(df['NIVEL_RIESGO'] == 'Alto').mean() * 100:.0f}%")

    fig = make_subplots(rows=1, cols=3, subplot_titles=(
        "Salario formal declarado (IESS)", "Deuda bancaria (en SBU)", "Nivel de riesgo (buro)"))
    fig.add_histogram(x=df.loc[df["SALARIO"] < 8000, "SALARIO"], nbinsx=40, marker_color=PALETA[0], row=1, col=1)
    fig.add_histogram(x=df.loc[df["DEUDA_BASICOS"] < 400, "DEUDA_BASICOS"], nbinsx=40, marker_color=PALETA[2], row=1, col=2)
    vc = df["NIVEL_RIESGO"].value_counts().reindex(ORDEN_RIESGO).dropna()
    fig.add_bar(x=vc.index, y=vc.values, marker_color=PALETA[3], row=1, col=3)
    fig.update_layout(height=380, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    col_izq, col_der = st.columns(2)
    with col_izq:
        sal_inst = df.groupby("INSTRUCCION")["SALARIO"].mean().sort_values(ascending=False)
        fig2 = px.bar(sal_inst, orientation="h", title="Salario promedio por instruccion",
                      labels={"value": "USD/mes", "INSTRUCCION": ""}, color_discrete_sequence=PALETA)
        fig2.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig2, use_container_width=True)
    with col_der:
        sub = df[(df["SALARIO"] < 8000) & (df["DEUDA_BASICOS"] < 300) & df["SALARIO"].notna()]
        fig3 = px.scatter(sub, x="SALARIO", y="DEUDA_BASICOS", color="NIVEL_RIESGO",
                          category_orders={"NIVEL_RIESGO": ORDEN_RIESGO}, opacity=0.6,
                          title="Endeudamiento vs. salario, por riesgo de buro",
                          labels={"SALARIO": "Salario USD/mes", "DEUDA_BASICOS": "Deuda (SBU)"},
                          color_discrete_sequence=PALETA)
        fig3.update_layout(height=320)
        st.plotly_chart(fig3, use_container_width=True)

    st.divider()
    st.markdown("### Carga financiera por tipo de empleo")
    carga = df.groupby("TIPO EMPLEO").agg(
        n=("TIPO EMPLEO", "size"),
        salario_promedio=("SALARIO", "mean"),
        deuda_basicos_prom=("DEUDA_BASICOS", "mean"),
        deuda_usd_prom=("DEUDA_USD_APROX", "mean"),
        apalancamiento_meses_prom=("APALANCAMIENTO_MESES", "mean"),
        operaciones_prom=("N_OPERACIONES_BURO", "mean"),
    ).round(1).sort_values("n", ascending=False)
    st.dataframe(carga, use_container_width=True)

    mix_riesgo = (pd.crosstab(compras["CATEGORIA"], compras["NIVEL_RIESGO"], normalize="index")
                  .reindex(columns=ORDEN_RIESGO).round(3) * 100)
    fig4 = px.bar(mix_riesgo, orientation="h", title="Perfil crediticio por categoria de vehiculo",
                  labels={"value": "% de clientes", "CATEGORIA": ""}, color_discrete_sequence=PALETA)
    fig4.update_layout(barmode="stack", height=340, xaxis_ticksuffix="%")
    st.plotly_chart(fig4, use_container_width=True)

    st.divider()
    st.markdown("### Pre-aprobacion de credito directo")
    st.caption("Pregunta de negocio: que porcentaje de la base tiene perfil de bajo riesgo para financiamiento pre-aprobado.")
    apal = df["APALANCAMIENTO_MESES"].fillna(0)
    a1_ok = df["PEOR_CALIFICACION"].eq("A1") & (apal <= 12)
    bajo_ok = df["NIVEL_RIESGO"].eq("Bajo") & (apal <= 18)
    p1, p2, p3 = st.columns(3)
    p1.metric("Pre-aprobable (A1 + deuda <= 12 meses)", f"{a1_ok.sum():,}",
              f"{a1_ok.mean() * 100:.0f}% de la base")
    p2.metric("Criterio amplio (riesgo Bajo + deuda <= 18 meses)", f"{bajo_ok.sum():,}",
              f"{bajo_ok.mean() * 100:.0f}% de la base")
    p3.metric("Sin calificacion de buro", f"{df['CALIFICACION'].isna().sum():,}",
              f"{df['CALIFICACION'].isna().mean() * 100:.0f}% - requieren consulta")
    preap_perfil = (df[a1_ok].groupby("PERFIL").size().sort_values(ascending=False))
    if len(preap_perfil):
        fig_pa = px.bar(preap_perfil, orientation="h", title="Clientes pre-aprobables por perfil de negocio",
                        labels={"value": "clientes", "index": ""}, color_discrete_sequence=PALETA)
        fig_pa.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig_pa, use_container_width=True)

    st.divider()
    st.markdown("### Brecha entre ingreso y ticket del vehiculo")
    st.caption("Pregunta de negocio: clientes con vehiculo de gama alta cuyo ingreso registrado puede exigir garante o mayor entrada. "
               "No hay precio de lista: el ticket se aproxima por el segmento (D/E SUV, Premium SUV, Full size pick up).")
    ids_gama = compras.loc[compras["SEGMENTO"].isin(SEGMENTOS_GAMA_ALTA), "IDENTIFICACION_CLIENTE"].unique()
    gama = df[df["IDENTIFICACION"].isin(ids_gama)]
    brecha = gama[gama["SALARIO"] < 3 * SBU]
    sin_sal = gama[gama["SALARIO"].isna()]
    b1, b2, b3 = st.columns(3)
    b1.metric("Clientes en gama alta", f"{len(gama):,}")
    b2.metric("Con salario < 3 SBU (posible brecha)", f"{len(brecha):,}",
              f"{len(brecha) / max(len(gama), 1) * 100:.0f}% de la gama alta")
    b3.metric("Sin salario formal declarado", f"{len(sin_sal):,}")

    st.divider()
    st.markdown("### Perfil de morosidad: donde se concentra el endeudamiento")
    st.caption("Pregunta de negocio: que profesiones, sectores o rangos de edad tienen mayor deuda bancaria.")
    col_e, col_f = st.columns(2)
    with col_e:
        deuda_edad = df.groupby("RANGO_EDAD", observed=True)["DEUDA_BASICOS"].mean().round(1)
        fig_de = px.bar(deuda_edad, title="Deuda promedio (SBU) por rango de edad",
                        labels={"value": "SBU", "RANGO_EDAD": ""}, color_discrete_sequence=PALETA)
        fig_de.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig_de, use_container_width=True)
    with col_f:
        deuda_prof = (df.groupby("PROFESION").agg(n=("PROFESION", "size"), deuda=("DEUDA_BASICOS", "mean"))
                      .query("n >= 15").sort_values("deuda", ascending=False).head(10).round(1))
        fig_dp = px.bar(deuda_prof["deuda"].sort_values(), orientation="h",
                        title="Profesiones con mayor deuda promedio (SBU, n>=15)",
                        labels={"value": "SBU", "PROFESION": ""}, color_discrete_sequence=PALETA)
        fig_dp.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig_dp, use_container_width=True)

    st.divider()
    st.markdown("### Salario y vehiculo por cargo (top 15)")
    con_cargo = compras[compras["CARGO"].notna()]
    con_cargo_dedup = con_cargo.drop_duplicates(["IDENTIFICACION_CLIENTE", "CARGO"])
    cargo = con_cargo.groupby("CARGO").agg(
        clientes=("IDENTIFICACION_CLIENTE", "nunique"),
        categoria_frecuente=("CATEGORIA", _moda),
        modelo_frecuente=("MODELO", _moda),
    )
    cargo["salario_promedio"] = con_cargo_dedup.groupby("CARGO")["SALARIO"].mean()
    cargo = cargo.round(0).sort_values("clientes", ascending=False).head(15)
    col_a, col_b = st.columns([1.4, 1])
    with col_a:
        st.dataframe(cargo, use_container_width=True)
    with col_b:
        fig5 = px.bar(cargo["salario_promedio"].dropna().sort_values(), orientation="h",
                      title="Salario promedio por cargo", labels={"value": "USD/mes", "CARGO": ""},
                      color_discrete_sequence=PALETA)
        fig5.update_layout(showlegend=False, height=430)
        st.plotly_chart(fig5, use_container_width=True)

    st.divider()
    st.markdown("### Empresas donde trabajan los clientes (top 15)")
    emp = df["EMPRESA"].value_counts().head(15).sort_values()
    fig6 = px.bar(x=emp.values, y=emp.index, orientation="h",
                  title="Clientes por empresa empleadora", labels={"x": "clientes", "y": ""},
                  color_discrete_sequence=PALETA)
    fig6.update_layout(height=430)
    st.plotly_chart(fig6, use_container_width=True)

    st.caption(
        "La mayor parte de la cartera (riesgo bajo, apalancamiento moderado) es apta para credito "
        "automotriz estandar; el control debe concentrarse en el segmento de riesgo Alto."
    )
