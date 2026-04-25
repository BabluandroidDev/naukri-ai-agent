from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import ApplicationLogRow


TRACKER_FIELDS = [
    "timestamp",
    "job_title",
    "company",
    "location",
    "experience",
    "url",
    "score",
    "decision",
    "status",
    "reason",
]


class ApplicationTracker:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_exists()

    def ensure_exists(self) -> None:
        if self.path.exists():
            return
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRACKER_FIELDS)
            writer.writeheader()

    def rows(self) -> list[dict[str, str]]:
        self.ensure_exists()
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def has_processed(self, url: str) -> bool:
        if not url:
            return False
        return any(row.get("url") == url for row in self.rows())

    def append(self, row: ApplicationLogRow) -> None:
        self.ensure_exists()
        data = row.model_dump()
        data["score"] = str(data.get("score", 0))
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRACKER_FIELDS)
            writer.writerow({field: data.get(field, "") for field in TRACKER_FIELDS})

    def recent(self, last: int = 50) -> list[dict[str, str]]:
        rows = self.rows()
        return rows[-last:]

    def count_today_submissions(self) -> int:
        today_prefix = date.today().isoformat()
        submitted_statuses = {
            "applied",
            "auto_submitted",
            "submitted",
            "maybe_submitted",
        }
        count = 0
        for row in self.rows():
            if not row.get("timestamp", "").startswith(today_prefix):
                continue
            status = row.get("status", "").strip().lower()
            if status in submitted_statuses:
                count += 1
        return count

    @staticmethod
    def print_rows(rows: Iterable[dict[str, str]]) -> None:
        rows = list(rows)
        if not rows:
            print("No rows found.")
            return
        widths = {
            "timestamp": 19,
            "score": 5,
            "decision": 20,
            "status": 20,
            "job_title": 32,
            "company": 24,
            "reason": 48,
        }
        headers = list(widths)
        print(" | ".join(header.ljust(widths[header]) for header in headers))
        print("-+-".join("-" * widths[header] for header in headers))
        for row in rows:
            values = []
            for header in headers:
                value = str(row.get(header, ""))
                if len(value) > widths[header]:
                    value = value[: widths[header] - 3] + "..."
                values.append(value.ljust(widths[header]))
            print(" | ".join(values))
