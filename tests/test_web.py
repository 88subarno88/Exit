"""Every surface renders, from a tiny throwaway DB -- no dependence on local data,
and no CMC key (the deployed site has none)."""
import os, json, sqlite3, importlib
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS = "2026-09-22T09:00:00+00:00"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path = tmp_path_factory.mktemp("site") / "site.db"
    db = sqlite3.connect(path)
    with open(os.path.join(ROOT, "ingest", "schema.sql")) as f:
        db.executescript(f.read())
    rows = [  # ts, id, sym, name, slug, price, mcap, vol, sigma, Y, delta, mp, lo, hi, ext, grade, exit100k, manip
        (TS, 1, "BTC", "Bitcoin", "bitcoin", 86000, 1.7e12, 5e10, 0.02, 4.4, 0.65, 5e9, 2e9, 9e9, 1, "AAA", 0.2, 3e10),
        (TS, 2, "ONE", "Harmony", "harmony", 0.01, 1e8, 5e6, 0.04, 4.4, 0.65, 2e5, 1e5, 4e5, 0, "BB", 120, 1e6),
        (TS, 3, "ONE", "ONEchain", "cross", 0.2, 9e7, 1e6, 0.05, 4.4, 0.65, 3e4, 1e4, 6e4, 0, "B", 400, 2e5),
        ("2026-09-21T09:00:00+00:00", 2, "ONE", "Harmony", "harmony", 0.01, 1e8, 5e6, 0.04, 4.4, 0.65,
         4e5, 2e5, 8e5, 0, "BBB", 90, 1e6),
    ]
    db.executemany(f"INSERT INTO ratings VALUES ({','.join('?' * 18)})", rows)
    db.execute("INSERT INTO observed_costs VALUES ('2026-09-22', 2, 1000000, NULL, 'unabsorbable', 2)")
    db.execute("INSERT INTO meta VALUES ('hindsight_cases', ?)", (json.dumps(
        [{"key": "ftt", "token_id": 4195, "label": "FTT", "date": "2022-11-08", "context": "FTX."}]),))
    db.executemany("INSERT INTO hindsight VALUES ('ftt', ?, ?, 1e8, 1e9, 0.03, ?, ?, 10)",
                   [("2022-10-01", 25, 1e7, "AAA"), ("2022-11-08", 5, 4e7, "AAA"), ("2022-11-15", 1.8, 2e5, "BB")])
    db.execute("INSERT INTO api_calls VALUES (?, '/v1/cryptocurrency/listings/latest', 200, 300, 3, 0)", (TS,))
    db.commit()
    db.close()

    os.environ["SITE_DB"] = str(path)
    os.environ.pop("CMC_API_KEY", None)
    import web.app as appmod
    importlib.reload(appmod)
    return appmod.app.test_client()


@pytest.mark.parametrize("url", ["/", "/token/bitcoin", "/token/harmony", "/ratings",
                                 "/ratings?tab=liquidity", "/ratings?tab=feed", "/hindsight",
                                 "/methodology", "/debug", "/search?q=one"])
def test_every_surface_renders(client, url):
    r = client.get(url)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Traceback" not in body and "{{" not in body


def test_extrapolated_max_position_is_never_printed(client):
    body = client.get("/token/bitcoin").get_data(as_text=True)
    assert "&gt; $10M" in body and "$5B" not in body


def test_downgrade_feed_shows_grade_change(client):
    body = client.get("/ratings?tab=feed").get_data(as_text=True)
    assert "g-BBB" in body and "g-BB" in body and "ONE" in body


def test_unknown_token_is_404_with_a_sentence(client):
    r = client.get("/token/nope")
    assert r.status_code == 404 and "We don't rate that token" in r.get_data(as_text=True)


def test_search_exact_symbol_redirects(client):
    assert client.get("/search?q=btc").status_code == 302


def test_api_impact(client):
    j = client.get("/api/v1/impact/BTC?size=2000000").get_json()
    assert j["grade"] == "AAA" and j["as_of"] == TS
    assert j["max_position_usd"] is None and "calibration limit" in j["max_position_note"]
    assert j["exit"]["bps"] > 0


def test_api_ambiguous_symbol_is_409_with_candidates(client):
    r = client.get("/api/v1/impact/ONE")
    assert r.status_code == 409 and len(r.get_json()["candidates"]) == 2
    assert client.get("/api/v1/impact/ONE?id=3").get_json()["slug"] == "cross"


def test_api_rejects_bad_size(client):
    assert client.get("/api/v1/impact/BTC?size=abc").status_code == 400
    assert client.get("/api/v1/impact/BTC?size=-5").status_code == 400
