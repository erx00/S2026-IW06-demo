"""Optional command-line troubleshooting, separate from the teaching example."""
import argparse
import json
import os
from urllib import error, request
from urllib.parse import urlencode


def list_models():
    """List generation models without exposing the API key or making inference calls."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY is missing. Run this in the terminal where you exported it.")
        return
    token = ""
    names = set()
    try:
        while True:
            query = urlencode({"pageSize": 1000, "pageToken": token})
            req = request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models?" + query,
                headers={"x-goog-api-key": key})
            with request.urlopen(req, timeout=20) as response:
                data = json.load(response)
            for model in data.get("models", []):
                if "generateContent" in model.get("supportedGenerationMethods", []):
                    names.add(model["name"].removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                break
    except error.HTTPError as exc:
        print(f"Google could not list models (HTTP {exc.code}). Check your API key and project access.")
        return
    except (OSError, ValueError, error.URLError):
        print("Could not retrieve the model list. Check your internet connection and retry.")
        return
    print("Models supporting generateContent (image support and quota must be checked separately):")
    print("\n".join(sorted(names)) if names else "No matching models returned.")


def run_cli(call_gemini, api_error):
    parser = argparse.ArgumentParser(description="Fieldnote server diagnostics")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--check-model", action="store_true")
    args = parser.parse_args()
    if args.list_models:
        list_models()
    elif args.check_model:
        print("Checking model:", os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
        try:
            # This text-only check uses a minimal body without a photo.
            request_body = {
                "contents": [{"role": "user", "parts": [{"text": "Reply with OK."}]}],
                "generationConfig": {"maxOutputTokens": 4096},
            }
            call_gemini(request_body, diagnostic=True)
            print("Success: Google accepted a text request. Photo support has not been tested.")
        except api_error as exc:
            print(exc.message)
