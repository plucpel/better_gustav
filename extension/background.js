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
      // 1. Execute deep DOM & API inspection across all frames on the active Medesync tab
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: async () => {
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

          // D. Query Medesync API with multi-host fallback
          let apiData = null;
          if (id && /^\d+$/.test(id)) {
            const currentHost = window.location.hostname;
            const hostsToTry = [
              `https://${currentHost.replace('.medesync.com', '-api.medesync.com')}`,
              `https://${currentHost}`,
              'https://secure2-api.medesync.com',
              'https://secure-api.medesync.com'
            ];

            for (const h of hostsToTry) {
              try {
                const resp = await fetch(`${h}/api/v3/patients/getBasicInfos/${id}`, {
                  credentials: 'include',
                  headers: { 'Accept': 'application/json' }
                });
                if (resp.ok) {
                  const data = await resp.json();
                  if (data && (data.nam || data.fullName || data.lastName || data.firstName)) {
                    apiData = data;
                    break;
                  }
                }
              } catch (err) {}
            }
          }

          // E. Deep DOM Regex Extraction (Fallback if API is unavailable)
          const bodyText = (document.body ? document.body.innerText : "") + " " + document.title;
          
          // RAMQ Regex (e.g. ABCD 1234 5678 or ABCD12345678)
          let extractedRamq = "";
          const ramqMatch = bodyText.match(/\b([A-Z]{4})\s*(\d{2})\s*(\d{2})\s*(\d{2})\s*(\d{2})\b/i) ||
                            bodyText.match(/\b([A-Z]{4})\s*(\d{4})\s*(\d{4})\b/i) ||
                            bodyText.match(/\b([A-Z]{4}\d{8})\b/i);
          if (ramqMatch) {
            extractedRamq = ramqMatch[0].replace(/\s+/g, "");
          }

          // Date of Birth Regex (YYYY-MM-DD or DD/MM/YYYY)
          let extractedDob = "";
          const dobMatch = bodyText.match(/\b(19\d{2}|20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b/) ||
                           bodyText.match(/\b(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/(19\d{2}|20\d{2})\b/);
          if (dobMatch) {
            if (dobMatch[0].includes("/")) {
              const parts = dobMatch[0].split("/");
              extractedDob = `${parts[2]}-${parts[1]}-${parts[0]}`;
            } else {
              extractedDob = dobMatch[0];
            }
          }

          // Prescriber
          let prescriber = "";
          if (window.__logon_user_code) {
            prescriber = String(window.__logon_user_code).replace(/-/g, " ");
          }

          return {
            medesync_id: id || "",
            apiData: apiData,
            extractedRamq: extractedRamq,
            extractedDob: extractedDob,
            prescriber_name: prescriber,
            pageTitle: document.title || ""
          };
        }
      });

      if (injectionResults && injectionResults.length > 0) {
        for (const res of injectionResults) {
          if (!res || !res.result) continue;
          const r = res.result;

          if (r.apiData) {
            const b = r.apiData;
            patientPayload.medesync_id = String(b.id || r.medesync_id || "");
            patientPayload.patient_name = b.fullName || `${b.firstName || ''} ${b.lastName || ''}`.trim();
            patientPayload.nom = b.lastName || "";
            patientPayload.prenom = b.firstName || "";
            patientPayload.ramq = b.nam || r.extractedRamq || "";
            patientPayload.dob = b.dobRaw || r.extractedDob || "";
            patientPayload.sex = b.sexeShort || (b.isMale ? "M" : "F");
            patientPayload.dossier = b.chartNumber || "";
            patientPayload.prescriber_name = r.prescriber_name || "";
            break; // Found complete API data!
          } else if (r.medesync_id || r.extractedRamq) {
            patientPayload.medesync_id = r.medesync_id || "";
            patientPayload.ramq = r.extractedRamq || "";
            patientPayload.dob = r.extractedDob || "";
            patientPayload.prescriber_name = r.prescriber_name || "";
          }
        }
      }

    } catch (err) {
      console.warn("[GUSTAV Background] Scripting tab failed, launching directly:", err);
    }
  }

  // 2. Negotiate single-use launch token with Gustav server and open tab
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
