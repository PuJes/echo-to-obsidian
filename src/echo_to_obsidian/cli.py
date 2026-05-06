from __future__ import annotations

import argparse
import sys
from pathlib import Path

from echo_to_obsidian.core import DEFAULT_OUTPUT_DIR, TranscribeOptions, transcribe_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="echo2obs",
        description="Local media transcription to Obsidian markdown with embedded audio and timestamp links.",
    )
    parser.add_argument("source", help="Local media path or public video URL")
    parser.add_argument("--title", help="Override note title")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--language", help="Language hint, for example zh or en")
    parser.add_argument(
        "--model-size",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu"],
        help="Inference device",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="faster-whisper compute type",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output files if they exist")
    parser.add_argument("--keep-temp", action="store_true", help="Keep extracted WAV file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    options = TranscribeOptions(
        source=args.source,
        title=args.title,
        output_dir=Path(args.output_dir),
        language=args.language,
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
        overwrite=args.overwrite,
        keep_temp=args.keep_temp,
    )

    try:
        result = transcribe_source(options)
    except KeyboardInterrupt:
        print("Canceled", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Markdown: {result.markdown_path}")
    print(f"JSON: {result.json_path}")
    print(f"Audio: {result.attachment_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
