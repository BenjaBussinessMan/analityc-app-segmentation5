"""Tema visual compartido por toda la app (paleta + plantilla de Plotly) y las
funciones de gráficos genéricos (Sankey, capa base del mapa coroplético).

Todas las tabs importan `PALETA_TEMA` (vía `app/data.py`) en vez de definir una
propia, para que colores y tipografía sean consistentes en toda la app.
"""
import plotly.graph_objects as go
import plotly.io as pio

PALETA_TEMA = ["#2F8FFF", "#FFA63D", "#1BC5A8", "#FF6B6B", "#8B7FE8", "#4ECDC4", "#FFB84D", "#6C7A96"]
COLOR_TEXTO = "#2E3348"

pio.templates["dashboard"] = go.layout.Template(
    layout=go.Layout(
        bargap=0.25, bargroupgap=0.12,
        colorway=PALETA_TEMA,
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font=dict(family="Segoe UI, Arial, sans-serif", color=COLOR_TEXTO, size=12),
        title=dict(font=dict(size=16, color=COLOR_TEXTO)),
    )
)
pio.templates.default = "plotly+dashboard"

# Color de "sin datos" para las provincias/cantones que no tienen ningun cliente
# (compartido por las tabs que dibujan el mapa coropletico por canton).
COLOR_SIN_DATOS = "#e8e8e8"


def sankey(df, cols, titulo, col_labels=None):
    """Diagrama de flujo (Sankey) genérico entre columnas categóricas consecutivas de `df`.
    `col_labels` (opcional): nombres legibles de cada columna de `cols`, mostrados como
    encabezado sobre cada etapa del diagrama para identificar a qué variable corresponde."""
    col_labels = list(col_labels) if col_labels else list(cols)
    d = df[cols].astype(str)
    d = d.replace({"nan": "Sin dato", "NaN": "Sin dato", "None": "Sin dato"})
    labels, stage_of, idx = [], [], {}

    def _nid(col_i, val):
        key = (col_i, val)
        if key not in idx:
            idx[key] = len(labels)
            labels.append(val)
            stage_of.append(col_i)
        return idx[key]

    src, tgt, val = [], [], []
    for i, (a, b) in enumerate(zip(cols, cols[1:])):
        g = d.groupby([a, b]).size().reset_index(name="n")
        for _, row in g.iterrows():
            src.append(_nid(i, row[a]))
            tgt.append(_nid(i + 1, row[b]))
            val.append(int(row["n"]))

    n_stages = len(cols)
    paleta = PALETA_TEMA
    # x fijo por etapa (con un pequeño margen en los extremos para que las etiquetas de la
    # primera/ultima columna no se corten contra el borde); la y la ajusta Plotly solo
    # (arrangement="snap") para evitar que los nodos se encimen.
    xs = [0.001 if s == 0 else 0.999 if s == n_stages - 1 else s / (n_stages - 1) for s in stage_of]

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=labels, x=xs, pad=18, thickness=18,
            color=[paleta[s % len(paleta)] for s in stage_of],
            line=dict(color="rgba(0,0,0,0.3)", width=0.5),
        ),
        link=dict(source=src, target=tgt, value=val, color="rgba(160,160,160,0.35)"),
        textfont=dict(size=14, color="#1a1a1a", family="Arial, sans-serif"),
    ))
    # Encabezados por etapa (arriba de cada columna de nodos) para identificar a que
    # variable corresponde cada segmento del diagrama.
    def _xanchor(s):
        if s == 0:
            return "left"
        if s == n_stages - 1:
            return "right"
        return "center"

    annotations = [
        dict(x=s / (n_stages - 1) if n_stages > 1 else 0.5, y=1.06, xref="paper", yref="paper",
             xanchor=_xanchor(s), text=f"<b>{lbl}</b>", showarrow=False, font=dict(size=13, color="#333"))
        for s, lbl in enumerate(col_labels)
    ]
    fig.update_layout(title_text=titulo, height=520, annotations=annotations,
                      margin=dict(t=100))
    return fig


def base_geojson(geojson_ec, todos_cantones):
    """Capa base: TODOS los cantones del GeoJSON en gris, para que el contorno
    completo del pais (y todas las provincias) se vea siempre, tenga o no datos."""
    return go.Choropleth(
        geojson=geojson_ec, locations=todos_cantones, z=[0] * len(todos_cantones),
        featureidkey="properties.DPA_DESCAN",
        colorscale=[[0, COLOR_SIN_DATOS], [1, COLOR_SIN_DATOS]],
        showscale=False, marker_line_color="white", marker_line_width=0.3,
        hovertemplate="%{location}<br>Sin datos<extra></extra>",
    )
