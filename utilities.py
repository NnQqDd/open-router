"""Shared OpenRouter text and speech generation."""

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import wave

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("Install the dependency: python -m pip install python-dotenv")

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
SPEECH_ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"


class TextGenerationError(Exception):
    """A text generation failure with credentials removed."""

    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class AudioGenerationError(Exception):
    """An audio generation or saving failure with credentials removed."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Avoid forwarding the API key to another URL.
        return None


def redact(message, key=""):
    if key:
        message = message.replace(key, "[REDACTED]")
    return re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", message)


def _error_detail(data):
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        error = error.get("message")
    return error if isinstance(error, str) else ""


def _load_api_key(error_type):
    load_dotenv(Path(__file__).with_name(".env"), encoding="utf-8-sig")
    key = os.getenv("OPEN_ROUTER_KEY", "").strip()
    if not key:
        raise error_type("Set OPEN_ROUTER_KEY=your_key in .env beside utilities.py.")
    if any(char.isspace() for char in key):
        raise error_type("OPEN_ROUTER_KEY must not contain whitespace.")
    return key


def _http_error_message(exc, key, fallback):
    detail = ""
    try:
        detail = _error_detail(json.loads(exc.read(65536)))
    except (ValueError, OSError):
        pass
    hints = {
        401: "Check OPEN_ROUTER_KEY in .env.",
        402: "Check your balance and key spending limit.",
        429: "The request was rate limited; try again later.",
    }
    detail = redact(detail, key).replace("\r", " ").replace("\n", " ")[:500]
    message = detail or hints.get(exc.code, fallback)
    return f"OpenRouter HTTP {exc.code}: {message}"


def _message_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return ""


def generate_text(model_id, prompt):
    """Return the model's response text unchanged, without printing or parsing it.

    ``prompt`` can be a string, or a chat request dictionary containing
    ``messages`` and optional OpenRouter parameters such as ``response_format``.
    A dictionary may also set ``timeout`` in seconds (default: 180); this is
    used locally and is not sent to OpenRouter. The dictionary is not modified.
    Credentials come from OPEN_ROUTER_KEY or .env beside this module.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        raise TextGenerationError("model_id must be a non-empty string.")
    if isinstance(prompt, str):
        if not prompt.strip():
            raise TextGenerationError("The prompt must not be empty.")
        payload = {"messages": [{"role": "user", "content": prompt}]}
    elif isinstance(prompt, dict):
        payload = dict(prompt)
        if not isinstance(payload.get("messages"), list) or not payload["messages"]:
            raise TextGenerationError("The prompt must contain a non-empty messages list.")
    else:
        raise TextGenerationError("prompt must be text or a chat request dictionary.")
    timeout = payload.pop("timeout", 180)
    if (
        not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise TextGenerationError("timeout must be a finite positive number.")
    payload["model"] = model_id.strip()
    payload["stream"] = False

    key = _load_api_key(TextGenerationError)
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise TextGenerationError(
            _http_error_message(exc, key, "Check the model and provider."),
            status_code=exc.code,
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TextGenerationError("Could not reach OpenRouter or the request timed out.") from None
    except ValueError:
        raise TextGenerationError("OpenRouter returned invalid JSON.") from None

    if isinstance(data, dict) and "error" in data:
        detail = redact(_error_detail(data), key).replace("\r", " ").replace("\n", " ")[:500]
        raise TextGenerationError(f"OpenRouter error: {detail or 'The request failed.'}")
    try:
        message = data["choices"][0]["message"]
        content = _message_text(message)
    except (KeyError, IndexError, TypeError, AttributeError):
        raise TextGenerationError("OpenRouter returned an unexpected response.") from None
    if not content.strip():
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            raise TextGenerationError(f"Model refused the request: {redact(refusal, key)}")
        raise TextGenerationError("OpenRouter returned no text.")
    return content


def _request_speech(model_id, voice_id, text, speed, key, timeout, response_format="mp3"):
    payload = {
        "model": model_id,
        "input": text,
        "speed": speed,
        "response_format": response_format,
    }
    if voice_id is not None:
        payload["voice"] = voice_id
    request = urllib.request.Request(
        SPEECH_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "audio/pcm" if response_format == "pcm" else "audio/mpeg",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            audio = response.read()
    except urllib.error.HTTPError as exc:
        raise AudioGenerationError(
            _http_error_message(exc, key, "Check the model, voice, and provider.")
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AudioGenerationError("Could not reach OpenRouter or the request timed out.") from None
    expected_types = ("audio/pcm",) if response_format == "pcm" else ("audio/mpeg", "audio/mp3")
    if content_type not in expected_types:
        raise AudioGenerationError(
            f"Expected {response_format.upper()} audio; the server returned another content type."
        )
    if not audio:
        raise AudioGenerationError("OpenRouter returned empty audio.")
    return audio


def _save_audio(audio, output, ffmpeg, overwrite, response_format="mp3"):
    # Finish writing/converting beside the destination before publishing it.
    with tempfile.TemporaryDirectory(prefix=".openrouter-tts-", dir=output.parent) as tmp:
        source = Path(tmp) / f"speech.{response_format}"
        source.write_bytes(audio)
        result = source
        if output.suffix.lower() == ".wav" or response_format == "pcm":
            result = Path(tmp) / f"converted{output.suffix.lower()}"
            command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error"]
            if response_format == "pcm":
                # OpenRouter's PCM speech output is signed 16-bit, 24 kHz mono.
                if len(audio) % 2:
                    raise AudioGenerationError("OpenRouter returned incomplete 16-bit PCM audio.")
                command.extend(["-f", "s16le", "-ar", "24000", "-ac", "1"])
            command.extend(["-i", str(source)])
            if output.suffix.lower() == ".wav":
                command.extend(["-c:a", "pcm_s16le"])
            command.append(str(result))
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise AudioGenerationError("FFmpeg could not convert the audio.") from None
            if completed.returncode:
                raise AudioGenerationError("FFmpeg rejected the returned audio.")
            if output.suffix.lower() == ".wav":
                with wave.open(str(result), "rb") as wav:
                    if not wav.getnframes():
                        raise AudioGenerationError("The converted WAV file contains no audio.")
        if overwrite:
            os.replace(result, output)
        else:
            try:
                # Linking fails atomically if another writer created the path.
                os.link(result, output)
            except FileExistsError:
                raise AudioGenerationError(
                    "The output file already exists. Set overwrite=True to replace it."
                ) from None


def generate_audio(model_id, voice_id, text, speed, save_path, *, timeout=180,
                   overwrite=False, response_format="mp3"):
    """Generate speech, save an MP3 or WAV, and return its absolute ``Path``.

    ``voice_id=None`` omits the voice so a provider can use its default.
    ``speed`` must be finite and positive; support and bounds depend on the
    provider. ``response_format`` selects MP3 (default) or raw 24 kHz, 16-bit
    mono PCM. WAV output and PCM conversion require FFmpeg on PATH.
    Credentials come from OPEN_ROUTER_KEY or .env beside this module.
    Existing files are preserved unless ``overwrite=True``. Nothing is printed.
    Failures raise ``AudioGenerationError``.
    """
    if not isinstance(model_id, str):
        raise AudioGenerationError("model_id must be a full OpenRouter provider/model ID.")
    model_id = model_id.strip()
    if "/" not in model_id or any(char.isspace() for char in model_id):
        raise AudioGenerationError("model_id must be a full OpenRouter provider/model ID.")
    if not isinstance(text, str) or not text.strip():
        raise AudioGenerationError("text must contain something to speak.")
    if voice_id is not None and (not isinstance(voice_id, str) or not voice_id.strip()):
        raise AudioGenerationError("voice_id must be a non-empty string or None.")
    if response_format not in ("mp3", "pcm"):
        raise AudioGenerationError("response_format must be 'mp3' or 'pcm'.")
    for name, value in (("speed", speed), ("timeout", timeout)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise AudioGenerationError(f"{name} must be a finite positive number.")
    try:
        output = Path(save_path).expanduser().absolute()
    except (TypeError, ValueError, RuntimeError):
        raise AudioGenerationError("save_path must be a valid .wav or .mp3 file path.") from None
    if output.suffix.lower() not in (".wav", ".mp3"):
        raise AudioGenerationError("save_path must end with .wav or .mp3.")
    if output.is_dir():
        raise AudioGenerationError("save_path must be a file path.")
    if os.path.lexists(output) and not overwrite:
        raise AudioGenerationError("The output file already exists. Set overwrite=True to replace it.")
    ffmpeg = shutil.which("ffmpeg")
    if (output.suffix.lower() == ".wav" or response_format == "pcm") and not ffmpeg:
        raise AudioGenerationError("WAV output and PCM conversion require FFmpeg on PATH.")
    key = _load_api_key(AudioGenerationError)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Check write permission before making a paid request.
        with tempfile.TemporaryFile(dir=output.parent):
            pass
        audio = _request_speech(model_id, voice_id, text, speed, key, timeout, response_format)
        _save_audio(audio, output, ffmpeg, overwrite, response_format)
    except (OSError, wave.Error, EOFError) as exc:
        raise AudioGenerationError(redact(f"Could not save audio: {exc}", key)) from None
    return output
