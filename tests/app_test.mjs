// DOM and network stubs exercise app state without contacting Google.
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
const elements = new Map();
const makeElement = () => ({textContent: "", value: "", hidden: true, disabled: false, children: [],
  scrollIntoView() {this.scrolled = true;},
  classList: {add() {}, remove() {}}, listeners: {}, addEventListener(name, callback) {this.listeners[name] = callback;}, setAttribute() {}, removeAttribute() {},
  replaceChildren() {this.children = [];}, append(...items) {this.children.push(...items);},
  getContext: () => ({fillRect() {}, drawImage() {}}), toDataURL: () => "data:image/jpeg;base64,/9j/dGVzdA=="});
const calls = [];
const context = vm.createContext({console, AbortController, setTimeout, clearTimeout,
  URL: {createObjectURL: () => "blob:test", revokeObjectURL() {}},
  createImageBitmap: async () => ({width: 2000, height: 1000, close() {}}),
  document: {querySelector(id) {if (!elements.has(id)) elements.set(id, makeElement()); return elements.get(id);},
    querySelectorAll: () => [], createElement: makeElement},
  fetch: (url, options) => {
    if (url === "/api/status") return Promise.resolve({ok: true, json: async () => ({configured: true, model: "test-model"})});
    assert.equal(url, "/api/chat");
    return new Promise(resolve => calls.push({body: JSON.parse(options.body), signal: options.signal,
      reply(text, ok = true) {resolve({ok, json: async () => ok ? {text} : {error: text}});}}));
  }});
// Run the real helper implementation in the same simulated browser context.
vm.runInContext(readFileSync("app_helpers.js", "utf8").replaceAll("export ", ""), context);
vm.runInContext(readFileSync("app_ui.js", "utf8").replace(/^import .*;[^\n]*\n/gm, "").replaceAll("export ", ""), context);
vm.runInContext(readFileSync("app.js", "utf8").replace(/^import .*;[^\n]*\n/gm, ""), context);
const run = code => vm.runInContext(code, context);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
elements.get("#image-input").files = [{type: "image/jpeg", size: 100}];
elements.get("#image-input").listeners.change();
await tick();
assert.equal(calls.length, 1);
assert.equal(elements.get("#result-status").textContent, "Waiting for Gemini…");
assert.equal(elements.get("#result-status").scrolled, true);
assert.equal(elements.get("#model-status").textContent, "Model: test-model. API key configured.");
assert.equal(calls[0].body.messages.length, 1);
assert.equal(calls[0].body.image.mimeType, "image/jpeg");
assert.equal(elements.get("#send-button").disabled, true);
calls[0].reply("Possibly a robin.");
await tick();
assert.equal(elements.get("#send-button").disabled, false);
elements.get("#chat-input").value = "Seen in New Jersey.";
let prevented = false;
elements.get("#chat-form").listeners.submit({preventDefault() {prevented = true;}});
assert.equal(prevented, true);
assert.equal(elements.get("#chat-input").value, "");
assert.equal(calls[1].body.messages.length, 3);
assert.equal(calls[1].body.messages[1].text, "Possibly a robin.");
assert.deepEqual(calls[1].body.image, calls[0].body.image);
calls[1].reply("Quota reached", false);
await tick();
assert.equal(elements.get("#retry-button").hidden, false);
elements.get("#retry-button").listeners.click();
assert.deepEqual(calls[2].body, calls[1].body);
calls[2].reply("That location supports the suggestion.");
await tick();
assert.equal(run("conversation.messages.length"), 4);
run('sendMessage("What does it eat?")');
elements.get("#new-observation").listeners.click();
assert.equal(calls[3].signal.aborted, true);
await run('identify({type:"image/png", size:100})');
calls[4].reply("A new sighting.");
await tick();
calls[3].reply("Stale answer must not appear");
await tick();
assert.equal(run("conversation.messages.length"), 2);
assert.equal(run("conversation.messages[1].text"), "A new sighting.");
await run('identify({type:"text/plain", size:100})');
assert.equal(calls.length, 5);
await run('identify({type:"image/jpeg", size:11000000})');
assert.equal(calls.length, 5);
assert.equal(run("conversation.messages.length"), 0);
// A failed question remains in history once, and retries reuse that question.
await run('identify({type:"image/jpeg", size:100})');
calls[5].reply("<script>alert(1)</script>");
await tick();
assert.equal(elements.get("#chat-messages").children[1].children[1].textContent, "<script>alert(1)</script>");
for (let i = 0; i < 19; i++) {
  run('sendMessage("Another observation")');
  calls.at(-1).reply("Answer");
  await tick();
}
assert.equal(run("conversation.messages.length"), 40);
assert.equal(elements.get("#send-button").disabled, true);
const count = calls.length;
run('sendMessage("One too many")');
assert.equal(calls.length, count);
console.log("PASS: image upload, chat context, duplicate-free retries, reset/cancellation, stale replies, and file validation.");
