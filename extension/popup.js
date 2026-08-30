/**
 * GUSTAV - Extension Settings & Direct Launcher Popup Logic
 */

const DEFAULT_GUSTAV_URL = "https://gustav.plucpel.net";
const DEFAULT_EXTENSION_SECRET = "gustav_ext_secret_chatterbox_2026";

document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("gustavUrl");
  const secretInput = document.getElementById("extensionSecret");
  const saveBtn = document.getElementById("saveBtn");
  const testBtn = document.getElementById("testBtn");
  const launchBtn = document.getElementById("launchBtn");
  const statusMsg = document.getElementById("statusMsg");

  // Load stored settings
  chrome.storage.sync.get(["gustavUrl", "extensionSecret"], (items) => {
    urlInput.value = items.gustavUrl || DEFAULT_GUSTAV_URL;
    secretInput.value = items.extensionSecret || DEFAULT_EXTENSION_SECRET;
  });

  // Direct Launch Button
  if (launchBtn) {
    launchBtn.addEventListener("click", async () => {
      launchBtn.innerHTML = `<span>⏳</span><span>Lancement...</span>`;
      launchBtn.disabled = true;

      try {
        // Query active tab to extract patient if on Medesync
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        let patientPayload = {
          patient_name: "",
          nom: "",
          prenom: "",
          ramq: "",
          dob: "",
          sex: "",
          dossier: ""
        };

        if (tab && tab.id) {
          try {
            // Attempt to read patient info from active page
            const results = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const params = new URLSearchParams(window.location.search);
                const id = params.get("id") || params.get("idPatient") || params.get("IdPatient");
                let name = "";
                let ramq = "";
                const ramqEl = document.getElementById("Ramq") || document.querySelector(".patient-ramq");
                if (ramqEl) ramq = ramqEl.innerText.trim();
                return { medesync_id: id || "", ramq: ramq };
              }
            });
            if (results && results[0] && results[0].result) {
              Object.assign(patientPayload, results[0].result);
            }
          } catch (e) {
            console.debug("Could not script active tab:", e);
          }
        }

        chrome.runtime.sendMessage({
          action: "LAUNCH_GUSTAV",
          patient: patientPayload
        }, (response) => {
          if (chrome.runtime.lastError) {
            showStatus("Erreur : " + chrome.runtime.lastError.message, "error");
          } else if (response && !response.success) {
            showStatus("Erreur : " + (response.error || "Inconnue"), "error");
          } else {
            showStatus("✓ GUSTAV lancé avec succès !", "success");
            setTimeout(() => window.close(), 600);
          }
        });

      } catch (err) {
        showStatus("Erreur : " + err.message, "error");
      } finally {
        setTimeout(() => {
          launchBtn.innerHTML = `<span>🧪</span><span>Ouvrir GUSTAV (Onglet Actif)</span>`;
          launchBtn.disabled = false;
        }, 1000);
      }
    });
  }

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
