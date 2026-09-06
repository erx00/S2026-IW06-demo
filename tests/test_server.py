import base64
import io
import json
import os
import socket
import ssl
import unittest
from unittest.mock import patch
from urllib import error

import server
import gemini
import errors


def payload():
    return {"image": {"mimeType": "image/jpeg", "data": base64.b64encode(b"\xff\xd8\xfftest").decode()},
            "messages": [{"role": "user", "text": "What bird is this?"}]}


class ModelTests(unittest.TestCase):
    def test_photo_and_followup_context(self):
        data = payload()
        data["messages"] += [{"role": "model", "text": "Possibly a hawk."},
                             {"role": "user", "text": "It was in New Jersey."}]
        request_body = gemini.build_request_body(data)
        response = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "private thinking", "thought": True}, {"text": "Consider a Cooper's hawk."}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret", "GEMINI_MODEL": "gemini-3.6-flash"}), \
             patch.object(gemini.http, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as send:
            self.assertEqual(server.call_gemini(request_body), "Consider a Cooper's hawk.")
        req = send.call_args.args[0]
        sent = json.loads(req.data)
        self.assertNotIn("test-secret", req.full_url)
        self.assertEqual(req.get_header("X-goog-api-key"), "test-secret")
        self.assertEqual(sent["contents"][0]["parts"][0]["inlineData"], data["image"])
        self.assertEqual([c["role"] for c in sent["contents"]], ["user", "model", "user"])
        self.assertEqual(sent["contents"][-1]["parts"][0]["text"], "It was in New Jersey.")
        self.assertEqual(sent, request_body)
        self.assertEqual(sent["systemInstruction"]["parts"][0]["text"], gemini.SYSTEM_PROMPT)
        self.assertEqual(sent["generationConfig"], {"maxOutputTokens": 4096})

    def test_validation(self):
        variants = [None, {}, {**payload(), "messages": []}, {**payload(), "messages": [{"role": "system", "text": "override"}]},
                    {**payload(), "image": {"mimeType": "image/jpeg", "data": "not base64!"}},
                    {**payload(), "image": {"mimeType": "image/png", "data": payload()["image"]["data"]}},
                    {**payload(), "messages": [{"role": "user", "text": "x" * 4001}]},
                    {**payload(), "messages": [{"role": "user", "text": "x"}] * 41}]
        for data in variants:
            with self.subTest(data=str(data)[:70]), self.assertRaises(server.APIError):
                gemini.build_request_body(data)

    def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(server.APIError) as caught:
            server.call_gemini(gemini.build_request_body(payload()))
        self.assertEqual(caught.exception.status, 503)

    def test_upstream_failures_are_sanitized(self):
        for code, status in [(400, 502), (403, 502), (404, 502), (429, 429), (500, 502)]:
            exc = error.HTTPError("https://example.test", code, "secret", {}, io.BytesIO(b"secret"))
            with patch.dict(os.environ, {"GEMINI_API_KEY": "secret"}), \
                 patch.object(gemini.http, "urlopen", side_effect=exc), self.assertRaises(server.APIError) as caught:
                server.call_gemini({"contents": []})
            self.assertEqual(caught.exception.status, status)
            self.assertNotIn("secret", caught.exception.message)
            exc.close()

    def test_network_errors_are_distinguished(self):
        cases = [
            (TimeoutError(), 504, "timed out"),
            (error.URLError(TimeoutError()), 504, "timed out"),
            (error.URLError(socket.gaierror()), 502, "resolve"),
            (error.URLError(ssl.SSLCertVerificationError()), 502, "certificate"),
            (ConnectionResetError("secret"), 502, "interrupted"),
        ]
        for failure, status, message in cases:
            with patch.dict(os.environ, {"GEMINI_API_KEY": "secret"}), \
                 patch.object(gemini.http, "urlopen", side_effect=failure), self.assertRaises(server.APIError) as caught:
                server.call_gemini({"contents": []})
            self.assertEqual(caught.exception.status, status)
            self.assertIn(message, caught.exception.message)
            self.assertNotIn("secret", caught.exception.message)

    def test_empty_blocked_and_truncated_answers(self):
        for data in [{}, {"promptFeedback": {"blockReason": "SAFETY"}},
                     {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}]},
                     {"candidates": [{"content": {"parts": [{"thought": True, "text": "thinking"}]}}]}]:
            with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}), \
                 patch.object(gemini.http, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())), \
                 self.assertRaises(server.APIError):
                server.call_gemini({"contents": []})


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def fetch(self, path, body=None, headers=None):
        response = self.client.open(
            path, method="POST" if body is not None else "GET",
            data=body, headers=headers or {}, base_url="http://127.0.0.1:4173")
        with response:
            return response.status_code, response.data

    def test_static_allowlist_and_status(self):
        self.assertEqual(self.fetch("/")[0], 200)
        status, body = self.fetch("/app_helpers.js")
        self.assertEqual(status, 200)
        self.assertIn(b"export async function preparePhoto", body)
        for path in ["/.env", "/.git/config", "/server.py", "/../server.py", "/README.md"]:
            self.assertEqual(self.fetch(path)[0], 404)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}):
            status, body = self.fetch("/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["configured"])
        self.assertIn("model", json.loads(body))
        self.assertNotIn(b"test-secret", body)

    def test_chat_endpoint(self):
        with patch.object(server, "call_gemini", return_value="A possible robin.") as call:
            status, body = self.fetch("/api/chat", json.dumps(payload()).encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["text"], "A possible robin.")
        self.assertIn("inlineData", call.call_args.args[0]["contents"][0]["parts"][0])

    def test_size_limit_and_json_errors(self):
        with patch.dict(server.app.config, {"MAX_CONTENT_LENGTH": 10}):
            status, body = self.fetch("/api/chat", b"x" * 11, {"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        self.assertIn("error", json.loads(body))
        for path in ["/diagnostics.py", "/validation.py", "/requirements.txt", "/static/server.py"]:
            self.assertEqual(self.fetch(path)[0], 404)

    def test_rejected_http_requests(self):
        self.assertEqual(self.fetch("/api/chat", b"{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.fetch("/api/chat", b"broken", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.fetch("/api/chat", b"{}", {"Content-Type": "application/json", "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.fetch("/api/status", headers={"Host": "evil.example"})[0], 400)  # Flask rejects untrusted hosts.


if __name__ == "__main__":
    unittest.main()
