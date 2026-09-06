// Supporting browser details, separate from the conversation flow in app.js.
// These limits match the server checks. A completed exchange has two messages.
export const MAX_CONVERSATION_MESSAGES = 40;
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;
const MAX_IMAGE_DIMENSION = 1600;
const REQUEST_TIMEOUT_MS = 75000;
const SUPPORTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export async function preparePhoto(file) {
  const supportedType = SUPPORTED_IMAGE_TYPES.includes(file.type);
  const withinSizeLimit = file.size <= MAX_PHOTO_BYTES;
  if (!supportedType || !withinSizeLimit) {
    throw new Error("Choose a JPG, PNG or WebP up to 10 MB.");
  }
  try {
    const image = await createImageBitmap(file);
    try {
      // Resize to reduce upload size; re-encoding removes original EXIF metadata.
      const longestSide = Math.max(image.width, image.height);
      const scale = Math.min(1, MAX_IMAGE_DIMENSION / longestSide);
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const context = canvas.getContext("2d");
      context.fillStyle = "white";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      const previewUrl = canvas.toDataURL("image/jpeg", 0.9);
      // A data URL has a format prefix, a comma, and then the Base64 image.
      const imageData = previewUrl.split(",")[1];
      return {
        previewUrl: previewUrl,
        photo: { mimeType: "image/jpeg", data: imageData },
      };
    } finally {
      image.close();
    }
  } catch {
    throw new Error("Could not read this photo. Choose another image.");
  }
}

export function describeError(error) {
  if (error.name === "AbortError") {
    return "The request timed out. Please retry.";
  }
  if (error instanceof TypeError || error instanceof SyntaxError) {
    return "Cannot reach the backend. Run python3 server.py and open http://127.0.0.1:4173.";
  }
  return error.message;
}

// Keep request timeout mechanics out of the main lesson.
export function startRequest() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  return {
    signal: controller.signal,
    cancel() {
      controller.abort();
      clearTimeout(timeout);
    },
    finish() {
      clearTimeout(timeout);
    },
  };
}

export function validateAnswer(response, data) {
  if (!response.ok) {
    throw new Error(data.error || "Request failed. Please retry.");
  }
  if (typeof data.text !== "string" || !data.text.trim()) {
    throw new Error("No answer returned. Please retry.");
  }
}
