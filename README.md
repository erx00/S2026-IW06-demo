# Fieldnote

Fieldnote is a photo-and-chat application for exploring bird sightings. A user uploads a photo, receives an identification suggestion from Google Gemini, and asks follow-up questions or adds observations.

The code demonstrates how a browser application accesses a hosted model through a Python backend. The main request pipeline is in `app.js`, `server.py`, and `gemini.py`. Supporting modules handle the interface, image preparation, validation, and errors.

## Codebase map

| File | Responsibility |
| --- | --- |
| `index.html` | Photo input, preview, conversation, question form, and model/data notices |
| `styles.css` | Page layout and visual styling |
| `app.js` | Event listeners, conversation state, photo identification flow, requests to Python, and storing answers |
| `server.py` | Flask routes that serve the page and connect browser requests to Gemini |
| `gemini.py` | System prompt, image/text message formatting, authenticated Gemini requests, and answer extraction |
| `app_ui.js` | Page rendering, control updates, waiting/error messages, and model-status display |
| `app_helpers.js` | Image resizing and encoding, timeouts, cancellation, and browser response checks |
| `errors.py` | Input/configuration validation, response checks, error messages, and API-key redaction |
| `diagnostics.py` | Commands for listing models and checking model access |
| `requirements.txt` | Python dependencies |
| `tests/` | Backend and browser lifecycle tests using simulated responses |

## Setup and configuration

You need Python 3.10+ and an API key from Google AI Studio. From the project directory, create a virtual environment and install Flask:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

In a zsh terminal, run the following command, then paste your key at the prompt and press Enter. The `-s` option hides the input:

```zsh
read -s "GEMINI_API_KEY?Paste your Gemini API key: "
```

Export the variable and start the server from that same terminal:

```zsh
export GEMINI_API_KEY
python3 server.py
```

Open **http://127.0.0.1:4173**. Press Ctrl+C to stop the server. In a new terminal session, activate `.venv` and set the key before starting Python.

| Environment variable | Purpose | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Authenticates requests to Google | Required |
| `GEMINI_MODEL` | Selects the model | `gemini-3.6-flash` |
| `PORT` | Local web-server port | `4173` |

For example, to explicitly select the model:

```zsh
export GEMINI_MODEL="gemini-3.6-flash"
python3 server.py
```

Restart the server after changing its environment variables. The Python process inherits exported variables from the shell that starts it. The app does not load `.env` files.

## The request pipeline

```text
User selects a photo
  -> app.js: identify(file)
  -> app_helpers.js: preparePhoto(file)
  -> app.js: sendMessage(initial question)
  -> POST /api/chat
  -> server.py: chat()
  -> gemini.py: build_request_body(payload)
  -> gemini.py: call_gemini(request_body)
  -> Google generates an answer
  -> server.py returns {"text": answer}
  -> app.js stores the answer
  -> app_ui.js displays the conversation
```

The file-input change listener in `app.js` calls `identify()`. The question-form submit listener calls `sendMessage()` directly for follow-ups, reusing the prepared photo and conversation history. Retry and reset listeners are also in `app.js`. `app_ui.js` displays state and makes no API requests.

### 1. Browser: prepare a photo and collect messages

`app.js` keeps a `conversation` object in memory. It contains the prepared photo, a message list, and request state.

- `reset()` cancels the browser's active request and creates an empty conversation.
- `identify(file)` prepares the image, displays its preview, and sends the initial identification question.
- `sendMessage(text)` adds a user message, submits the photo and history to Python, reads the response, and appends the model's answer.

The browser sends JSON with this structure:

```javascript
{
  image: {
    mimeType: "image/jpeg",
    data: "...Base64 image data..."
  },
  messages: [
    { role: "user", text: "What bird is this?" }
  ]
}
```

`fetch("/api/chat", ...)` sends this data to the local Python server. The API key is not part of the browser request.

### 2. Flask: receive the request

The main route in `server.py` is:

```python
@app.post("/api/chat")
def chat():
    payload = request.get_json()
    request_body = build_request_body(payload)
    answer = call_gemini(request_body)
    return {"text": answer}
```

The decorator connects POST requests at `/api/chat` to `chat()`. Flask parses incoming JSON through `request.get_json()` and converts the returned dictionary into a JSON response.

The server also provides:

| Route | Response |
| --- | --- |
| `/` and `/index.html` | The webpage |
| `/app.js`, `/app_helpers.js`, `/app_ui.js` | Browser JavaScript modules |
| `/styles.css` | Stylesheet |
| `/api/status` | Configured model name and whether an API key is present |

Only these public files are served. Python files, credentials, and repository metadata are not exposed through the file route.

### 3. Gemini: package the photo and prompts

`build_request_body()` in `gemini.py` builds the full JSON body, including the system instruction, conversation contents, and generation settings. It validates the input and translates the browser's messages into Gemini's `contents` format. Each turn contains a `role` identifying the speaker and `parts` containing text or an image.

For a conversation with a follow-up question, the contents look like:

```python
[
    {
        "role": "user",
        "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": "...Base64 image..."}},
            {"text": "What bird is this?"},
        ],
    },
    {"role": "model", "parts": [{"text": "Possibly a robin."}]},
    {"role": "user", "parts": [{"text": "What features identify it?"}]},
]
```

Base64 represents image bytes as text that can travel inside JSON. The photo appears in the first user turn. Every request includes that photo, the previous questions and answers, and the latest question.

`SYSTEM_PROMPT` describes the assistant's behavior: explain visible evidence, consider lookalikes, ask for useful observations, and admit uncertainty. It is included separately as `systemInstruction` on every Gemini request.

### 4. Gemini: authenticate, send, and read the answer

`call_gemini(request_body)` receives the completed body from `build_request_body()`. It reads `GEMINI_API_KEY` and `GEMINI_MODEL` using `os.environ`, authenticates the request, sends the body, and reads the answer.

The request targets:

```text
https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
```

The API key is placed in the `x-goog-api-key` HTTP header. `http.Request(...)` constructs the request; this code actually sends it and reads Google's JSON response:

```python
with http.urlopen(api_request, timeout=GOOGLE_TIMEOUT_SECONDS) as response:
    result = json.load(response)
```

The function validates the response and extracts text from the first generated answer candidate, excluding parts marked as thoughts. It returns that text to the Flask route.

Google's endpoint and request format are documented in the [Gemini API reference](https://ai.google.dev/api/generate-content).

### 5. Browser: store and display the answer

`sendMessage()` reads the server's JSON response and appends its text to the conversation with the role `model`. `updatePage()` in `app_ui.js` renders the messages and updates the controls.

The app waits for the complete answer. While a request is pending, “Waiting for Gemini…” appears below the conversation and scrolls into view.

## Conversation state and errors

A failed question remains at the end of the message list. Retry resends the same conversation without adding that question twice. Requests are not retried automatically.

Starting over replaces the conversation object. Asynchronous functions retain the object they started with and compare it with the current conversation before updating the page. This prevents a late answer from appearing in a new sighting. Cancelling the browser request does not guarantee cancellation of work already submitted to Google.

`errors.py` checks inputs, model configuration, and returned data. Its `APIError` class carries an HTTP status and a readable message. The Flask error handlers return errors as JSON for the browser to display. Error helpers distinguish quota failures, timeouts, DNS problems, and certificate failures without exposing credentials.

## Data handling and limits

- Gemini is a proprietary model hosted by Google. Model inference happens on Google's servers.
- The browser accepts JPG, PNG, and WebP files up to 10 MB. It resizes them to at most 1,600 pixels on the longest edge and re-encodes them as JPEG, removing original EXIF metadata.
- Each question and retry sends the prepared photo and full conversation to Google. Google processes submitted data under its [Gemini API terms](https://ai.google.dev/gemini-api/terms).
- Fieldnote keeps the conversation in tab memory. Refreshing or starting over clears it. The backend does not save photos or conversations.
- The key stays on the backend and is sent to Google over HTTPS. It should not be placed in browser code, committed to the repository, or shared in chat.
- Each observation permits 20 questions, with up to 4,000 characters per user question. Browser limits and server checks must remain consistent when edited.
- The backend uses a 60-second network timeout for Google requests; the browser cancels its request after 75 seconds. These are waiting limits, not deliberate delays.
- Identifications are suggestions, not verified facts. The assistant has no connected web search or field-guide database.
- The Flask server runs on the local computer and checks request origins. A public deployment would need authentication and usage controls.

## Diagnostics

Run these commands from the activated environment with your key configured:

```sh
python3 server.py --list-models
python3 server.py --check-model
```

`--list-models` lists models advertising support for `generateContent`. Listing does not guarantee access, image support, or available quota.

`--check-model` submits one small text request and reports success or a redacted error. It does not test photo identification. The webpage's key status only checks that a key is present; it does not verify access to Google.

## Tests

With the virtual environment activated:

```sh
python3 -m unittest discover -s tests -v
```

For browser lifecycle tests, install Deno and run:

```sh
deno run --allow-read tests/app_test.mjs
```

The tests use simulated model responses and do not submit requests to Google. They cover conversation packaging, authentication headers, validation, errors, public routes, retries, resets, and handling late responses.

For a live check, start the app with your key, upload a known bird photo, and ask a follow-up that adds location or behavior. Check that the answer uses the context and that starting over clears the sighting.
