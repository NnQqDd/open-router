#!/usr/bin/env python3
"""Generate speech with OpenRouter. Load OPEN_ROUTER_KEY from .env."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("Install the dependency: python -m pip install python-dotenv")

ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"
DEFAULT_MODEL = "fish-audio/s2.1-pro-free:free"


class InferenceError(Exception):
    """An error safe to display after removing credentials."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the Authorization header to a redirect destination.
        return None


def redact(message, key):
    if key:
        message = message.replace(key, "[REDACTED]")
    return re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", message)


def request_speech(model, voice, text, key, timeout):
    payload = {
        "model": model,
        "input": text,
        "response_format": "mp3",
    }
    if voice is not None:
        payload["voice"] = voice
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            error = json.loads(exc.read(65536).decode("utf-8"))
            detail = error.get("error", {}).get("message", "")
            if not isinstance(detail, str):
                detail = ""
        except (ValueError, AttributeError):
            pass
        hints = {
            401: "Check OPEN_ROUTER_KEY in .env.",
            402: "Check your balance and key spending limit.",
            429: "The request was rate limited; try again later.",
        }
        detail = redact(detail, key).replace("\r", " ").replace("\n", " ")[:500]
        message = detail or hints.get(exc.code, "Check the model, voice, and provider.")
        raise InferenceError(f"OpenRouter HTTP {exc.code}: {message}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise InferenceError("Could not reach OpenRouter or the request timed out.") from None
    if content_type not in ("audio/mpeg", "audio/mp3"):
        raise InferenceError("Expected MP3 audio; the server returned another content type.")
    if not audio:
        raise InferenceError("OpenRouter returned empty audio.")
    return audio


def save_audio(audio, output, ffmpeg, overwrite):
    # Convert in the destination directory, then publish the completed file.
    with tempfile.TemporaryDirectory(prefix=".openrouter-tts-", dir=output.parent) as tmp:
        source = Path(tmp) / "speech.mp3"
        source.write_bytes(audio)
        result = source
        if output.suffix.lower() == ".wav":
            result = Path(tmp) / "speech.wav"
            try:
                completed = subprocess.run(
                    [
                        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-i", str(source), "-c:a", "pcm_s16le", str(result),
                    ],
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise InferenceError("FFmpeg could not convert the audio to WAV.") from None
            if completed.returncode:
                raise InferenceError("FFmpeg rejected the returned audio.") from None
            with wave.open(str(result), "rb") as wav:
                if not wav.getnframes():
                    raise InferenceError("The converted WAV file contains no audio.")
        if output.exists() and not overwrite:
            raise InferenceError("The output file already exists. Use --overwrite to replace it.")
        os.replace(result, output)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OpenRouter TTS; reads OPEN_ROUTER_KEY from .env next to this script."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Full OpenRouter model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--text", required=True, help="Text to speak")
    parser.add_argument("--output", type=Path, default=Path("output.wav"),
                        help="Destination .wav or .mp3 (default: output.wav)")
    parser.add_argument("--voice", help="Provider voice ID, passed unchanged; omit for provider default")
    parser.add_argument("--timeout", type=float, default=180,
                        help="HTTP timeout in seconds (default: 180)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    key = ""
    try:
        if not args.text.strip():
            raise InferenceError("--text must contain something to speak.")
        if args.timeout <= 0:
            raise InferenceError("--timeout must be positive.")
        model = args.model.strip()
        if "/" not in model or any(char.isspace() for char in model):
            raise InferenceError("--model must be a full OpenRouter provider/model ID.")
        voice = args.voice
        if voice is not None and not voice.strip():
            raise InferenceError("--voice must not be empty.")
        output = args.output.expanduser().absolute()
        if output.suffix.lower() not in (".wav", ".mp3"):
            raise InferenceError("--output must end with .wav or .mp3.")
        if output.exists() and not args.overwrite:
            raise InferenceError("The output file already exists. Use --overwrite to replace it.")
        if output.is_dir():
            raise InferenceError("--output must be a file path.")
        ffmpeg = shutil.which("ffmpeg")
        if output.suffix.lower() == ".wav" and not ffmpeg:
            raise InferenceError("WAV output requires FFmpeg on PATH. Alternatively, use .mp3.")
        load_dotenv(Path(__file__).with_name(".env"), encoding="utf-8-sig")
        key = os.getenv("OPEN_ROUTER_KEY", "").strip()
        if not key:
            raise InferenceError("Set OPEN_ROUTER_KEY=your_key in .env next to tts.py.")
        if any(char.isspace() for char in key):
            raise InferenceError("OPEN_ROUTER_KEY must not contain whitespace.")
        output.parent.mkdir(parents=True, exist_ok=True)
        # Check write permission before making a paid request.
        with tempfile.TemporaryFile(dir=output.parent):
            pass
        audio = request_speech(model, voice, args.text, key, args.timeout)
        save_audio(audio, output, ffmpeg, args.overwrite)
        print(f"Saved: {output}")
        print(f"Model: {model}")
        print(f"Voice: {voice if voice is not None else 'provider default'}")
        return 0
    except (InferenceError, OSError, wave.Error) as exc:
        print(f"Error: {redact(str(exc), key)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
