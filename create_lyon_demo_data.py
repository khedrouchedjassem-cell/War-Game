"""Create a small, runnable Lyon demonstration dataset for Wargame Simulation.

Vector features are fetched from OpenStreetMap.  The elevation raster is a
synthetic demonstration surface calibrated to the broad west/east relief of
Lyon; replace it with an official MNT for analytical use.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Polygon


ROOT = Path(__file__).parent
OUTPUT = ROOT / "data"
# Around central Lyon: approximately 5 x 5 km.
BBOX = (45.735, 4.790, 45.780, 4.855)  # south, west, north, east
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def fetch_osm() -> list[dict]:
    south, west, north, east = BBOX
    query = f"""
    [out:json][timeout:120];
    (
      way[highway]({south},{west},{north},{east});
      way[building]({south},{west},{north},{east});
      way[waterway]({south},{west},{north},{east});
      way[natural=water]({south},{west},{north},{east});
      way[landuse]({south},{west},{north},{east});
      way[leisure=park]({south},{west},{north},{east});
      way[natural~"wood|scrub|grassland"]({south},{west},{north},{east});
    );
    out geom;
    """
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={"User-Agent": "Wargame-Lyon-demo-data/1.0"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)["elements"]


def geometry(element: dict):
    points = [(point["lon"], point["lat"]) for point in element.get("geometry", [])]
    if len(points) < 2:
        return None
    is_closed = len(points) >= 4 and points[0] == points[-1]
    return Polygon(points) if is_closed else LineString(points)


def write_layer(path: Path, features: list[dict], expected_type: str) -> None:
    records = []
    for feature in features:
        geom = geometry(feature)
        if geom is None or geom.geom_type != expected_type:
            continue
        tags = feature.get("tags", {})
        records.append({
            "kind": tags.get("highway") or tags.get("waterway") or tags.get("landuse")
                    or tags.get("natural") or tags.get("leisure") or "building",
            "name": tags.get("name", ""),
            "geometry": geom,
        })
    if not records:
        return
    gpd.GeoDataFrame(records, crs="EPSG:4326").to_crs("EPSG:2154").to_file(path)


def write_demo_dem(path: Path) -> None:
    # The raster is deliberately modest so loading remains fast with the
    # project's default 2-km hexagons.
    west, south, east, north = (838000.0, 6512000.0, 845000.0, 6519000.0)
    pixel = 25.0
    width = height = int((east - west) / pixel)
    x, y = np.meshgrid(np.linspace(0, 1, width), np.linspace(0, 1, height))
    elevation = 165 + 105 * (1 - x) + 18 * np.sin(5 * y) + 8 * np.cos(7 * x * y)
    transform = from_origin(west, north, pixel, pixel)
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:2154", transform=transform, nodata=-9999.0,
    ) as dataset:
        dataset.write(elevation.astype("float32"), 1)


def main() -> None:
    if OUTPUT.exists() and any(path.is_file() for path in OUTPUT.rglob("*")):
        raise SystemExit(
            "Le dossier data existe deja. Renommez-le ou supprimez-le avant de lancer ce script."
        )
    dem_dir = OUTPUT / "DEM"
    vector_dir = OUTPUT / "Vector"
    dem_dir.mkdir(parents=True, exist_ok=True)
    vector_dir.mkdir(exist_ok=True)

    print("Téléchargement des objets OpenStreetMap autour de Lyon...")
    elements = fetch_osm()
    layers = {"roads": [], "buildings": [], "water_ways": [], "water_zones": [], "landuse": []}
    for element in elements:
        tags = element.get("tags", {})
        if "highway" in tags:
            layers["roads"].append(element)
        elif "building" in tags:
            layers["buildings"].append(element)
        elif "waterway" in tags:
            layers["water_ways"].append(element)
        elif tags.get("natural") == "water":
            layers["water_zones"].append(element)
        else:
            layers["landuse"].append(element)

    layer_types = {
        "roads": "LineString",
        "buildings": "Polygon",
        "water_ways": "LineString",
        "water_zones": "Polygon",
        "landuse": "Polygon",
    }
    for name, features in layers.items():
        write_layer(vector_dir / f"{name}.shp", features, layer_types[name])
    write_demo_dem(dem_dir / "DEM_Projected.tif")
    (OUTPUT / "README.txt").write_text(
        "Jeu de demonstration Lyon. Les couches vectorielles proviennent "
        "d'OpenStreetMap. Le relief est synthetique et doit etre remplace par "
        "un MNT officiel pour une analyse geographique reelle.\n",
        encoding="utf-8",
    )
    print(f"Dossier cree : {OUTPUT}")


if __name__ == "__main__":
    main()
