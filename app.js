import { preparePhoto, validateAnswer, startRequest, MAX_CONVERSATION_MESSAGES } from "./app_helpers.js";
import { showModel, updatePage, showStatus, showError, showPhoto, clearPage } from "./app_ui.js";

// One conversation in memory. Starting over replaces this object.
let conversation;

function reset() {
  if (conversation && conversation.request) {
    conversation.request.cancel();
  }
  conversation = { photo: null, messages: [], busy: false };
  clearPage();
  updatePage(conversation);
}

// Upload a photo, then ask the first question automatically.
async function identify(file) {
  reset();
  const activeConversation = conversation;
  showStatus("Preparing photo…");
  try {
    const preparedPhoto = await preparePhoto(file);
    // A new upload or reset replaces the conversation object while we wait.
    if (activeConversation !== conversation) {
      return;
    }
    activeConversation.photo = preparedPhoto.photo;
    showPhoto(preparedPhoto.previewUrl);
    sendMessage("What bird is this? Explain the visible features and possible lookalikes. What other observations would help?");
  } catch (error) {
    if (activeConversation === conversation) {
      showError(error);
    }
  }
}

// Send the photo and conversation to Python. Python adds the key and calls Gemini.
async function sendMessage(text) {
  const activeConversation = conversation;
  const hasPhoto = activeConversation.photo !== null;
  const requestInProgress = activeConversation.busy;
  const conversationIsFull = activeConversation.messages.length >= MAX_CONVERSATION_MESSAGES;
  if (!hasPhoto || requestInProgress || conversationIsFull) {
    return;
  }

  // Retry calls this without text, so the unanswered question is not added twice.
  if (text !== undefined) {
    const lastMessage = activeConversation.messages.at(-1);
    const waitingForAnswer = lastMessage && lastMessage.role === "user";
    if (!text.trim() || waitingForAnswer) {
      return;
    }
    activeConversation.messages.push({ role: "user", text: text.trim() });
  }
  const lastMessage = activeConversation.messages.at(-1);
  if (!lastMessage || lastMessage.role !== "user") {
    return;
  }

  activeConversation.busy = true;
  activeConversation.request = startRequest();
  showStatus("Waiting for Gemini…");
  updatePage(activeConversation);
  try {
    // Send the request to the Python backend.
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: activeConversation.photo, messages: activeConversation.messages }),
      signal: activeConversation.request.signal,
    });
    // Read the backend response and retain the answer in our conversation.
    const data = await response.json();
    validateAnswer(response, data);
    const answer = data.text;
    // Ignore an answer that belongs to a conversation the user has cleared.
    if (activeConversation !== conversation) {
      return;
    }
    // Push the answer to the conversation.
    activeConversation.messages.push({ role: "model", text: answer });
    if (activeConversation.messages.length >= MAX_CONVERSATION_MESSAGES) {
      showStatus("Start over to begin another conversation.");
    } else {
      showStatus("Ask a follow-up question or add an observation.");
    }
  } catch (error) {
    if (activeConversation === conversation) {
      showError(error);
    }
  } finally {
    activeConversation.request.finish();
    activeConversation.busy = false;
    if (activeConversation === conversation) {
      updatePage(activeConversation);
    }
  }
}

// User actions enter the request pipeline here.
const uploadInput = document.querySelector("#image-input");
const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#chat-input");
const retryControl = document.querySelector("#retry-button");

uploadInput.addEventListener("change", () => {
  const selectedFile = uploadInput.files[0];
  if (selectedFile) {
    identify(selectedFile);
  }
});
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
  messageInput.value = "";
});
retryControl.addEventListener("click", () => sendMessage());
document.querySelector("#new-observation").addEventListener("click", reset);


// Load configuration from Python; the UI helper only displays it.
async function loadModelStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) {
      throw new Error("Server unavailable");
    }
    const config = await response.json();
    showModel(config);
  } catch {
    showModel(null);
  }
}

reset();
loadModelStatus();
