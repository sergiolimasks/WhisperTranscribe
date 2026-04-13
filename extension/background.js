const API_BASE = "http://localhost:50061";

// Context menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "whisper-transcribe",
    title: "Transcrever com WhisperTranscribe",
    contexts: ["page", "video", "audio", "link"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "whisper-transcribe") return;

  // Use link URL if right-clicked on a link, otherwise use page URL
  const url = info.linkUrl || info.pageUrl || tab.url;

  try {
    const resp = await fetch(`${API_BASE}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();

    if (data.ok) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "WhisperTranscribe",
        message: "Enviado para transcrição!",
      });
    } else {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "WhisperTranscribe — Erro",
        message: data.error || "Erro desconhecido",
      });
    }
  } catch (e) {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "WhisperTranscribe",
      message: "App não está aberto. Abra o WhisperTranscribe primeiro.",
    });
  }
});

// Handle messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "get-video-url") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "detect-video" }, (response) => {
          sendResponse(response || { url: tabs[0].url });
        });
      }
    });
    return true; // async response
  }
});
