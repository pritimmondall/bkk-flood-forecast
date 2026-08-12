#!/usr/bin/env python3
"""
Fetch Bangkok road centrelines from OpenStreetMap.

    python scripts/fetch_osm_roads.py
    python scripts/fetch_osm_roads.py --with-service   # include sois/driveways
    python scripts/fetch_osm_roads.py --grid 6         # smaller chunks if it stalls

Writes `data/gis/osm_roads.gpkg`, ODbL licensed.

WHY. `DTM_1M` is not bare earth in dense districts — buildings were stripped from
a surface model and the holes interpolated, so the surface drifts up toward roof
height over large footprints. `terrain.ground_mask()` recovers the low surface
from the raster itself and works offline, but it cannot tell a street from a
canal or a car park. Road centrelines can, and they produce the **road**
elevation the supervisor's `Flood Depth = Water Level - Road Elevation` formula
asks for.

THIS IS OPTIONAL. `ground_mask()` already fixes the contamination (Bang Rak
4.54 -> 1.25 m) and notebook 03 falls back to it automatically. If Overpass will
not cooperate, skip this and move on.

--------------------------------------------------------------------------
WHAT WENT WRONG THE FIRST TIME, AND WHAT CHANGED
--------------------------------------------------------------------------
The first version asked for every road in Bangkok in one request and got three
different failures in a row:

    overpass-api.de      HTTP 406   rejects the default python-requests
                                    User-Agent; Overpass wants to know who is
                                    calling and returns "Not Acceptable" if not
    kumi.systems         HTTP 429   rate limited
    overpass.osm.ch      0 ways     the request was simply too big -- Bangkok has
                                    hundreds of thousands of ways once `service`
                                    roads are included, and a single query over a
                                    60 x 50 km box does not complete

All three are the same underlying mistake: asking a free, shared, volunteer-run
service for everything at once, anonymously. So now it:

  * sends a real User-Agent identifying the project,
  * splits the city into a grid and asks for one tile at a time,
  * pauses between tiles and backs off on 429,
  * saves after every tile, so a failure half way keeps what it has,
  * merges with any existing file rather than overwriting, because a different
    subset of tiles fails on every run and a re-run must never lose coverage,
  * excludes `service` roads by default (they are the bulk of the volume and are
    mostly private driveways),
  * prints Overpass's own `remark` field, which is where it explains itself.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

# Bangkok, from data/gis/bangkok_districts.geojson (notebook 00 measures it).
SOUTH, WEST, NORTH, EAST = 13.4934, 100.3279, 13.9546, 100.9385

BASE_TYPES = ("primary|secondary|tertiary|residential|unclassified|"
              "living_street|primary_link|secondary_link|tertiary_link")
SERVICE_TYPES = BASE_TYPES + "|service|pedestrian"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# Overpass asks callers to identify themselves. Anonymous requests get 406.
HEADERS = {
    "User-Agent": "bkk-flood-forecast/3.0 (BMA urban flood research; contact via repo)",
    "Accept": "application/json",
}

OUT = Path("data/gis/osm_roads.gpkg")


def tile_query(bbox, types: str) -> str:
    s, w, n, e = bbox
    return (f'[out:json][timeout:180];'
            f'way["highway"~"^({types})$"]({s:.4f},{w:.4f},{n:.4f},{e:.4f});'
            f'out geom;')


def fetch_tile(bbox, types, tries: int = 3):
    """One tile, trying each endpoint. Returns elements, or None."""
    for attempt in range(tries):
        for url in ENDPOINTS:
            try:
                r = requests.post(url, data={"data": tile_query(bbox, types)},
                                  headers=HEADERS, timeout=240)
                if r.status_code == 429:
                    time.sleep(10 * (attempt + 1))
                    continue
                if r.status_code != 200:
                    print(f"      {url.split('/')[2]}: HTTP {r.status_code}")
                    continue
                payload = r.json()
                if payload.get("remark"):
                    # Overpass explains itself here: timeouts, memory limits.
                    print(f"      remark: {payload['remark'][:120]}")
                    continue
                return payload.get("elements", [])
            except Exception as exc:  # noqa: BLE001
                print(f"      {url.split('/')[2]}: {str(exc)[:80]}")
        time.sleep(5 * (attempt + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", type=int, default=4,
                    help="split the city into GRID x GRID tiles (default 4)")
    ap.add_argument("--with-service", action="store_true",
                    help="include service roads and sois (far more data)")
    ap.add_argument("--pause", type=float, default=4.0,
                    help="seconds between tiles; be kind to a free service")
    args = ap.parse_args()

    try:
        import geopandas as gpd
        from shapely.geometry import LineString
    except ImportError:
        raise SystemExit("pip install geopandas shapely")

    types = SERVICE_TYPES if args.with_service else BASE_TYPES
    n = args.grid
    dlat = (NORTH - SOUTH) / n
    dlon = (EAST - WEST) / n

    print("Fetching Bangkok road centrelines from OpenStreetMap")
    print(f"  area   : {SOUTH}, {WEST} -> {NORTH}, {EAST}")
    print(f"  tiles  : {n} x {n} = {n * n}")
    print(f"  types  : {'base + service' if args.with_service else 'base only'}")
    print()

    rows, failed = [], []
    for i in range(n):
        for j in range(n):
            bbox = (SOUTH + i * dlat, WEST + j * dlon,
                    SOUTH + (i + 1) * dlat, WEST + (j + 1) * dlon)
            label = f"tile {i * n + j + 1}/{n * n}"
            print(f"  {label} ...", flush=True)
            elements = fetch_tile(bbox, types)
            if elements is None:
                print(f"    {label} FAILED")
                failed.append(bbox)
                continue

            before = len(rows)
            for el in elements:
                geom = el.get("geometry") or []
                if len(geom) < 2:
                    continue
                tags = el.get("tags") or {}
                rows.append({
                    "osm_id": el.get("id"),
                    "highway": tags.get("highway"),
                    "name": tags.get("name"),
                    # A viaduct is not the ground surface, and sampling terrain
                    # under one would put back exactly the contamination this
                    # whole exercise removes.
                    "bridge": tags.get("bridge") is not None,
                    "tunnel": tags.get("tunnel") is not None,
                    "geometry": LineString([(p["lon"], p["lat"]) for p in geom]),
                })
            print(f"    +{len(rows) - before:,} ways  (total {len(rows):,})")
            time.sleep(args.pause)

    if not rows:
        raise SystemExit(
            "\nNo roads retrieved from any tile.\n"
            "This is not fatal. terrain.ground_mask() already fixes the DTM\n"
            "contamination and notebook 03 falls back to it automatically.\n"
            "If you want roads: try --grid 8, or download a Geofabrik Thailand\n"
            "extract and clip it offline."
        )

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")

    # MERGE WITH WHAT IS ALREADY THERE, never overwrite.
    # Overpass returns 504 on a different subset of tiles every run, so a second
    # attempt can easily retrieve FEWER roads than the first. Overwriting would
    # then quietly shrink the coverage — the first run got 165,868 segments, the
    # second 196,720, and had the second failed differently it could have gone
    # the other way with no sign that anything was lost.
    previous = 0
    if OUT.exists():
        old_gdf = gpd.read_file(OUT)
        previous = len(old_gdf)
        gdf = gpd.GeoDataFrame(
            __import__("pandas").concat([old_gdf, gdf], ignore_index=True),
            crs="EPSG:4326")

    gdf = gdf.drop_duplicates(subset="osm_id").reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GPKG")
    if previous:
        print()
        print(f"  merged with {previous:,} existing segments "
              f"-> {len(gdf) - previous:+,} new")

    print()
    print(f"  {len(gdf):,} unique road segments -> {OUT}")
    print(f"  on bridges: {int(gdf.bridge.sum()):,}   in tunnels: {int(gdf.tunnel.sum()):,}")
    if failed:
        print(f"  WARNING: {len(failed)} tile(s) failed -- coverage is incomplete.")
        print("           Re-run to retry; completed tiles are already saved.")
    print()
    for kind, count in gdf.highway.value_counts().head(10).items():
        print(f"    {kind:<18} {count:>7,}")
    # ---------------------------------------------------------------------
    # Check the coverage that actually matters, and say plainly whether to
    # run this again. A tile failing is not the question -- a DISTRICT having
    # no roads is. The first run lost the tile covering central Bangkok, which
    # left nine districts empty, and nothing in the output said so.
    # ---------------------------------------------------------------------
    try:
        sys.path.insert(0, str(Path("src")))
        from bkkflood import terrain as T
        from bkkflood.config import load_config

        d = T.districts()
        d["km2"] = d.area / 1e6
        usable = gdf[~gdf.bridge & ~gdf.tunnel].to_crs(load_config()["terrain"]["working_crs"])
        joined = gpd.sjoin(usable[["geometry"]], d[["name", "geometry"]],
                           how="inner", predicate="intersects")
        counts = joined.groupby("name").size().rename("segments")
        cov = (d[["name", "km2"]].merge(counts.reset_index(), on="name", how="left")
                                 .fillna({"segments": 0}))
        # DENSITY, not raw count. An absolute threshold flags small districts
        # forever: Samphanthawong is 1.4 km2, so 185 segments is 129 per km2 --
        # denser than the city median -- yet a "< 200 segments" rule called it
        # thin and told you to run this again, permanently.
        cov["per_km2"] = cov.segments / cov.km2
        empty = sorted(cov.loc[cov.segments == 0, "name"])
        sparse = cov[(cov.segments > 0) & (cov.per_km2 < 20)].sort_values("per_km2")

        print()
        print(f"  district coverage : {int((cov.segments > 0).sum())} of {len(d)}")
        print(f"  median density    : {cov.per_km2.median():.0f} segments/km2")
        if empty:
            print(f"  NO ROADS in {len(empty)}: {', '.join(empty)}")
        for _, r in sparse.iterrows():
            print(f"  sparse: {r['name']} ({r.per_km2:.0f}/km2 over {r.km2:.0f} km2)")
        print()
        if empty or len(sparse):
            print("  >> RUN THIS AGAIN. Re-runs merge, so they can only add.")
        else:
            print("  >> Coverage is complete. DO NOT run this again.")
    except Exception as exc:  # noqa: BLE001
        print(f"  (coverage check skipped: {str(exc)[:80]})")

    print()
    print("Next: re-run notebooks/03_terrain_from_dtm.ipynb — Part 2b picks this")
    print("up automatically and uses road masking instead of the inferred ground.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
