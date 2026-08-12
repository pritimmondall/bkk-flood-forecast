"""Offline tests for the live collectors.

Every test here runs with NO network. The parsers are separated from `fetch()`
precisely so they can be tested against a recorded payload — which matters more
than usual, because these parse undocumented government APIs and the parsers are
the part most likely to be quietly wrong.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from bkkflood.collectors import bma_dds, capability_matrix, pumps, thaiwater, traffy
from bkkflood.collectors import base


# ---------------------------------------------------------------------------
# Fixtures — shaped from the real 2026-08-10 responses
# ---------------------------------------------------------------------------
THAIWATER_PAYLOAD = {
    "result": "OK",
    "data": {
        "waterlevel_data": {
            "data": [
                {
                    "id": 1,
                    "waterlevel_datetime": "2026-08-10 16:00:00",
                    "waterlevel_m": 1.42,
                    "waterlevel_msl": 0.61,
                    "waterlevel_msl_previous": 0.55,
                    "flow_rate": 12.4,
                    "discharge": None,
                    "storage_percent": 41.2,
                    "situation_level": 1,
                    "diff_wl_bank": -1.85,
                    "river_name": "Khlong Saen Saep",
                    "agency": {"agency_shortname": {"en": "RID"}},
                    "basin": {"basin_name": {"en": "Chao Phraya"}},
                    "geocode": {"amphoe_name": {"en": "Watthana"}},
                    "station": {
                        "id": 101,
                        "tele_station_name": {"en": "Asok"},
                        "tele_station_lat": 13.74325,
                        "tele_station_long": 100.562164,
                        "ground_level": 0.9,
                        "left_bank": 2.4,
                        "right_bank": 2.5,
                        "min_bank": 2.4,
                    },
                },
                {
                    "id": 2,
                    "waterlevel_datetime": "2026-08-10 16:00:00",
                    "waterlevel_m": 2.10,
                    "waterlevel_msl": 1.05,
                    "waterlevel_msl_previous": 1.19,
                    "flow_rate": None,
                    "discharge": None,
                    "storage_percent": None,
                    "situation_level": 2,
                    "diff_wl_bank": -0.4,
                    "river_name": "Chao Phraya",
                    "agency": {"agency_shortname": {"en": "HII"}},
                    "basin": {"basin_name": {"en": "Chao Phraya"}},
                    "geocode": {"amphoe_name": {"en": "Bang Kho Laem"}},
                    "station": {
                        "id": 102,
                        "tele_station_name": {"en": "Chao Phraya 15"},
                        "tele_station_lat": 13.700301,
                        "tele_station_long": 100.49277,
                        "ground_level": None,
                        "left_bank": 1.6,
                        "right_bank": 1.7,
                        "min_bank": 1.6,
                    },
                },
            ]
        }
    },
}

#: The REAL property names, read from the live endpoint on 2026-08-10. The text
#: field is `description`; the category is `problem_type_fondue`. The first
#: version of the parser looked for `comment` and would have produced rows that
#: looked fine and were all `is_flood = False`.
TRAFFY_PAYLOAD = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [100.5312, 13.7461]},
            "properties": {
                "ticket_id": "2026-AAA",
                "message_id": "m-1",
                "timestamp": "2026-08-10T09:12:00Z",
                "last_activity": "2026-08-10T11:00:00Z",
                "state": "finish",
                "state_type_latest": "finish",
                "problem_type_fondue": ["น้ำท่วม", "ถนน"],
                "problem_type_abdul": ["น้ำท่วม"],
                "type": ["น้ำท่วม"],
                "description": "น้ำท่วมขังหน้าปากซอย ระดับสูงประมาณ 20 ซม.",
                "address": "ซอยสุขุมวิท 23",
                "district": "Watthana",
                "subdistrict": "Khlong Toei Nuea",
                "province": "กรุงเทพมหานคร",
                "org": "สำนักการระบายน้ำ",
                "photo_url": "https://example/x.jpg",
                "view_count": 42,
                "duration_minutes_total": 180,
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [100.61, 13.81]},
            "properties": {
                "ticket_id": "2026-BBB",
                "timestamp": "2026-08-10T10:00:00Z",
                "state": "start",
                "problem_type_fondue": ["ทางเท้า"],
                "description": "ฟุตปาธชำรุด",
                "district": "Lat Phrao",
                "province": "กรุงเทพมหานคร",
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [100.49, 13.72]},
            "properties": {
                "ticket_id": "2026-CCC",
                "timestamp": "2026-08-10T10:30:00Z",
                "state": "start",
                "problem_type_fondue": ["ถนน"],
                # No tag, but the citizen described standing water anyway.
                "description": "น้ำรอระบาย ตลอดแนวถนน",
                "district": "Bangkok Noi",
                "province": "กรุงเทพมหานคร",
            },
        },
    ],
}

#: A national report that must be filtered out.
TRAFFY_UPCOUNTRY = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [100.16, 18.14]},
            "properties": {
                "ticket_id": "2026-PHRAE",
                "timestamp": "2026-08-10T10:00:00Z",
                "problem_type_fondue": ["น้ำท่วม"],
                "description": "น้ำท่วม",
                "province": "แพร่",
            },
        }
    ],
}

#: The real `/api/water-levels?limit=N` envelope, read live 2026-08-11.
PUMPS_LEVELS_PAYLOAD = {
    "data": [
        {"id": 1, "stationId": 12, "district": "din-daeng", "nameTH": "ดินแดง 6",
         "nameEN": {"en": "Din Daeng 6"}, "code": "PH.DDG.06",
         "waterLevelPercent": 62.0, "waterLevelCM": 124.0,
         "timestamp": "2026-08-11 11:45"},
        {"id": 2, "stationId": 44, "district": "bang-khen", "nameTH": "บางเขน 2",
         "nameEN": {"en": "Bang Khen 2"}, "code": "PH.BKN.02",
         "waterLevelPercent": None, "waterLevelCM": None,
         "timestamp": "2026-08-11 11:45"},
        {"id": 3, "stationId": 148, "district": "chatuchak", "nameTH": "รัชดา 2",
         "nameEN": {"en": "Ratchada 2"}, "code": "dds-ratchada-02",
         "waterLevelPercent": 30.0, "waterLevelCM": 45.0,
         "timestamp": "2026-08-11 11:40"},
    ],
    "count": 3, "total": 12370842, "page": 1, "pageCount": 618543,
}

#: The real `/api/stations/{id}` record — including the personal fields that
#: must never reach disk.
PUMPS_STATION_PAYLOAD = {
    "id": 1, "deviceType": "sensor", "code": "PH.DST.04", "type": "pump-station",
    "isActive": True, "nameTH": "ดุสิต 4", "nameEN": "Dusit 4",
    "latitude": 13.7765, "longitude": 100.5142,
    "contactPersonFirstName": "Somchai", "contactPersonLastName": "P.",
    "phone": "081-000-0000",
    "district": "dusit", "cabinetDoorOpen": False, "tankDepth": 800,
    "noOfPumps": 2, "waterLevelPercent": 41.0, "waterLevelCM": 328.0,
    "lastSync": "2026-08-11 11:45", "status": "online",
    "pumps": [{"id": 1, "status": "on", "power": 30, "operatingHrs": 1204},
              {"id": 2, "status": "off", "power": 30, "operatingHrs": 980}],
}


# ---------------------------------------------------------------------------
# ThaiWater
# ---------------------------------------------------------------------------
def test_thaiwater_finds_records_through_nested_envelope():
    """The station list is three levels down and the wrapper keys are undocumented."""
    recs = thaiwater._find_records(THAIWATER_PAYLOAD)
    assert len(recs) == 2


def test_thaiwater_parses_coordinates():
    """Coordinates are the whole reason this source is first — assert them hard."""
    df = thaiwater.parse(THAIWATER_PAYLOAD)
    assert len(df) == 2
    assert df["lat"].notna().all()
    assert df["long"].notna().all()
    assert df["lat"].between(13.4, 14.1).all(), "outside Bangkok"
    assert df["long"].between(100.2, 100.95).all(), "outside Bangkok"


def test_thaiwater_rise_is_signed_and_not_imputed():
    df = thaiwater.parse(THAIWATER_PAYLOAD).set_index("station_name")
    assert df.loc["Asok", "wl_rise_m"] == pytest.approx(0.06)
    assert df.loc["Chao Phraya 15", "wl_rise_m"] == pytest.approx(-0.14)


def test_thaiwater_missing_values_stay_nan():
    """An offline sensor must stay NaN. LightGBM handles NaN; a zero is a lie."""
    df = thaiwater.parse(THAIWATER_PAYLOAD).set_index("station_name")
    assert pd.isna(df.loc["Chao Phraya 15", "flow_rate"])
    assert pd.isna(df.loc["Chao Phraya 15", "storage_percent"])


def test_thaiwater_carries_a_chao_phraya_gauge():
    """This is what partly closes the tide-amplitude gap. Regression-guard it."""
    df = thaiwater.parse(THAIWATER_PAYLOAD)
    assert (df["river_name"] == "Chao Phraya").any()


def test_thaiwater_empty_payload_is_empty_frame_not_a_crash():
    assert thaiwater.parse({"data": {}}).empty
    assert thaiwater.parse(None).empty


# ---------------------------------------------------------------------------
# ThaiWater — against the ACTUAL first collection, not a hand-written fixture
#
# `tests/fixtures/thaiwater_20260811T051921Z.json.gz` is the untouched response
# from the first real poll, copied out of `data/live/_raw/`. This is what keeping
# the raw payloads was for: the three bugs below were all found by looking at
# what really came back, and this file makes them permanent regressions rather
# than things we remember for a while.
# ---------------------------------------------------------------------------
FIXTURE = (Path(__file__).parent / "fixtures"
           / "thaiwater_20260811T051921Z.json.gz")
#: The moment that poll was made, so `age_minutes` is deterministic.
FIXTURE_FETCHED_AT = datetime(2026, 8, 11, 5, 19, 21, tzinfo=timezone.utc)


def _real_payload():
    if not FIXTURE.exists():
        pytest.skip(f"fixture not present: {FIXTURE}")
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def test_real_payload_parses_to_eleven_stations():
    df = thaiwater.parse(_real_payload(), now=FIXTURE_FETCHED_AT)
    assert len(df) == thaiwater.EXPECTED_STATIONS == 11


def test_timestamps_are_bangkok_local_and_converted_to_utc():
    """The most dangerous thing in this file.

    `waterlevel_datetime` carries no offset and is Asia/Bangkok. Read as UTC,
    the newest reading in this poll sits nearly 7 hours in the FUTURE. Nothing
    would raise — it would just move every canal reading 7 hours away from the
    rainfall that caused it, and the finding would be "canal levels do not
    predict floods", which is the opposite of what Phase 5 measured.
    """
    df = thaiwater.parse(_real_payload(), now=FIXTURE_FETCHED_AT)
    fetched = pd.Timestamp(FIXTURE_FETCHED_AT).tz_localize(None)

    assert (df["ts_local"] > fetched).any(), "fixture no longer shows the trap"
    assert (df["ts"] <= fetched).all(), "a reading is in the future — tz lost"
    assert (df["ts_local"] - df["ts"]).eq(pd.Timedelta(hours=7)).all()
    assert df["age_minutes"].min() == pytest.approx(19.4, abs=0.1)


def test_stations_with_null_names_are_not_silently_dropped():
    """Two of eleven return `station_name = null`. `groupby("station_name")`
    drops NaN keys without a word — that is how the first coordinates export
    wrote 9 stations instead of 11."""
    df = thaiwater.parse(_real_payload(), now=FIXTURE_FETCHED_AT)

    assert df["station_name"].nunique() == 9, "fixture changed"
    assert df["station_id"].nunique() == 11
    assert df["station_label"].notna().all()
    assert df.groupby("station_id").ngroups == 11


def test_zero_bank_reference_is_flagged_rather_than_believed():
    """Station 11688984 reports `min_bank = 0`, so `diff_wl_bank` is 0.00 and the
    API's own text reads 'water at bank level'. Every other station's min_bank is
    0.62–4.46 m. It is a missing reference formatted as maximum severity, and an
    alert rule on bank clearance would fire on it forever."""
    df = thaiwater.parse(_real_payload(), now=FIXTURE_FETCHED_AT).set_index("station_id")

    assert df.loc[11688984, "min_bank"] == 0.0
    assert not df.loc[11688984, "bank_ref_valid"]
    assert pd.isna(df.loc[11688984, "diff_wl_bank_clean"])
    # Flagged, not erased — Phase 0's lesson about checks that quietly edit data.
    assert df.loc[11688984, "diff_wl_bank"] == 0.0
    assert int((~df["bank_ref_valid"]).sum()) == 1


def test_history_repairs_a_parquet_written_by_an_older_parser(tmp_path, monkeypatch):
    """The situation this actually solves, reproduced.

    A parquet is on disk from before the parser gained `station_label`,
    `ts_local` and `bank_ref_valid`. Every downstream cell would KeyError on a
    file that is perfectly recoverable — because the raw payload is right there.
    `history()` notices and rebuilds. Nothing on disk is rewritten: silently
    conforming old data to today's parser would destroy the evidence of what the
    API actually sent.
    """
    import gzip as _gz
    from bkkflood import collectors as C

    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    when = datetime(2026, 8, 11, 5, 19, 21, tzinfo=timezone.utc)
    payload = _real_payload()

    # An "old parser" that produced only a couple of columns.
    old = pd.DataFrame({"station_id": [1, 2], "waterlevel_msl": [0.5, 1.0]})
    base.write_parquet(base.stamp_provenance(old, "thaiwater", when),
                       "thaiwater", when)
    raw_dir = base.live_dir("thaiwater", when, raw=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    with _gz.open(raw_dir / "20260811T051921Z.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(payload, fh)

    stored, repaired = C.read_history("thaiwater"), C.history("thaiwater")

    assert len(stored) == 2 and "station_label" not in stored.columns
    assert len(repaired) == 11
    assert {"station_label", "ts_local", "bank_ref_valid"} <= set(repaired.columns)
    # age_minutes is relative to the ORIGINAL fetch, not to now.
    assert repaired["age_minutes"].min() == pytest.approx(19.4, abs=0.1)
    # The stored file is untouched.
    assert len(C.read_history("thaiwater")) == 2


def test_history_repairs_a_mixed_timezone_history(tmp_path, monkeypatch):
    """The failure the column check could not see, reproduced exactly.

    One file written by parser 1.0.0 (ts in Bangkok local) and one by 1.1.0 (ts
    in UTC). Every expected column is present in the concatenation, so comparing
    column sets says "fine" — while the frame quietly holds two timezones in one
    column. This is what the notebook's own "no readings from the future"
    assertion caught. The version stamp is the signal; columns are not.
    """
    from bkkflood import collectors as C

    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    payload = _real_payload()
    old_when = datetime(2026, 8, 11, 5, 19, 21, tzinfo=timezone.utc)
    new_when = datetime(2026, 8, 11, 6, 25, 54, tzinfo=timezone.utc)

    for when, version, shift_utc in ((old_when, "1.0.0", False),
                                     (new_when, base.COLLECTOR_VERSION, True)):
        df = thaiwater.parse(payload, now=when)
        if not shift_utc:                      # emulate the pre-fix parser
            df["ts"] = df["ts_local"]
        df = base.stamp_provenance(df, "thaiwater", when)
        df["_collector_version"] = version
        base.write_parquet(df, "thaiwater", when)

        raw_dir = base.live_dir("thaiwater", when, raw=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        with gzip.open(raw_dir / f"{when:%Y%m%dT%H%M%SZ}.json.gz", "wt",
                       encoding="utf-8") as fh:
            json.dump(payload, fh)

    stored = C.read_history("thaiwater")
    assert not (set(thaiwater.parse(payload).columns) - set(stored.columns)), \
        "columns alone cannot detect this — that is the point"
    assert (stored["ts"] > stored["_fetched_at_utc"]).any(), \
        "the stored frame really does contain readings from the future"

    repaired = C.history("thaiwater")
    assert (repaired["ts"] <= repaired["_fetched_at_utc"]).all()
    assert (repaired["_collector_version"] == base.COLLECTOR_VERSION).all()


def test_real_payload_coordinates_are_all_inside_bangkok():
    df = thaiwater.parse(_real_payload(), now=FIXTURE_FETCHED_AT)
    assert df["lat"].between(13.4, 14.1).all()
    assert df["long"].between(100.2, 100.95).all()
    assert df["lat"].notna().all() and df["long"].notna().all()


# ---------------------------------------------------------------------------
# Traffy
# ---------------------------------------------------------------------------
def test_traffy_flags_only_flood_reports():
    df = traffy.parse(TRAFFY_PAYLOAD).set_index("ticket_id")
    assert len(df) == 3
    assert df.loc["2026-AAA", "is_flood"]
    assert not df.loc["2026-BBB", "is_flood"]


def test_traffy_reads_the_description_field_not_comment():
    """The regression that motivated re-reading the live schema.

    `comment` does not exist in the real payload. A parser that looks for it
    finds nothing, marks every report not-flood, and writes rows that look
    perfectly healthy. Assert on the text actually arriving.
    """
    df = traffy.parse(TRAFFY_PAYLOAD).set_index("ticket_id")
    assert "20 ซม." in str(df.loc["2026-AAA", "description"])


def test_traffy_catches_flooding_described_without_the_tag():
    """`น้ำรอระบาย` ("water waiting to drain") is how people describe standing
    water when they do not use the flood category. Missing these would bias the
    coverage check in exactly the direction that flatters our sensor network."""
    df = traffy.parse(TRAFFY_PAYLOAD).set_index("ticket_id")
    assert df.loc["2026-CCC", "is_flood"]


def test_traffy_filters_out_upcountry_reports():
    """The feed is national. A Phrae flood is not a Bangkok label."""
    assert traffy.parse(TRAFFY_UPCOUNTRY).empty


def test_traffy_keeps_unmapped_properties_verbatim():
    df = traffy.parse(TRAFFY_PAYLOAD)
    assert "raw_state_type_latest" in df.columns


def test_traffy_coordinates_are_lon_lat_order_in_geojson():
    """GeoJSON is [long, lat]. Swapping them puts Bangkok in the Indian Ocean."""
    df = traffy.parse(TRAFFY_PAYLOAD)
    assert df["lat"].between(13.4, 14.1).all()
    assert df["long"].between(100.2, 100.95).all()


def test_traffy_empty_payload_is_empty_frame():
    assert traffy.parse({"features": []}).empty
    assert traffy.parse(None).empty


# ---------------------------------------------------------------------------
# Pumps
# ---------------------------------------------------------------------------
def test_pumps_extracts_the_district_prefix_that_joins_to_our_stations():
    df = pumps.parse_levels(PUMPS_LEVELS_PAYLOAD).set_index("station_code")
    assert df.loc["PH.DDG.06", "district_prefix"] == "DDG"
    assert df.loc["PH.BKN.02", "district_prefix"] == "BKN"


def test_pumps_refuses_to_guess_a_district_from_a_malformed_code():
    """Some stations are named `dds-ratchada-02`, not `PH.XXX.NN`. A wrong
    district is worse than a missing one — it attaches a reading to the wrong
    part of the city and nothing downstream can detect that."""
    df = pumps.parse_levels(PUMPS_LEVELS_PAYLOAD).set_index("station_code")
    assert pd.isna(df.loc["dds-ratchada-02", "district_prefix"])


def test_pumps_offline_station_stays_nan():
    df = pumps.parse_levels(PUMPS_LEVELS_PAYLOAD).set_index("station_code")
    assert pd.isna(df.loc["PH.BKN.02", "water_level_cm"])


def test_pumps_levels_are_centimetres_under_our_own_column_name():
    df = pumps.parse_levels(PUMPS_LEVELS_PAYLOAD).set_index("station_code")
    assert df.loc["PH.DDG.06", "water_level_cm"] == pytest.approx(124.0)
    assert df.loc["PH.DDG.06", "water_level_pct"] == pytest.approx(62.0)


def test_pumps_empty_envelope_is_an_empty_frame():
    assert pumps.parse_levels({"data": [], "total": 0}).empty
    assert pumps.parse_levels(None).empty


def test_pumps_only_limit_is_honoured_by_the_api(monkeypatch):
    """`pageSize`, `perPage`, `take` and `size` are accepted and silently
    ignored, returning the 20-row default. Renaming this parameter would cost
    99% of every poll without any error to notice."""
    seen = {}

    def fake(url, params=None, **k):
        seen["params"] = params
        return PUMPS_LEVELS_PAYLOAD

    monkeypatch.setattr(pumps, "http_get_json", fake)
    pumps.fetch(limit=2000)
    assert seen["params"] == {"limit": 2000}


# --- the station registry, and the personal data in it ---------------------
def test_pumps_station_gives_real_bangkok_coordinates():
    """Terrain contributes 0% of model gain because every station currently sits
    at a district centroid. These are measured positions."""
    rec = pumps.parse_station(PUMPS_STATION_PAYLOAD)
    assert 13.4 < rec["lat"] < 14.1
    assert 100.2 < rec["long"] < 100.95


def test_pumps_station_counts_running_pumps():
    """Pump activity is the confounder: a flood a pump prevented is labelled
    'no flood' in our training data."""
    rec = pumps.parse_station(PUMPS_STATION_PAYLOAD)
    assert rec["n_pumps"] == 2
    assert rec["n_pumps_running"] == 1


def test_pumps_station_drops_personal_data():
    """Named BMA staff and their phone numbers have no scientific value here and
    there is no reason to hold them. They must not reach the frame OR the stored
    raw payload."""
    rec = pumps.parse_station(PUMPS_STATION_PAYLOAD)
    blob = " ".join(str(v) for v in rec.values())
    for field_name in ("contactPersonFirstName", "contactPersonLastName", "phone"):
        assert field_name not in rec
    assert "Somchai" not in blob
    assert "081-000-0000" not in blob

    stripped = pumps._strip_pii(PUMPS_STATION_PAYLOAD)
    assert "phone" not in stripped
    assert "Somchai" not in json.dumps(stripped)


def test_pumps_station_walk_stops_after_the_ids_run_out(monkeypatch):
    """Ids run 1..~148 and then 404. The walk must stop, not grind to max_id."""
    calls = {"n": 0}

    def fake(url, **k):
        calls["n"] += 1
        sid = int(url.rsplit("/", 1)[1])
        if sid > 3:
            raise RuntimeError("404")
        return dict(PUMPS_STATION_PAYLOAD, id=sid, code=f"PH.DST.0{sid}")

    monkeypatch.setattr(pumps, "http_get_json", fake)
    df, raw = pumps.fetch_stations(max_id=400, stop_after_misses=5)

    assert len(df) == 3
    assert calls["n"] == 8, "walked past the stop threshold"
    assert len(raw) == 3


def test_pumps_fetch_fails_cleanly_when_the_host_is_unreachable(monkeypatch):
    """The failure must be a normal failed result, not a crash — one dead source
    must never cost the others their hour."""
    def dead(*a, **k):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(pumps, "http_get_json", dead)
    res = base.run_collector("pumps", pumps.fetch)
    assert res.ok is False
    assert "no route to host" in res.error


# ---------------------------------------------------------------------------
# Cadence — one hourly job carrying sources on different clocks
# ---------------------------------------------------------------------------
def test_source_with_no_history_is_always_due(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    assert base.is_due("never_run", 1440) is True


def test_daily_source_is_not_due_an_hour_later(tmp_path, monkeypatch):
    """`pumps_stations` costs ~148 requests because BMA publishes no bulk
    endpoint. Fine daily; rude hourly."""
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    an_hour_ago = base.utc_now() - timedelta(hours=1)
    base.write_parquet(pd.DataFrame({"x": [1]}), "pumps_stations", an_hour_ago)

    assert base.is_due("pumps_stations", 1440) is False
    assert base.is_due("pumps_stations", 60) is True


def test_hourly_source_is_due_despite_scheduler_drift(tmp_path, monkeypatch):
    """launchd's hourly timer drifts. A strict `>= 60 min` test would skip about
    every other run — data loss disguised as politeness."""
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    just_under_an_hour = base.utc_now() - timedelta(minutes=58)
    base.write_parquet(pd.DataFrame({"x": [1]}), "thaiwater", just_under_an_hour)

    assert base.is_due("thaiwater", 60) is True


def test_skipped_sources_are_marked_not_counted_as_successes(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    res = base.CollectorResult("pumps_stations", base.utc_now(), ok=True, skipped=True)
    payload = json.loads(base.write_status([res]).read_text())

    assert payload["n_ok"] == 0
    assert payload["n_skipped"] == 1


# ---------------------------------------------------------------------------
# BMA — parser must survive being wrong about field names
# ---------------------------------------------------------------------------
def test_bma_parse_survives_completely_unexpected_schema():
    """Every field name in bma_dds is a guess. Guessing wrong must cost a column,
    not the poll."""
    payload = {"result": [{"totally": "unexpected", "shape": 1}]}
    df = bma_dds.parse(payload, "rain")
    assert len(df) == 1
    assert "raw_totally" in df.columns  # original data preserved
    assert df["station_code"].isna().all()  # guess missed, no crash


def test_bma_parse_maps_training_column_names():
    payload = {"data": [{"rain_code": "RF.BBN.01", "rf1hr": 3.2, "rf24hr": 41.0,
                         "site_timestamp": "2026-08-10 16:05:00"}]}
    df = bma_dds.parse(payload, "rain")
    assert df.loc[0, "station_code"] == "RF.BBN.01"
    assert df.loc[0, "rf1hr"] == pytest.approx(3.2)
    assert pd.notna(df.loc[0, "ts"])


def test_bma_fetch_refuses_without_permission():
    """Project rule 8. This must fail loudly, not collect quietly."""
    assert bma_dds.ENABLED is False
    with pytest.raises(RuntimeError, match="permission"):
        bma_dds.fetch()


# ---------------------------------------------------------------------------
# Storage — the append-only guarantee
# ---------------------------------------------------------------------------
def test_write_parquet_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    when = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({"a": [1]})

    p1 = base.write_parquet(df, "src", when)
    p2 = base.write_parquet(df, "src", when)  # same second
    assert p1 != p2, "second write clobbered the first"
    assert p1.exists() and p2.exists()


def test_write_raw_never_overwrites(tmp_path, monkeypatch):
    """Regression: the first version of this stamped only to the second, so three
    polls inside one second left ONE raw file. The raw payloads are the recovery
    path for a parser bug found months later — losing them silently is the worst
    kind of bug this module can have."""
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    when = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    paths = {base.write_raw("src", {"n": i}, when) for i in range(3)}
    assert len(paths) == 3, "raw writes collided"

    seen = set()
    for p in paths:
        import gzip as _gz
        with _gz.open(p, "rt", encoding="utf-8") as fh:
            seen.add(json.load(fh)["n"])
    assert seen == {0, 1, 2}


def test_run_collector_turns_a_crash_into_a_failed_result(tmp_path, monkeypatch):
    """One dead source must never stop the others — that hour is unrecoverable."""
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)

    def boom():
        raise ConnectionError("host unreachable")

    res = base.run_collector("broken", boom)
    assert res.ok is False
    assert "unreachable" in res.error


def test_coverage_reports_cold_start_until_24h(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)
    base.write_parquet(
        pd.DataFrame({"x": [1], "_fetched_at_utc": [pd.Timestamp("2026-08-10 00:00")]}),
        "src", datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc))
    base.write_parquet(
        pd.DataFrame({"x": [1], "_fetched_at_utc": [pd.Timestamp("2026-08-10 06:00")]}),
        "src", datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc))

    cov = base.coverage("src")
    assert cov["hours"] == pytest.approx(6.0)
    assert cov["cold_start"] is True


def test_provenance_is_stamped_on_every_row():
    when = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    out = base.stamp_provenance(pd.DataFrame({"a": [1, 2]}), "src", when)
    assert (out["_source"] == "src").all()
    assert out["_fetched_at_utc"].notna().all()
    assert out["_collector_version"].notna().all()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_bma_is_not_scheduled_by_default():
    from bkkflood.collectors import DEFAULT_SOURCES

    assert "bma_dds" not in DEFAULT_SOURCES


def test_pumps_is_not_scheduled_while_the_api_returns_403():
    """The parsers are written and green, but the host is behind Cloudflare and
    403s every HTTP client. Scheduling it would write a failure row every hour
    and hammer a government server for nothing. Re-add both names the day BMA
    grants access — this test is the reminder that it is a deliberate pause,
    not an oversight."""
    from bkkflood.collectors import DEFAULT_SOURCES, REGISTRY

    assert "pumps" not in DEFAULT_SOURCES
    assert "pumps_stations" not in DEFAULT_SOURCES
    assert "pumps" in REGISTRY and "pumps_stations" in REGISTRY


def test_capability_matrix_is_honest_about_verification():
    m = capability_matrix().set_index("source")
    assert "NOT VERIFIED" in m.loc["bma_dds", "verified"]
    assert m.loc["bma_dds", "needs_permission"]
    assert "BLOCKED" in m.loc["pumps", "verified"]
    assert m.loc["pumps", "needs_permission"]
    assert "PII fields dropped" in m.loc["pumps_stations", "verified"]


def test_status_file_records_failures_not_just_successes(tmp_path, monkeypatch):
    """A run where every source failed must not look like a run that never
    happened. Silence is the failure mode that costs months."""
    monkeypatch.setattr(base, "_repo_root", lambda: tmp_path)

    def boom():
        raise ConnectionError("down")

    results = [base.run_collector("a", boom), base.run_collector("b", boom)]
    p = base.write_status(results)

    payload = json.loads(p.read_text())
    assert payload["n_ok"] == 0
    assert payload["n_failed"] == 2
    assert {s["source"] for s in payload["sources"]} == {"a", "b"}
