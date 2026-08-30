/**
 * GUSTAV - Medesync Background Service Worker (Manifest V3)
 * Direct 1-Click Launch Handler from Chrome Toolbar Icon
 */

const DEFAULT_GUSTAV_URL = "https://gustav.plucpel.net";
const DEFAULT_EXTENSION_SECRET = "gustav_ext_secret_chatterbox_2026";

/**
 * Handle direct 1-click on the Extension Icon in the Chrome Toolbar
 */
chrome.action.onClicked.addListener(async (tab) => {
  console.log("[GUSTAV Background] Toolbar icon clicked on tab:", tab ? tab.url : "unknown");

  let patientPayload = {
    medesync_id: "",
    patient_name: "",
    nom: "",
    prenom: "",
    ramq: "",
    dob: "",
    sex: "",
    dossier: "",
    prescriber_name: ""
  };

  if (tab && tab.id) {
    try {
      // 1. Execute DOM / frame inspection script on the active tab
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: () => {
          let id = "";

          // A. From URL params
          try {
            const params = new URLSearchParams(window.location.search);
            id = params.get("id") || params.get("idPatient") || params.get("IdPatient") || "";
          } catch (e) {}

          // B. From ASP.NET forms
          if (!id) {
            try {
              const aspnetForm = document.getElementById("aspnetForm") || document.forms["aspnetForm"];
              if (aspnetForm && aspnetForm.action) {
                const m = aspnetForm.action.match(/[?&]id=(\d+)/i);
                if (m) id = m[1];
              }
            } catch (e) {}
          }

          // C. From scripts / InitSetting
          if (!id) {
            try {
              const scripts = document.querySelectorAll("script");
              for (const s of scripts) {
                const text = s.textContent || "";
                if (text.includes("idPatient")) {
                  const m = text.match(/"idPatient"\s*:\s*(\d+)/i) || text.match(/idPatient\s*=\s*(\d+)/i);
                  if (m && m[1] && m[1] !== "0") { id = m[1]; break; }
                }
              }
            } catch (e) {}
          }

          // D. Direct DOM inspection (RAMQ, Dossier, Prescriber)
          let ramq = "";
          let dossier = "";
          let prescriber = "";

          try {
            const ramqEl = document.getElementById("Ramq") || document.querySelector(".patient-ramq");
            if (ramqEl) ramq = ramqEl.innerText.trim();
          } catch (e) {}

          try {
            if (window.__logon_user_code) {
              prescriber = String(window.__logon_user_code).replace(/-/g, " ");
            }
          } catch (e) {}

          return {
            medesync_id: id || "",
            ramq: ramq,
            dossier: dossier,
            prescriber_name: prescriber,
            hostname: window.location.hostname
          };
        }
      });

      if (injectionResults && injectionResults.length > 0) {
        for (const res of injectionResults) {
          if (res.result && res.result.medesync_id) {
            Object.assign(patientPayload, res.result);
            break;
          }
        }
        if (!patientPayload.medesync_id && injectionResults[0].result) {
          Object.assign(patientPayload, injectionResults[0].result);
        }
      }

      // 2. If patient ID is found, query Medesync basicInfos endpoint within page session
      if (patientPayload.medesync_id && /^\d+$/.test(patientPayload.medesync_id)) {
        const [apiRes] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: async (patientId) => {
            try {
              const r = await fetch(`/api/v3/patients/getBasicInfos/${patientId}`);
              if (r.ok) return await r.json();
            } catch (e) {}
            return null;
          },
          args: [patientPayload.medesync_id]
        });

        if (apiRes && apiRes.result) {
          const b = apiRes.result;
          patientPayload.patient_name = b.fullName || `${b.firstName || ''} ${b.lastName || ''}`.trim();
          patientPayload.nom = b.lastName || "";
          patientPayload.prenom = b.firstName || "";
          patientPayload.ramq = b.nam || patientPayload.ramq || "";
          patientPayload.dob = b.dobRaw || "";
          patientPayload.sex = b.sexeShort || (b.isMale ? "M" : "F");
          patientPayload.dossier = b.chartNumber || patientPayload.dossier || "";
        }
      }

    } catch (err) {
      console.warn("[GUSTAV Background] Scripting tab failed, launching directly:", err);
    }
  }

  // 3. Negotiate single-use launch token with Gustav server and open tab
  try {
    await handleLaunchGustav(patientPayload);
  } catch (err) {
    console.error("[GUSTAV Background] Direct launch error:", err);
  }
});

/**
 * Message listener fallback for programmatic triggers
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "LAUNCH_GUSTAV") {
    handleLaunchGustav(message.patient)
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
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

  console.log("[GUSTAV Background] Negotiating launch with:", `${gustavUrl}/api/context/launch`, patientPayload);

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
      throw new Error("Aucun jeton de lancement retourné.");
    }

    const launchUrl = `${gustavUrl}/?launch=${encodeURIComponent(data.launch_token)}`;
    console.log("[GUSTAV Background] Opening authenticated Gustav tab:", launchUrl);

    await chrome.tabs.create({ url: launchUrl });

    return { success: true, launch_token: data.launch_token };
  } catch (err) {
    console.error("[GUSTAV Background] Launch failed:", err);
    throw err;
  }
}
