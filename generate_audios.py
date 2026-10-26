#!/usr/bin/env python3
"""Generate WAV files from text or JSON files, skipping existing audio."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

from tqdm import tqdm

from utilities import AudioGenerationError, generate_audio, redact

DEFAULT_MODEL = "fish-audio/s2.1-pro-free:free"


class GenerateAudiosError(Exception):
    """An input or batch generation error that can be displayed to the user."""


def _read_text(source):
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise GenerateAudiosError(f"Cannot read '{source}': {exc}") from None
    if source.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise GenerateAudiosError(f"Invalid JSON in '{source}': {exc}") from None
        text = data.get("normalized_text") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise GenerateAudiosError(
                f"'{source}' must contain a non-empty string field 'normalized_text'."
            )
    elif not text.strip():
        raise GenerateAudiosError(f"'{source}' must contain text.")
    return text


def _source_key(source):
    if source.stem.isdecimal():
        return (0, int(source.stem), source.name)
    return (1, source.name.casefold(), source.name)


def _select_sources(text_dir, start_idx, end_idx):
    sources = []
    for source in text_dir.iterdir():
        if not source.is_file() or source.suffix.lower() not in (".txt", ".json"):
            continue
        if start_idx is not None or end_idx is not None:
            if not source.stem.isdecimal():
                continue
            index = int(source.stem)
            if start_idx is not None and index < start_idx:
                continue
            if end_idx is not None and index > end_idx:
                continue
        sources.append(source)
    return sorted(sources, key=_source_key)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate WAV audio from .txt files or JSON normalized_text fields.",
        allow_abbrev=False,
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Full OpenRouter speech model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--voice", help="Provider voice ID; omit for provider default")
    parser.add_argument("--response-format", choices=("mp3", "pcm"), default="mp3",
                        help="API audio format; use pcm for Gemini TTS (default: mp3)")
    parser.add_argument("--timeout", type=float, default=180,
                        help="HTTP timeout per file in seconds (default: 180)")
    parser.add_argument("--text-dir", type=Path, required=True,
                        help="Directory containing .txt and/or .json input files")
    parser.add_argument("--save-dir", type=Path, required=True,
                        help="Destination directory for .wav files; existing files are skipped")
    parser.add_argument("--start-idx", type=int,
                        help="First numeric filename index to include (inclusive)")
    parser.add_argument("--end-idx", type=int,
                        help="Last numeric filename index to include (inclusive)")
    args = parser.parse_args(argv)
    try:
        model = args.model.strip()
        if "/" not in model or any(char.isspace() for char in model):
            raise GenerateAudiosError("--model must be a full OpenRouter provider/model ID.")
        if args.voice is not None and not args.voice.strip():
            raise GenerateAudiosError("--voice must not be empty.")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise GenerateAudiosError("--timeout must be a finite positive number.")
        if args.start_idx is not None and args.start_idx < 0:
            raise GenerateAudiosError("--start-idx must be non-negative.")
        if args.end_idx is not None and args.end_idx < 0:
            raise GenerateAudiosError("--end-idx must be non-negative.")
        if (args.start_idx is not None and args.end_idx is not None
                and args.end_idx < args.start_idx):
            raise GenerateAudiosError("--end-idx must be at least --start-idx.")

        text_dir = args.text_dir.expanduser().absolute()
        save_dir = args.save_dir.expanduser().absolute()
        if not text_dir.is_dir():
            raise GenerateAudiosError(f"--text-dir '{text_dir}' must be an existing directory.")
        sources = _select_sources(text_dir, args.start_idx, args.end_idx)
        if not sources:
            raise GenerateAudiosError(f"No .txt or .json files match the selection in '{text_dir}'.")

        pending = []
        destinations = {}
        skipped = 0
        for source in sources:
            output = save_dir / f"{source.stem}.wav"
            if output in destinations:
                raise GenerateAudiosError(
                    f"'{destinations[output].name}' and '{source.name}' both map to '{output.name}'."
                )
            destinations[output] = source
            if output.is_dir():
                raise GenerateAudiosError(f"'{output}' must be a file path, not a directory.")
            if os.path.lexists(output):
                skipped += 1
            else:
                pending.append((source, output, _read_text(source)))

        if pending:
            if not shutil.which("ffmpeg"):
                raise GenerateAudiosError("WAV output requires FFmpeg on PATH.")
            save_dir.mkdir(parents=True, exist_ok=True)
            # Check write permission before making a paid request.
            with tempfile.TemporaryFile(dir=save_dir):
                pass

        saved = 0
        with tqdm(total=len(sources), initial=skipped, desc="Generating audio",
                  unit="file", dynamic_ncols=True, file=sys.stderr) as progress:
            for source, output, text in pending:
                if output.is_dir():
                    raise GenerateAudiosError(f"'{output}' must be a file path, not a directory.")
                if os.path.lexists(output):
                    skipped += 1
                    progress.update(1)
                    continue
                try:
                    generate_audio(model, args.voice, text, 1.0, output,
                                   timeout=args.timeout, response_format=args.response_format)
                except AudioGenerationError as exc:
                    if os.path.lexists(output) and not output.is_dir():
                        # Another writer may have completed this audio during the request.
                        skipped += 1
                    else:
                        raise GenerateAudiosError(f"'{source.name}': {exc}") from None
                else:
                    saved += 1
                progress.update(1)
        print(f"Saved {saved} WAV files to {save_dir}; skipped {skipped} existing files.")
        return 0
    except (GenerateAudiosError, OSError) as exc:
        print(f"Error: {redact(str(exc))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
