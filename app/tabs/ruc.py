"""Tab: Clientes con RUC — empresas y personas naturales con RUC."""
import pandas as pd
import plotly.express as px
import streamlit as st

from data import ORDEN_PORTE, PALETA_TEMA, tabla_segura

PALETA = PALETA_TEMA


def render(ruc, compras_ruc, ced=None, compras_ced=None):
    st.subheader("Clientes con RUC - empresas y personas naturales con RUC")

    with st.expander("Filtros de este tab", expanded=False):
        c1, c2 = st.columns(2)
        f_tipo = c1.multiselect("Tipo de persona", sorted(ruc["TIPO_PERSONA"].dropna().unique()))
        f_prov = c2.multiselect("Provincia (RUC)", sorted(ruc["PROVINCIA RUC"].dropna().unique()))

    df = ruc.copy()
    if f_tipo:
        df = df[df["TIPO_PERSONA"].isin(f_tipo)]
    if f_prov:
        df = df[df["PROVINCIA RUC"].isin(f_prov)]

    if df.empty:
        st.warning("No hay registros con esos filtros.")
        return

    compras_df = compras_ruc[compras_ruc["IDENTIFICACION"].isin(df["IDENTIFICACION"])]

    tp = df["TIPO_PERSONA"].value_counts()
    k1, k2, k3 = st.columns(3)
    k1.metric("Registros", f"{len(df):,}")
    k2.metric("Personas jurídicas", f"{tp.get('Persona Juridica', 0)} ({tp.get('Persona Juridica', 0) / len(df) * 100:.0f}%)")
    k3.metric("Naturales con RUC", f"{tp.get('Persona Natural con RUC', 0)} ({tp.get('Persona Natural con RUC', 0) / len(df) * 100:.0f}%)")

    col1, col2, col3 = st.columns(3)
    with col1:
        porte = df["PORTE"].value_counts().reindex(ORDEN_PORTE)
        fig = px.bar(x=porte.index.astype(str), y=porte.values, title="Porte (proxy nómina en SBU)",
                    color_discrete_sequence=PALETA)
        fig.update_layout(showlegend=False, height=340)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig2 = px.histogram(df.loc[df["DEUDA_BASICOS"] < 400, "DEUDA_BASICOS"], nbins=40,
                            title="Deuda bancaria (en SBU)", color_discrete_sequence=PALETA)
        fig2.update_layout(showlegend=False, height=340)
        st.plotly_chart(fig2, use_container_width=True)
    with col3:
        fig3 = px.bar(tp, title="Tipo de persona", color_discrete_sequence=PALETA)
        fig3.update_layout(showlegend=False, height=340)
        st.plotly_chart(fig3, use_container_width=True)

    seg = (pd.crosstab(compras_df["TIPO_PERSONA"], compras_df["CATEGORIA"], normalize="index") * 100).round(1)
    fig4 = px.bar(seg, barmode="stack", title="Categoria de vehiculo por tipo de persona",
                 labels={"value": "%", "TIPO_PERSONA": ""}, color_discrete_sequence=PALETA)
    fig4.update_layout(height=340, yaxis_ticksuffix="%")
    st.plotly_chart(fig4, use_container_width=True)

    st.markdown("**Perfiles RUC**")
    _moda = lambda s: s.mode().iat[0] if not s.mode().empty else "-"
    resumen_demo = df.groupby("PERFIL").agg(
        n=("PERFIL", "size"), deuda_usd_prom=("DEUDA_USD_APROX", "mean"),
        provincia_frecuente=("PROVINCIA RUC", _moda),
    )
    resumen_veh = compras_df.groupby("PERFIL").agg(
        categoria_frecuente=("CATEGORIA", _moda),
        modelo_frecuente=("MODELO", _moda),
    )
    resumen = resumen_demo.join(resumen_veh, how="left").round(0)
    st.dataframe(resumen, use_container_width=True)

    st.caption(
        "El canal RUC no es principalmente empresas grandes sino profesionales y micronegocios; "
        "la venta de flota real (4x4, pick-up, mediana empresa) es un segmento pequeno pero de mayor ticket."
    )

    if ced is not None and not ced.empty and compras_ced is not None:
        st.divider()
        st.markdown("### B2B (RUC) vs. B2C (cedula)")
        st.caption("Pregunta de negocio: como difieren los patrones de compra e ingresos entre clientes con RUC y personas naturales. "
                   "Los % de vehiculo se calculan sobre la ultima compra de cada cliente comprador.")
        cv_ced = compras_ced.sort_values("FECHA").drop_duplicates("IDENTIFICACION_CLIENTE", keep="last")
        cv_ruc = compras_ruc.sort_values("FECHA").drop_duplicates("IDENTIFICACION_CLIENTE", keep="last")
        juridica = ruc[ruc["TIPO_PERSONA"] == "Persona Juridica"]
        cv_juridica = cv_ruc[cv_ruc["TIPO_PERSONA"] == "Persona Juridica"]
        comp = pd.DataFrame({
            "Personas (cedula)": {
                "Clientes": len(ced),
                "% 4x4": (cv_ced["TRACCION"] == "4x4").mean() * 100,
                "% Pick-up": (cv_ced["CATEGORIA"] == "PICK UPS").mean() * 100,
                "% SUV": (cv_ced["CATEGORIA"] == "SUV").mean() * 100,
                "Deuda promedio (SBU)": ced["DEUDA_BASICOS"].mean(),
                "Cilindrada promedio": cv_ced["CILINDRADA"].mean(),
            },
            "Clientes con RUC": {
                "Clientes": len(ruc),
                "% 4x4": (cv_ruc["TRACCION"] == "4x4").mean() * 100,
                "% Pick-up": (cv_ruc["CATEGORIA"] == "PICK UPS").mean() * 100,
                "% SUV": (cv_ruc["CATEGORIA"] == "SUV").mean() * 100,
                "Deuda promedio (SBU)": ruc["DEUDA_BASICOS"].mean(),
                "Cilindrada promedio": cv_ruc["CILINDRADA"].mean(),
            },
            "Personas juridicas": {
                "Clientes": len(juridica),
                "% 4x4": (cv_juridica["TRACCION"] == "4x4").mean() * 100,
                "% Pick-up": (cv_juridica["CATEGORIA"] == "PICK UPS").mean() * 100,
                "% SUV": (cv_juridica["CATEGORIA"] == "SUV").mean() * 100,
                "Deuda promedio (SBU)": juridica["DEUDA_BASICOS"].mean(),
                "Cilindrada promedio": cv_juridica["CILINDRADA"].mean(),
            },
        }).round(1)
        st.dataframe(comp, use_container_width=True)

        mix = pd.DataFrame({
            "Personas (cedula)": compras_ced["CATEGORIA"].value_counts(normalize=True) * 100,
            "Clientes con RUC": compras_ruc["CATEGORIA"].value_counts(normalize=True) * 100,
        }).fillna(0).round(1)
        fig5 = px.bar(mix, barmode="group", title="Mix de categoria de vehiculo: B2B vs B2C",
                      labels={"value": "%", "index": ""}, color_discrete_sequence=PALETA)
        fig5.update_layout(height=340, yaxis_ticksuffix="%")
        st.plotly_chart(fig5, use_container_width=True)
        st.caption("Los clientes con RUC compran mucho mas 4x4 y pick-up (uso productivo / flota); "
                   "las personas naturales concentran el SUV urbano. Los RUC no tienen campo de salario.")

    with st.expander("Ver datos filtrados"):
        st.dataframe(
            tabla_segura(df, ["IDENTIFICACION", "RAZON_SOCIAL RUC", "TIPO_PERSONA", "PERFIL",
                              "PROVINCIA RUC", "CANTON RUC", "PROFESION", "DEUDA_BASICOS"]),
            use_container_width=True,
        )
