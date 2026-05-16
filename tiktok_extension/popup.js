const wsInput = document.getElementById("wsUrl");
const receiverInput = document.getElementById("receiverId");
const status = document.getElementById("status");
const saveBtn = document.getElementById("save");

function showStatus(text) {
  status.textContent = text;
}

chrome.storage.local.get(["wsUrl", "receiverId"], (result) => {
  wsInput.value = result.wsUrl || "";
  wsInput.placeholder = "Tự dò ws://127.0.0.1:8765-8785";
  receiverInput.value = result.receiverId || "";
});

saveBtn.addEventListener("click", () => {
  const value = wsInput.value.trim();
  if (!value) {
    const receiverId = receiverInput.value.trim();
    chrome.storage.local.remove(["wsUrl"], () => {
      chrome.storage.local.set({ receiverId }, () => showStatus("Saved auto port mode."));
    });
    return;
  }
  if (!value.startsWith("ws://") && !value.startsWith("wss://")) {
    showStatus("Invalid WebSocket URL.");
    return;
  }
  const receiverId = receiverInput.value.trim();
  chrome.storage.local.set({ wsUrl: value, receiverId }, () => {
    showStatus("Saved.");
  });
});
