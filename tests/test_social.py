from datetime import UTC, datetime, timedelta

import pytest

from tori_taurus.social import collect, summarize, tone

NOW = datetime(2026, 10, 9, 15, tzinfo=UTC)


def post(n, text, **changes):
    return {"platform": "reddit", "id": str(n), "author": str(n), "text": text,
            "published_at": NOW.isoformat(), "url": "https://www.reddit.com/example",
            **changes}


def test_deduplication_cashtags_and_sentiment():
    posts = [post(1, "$XYZ bullish"), post(1, "$XYZ bullish"),
             post(2, "$XYZ buy"), post(3, "$XYZ upside"), post(4, "XYZ bullish"),
             post(5, "$OTHER bullish")]
    row = summarize(posts, ["XYZ"], NOW, [])["tickers"][0]
    assert row["mentions"] == row["unique_authors"] == 3
    assert row["sentiment"] == "positive"
    assert "text" not in row["evidence"][0]


def test_direction_not_transferred_between_tickers():
    result = summarize([post(1, "$XYZ bullish. $ABC bearish.")], ["XYZ", "ABC"], NOW, [])
    counts = {r["symbol"]: r["tone_counts"] for r in result["tickers"]}
    assert counts["XYZ"]["positive"] == 1
    assert counts["ABC"]["negative"] == 1
    assert tone("$XYZ not bullish") == "unclear"
    assert tone("bullish but dilution") == "mixed"
    assert summarize([post(1, "$XYZ bullish $ABC")], ["XYZ", "ABC"], NOW, [])["tickers"][0][
        "tone_counts"]["unclear"] == 1


def test_old_future_missing_and_small_sample():
    result = summarize([
        post(1, "$XYZ bullish", published_at=(NOW - timedelta(days=2)).isoformat()),
        post(2, "$XYZ bullish", published_at=(NOW + timedelta(minutes=1)).isoformat()),
        post(3, "$XYZ bullish"),
    ], ["XYZ"], NOW, [{"source": "x", "status": "not configured", "posts": None}])
    assert result["tickers"][0]["mentions"] == 1
    assert result["tickers"][0]["sentiment"] == "unclear"
    assert result["coverage"][0]["posts"] is None


def test_no_network_or_paid_reads_without_access(monkeypatch):
    monkeypatch.delenv("TORI_REDDIT_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TORI_X_BEARER_TOKEN", "synthetic-test-token")
    monkeypatch.setattr("tori_taurus.social._get", lambda *a: pytest.fail("Unexpected request"))
    result = collect(["XYZ"], NOW)
    assert not result["tickers"]
    assert result["coverage"][2]["status"] == "paid reads disabled"


def test_invalid_universe_rejected_before_network(monkeypatch):
    monkeypatch.setattr("tori_taurus.social._get", lambda *a: pytest.fail("Unexpected request"))
    with pytest.raises(ValueError):
        collect(["XYZ OR secret"], NOW, True)


def test_reddit_access_failure_not_zero_mentions(monkeypatch):
    monkeypatch.setenv("TORI_REDDIT_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.delenv("TORI_X_BEARER_TOKEN", raising=False)

    def denied(*args):
        raise ValueError("HTTP 403")

    monkeypatch.setattr("tori_taurus.social._get", denied)
    result = collect(["XYZ"], NOW)
    assert all(c["posts"] is None for c in result["coverage"])
    assert result["coverage"][0]["status"].startswith("unavailable")


def test_bounded_public_collection_and_paid_opt_in(monkeypatch):
    monkeypatch.setenv("TORI_REDDIT_ACCESS_TOKEN", "synthetic-reddit-token")
    monkeypatch.setenv("TORI_X_BEARER_TOKEN", "synthetic-x-token")
    calls = []

    def response(url, token):
        calls.append(url)
        if "reddit.com" in url:
            return {"data": {"children": [{"data": {
                "id": "1", "author": "public-author", "title": "$XYZ bullish",
                "selftext": "", "created_utc": NOW.timestamp(), "permalink": "/r/example/1",
            }}]}}
        return {"data": [{"id": "2", "author_id": "public-author", "text": "$XYZ bearish",
                          "created_at": NOW.isoformat()}], "meta": {"next_token": "unused"}}

    monkeypatch.setattr("tori_taurus.social._get", response)
    result = collect(["XYZ"], NOW, True)
    assert len(calls) == 3  # Two communities, one X page; never follow pagination.
    assert result["tickers"][0]["mentions"] == 2  # Same Reddit post returned twice.
    assert result["tickers"][0]["sentiment"] == "mixed"
    assert "synthetic" not in str(result)
    assert "public-author" not in str(result)


@pytest.mark.parametrize("code", [400, 401, 402, 403, 429])
def test_x_failure_has_safe_actionable_status(monkeypatch, code):
    from tori_taurus.social import PublicDataError
    monkeypatch.delenv("TORI_REDDIT_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TORI_X_BEARER_TOKEN", "synthetic-private-token")
    def denied(*args):
        raise PublicDataError(code)
    monkeypatch.setattr("tori_taurus.social._get", denied)
    result = collect(["XYZ"], NOW, True)
    assert f"HTTP {code}" in result["coverage"][2]["status"]
    assert "synthetic-private-token" not in str(result)
    assert result["coverage"][2]["posts"] is None
