"""
Extract fiber routes from Southern Telecom's georeferenced PDF network maps
(southern-telecom.com/network.html) into sources/static/southern_telecom_geopdf.geojson.

Southern Telecom (a Southern Company subsidiary; Infrapedia lists its networks
as "sti-*") publishes its maps only as PDFs, but 8 of the 15 are GeoPDFs:
exported from ArcGIS with a coordinate system and real vector layers. In
every one, the fiber is the only linework drawn in a colour (blue #0000FF,
red #FF0000, green #38A800 or #0070FF). Basemap, frame and label lines are
black, white or grey, so fiber is selected by pen colour.

Needs a GDAL built with the PDF driver. The pip wheels used by the main
build don't include it, so run this with QGIS's Python (OSGeo4W shell:
`python-qgis tools/extract_geopdf.py`, or paste into the QGIS Python console).
The output is committed, so the main build doesn't need to run this.
"""

import os
import re
import sys
import tempfile
import urllib.request

from osgeo import gdal, ogr, osr

BASE = "https://www.southern-telecom.com/content/dam/southern-telecom/pdfs/"
PDFS = [  # every map linked from southern-telecom.com/network.html (2026-09)
    "STI-Marketable-Fiber-Map-2-2025.pdf", "BHM%20AL%20Fiber%202024.pdf", "MontgomerySTI.pdf",
    "Tuscaloosa.pdf", "JacksonvilleSTI.pdf", "Atlanta-Metro-Fiber-2024.pdf",
    "Downtown-Atlanta-Fiber-2024.pdf", "Atlanta-to-Jacksonsville-FL-Fiber-2024.pdf",
    "Atlanta-FL-Fiber-2024.pdf", "Eastern%20GeorgiaSTI.pdf", "MaconSTI.pdf", "SavannahSTI.pdf",
    "ValdostaSTI.pdf", "WindertoHartwellSTI.pdf", "MS-Fiber-2024.pdf",
]
FIBER_PEN = re.compile(r"PEN\(c:#(0000FF|FF0000|38A800|0070FF)\)")
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
OUT = os.path.join(HERE, "..", "sources", "static", "southern_telecom_geopdf.geojson")


def main(out_path: str = OUT) -> None:
    gdal.UseExceptions()
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    out_ds = ogr.GetDriverByName("GeoJSON").CreateDataSource(out_path)
    out = out_ds.CreateLayer("southern_telecom", wgs84, ogr.wkbLineString,
                             ["COORDINATE_PRECISION=6", "RFC7946=YES"])
    for name in ("map_file", "map_url", "pdf_layer", "pen_color"):
        out.CreateField(ogr.FieldDefn(name, ogr.OFTString))

    tmp = tempfile.mkdtemp()
    for pdf in PDFS:
        local = os.path.join(tmp, pdf.replace("%20", "_"))
        req = urllib.request.Request(BASE + pdf, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(local, "wb") as fh:
            fh.write(resp.read())
        try:
            ds = gdal.OpenEx(local, gdal.OF_VECTOR)
        except RuntimeError:
            print(f"{pdf}: not georeferenced, skipped")
            continue
        n = 0
        for i in range(ds.GetLayerCount()):
            layer = ds.GetLayer(i)
            if "Label" in layer.GetName():
                continue
            src = layer.GetSpatialRef()
            src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            to_wgs84 = osr.CoordinateTransformation(src, wgs84)
            for feat in layer:
                pen = FIBER_PEN.search(feat.GetStyleString() or "")
                geom = feat.GetGeometryRef()
                if not pen or geom is None or geom.GetGeometryName() != "LINESTRING":
                    continue
                geom = geom.Clone()
                geom.Transform(to_wgs84)
                f = ogr.Feature(out.GetLayerDefn())
                f.SetGeometry(geom)
                f.SetField("map_file", pdf.replace("%20", " "))
                f.SetField("map_url", BASE + pdf)
                f.SetField("pdf_layer", layer.GetName())
                f.SetField("pen_color", "#" + pen.group(1))
                out.CreateFeature(f)
                n += 1
        print(f"{pdf}: {n} fiber segments")
    out_ds = None
    print(f"-> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else OUT)
