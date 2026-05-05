"""
Brisbane Real-Time Bus Tracker
================================
Dash + Plotly + OpenStreetMap dashboard that tracks live bus positions
from the Translink GTFS-RT feed for South East Queensland.

INSTALLATION
------------
pip install dash plotly gtfs-realtime-bindings requests pandas

RUN
---
python brisbane_bus_tracker.py
Then open http://127.0.0.1:8050 in your browser.

DATA SOURCE
-----------
Translink GTFS-RT SEQ Bus Vehicle Positions (no API key required)
https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions/Bus
Licensed under Creative Commons Attribution 4.0
"""

import requests
import pandas as pd
from datetime import datetime

from google.transit import gtfs_realtime_pb2

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
GTFS_RT_BUS_URL = (
    "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions/Bus"
)
BRISBANE_LAT = -27.4698
BRISBANE_LON = 153.0251
REFRESH_INTERVAL_MS = 10_000  # 10 seconds

# ─────────────────────────────────────────────
# Data fetching
# ─────────────────────────────────────────────

def fetch_vehicle_positions() -> pd.DataFrame:
    """Fetch live bus positions from Translink GTFS-RT and return a DataFrame."""
    try:
        response = requests.get(GTFS_RT_BUS_URL, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[ERROR] Failed to fetch GTFS-RT feed: {exc}")
        return pd.DataFrame()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    records = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        pos = v.position
        trip = v.trip

        records.append(
            {
                "vehicle_id": v.vehicle.id or entity.id,
                "label": v.vehicle.label or v.vehicle.id or entity.id,
                "route_id": trip.route_id,
                "trip_id": trip.trip_id,
                "lat": pos.latitude,
                "lon": pos.longitude,
                "speed_kmh": round(pos.speed * 3.6, 1) if pos.speed else None,
                "bearing": pos.bearing if pos.bearing else None,
                "timestamp": (
                    datetime.utcfromtimestamp(v.timestamp).strftime("%H:%M:%S UTC") #DeprecationWarning: datetime.datetime.utcfromtimestamp() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.fromtimestamp(timestamp, datetime.UTC).
                    if v.timestamp
                    else "—"
                ),
            }
        )

    df = pd.DataFrame(records)

    # Drop rows with invalid coords
    if not df.empty:
        df = df[(df.lat != 0) & (df.lon != 0)].copy()

    return df


def get_route_options(df: pd.DataFrame) -> list[dict]:
    """Return sorted list of route IDs as dropdown options."""
    if df.empty or "route_id" not in df.columns:
        return []
    routes = sorted(df["route_id"].dropna().unique())
    return [{"label": r, "value": r} for r in routes if r]


# ─────────────────────────────────────────────
# Map builder
# ─────────────────────────────────────────────

def build_map(df: pd.DataFrame, selected_routes: list[str]) -> go.Figure:
    """Build a Plotly scatter_mapbox figure for the given bus positions.
    The OSM map is always rendered regardless of whether df has data."""
    fig = go.Figure()
 
    if not df.empty:
        filtered = df[df["route_id"].isin(selected_routes)] if selected_routes else df
 
        if filtered.empty:
            filtered = df  # fall back to all buses if filter yields nothing
 
        # Colour buses by route
        unique_routes = filtered["route_id"].unique()
        palette = [
            "#E63946", "#2196F3", "#4CAF50", "#FF9800", "#9C27B0",
            "#00BCD4", "#F44336", "#8BC34A", "#FF5722", "#3F51B5",
            "#FFC107", "#009688", "#E91E63", "#607D8B", "#CDDC39",
        ]
        route_colour = {
            r: palette[i % len(palette)] for i, r in enumerate(unique_routes)
        }
        colours = filtered["route_id"].map(route_colour)
 
        hover_text = (
            "<b>Route " + filtered["route_id"].astype(str) + "</b><br>"
            + "Vehicle: " + filtered["label"].astype(str) + "<br>"
            + "Speed: " + filtered["speed_kmh"].apply(
                lambda s: f"{s} km/h" if pd.notna(s) else "—"
            ) + "<br>"
            + "Updated: " + filtered["timestamp"].astype(str)
        )
        # DeprecationWarning: *scattermapbox* is deprecated! Use *scattermap* instead.
        fig.add_trace(
            go.Scattermapbox(
                lat=filtered["lat"],
                lon=filtered["lon"],
                mode="markers",
                marker=go.scattermapbox.Marker(
                    size=12,
                    color=colours,
                    opacity=0.85,
                ),
                text=hover_text,
                hoverinfo="text",
                customdata=filtered["route_id"],
                name="Buses",
            )
        )
 
    # Centre map on selected buses or Brisbane CBD
    if not df.empty and selected_routes:
        subset = df[df["route_id"].isin(selected_routes)]
        if not subset.empty:
            centre_lat = subset["lat"].mean()
            centre_lon = subset["lon"].mean()
            zoom = 12
        else:
            centre_lat, centre_lon, zoom = BRISBANE_LAT, BRISBANE_LON, 11
    else:
        centre_lat, centre_lon, zoom = BRISBANE_LAT, BRISBANE_LON, 11
 
    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=centre_lat, lon=centre_lon),
            zoom=zoom,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#1a1a2e",
        showlegend=False,
        uirevision="map",  # keep user pan/zoom across refreshes
    )
    return fig


# ─────────────────────────────────────────────
# Dash App layout
# ─────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title="Brisbane Live Bus Tracker",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

app.layout = html.Div(
    style={
        "fontFamily": "'Segoe UI', Arial, sans-serif",
        "backgroundColor": "#1a1a2e",
        "color": "#e0e0e0",
        "height": "100vh",
        "display": "flex",
        "flexDirection": "column",
        "overflow": "hidden",
    },
    children=[
        # ── Header ──────────────────────────────────────────
        html.Div(
            style={
                "backgroundColor": "#16213e",
                "padding": "12px 20px",
                "display": "flex",
                "alignItems": "center",
                "gap": "16px",
                "borderBottom": "2px solid #0f3460",
                "flexShrink": 0,
            },
            children=[
                html.Div("🚌", style={"fontSize": "28px"}),
                html.Div(
                    children=[
                        html.H1(
                            "Brisbane Live Bus Tracker",
                            style={"margin": 0, "fontSize": "20px", "color": "#e94560"},
                        ),
                        html.Div(
                            "Powered by Translink GTFS-RT · OpenStreetMap",
                            style={"fontSize": "11px", "color": "#888", "marginTop": "2px"},
                        ),
                    ]
                ),
                # spacer
                html.Div(style={"flex": 1}),
                # Status badge
                html.Div(
                    id="status-badge",
                    style={
                        "fontSize": "12px",
                        "padding": "4px 12px",
                        "borderRadius": "12px",
                        "backgroundColor": "#0f3460",
                        "color": "#aaa",
                    },
                    children="⏳ Loading…",
                ),
            ],
        ),

        # ── Controls bar ─────────────────────────────────────
        html.Div(
            style={
                "backgroundColor": "#16213e",
                "padding": "10px 20px",
                "display": "flex",
                "alignItems": "center",
                "gap": "12px",
                "flexWrap": "wrap",
                "flexShrink": 0,
                "borderBottom": "1px solid #0f3460",
            },
            children=[
                html.Label(
                    "Route(s):",
                    style={"fontWeight": "bold", "color": "#e94560", "whiteSpace": "nowrap"},
                ),
                dcc.Dropdown(
                    id="route-dropdown",
                    options=[],
                    value=[],
                    multi=True,
                    placeholder="Select one or more routes…",
                    style={
                        "flex": "1",
                        "minWidth": "260px",
                        "backgroundColor": "#0f3460",
                        "color": "#fff",
                        "border": "none",
                        "borderRadius": "6px",
                    },
                    className="dark-dropdown",
                ),
                html.Button(
                    "Show All Routes",
                    id="btn-all-routes",
                    n_clicks=0,
                    style={
                        "padding": "8px 16px",
                        "backgroundColor": "#e94560",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "6px",
                        "cursor": "pointer",
                        "fontWeight": "bold",
                        "whiteSpace": "nowrap",
                    },
                ),
                html.Button(
                    "Clear",
                    id="btn-clear",
                    n_clicks=0,
                    style={
                        "padding": "8px 16px",
                        "backgroundColor": "#333",
                        "color": "#ccc",
                        "border": "1px solid #555",
                        "borderRadius": "6px",
                        "cursor": "pointer",
                        "whiteSpace": "nowrap",
                    },
                ),
                html.Div(
                    id="bus-count",
                    style={"color": "#aaa", "fontSize": "13px", "whiteSpace": "nowrap"},
                ),
            ],
        ),

        # ── Map ──────────────────────────────────────────────
        html.Div(
            style={"flex": 1, "position": "relative", "overflow": "hidden"},
            children=[
                dcc.Graph(
                    id="bus-map",
                    config={"scrollZoom": True, "displayModeBar": False},
                    style={"height": "100%", "width": "100%"},
                ),
            ],
        ),

        # ── Hidden stores & timers ────────────────────────────
        dcc.Store(id="store-df-json"),          # raw fetched data as JSON
        dcc.Store(id="store-all-routes"),        # list of all route IDs
        dcc.Interval(
            id="interval-refresh",
            interval=REFRESH_INTERVAL_MS,
            n_intervals=0,
        ),
    ],
)

# ─────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────

@app.callback(
    Output("store-df-json", "data"),
    Output("store-all-routes", "data"),
    Output("status-badge", "children"),
    Output("status-badge", "style"),
    Input("interval-refresh", "n_intervals"),
)
def refresh_data(n_intervals):
    """Fetch fresh GTFS-RT data and store it."""
    df = fetch_vehicle_positions()

    base_style = {
        "fontSize": "12px",
        "padding": "4px 12px",
        "borderRadius": "12px",
    }

    if df.empty:
        status_text = "❌ No data"
        style = {**base_style, "backgroundColor": "#5a1a1a", "color": "#ff6b6b"}
        return None, [], status_text, style

    all_routes = sorted(df["route_id"].dropna().unique().tolist())
    now = datetime.now().strftime("%H:%M:%S")
    status_text = f"✅ {len(df)} buses · {now}"
    style = {**base_style, "backgroundColor": "#1a4a2a", "color": "#6bff9e"}
    with open('json_sample.txt', 'w') as file:
        file.write(str(df.to_dict(orient="records")))
    return df.to_dict(orient="records"), all_routes, status_text, style


@app.callback(
    Output("route-dropdown", "options"),
    Input("store-all-routes", "data"),
)
def update_route_options(all_routes):
    if not all_routes:
        return []
    return [{"label": r, "value": r} for r in all_routes]


@app.callback(
    Output("route-dropdown", "value"),
    Input("btn-all-routes", "n_clicks"),
    Input("btn-clear", "n_clicks"),
    State("store-all-routes", "data"),
    State("route-dropdown", "value"),
    prevent_initial_call=True,
)
def handle_buttons(n_all, n_clear, all_routes, current_value):
    ctx = callback_context
    if not ctx.triggered:
        return current_value or []
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if btn_id == "btn-all-routes":
        return all_routes or []
    return []  # clear


@app.callback(
    Output("bus-map", "figure"),
    Output("bus-count", "children"),
    Input("route-dropdown", "value"),
    Input("store-df-json", "data"),
)
def update_map(selected_routes, df_json):
    df = pd.DataFrame.from_records(df_json) if df_json else pd.DataFrame()

    routes = selected_routes or []

    if df.empty:
        count_text = "⏳ Waiting for data…"
    elif routes:
        display_df = df[df["route_id"].isin(routes)]
        count_text = (
            f"🚌 {len(display_df)} bus(es) on route(s): {', '.join(routes)}"
            if not display_df.empty
            else f"⚠️ No active buses for route(s): {', '.join(routes)}"
        )
    else:
        count_text = f"🚌 {len(df)} buses across all routes (no filter applied)"

    fig = build_map(df, routes)
    return fig, count_text


# ─────────────────────────────────────────────
# Custom CSS (injected via index_string)
# ─────────────────────────────────────────────

app.index_string = """
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        body { margin: 0; overflow: hidden; }

        /* Dark dropdown styling */
        .dark-dropdown .Select-control {
            background-color: #0f3460 !important;
            border-color: #e94560 !important;
            color: #fff !important;
        }
        .dark-dropdown .Select-menu-outer {
            background-color: #16213e !important;
            border-color: #0f3460 !important;
            z-index: 9999 !important;
        }
        .dark-dropdown .Select-option {
            background-color: #16213e !important;
            color: #ddd !important;
        }
        .dark-dropdown .Select-option:hover,
        .dark-dropdown .Select-option.is-focused {
            background-color: #0f3460 !important;
            color: #fff !important;
        }
        .dark-dropdown .Select-value-label { color: #fff !important; }
        .dark-dropdown .Select-placeholder { color: #888 !important; }
        .dark-dropdown .Select-input input { color: #fff !important; }
        .dark-dropdown .Select-arrow { border-top-color: #e94560 !important; }
        .dark-dropdown .Select-multi-value-wrapper .Select-value {
            background-color: #e94560 !important;
            border-color: #e94560 !important;
            color: #fff !important;
        }
        .dark-dropdown .Select-value-icon { border-right-color: rgba(255,255,255,0.3) !important; }
        .dark-dropdown .Select-value-icon:hover { background-color: rgba(0,0,0,0.2) !important; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
"""

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Brisbane Live Bus Tracker")
    print("  Open http://127.0.0.1:8050 in your browser")
    print("  Buses refresh every 10 seconds automatically")
    print("=" * 60)
    app.run(debug=False, port=8050)
