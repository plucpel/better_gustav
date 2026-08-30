/**
 * GUSTAV - Extension Settings Popup Logic
 */

const DEFAULT_GUSTAV_URL = "https://gustav.plucpel.net";
const DEFAULT_EXTENSION_SECRET = "gustav_ext_secret_chatterbox_2026";

document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("gustavUrl");
  const secretInput = document.getElementById("extensionSecret");
  const saveBtn = document.getElementById("saveBtn");
  const testBtn = document.getElementById("testBtn");
  const statusMsg = document.getElementById("statusMsg");

  // Load stored settings
  chrome.storage.sync.get(["gustavUrl", "extensionSecret"], (items) => {
    urlInput.value = items.gustavUrl || DEFAULT_GUSTAV_URL;
    secretInput.value = items.extensionSecret || DEFAULT_EXTENSION_SECRET;
  });

  // Save settings
  saveBtn.addEventListener("click", () => {
    const gustavUrl = urlInput.value.trim().replace(/\/+$/, "");
    const extensionSecret = secretInput.value.trim();

    chrome.storage.sync.set({ gustavUrl, extensionSecret }, () => {
      showStatus("Réglages enregistrés avec succès !", "success");
    });
  });

  // Test connection
  testBtn.addEventListener("click", async () => {
    const gustavUrl = urlInput.value.trim().replace(/\/+$/, "");
    const extensionSecret = secretInput.value.trim();

    showStatus("Test de connexion en cours...", "success");

    try {
      const resp = await fetch(`${gustavUrl}/api/context/launch`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Gustav-Secret": extensionSecret
        },
        body: JSON.stringify({ patient_name: "Test Connection" })
      });

      if (resp.ok) {
        showStatus("✓ Connexion à GUSTAV réussie !", "success");
      } else {
        const errText = await resp.text();
        showStatus(`Erreur (${resp.status}): ${errText}`, "error");
      }
    } catch (err) {
      showStatus(`Échec de connexion : ${err.message}`, "error");
    }
  });

  function showStatus(text, type) {
    statusMsg.innerText = text;
    statusMsg.className = `status ${type}`;
    statusMsg.style.display = "block";
  }
});
