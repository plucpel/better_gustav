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
    prescriber_name: "",
    doctor_license: ""
  };

  if (tab && tab.id) {
    try {
      // 1. Execute deep DOM & API inspection across all frames on the active Medesync tab
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: async () => {
          let id = "";
          let patientName = "";
          let ramq = "";
          let dob = "";
          let sex = "";
          let dossier = "";
          let prescriber = "";
          let doctorLicense = "";

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
          try {
            const scripts = document.querySelectorAll("script");
            for (const s of scripts) {
              const text = s.textContent || "";
              if (!id && text.includes("idPatient")) {
                const m = text.match(/"idPatient"\s*:\s*(\d+)/i) || text.match(/idPatient\s*=\s*(\d+)/i);
                if (m && m[1] && m[1] !== "0") id = m[1];
              }
            }
          } catch (e) {}

          // D. Prescriber info from global variables
          try {
            if (window.__logon_user_code) {
              prescriber = String(window.__logon_user_code).replace(/-/g, " ");
            }
            if (window.__logon_user_professional_id) {
              doctorLicense = String(window.__logon_user_professional_id);
            }
          } catch (e) {}

          // E. Look for Bearer / Auth tokens in storage
          let authToken = "";
          try {
            for (let i = 0; i < sessionStorage.length; i++) {
              const k = sessionStorage.key(i);
              const val = sessionStorage.getItem(k);
              if (val && (k.toLowerCase().includes("token") || k.toLowerCase().includes("auth") || val.startsWith("ey") || val.startsWith("Bearer "))) {
                authToken = val.replace(/^Bearer\s+/i, "");
                break;
              }
            }
            if (!authToken) {
              for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                const val = localStorage.getItem(k);
                if (val && (k.toLowerCase().includes("token") || k.toLowerCase().includes("auth") || val.startsWith("ey") || val.startsWith("Bearer "))) {
                  authToken = val.replace(/^Bearer\s+/i, "");
                  break;
                }
              }
            }
          } catch (e) {}

          // F. Query Medesync API with multi-host fallback
          if (id && /^\d+$/.test(id)) {
            const currentHost = window.location.hostname;
            const hostsToTry = [
              `https://${currentHost.replace('.medesync.com', '-api.medesync.com')}`,
              `https://${currentHost}`,
              'https://secure2-api.medesync.com',
              'https://secure-api.medesync.com'
            ];

            const reqHeaders = { 'Accept': 'application/json' };
            if (authToken) {
              reqHeaders['Authorization'] = `Bearer ${authToken}`;
            }

            for (const h of hostsToTry) {
              try {
                const resp = await fetch(`${h}/api/v3/patients/getBasicInfos/${id}`, {
                  credentials: 'include',
                  headers: reqHeaders
                });
                if (resp.ok) {
                  const data = await resp.json();
                  if (data && (data.nam || data.fullName || data.lastName || data.firstName)) {
                    patientName = data.fullName || `${data.firstName || ''} ${data.lastName || ''}`.trim();
                    ramq = data.nam || "";
                    dob = data.dobRaw || "";
                    sex = data.sexeShort || (data.isMale ? "M" : "F");
                    dossier = data.chartNumber || "";
                    break;
                  }
                }
              } catch (err) {
                // Silently continue to next host or fallback
              }
            }
          }

          // G. Deep DOM Regex Extraction (Fallback if API is unauthorized or blocked)
          try {
            const bodyText = (document.body ? document.body.innerText : "") + " " + document.title;
            
            // RAMQ Regex (e.g. ABCD 1234 5678 or ABCD12345678)
            if (!ramq) {
              const ramqMatch = bodyText.match(/\b([A-Z]{4})\s*(\d{2})\s*(\d{2})\s*(\d{2})\s*(\d{2})\b/i) ||
                                bodyText.match(/\b([A-Z]{4})\s*(\d{4})\s*(\d{4})\b/i) ||
                                bodyText.match(/\b([A-Z]{4}\d{8})\b/i);
              if (ramqMatch) {
                ramq = ramqMatch[0].replace(/\s+/g, "");
              }
            }

            // Date of Birth Regex (YYYY-MM-DD or DD/MM/YYYY)
            if (!dob) {
              const dobMatch = bodyText.match(/\b(19\d{2}|20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b/) ||
                               bodyText.match(/\b(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/(19\d{2}|20\d{2})\b/);
              if (dobMatch) {
                if (dobMatch[0].includes("/")) {
                  const parts = dobMatch[0].split("/");
                  dob = `${parts[2]}-${parts[1]}-${parts[0]}`;
                } else {
                  dob = dobMatch[0];
                }
              }
            }

            // Dossier
            if (!dossier) {
              const dosMatch = bodyText.match(/\b(?:Dossier|Chart|No dossier)[\s:#]+(\d+)\b/i);
              if (dosMatch) dossier = dosMatch[1];
            }

            // Patient Name from header / banner elements
            if (!patientName) {
              const nameEl = document.getElementById("patient_file") || 
                             document.querySelector(".patient_name") || 
                             document.querySelector(".patient-name") ||
                             document.querySelector(".patient-banner");
              if (nameEl && nameEl.innerText) {
                const lines = nameEl.innerText.split("\n").map(l => l.trim()).filter(Boolean);
                if (lines.length > 0) patientName = lines[0];
              }
            }
          } catch (e) {}

          return {
            medesync_id: id || "",
            patient_name: patientName || "",
            ramq: ramq || "",
            dob: dob || "",
            sex: sex || "",
            dossier: dossier || "",
            prescriber_name: prescriber || "",
            doctor_license: doctorLicense || ""
          };
        }
      });

      if (injectionResults && injectionResults.length > 0) {
        for (const res of injectionResults) {
          if (!res || !res.result) continue;
          const r = res.result;
          if (r.ramq || r.patient_name || r.medesync_id) {
            Object.assign(patientPayload, r);
            if (r.ramq && r.patient_name) break; // Found comprehensive data
          }
        }
      }

    } catch (err) {
      console.warn("[GUSTAV Background] Scripting tab completed with fallback:", err);
    }
  }

  // 2. Negotiate single-use launch token with Gustav server and open tab
  try {
    await handleLaunchGustav(patientPayload);
  } catch (err) {
    console.error("[GUSTAV Background] Launch failed:", err);
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

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.set({
    gustavUrl: DEFAULT_GUSTAV_URL,
    extensionSecret: DEFAULT_EXTENSION_SECRET
  });
  console.log("[GUSTAV Background] Initialized defaults on install/reload.");
});

async function getStoredSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(["gustavUrl", "extensionSecret"], (items) => {
      resolve({
        gustavUrl: (items.gustavUrl && items.gustavUrl.trim()) ? items.gustavUrl.trim().replace(/\/+$/, "") : DEFAULT_GUSTAV_URL,
        extensionSecret: (items.extensionSecret && items.extensionSecret.trim()) ? items.extensionSecret.trim() : DEFAULT_EXTENSION_SECRET
      });
    });
  });
}

async function handleLaunchGustav(patientPayload) {
  const { gustavUrl, extensionSecret } = await getStoredSettings();

  const bodyData = Object.assign({}, patientPayload || {}, {
    secret: extensionSecret,
    extension_secret: extensionSecret
  });

  console.log("[GUSTAV Background] Negotiating launch with:", `${gustavUrl}/api/context/launch`, bodyData);

  try {
    const resp = await fetch(`${gustavUrl}/api/context/launch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Gustav-Secret": extensionSecret
      },
      body: JSON.stringify(bodyData)
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
