"""
Trace the Connecticut Education Network's fiber map (a 2018 JPG on
ctedunet.net/fiber-map) into approximate lines:
sources/static/cen_ct_traced_2018.geojson.

CEN publishes no route data, only this picture: its fiber drawn in blue over
a Google Maps basemap. It is NOT part of the route dataset the main build
produces. It's a separate, clearly-labelled approximation (Vy's call,
2026-09-25), because Connecticut is otherwise nearly empty.

How:
  1. Georeference. The basemap is Web Mercator, so pixel = scale * mercator
     + offset. The picture was resized unevenly, so x and y get their own scale.
     A first guess from the state's two northern corners is refined by fitting
     the real coastline (Census) to the map's water edge, and real interstates
     (NTAD, from data/us_fiber_network.gpkg) to the map's orange highways,
     ignoring stretches hidden under fiber. Median highway misfit: ~1 px
     (~170 m on the ground). Expect errors of up to ~1-2 km in places.
  2. Keep the pure-blue fiber pixels. Interstate shields are a greener
     steel-blue and drop out.
  3. Thin to one-pixel centrelines and vectorize (GRASS r.thin, r.to.vect),
     simplify and smooth.

Run with QGIS's Python (needs GRASS processing + scipy + PIL), e.g. paste into
the QGIS Python console. The output is committed.
"""

import json
import math
import os
import tempfile
import urllib.request

import numpy as np
import processing
from osgeo import gdal, ogr, osr
from PIL import Image
from qgis.core import QgsVectorLayer
from scipy import ndimage, optimize

IMAGE_URL = ("https://ctedunet.media.uconn.edu/wp-content/uploads/sites/2510/2018/07/"
             "cen-fiber-map-summer18.jpg")
STATES_URL = "/vsizip//vsicurl/https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip"
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
INTERSTATES = os.path.join(HERE, "..", "data", "us_fiber_network.gpkg")
OUT = os.path.join(HERE, "..", "sources", "static", "cen_ct_traced_2018.geojson")
R = 6378137.0
# CT's NW (CT/MA/NY) and NE (CT/MA/RI) corners, and where they sit in the JPG.
CORNERS = [((-73.487314, 42.049638), (155.5, 53.5)), ((-71.80065, 42.023569), (963.0, 68.0))]


def merc(lon, lat):
    return math.radians(lon) * R, R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def _points(path, where=None, bbox=None, step=None):
    ds = ogr.Open(path)
    lyr = ds.GetLayer(0) if where else ds.GetLayerByName("interstates")
    if where:
        lyr.SetAttributeFilter(where)
    if bbox:
        lyr.SetSpatialFilterRect(*bbox)
    pts = []
    for f in lyr:
        g = f.GetGeometryRef().Clone()
        if step:
            g.Segmentize(step)
        stack = [g]
        while stack:
            h = stack.pop()
            if h.GetGeometryCount():
                stack += [h.GetGeometryRef(i) for i in range(h.GetGeometryCount())]
            else:
                pts += [merc(*h.GetPoint_2D(j)) for j in range(h.GetPointCount())]
    return np.array(pts)


def georeference(rgb):
    r, g, b = (rgb[..., i] for i in range(3))
    h, w = r.shape
    water = ndimage.binary_opening((abs(r - 198) < 14) & (abs(g - 227) < 12) & (b > 240))
    lab, n = ndimage.label(water)
    sizes = ndimage.sum(water, lab, range(1, n + 1))
    sound = ndimage.binary_fill_holes(ndimage.binary_closing(
        np.isin(lab, 1 + np.where(sizes > 20000)[0]), iterations=3))
    dist_coast = ndimage.distance_transform_edt(~(sound ^ ndimage.binary_erosion(sound)))
    orange = (r > 215) & (g > 120) & (g < 205) & (b < 120) & (r - b > 120)
    dist_road = ndimage.distance_transform_edt(~orange)
    fiber_near = ndimage.binary_dilation(fiber_mask(rgb), iterations=3)

    border = _points(STATES_URL, where="STUSPS IN ('CT','RI','MA','NY')")
    lat = np.degrees(2 * np.arctan(np.exp(border[:, 1] / R)) - math.pi / 2)
    lon = np.degrees(border[:, 0] / R)
    coast = border[(lat < 41.35) & (lat > 40.9) & (lon > -73.65) & (lon < -71.9)]
    roads = _points(INTERSTATES, bbox=(-73.9, 40.9, -71.5, 42.2), step=0.002)

    def proj(p, a):
        return p[0] * a[:, 0] + p[2], p[3] - p[1] * a[:, 1]

    def misfit(p, a, dist, cap):
        x, y = proj(p, a)
        ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        d = np.full(len(a), float(cap))
        d[ok] = np.minimum(dist[y[ok].astype(int), x[ok].astype(int)], cap)
        return d

    (x1, y1), (u1, v1) = merc(*CORNERS[0][0]), CORNERS[0][1]
    (x2, _), (u2, _) = merc(*CORNERS[1][0]), CORNERS[1][1]
    s = (u2 - u1) / (x2 - x1)
    y_top = y1

    def from_sy(sy, dy):
        return np.array([s, sy, u1 - s * x1, v1 + dy + sy * y_top])

    # Vertical scale first (coast only), then everything together.
    sy, dy = min(((sy, dy) for sy in s * np.linspace(0.75, 1.05, 61) for dy in range(-6, 7)),
                 key=lambda t: misfit(from_sy(*t), coast, dist_coast, 20).mean())
    p = from_sy(*optimize.minimize(lambda v: misfit(from_sy(*v), coast, dist_coast, 20).mean(),
                                   [sy, dy], method="Nelder-Mead").x)
    corners = [(merc(*ll), px) for ll, px in CORNERS]

    def corner_cost(p):
        return np.mean([math.hypot(p[0] * X + p[2] - u, p[3] - p[1] * Y - v) for (X, Y), (u, v) in corners])

    p = optimize.minimize(lambda p: misfit(p, coast, dist_coast, 20).mean() + 0.5 * corner_cost(p), p,
                          method="Nelder-Mead", options={"maxiter": 8000, "xatol": 1e-10, "fatol": 1e-5}).x
    x, y = proj(p, roads)
    ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    visible = np.zeros(len(roads), bool)
    visible[ok] = ~fiber_near[y[ok].astype(int), x[ok].astype(int)]
    roads = roads[visible]
    p = optimize.minimize(lambda p: misfit(p, coast, dist_coast, 20).mean() + misfit(p, roads, dist_road, 12).mean(),
                          p, method="Nelder-Mead", options={"maxiter": 8000, "xatol": 1e-10, "fatol": 1e-5}).x
    print(f"  highway misfit median {np.median(misfit(p, roads, dist_road, 99)):.1f} px, "
          f"coast {np.median(misfit(p, coast, dist_coast, 99)):.1f} px")
    return p


def fiber_mask(rgb):
    r, g, b = (rgb[..., i] for i in range(3))
    # CEN's pure blue has g <= r; interstate shields are a greener steel-blue.
    m = (b > 150) & (r < 120) & (g < 120) & (b - r > 90) & (g - r < 18)
    m = ndimage.binary_closing(m, structure=np.ones((3, 3)))
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    return np.isin(lab, 1 + np.where(ndimage.sum(m, lab, range(1, n + 1)) >= 12)[0])


def main(out_path=OUT):
    gdal.UseExceptions()
    tmp = tempfile.mkdtemp()
    jpg = os.path.join(tmp, "cen.jpg")
    urllib.request.urlretrieve(IMAGE_URL, jpg)
    rgb = np.asarray(Image.open(jpg).convert("RGB")).astype(int)
    sx, sy, tx, ty = georeference(rgb)
    mask = fiber_mask(rgb)
    h, w = mask.shape
    tif = os.path.join(tmp, "mask.tif")
    ds = gdal.GetDriverByName("GTiff").Create(tif, w, h, 1, gdal.GDT_Byte)
    ds.SetGeoTransform([-tx / sx, 1 / sx, 0, ty / sy, 0, -1 / sy])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(mask.astype(np.uint8))
    ds.GetRasterBand(1).SetNoDataValue(0)
    ds = None

    thin = processing.run("grass:r.thin", {"input": tif, "iterations": 200,
                                           "output": os.path.join(tmp, "thin.tif")})["output"]
    raw = processing.run("grass:r.to.vect", {"input": thin, "type": 0, "column": "value",
                                             "output": os.path.join(tmp, "raw.gpkg")})["output"]
    lines = processing.run("native:simplifygeometries", {"INPUT": raw, "METHOD": 0, "TOLERANCE": 120,
                                                         "OUTPUT": "memory:"})["OUTPUT"]
    lines = processing.run("native:smoothgeometry", {"INPUT": lines, "ITERATIONS": 2, "OFFSET": 0.25,
                                                     "MAX_ANGLE": 180, "OUTPUT": "memory:"})["OUTPUT"]
    lines = processing.run("native:reprojectlayer", {"INPUT": lines, "TARGET_CRS": "EPSG:4326",
                                                     "OUTPUT": "memory:"})["OUTPUT"]
    feats = [{"type": "Feature", "properties": {},
              "geometry": json.loads(f.geometry().asJson(6))} for f in lines.getFeatures()]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)
    print(f"  {len(feats)} traced lines -> {out_path}")


if __name__ == "__main__" or "__file__" not in globals():
    main()
