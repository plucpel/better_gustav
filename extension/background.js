/**
 * GUSTAV - Medesync Background Service Worker (Manifest V3)
 * Direct 1-Click Launch Handler from Chrome Toolbar Icon
 * 100% In-Memory DOM & Script Extraction (Zero Medesync API calls)
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
      // Execute 100% in-memory DOM & Script extraction across all frames
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: () => {
          let id = "";
          let patientName = "";
          let ramq = "";
          let dob = "";
          let sex = "";
          let dossier = "";
          let prescriber = "";
          let doctorLicense = "";

          // 1. Patient ID from URL params
          try {
            const params = new URLSearchParams(window.location.search);
            id = params.get("id") || params.get("idPatient") || params.get("IdPatient") || "";
          } catch (e) {}

          // 2. Patient ID from ASP.NET form action
          if (!id) {
            try {
              const form = document.getElementById("aspnetForm") || document.forms["aspnetForm"];
              if (form && form.action) {
                const m = form.action.match(/[?&]id=(\d+)/i);
                if (m) id = m[1];
              }
            } catch (e) {}
          }

          // 3. Patient ID from script tags (Medesync.Patient.InitSetting)
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

          // 4. Prescriber info from Medesync global variables
          try {
            if (window.__logon_user_code) {
              prescriber = String(window.__logon_user_code).replace(/-/g, " ");
            }
            if (window.__logon_user_professional_id) {
              doctorLicense = String(window.__logon_user_professional_id);
            }
          } catch (e) {}

          // 5. Patient Data from DOM Text & Specific Elements
          const bodyText = (document.body ? document.body.innerText : "") + " " + document.title;

          // RAMQ Regex (format: ABCD 1234 5678 or ABCD12345678 or ABCD 12 34 56 78)
          const ramqMatch = bodyText.match(/\b([A-Za-z]{4})\s*(\d{2})\s*(\d{2})\s*(\d{2})\s*(\d{2})\b/) ||
                            bodyText.match(/\b([A-Za-z]{4})\s*(\d{4})\s*(\d{4})\b/) ||
                            bodyText.match(/\b([A-Za-z]{4}\d{8})\b/);
          if (ramqMatch) {
            ramq = ramqMatch[0].replace(/\s+/g, "").toUpperCase();
          }

          // Date of Birth (ISO YYYY-MM-DD, DD/MM/YYYY, or French text '30 novembre 1974')
          const isoDobMatch = bodyText.match(/\b(19\d{2}|20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b/);
          const slashDobMatch = bodyText.match(/\b(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/(19\d{2}|20\d{2})\b/);
          const frenchDobMatch = bodyText.match(/(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)\s+(\d{4})/i);

          if (isoDobMatch) {
            dob = isoDobMatch[0];
          } else if (slashDobMatch) {
            const p = slashDobMatch[0].split("/");
            dob = `${p[2]}-${p[1]}-${p[0]}`;
          } else if (frenchDobMatch) {
            const months = {
              'janvier': '01', 'fevrier': '02', 'février': '02', 'mars': '03',
              'avril': '04', 'mai': '05', 'juin': '06', 'juillet': '07',
              'aout': '08', 'août': '08', 'septembre': '09', 'octobre': '10',
              'novembre': '11', 'decembre': '12', 'décembre': '12'
            };
            const d = String(frenchDobMatch[1]).padStart(2, "0");
            const m = months[frenchDobMatch[2].toLowerCase()] || "01";
            const y = frenchDobMatch[3];
            dob = `${y}-${m}-${d}`;
          }

          // Sex (Homme / Femme / M / F)
          if (/\b(?:Genre|Sexe)\s*:\s*(?:Homme|M|Masculin)\b/i.test(bodyText) || /\bHomme\b/i.test(bodyText)) {
            sex = "M";
          } else if (/\b(?:Genre|Sexe)\s*:\s*(?:Femme|F|Féminin)\b/i.test(bodyText) || /\bFemme\b/i.test(bodyText)) {
            sex = "F";
          }

          // Dossier / Chart Number (format: Dossier: 4629-2995 or Chart #1234)
          const dosMatch = bodyText.match(/(?:Dossier|Chart|No dossier)[\s:#]+([\d-]+)/i);
          if (dosMatch) {
            dossier = dosMatch[1].trim();
          }

          // Patient Name from headers, titles, or DOM sections
          const patientFileEl = document.getElementById("patient_file") || 
                                document.querySelector(".patient_name") || 
                                document.querySelector(".patient-name") ||
                                document.querySelector(".patient-banner");
          if (patientFileEl && patientFileEl.innerText) {
            const lines = patientFileEl.innerText.split("\n").map(l => l.trim()).filter(Boolean);
            if (lines.length > 0) patientName = lines[0];
          }

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
            if (r.ramq && (r.patient_name || r.dob)) break;
          }
        }
      }

    } catch (err) {
      console.warn("[GUSTAV Background] Extraction completed with fallback:", err);
    }
  }

  // Negotiate single-use launch token with Gustav server and open tab
  try {
    await handleLaunchGustav(patientPayload);
  } catch (err) {
    console.error("[GUSTAV Background] Launch failed:", err);
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
