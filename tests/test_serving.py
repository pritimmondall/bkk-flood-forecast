"""API contract tests.

These are about the PROMISES the service makes, not about model accuracy. The
promises are what an integrator relies on, and they are exactly what a refactor
silently breaks.
"""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient           # noqa: E402

from backend.app.main import app                    # noqa: E402

client = TestClient(app)


def test_health_reports_replay_and_the_available_window():
    r = client.get("/health")
    assert r.status_code == 200
    b = r.json()
    assert b["data_mode"] == "replay"
    assert b["available"]["first"] < b["available"]["last"]


def test_cap_status_is_test_everywhere_it_appears():
    """The single most important guard in this file.

    An `Actual` CAP message is a real public warning with legal weight. It must
    never become Actual by accident — only by a deliberate config change with
    written BMA authorisation behind it.
    """
    assert client.get("/health").json()["cap_status"] == "Test"
    a = client.get("/api/alerts").json()
    assert a["cap_status"] == "Test"
    assert a["authorised_for_public_use"] is False
    for alert in a["alerts"]:
        assert alert["status"] == "Test"


def test_every_forecast_response_carries_its_caveats():
    """Project rule 6: a caveat is a field, not a footnote."""
    b = client.get("/api/forecast").json()
    assert b["data_mode"] == "replay"
    assert isinstance(b["caveats"], list) and len(b["caveats"]) >= 4
    assert any("replay" in c.lower() for c in b["caveats"])
    assert any("15 minutes" in c for c in b["caveats"])


def test_depth_is_never_predicted():
    """The depth intervals failed their coverage check (43-63% vs 90%).

    Until the two-stage model exists, the field must stay null. A number here
    would be believed.
    """
    for s in client.get("/api/forecast").json()["stations"]:
        assert s["predicted_depth_cm"] is None
    for alert in client.get("/api/alerts").json()["alerts"]:
        assert alert["info"]["parameter"]["predicted_depth_cm"] is None


def test_an_already_flooded_station_gets_no_probability():
    """The onset model never saw such rows. It has no opinion worth serving."""
    b = client.get("/api/forecast", params={"ts": "2025-11-13 03:00:00"}).json()
    flooded = [s for s in b["stations"] if s["status"] == "flooded_now"]
    assert flooded, "expected some flooded stations at this timestamp"
    for s in flooded:
        assert s["probability"] is None
        assert s["alert"] is True


def test_district_risk_denies_being_a_flood_extent():
    """When a district floods only ~35% of its sensors register it.

    A district colour is a summary of a few points. If a frontend draws it as a
    flood extent it is lying, so the payload says so explicitly.
    """
    b = client.get("/api/risk").json()
    assert b["is_flood_extent"] is False
    assert "extent" in b["extent_note"].lower()


def test_model_card_states_the_uncomfortable_numbers():
    c = client.get("/api/model-card").json()
    assert c["performance"]["precision"] < 0.25
    assert c["performance"]["median_warning_minutes"] <= 15
    assert c["alerting"]["authorised_for_public_use"] is False
    joined = " ".join(c["known_limitations"]).lower()
    assert "resolution" in joined and "terrain" in joined and "depth" in joined
    assert len(c["would_most_improve_it"]) >= 3


def test_unknown_station_is_404_not_an_empty_success():
    assert client.get("/api/forecast/FL.NOPE.99").status_code == 404


def test_alerting_only_filter_returns_only_alerts():
    b = client.get("/api/forecast", params={"ts": "2025-11-13 03:00:00",
                                            "alerting_only": True}).json()
    assert b["returned"] == len(b["stations"])
    assert all(s["alert"] for s in b["stations"])


def test_the_service_root_does_not_look_broken():
    """Opening the root URL is the first thing anyone does.

    A bare FastAPI 404 there is correct and indistinguishable from a dead
    server. It should land on the docs instead.
    """
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/docs" in r.headers["location"]


def test_api_index_lists_the_endpoints_and_points_at_the_model_card():
    b = client.get("/api").json()
    assert b["start_here"] == "/api/model-card"
    assert b["data_mode"] == "replay"
    assert any("forecast" in k for k in b["endpoints"])


def test_replay_is_default_mode():
    b = client.get("/api/forecast").json()
    assert b["data_mode"] == "replay"


def test_live_forecast_endpoint_returns_live_mode_data():
    r = client.get("/api/forecast", params={"mode": "live"})
    assert r.status_code == 200
    b = r.json()
    assert b["data_mode"] == "live_public"
    assert "mode_performance" in b
    assert b["mode_performance"]["event_pod"] == 0.049


def test_live_status_endpoint():
    r = client.get("/api/live/status")
    assert r.status_code == 200
    b = r.json()
    assert b["data_mode"] == "live_public"
    assert "cold_start" in b
    assert "collector" in b


def test_live_risk_endpoint():
    r = client.get("/api/risk", params={"mode": "live"})
    assert r.status_code == 200
    b = r.json()
    assert b["data_mode"] == "live_public"
    assert b["is_flood_extent"] is False


def test_live_alerts_endpoint():
    r = client.get("/api/alerts", params={"mode": "live"})
    assert r.status_code == 200
    b = r.json()
    assert b["data_mode"] == "live_public"
    assert b["cap_status"] == "Test"

