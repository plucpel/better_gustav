/**
 * GUSTAV - Medesync Background Service Worker (Manifest V3)
 * Handles secure token negotiation with Gustav server and tab opening.
 */

const DEFAULT_GUSTAV_URL = "http://chatterbox:8000";
const DEFAULT_EXTENSION_SECRET = "gustav_ext_secret_chatterbox_2026";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "LAUNCH_GUSTAV") {
    handleLaunchGustav(message.patient)
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // Keep message channel open for async response
  }
});

async function getStoredSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(["gustavUrl", "extensionSecret"], (items) => {
      resolve({
        gustavUrl: (items.gustavUrl || DEFAULT_GUSTAV_URL).replace(/\/+$/, ""),
        extensionSecret: items.extensionSecret || DEFAULT_EXTENSION_SECRET
      });
    });
  });
}

async function handleLaunchGustav(patientPayload) {
  const { gustavUrl, extensionSecret } = await getStoredSettings();

  console.log("[GUSTAV Background] Launching Gustav with endpoint:", `${gustavUrl}/api/context/launch`);

  try {
    const resp = await fetch(`${gustavUrl}/api/context/launch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Gustav-Secret": extensionSecret
      },
      body: JSON.stringify(patientPayload || {})
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Serveur GUSTAV (${resp.status}): ${errText}`);
    }

    const data = await resp.json();
    if (!data.launch_token) {
      throw new Error("Aucun jeton de lancement retourné par GUSTAV.");
    }

    const launchUrl = `${gustavUrl}/?launch=${encodeURIComponent(data.launch_token)}`;
    console.log("[GUSTAV Background] Opening secure tab:", launchUrl);

    chrome.tabs.create({ url: launchUrl });

    return { success: true, launch_token: data.launch_token };
  } catch (err) {
    console.error("[GUSTAV Background] Launch failed:", err);
    throw err;
  }
}
