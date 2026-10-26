import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import query
import utilities


def response(data):
    return io.BytesIO(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def completion(content):
    return response({
        "choices": [{"message": {"content": content}}],
        "usage": {"cost": 1, "prompt_tokens": 10},
    })


class TextGenerationTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"OPEN_ROUTER_KEY": "test-secret"}, clear=True))
        stack.enter_context(patch.object(utilities, "load_dotenv"))
        opener_factory = stack.enter_context(patch.object(utilities.urllib.request, "build_opener"))
        self.opener = opener_factory.return_value

    def test_returns_only_raw_text_without_printing(self):
        raw = '  Xin chào!\n{"value": 42}\n'
        self.opener.open.return_value = completion(raw)
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = utilities.generate_text("test/model", "Chào bạn")
        self.assertEqual(result, raw)
        self.assertEqual(stdout.getvalue(), "")

    def test_request_options_preserve_schema_and_timeout_without_mutating_prompt(self):
        prompt = {
            "messages": [{"role": "user", "content": "Return JSON"}],
            "response_format": {"type": "json_object"},
            "timeout": 12,
        }
        original = copy.deepcopy(prompt)
        self.opener.open.return_value = completion('{"ok": true}')
        self.assertEqual(utilities.generate_text("test/model", prompt), '{"ok": true}')
        request = self.opener.open.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual(sent["response_format"], original["response_format"])
        self.assertEqual(sent["model"], "test/model")
        self.assertNotIn("timeout", sent)
        self.assertFalse(sent["stream"])
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 12)
        self.assertEqual(prompt, original)

    def test_joins_text_content_parts(self):
        self.opener.open.return_value = completion([
            {"type": "text", "text": "Xin "},
            {"type": "text", "text": "chào!"},
        ])
        self.assertEqual(utilities.generate_text("test/model", "Hello"), "Xin chào!")

    def test_http_errors_preserve_status_and_redact_credentials(self):
        for status in (400, 401, 429, 503):
            with self.subTest(status=status):
                self.opener.open.side_effect = urllib.error.HTTPError(
                    utilities.ENDPOINT, status, "Request failed", {},
                    response({"error": {"message": "Request failed for test-secret"}}),
                )
                with self.assertRaises(utilities.TextGenerationError) as caught:
                    utilities.generate_text("test/model", "Hello")
                self.assertEqual(caught.exception.status_code, status)
                self.assertIn(f"HTTP {status}", str(caught.exception))
                self.assertIn("[REDACTED]", str(caught.exception))
                self.assertNotIn("test-secret", str(caught.exception))

    def test_invalid_or_empty_responses_raise_readable_errors(self):
        cases = [
            (b"not json", "invalid JSON"),
            (b'{"choices": []}', "unexpected response"),
            (b'{"choices": [{"message": null}]}', "unexpected response"),
            (b'{"choices": [{"message": {"content": " "}}]}', "no text"),
            (b'{"error": {"message": "test-secret"}}', r"\[REDACTED\]"),
            (b'{"choices": [{"message": {"refusal": "test-secret"}}]}', r"\[REDACTED\]"),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.opener.open.return_value = io.BytesIO(body)
                with self.assertRaisesRegex(utilities.TextGenerationError, expected):
                    utilities.generate_text("test/model", "Hello")

    def test_network_failure_is_wrapped(self):
        self.opener.open.side_effect = urllib.error.URLError("unreachable")
        with self.assertRaisesRegex(utilities.TextGenerationError, "Could not reach"):
            utilities.generate_text("test/model", "Hello")

    def test_invalid_configuration_never_sends_request(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(utilities.TextGenerationError, "timeout"):
                    utilities.generate_text("test/model", {
                        "messages": [{"role": "user", "content": "Hi"}],
                        "timeout": timeout,
                    })
        os.environ.pop("OPEN_ROUTER_KEY")
        with self.assertRaisesRegex(utilities.TextGenerationError, "OPEN_ROUTER_KEY"):
            utilities.generate_text("test/model", "Hello")
        self.opener.open.assert_not_called()

    def test_query_reads_markdown_and_prints_raw_answer(self):
        self.opener.open.return_value = completion(" Xin chào!\n")
        with tempfile.TemporaryDirectory() as tmp:
            prompt_file = Path(tmp) / "prompt.md"
            prompt_file.write_text("\ufeffChào bạn", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                result = query.main([
                    "--model", "test/model", "--markdown", str(prompt_file), "--timeout", "15",
                ])
        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), " Xin chào!\n\n")
        request = self.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data)["messages"][0]["content"], "Chào bạn")
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 15)

    def test_query_handles_shared_helper_errors(self):
        os.environ.pop("OPEN_ROUTER_KEY")
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = query.main(["--prompt", "Hi"])
        self.assertEqual(result, 1)
        self.assertIn("OPEN_ROUTER_KEY", stderr.getvalue())
        self.opener.open.assert_not_called()

if __name__ == "__main__":
    unittest.main()
