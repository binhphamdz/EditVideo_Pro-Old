(function () {
if (globalThis.__editVideoProTikTokContentLoaded) {
  return;
}
globalThis.__editVideoProTikTokContentLoaded = true;

const DEFAULT_WS_URL = "ws://127.0.0.1:8765";
const TARGET_URL = "https://shop.tiktok.com/streamer/showcase/product/list";
const UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload";
const CONNECT_RETRY_MS = 3000;
const STEP_DELAY_MS = 600;
let ws = null;
let connecting = false;
let isFilling = false;
let receiverId = "";
const processedRequestIds = new Set();
const activeRequestIds = new Set();
const PENDING_URL_KEY = "tiktok_auto_link_pending_url";
const BADGE_ID = "tiktok-auto-link-badge";
const APP_ID = "editvideo_pro_tiktok_agent_v1";

setStatusBadge("loaded");
log("Content script loaded.");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setStatusBadge(text) {
  let badge = document.getElementById(BADGE_ID);
  if (!badge) {
    badge = document.createElement("div");
    badge.id = BADGE_ID;
    badge.style.position = "fixed";
    badge.style.right = "12px";
    badge.style.bottom = "12px";
    badge.style.zIndex = "999999";
    badge.style.background = "#0f172a";
    badge.style.color = "#ffffff";
    badge.style.padding = "6px 10px";
    badge.style.borderRadius = "10px";
    badge.style.fontSize = "12px";
    badge.style.fontFamily = "Arial, sans-serif";
    badge.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";
    badge.style.opacity = "0.9";
    badge.textContent = "Auto Link: ready";
    document.documentElement.appendChild(badge);
  }
  if (text) {
    badge.textContent = "Auto Link: " + text;
  }
}

function log(msg) {
  console.log("[TikTok Auto Link]", msg);
  setStatusBadge(msg);
}

function textEquals(el, text) {
  return (el && el.textContent || "").trim() === text;
}

function findButtonByText(text) {
  const buttons = Array.from(document.querySelectorAll("button"));
  return buttons.find((btn) => textEquals(btn, text)) ||
    buttons.find((btn) => (btn.textContent || "").trim().includes(text)) ||
    null;
}

function findClickableButtonByTexts(texts) {
  for (const text of texts) {
    const btn = findButtonByText(text);
    if (isClickable(btn)) return btn;
  }
  return null;
}

function findAddLinkEntryButton() {
  const buttons = Array.from(document.querySelectorAll("button"));
  return buttons.find((btn) => {
    if (!isClickable(btn)) return false;
    const text = (btn.textContent || "").trim();
    const hasPlus = Boolean(btn.querySelector('[data-icon="Plus"], [data-testid="Plus"]'));
    const rect = btn.getBoundingClientRect();
    return text === "Thêm" && (hasPlus || rect.width >= 220);
  }) || findClickableButtonByTexts(["Thêm liên kết", "Add link"]);
}

async function waitAndClickAddLinkEntry(timeoutMs = 90000) {
  log("Waiting add-link entry button...");
  const btn = await waitForElement(findAddLinkEntryButton, timeoutMs);
  if (!btn) throw new Error("Không thấy nút Thêm để mở phần thêm liên kết");
  btn.scrollIntoView({ block: "center", inline: "center" });
  await sleep(900);
  btn.click();
  log("Clicked add-link entry button.");
}

async function waitAndClickButtonByTexts(texts, timeoutMs = 60000) {
  log("Waiting button: " + texts.join(" / "));
  const btn = await waitForElement(() => findClickableButtonByTexts(texts), timeoutMs);
  if (!btn) throw new Error("Không thấy nút: " + texts.join(" / "));
  btn.scrollIntoView({ block: "center", inline: "center" });
  await sleep(800);
  btn.click();
  log("Clicked button: " + texts.join(" / "));
}

function findUrlInput() {
  return document.querySelector("input[data-tid='m4b_input'][placeholder*='URL sản phẩm']") ||
    document.querySelector("input[data-tid='m4b_input'][placeholder*='URL']") ||
    document.querySelector("input[placeholder*='URL sản phẩm']") ||
    document.querySelector("input[placeholder^='Vui lòng nhập URL']");
}

function findAddProductButton() {
  return document.querySelector("button.pc_add_product") || findButtonByText("Thêm sản phẩm");
}

function findCloseDrawerButton() {
  return document.querySelector("span.arco-drawer-close-icon");
}

function findSuccessToast() {
  const messages = Array.from(document.querySelectorAll("span.arco-message-content, .arco-message-content"));
  return messages.find((el) => (el.textContent || "").includes("Đã thêm thành công")) || null;
}

function readReceiverIdFromPage() {
  const el = document.querySelector(
    "span.text-body-s-medium.text-white\\/60.px-8.py-3"
  );
  return el ? el.textContent.trim() : "";
}

function sendHello() {
  if (!receiverId) {
    return;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "hello", appId: APP_ID, receiver: receiverId }));
    } catch {
      // ignore
    }
  }
}

function wakeBackground() {
  try {
    chrome.runtime.sendMessage({ type: "wake", appId: APP_ID });
  } catch {
    // ignore
  }
}

function ensureReceiverId(callback) {
  chrome.storage.local.get(["receiverId"], (result) => {
    receiverId = (result.receiverId || "").trim();
    if (!receiverId) {
      receiverId = "chrome-" + Math.random().toString(36).slice(2, 8);
      chrome.storage.local.set({ receiverId }, () => callback(receiverId));
      return;
    }
    callback(receiverId);
  });
}

function updateReceiverId(newId) {
  if (!newId || newId === receiverId) {
    return;
  }
  receiverId = newId;
  chrome.storage.local.set({ receiverId: receiverId });
  log("Receiver ID set: " + receiverId);
  sendHello();
}

function startReceiverIdWatch() {
  if (receiverId) {
    return;
  }
  let tries = 0;
  const timer = setInterval(() => {
    tries += 1;
    const found = readReceiverIdFromPage();
    if (found) {
      updateReceiverId(found);
      clearInterval(timer);
      return;
    }
    if (tries >= 60) {
      clearInterval(timer);
    }
  }, 1000);
}

async function waitForElement(getter, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const el = getter();
    if (el) {
      return el;
    }
    await sleep(200);
  }
  return null;
}

async function clickIfExists(getter) {
  const el = getter();
  if (isClickable(el)) {
    el.scrollIntoView({ block: "center", inline: "center" });
    await sleep(150);
    el.click();
    return true;
  }
  return false;
}

function isClickable(el) {
  if (!el || el.disabled) return false;
  if (el.getAttribute("aria-disabled") === "true" || el.getAttribute("data-disabled") === "true") return false;
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function isVisible(el) {
  if (!el) return false;
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function findVisibleByText(texts) {
  const lowerTexts = texts.map((text) => text.toLowerCase());
  const nodes = Array.from(document.querySelectorAll("button, [role='button'], span, div"));
  return nodes.find((node) => {
    if (!isVisible(node)) return false;
    const text = (node.textContent || "").trim().toLowerCase();
    return text && lowerTexts.some((needle) => text.includes(needle));
  }) || null;
}

function findButtonInModal(text) {
  const modals = Array.from(document.querySelectorAll(".TUXModal, [role='dialog']")).filter(isVisible);
  const roots = modals.length ? modals : [document];
  for (const root of roots) {
    const buttons = Array.from(root.querySelectorAll("button"));
    const found = buttons.find((btn) => isClickable(btn) && (btn.textContent || "").trim().includes(text));
    if (found) return found;
  }
  return null;
}

function findModalByTitles(titles) {
  const lowerTitles = titles.map((title) => title.toLowerCase());
  return Array.from(document.querySelectorAll(".TUXModal, [role='dialog']")).find((modal) => {
    if (!isVisible(modal)) return false;
    const title = (modal.getAttribute("title") || "").trim().toLowerCase();
    const text = (modal.textContent || "").trim().toLowerCase();
    return lowerTitles.some((needle) => title.includes(needle) || text.includes(needle));
  }) || null;
}

function findPrimaryButtonIn(root, texts) {
  const lowerTexts = texts.map((text) => text.toLowerCase());
  return Array.from(root.querySelectorAll("button.TUXButton--primary, button")).find((btn) => {
    if (!isVisible(btn)) return false;
    const text = (btn.textContent || "").trim().toLowerCase();
    return lowerTexts.some((needle) => text.includes(needle));
  }) || null;
}

function isDisabledButton(btn) {
  return !btn || btn.disabled || btn.getAttribute("aria-disabled") === "true" || btn.getAttribute("data-disabled") === "true";
}

async function waitPrimaryButtonEnabled(rootGetter, texts, timeoutMs = 30000) {
  const btn = await waitForElement(() => {
    const root = rootGetter();
    if (!root) return null;
    const found = findPrimaryButtonIn(root, texts);
    return found && !isDisabledButton(found) ? found : null;
  }, timeoutMs);
  if (!btn) throw new Error("Nút " + texts.join("/") + " vẫn bị disabled hoặc không thấy");
  return btn;
}

function findAnyButtonInModal(text) {
  const modals = Array.from(document.querySelectorAll(".TUXModal, [role='dialog']")).filter(isVisible);
  const roots = modals.length ? modals : [document];
  for (const root of roots) {
    const buttons = Array.from(root.querySelectorAll("button"));
    const found = buttons.find((btn) => isVisible(btn) && (btn.textContent || "").trim().includes(text));
    if (found) return found;
  }
  return null;
}

function clickElementLikeUser(el) {
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const x = Math.max(1, Math.floor(rect.left + rect.width / 2));
  const y = Math.max(1, Math.floor(rect.top + rect.height / 2));
  const target = document.elementFromPoint(x, y) || el;
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
    const EventCtor = type.startsWith("pointer") ? PointerEvent : MouseEvent;
    target.dispatchEvent(new EventCtor(type, {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: x,
      clientY: y,
      pointerId: 1,
      pointerType: "mouse",
      isPrimary: true,
    }));
  }
}

function setNativeChecked(input, checked) {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "checked");
  if (descriptor && descriptor.set) {
    descriptor.set.call(input, checked);
  } else {
    input.checked = checked;
  }
}

async function clickButtonInModal(text, timeoutMs = 30000) {
  const btn = await waitForElement(() => findButtonInModal(text), timeoutMs);
  if (!btn) throw new Error(`Không thấy nút ${text}`);
  btn.scrollIntoView({ block: "center", inline: "center" });
  await sleep(500);
  btn.click();
  log(`Clicked modal button: ${text}`);
}

function hasProductSelectorRows() {
  const modal = Array.from(document.querySelectorAll(".product-selector-modal, .TUXModal, [role='dialog']")).find(isVisible);
  return Boolean(modal && modal.querySelector("tbody input.TUXRadioStandalone-input[type='radio'], tbody input[type='radio']"));
}

async function clickInitialNextIfNeeded() {
  await sleep(1000);
  if (hasProductSelectorRows()) {
    log("Product table already open; skip initial Next.");
    return;
  }
  const modal = await waitForElement(() => findModalByTitles(["Add link", "Thêm liên kết"]), 30000);
  if (!modal) throw new Error("Không tìm thấy modal Thêm liên kết/Add link");

  try {
    const selected = modal.querySelector("button.TUXSelect-button .select-option-label");
    const selectedText = (selected && selected.textContent || "").trim().toLowerCase();
    if (selected && !["products", "sản phẩm"].includes(selectedText)) {
      selected.closest("button").click();
      await sleep(500);
      const option = findVisibleByText(["Products", "Sản phẩm"]);
      if (option) option.click();
      await sleep(500);
      log("Selected Products/Sản phẩm in Add link modal.");
    }
  } catch {
    // Nếu TikTok đã chọn sẵn Sản phẩm thì bỏ qua.
  }

  const nextBtn = await waitPrimaryButtonEnabled(() => modal, ["Next", "Tiếp"], 30000);
  nextBtn.click();
  log("Clicked modal button: Tiếp");
}

async function selectFirstProductInModal(timeoutMs = 30000) {
  log("Waiting for product selector modal...");
  const radio = await waitForElement(() => {
    const modal = document.querySelector(".TUXModal.product-selector-modal") || findModalByTitles(["Thêm liên kết sản phẩm", "Add product"]);
    if (!modal || !isVisible(modal)) return null;
    const input = modal.querySelector(".product-table input[type='radio'], tbody input.TUXRadioStandalone-input[type='radio'], tbody input[type='radio']");
    return input || null;
  }, timeoutMs);
  if (!radio) throw new Error("Dòng sản phẩm đầu tiên không có radio");
  const modal = radio.closest(".TUXModal") || document;
  const row = radio.closest("tr") || radio.closest(".TUXRadio") || radio;
  const label = radio.id ? row.querySelector(`label[for="${CSS.escape(radio.id)}"]`) : null;
  const targets = [
    row.querySelector(".TUXRadioStandalone-circleOutside"),
    row.querySelector(".TUXRadioStandalone"),
    row.querySelector(".TUXRadio"),
    label,
    row.querySelector(".product-info-cell"),
    row,
  ].filter(Boolean);

  row.scrollIntoView({ block: "center", inline: "center" });
  await sleep(1200);

  radio.scrollIntoView({ block: "center", inline: "center" });
  radio.focus();
  radio.click();
  setNativeChecked(radio, true);
  radio.dispatchEvent(new Event("input", { bubbles: true }));
  radio.dispatchEvent(new Event("change", { bubbles: true }));
  await sleep(1000);

  for (const target of targets) {
    clickElementLikeUser(target);
    await sleep(800);
    setNativeChecked(radio, true);
    radio.dispatchEvent(new Event("input", { bubbles: true }));
    radio.dispatchEvent(new Event("change", { bubbles: true }));
    radio.focus();
    radio.dispatchEvent(new KeyboardEvent("keydown", { key: " ", code: "Space", bubbles: true, cancelable: true }));
    radio.dispatchEvent(new KeyboardEvent("keyup", { key: " ", code: "Space", bubbles: true, cancelable: true }));
    await sleep(800);
    const nextBtn = findButtonInModal("Tiếp");
    if (radio.checked || nextBtn) break;
  }

  const nextBtn = await waitForElement(() => {
    const btn = findPrimaryButtonIn(modal, ["Next", "Tiếp"]);
    return btn && !isDisabledButton(btn) ? btn : null;
  }, 15000);
  if (!nextBtn) throw new Error("Đã chọn sản phẩm đầu tiên nhưng nút Tiếp chưa bật");
  log("Selected first product.");
}

async function clickProductSelectorNext() {
  const modal = document.querySelector(".TUXModal.product-selector-modal") || findModalByTitles(["Thêm liên kết sản phẩm", "Add product"]);
  const nextBtn = await waitPrimaryButtonEnabled(() => modal, ["Next", "Tiếp"], 30000);
  nextBtn.click();
  log("Clicked product selector Next/Tiếp.");
}

async function clickAddProductLinks() {
  const modal = await waitForElement(() => findModalByTitles(["Add product links", "Thêm liên kết sản phẩm", "Thêm liên kết"]), 30000);
  if (!modal) throw new Error("Không tìm thấy modal Add product links");
  const addBtn = await waitPrimaryButtonEnabled(() => modal, ["Add", "Thêm"], 30000);
  addBtn.click();
  log("Clicked Add/Thêm in product links modal.");
}

async function fillProductDisplayName(captionText, timeoutMs = 30000) {
  log("Waiting for product name modal...");
  const input = await waitForElement(() => {
    const modals = Array.from(document.querySelectorAll(".TUXModal, [role='dialog']")).filter(isVisible);
    for (const modal of modals) {
      const labelHit = Array.from(modal.querySelectorAll("label, .TUXFormField-label")).some((el) => (el.textContent || "").includes("Tên sản phẩm"));
      const inputEl = modal.querySelector("input.TUXTextInputCore-input, input[type='text']");
      if (labelHit && inputEl && isVisible(inputEl)) return inputEl;
    }
    return null;
  }, timeoutMs);
  if (!input) throw new Error("Không thấy ô Tên sản phẩm");
  setInputValue(input, (captionText || "").slice(0, 30));
  log("Filled product display name.");
}

async function fillProductNameThenAdd(captionText) {
  const modal = await waitForElement(() => {
    const modals = Array.from(document.querySelectorAll(".TUXModal, [role='dialog']")).filter(isVisible);
    return modals.find((m) => {
      const hasNameLabel = Array.from(m.querySelectorAll("label, .TUXFormField-label")).some((el) => (el.textContent || "").includes("Tên sản phẩm"));
      const hasInput = Boolean(m.querySelector("input.TUXTextInputCore-input, input[type='text']"));
      return hasNameLabel && hasInput;
    }) || null;
  }, 30000);
  if (!modal) throw new Error("Không thấy modal nhập Tên sản phẩm");

  const input = modal.querySelector("input.TUXTextInputCore-input, input[type='text']");
  if (!input) throw new Error("Không thấy ô Tên sản phẩm");
  setInputValue(input, (captionText || "").slice(0, 30));
  log("Filled product name with caption.");
  await sleep(1200);

  const addBtn = await waitPrimaryButtonEnabled(() => modal, ["Add", "Thêm"], 30000);
  addBtn.click();
  log("Clicked Add/Thêm after filling product name.");
}

async function turnOffContentChecks() {
  log("Checking content/copyright switches...");
  const labels = ["Kiểm tra bản quyền nhạc", "Kiểm tra nội dung nhanh"];
  for (const label of labels) {
    const textNode = Array.from(document.querySelectorAll("span, div")).find((el) => isVisible(el) && (el.textContent || "").trim() === label);
    const container = textNode ? (textNode.closest(".switch-wrap") || textNode.closest(".headline-wrapper") || textNode.parentElement) : null;
    const switchEl = container ? container.querySelector(".Switch__content[aria-checked='true'], [role='switch'][aria-checked='true']") : null;
    if (isClickable(switchEl)) {
      switchEl.scrollIntoView({ block: "center", inline: "center" });
      await sleep(700);
      switchEl.click();
      log(`Turned off: ${label}`);
      await sleep(1200);
    }
  }
}

async function waitForProductLinkAttached(timeoutMs = 90000) {
  log("Waiting for product link to attach...");
  const start = Date.now();
  let modalGoneAt = 0;
  while (Date.now() - start < timeoutMs) {
    const stillHasAddProductButton = isClickable(findButtonByText("Thêm")) || isClickable(findButtonByText("Add"));
    const attachedMarker = findVisibleByText([
      "đã thêm",
      "đã liên kết",
      "xóa",
      "remove",
      "edit",
      "chỉnh sửa",
    ]);

    if (!stillHasAddProductButton || attachedMarker) {
      if (!modalGoneAt) modalGoneAt = Date.now();
      if (Date.now() - modalGoneAt >= 2500) {
        log("Product link looks attached.");
        return true;
      }
    } else {
      modalGoneAt = 0;
    }
    await sleep(500);
  }
  return false;
}

function beginRequest(requestId) {
  if (!requestId) return true;
  if (processedRequestIds.has(requestId) || activeRequestIds.has(requestId)) {
    log("Message ignored: request already running/processed.");
    return false;
  }
  activeRequestIds.add(requestId);
  return true;
}

function finishRequest(requestId) {
  if (!requestId) return;
  activeRequestIds.delete(requestId);
  processedRequestIds.add(requestId);
}

function setInputValue(input, value) {
  input.focus();
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function setEditableValue(el, value) {
  el.focus();
  if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(el);
  selection.removeAllRanges();
  selection.addRange(range);
  document.execCommand("delete", false, null);
  document.execCommand("insertText", false, value);
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function reportPostDone(requestId, ok, error = "") {
  try {
    chrome.runtime.sendMessage({ type: "post_done", requestId, ok, error });
  } catch {
    // ignore
  }
}

function getPendingUrlPayload() {
  const raw = sessionStorage.getItem(PENDING_URL_KEY) || "";
  if (!raw) return { url: "", requestId: "" };
  try {
    const obj = JSON.parse(raw);
    if (obj && typeof obj === "object") {
      return { url: (obj.url || ""), requestId: (obj.requestId || "") };
    }
  } catch {
    // Backward compat: raw URL string
  }
  return { url: raw, requestId: "" };
}

function setPendingUrlPayload(url, requestId) {
  sessionStorage.setItem(PENDING_URL_KEY, JSON.stringify({ url, requestId: requestId || "" }));
}

function clearPendingUrl() {
  sessionStorage.removeItem(PENDING_URL_KEY);
}

function maybeRunPending() {
  const pending = getPendingUrlPayload();
  if (!pending.url) {
    return;
  }
  if (!location.href.startsWith(TARGET_URL)) {
    return;
  }
  if (isFilling) {
    return;
  }
  log("Running pending URL.");
  runFillSequence(pending.url, pending.requestId);
}

function watchForUrlInput() {
  if (!location.href.startsWith(TARGET_URL)) {
    return;
  }
  const observer = new MutationObserver(() => {
    const pending = getPendingUrlPayload();
    if (findUrlInput() && pending.url && !isFilling) {
      log("URL input appeared. Running pending URL.");
      runFillSequence(pending.url, pending.requestId);
      observer.disconnect();
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  setTimeout(() => observer.disconnect(), 30000);
}

async function runFillSequence(productUrl, requestId = "") {
  if (isFilling) {
    log("Fill already in progress. Skipping.");
    return;
  }
  if (!beginRequest(requestId)) {
    return;
  }

  isFilling = true;
  try {
    log("Starting fill sequence.");

    await clickIfExists(() => findButtonByText("Thêm sản phẩm mới"));
    await sleep(STEP_DELAY_MS);

    log("Waiting for URL input (up to 20s)...");
    const input = await waitForElement(findUrlInput, 20000);
    if (!input) {
      log("URL input not found.");
      chrome.runtime.sendMessage({ type: "link_done", requestId, receiver: receiverId, url: productUrl, ok: false });
      return;
    }

    setInputValue(input, productUrl);
    await sleep(STEP_DELAY_MS);

    await clickIfExists(() => findButtonByText("URL sản phẩm"));
    await sleep(1200);

    const addBtn = await waitForElement(findAddProductButton, 20000);
    if (isClickable(addBtn)) {
      addBtn.scrollIntoView({ block: "center", inline: "center" });
      await sleep(150);
      addBtn.click();
      log("Clicked add product.");
    } else {
      log("Add product button not found.");
    }

    // Wait for success toast before closing drawer.
    log("Waiting for success message...");
    const toast = await waitForElement(findSuccessToast, 20000);
    const ok = Boolean(toast);
    if (ok) {
      log("Success: added 1 product.");
    } else {
      log("No success message found (timeout).");
    }

    await sleep(800);
    const closeBtn = findCloseDrawerButton();
    if (isClickable(closeBtn)) {
      closeBtn.click();
      log("Closed drawer.");
    } else {
      log("Close drawer button not found.");
    }
    clearPendingUrl();
    if (requestId && ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "link_done", requestId, receiver: receiverId, url: productUrl, ok }));
      } catch {
        // ignore
      }
    }
    if (requestId) {
      try {
        chrome.runtime.sendMessage({ type: "link_done", requestId, receiver: receiverId, url: productUrl, ok });
      } catch {
        // ignore
      }
    }

    // Stay on the page and wait for the next command.
  } finally {
    isFilling = false;
    finishRequest(requestId);
  }
}

async function runUploadPostSequence(captionText, requestId = "", attachProductLink = true) {
  if (!beginRequest(requestId)) {
    return;
  }
  try {
    log("Starting upload/post sequence.");

    await sleep(2500);
    const captionBox = await waitForElement(() => (
      document.querySelector("textarea") ||
      document.querySelector("div[contenteditable='true']") ||
      document.querySelector("[role='textbox']")
    ), 60000);
    if (!captionBox) throw new Error("Không thấy ô caption");
    setEditableValue(captionBox, captionText || "");
    log("Filled caption.");

    if (attachProductLink) {
      await sleep(2500);
      await waitAndClickAddLinkEntry(90000);
      await sleep(1800);
      await waitAndClickButtonByTexts(["Sản phẩm", "Product"], 60000);
      await sleep(1800);

      await clickInitialNextIfNeeded();
      await sleep(1800);

      await selectFirstProductInModal(30000);
      await sleep(1200);

      await clickProductSelectorNext();
      await sleep(1800);

      await fillProductNameThenAdd(captionText);
      await sleep(2500);

      const attached = await waitForProductLinkAttached(90000);
      if (!attached) throw new Error("Gắn giỏ hàng chưa xong nên không bấm Đăng");
    } else {
      log("Skip product link attach.");
    }

    log("Waiting 10s before content checks...");
    await sleep(10000);

    await turnOffContentChecks();
    log("Waiting 2s after content checks...");
    await sleep(2000);

    const postBtn = await waitForElement(() => {
      const direct = document.querySelector('button[data-e2e="post_video_button"]');
      if (isClickable(direct)) return direct;
      const btn = findButtonByText("Đăng") || findButtonByText("Post") || findButtonByText("Publish");
      if (isClickable(btn)) return btn;
      return null;
    }, 12 * 60 * 1000);
    if (!postBtn) throw new Error("Không thấy nút Đăng khả dụng");

    try { window.scrollTo(0, document.body.scrollHeight); } catch {}
    await sleep(500);
    postBtn.click();
    await sleep(5000);
    reportPostDone(requestId, true);
  } catch (error) {
    reportPostDone(requestId, false, error && error.message ? error.message : String(error));
  } finally {
    finishRequest(requestId);
  }
}

function parseMessage(message) {
  try {
    const data = JSON.parse(message);
    if (data && typeof data === "object") {
      const type = data.type || "fill_product";
      if (type !== "fill_product") {
        return { type, url: "", target: "", requestId: "" };
      }
      return {
        type,
        url: data.url || data.product_url || "",
        target: data.target || data.receiver_id || "",
        requestId: data.requestId || data.request_id || "",
      };
    }
  } catch {
    // Not JSON
  }

  if (typeof message === "string" && message.startsWith("http")) {
    return { type: "fill_product", url: message.trim(), target: "" };
  }
  return { type: "", url: "", target: "", requestId: "" };
}

function connect(wsUrl) {
  if (connecting || (ws && ws.readyState === WebSocket.OPEN)) {
    return;
  }

  connecting = true;
  log("Connecting to " + wsUrl + " ...");
  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    log("WebSocket init failed: " + err.message);
    connecting = false;
    return;
  }

  ws.addEventListener("open", () => {
    connecting = false;
    log("Connected: " + wsUrl);
    startReceiverIdWatch();
    sendHello();
  });

  ws.addEventListener("message", (event) => {
    const payload = parseMessage(event.data);
    if (!payload.url) {
      log("Message ignored.");
      return;
    }
    // If a target is specified, we must have a receiverId and it must match.
    if (payload.target && !receiverId) {
      log("Message ignored: receiver not set.");
      return;
    }
    if (receiverId && payload.target && payload.target !== receiverId) {
      log("Message ignored: receiver mismatch.");
      return;
    }

    if (payload.requestId) {
      if (processedRequestIds.has(payload.requestId) || activeRequestIds.has(payload.requestId)) {
        log("Message ignored: request already processed.");
        return;
      }
    }
    if (!location.href.startsWith(TARGET_URL)) {
      log("Navigating to target page...");
      if (payload.requestId) {
        activeRequestIds.add(payload.requestId);
      }
      setPendingUrlPayload(payload.url, payload.requestId);
      location.href = TARGET_URL;
      return;
    }
    runFillSequence(payload.url, payload.requestId);
  });

  ws.addEventListener("close", () => {
    connecting = false;
    log("Disconnected. Retrying...");
    setTimeout(() => connect(wsUrl), CONNECT_RETRY_MS);
  });

  ws.addEventListener("error", () => {
    log("WebSocket error. Retrying...");
    try {
      ws.close();
    } catch {
      // ignore
    }
  });
}

ensureReceiverId(() => sendHello());
wakeBackground();

const pending = getPendingUrlPayload();
if (pending.url && location.href.startsWith(TARGET_URL)) {
  log("Found pending URL after navigation.");
  runFillSequence(pending.url, pending.requestId);
}

setInterval(maybeRunPending, 1000);
setInterval(wakeBackground, 5000);
watchForUrlInput();

chrome.storage.onChanged.addListener((changes) => {
  if (changes.receiverId) {
    receiverId = (changes.receiverId.newValue || "").trim();
    sendHello();
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (!message) {
    return;
  }
  if (message.type === "fill_product" && message.url) {
    runFillSequence(message.url, message.requestId || "");
  }
  if (message.type === "upload_post") {
    runUploadPostSequence(message.caption || "", message.requestId || "", message.attachProductLink !== false);
  }
});

globalThis.__editVideoProRunUploadPost = runUploadPostSequence;
globalThis.__editVideoProRunFill = runFillSequence;
})();
