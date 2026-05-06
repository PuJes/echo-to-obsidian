from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_REPORT = Path.cwd() / "echo2obs-batch-report.json"
MEDIA_EXTENSIONS = {".mp3", ".m4a", ".wav", ".mp4", ".mov", ".aac", ".flac", ".mkv"}
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


@dataclass
class BatchItem:
    source: str
    label: str
    source_file: str | None = None
    title: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="echo2obs-batch",
        description="Batch transcription from media directories or markdown links.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--from-dir", help="Directory (or single file) to scan for media")
    source_group.add_argument("--from-md", help="Markdown file or directory to scan for video links")
    parser.add_argument("--limit", type=int, help="Maximum number of items to process")
    parser.add_argument("--match", help="Keyword filter over title, label and source")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output files")
    parser.add_argument("--language", help="Language hint, for example zh")
    parser.add_argument(
        "--model-size",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size",
    )
    parser.add_argument("--output-dir", help="Output directory for notes")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help=f"Batch report path (default: {DEFAULT_REPORT})")
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve()


def collect_media_files(root: Path) -> list[BatchItem]:
    if root.is_file():
        if root.suffix.lower() not in MEDIA_EXTENSIONS:
            return []
        return [BatchItem(source=str(root), label=root.name, title=root.stem)]

    items: list[BatchItem] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        label = str(path.relative_to(root))
        items.append(BatchItem(source=str(path), label=label, title=path.stem))
    return items


def normalize_url(url: str) -> str:
    return url.rstrip(".,;)]}>")


def collect_urls_from_markdown(root: Path) -> list[BatchItem]:
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    found: list[BatchItem] = []
    seen: set[str] = set()

    for file_path in files:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for raw_url in URL_PATTERN.findall(text):
            url = normalize_url(raw_url)
            if not any(domain in url for domain in ("bilibili.com/video", "b23.tv/", "youtube.com/watch", "youtu.be/")):
                continue
            if url in seen:
                continue
            seen.add(url)
            found.append(
                BatchItem(
                    source=url,
                    label=f"{file_path.stem} -> {url}",
                    source_file=str(file_path),
                    title=file_path.stem,
                )
            )
    return found


def filter_items(items: list[BatchItem], match: str | None, limit: int | None) -> list[BatchItem]:
    filtered = items
    if match:
        lowered = match.lower()
        filtered = [
            item
            for item in filtered
            if lowered in item.label.lower()
            or lowered in item.source.lower()
            or (item.source_file and lowered in item.source_file.lower())
            or (item.title and lowered in item.title.lower())
        ]
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


def build_command(item: BatchItem, args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-m", "echo_to_obsidian.cli", item.source, "--model-size", args.model_size]
    if args.language:
        command.extend(["--language", args.language])
    if args.output_dir:
        command.extend(["--output-dir", str(resolve_path(args.output_dir))])
    if args.overwrite:
        command.append("--overwrite")
    if item.title:
        command.extend(["--title", item.title])
    return command


def run_batch(items: list[BatchItem], args: argparse.Namespace) -> list[dict[str, str | int]]:
    results: list[dict[str, str | int]] = []
    for index, item in enumerate(items, start=1):
        row: dict[str, str | int] = {
            "index": index,
            "item": item.source,
            "label": item.label,
            "status": "pending",
        }
        if item.source_file:
            row["source_file"] = item.source_file
        if item.title:
            row["title"] = item.title

        command = build_command(item, args)
        row["command"] = " ".join(command)

        if args.dry_run:
            row["status"] = "preview"
            results.append(row)
            continue

        completed = subprocess.run(command, text=True, capture_output=True)
        row["status"] = "success" if completed.returncode == 0 else "failed"
        row["returncode"] = completed.returncode
        if completed.stdout.strip():
            row["stdout"] = completed.stdout.strip()
        if completed.stderr.strip():
            row["stderr"] = completed.stderr.strip()
        results.append(row)
    return results


def write_report(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    report_path = resolve_path(args.report)

    if args.from_dir:
        source_root = resolve_path(args.from_dir)
        items = collect_media_files(source_root)
        source_mode = "directory"
    else:
        source_root = resolve_path(args.from_md)
        items = collect_urls_from_markdown(source_root)
        source_mode = "markdown"

    selected = filter_items(items, args.match, args.limit)
    results = run_batch(selected, args)

    payload = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_mode": source_mode,
        "source_root": str(source_root),
        "total_found": len(items),
        "total_selected": len(selected),
        "dry_run": args.dry_run,
        "results": results,
    }
    write_report(report_path, payload)

    print(f"Report: {report_path}")
    print(f"Found: {len(items)}")
    print(f"Selected: {len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
