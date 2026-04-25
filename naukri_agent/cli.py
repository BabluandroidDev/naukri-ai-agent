from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from .browser_agent import NaukriBrowserAgent
from .matcher import JobMatcher
from .models import ApplicationLogRow
from .settings import load_settings
from .tracker import ApplicationTracker
from .utils import copy_if_missing, now_iso


PROJECT_FILES = [
    (".env.example", ".env"),
    ("profile.example.json", "profile.json"),
    ("answers.example.json", "answers.json"),
]


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd().resolve()
    created: list[str] = []
    skipped: list[str] = []
    for src_name, dst_name in PROJECT_FILES:
        src = root / src_name
        dst = root / dst_name
        if not src.exists():
            print(f"Missing template file: {src}")
            return 1
        if copy_if_missing(src, dst):
            created.append(dst_name)
        else:
            skipped.append(dst_name)

    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / ".gitkeep").touch(exist_ok=True)
    tracker = ApplicationTracker(data_dir / "applications.csv")
    tracker.ensure_exists()
    created.append("data/applications.csv" if len(tracker.rows()) == 0 else "data/applications.csv")

    print("Initialization complete.")
    if created:
        print("Created/verified:", ", ".join(created))
    if skipped:
        print("Already existed:", ", ".join(skipped))
    print("Next: edit .env, profile.json, answers.json, and config.yaml")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    settings = load_settings()
    NaukriBrowserAgent(settings).login()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    dry_run = settings.dry_run_default
    if args.no_dry_run:
        dry_run = False
    auto_submit = bool(args.auto_submit or settings.auto_submit_default)

    print(f"Mode: dry_run={dry_run}, auto_submit={auto_submit}")
    if not dry_run and not auto_submit:
        print("Final submission remains disabled. Use --auto-submit to allow safe matched submissions.")
    if dry_run and auto_submit:
        print("Dry-run is active, so --auto-submit will not submit anything.")

    tracker = ApplicationTracker(settings.tracker_path)
    browser = NaukriBrowserAgent(settings)
    matcher = JobMatcher(settings)

    jobs = browser.scan_jobs()
    if not jobs:
        print("No jobs found. Check config.yaml search_urls and login session.")
        return 0

    processed = 0
    skipped_duplicates = 0
    submitted_today = tracker.count_today_submissions()

    for job in jobs:
        if tracker.has_processed(job.url):
            skipped_duplicates += 1
            continue

        result = matcher.match(job)
        status = "not_applied"
        reason = result.reason

        can_attempt_apply = result.decision == "apply" and result.score >= settings.min_match_score
        if can_attempt_apply:
            if submitted_today >= settings.max_applications_per_day:
                status = "daily_limit_reached"
                reason = f"Daily application limit reached: {settings.max_applications_per_day}"
            else:
                outcome = browser.apply_to_job(job, result, dry_run=dry_run, auto_submit=auto_submit)
                status = outcome.status
                reason = f"{result.reason} | {outcome.reason}".strip(" |")
                if status in {"applied", "auto_submitted", "submitted", "maybe_submitted"}:
                    submitted_today += 1
        elif result.decision == "needs_manual_review":
            status = "needs_manual_review"
        else:
            status = "skipped"

        tracker.append(
            ApplicationLogRow(
                timestamp=now_iso(),
                job_title=job.title,
                company=job.company,
                location=job.location,
                experience=job.experience,
                url=job.url,
                score=result.score,
                decision=result.decision,
                status=status,
                reason=reason,
            )
        )
        processed += 1
        print(f"[{processed}] {result.score:3d} {result.decision:20s} {status:24s} {job.title} - {job.company}")
        time.sleep(max(0, settings.delay_seconds_between_jobs))

    print(f"Done. Processed={processed}, duplicate_skips={skipped_duplicates}, log={settings.tracker_path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    settings = load_settings()
    tracker = ApplicationTracker(settings.tracker_path)
    tracker.print_rows(tracker.recent(args.last))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local AI job-application assistant for Naukri")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create .env, profile.json, answers.json, and tracker CSV")
    init_parser.set_defaults(func=cmd_init)

    login_parser = subparsers.add_parser("login", help="Open visible browser for manual Naukri login")
    login_parser.set_defaults(func=cmd_login)

    run_parser = subparsers.add_parser("run", help="Scan, score, and optionally apply to jobs")
    run_parser.add_argument("--no-dry-run", action="store_true", help="Perform live browser flow checks")
    run_parser.add_argument("--auto-submit", action="store_true", help="Allow final submission for safe matched jobs")
    run_parser.set_defaults(func=cmd_run)

    report_parser = subparsers.add_parser("report", help="Print recent tracker rows")
    report_parser.add_argument("--last", type=int, default=50, help="Number of recent rows to print")
    report_parser.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
