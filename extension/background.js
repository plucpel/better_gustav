/**
 * GUSTAV - Medesync Background Service Worker (Manifest V3)
 * Universal 1-Click Patient Context Extraction from Any Medesync Tab
 * Version 1.3.0
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
      // 1. Fallback tab title name (e.g. "Patient Test")
      if (tab.title && !tab.title.toLowerCase().includes("medesync")) {
        const cleanTitle = tab.title.replace(/\s*[-–|].*$/, "").trim();
        if (cleanTitle && cleanTitle.length > 2) {
          patientPayload.patient_name = cleanTitle;
        }
      }

      // 2. Execute deep frame & DOM extraction across all frames (top shell + sub-iframes)
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: () => {
          let id = "";
          let patientName = "";
          let nom = "";
          let prenom = "";
          let ramq = "";
          let dob = "";
          let sex = "";
          let dossier = "";
          let prescriber = "";
          let doctorLicense = "";

          // --- A. PATIENT ID DETECTION ---
          try {
            // Path: /Patients/Edit/35660746
            const pathMatch = window.location.pathname.match(/\/Patients\/Edit\/(\d+)/i);
            if (pathMatch) id = pathMatch[1];

            // Search params: ?id=35660746
            if (!id) {
              const params = new URLSearchParams(window.location.search);
              id = params.get("id") || params.get("idPatient") || params.get("IdPatient") || "";
            }

            // Form action
            if (!id) {
              const form = document.getElementById("aspnetForm") || document.forms["aspnetForm"];
              if (form && form.action) {
                const m = form.action.match(/[?&]id=(\d+)/i) || form.action.match(/\/(\d{6,10})/);
                if (m) id = m[1];
              }
            }

            // Script tags
            if (!id) {
              const scripts = document.querySelectorAll("script");
              for (const s of scripts) {
                const text = s.textContent || "";
                if (text.includes("idPatient")) {
                  const m = text.match(/"idPatient"\s*:\s*(\d+)/i) || text.match(/idPatient\s*=\s*(\d+)/i);
                  if (m && m[1] && m[1] !== "0") { id = m[1]; break; }
                }
              }
            }
          } catch (e) {}

          // --- B. PRESCRIBER DETECTION ---
          try {
            if (window.__logon_user_code) {
              prescriber = String(window.__logon_user_code).replace(/-/g, " ");
            }
            if (window.__logon_user_professional_id) {
              doctorLicense = String(window.__logon_user_professional_id);
            }
          } catch (e) {}

          // --- C. PERSISTENT TOP BANNER EXTRACTION (WORKS ON ALL TABS) ---
          // Format from screenshot:
          // Line 1: "Patient Test 30 nov. 1974 (51 ans, 9 mois) | Homme"
          // Line 2: "NAM: TEST 7461 3019 | N° dossier: 3"
          const months = {
            'janv': '01', 'janvier': '01',
            'fevr': '02', 'févr': '02', 'fevrier': '02', 'février': '02',
            'mars': '03',
            'avr': '04', 'avril': '04',
            'mai': '05',
            'juin': '06',
            'juil': '07', 'juillet': '07',
            'aout': '08', 'août': '08',
            'sept': '09', 'septembre': '09',
            'oct': '10', 'octobre': '10',
            'nov': '11', 'novembre': '11',
            'dec': '12', 'déc': '12', 'decembre': '12', 'décembre': '12'
          };

          const bodyText = (document.body ? document.body.innerText : "") + "\n" + (document.title || "");
          const lines = bodyText.split("\n").map(l => l.trim()).filter(Boolean);

          for (const line of lines) {
            // Check for persistent header line with Name + DOB + Sex:
            // e.g. "Patient Test 30 nov. 1974 (51 ans, 9 mois) | Homme"
            const bannerMatch = line.match(/^([A-Za-z\u00c0-\u00ff\s\'-]{2,50}?)\s+(\d{1,2})\s+(janv|f[eé]vr|fevr|mars|avr|mai|juin|juil|ao[uû]t|aout|sept|oct|nov|d[eé]c|dec|janvier|f[eé]vrier|février|avril|mai|juin|juillet|août|septembre|octobre|novembre|d[eé]cembre)\.?\s+(\d{4})/i);
            if (bannerMatch) {
              const rawName = bannerMatch[1].trim();
              if (rawName && !/^(sommaire|historique|informations|ramq|notes|rendez-vous|ordonnances)/i.test(rawName)) {
                patientName = rawName;
              }
              const d = String(bannerMatch[2]).padStart(2, "0");
              const mKey = bannerMatch[3].toLowerCase();
              const mVal = months[mKey] || "01";
              const y = bannerMatch[4];
              dob = `${y}-${mVal}-${d}`;
            }

            // Check for RAMQ in line (NAM: TEST 7461 3019 or TEST 7461 3019)
            if (!ramq) {
              const rMatch = line.match(/(?:NAM|RAMQ)[\s:#]*([A-Za-z]{4}\s*\d{2}\s*\d{2}\s*\d{2}\s*\d{2}|[A-Za-z]{4}\s*\d{4}\s*\d{4}|[A-Za-z]{4}\d{8})/i) ||
                             line.match(/\b([A-Za-z]{4}\s*\d{4}\s*\d{4})\b/);
              if (rMatch) {
                ramq = rMatch[1].replace(/\s+/g, "").toUpperCase();
              }
            }

            // Check for Dossier (N° dossier: 3 or No. dossier 3)
            if (!dossier) {
              const dMatch = line.match(/(?:N[°o]\.?\s*dossier|No\.\s*dossier|Dossier)[\s:#]+([\d-]+)/i);
              if (dMatch) {
                dossier = dMatch[1].trim();
              }
            }

            // Check for Sex
            if (!sex) {
              const sMatch = line.match(/\|\s*(Homme|Femme|Masculin|F[eé]minin|M|F)\b/i) ||
                             line.match(/(?:Genre|Sexe)\s*:\s*(Homme|Femme|M|F)\b/i);
              if (sMatch) {
                const sStr = sMatch[1].toLowerCase();
                sex = (sStr.startsWith("h") || sStr === "m") ? "M" : "F";
              }
            }
          }

          // --- D. FORM INPUTS (WHEN ON "INFORMATIONS GÉNÉRALES" TAB) ---
          try {
            // Prénom / Nom inputs
            const prenomInput = document.querySelector("input[name*='Prenom' i], input[id*='Prenom' i], input[name*='FirstName' i]");
            if (prenomInput && prenomInput.value) prenom = prenomInput.value.trim();

            const nomInput = document.querySelector("input[name*='Nom' i], input[id*='Nom' i], input[name*='LastName' i]");
            if (nomInput && nomInput.value) nom = nomInput.value.trim();

            if (prenom && nom && !patientName) {
              patientName = `${prenom} ${nom}`;
            }

            // RAMQ input
            if (!ramq) {
              const ramqInput = document.querySelector("input[name*='Ramq' i], input[id*='Ramq' i], input[name*='Nam' i]");
              if (ramqInput && ramqInput.value) {
                ramq = ramqInput.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
              }
            }

            // DOB input
            if (!dob) {
              const dobInput = document.querySelector("input[name*='DateNaissance' i], input[id*='DateNaissance' i], input[name*='Dob' i]");
              if (dobInput && dobInput.value) {
                const val = dobInput.value.trim();
                const dMatch = val.match(/(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)\s+(\d{4})/i);
                if (dMatch) {
                  const d = String(dMatch[1]).padStart(2, "0");
                  const m = months[dMatch[2].toLowerCase()] || "01";
                  const y = dMatch[3];
                  dob = `${y}-${m}-${d}`;
                } else if (/^\d{4}-\d{2}-\d{2}$/.test(val)) {
                  dob = val;
                }
              }
            }

            // Dossier input
            if (!dossier) {
              const dosInput = document.querySelector("input[name*='Dossier' i], input[id*='Dossier' i], input[name*='Chart' i]");
              if (dosInput && dosInput.value) dossier = dosInput.value.trim();
            }
          } catch (e) {}

          // --- E. TAB TITLE CLEANUP ---
          if (!patientName && document.title && !document.title.toLowerCase().includes("medesync")) {
            patientName = document.title.replace(/\s*[-–|].*$/, "").trim();
          }

          return {
            medesync_id: id || "",
            patient_name: patientName || "",
            nom: nom || "",
            prenom: prenom || "",
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

          // Merge non-empty fields with preference for fuller data
          if (r.patient_name && !patientPayload.patient_name) patientPayload.patient_name = r.patient_name;
          if (r.nom && !patientPayload.nom) patientPayload.nom = r.nom;
          if (r.prenom && !patientPayload.prenom) patientPayload.prenom = r.prenom;
          if (r.ramq && !patientPayload.ramq) patientPayload.ramq = r.ramq;
          if (r.dob && !patientPayload.dob) patientPayload.dob = r.dob;
          if (r.sex && !patientPayload.sex) patientPayload.sex = r.sex;
          if (r.dossier && !patientPayload.dossier) patientPayload.dossier = r.dossier;
          if (r.medesync_id && !patientPayload.medesync_id) patientPayload.medesync_id = r.medesync_id;
          if (r.prescriber_name && !patientPayload.prescriber_name) patientPayload.prescriber_name = r.prescriber_name;
          if (r.doctor_license && !patientPayload.doctor_license) patientPayload.doctor_license = r.doctor_license;
        }
      }

    } catch (err) {
      console.warn("[GUSTAV Background] Extraction error:", err);
    }
  }

  // If patient_name is set but nom/prenom are blank, split into parts
  if (patientPayload.patient_name && (!patientPayload.nom || !patientPayload.prenom)) {
    const parts = patientPayload.patient_name.split(/\s+/);
    if (parts.length >= 2) {
      patientPayload.prenom = patientPayload.prenom || parts[0];
      patientPayload.nom = patientPayload.nom || parts.slice(1).join(" ");
    } else {
      patientPayload.nom = patientPayload.nom || patientPayload.patient_name;
    }
  }

  console.log("[GUSTAV Background] Final patient context extracted:", patientPayload);

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

  console.log("[GUSTAV Background] Launching Gustav with payload:", bodyData);

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
