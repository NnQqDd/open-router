import contextlib
from email.message import Message
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import wave

import tts
import utilities


def audio_response(audio=b"ID3test-audio", content_type="audio/mpeg"):
    response = io.BytesIO(audio)
    response.headers = Message()
    response.headers["Content-Type"] = content_type
    return response


class AudioGenerationTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"OPEN_ROUTER_KEY": "test-secret"}, clear=True))
        stack.enter_context(patch.object(utilities, "load_dotenv"))
        opener_factory = stack.enter_context(patch.object(utilities.urllib.request, "build_opener"))
        self.opener = opener_factory.return_value
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))

    def generate(self, **overrides):
        args = {
            "model_id": "test/model",
            "voice_id": "test-voice",
            "text": "Xin chào!",
            "speed": 1.25,
            "save_path": self.tmp / "speech.mp3",
        }
        args.update(overrides)
        return utilities.generate_audio(**args)

    def test_saves_mp3_and_returns_path_without_printing(self):
        audio = b"ID3audio-bytes"
        self.opener.open.return_value = audio_response(audio)
        output = self.tmp / "nested" / "speech.mp3"
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = self.generate(save_path=str(output), timeout=25)
        self.assertEqual(result, output.absolute())
        self.assertEqual(result.read_bytes(), audio)
        self.assertEqual(stdout.getvalue(), "")
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, utilities.SPEECH_ENDPOINT)
        sent = json.loads(request.data)
        self.assertEqual(sent["voice"], "test-voice")
        self.assertEqual(sent["input"], "Xin chào!")
        self.assertEqual(sent["speed"], 1.25)
        self.assertEqual(sent["response_format"], "mp3")
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 25)

    def test_none_voice_uses_provider_default(self):
        self.opener.open.return_value = audio_response()
        self.generate(voice_id=None)
        request = self.opener.open.call_args.args[0]
        self.assertNotIn("voice", json.loads(request.data))

    def test_existing_output_requires_explicit_overwrite(self):
        output = self.tmp / "speech.mp3"
        output.write_bytes(b"original")
        with self.assertRaisesRegex(utilities.AudioGenerationError, "already exists"):
            self.generate()
        self.assertEqual(output.read_bytes(), b"original")
        self.opener.open.assert_not_called()
        self.opener.open.return_value = audio_response(b"replacement")
        self.generate(overwrite=True)
        self.assertEqual(output.read_bytes(), b"replacement")

    def test_no_overwrite_when_another_writer_creates_output_during_request(self):
        output = self.tmp / "speech.mp3"

        def competing_writer(request, timeout):
            output.write_bytes(b"other writer")
            return audio_response()

        self.opener.open.side_effect = competing_writer
        with self.assertRaisesRegex(utilities.AudioGenerationError, "already exists"):
            self.generate()
        self.assertEqual(output.read_bytes(), b"other writer")
        self.assertEqual(list(self.tmp.iterdir()), [output])

    def test_network_failure_preserves_original_when_overwriting(self):
        output = self.tmp / "speech.mp3"
        output.write_bytes(b"original")
        self.opener.open.side_effect = urllib.error.URLError("unreachable")
        with self.assertRaisesRegex(utilities.AudioGenerationError, "Could not reach"):
            self.generate(overwrite=True)
        self.assertEqual(output.read_bytes(), b"original")

    def test_http_errors_redact_key_without_creating_output(self):
        body = io.BytesIO(json.dumps({"error": {"message": "Invalid key test-secret"}}).encode())
        self.opener.open.side_effect = urllib.error.HTTPError(
            utilities.SPEECH_ENDPOINT, 401, "Unauthorized", {}, body,
        )
        with self.assertRaises(utilities.AudioGenerationError) as caught:
            self.generate()
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertFalse((self.tmp / "speech.mp3").exists())

    def test_wrong_content_type_and_empty_audio_are_not_saved(self):
        cases = [
            (b'{"error": "failed"}', "application/json", "content type"),
            (b"", "audio/mpeg", "empty audio"),
        ]
        for audio, content_type, expected in cases:
            with self.subTest(content_type=content_type):
                self.opener.open.return_value = audio_response(audio, content_type)
                with self.assertRaisesRegex(utilities.AudioGenerationError, expected):
                    self.generate()
                self.assertFalse((self.tmp / "speech.mp3").exists())

    def test_invalid_input_is_rejected_before_request(self):
        cases = [
            {"model_id": ""}, {"text": " "}, {"voice_id": ""},
            {"speed": 0}, {"speed": -1}, {"speed": float("nan")},
            {"speed": float("inf")}, {"speed": True},
            {"timeout": float("nan")}, {"timeout": 0},
            {"response_format": "wav"},
            {"save_path": self.tmp / "speech.ogg"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(utilities.AudioGenerationError):
                    self.generate(**overrides)
        self.opener.open.assert_not_called()

    def test_missing_credentials_fail_before_request(self):
        os.environ.pop("OPEN_ROUTER_KEY")
        with self.assertRaisesRegex(utilities.AudioGenerationError, "OPEN_ROUTER_KEY"):
            self.generate()
        self.opener.open.assert_not_called()

    def test_wav_requires_ffmpeg_before_request(self):
        with patch.object(utilities.shutil, "which", return_value=None):
            with self.assertRaisesRegex(utilities.AudioGenerationError, "FFmpeg"):
                self.generate(save_path=self.tmp / "speech.wav")
        self.opener.open.assert_not_called()

    def test_conversion_failure_preserves_original_and_cleans_temporary_files(self):
        output = self.tmp / "speech.wav"
        output.write_bytes(b"original")
        self.opener.open.return_value = audio_response()
        with patch.object(utilities.shutil, "which", return_value="ffmpeg"), patch.object(
            utilities.subprocess, "run", return_value=SimpleNamespace(returncode=1),
        ):
            with self.assertRaisesRegex(utilities.AudioGenerationError, "FFmpeg rejected"):
                self.generate(save_path=output, overwrite=True)
        self.assertEqual(output.read_bytes(), b"original")
        self.assertEqual(list(self.tmp.iterdir()), [output])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is not installed")
    def test_converts_real_mp3_to_pcm_wav(self):
        encoded = subprocess.run(
            [
                shutil.which("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.1", "-f", "mp3", "pipe:1",
            ],
            capture_output=True, timeout=10, check=True,
        )
        self.opener.open.return_value = audio_response(encoded.stdout)
        output = self.generate(save_path=self.tmp / "speech.wav")
        with wave.open(str(output), "rb") as audio:
            self.assertGreater(audio.getnframes(), 0)
            self.assertEqual(audio.getsampwidth(), 2)
            self.assertEqual(audio.getframerate(), 24000)
            self.assertEqual(audio.getnchannels(), 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is not installed")
    def test_pcm_response_is_requested_and_saved_with_correct_wav_metadata(self):
        pcm = b"\x00\x00\x01\x00" * 1200
        self.opener.open.return_value = audio_response(pcm, "audio/pcm")
        output = self.generate(save_path=self.tmp / "speech.wav", response_format="pcm")
        request = self.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data)["response_format"], "pcm")
        self.assertEqual(request.get_header("Accept"), "audio/pcm")
        with wave.open(str(output), "rb") as audio:
            self.assertEqual(audio.getsampwidth(), 2)
            self.assertEqual(audio.getframerate(), 24000)
            self.assertEqual(audio.getnchannels(), 1)
            self.assertEqual(audio.readframes(audio.getnframes()), pcm)

    def test_truncated_pcm_is_rejected_without_publishing_a_file(self):
        self.opener.open.return_value = audio_response(b"\x00", "audio/pcm")
        with patch.object(utilities.shutil, "which", return_value="ffmpeg"):
            with self.assertRaisesRegex(utilities.AudioGenerationError, "incomplete"):
                self.generate(save_path=self.tmp / "speech.wav", response_format="pcm")
        self.assertFalse((self.tmp / "speech.wav").exists())

    def test_cli_uses_helper_and_forwards_speed_timeout_and_overwrite(self):
        output = self.tmp / "speech.mp3"
        output.write_bytes(b"original")
        self.opener.open.return_value = audio_response(b"replacement")
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = tts.main([
                "--model", "test/model", "--voice", "test-voice", "--text", "Xin chào!",
                "--speed", "1.5", "--timeout", "15", "--output", str(output), "--overwrite",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(output.read_bytes(), b"replacement")
        self.assertIn(f"Saved: {output}", stdout.getvalue())
        request = self.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data)["speed"], 1.5)
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 15)

    def test_cli_explains_overwrite_flag(self):
        output = self.tmp / "speech.mp3"
        output.write_bytes(b"original")
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = tts.main(["--text", "Hi", "--output", str(output)])
        self.assertEqual(result, 1)
        self.assertIn("Use --overwrite", stderr.getvalue())
        self.opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
