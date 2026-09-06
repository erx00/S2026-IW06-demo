"""The hosted-model lesson: package a conversation and call Gemini."""
import json
import os
from urllib import error, request as http

from errors import validate_payload, validate_settings, gemini_request_error, validate_response, validate_answer

GOOGLE_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = """You are Fieldnote, a helpful birding companion discussing one photographed sighting.
Suggest an identification only as specifically as the image supports. Explain visible field marks,
mention plausible lookalikes, and ask for location, date, size or behavior when helpful. If there is
no bird or the photo is unclear, say so rather than inventing an identification. Distinguish visible
evidence from user observations and general knowledge. Reconsider suggestions when new evidence
arrives. Never invent confidence percentages, sources, sightings, or claim to have searched the web.
Answer follow-up birding questions concisely in plain text, usually under 200 words. Do not use
Markdown formatting. Encourage checking a field guide for uncertain identifications."""


def build_request_body(payload):
    """Build the complete body: system prompt, photo, history, and settings."""
    validate_payload(payload)

    # Each turn says WHO is speaking and WHAT they sent.
    # The role is "user" for questions or "model" for previous answers.
    contents = []
    for message in payload["messages"]:
        turn = {
            "role": message["role"],
            "parts": [{"text": message["text"]}],
        }
        contents.append(turn)

    # A turn can contain more than text: attach the photo to the first question.
    # Base64 is the image represented as text so it can travel inside JSON.
    image = payload["image"]
    photo_part = {
        "inlineData": {
            "mimeType": image["mimeType"],
            "data": image["data"],
        }
    }
    first_message = contents[0]
    first_message["parts"].insert(0, photo_part)
    # Every request includes the instructions, photo, and full conversation.
    request_body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 4096},
    }
    return request_body


def call_gemini(request_body, diagnostic=False):
    """Authenticate and send the prepared request body, then read the answer."""
    # The terminal provides the key; it never comes from browser JavaScript.
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    validate_settings(key, model)
    api_request = http.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    # This is the actual network call: send the request and read Google's JSON.
    try:
        with http.urlopen(api_request, timeout=GOOGLE_TIMEOUT_SECONDS) as response:
            result = json.load(response)
    except (error.URLError, OSError, ValueError) as exc:
        raise gemini_request_error(exc, key, model, diagnostic=diagnostic) from None
    # Read the generated text from the first answer candidate.
    validate_response(result)
    candidate = result["candidates"][0]
    answer_parts = []
    content = candidate.get("content", {})
    for part in content.get("parts", []):
        part_text = part.get("text")
        is_thought = part.get("thought", False)
        if isinstance(part_text, str) and not is_thought:
            answer_parts.append(part_text)
    answer = "\n".join(answer_parts).strip()
    validate_answer(answer)
    return answer


