"""Bounded public-post research. No orders, account access, or background polling."""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CASHTAG = re.compile(r"(?<![\w$])\$([A-Za-z][A-Za-z0-9.-]{0,14})(?![\w.-])")
POSITIVE = {"bullish", "breakout", "undervalued", "upside", "buy", "buying", "long"}
NEGATIVE = {"bearish", "dilution", "overvalued", "downside", "sell", "selling", "scam"}


def tone(text: str) -> str:
    """Conservative lexical tone; ambiguity is never forced into a direction."""
    words = re.findall(r"[a-z]+", text.lower())
    if any(word in {"not", "never", "sarcasm", "sarcastic"} for word in words):
        return "unclear"
    positive, negative = bool(set(words) & POSITIVE), bool(set(words) & NEGATIVE)
    if positive and negative:
        return "mixed"
    return "positive" if positive else "negative" if negative else "unclear"


def summarize(posts: list[dict], symbols: list[str], now: datetime, coverage: list[dict]):
    universe = set(symbols)
    if not universe or len(universe) > 100 or any(
        not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", s) for s in universe
    ):
        raise ValueError("Provide 1 to 100 uppercase stock symbols")
    if now.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    buckets, seen = defaultdict(list), set()
    for post in posts[:300]:
        key = (post["platform"], post["id"])
        published = datetime.fromisoformat(post["published_at"])
        if published.tzinfo is None or not now - timedelta(hours=24) <= published <= now:
            continue
        if key in seen:
            continue
        seen.add(key)
        # Each post counts once per ticker. Multi-ticker sentences remain ambiguous.
        ticker_text = defaultdict(list)
        for sentence in re.split(r"[!?\n]|\.(?=\s|$)", post["text"]):
            found = set(CASHTAG.findall(sentence.upper())) & universe
            for ticker in found:
                ticker_text[ticker].append(sentence if len(found) == 1 else "")
        for ticker, sentences in ticker_text.items():
            buckets[ticker].append((post, tone(" ".join(sentences))))
    rows = []
    for ticker, entries in buckets.items():
        counts = Counter(label for _, label in entries)
        directional = counts["positive"] + counts["negative"]
        if counts["mixed"] or (counts["positive"] and counts["negative"]):
            sentiment = "mixed"
        elif directional >= 3 and directional / len(entries) >= 0.6:
            sentiment = "positive" if counts["positive"] else "negative"
        else:
            sentiment = "unclear"
        rows.append({
            "symbol": ticker, "mentions": len(entries),
            "unique_authors": len({(p["platform"], p["author"]) for p, _ in entries}),
            "sentiment": sentiment, "confidence": "low — keyword heuristic",
            "tone_counts": {k: counts[k] for k in ("positive", "negative", "mixed", "unclear")},
            "platform_counts": dict(Counter(p["platform"] for p, _ in entries)),
            "evidence": [{"url": p["url"], "published_at": p["published_at"], "tone": label}
                         for p, label in entries[:5]],
        })
    return {
        "schema": "tori.social.v1", "collected_at": now.isoformat(),
        "window_start": (now - timedelta(hours=24)).isoformat(),
        "symbols_checked": sorted(universe), "coverage": coverage,
        "ranking_scope": "Cashtags in fetched public posts for the supplied ticker list; "
                         "not a platform-wide ranking. No comments, video or audio analysis.",
        "sentiment_method": "Keyword heuristic; no sarcasm detection or spam verification. "
                            "Sentiment is discussion tone, not an entry signal.",
        "tickers": sorted(rows, key=lambda row: (-row["mentions"], row["symbol"])),
    }


def _get(url: str, token: str):
    request = Request(url, headers={
        "Authorization": "Bearer " + token, "User-Agent": "ToriTaurus/0.3 public research"
    })
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Response exceeded the scan limit")
        return json.loads(raw)
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}; check access, quota and entitlement") from None
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Public data request unavailable; private response omitted") from None


def collect(symbols: list[str], now: datetime, allow_paid_x: bool = False):
    # Validate before making any potentially billable requests.
    summarize([], symbols, now, [])
    posts, coverage = [], []
    reddit_token = os.environ.get("TORI_REDDIT_ACCESS_TOKEN", "").strip()
    x_token = os.environ.get("TORI_X_BEARER_TOKEN", "").strip()
    for community in ("pennystocks", "stocks"):
        source = "reddit/r/" + community
        if not reddit_token:
            coverage.append({"source": source, "status": "not configured", "posts": None})
            continue
        try:
            data = _get(f"https://oauth.reddit.com/r/{community}/new?limit=100", reddit_token)
            children = data["data"]["children"]
            for child in children[:100]:
                p = child["data"]
                posts.append({
                    "platform": "reddit", "id": p["id"], "author": p["author"],
                    "text": p["title"] + " " + p.get("selftext", ""),
                    "published_at": datetime.fromtimestamp(p["created_utc"], UTC).isoformat(),
                    "url": "https://www.reddit.com" + p["permalink"],
                })
            coverage.append({"source": source, "status": "sampled latest posts",
                             "posts": len(children[:100]), "limit": 100})
        except (ValueError, KeyError, TypeError, OverflowError):
            coverage.append({"source": source, "status": "unavailable; check API access",
                             "posts": None})
    if x_token and allow_paid_x:
        # One request, no pagination/retry. Limit query length before any paid read.
        query = "(" + " OR ".join("$" + s for s in sorted(set(symbols))) + ") lang:en -is:retweet"
        if len(query) > 512:
            coverage.append({"source": "x", "status": "ticker query too long", "posts": None})
        else:
            try:
                params = urlencode({"query": query, "max_results": 100,
                                    "tweet.fields": "created_at,author_id",
                                    "start_time": (now - timedelta(hours=24)).strftime(
                                        "%Y-%m-%dT%H:%M:%SZ")})
                data = _get("https://api.x.com/2/tweets/search/recent?" + params, x_token)
                for p in data.get("data", [])[:100]:
                    posts.append({"platform": "x", "id": p["id"], "author": p["author_id"],
                                  "text": p["text"], "published_at": p["created_at"],
                                  "url": "https://x.com/i/status/" + p["id"]})
                coverage.append({"source": "x", "status": "partial response" if data.get(
                    "errors") else "sampled recent posts", "posts": len(data.get("data", [])),
                    "limit": 100})
            except (ValueError, KeyError, TypeError):
                coverage.append({"source": "x", "status": "unavailable; check API access",
                                 "posts": None})
    else:
        coverage.append({"source": "x", "status": "paid reads disabled" if x_token else
                         "not configured", "posts": None})
    for source in ("discord", "kick", "tiktok"):
        coverage.append({"source": source, "status": "not connected", "posts": None})
    return summarize(posts, symbols, now, coverage)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded public social-buzz research")
    parser.add_argument("--symbols", required=True, help="Comma-separated uppercase stock symbols")
    parser.add_argument("--output", type=Path, required=True, help="Local JSON report path")
    parser.add_argument("--allow-paid-x", action="store_true", help="Allow one billed X request")
    args = parser.parse_args(argv)
    try:
        report = collect(args.symbols.split(","), datetime.now(UTC), args.allow_paid_x)
    except ValueError:
        parser.error("Provide 1 to 100 valid uppercase stock symbols")
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Social report saved. Review source coverage before interpreting ticker counts.")


if __name__ == "__main__":
    main()
