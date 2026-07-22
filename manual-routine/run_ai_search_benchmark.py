#!/usr/bin/env python3
"""Run the AI-search benchmark with browser-assisted, human review.

This runner never supplies credentials, bypasses challenges, or determines
whether a description is accurate. It opens each platform with Playwright CLI,
saves a screenshot after the reviewer has submitted the question, and records
the reviewer's answers in the CSV.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "manual-routine" / "ai-search-benchmark.csv"
PLATFORMS = ("google_ai", "chatgpt", "perplexity", "bing_copilot")
PLATFORM_LABELS = {
    "google_ai": "Google AI results",
    "chatgpt": "ChatGPT",
    "perplexity": "Perplexity",
    "bing_copilot": "Bing/Copilot",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Benchmark CSV path.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Run date (YYYY-MM-DD).")
    parser.add_argument("--country", default="", help="Country or region for this run.")
    parser.add_argument(
        "--session-mode",
        default="signed-out/private",
        help="Browser context, such as signed-out/private.",
    )
    parser.add_argument(
        "--platform",
        choices=PLATFORMS,
        action="append",
        help="Run only this platform; repeat to select several.",
    )
    parser.add_argument("--session", default="ai-benchmark", help="Playwright CLI session name.")
    parser.add_argument("--dry-run", action="store_true", help="List planned checks without opening a browser.")
    return parser.parse_args()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def ensure_run_rows(
    fields: list[str], rows: list[dict[str, str]], run_date: str, country: str, session_mode: str
) -> list[dict[str, str]]:
    questions = list(dict.fromkeys(row["exact_question"] for row in rows if row["exact_question"]))
    run_rows = [row for row in rows if row["run_date"] == run_date]
    if run_rows:
        return run_rows

    blank_rows = [row for row in rows if not row["run_date"]]
    if blank_rows:
        run_rows = blank_rows
    else:
        run_rows = [{field: "" for field in fields} for _ in questions]
        for row, question in zip(run_rows, questions, strict=True):
            row["exact_question"] = question
        rows.extend(run_rows)

    for row in run_rows:
        row["run_date"] = run_date
        row["country_or_region"] = country
        row["session_mode"] = session_mode
    return run_rows


def command(session: str, *args: str) -> None:
    subprocess.run(["playwright-cli", f"-s={session}", *args], check=True)


def destination(platform: str, question: str) -> str:
    query = quote_plus(question)
    if platform == "google_ai":
        return f"https://www.google.com/search?q={query}"
    if platform == "bing_copilot":
        return f"https://www.bing.com/search?q={query}"
    if platform == "chatgpt":
        return "https://chatgpt.com/"
    return "https://www.perplexity.ai/"


def prompt_yes_no(label: str) -> str:
    while True:
        answer = input(f"{label} [y/n]: ").strip().lower()
        if answer in {"y", "yes"}:
            return "yes"
        if answer in {"n", "no"}:
            return "no"
        print("Enter y or n.")


def screenshot_path(run_date: str, platform: str, index: int) -> Path:
    directory = ROOT / "benchmark" / "screenshots" / run_date / platform
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{index:02d}.png"


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    fields, rows = read_rows(args.csv)
    if not fields or "exact_question" not in fields:
        raise ValueError(f"{args.csv} is not a valid benchmark CSV.")
    platforms = tuple(args.platform or PLATFORMS)
    run_rows = ensure_run_rows(fields, rows, args.date, args.country, args.session_mode)

    if args.dry_run:
        for platform in platforms:
            for index, row in enumerate(run_rows, start=1):
                print(f"{platform}: {index:02d}. {row['exact_question']}")
        return 0

    command(args.session, "open", "--persistent")
    for platform in platforms:
        print(f"\n--- {PLATFORM_LABELS[platform]} ---")
        for index, row in enumerate(run_rows, start=1):
            question = row["exact_question"]
            print(f"\n{index:02d}. {question}")
            command(args.session, "goto", destination(platform, question))
            if platform in {"chatgpt", "perplexity"}:
                print("Paste the question into the site and submit it yourself.")
            input("Press Enter after the complete result is visible (or Ctrl-C to stop): ")
            shot = screenshot_path(args.date, platform, index)
            command(args.session, "screenshot", "--filename", str(shot))
            row[f"{platform}_cited"] = prompt_yes_no("Was Mushin cited?")
            row[f"{platform}_linked"] = prompt_yes_no("Was Mushin linked?")
            row[f"{platform}_accurate"] = prompt_yes_no("Was the description accurate?")
            note = input("Notes (optional): ").strip()
            if note:
                row["notes"] = f"{row['notes']} | {PLATFORM_LABELS[platform]}: {note}".strip(" |")
            previous = row["screenshot_paths"]
            row["screenshot_paths"] = f"{previous}; {shot.relative_to(ROOT)}".strip("; ")
            write_rows(args.csv, fields, rows)

    print(f"\nSaved benchmark results to {args.csv}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, KeyboardInterrupt) as error:
        print(f"Benchmark stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
