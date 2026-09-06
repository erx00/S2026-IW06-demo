"""Fieldnote: receive a conversation, ask Gemini, return its answer."""
import os
import sys

from flask import Flask, abort, request, send_from_directory
from werkzeug.exceptions import HTTPException
from gemini import build_request_body, call_gemini
from errors import APIError, model_error, request_error

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1"]

# Flask connects URLs to Python functions and converts dictionaries to JSON.
@app.post("/api/chat")
def chat():
    payload = request.get_json()
    request_body = build_request_body(payload)
    answer = call_gemini(request_body)
    return {"text": answer}


@app.get("/api/status")
def status():
    return {
        "configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
    }


@app.get("/")
@app.get("/<path:filename>")
def page(filename="index.html"):
    # Serve only public files, never keys, Python source, or Git metadata.
    if filename not in {"index.html", "app.js", "app_helpers.js", "app_ui.js", "styles.css"}:
        abort(404)
    return send_from_directory(app.root_path, filename)


@app.before_request
def check_origin():
    origin = request.headers.get("Origin")
    different_origin = origin and origin != request.host_url.rstrip("/")
    cross_site_request = request.headers.get("Sec-Fetch-Site") == "cross-site"
    if different_origin or cross_site_request:
        abort(403, description="Open Fieldnote from its local server address.")


@app.after_request
def response_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Error response functions live together in errors.py.
app.register_error_handler(APIError, model_error)
app.register_error_handler(HTTPException, request_error)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        from diagnostics import run_cli
        run_cli(call_gemini, APIError)
    else:
        print("Gemini model:", os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
        app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "4173")))
