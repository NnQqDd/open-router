import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

import generate_audios
import utilities
from utilities import AudioGenerationError


class GenerateAudiosTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.inputs = self.tmp / "texts"
        self.inputs.mkdir()
        self.outputs = self.tmp / "audios"
        self.audio = stack.enter_context(patch.object(generate_audios, "generate_audio"))
        self.audio.side_effect = self.save_audio
        stack.enter_context(patch.object(generate_audios.shutil, "which", return_value="ffmpeg"))
        self.stdout = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def save_audio(self, model, voice, text, speed, output, *, timeout, response_format="mp3"):
        output.write_bytes(b"new audio")
        return output

    def source(self, name, text):
        path = self.inputs / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_generate(self, extra=()):
        return generate_audios.main([
            "--model", "test/speech", "--text-dir", str(self.inputs),
            "--save-dir", str(self.outputs), *extra,
        ])

    def test_mixed_inputs_preserve_stems_and_speak_normalized_text(self):
        self.source("greeting.txt", "\ufeff  Xin chào!\n")
        self.source("000.JSON", json.dumps({
            "written_text": "Không đọc câu này 25%.",
            "normalized_text": "Đọc hai lăm phần trăm.",
        }, ensure_ascii=False))
        self.source("ignored.md", "ignored")
        (self.inputs / "nested.txt").mkdir()
        self.assertEqual(self.run_generate(["--voice", "test-voice", "--timeout", "25"]), 0)
        self.assertEqual(sorted(path.name for path in self.outputs.iterdir()), ["000.wav", "greeting.wav"])
        self.assertEqual(self.audio.call_count, 2)
        for call, text, name in zip(self.audio.call_args_list,
                                    ["Đọc hai lăm phần trăm.", "  Xin chào!\n"],
                                    ["000.wav", "greeting.wav"]):
            self.assertEqual(call.args, ("test/speech", "test-voice", text, 1.0, self.outputs / name))
            self.assertEqual(call.kwargs, {"timeout": 25, "response_format": "mp3"})

    def test_pcm_format_is_forwarded_to_the_shared_helper(self):
        self.source("0.txt", "Xin chào!")
        self.assertEqual(self.run_generate(["--response-format", "pcm"]), 0)
        self.assertEqual(self.audio.call_args.kwargs["response_format"], "pcm")

    def test_range_is_inclusive_and_uses_filename_numbers(self):
        for name in ("000", "009", "010", "020", "100", "named"):
            self.source(f"{name}.txt", name)
        self.assertEqual(self.run_generate(["--start-idx", "10", "--end-idx", "20"]), 0)
        self.assertEqual(sorted(path.name for path in self.outputs.iterdir()), ["010.wav", "020.wav"])
        self.assertEqual([call.args[2] for call in self.audio.call_args_list], ["010", "020"])

    def test_either_range_bound_can_be_omitted(self):
        for index in range(3):
            self.source(f"{index:03d}.txt", str(index))
        for flags, expected in [
            (["--end-idx", "1"], ["000.wav", "001.wav"]),
            (["--start-idx", "1"], ["001.wav", "002.wav"]),
        ]:
            with self.subTest(flags=flags):
                output = self.tmp / flags[0][2:]
                self.assertEqual(self.run_generate([*flags, "--save-dir", str(output)]), 0)
                self.assertEqual(sorted(path.name for path in output.iterdir()), expected)

    def test_existing_audio_is_skipped_without_reading_invalid_input(self):
        self.source("000.json", "invalid JSON")
        self.source("001.txt", "new text")
        self.outputs.mkdir()
        previous = self.outputs / "000.wav"
        previous.write_bytes(b"original")
        self.assertEqual(self.run_generate(), 0)
        self.assertEqual(previous.read_bytes(), b"original")
        self.audio.assert_called_once()
        self.assertEqual(self.audio.call_args.args[2], "new text")
        self.assertIn("skipped 1 existing files", self.stdout.getvalue())
        self.assertIn("2/2", self.stderr.getvalue())

    def test_completed_batch_needs_no_requests_or_ffmpeg(self):
        self.source("0.txt", "")
        self.outputs.mkdir()
        (self.outputs / "0.wav").write_bytes(b"original")
        with patch.object(generate_audios.shutil, "which", return_value=None):
            self.assertEqual(self.run_generate(), 0)
        self.audio.assert_not_called()
        self.assertIn("Saved 0 WAV files", self.stdout.getvalue())

    def test_invalid_inputs_are_reported_before_any_audio_requests(self):
        cases = [
            ("1.txt", "  "), ("1.json", "{broken}"),
            ("1.json", "[]"), ("1.json", "null"), ("1.json", "{}"),
            ("1.json", '{"normalized_text": 25}'),
            ("1.json", '{"normalized_text": "  "}'),
        ]
        for index, (name, text) in enumerate(cases):
            with self.subTest(text=text):
                inputs = self.tmp / str(index)
                inputs.mkdir()
                (inputs / "0.txt").write_text("valid")
                (inputs / name).write_text(text)
                self.assertEqual(self.run_generate(["--text-dir", str(inputs)]), 1)
                self.assertIn(name, self.stderr.getvalue())
        self.audio.assert_not_called()

    def test_duplicate_stems_are_rejected_before_audio_requests(self):
        self.source("000.txt", "plain text")
        self.source("000.json", '{"normalized_text": "JSON text"}')
        self.assertEqual(self.run_generate(), 1)
        self.assertIn("both map to '000.wav'", self.stderr.getvalue())
        self.audio.assert_not_called()

    def test_invalid_options_do_not_generate_audio(self):
        self.source("0.txt", "text")
        for flags in [
            ["--model", " "], ["--model", "invalid"], ["--voice", " "],
            ["--timeout", "0"], ["--timeout", "nan"], ["--timeout", "inf"],
            ["--start-idx", "-1"], ["--end-idx", "-1"],
            ["--start-idx", "2", "--end-idx", "1"],
            ["--text-dir", str(self.tmp / "missing")],
        ]:
            with self.subTest(flags=flags):
                self.assertEqual(self.run_generate(flags), 1)
        self.audio.assert_not_called()

    def test_no_matching_sources_is_a_readable_error(self):
        self.source("0.txt", "text")
        self.assertEqual(self.run_generate(["--start-idx", "1"]), 1)
        self.assertIn("No .txt or .json files match", self.stderr.getvalue())
        self.audio.assert_not_called()

    def test_output_directory_collision_aborts_before_requests(self):
        self.source("0.txt", "text")
        (self.outputs / "0.wav").mkdir(parents=True)
        self.assertEqual(self.run_generate(), 1)
        self.assertIn("not a directory", self.stderr.getvalue())
        self.audio.assert_not_called()

    def test_missing_ffmpeg_aborts_before_requests(self):
        self.source("0.txt", "text")
        with patch.object(generate_audios.shutil, "which", return_value=None):
            self.assertEqual(self.run_generate(), 1)
        self.assertIn("FFmpeg", self.stderr.getvalue())
        self.audio.assert_not_called()

    def test_audio_errors_stop_and_rerun_resumes_completed_files(self):
        self.source("0.txt", "first")
        self.source("1.txt", "second")

        def reply(*args, **kwargs):
            if args[2] == "second":
                raise AudioGenerationError("OpenRouter HTTP 400: invalid model")
            return self.save_audio(*args, **kwargs)

        self.audio.side_effect = reply
        self.assertEqual(self.run_generate(), 1)
        self.assertIn("'1.txt': OpenRouter HTTP 400", self.stderr.getvalue())
        self.assertEqual((self.outputs / "0.wav").read_bytes(), b"new audio")
        self.assertFalse((self.outputs / "1.wav").exists())
        self.audio.reset_mock()
        self.audio.side_effect = self.save_audio
        self.assertEqual(self.run_generate(), 0)
        self.audio.assert_called_once()
        self.assertEqual(self.audio.call_args.args[2], "second")

    def test_cancellation_keeps_completed_audio(self):
        self.source("0.txt", "first")
        self.source("1.txt", "second")

        def reply(*args, **kwargs):
            if args[2] == "second":
                raise KeyboardInterrupt()
            return self.save_audio(*args, **kwargs)

        self.audio.side_effect = reply
        self.assertEqual(self.run_generate(), 130)
        self.assertEqual((self.outputs / "0.wav").read_bytes(), b"new audio")
        self.assertFalse((self.outputs / "1.wav").exists())

    def test_audio_created_before_its_turn_is_skipped(self):
        self.source("0.txt", "first")
        self.source("1.txt", "second")

        def reply(*args, **kwargs):
            (self.outputs / "1.wav").write_bytes(b"another writer")
            return self.save_audio(*args, **kwargs)

        self.audio.side_effect = reply
        self.assertEqual(self.run_generate(), 0)
        self.audio.assert_called_once()
        self.assertEqual((self.outputs / "1.wav").read_bytes(), b"another writer")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is not installed")
    def test_batch_uses_shared_helper_to_write_a_real_pcm_wav(self):
        self.source("007.json", '{"normalized_text": "Xin chào!"}')
        encoded = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.1", "-f", "mp3", "pipe:1",
        ], capture_output=True, timeout=10, check=True)
        with patch.object(generate_audios, "generate_audio", utilities.generate_audio), patch.object(
            utilities, "_load_api_key", return_value="test-secret",
        ), patch.object(utilities, "_request_speech", return_value=encoded.stdout) as speech:
            self.assertEqual(self.run_generate(), 0)
        self.assertEqual(speech.call_args.args[2], "Xin chào!")
        with wave.open(str(self.outputs / "007.wav"), "rb") as audio:
            self.assertGreater(audio.getnframes(), 0)
            self.assertEqual(audio.getsampwidth(), 2)
            self.assertEqual(audio.getframerate(), 24000)


if __name__ == "__main__":
    unittest.main()
