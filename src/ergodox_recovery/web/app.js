"use strict";

const token = document.querySelector('meta[name="recovery-token"]').content;
const headers = {"Content-Type": "application/json", "X-Recovery-Token": token};
let session = null;
let layout = null;
let selectedPosition = null;
let armed = false;
let captureTimer = null;
let pendingModifier = null;

const byId = (id) => document.getElementById(id);
const layerSelect = byId("layer");
const kindInput = byId("kind");
const valueInput = byId("value");
const holdInput = byId("hold-value");
const targetInput = byId("target-layer");
const confidenceInput = byId("confidence");
const notesInput = byId("notes");

function currentLayer() {
  return session.layers.find((layer) => layer.id === layerSelect.value) || session.layers[0];
}

function emptyBinding() {
  return {kind: "unknown", value: "", hold_value: "", target_layer: "", confidence: "unknown", notes: ""};
}

function positionBinding() {
  if (!selectedPosition) return emptyBinding();
  return currentLayer().bindings[selectedPosition] || emptyBinding();
}

function setStatus(message, failed = false) {
  const element = byId("save-status");
  element.textContent = message;
  element.style.color = failed ? "var(--danger)" : "var(--muted)";
}

async function saveSession() {
  setStatus("Saving locally…");
  const response = await fetch("/api/session", {method: "PUT", headers, body: JSON.stringify(session)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to save session");
  session.updated_at = result.updated_at;
  setStatus("Saved locally");
}

function renderLayerOptions() {
  layerSelect.replaceChildren();
  targetInput.replaceChildren(new Option("Choose a layer", ""));
  session.layers.forEach((layer, index) => {
    layerSelect.add(new Option(`${index}: ${layer.name}`, layer.id));
    targetInput.add(new Option(layer.name, layer.id));
  });
}

function renderEditor() {
  const enabled = selectedPosition !== null;
  byId("save").disabled = !enabled;
  byId("selected-title").textContent = enabled ? `Position ${selectedPosition}` : "Select a key";
  byId("capture-help").textContent = enabled
    ? "Double-click this key in the diagram to arm capture. Confirm tap-holds, macros, combos, and layer actions manually."
    : "Choose a physical key in the diagram first.";
  const binding = positionBinding();
  kindInput.value = binding.kind;
  valueInput.value = binding.value;
  holdInput.value = binding.hold_value;
  targetInput.value = binding.target_layer;
  confidenceInput.value = binding.confidence;
  notesInput.value = binding.notes;
}

function mappedClass(binding) {
  if (!binding || binding.kind === "unknown") return "";
  return ["unknown", "inferred"].includes(binding.confidence) ? "uncertain" : "mapped";
}

function renderKeyboard() {
  const keyboard = byId("keyboard");
  keyboard.replaceChildren();
  const layer = currentLayer();
  for (let rowIndex = 0; rowIndex < layout.half_row_key_counts.length; rowIndex += 1) {
    const row = document.createElement("div");
    row.className = "key-row";
    ["left", "right"].forEach((side) => {
      const half = document.createElement("div");
      half.className = `half ${side}`;
      layout.positions
        .filter((position) => position.row === rowIndex && position.side === side)
        .sort((first, second) => first.visual_column - second.visual_column)
        .forEach((position) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = `key ${mappedClass(layer.bindings[position.id])}`;
          if (position.id === selectedPosition) button.classList.add("selected");
          if (armed && position.id === selectedPosition) button.classList.add("armed");
          button.textContent = position.label;
          button.title = layer.bindings[position.id]
            ? bindingLabel(layer.bindings[position.id])
            : `${position.id}: unresolved`;
          button.addEventListener("click", () => {
            disarm();
            selectedPosition = position.id;
            document.querySelectorAll(".key.selected, .key.armed").forEach((key) => {
              key.classList.remove("selected", "armed");
            });
            button.classList.add("selected");
            renderEditor();
          });
          button.addEventListener("dblclick", (event) => {
            event.preventDefault();
            selectedPosition = position.id;
            arm();
            button.classList.add("selected", "armed");
            renderEditor();
          });
          half.append(button);
        });
      row.append(half);
    });
    keyboard.append(row);
  }
  const assigned = Object.values(layer.bindings).filter((binding) => binding.kind !== "unknown").length;
  byId("progress").textContent = `${assigned} / ${layout.key_count} mapped on ${layer.name}`;
}

function bindingLabel(binding) {
  if (binding.kind === "key_press") return `&kp ${binding.value}`;
  if (binding.kind === "mod_tap") return `&mt ${binding.hold_value} ${binding.value}`;
  if (binding.kind === "raw") return binding.value;
  if (["momentary_layer", "to_layer", "toggle_layer"].includes(binding.kind)) {
    return `${binding.kind} → ${binding.target_layer}`;
  }
  return binding.kind;
}

function editorBinding() {
  return {
    kind: kindInput.value,
    value: valueInput.value.trim(),
    hold_value: holdInput.value.trim(),
    target_layer: targetInput.value,
    confidence: confidenceInput.value,
    notes: notesInput.value.trim(),
  };
}

function normalizeKey(event) {
  const special = {
    Backspace: "BACKSPACE", Tab: "TAB", Enter: "RETURN", Escape: "ESCAPE", Space: "SPACE",
    Delete: "DELETE", Insert: "INSERT", Home: "HOME", End: "END", PageUp: "PAGE_UP",
    PageDown: "PAGE_DOWN", ArrowLeft: "LEFT_ARROW", ArrowRight: "RIGHT_ARROW",
    ArrowUp: "UP_ARROW", ArrowDown: "DOWN_ARROW", CapsLock: "CAPSLOCK",
    PrintScreen: "PRINTSCREEN", ScrollLock: "SCROLLLOCK", Pause: "PAUSE_BREAK",
  };
  const modifierByCode = {
    ShiftLeft: "LEFT_SHIFT", ShiftRight: "RIGHT_SHIFT", ControlLeft: "LEFT_CONTROL",
    ControlRight: "RIGHT_CONTROL", AltLeft: "LEFT_ALT", AltRight: "RIGHT_ALT",
    MetaLeft: "LEFT_GUI", MetaRight: "RIGHT_GUI",
  };
  const plainByCode = {
    Backquote: "GRAVE", Minus: "MINUS", Equal: "EQUAL",
    BracketLeft: "LEFT_BRACKET", BracketRight: "RIGHT_BRACKET", Backslash: "BACKSLASH",
    Semicolon: "SEMICOLON", Quote: "SINGLE_QUOTE", Comma: "COMMA", Period: "PERIOD",
    Slash: "SLASH", ContextMenu: "K_APPLICATION", NumLock: "KP_NUMLOCK",
    NumpadAdd: "KP_PLUS", NumpadDecimal: "KP_DOT", NumpadDivide: "KP_DIVIDE",
    NumpadEnter: "KP_ENTER", NumpadMultiply: "KP_MULTIPLY", NumpadSubtract: "KP_MINUS",
  };
  const shiftedByCode = {
    Backquote: "TILDE", Digit1: "EXCLAMATION", Digit2: "AT_SIGN", Digit3: "HASH",
    Digit4: "DOLLAR", Digit5: "PERCENT", Digit6: "CARET", Digit7: "AMPERSAND",
    Digit8: "ASTERISK", Digit9: "LEFT_PARENTHESIS", Digit0: "RIGHT_PARENTHESIS",
    Minus: "UNDERSCORE", Equal: "PLUS", BracketLeft: "LEFT_BRACE",
    BracketRight: "RIGHT_BRACE", Backslash: "PIPE", Semicolon: "COLON",
    Quote: "DOUBLE_QUOTES", Comma: "LESS_THAN", Period: "GREATER_THAN", Slash: "QUESTION",
  };
  if (modifierByCode[event.code]) return modifierByCode[event.code];
  if (special[event.code]) return special[event.code];
  if (event.shiftKey && shiftedByCode[event.code]) return shiftedByCode[event.code];
  if (plainByCode[event.code]) return plainByCode[event.code];
  if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3);
  if (/^Digit[0-9]$/.test(event.code)) return `NUMBER_${event.code.slice(5)}`;
  if (/^Numpad[0-9]$/.test(event.code)) return `KP_NUMBER_${event.code.slice(6)}`;
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(event.code)) return event.code;
  return null;
}

function arm() {
  if (!selectedPosition) return;
  armed = true;
  pendingModifier = null;
  clearTimeout(captureTimer);
  captureTimer = setTimeout(() => {
    disarm();
    renderKeyboard();
    renderEditor();
    setStatus("Capture timed out without recording a key", true);
  }, 10000);
  byId("armed-banner").hidden = false;
}

function disarm() {
  armed = false;
  pendingModifier = null;
  clearTimeout(captureTimer);
  captureTimer = null;
  byId("armed-banner").hidden = true;
}

async function recordCaptured(normalized) {
  currentLayer().bindings[selectedPosition] = {
    kind: "key_press", value: normalized, hold_value: "", target_layer: "",
    confidence: "observed", notes: "",
  };
  renderKeyboard();
  renderEditor();
  try { await saveSession(); } catch (error) { setStatus(error.message, true); }
}

document.addEventListener("keydown", async (event) => {
  if (!armed || event.repeat) return;
  event.preventDefault();
  event.stopPropagation();
  const normalized = normalizeKey(event);
  if (!normalized) {
    disarm();
    setStatus(`Key ${event.code || "event"} needs a manual binding`, true);
    return;
  }
  if (["ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight"].includes(event.code)) {
    pendingModifier = {code: event.code, value: normalized};
    return;
  }
  disarm();
  await recordCaptured(normalized);
}, true);

document.addEventListener("keyup", async (event) => {
  if (!armed || !pendingModifier || pendingModifier.code !== event.code) return;
  event.preventDefault();
  event.stopPropagation();
  const normalized = pendingModifier.value;
  disarm();
  await recordCaptured(normalized);
}, true);

byId("save").addEventListener("click", async () => {
  currentLayer().bindings[selectedPosition] = editorBinding();
  renderKeyboard();
  try { await saveSession(); } catch (error) { setStatus(error.message, true); }
});
layerSelect.addEventListener("change", () => { disarm(); selectedPosition = null; renderKeyboard(); renderEditor(); });
byId("add-layer").addEventListener("click", async () => {
  const name = window.prompt("Name the layer");
  if (!name || !name.trim()) return;
  if (session.layers.some((layer) => layer.name === name.trim())) {
    setStatus("That layer name is already in use", true); return;
  }
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "layer";
  let id = base; let suffix = 2;
  while (session.layers.some((layer) => layer.id === id)) { id = `${base}-${suffix}`; suffix += 1; }
  session.layers.push({id, name: name.trim(), notes: "", bindings: {}});
  renderLayerOptions(); layerSelect.value = id; selectedPosition = null; renderKeyboard(); renderEditor();
  try { await saveSession(); } catch (error) { setStatus(error.message, true); }
});
window.addEventListener("blur", () => { disarm(); renderKeyboard(); renderEditor(); });
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { disarm(); renderKeyboard(); renderEditor(); }
});

async function initialize() {
  try {
    const [sessionResponse, layoutResponse] = await Promise.all([
      fetch("/api/session", {headers}), fetch("/api/layout", {headers}),
    ]);
    if (!sessionResponse.ok || !layoutResponse.ok) throw new Error("Local server rejected the session token");
    session = await sessionResponse.json();
    layout = await layoutResponse.json();
    byId("session-name").textContent = `${session.name} · ${session.target.board} / ${session.target.shield}`;
    renderLayerOptions(); renderKeyboard(); renderEditor(); setStatus("Saved locally");
  } catch (error) { setStatus(error.message, true); }
}

initialize();
