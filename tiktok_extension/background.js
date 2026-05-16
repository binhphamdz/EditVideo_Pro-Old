const APP_ID = "editvideo_pro_tiktok_agent_v1";
const DEFAULT_WS_PORTS = Array.from({ length: 21 }, (_, index) => 8765 + index);
const SHOWCASE_URL = "https://shop.tiktok.com/streamer/showcase/product/list";
const UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload";
const RETRY_MS = 3000;

let ws = null;
let connecting = false;
let receiverId = "";
let portIndex = 0;
let candidateUrls = [];
const activeServerRequests = new Set();

function wakeAndConnect() {
  ensureReceiverId(() => {
    sendHello();
    if (ws && ws.readyState !== WebSocket.OPEN && ws.readyState !== WebSocket.CONNECTING) {
      try { ws.close(); } catch {}
      ws = null;
    }
    connect();
  });
}

function buildCandidateUrls(savedUrl) {
  const urls = [];
  if (savedUrl) urls.push(savedUrl);
  for (const port of DEFAULT_WS_PORTS) urls.push(`ws://127.0.0.1:${port}`);
  return Array.from(new Set(urls));
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

function sendHello() {
  if (ws && ws.readyState === WebSocket.OPEN && receiverId) {
    ws.send(JSON.stringify({ type: "hello", appId: APP_ID, receiver: receiverId, extensionId: chrome.runtime.id }));
  }
}

function sendWs(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ appId: APP_ID, receiver: receiverId, ...payload }));
  }
}

function connect() {
  if (connecting || (ws && ws.readyState === WebSocket.OPEN)) return;
  connecting = true;
  chrome.storage.local.get(["wsUrl"], (result) => {
    candidateUrls = buildCandidateUrls((result.wsUrl || "").trim());
    const wsUrl = candidateUrls[portIndex % candidateUrls.length];
    console.log("[EditVideo Pro Agent] connecting", wsUrl);
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      connecting = false;
      portIndex += 1;
      setTimeout(connect, RETRY_MS);
      return;
    }

    ws.addEventListener("open", () => {
      connecting = false;
      console.log("[EditVideo Pro Agent] connected", wsUrl, receiverId);
      sendHello();
    });
    ws.addEventListener("message", (event) => handleServerMessage(event.data));
    ws.addEventListener("close", () => {
      connecting = false;
      portIndex += 1;
      setTimeout(connect, RETRY_MS);
    });
    ws.addEventListener("error", () => {
      try { ws.close(); } catch {}
    });
  });
}

function parsePayload(raw) {
  try {
    const data = JSON.parse(raw);
    return {
      type: data.type || "fill_product",
      appId: data.appId || data.app_id || "",
      url: data.url || data.product_url || "",
      videoPath: data.videoPath || data.video_path || "",
      caption: data.caption || "",
      attachProductLink: data.attachProductLink !== false && data.attach_product_link !== false,
      requestId: data.requestId || data.request_id || "",
      target: data.target || data.receiver_id || "",
    };
  } catch {
    return { type: "", appId: "", url: "", videoPath: "", caption: "", attachProductLink: true, requestId: "", target: "" };
  }
}

function handleServerMessage(raw) {
  const payload = parsePayload(raw);
  if (payload.appId && payload.appId !== APP_ID) return;
  if (payload.target && payload.target !== receiverId) return;
  if (!payload.requestId) return;
  if (activeServerRequests.has(payload.requestId)) return;

  if (payload.type === "open_upload") {
    activeServerRequests.add(payload.requestId);
    openUploadAndReport(payload);
    return;
  }
  if (payload.type === "full_post") {
    activeServerRequests.add(payload.requestId);
    openUploadSetFileAndPost(payload);
    return;
  }
  if (payload.url) openShowcaseAndSend(payload);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function chromeCall(fn, ...args) {
  return new Promise((resolve, reject) => {
    fn(...args, (result) => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(err.message));
      else resolve(result);
    });
  });
}

function getOrCreateUploadTab() {
  return new Promise((resolve, reject) => {
    chrome.tabs.query({ url: UPLOAD_URL + "*" }, (tabs) => {
      const tab = tabs && tabs.length ? tabs[0] : null;
      if (tab && tab.id) {
        chrome.tabs.update(tab.id, { active: true }, () => resolve(tab.id));
        return;
      }
      chrome.tabs.create({ url: UPLOAD_URL, active: true }, (createdTab) => {
        if (createdTab && createdTab.id) resolve(createdTab.id);
        else reject(new Error("Không tạo được tab upload"));
      });
    });
  });
}

async function waitForUploadTabReady(tabId) {
  for (let i = 0; i < 80; i += 1) {
    const tab = await chromeCall(chrome.tabs.get, tabId);
    if (tab && tab.url && tab.url.startsWith(UPLOAD_URL) && tab.status === "complete") return;
    await sleep(500);
  }
  throw new Error("Tab upload chưa load xong");
}

async function sendDebuggerCommand(target, method, params = {}) {
  return chromeCall(chrome.debugger.sendCommand, target, method, params);
}

async function setUploadFileByDebugger(tabId, videoPath) {
  if (!videoPath) throw new Error("Thiếu đường dẫn video");
  const target = { tabId };
  let attached = false;
  try {
    await chromeCall(chrome.debugger.attach, target, "1.3");
    attached = true;
    await sendDebuggerCommand(target, "DOM.enable");
    for (let i = 0; i < 80; i += 1) {
      const root = await sendDebuggerCommand(target, "DOM.getDocument", { depth: 1, pierce: true });
      const found = await sendDebuggerCommand(target, "DOM.querySelector", {
        nodeId: root.root.nodeId,
        selector: "input[type='file']",
      });
      if (found && found.nodeId) {
        await sendDebuggerCommand(target, "DOM.setFileInputFiles", { nodeId: found.nodeId, files: [videoPath] });
        return;
      }
      await sleep(500);
    }
    throw new Error("Không thấy input upload file");
  } finally {
    if (attached) {
      try { await chromeCall(chrome.debugger.detach, target); } catch {}
    }
  }
}

async function openUploadSetFileAndPost(payload) {
  try {
    const tabId = await getOrCreateUploadTab();
    await waitForUploadTabReady(tabId);
    await sleep(1500);
    await setUploadFileByDebugger(tabId, payload.videoPath);
    await sleep(2500);
    const started = await startUploadPostInContent(tabId, payload, 30);
    if (!started) {
      reportPostDone(payload.requestId, false, "Không khởi động được luồng đăng trong content script");
    }
  } catch (error) {
    reportPostDone(payload.requestId, false, error && error.message ? error.message : String(error));
  }
}

async function startUploadPostInContent(tabId, payload, triesLeft) {
  for (let i = 0; i < triesLeft; i += 1) {
    try {
      const tab = await chromeCall(chrome.tabs.get, tabId);
      if (!tab || !tab.url || !tab.url.startsWith(UPLOAD_URL)) {
        await sleep(500);
        continue;
      }

      const result = await chromeCall(chrome.scripting.executeScript, {
        target: { tabId },
        func: (caption, requestId, attachProductLink) => {
          if (typeof globalThis.__editVideoProRunUploadPost === "function") {
            globalThis.__editVideoProRunUploadPost(caption || "", requestId || "", attachProductLink !== false);
            return true;
          }
          return false;
        },
        args: [payload.caption || "", payload.requestId || "", payload.attachProductLink !== false],
      });
      if (result && result[0] && result[0].result) return true;

      await chromeCall(chrome.scripting.executeScript, { target: { tabId }, files: ["content.js"] });
      await sleep(700);
    } catch {
      await sleep(500);
    }
  }
  return false;
}

function openUploadAndReport(payload) {
  chrome.tabs.query({ url: UPLOAD_URL + "*" }, (tabs) => {
    const tab = tabs && tabs.length ? tabs[0] : null;
    if (tab && tab.id) {
      chrome.tabs.update(tab.id, { active: true }, () => reportOpenUploadDone(payload.requestId, true, ""));
      return;
    }
    chrome.tabs.create({ url: UPLOAD_URL, active: true }, (createdTab) => {
      if (createdTab && createdTab.id) {
        reportOpenUploadDone(payload.requestId, true, "");
      } else {
        reportOpenUploadDone(payload.requestId, false, "Không tạo được tab upload");
      }
    });
  });
}

function openShowcaseAndSend(payload) {
  chrome.tabs.query({ url: SHOWCASE_URL + "*" }, (tabs) => {
    const tab = tabs && tabs.length ? tabs[0] : null;
    if (tab && tab.id) {
      chrome.tabs.update(tab.id, { active: true }, () => sendToContent(tab.id, "fill_product", payload));
      return;
    }
    chrome.tabs.create({ url: SHOWCASE_URL, active: true }, (createdTab) => {
      if (createdTab && createdTab.id) waitAndSend(createdTab.id, "fill_product", payload, SHOWCASE_URL, 40);
    });
  });
}

function waitAndSend(tabId, type, payload, urlPrefix, triesLeft) {
  if (triesLeft <= 0) {
    reportLinkDone(payload.requestId, payload.url || "", false);
    return;
  }
  chrome.tabs.get(tabId, (tab) => {
    if (!tab || !tab.url || !tab.url.startsWith(urlPrefix)) {
      setTimeout(() => waitAndSend(tabId, type, payload, urlPrefix, triesLeft - 1), 500);
      return;
    }
    sendToContent(tabId, type, payload, () => {
      setTimeout(() => waitAndSend(tabId, type, payload, urlPrefix, triesLeft - 1), 500);
    });
  });
}

function buildContentMessage(type, payload) {
  return { type, url: payload.url, requestId: payload.requestId, caption: payload.caption, attachProductLink: payload.attachProductLink !== false };
}

function sendToContent(tabId, type, payload, onFail) {
  chrome.tabs.sendMessage(tabId, buildContentMessage(type, payload), () => {
    if (!chrome.runtime.lastError) return;
    chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] }, () => {
      if (chrome.runtime.lastError) {
        if (onFail) onFail();
        return;
      }
      chrome.tabs.sendMessage(tabId, buildContentMessage(type, payload), () => {
        if (chrome.runtime.lastError && onFail) onFail();
      });
    });
  });
}

function sendToContentWithRetry(tabId, type, payload, triesLeft, onFail) {
  if (triesLeft <= 0) {
    if (onFail) onFail();
    return;
  }

  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError || !tab || !tab.url || !tab.url.startsWith(UPLOAD_URL)) {
      setTimeout(() => sendToContentWithRetry(tabId, type, payload, triesLeft - 1, onFail), 500);
      return;
    }

    chrome.tabs.sendMessage(tabId, buildContentMessage(type, payload), () => {
      if (!chrome.runtime.lastError) return;

      chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] }, () => {
        if (chrome.runtime.lastError) {
          setTimeout(() => sendToContentWithRetry(tabId, type, payload, triesLeft - 1, onFail), 500);
          return;
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tabId, buildContentMessage(type, payload), () => {
            if (!chrome.runtime.lastError) return;
            setTimeout(() => sendToContentWithRetry(tabId, type, payload, triesLeft - 1, onFail), 500);
          });
        }, 300);
      });
    });
  });
}

function reportLinkDone(requestId, url, ok) {
  sendWs({ type: "link_done", requestId, url, ok });
}

function reportOpenUploadDone(requestId, ok, error) {
  activeServerRequests.delete(requestId);
  sendWs({ type: "open_upload_done", requestId, ok, error: error || "" });
}

function reportPostDone(requestId, ok, error) {
  activeServerRequests.delete(requestId);
  sendWs({ type: "post_done", requestId, ok, error: error || "" });
}

chrome.runtime.onMessage.addListener((message) => {
  if (!message) return;
  if (message.type === "wake") {
    wakeAndConnect();
    return;
  }
  if (message.type === "link_done") {
    reportLinkDone(message.requestId || "", message.url || "", Boolean(message.ok));
  }
  if (message.type === "post_done") {
    reportPostDone(message.requestId || "", Boolean(message.ok), message.error || "");
  }
});

ensureReceiverId(connect);
setInterval(sendHello, 5000);
setInterval(wakeAndConnect, 15000);

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("editvideo-pro-agent-keepalive", { periodInMinutes: 0.5 });
  wakeAndConnect();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("editvideo-pro-agent-keepalive", { periodInMinutes: 0.5 });
  wakeAndConnect();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "editvideo-pro-agent-keepalive") {
    wakeAndConnect();
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url && (tab.url.startsWith(SHOWCASE_URL) || tab.url.startsWith(UPLOAD_URL))) {
    wakeAndConnect();
  }
});

chrome.tabs.onActivated.addListener(() => wakeAndConnect());

chrome.alarms.create("editvideo-pro-agent-keepalive", { periodInMinutes: 0.5 });
wakeAndConnect();
