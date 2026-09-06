"""Validation, API failures, and error responses for the teaching app."""
import base64
import binascii
import json
import re
import socket
import ssl
from urllib import error

MAX_IMAGE = 10 * 1024 * 1024
MAX_MESSAGES = 39  # 20 user questions and 19 previous model answers.
MAX_USER_CHARACTERS = 4000
MAX_ANSWER_CHARACTERS = 16000
MAX_CONVERSATION_CHARACTERS = 150000


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def validate_settings(key, model):
    if not key:
        raise APIError(503, "The server needs GEMINI_API_KEY. Start it from the terminal where you exported the key.")
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
        raise APIError(503, "Check the server's GEMINI_MODEL setting.")


def validate_payload(payload):
    """Reject invalid or oversized inputs before building the API contents.

    These checks are separate so the packaging example above stays readable.
    """
    if not isinstance(payload, dict):
        raise APIError(400, "Expected a photo and conversation.")
    image = payload.get("image")
    messages = payload.get("messages")
    if not isinstance(image, dict) or image.get("mimeType") not in {"image/jpeg", "image/png", "image/webp"}:
        raise APIError(400, "Choose a JPG, PNG or WebP photo.")
    data = image.get("data")
    # Base64 uses four characters for every three bytes (rounded up).
    max_encoded_length = ((MAX_IMAGE + 2) // 3) * 4
    if not isinstance(data, str) or len(data) > max_encoded_length:
        raise APIError(413, "The photo must be under 10 MB.")
    try:
        decoded = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        raise APIError(400, "Could not read the photo data.") from None
    signatures = {
        "image/jpeg": decoded.startswith(b"\xff\xd8\xff"),
        "image/png": decoded.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP",
    }
    if not decoded or len(decoded) > MAX_IMAGE or not signatures[image["mimeType"]]:
        raise APIError(400, "The photo data does not match its image format.")
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES or len(messages) % 2 != 1:
        raise APIError(400, "Start a new observation after 20 questions.")
    total = 0
    for index, message in enumerate(messages):
        # Turns alternate: user, model, user, model, ...
        if index % 2 == 0:
            role = "user"
            limit = MAX_USER_CHARACTERS
        else:
            role = "model"
            limit = MAX_ANSWER_CHARACTERS
        if not isinstance(message, dict) or message.get("role") != role:
            raise APIError(400, "Invalid conversation order.")
        text = message.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise APIError(400, "A conversation message is empty or too long.")
        total += len(text)
    if total > MAX_CONVERSATION_CHARACTERS:
        raise APIError(400, "This conversation is too long. Start a new observation.")


def error_detail(exc, key):
    """Read Google's diagnostic message without printing the API key."""
    detail = "No readable error details returned."
    try:
        message = json.loads(exc.read(65536)).get("error", {}).get("message")
        if isinstance(message, str):
            message = message.replace(key, "[REDACTED]")
            message = re.sub(r"AIza[\w-]+", "[REDACTED]", message)
            detail = " ".join(message.split())[:1500]
    except (ValueError, AttributeError, OSError):
        pass
    return detail


def connection_error(exc):
    """Describe network failures without exposing request details or credentials."""
    reason = exc
    if isinstance(exc, error.URLError):
        reason = exc.reason
    if isinstance(reason, TimeoutError):
        return APIError(504, "The Google request timed out after waiting up to 60 seconds for network activity. Please retry.")
    if isinstance(reason, ssl.SSLCertVerificationError):
        return APIError(502, "Python could not verify Google's HTTPS certificate. Check the certificates for the Python installation running this server.")
    if isinstance(reason, socket.gaierror):
        return APIError(502, "Python could not resolve Google's server address. Check your internet connection or DNS settings and retry.")
    if isinstance(reason, ssl.SSLError):
        return APIError(502, "The secure connection to Google failed. Check your network or proxy settings and retry.")
    return APIError(502, "The connection to Google failed or was interrupted. Check your network or proxy settings and retry.")


def gemini_request_error(exc, key, model, diagnostic=False):
    """Translate a failed request into an APIError; this makes no network calls."""
    if isinstance(exc, error.HTTPError):
        if diagnostic:
            detail = error_detail(exc, key)
            return APIError(502, f"Google HTTP {exc.code}; model={model}\n{detail}")
        # Never return Google's raw error body: it may contain request details.
        messages = {
            400: "Google rejected the request. Check your API key and try another photo.",
            401: "Google could not authenticate the API key. Check the server's key and restart it.",
            403: "Google denied access. Check your API key permissions and project access.",
            404: "The configured Gemini model is unavailable. Set GEMINI_MODEL to a model available in your AI Studio account.",
            429: "Google's quota or rate limit was reached. Wait and retry, or check your AI Studio quota.",
        }
        return APIError(429 if exc.code == 429 else 502,
                       messages.get(exc.code, "Google is temporarily unavailable. Please retry."))
    if isinstance(exc, (TimeoutError, error.URLError, OSError)):
        return connection_error(exc)
    return APIError(502, "Google returned an unreadable response. Please retry.")


def validate_response(result):
    """Check that Google returned a completed answer candidate."""
    if not isinstance(result, dict):
        raise APIError(502, "Google returned an unexpected response. Please retry.")
    candidates = result.get("candidates") or []
    if not candidates:
        raise APIError(422, "Google returned no answer for this photo or question. Try a different photo or wording.")
    candidate = candidates[0]
    if candidate.get("finishReason") not in (None, "STOP"):
        raise APIError(422, "Google could not complete this answer. Try a shorter question or a different photo.")


def validate_answer(text):
    if not text or len(text) > MAX_ANSWER_CHARACTERS:
        raise APIError(502, "Google returned no usable answer. Please retry.")


def model_error(exc):
    return {"error": exc.message}, exc.status


def request_error(exc):
    return {"error": exc.description}, exc.code


