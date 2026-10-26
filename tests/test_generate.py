import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_texts as generate
from utilities import TextGenerationError


class GenerateTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.generate_text = stack.enter_context(patch.object(generate, "generate_text"))
        self.sleep = stack.enter_context(patch.object(generate.time, "sleep"))
        self.stdout = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def run_generate(self, count=1, extra=()):
        return generate.main([
            "--prompt", "Say hello", "--model", "test/model", "--N", str(count),
            "--save-dir", str(self.tmp / "responses"), *extra,
        ])

    def test_text_is_saved_verbatim_and_each_request_uses_the_same_prompt(self):
        answers = ["  Xin chào!\n", "not JSON at all", "```json\n{}\n```\n"]
        self.generate_text.side_effect = answers
        self.assertEqual(self.run_generate(3, ["--timeout", "12"]), 0)
        output = self.tmp / "responses"
        self.assertEqual(sorted(path.name for path in output.iterdir()), ["0.txt", "1.txt", "2.txt"])
        for index, answer in enumerate(answers):
            self.assertEqual((output / f"{index}.txt").read_text(encoding="utf-8"), answer)
        self.assertEqual(self.generate_text.call_count, 3)
        for call in self.generate_text.call_args_list:
            self.assertEqual(call.args, ("test/model", {
                "messages": [{"role": "user", "content": "Say hello"}], "timeout": 12,
            }))
        self.sleep.assert_not_called()

    def test_minimum_padding_at_decimal_boundaries(self):
        self.generate_text.return_value = "response"
        for count, first, last in [
            (1, "0.txt", "0.txt"),
            (10, "0.txt", "9.txt"),
            (11, "00.txt", "10.txt"),
            (100, "00.txt", "99.txt"),
            (101, "000.txt", "100.txt"),
        ]:
            with self.subTest(count=count):
                output = self.tmp / str(count)
                self.assertEqual(self.run_generate(count, ["--save-dir", str(output)]), 0)
                names = sorted(path.name for path in output.iterdir())
                self.assertEqual(len(names), count)
                self.assertEqual(names[0], first)
                self.assertEqual(names[-1], last)

    def test_json_cleanup_preserves_content_and_formatting(self):
        expected = ['{\n  "message": "Xin chào!"\n}', '[1, 2, 3]', '{"ok": true}']
        self.generate_text.side_effect = [
            f"\ufeff  {expected[0]}\n",
            f"```json\n{expected[1]}\n```",
            f"  ```\n{expected[2]}\n```  ",
        ]
        self.assertEqual(self.run_generate(3, ["--json"]), 0)
        output = self.tmp / "responses"
        self.assertEqual(sorted(path.name for path in output.iterdir()), ["0.json", "1.json", "2.json"])
        for index, text in enumerate(expected):
            actual = (output / f"{index}.json").read_text(encoding="utf-8")
            self.assertEqual(actual, text)
            json.loads(actual)

    def test_invalid_json_is_retried_until_a_valid_response_is_saved(self):
        self.generate_text.side_effect = [
            "not JSON", "{'single': 'quotes'}", '{"value": NaN}',
            "Here is your JSON: {}", "```json\n{broken}\n```", '{"ok": true}',
        ]
        self.assertEqual(self.run_generate(extra=["--json"]), 0)
        output = self.tmp / "responses"
        self.assertEqual(list(output.iterdir()), [output / "0.json"])
        self.assertEqual((output / "0.json").read_text(encoding="utf-8"), '{"ok": true}')
        self.assertEqual(self.generate_text.call_count, 6)
        self.assertEqual(self.sleep.call_count, 5)

    def test_json_accepts_any_valid_value_without_schema_checks(self):
        answers = ["[]", "null", "false", "17", '"hello"']
        self.generate_text.side_effect = answers
        self.assertEqual(self.run_generate(5, ["--json"]), 0)
        for index, answer in enumerate(answers):
            output = self.tmp / "responses" / f"{index}.json"
            self.assertEqual(output.read_text(encoding="utf-8"), answer)
        self.sleep.assert_not_called()

    def test_request_errors_keep_retrying_without_consuming_file_indices(self):
        self.generate_text.side_effect = [
            "first", *[TextGenerationError("temporarily unavailable") for _ in range(7)], "second",
        ]
        self.assertEqual(self.run_generate(2), 0)
        output = self.tmp / "responses"
        self.assertEqual(sorted(path.name for path in output.iterdir()), ["0.txt", "1.txt"])
        self.assertEqual((output / "0.txt").read_text(), "first")
        self.assertEqual((output / "1.txt").read_text(), "second")
        self.assertEqual(self.generate_text.call_count, 9)
        self.assertEqual(self.sleep.call_count, 7)
        self.assertTrue(all(0 < call.args[0] <= 30 for call in self.sleep.call_args_list))

    def test_markdown_is_read_once_and_timeout_is_forwarded(self):
        markdown = self.tmp / "prompt.md"
        markdown.write_text("\ufeffXin chào!", encoding="utf-8")
        self.generate_text.return_value = "answer"
        self.assertEqual(generate.main([
            "--markdown", str(markdown), "--N", "2", "--model", "test/model",
            "--save-dir", str(self.tmp / "responses"), "--timeout", "15",
        ]), 0)
        for call in self.generate_text.call_args_list:
            self.assertEqual(call.args[1], {
                "messages": [{"role": "user", "content": "Xin chào!"}], "timeout": 15,
            })

    def test_permanent_http_errors_stop_without_retrying_and_keep_completed_files(self):
        for status in (400, 401, 402, 403, 404, 422):
            with self.subTest(status=status):
                output = self.tmp / str(status)
                message = f"OpenRouter HTTP {status}: invalid request"
                self.generate_text.reset_mock()
                self.generate_text.side_effect = [
                    "first", TextGenerationError(message, status_code=status),
                ]
                self.assertEqual(self.run_generate(2, ["--save-dir", str(output)]), 1)
                self.assertEqual(list(output.iterdir()), [output / "0.txt"])
                self.assertEqual((output / "0.txt").read_text(), "first")
                self.assertEqual(self.generate_text.call_count, 2)
                self.assertIn(f"Error: {message}", self.stderr.getvalue())
                self.sleep.assert_not_called()

    def test_transient_http_errors_are_retried(self):
        self.generate_text.side_effect = [
            TextGenerationError(f"HTTP {status}", status_code=status)
            for status in (408, 429, 500, 502, 503, 504)
        ] + ["recovered"]
        self.assertEqual(self.run_generate(), 0)
        self.assertEqual((self.tmp / "responses" / "0.txt").read_text(), "recovered")
        self.assertEqual(self.generate_text.call_count, 7)
        self.assertEqual(self.sleep.call_count, 6)

    def test_existing_files_are_skipped_and_only_gaps_are_generated(self):
        for suffix, extra, answers in [
            (".txt", [], ["new first", "new second"]),
            (".json", ["--json"], ['{"first": 1}', '{"second": 2}']),
        ]:
            with self.subTest(suffix=suffix):
                output = self.tmp / suffix[1:]
                output.mkdir()
                for index in (0, 2, 4):
                    (output / f"{index}{suffix}").write_text("original")
                self.generate_text.reset_mock()
                self.generate_text.side_effect = answers
                self.assertEqual(self.run_generate(5, ["--save-dir", str(output), *extra]), 0)
                self.assertEqual(len(list(output.iterdir())), 5)
                for index in (0, 2, 4):
                    self.assertEqual((output / f"{index}{suffix}").read_text(), "original")
                for index, answer in zip((1, 3), answers):
                    self.assertEqual((output / f"{index}{suffix}").read_text(), answer)
                self.assertEqual(self.generate_text.call_count, 2)
                self.assertIn("Saved 2 responses", self.stdout.getvalue())
                self.assertIn("skipped 3 existing files", self.stdout.getvalue())
                self.sleep.assert_not_called()

    def test_completed_run_skips_every_file_without_requests(self):
        output = self.tmp / "responses"
        output.mkdir()
        for index in range(11):
            (output / f"{index:02d}.json").write_text('{"original": true}')
        self.assertEqual(self.run_generate(11, ["--json"]), 0)
        self.generate_text.assert_not_called()
        self.sleep.assert_not_called()
        self.assertEqual(len(list(output.iterdir())), 11)
        self.assertIn("Saved 0 responses", self.stdout.getvalue())
        self.assertIn("skipped 11 existing files", self.stdout.getvalue())
        self.assertIn("11/11", self.stderr.getvalue())

    def test_directory_at_response_path_fails_before_requests(self):
        (self.tmp / "responses" / "1.txt").mkdir(parents=True)
        self.assertEqual(self.run_generate(2), 1)
        self.assertIn("not a directory", self.stderr.getvalue())
        self.generate_text.assert_not_called()

    def test_overwrite_replaces_all_numbered_text_or_json_files(self):
        for suffix, extra, answers in [
            (".txt", [], ["new first", "new second"]),
            (".json", ["--json"], ['{"first": 1}', '{"second": 2}']),
        ]:
            with self.subTest(suffix=suffix):
                output = self.tmp / suffix[1:]
                output.mkdir()
                for index in range(2):
                    (output / f"{index}{suffix}").write_text("old response")
                self.generate_text.side_effect = answers
                self.assertEqual(self.run_generate(2, [
                    "--save-dir", str(output), "--overwrite", *extra,
                ]), 0)
                self.assertEqual(len(list(output.iterdir())), 2)
                for index, answer in enumerate(answers):
                    self.assertEqual((output / f"{index}{suffix}").read_text(), answer)

    def test_overwrite_keeps_original_until_a_valid_response_is_ready(self):
        output = self.tmp / "responses"
        output.mkdir()
        destination = output / "0.json"
        original = '{"old": true}'
        destination.write_text(original)
        replies = iter([TextGenerationError("temporary failure"), "invalid JSON", '{"new": true}'])

        def reply(model, prompt):
            self.assertEqual(destination.read_text(), original)
            result = next(replies)
            if isinstance(result, Exception):
                raise result
            return result

        self.generate_text.side_effect = reply
        self.assertEqual(self.run_generate(extra=["--json", "--overwrite"]), 0)
        self.assertEqual(destination.read_text(), '{"new": true}')
        self.assertEqual(list(output.iterdir()), [destination])
        self.assertEqual(self.generate_text.call_count, 3)

    def test_concurrent_writer_is_preserved_and_temporary_files_are_cleaned(self):
        output = self.tmp / "responses" / "0.txt"

        def competing_writer(model, prompt):
            output.write_text("another writer")
            return "new response"

        self.generate_text.side_effect = competing_writer
        self.assertEqual(self.run_generate(2), 0)
        self.assertEqual(output.read_text(), "another writer")
        self.assertEqual((output.parent / "1.txt").read_text(), "new response")
        self.assertEqual(len(list(output.parent.iterdir())), 2)
        self.assertIn("Saved 1 responses", self.stdout.getvalue())
        self.assertIn("skipped 1 existing files", self.stdout.getvalue())
        self.sleep.assert_not_called()

    def test_file_created_before_its_turn_is_skipped_without_a_request(self):
        output = self.tmp / "responses"

        def competing_writer(model, prompt):
            (output / "1.txt").write_text("another writer")
            return "first"

        self.generate_text.side_effect = competing_writer
        self.assertEqual(self.run_generate(2), 0)
        self.assertEqual((output / "0.txt").read_text(), "first")
        self.assertEqual((output / "1.txt").read_text(), "another writer")
        self.generate_text.assert_called_once()
        self.assertIn("skipped 1 existing files", self.stdout.getvalue())

    def test_cancellation_keeps_completed_files_and_rerun_resumes(self):
        self.generate_text.side_effect = ["first", KeyboardInterrupt()]
        self.assertEqual(self.run_generate(2), 130)
        output = self.tmp / "responses"
        self.assertEqual(list(output.iterdir()), [output / "0.txt"])
        self.assertEqual((output / "0.txt").read_text(), "first")
        self.generate_text.reset_mock()
        self.generate_text.side_effect = None
        self.generate_text.return_value = "second"
        self.assertEqual(self.run_generate(2), 0)
        self.assertEqual((output / "0.txt").read_text(), "first")
        self.assertEqual((output / "1.txt").read_text(), "second")
        self.generate_text.assert_called_once()

    def test_invalid_input_fails_without_requests(self):
        for extra in [
            ["--N", "0"], ["--N", "-1"], ["--timeout", "nan"],
            ["--timeout", "0"], ["--prompt", " "], ["--model", " "],
        ]:
            with self.subTest(extra=extra):
                self.assertEqual(self.run_generate(extra=extra), 1)
        self.generate_text.assert_not_called()

    def test_file_write_errors_abort_without_regenerating(self):
        self.generate_text.return_value = "response"
        with patch.object(generate, "_save_response", side_effect=PermissionError("not writable")):
            self.assertEqual(self.run_generate(), 1)
        self.assertEqual(self.generate_text.call_count, 1)
        self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
