#!/usr/bin/env python3
"""Generate N Vietnamese and N English WAVs for every configured voice."""

import argparse
from collections import Counter, defaultdict, deque
from contextlib import nullcontext
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import NamedTuple
from uuid import UUID, uuid4
import wave

try:
    from tqdm import tqdm
except ModuleNotFoundError as exc:
    if exc.name != "tqdm":
        raise
    tqdm = None

from modules.utilities import AudioGenerationError, generate_audio, redact


GEMINI_VOICES = (
    "Kore", "Puck", "Charon", "Zephyr", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe",
)
ELEVEN_VOICES = (
    "george", "sarah", "adam", "alice", "bella", "brian", "charlie", "daniel",
    "jessica", "laura",
)
MINIMAX_VOICES = (
    "English_expressive_narrator", "English_radiant_girl", "English_magnetic_voiced_man",
    "English_compelling_lady1", "English_Aussie_Bloke", "English_captivating_female1",
    "English_Upbeat_Woman", "English_Trustworth_Man", "English_CalmWoman",
    "English_Gentle-voiced_man",
)


class ModelPreset(NamedTuple):
    model: str
    response_format: str
    voices: tuple[str, ...]


# The ten-model comparison set; 84 voice profiles in total.
MODEL_PRESETS = (
    ModelPreset("google/gemini-3.8-flash-tts", "pcm", GEMINI_VOICES),
    ModelPreset("google/gemini-3.8-flash-lite-tts", "pcm", GEMINI_VOICES),
    ModelPreset("google/gemini-3.1-flash-tts-preview", "pcm", GEMINI_VOICES),
    ModelPreset("elevenlabs/eleven-v4", "mp3", ELEVEN_VOICES),
    ModelPreset("elevenlabs/eleven-v4-turbo", "mp3", ELEVEN_VOICES),
    ModelPreset("elevenlabs/eleven-v3", "mp3", ELEVEN_VOICES),
    ModelPreset("microsoft/mai-voice-2.1", "mp3", (
        "vi-VN-Grant:MAI-Voice-2.1", "vi-VN-Harper:MAI-Voice-2.1",
    )),
    ModelPreset("microsoft/mai-voice-2.1-flash", "mp3", (
        "vi-VN-Grant:MAI-Voice-2.1-Flash", "vi-VN-Harper:MAI-Voice-2.1-Flash",
    )),
    ModelPreset("minimax/speech-2.8-hd", "mp3", MINIMAX_VOICES),
    ModelPreset("minimax/speech-2.8-turbo", "mp3", MINIMAX_VOICES),
)


class BatchGenerationError(Exception):
    """A batch input, output, or generation failure."""


class Job(NamedTuple):
    model: str
    text: str
    voice: str
    response_format: str

    @property
    def key(self):
        return self.model, self.text, self.voice


def _read_texts(metadata_path, count):
    """Keep CSV order and whitespace; select VI from the top and EN from the bottom."""
    values = {"vi": [], "en": []}
    try:
        with metadata_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if (reader.fieldnames is None or
                    any(reader.fieldnames.count(lang) != 1 for lang in values)):
                raise BatchGenerationError("--metadata-path must be a CSV with 'en' and 'vi' columns.")
            for row in reader:
                if None in row:
                    raise BatchGenerationError(f"CSV row ending at line {reader.line_num} has extra fields.")
                for lang in values:
                    text = row.get(lang)
                    if text is not None and text.strip():
                        values[lang].append(text)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise BatchGenerationError(f"Cannot read --metadata-path '{metadata_path}': {exc}") from None

    for lang, texts in values.items():
        if len(texts) < count:
            raise BatchGenerationError(
                f"The CSV has only {len(texts)} non-empty '{lang}' texts; {count} are required."
            )
    return {"vi": values["vi"][:count], "en": values["en"][-count:][::-1]}


def _build_jobs(texts):
    for preset in MODEL_PRESETS:
        for profile in preset.voices:
            for lang in ("vi", "en"):
                voice = profile
                if preset.model.startswith("microsoft/") and lang == "en":
                    # MAI's locale controls the spoken language, even for the same speaker.
                    voice = profile.replace("vi-VN-", "en-US-", 1)
                for text in texts[lang]:
                    yield Job(preset.model, text, voice, preset.response_format)


def _valid_wav(path):
    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            if frames <= 0 or audio.getframerate() <= 0:
                return False
            frame_size = audio.getnchannels() * audio.getsampwidth()
            # Detect truncated files without loading the entire recording into memory.
            while frames:
                chunk = min(frames, 8192)
                if len(audio.readframes(chunk)) != chunk * frame_size:
                    return False
                frames -= chunk
        return True
    except (OSError, EOFError, wave.Error):
        return False


def _scan_existing(audio_dir, metadata_dir):
    """Count completed jobs as a multiset so repeated CSV text is still recorded N times."""
    completed = Counter()
    incomplete = defaultdict(deque)
    ignored = 0
    for path in sorted(metadata_dir.glob("*.json")):
        try:
            identifier = UUID(path.stem)
            if identifier.version != 4 or str(identifier) != path.stem:
                raise ValueError("Expected a UUIDv4 filename")
            data = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(data, dict) or set(data) != {"model", "text", "voice"} or
                    not all(isinstance(value, str) and value.strip() for value in data.values())):
                raise ValueError("Invalid recording metadata")
        except (OSError, UnicodeError, ValueError):
            ignored += 1
            continue
        key = data["model"], data["text"], data["voice"]
        audio_path = audio_dir / f"{path.stem}.wav"
        if audio_path.is_dir():
            raise BatchGenerationError(f"Expected a WAV file, found a directory: '{audio_path}'.")
        if _valid_wav(audio_path):
            completed[key] += 1
        else:
            incomplete[key].append(path.stem)
    if ignored:
        message = f"Ignored {ignored} unreadable or invalid metadata files."
        if tqdm is None:
            print(message, file=sys.stderr)
        else:
            tqdm.write(message, file=sys.stderr)
    return completed, incomplete


def _write_metadata(path, job):
    data = {"model": job.model, "text": job.text, "voice": job.voice}
    # Publish complete JSON before making the speech request. A failed request leaves
    # enough information to reuse the UUID on the next --resume run.
    with tempfile.TemporaryDirectory(prefix=".metadata-", dir=path.parent) as tmp:
        temporary = Path(tmp) / "recording.json"
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.link(temporary, path)


def _generate_recording(job, identifier, audio_dir, metadata_dir):
    if identifier is None:
        while True:
            identifier = str(uuid4())
            if (not os.path.lexists(audio_dir / f"{identifier}.wav") and
                    not os.path.lexists(metadata_dir / f"{identifier}.json")):
                break
        _write_metadata(metadata_dir / f"{identifier}.json", job)
    audio_path = audio_dir / f"{identifier}.wav"
    generate_audio(
        job.model, job.voice, job.text, 1.0, audio_path,
        timeout=180, response_format=job.response_format,
        overwrite=os.path.lexists(audio_path),
    )
    if not _valid_wav(audio_path):
        raise BatchGenerationError(f"Generation did not produce a complete WAV: '{audio_path}'.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate N Vietnamese and N English WAVs for each of 84 voice profiles.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--part-num-audios", type=int, required=True, metavar="N",
        help="Recordings per language per voice: N Vietnamese plus N English",
    )
    parser.add_argument(
        "--metadata-path", type=Path, required=True, metavar="CSV",
        help="UTF-8 CSV with en and vi columns; VI reads top-down, EN bottom-up",
    )
    parser.add_argument("--save-path", type=Path, required=True, metavar="DIR",
                        help="Output root for audios/<uuid>.wav and metadatas/<uuid>.json")
    parser.add_argument("--resume", action="store_true",
                        help="Skip complete WAV/JSON pairs and retry incomplete recordings")
    args = parser.parse_args(argv)
    try:
        if args.part_num_audios < 1:
            raise BatchGenerationError("--part-num-audios must be at least 1.")
        texts = _read_texts(args.metadata_path.expanduser().absolute(), args.part_num_audios)
        jobs = list(_build_jobs(texts))
        save_path = args.save_path.expanduser().absolute()
        audio_dir = save_path / "audios"
        metadata_dir = save_path / "metadatas"
        for directory in (audio_dir, metadata_dir):
            directory.mkdir(parents=True, exist_ok=True)
        if not args.resume and any(any(directory.iterdir()) for directory in (audio_dir, metadata_dir)):
            raise BatchGenerationError(
                "Output already contains recordings; use --resume or choose a different --save-path."
            )

        completed, incomplete = _scan_existing(audio_dir, metadata_dir)
        pending = []
        skipped = 0
        for job in jobs:
            if completed[job.key]:
                completed[job.key] -= 1
                skipped += 1
            else:
                identifier = incomplete[job.key].popleft() if incomplete[job.key] else None
                pending.append((job, identifier))
        if pending:
            if not shutil.which("ffmpeg"):
                raise BatchGenerationError("WAV output requires FFmpeg on PATH.")
            for directory in (audio_dir, metadata_dir):
                with tempfile.TemporaryFile(dir=directory):
                    pass

        print(
            f"Target: {len(jobs)} WAV/JSON pairs; {args.part_num_audios} VI + "
            f"{args.part_num_audios} EN per voice. Complete: {skipped}; remaining: {len(pending)}.",
            flush=True,
        )
        saved = 0
        progress_context = (
            tqdm(total=len(jobs), initial=skipped, desc="Generating audio", unit="file",
                 dynamic_ncols=True, file=sys.stderr)
            if tqdm is not None else nullcontext()
        )
        with progress_context as progress:
            for job, identifier in pending:
                if progress is not None:
                    progress.set_postfix_str(f"{job.model} / {job.voice}", refresh=False)
                try:
                    _generate_recording(job, identifier, audio_dir, metadata_dir)
                except AudioGenerationError as exc:
                    raise BatchGenerationError(f"{job.model} / {job.voice}: {exc}") from None
                saved += 1
                if progress is not None:
                    progress.update(1)
                else:
                    print(
                        f"Generating audio: {skipped + saved}/{len(jobs)} "
                        f"{job.model} / {job.voice}", file=sys.stderr, flush=True,
                    )
        print(f"Saved {saved} recordings to {save_path}; skipped {skipped} complete pairs.")
        return 0
    except (BatchGenerationError, OSError) as exc:
        print(f"Error: {redact(str(exc))}\nRerun with --resume to continue.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled. Rerun with --resume to continue.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
