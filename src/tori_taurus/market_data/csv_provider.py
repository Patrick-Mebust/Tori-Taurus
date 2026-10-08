"""CSV replay adapter. Never represents imported records as live quotes."""

import csv
from datetime import datetime
from pathlib import Path

from .models import Bar, Quote, symbol, utc


class CsvProvider:
    def __init__(self, quotes_path: Path, bars_path: Path):
        self.quotes = self._read(quotes_path, Quote)
        self.bars = self._read(bars_path, Bar)
        keys = [(b.symbol, b.timestamp, b.interval) for b in self.bars]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate bar")

    @staticmethod
    def _read(path, model):
        records = []
        with Path(path).open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                row["timestamp"] = datetime.fromisoformat(row["timestamp"])
                if model is Bar:
                    row["volume"] = int(row["volume"])
                row["source"] = "csv"
                row["mode"] = "replay"
                records.append(model(**row))
        return records

    def get_quote(self, ticker: str) -> Quote:
        ticker = symbol(ticker)
        matches = [q for q in self.quotes if q.symbol == ticker]
        if not matches:
            raise LookupError("No quote for ticker")
        return max(matches, key=lambda q: q.timestamp)

    def get_bars(
        self, ticker: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> list[Bar]:
        ticker, start, end = symbol(ticker), utc(start), utc(end)
        if start >= end:
            raise ValueError("Start must precede end")
        if interval not in {"1m", "5m", "15m", "1h", "1d"}:
            raise ValueError("Unsupported interval")
        return sorted(
            (
                b
                for b in self.bars
                if b.symbol == ticker and b.interval == interval and start <= b.timestamp < end
            ),
            key=lambda b: b.timestamp,
        )
