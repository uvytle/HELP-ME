"""
Interstate right-of-way context layer from the US DOT's National Transportation
Atlas Database (NTAD, published by BTS on ArcGIS Online, public domain).

This is NOT fiber. It's here because US long-haul fiber largely runs inside
highway and railroad rights-of-way (Durairajan et al., "InterTubes", SIGCOMM
2015), so it shows likely corridors where no route data is published.
Railroads were deliberately left out at the user's request.
"""

from __future__ import annotations

import geopandas as gpd

from .arcgis import fetch_layer

BASE = "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services"

# ~0.0005 deg ≈ 50 m: keeps curves recognizable at state/national scale while
# cutting file size several-fold versus the full-resolution survey geometry.
GENERALIZE_DEG = 0.0005


def fetch_interstates() -> gpd.GeoDataFrame:
    gdf = fetch_layer(
        f"{BASE}/Eisenhower_Interstate_System/FeatureServer/0",
        out_fields="ROUTEID,SIGN1,LNAME,STFIPS,MILES",
        max_offset_deg=GENERALIZE_DEG,
    )
    gdf["source"] = "NTAD Eisenhower Interstate System"
    return gdf
