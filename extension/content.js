// Detect video URLs on the current page
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== "detect-video") return;

  const url = window.location.href;

  // YouTube
  if (url.includes("youtube.com/watch") || url.includes("youtu.be/")) {
    sendResponse({ url, source: "youtube" });
    return;
  }

  // Vimeo
  if (url.includes("vimeo.com/")) {
    sendResponse({ url, source: "vimeo" });
    return;
  }

  // Try to find a <video> or <source> element
  const video = document.querySelector("video");
  if (video) {
    const src = video.src || video.querySelector("source")?.src;
    if (src && src.startsWith("http")) {
      sendResponse({ url: src, source: "video-element" });
      return;
    }
  }

  // Fallback: page URL (yt-dlp supports many sites)
  sendResponse({ url, source: "page" });
});
