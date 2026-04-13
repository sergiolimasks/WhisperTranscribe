const API_BASE = "http://localhost:50061";

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const urlDisplay = document.getElementById("url-display");
const sendBtn = document.getElementById("send-btn");
const feedback = document.getElementById("feedback");

let detectedUrl = null;
let appOnline = false;

// Check app status
async function checkStatus() {
  try {
    const resp = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(2000) });
    const data = await resp.json();
    appOnline = true;
    statusDot.classList.add("online");
    statusText.textContent = "App conectado";
    updateButton();
  } catch {
    appOnline = false;
    statusDot.classList.remove("online");
    statusText.textContent = "App offline — abra o WhisperTranscribe";
    updateButton();
  }
}

// Detect video URL on current tab
function detectUrl() {
  chrome.runtime.sendMessage({ type: "get-video-url" }, (response) => {
    if (response && response.url) {
      detectedUrl = response.url;
      const display = detectedUrl.length > 80
        ? detectedUrl.substring(0, 77) + "..."
        : detectedUrl;
      urlDisplay.textContent = display;
      updateButton();
    } else {
      urlDisplay.textContent = "Nenhuma URL detectada";
    }
  });
}

function updateButton() {
  sendBtn.disabled = !appOnline || !detectedUrl;
}

// Send URL to app
sendBtn.addEventListener("click", async () => {
  if (!detectedUrl || !appOnline) return;

  sendBtn.disabled = true;
  sendBtn.textContent = "Enviando...";
  feedback.textContent = "";
  feedback.className = "feedback";

  try {
    const resp = await fetch(`${API_BASE}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: detectedUrl }),
    });
    const data = await resp.json();

    if (data.ok) {
      feedback.textContent = "\u2713 Enviado para transcrição!";
      sendBtn.textContent = "✓ Enviado";
    } else {
      feedback.textContent = data.error || "Erro desconhecido";
      feedback.className = "feedback error";
      sendBtn.textContent = "Transcrever";
      sendBtn.disabled = false;
    }
  } catch {
    feedback.textContent = "Não foi possível conectar ao app";
    feedback.className = "feedback error";
    sendBtn.textContent = "Transcrever";
    sendBtn.disabled = false;
  }
});

// Init
checkStatus();
detectUrl();
