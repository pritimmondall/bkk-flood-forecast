#!/usr/bin/env python3
"""Geocode unresolved canal stations via OpenStreetMap Overpass API.

For every station in data/station_registry_full.csv still marked Unresolved,
this script:
  1. extracts the canal name from the Thai station name
     ("จุดวัดคลองX ตอนถนนY" -> canal X, road Y)
  2. queries Overpass for a waterway named X inside the Bangkok bbox
  3. if the name also references a road Y, additionally queries Y and takes
     the closest point of the canal to that road (~the actual measuring
     point); otherwise takes the canal's midpoint
  4. writes candidates to data/station_registry_osm_candidates.csv with
     confidence Medium (canal+road intersection) or Low (canal midpoint)

Review the candidates before merging them into the registry — OSM coverage
of small khlongs is good but not complete, and canal names may repeat.
A merge helper is at the bottom (--merge flag) once you've eyeballed them.

Usage:
  pip install requests
  python data_pipeline/geocode_canals_osm.py            # query + write candidates
  python data_pipeline/geocode_canals_osm.py --merge    # merge reviewed file

Overpass is a free community service: the script sleeps 2s between queries
(~200 stations => ~10 min) and caches responses in .osm_cache.json so
re-runs are instant.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "station_registry_full.csv"
CANDIDATES = ROOT / "data" / "station_registry_osm_candidates.csv"
CACHE_FILE = ROOT / "data_pipeline" / ".osm_cache.json"

MIRRORS = [                                  # rotated on rate-limit/failure
    "https://overpass.kumi.systems/api/interpreter",   # most permissive
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",         # main (often busy)
]
BBOX = "13.45,100.30,14.05,100.95"          # Bangkok + margin
HEADERS = {"User-Agent": "bkk-flood-forecast-registry/1.0 (student project)"}

_cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
_mirror = [0]                                # rotating index


def overpass(query: str) -> dict:
    if query in _cache:
        return _cache[query]
    last_err = None
    for attempt in range(6):                 # tries mirrors round-robin
        url = MIRRORS[_mirror[0] % len(MIRRORS)]
        try:
            r = requests.post(url, data={"data": query}, headers=HEADERS,
                              timeout=90)
            if r.status_code == 429:         # rate-limited: next mirror + wait
                _mirror[0] += 1
                time.sleep(10 * (attempt + 1))
                last_err = f"429 from {url}"
                continue
            r.raise_for_status()
            out = r.json()
            _cache[query] = out
            CACHE_FILE.write_text(json.dumps(_cache))
            time.sleep(3)                    # be polite to the free service
            return out
        except requests.RequestException as e:
            _mirror[0] += 1
            last_err = str(e)
            time.sleep(5)
    raise RuntimeError(f"all mirrors failed: {last_err}")


def find_waterway(canal: str) -> list[tuple[float, float]]:
    """All node coords of waterways whose name contains the canal name."""
    q = (f'[out:json][timeout:30];way["waterway"]["name"~"{canal}"]'
         f'({BBOX});out geom;')
    pts = []
    for el in overpass(q).get("elements", []):
        pts += [(g["lat"], g["lon"]) for g in el.get("geometry", [])]
    return pts


def find_road(road: str) -> list[tuple[float, float]]:
    q = (f'[out:json][timeout:30];way["highway"]["name"~"{road}"]'
         f'({BBOX});out geom;')
    pts = []
    for el in overpass(q).get("elements", []):
        pts += [(g["lat"], g["lon"]) for g in el.get("geometry", [])]
    return pts


def parse_name(name: str) -> tuple[str | None, str | None]:
    """-> (canal, road-or-section) from a Thai station name."""
    canal = road = None
    m = re.search(r"คลอง\s*([^\s(]+)", name)
    if m and m.group(1) != "ระบายน้ำ":
        canal = m.group(1)
    m = re.search(r"ตอน\s*ถนน\s*([^\s(]+)", name) or \
        re.search(r"ตอน\s*([^\s(]+)", name)
    if m:
        road = m.group(1)
    return canal, road


def closest_pair(a: list, b: list) -> tuple[float, float]:
    """Point in `a` closest to any point in `b` (coarse but fine at city scale)."""
    best, bd = a[0], 1e9
    bs = b[:: max(1, len(b) // 200)]         # subsample road for speed
    for p in a[:: max(1, len(a) // 400)]:
        for q in bs:
            d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
            if d < bd:
                bd, best = d, p
    return best


def midpoint(pts: list) -> tuple[float, float]:
    return (round(sum(p[0] for p in pts) / len(pts), 5),
            round(sum(p[1] for p in pts) / len(pts), 5))


def run_geocode() -> None:
    rows = list(csv.reader(open(REGISTRY, encoding="utf-8-sig")))
    header, body = rows[0], rows[1:]
    todo = [r for r in body if r[7] == "Unresolved"]
    print(f"{len(todo)} unresolved stations")

    out = [["station_code", "name_thai", "canal", "road",
            "lat", "lon", "confidence", "basis"]]
    hits = 0
    for i, r in enumerate(todo):
        code, name = r[0], r[2]
        canal, road = parse_name(name)
        if not canal:
            continue
        try:
            cpts = find_waterway(canal)
        except Exception as e:
            print(f"  {code}: overpass error {e}")
            continue
        if not cpts:
            continue
        if road:
            try:
                rpts = find_road(road)
            except Exception:
                rpts = []
            if rpts:
                lat, lon = closest_pair(cpts, rpts)
                conf = "Medium"
                basis = (f"OSM: canal 'คลอง{canal}' nearest point to road "
                         f"'{road}' (canal-road intersection)")
            else:
                lat, lon = midpoint(cpts)
                conf, basis = "Low", f"OSM: midpoint of canal 'คลอง{canal}' (road '{road}' not found)"
        else:
            lat, lon = midpoint(cpts)
            conf, basis = "Low", f"OSM: midpoint of canal 'คลอง{canal}'"
        out.append([code, name, canal, road or "", round(lat, 5),
                    round(lon, 5), conf, basis])
        hits += 1
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(todo)} queried, {hits} located")

    with open(CANDIDATES, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(out)
    print(f"\n{hits} candidates -> {CANDIDATES}")
    print("Review them (spot-check a few in a map), then rerun with --merge")


def run_merge() -> None:
    cand = {r["station_code"]: r for r in
            csv.DictReader(open(CANDIDATES, encoding="utf-8-sig"))}
    rows = list(csv.reader(open(REGISTRY, encoding="utf-8-sig")))
    header, body = rows[0], rows[1:]
    n = 0
    for r in body:
        c = cand.get(r[0])
        if c and r[7] == "Unresolved":
            r[5], r[6], r[7], r[8] = c["lat"], c["lon"], c["confidence"], c["basis"]
            n += 1
    with open(REGISTRY, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    print(f"merged {n} OSM candidates into {REGISTRY}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    run_merge() if args.merge else run_geocode()
