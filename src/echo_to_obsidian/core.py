from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".webm", ".3gp"}
DEFAULT_OUTPUT_DIR = Path.cwd() / "transcripts"
URL_PREFIXES = ("http://", "https://")


@dataclass
class SourceInfo:
    title: str
    source: str
    local_media_path: Path
    duration_seconds: float | None


@dataclass
class TranscribeOptions:
    source: str
    title: str | None = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    language: str | None = None
    model_size: str = "small"
    device: str = "auto"
    compute_type: str = "int8"
    overwrite: bool = False
    keep_temp: bool = False


@dataclass
class TranscribeResult:
    markdown_path: Path
    json_path: Path
    attachment_path: Path
    title: str
    source: str


def is_url(value: str) -> bool:
    return value.startswith(URL_PREFIXES)


def run(
    cmd: list[str],
    *,
    capture_output: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=capture_output,
        env=env,
    )


def require_binary(name: str) -> None:
    result = subprocess.run(["/usr/bin/env", "bash", "-lc", f"command -v {name} >/dev/null"])
    if result.returncode != 0:
        raise RuntimeError(f"Missing dependency: {name}")


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[/:*?\"<>|]", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:120] or "untitled-transcript"


def format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def clear_proxy_env(env: dict[str, str]) -> dict[str, str]:
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    return env


def probe_duration(path: Path) -> float | None:
    try:
        result = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def download_media(url: str, temp_dir: Path) -> SourceInfo:
    require_binary("yt-dlp")
    output_template = str(temp_dir / "source.%(ext)s")
    clean_env = clear_proxy_env(os.environ.copy())
    try:
        result = run(
            [
                "yt-dlp",
                "--ignore-config",
                "--proxy",
                "",
                "--no-playlist",
                "-f",
                "bestaudio/best",
                "-o",
                output_template,
                "--print",
                "title",
                "--print",
                "after_move:filepath",
                url,
            ],
            env=clean_env,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        raise RuntimeError(f"Download failed: {detail}") from exc
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError("Download failed: title or file path missing")
    title = lines[-2]
    media_path = Path(lines[-1])
    return SourceInfo(
        title=title,
        source=url,
        local_media_path=media_path,
        duration_seconds=probe_duration(media_path),
    )


def prepare_local_source(path_str: str) -> SourceInfo:
    media_path = Path(path_str).expanduser().resolve()
    if not media_path.exists():
        raise RuntimeError(f"File not found: {media_path}")
    return SourceInfo(
        title=media_path.stem,
        source=str(media_path),
        local_media_path=media_path,
        duration_seconds=probe_duration(media_path),
    )


def extract_audio(source_path: Path, target_wav: Path) -> None:
    require_binary("ffmpeg")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(target_wav),
        ],
        capture_output=True,
    )


def export_attachment_audio(source_path: Path, target_audio: Path) -> None:
    require_binary("ffmpeg")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(target_audio),
        ],
        capture_output=True,
    )


def prepare_attachment_file(
    *,
    source_media_path: Path,
    output_dir: Path,
    title: str,
) -> tuple[Path, str]:
    attachments_dir = output_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(title)

    if source_media_path.suffix.lower() in AUDIO_EXTENSIONS:
        attachment_path = attachments_dir / f"{safe_name}{source_media_path.suffix.lower()}"
        shutil.copy2(source_media_path, attachment_path)
    else:
        attachment_path = attachments_dir / f"{safe_name}.m4a"
        export_attachment_audio(source_media_path, attachment_path)

    relative_link = f"attachments/{attachment_path.name}"
    return attachment_path, relative_link


def transcribe_audio(
    wav_path: Path,
    *,
    model_size: str,
    device: str,
    compute_type: str,
    language: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    clear_proxy_env(os.environ)
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(wav_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )

    rows: list[dict[str, Any]] = []
    for segment in segments:
        rows.append(
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
            }
        )

    meta = {
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration_after_vad": getattr(info, "duration_after_vad", None),
    }
    return rows, meta


def build_markdown(
    *,
    title: str,
    source: str,
    created_at: str,
    duration_seconds: float | None,
    model_size: str,
    language: str | None,
    audio_embed_link: str,
    segments: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Transcript: {title}",
        "",
        f"- Source: {source}",
        f"- Transcribed At: {created_at}",
        f"- Model: faster-whisper / {model_size}",
        f"- Language: {language or 'auto-detect'}",
        f"- Duration: {format_ts(duration_seconds)}" if duration_seconds else "- Duration: unknown",
        "",
        "## Audio",
        "",
        f"![[{audio_embed_link}]]",
        "",
        "## Timestamped Transcript",
        "",
    ]

    for segment in segments:
        if not segment["text"]:
            continue
        timestamp = format_ts(segment["start"])
        lines.append(f"[[{audio_embed_link}#t={int(segment['start'])}|{timestamp}]] {segment['text']}")

    lines.append("")
    return "\n".join(lines)


def write_outputs(
    *,
    output_dir: Path,
    title: str,
    markdown: str,
    payload: dict[str, Any],
    overwrite: bool,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(title)
    md_path = output_dir / f"{safe_name}.md"
    json_path = output_dir / f"{safe_name}.json"

    if not overwrite and (md_path.exists() or json_path.exists()):
        raise RuntimeError(f"Target exists. Use --overwrite: {md_path.name}")

    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def transcribe_source(options: TranscribeOptions) -> TranscribeResult:
    output_dir = options.output_dir.expanduser().resolve()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="echo2obs-") as temp_name:
        temp_dir = Path(temp_name)
        source = download_media(options.source, temp_dir) if is_url(options.source) else prepare_local_source(options.source)
        title = options.title or source.title
        wav_path = temp_dir / "audio.wav"

        extract_audio(source.local_media_path, wav_path)
        attachment_path, audio_embed_link = prepare_attachment_file(
            source_media_path=source.local_media_path,
            output_dir=output_dir,
            title=title,
        )
        segments, model_meta = transcribe_audio(
            wav_path,
            model_size=options.model_size,
            device=options.device,
            compute_type=options.compute_type,
            language=options.language,
        )

        markdown = build_markdown(
            title=title,
            source=source.source,
            created_at=created_at,
            duration_seconds=source.duration_seconds,
            model_size=options.model_size,
            language=model_meta.get("language") or options.language,
            audio_embed_link=audio_embed_link,
            segments=segments,
        )

        payload = {
            "title": title,
            "source": source.source,
            "created_at": created_at,
            "media_path": str(source.local_media_path),
            "attachment_path": str(attachment_path),
            "attachment_embed": audio_embed_link,
            "duration_seconds": source.duration_seconds,
            "model": {
                "name": options.model_size,
                "device": options.device,
                "compute_type": options.compute_type,
            },
            "transcribe_meta": model_meta,
            "segments": segments,
        }

        md_path, json_path = write_outputs(
            output_dir=output_dir,
            title=title,
            markdown=markdown,
            payload=payload,
            overwrite=options.overwrite,
        )

        if options.keep_temp:
            kept_dir = output_dir / "_temp"
            kept_dir.mkdir(parents=True, exist_ok=True)
            kept_wav = kept_dir / f"{sanitize_filename(title)}.wav"
            kept_wav.write_bytes(wav_path.read_bytes())

    return TranscribeResult(
        markdown_path=md_path,
        json_path=json_path,
        attachment_path=attachment_path,
        title=title,
        source=source.source,
    )
