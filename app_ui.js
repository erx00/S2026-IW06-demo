// Page details: students can read this after the conversation flow in app.js.
import { describeError, MAX_CONVERSATION_MESSAGES } from "./app_helpers.js";

// 1. Find the HTML elements we will update.
const photoInput = document.querySelector("#image-input");
const photoPreview = document.querySelector("#preview-image");
const questionInput = document.querySelector("#chat-input");
const sendButton = document.querySelector("#send-button");
const retryButton = document.querySelector("#retry-button");
const statusLabel = document.querySelector("#result-status");
const errorMessage = document.querySelector("#chat-error");
const chatContainer = document.querySelector("#chat-messages");

function renderMessages(messages) {
  chatContainer.replaceChildren();
  for (const message of messages) {
    const article = document.createElement("article");
    article.className = message.role;
    const name = document.createElement("strong");
    name.textContent = message.role === "user" ? "You" : "Fieldnote";
    const text = document.createElement("p");
    text.textContent = message.text; // Display model text without treating it as HTML.
    article.append(name, text);
    chatContainer.append(article);
  }
}

export function showModel(config) {
  const label = document.querySelector("#model-status");
  if (!config) {
    label.textContent = "Start the server with python3 server.py, then open http://127.0.0.1:4173.";
    return;
  }
  let keyStatus = "Server needs GEMINI_API_KEY.";
  if (config.configured) {
    keyStatus = "API key configured.";
  }
  label.textContent = `Model: ${config.model}. ${keyStatus}`;
}

export function updatePage(conversation) {
  renderMessages(conversation.messages);
  if (conversation.busy) {
    statusLabel.scrollIntoView({ block: "nearest" });
  }
  const lastMessage = conversation.messages.at(-1);
  const waitingForAnswer = Boolean(lastMessage && lastMessage.role === "user");
  const conversationIsFull = conversation.messages.length >= MAX_CONVERSATION_MESSAGES;
  const canAskQuestion = Boolean(conversation.photo) && !conversation.busy && !waitingForAnswer && !conversationIsFull;
  questionInput.disabled = !canAskQuestion;
  sendButton.disabled = questionInput.disabled;
  retryButton.hidden = !waitingForAnswer || conversation.busy;
}

export function showStatus(text) {
  statusLabel.textContent = text;
  errorMessage.hidden = true;
}

export function showError(error) {
  statusLabel.textContent = "Could not complete the request.";
  errorMessage.textContent = describeError(error);
  errorMessage.hidden = false;
}

export function showPhoto(url) {
  photoPreview.src = url;
  photoPreview.hidden = false;
}

export function clearPage() {
  photoInput.value = "";
  questionInput.value = "";
  photoPreview.hidden = true;
  photoPreview.removeAttribute("src");
  showStatus("Choose a photo to begin.");
}

