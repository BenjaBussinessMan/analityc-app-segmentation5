"""Tab: Contactabilidad y calidad de datos"""
import pandas as pd
import plotly.express as px
import streamlit as st

from data import PALETA_TEMA

PALETA = PALETA_TEMA


def _tabla_contacto(df, etiqueta):
    return pd.Series({
        "registros": len(df),
        "con_email_%": df["TIENE_EMAIL"].mean() * 100,
        "con_celular_%": df["TIENE_CELULAR"].mean() * 100,
        "con_fijo_%": df["TIENE_FIJO"].mean() * 100,
        "omnicanal_%": df["CONTACTO_OMNICANAL"].mean() * 100,
        "sin_ningun_canal_%": df["N_CANALES"].eq(0).mean() * 100,
    }, name=etiqueta).round(1)


def render(ced, ruc):
    st.subheader("Contactabilidad y calidad de datos")

    cont = pd.concat([_tabla_contacto(ced, "Personas (CED, filtrado)"), _tabla_contacto(ruc, "Clientes RUC")], axis=1)
    st.dataframe(cont, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        n = len(ced)
        funnel = pd.DataFrame({
            "etapa": ["Registros", "Con email", "Con celular", "Email + celular", "Omnicanal (email+cel+fijo)"],
            "clientes": [n, ced["TIENE_EMAIL"].sum(), ced["TIENE_CELULAR"].sum(),
                         (ced["TIENE_EMAIL"] & ced["TIENE_CELULAR"]).sum(), ced["CONTACTO_OMNICANAL"].sum()],
        })
        fig = px.funnel(funnel, x="clientes", y="etapa", title="Embudo de contactabilidad — personas",
                        color_discrete_sequence=PALETA)
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        brecha = (ced.groupby("PROVINCIA").agg(n=("PROVINCIA", "size"), email=("TIENE_EMAIL", "mean"),
                                                celular=("TIENE_CELULAR", "mean"), omnicanal=("CONTACTO_OMNICANAL", "mean")))
        brecha = brecha[brecha["n"] >= 15]
        brecha[["email", "celular", "omnicanal"]] = (brecha[["email", "celular", "omnicanal"]] * 100).round(1)
        brecha.index = brecha.index.str.replace("ð", "Ñ", regex=False)
        if brecha.empty:
            st.info("Ninguna provincia alcanza el mínimo de 15 registros con los filtros actuales.")
        else:
            fig2 = px.bar(brecha.sort_values("celular").reset_index(), x="celular", y="PROVINCIA", orientation="h",
                         title="% con celular por provincia (n>=15)", labels={"celular": "% con celular"},
                         color_discrete_sequence=PALETA)
            fig2.update_layout(showlegend=False, height=380, xaxis_ticksuffix="%")
            st.plotly_chart(fig2, use_container_width=True)

    st.caption(
        "Email y celular cubren a la gran mayoria de las personas; la brecha real esta en el "
        "telefono fijo y en la normalizacion de numeros telefonicos."
    )

    st.divider()
    st.markdown("### Volumen para campanas omnicanal por provincia")
    st.caption("Pregunta de negocio: donde hay mayor concentracion de clientes con email y celular completos.")
    ced2 = ced.copy()
    ced2["EMAIL_Y_CELULAR"] = ced2["TIENE_EMAIL"] & ced2["TIENE_CELULAR"]
    vol = (ced2.groupby("PROVINCIA")
           .agg(clientes=("PROVINCIA", "size"), email_y_celular=("EMAIL_Y_CELULAR", "sum"))
           .assign(pct=lambda d: (d["email_y_celular"] / d["clientes"] * 100).round(0))
           .sort_values("email_y_celular", ascending=False).head(10)
           .reset_index().sort_values("email_y_celular"))
    fig3 = px.bar(vol, x="email_y_celular", y="PROVINCIA", orientation="h",
                  title="Clientes con email + celular (volumen absoluto)",
                  labels={"email_y_celular": "clientes", "PROVINCIA": ""}, color_discrete_sequence=PALETA,
                  hover_data=["pct", "clientes"])
    fig3.update_layout(height=380)
    st.plotly_chart(fig3, use_container_width=True)
    st.caption(f"Total de la base con email + celular: {int(ced2['EMAIL_Y_CELULAR'].sum()):,} "
               f"({ced2['EMAIL_Y_CELULAR'].mean() * 100:.0f}%).")

    st.divider()
    st.markdown("### Salud de la base de datos")
    st.caption("Pregunta de negocio: que porcentaje de registros tiene informacion incompleta en variables criticas.")
    salud = pd.Series({
        "Ingreso (SALARIO IESS)": ced["SALARIO"].isna().mean() * 100,
        "Calificacion de buro": ced["CALIFICACION"].isna().mean() * 100,
        "Email": (~ced["TIENE_EMAIL"]).mean() * 100,
        "Celular": (~ced["TIENE_CELULAR"]).mean() * 100,
        "Canton ubicable en mapa": (~ced["EN_GEOJSON"]).mean() * 100,
    }).round(1)
    col_s, col_t = st.columns([1.3, 1])
    with col_s:
        fig4 = px.bar(salud.sort_values(), orientation="h", title="% de registros sin dato",
                      labels={"value": "%", "index": ""}, color_discrete_sequence=PALETA)
        fig4.update_layout(showlegend=False, height=320, xaxis_ticksuffix="%")
        st.plotly_chart(fig4, use_container_width=True)
    with col_t:
        completo = ced["SALARIO"].notna() & ced["CALIFICACION"].notna() & (ced["TIENE_EMAIL"] & ced["TIENE_CELULAR"])
        st.metric("Registros completos (ingreso + buro + contacto)", f"{int(completo.sum()):,}",
                  f"{completo.mean() * 100:.0f}% de la base")
        st.metric("Registros con algun dato critico faltante", f"{int((~completo).sum()):,}",
                  f"{(~completo).mean() * 100:.0f}% - gestion manual antes de oferta/campana")
    st.caption("La base es de clientes ya cerrados (sin prospectos), por lo que el impacto en tasa de conversion "
               "no es medible aqui; el porcentaje incompleto es el margen que hoy exige verificacion manual.")
