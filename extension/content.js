/**
 * GUSTAV - Medesync Content Script (Manifest V3)
 * Injects GUSTAV launch triggers into Medesync EMR across top window and frames.
 */

(function () {
  console.log("%c[GUSTAV EXTENSION] Content script active on:", "background: #0284c7; color: #fff; font-weight: bold; padding: 2px 6px; border-radius: 3px;", window.location.href);

  function isMedesyncEnvironment() {
    const host = window.location.hostname.toLowerCase();
    if (host.includes("medesync") || host.includes("telus") || host.includes("dmeqc")) {
      return true;
    }
    if (document.getElementById("aspnetForm") || document.getElementById("patient_file") || document.getElementById("dlgMenuBureaux")) {
      return true;
    }
    if (document.title && document.title.toLowerCase().includes("medesync")) {
      return true;
    }
    return false;
  }

  // Only run inside Medesync or DME environments
  if (!isMedesyncEnvironment()) {
    return;
  }

  const isTopWindow = (window === window.top);

  /**
   * Search for active patient ID across multiple Medesync DOM structures
   */
  function findActivePatientId() {
    // 1. From URL Query Parameters
    try {
      const params = new URLSearchParams(window.location.search);
      const urlId = params.get("id") || params.get("idPatient") || params.get("IdPatient");
      if (urlId && /^\d+$/.test(urlId) && urlId !== "0") return urlId;
    } catch (e) {}

    // 2. From ASP.NET form action attribute
    try {
      const aspnetForm = document.getElementById("aspnetForm") || document.forms["aspnetForm"];
      if (aspnetForm && aspnetForm.action) {
        const m = aspnetForm.action.match(/[?&]id=(\d+)/i);
        if (m && m[1]) return m[1];
      }
    } catch (e) {}

    // 3. From Medesync inline init scripts (e.g. Medesync.Patient.InitSetting)
    try {
      const scripts = document.querySelectorAll("script");
      for (const s of scripts) {
        const text = s.textContent || "";
        if (text.includes("idPatient")) {
          const m = text.match(/"idPatient"\s*:\s*(\d+)/i) || text.match(/idPatient\s*=\s*(\d+)/i);
          if (m && m[1] && m[1] !== "0") return m[1];
        }
      }
    } catch (e) {}

    // 4. From any child iframes if in top window
    if (isTopWindow) {
      try {
        const iframes = document.querySelectorAll("iframe");
        for (const frame of iframes) {
          const src = frame.getAttribute("src") || "";
          const m = src.match(/[?&]id=(\d+)/i) || src.match(/[?&]idPatient=(\d+)/i);
          if (m && m[1] && m[1] !== "0") return m[1];
        }
      } catch (e) {}
    }

    return null;
  }

  /**
   * Extract prescriber info from Medesync global variables
   */
  function extractPrescriberName() {
    try {
      if (window.__logon_user_code) {
        return String(window.__logon_user_code).replace(/-/g, " ");
      }
    } catch (e) {}
    return "";
  }

  /**
   * Fetch patient demographics from ambient Medesync session API
   */
  async function fetchPatientBasicInfos(patientId) {
    if (!patientId) return null;
    const apiHost = window.location.hostname.includes("-api") 
      ? window.location.origin 
      : `https://${window.location.hostname}`;

    try {
      const resp = await fetch(`${apiHost}/api/v3/patients/getBasicInfos/${patientId}`, {
        headers: { "Accept": "application/json" }
      });
      if (resp.ok) {
        return await resp.json();
      }
    } catch (e) {
      console.warn("[GUSTAV] Could not fetch basic infos via API:", e);
    }
    return null;
  }

  /**
   * Action triggered on click: constructs payload and messages background worker
   */
  async function handleLaunchClick(btnElement) {
    const origHtml = btnElement.innerHTML;
    btnElement.innerHTML = `<span class="gustav-spinner"></span> Lancement...`;
    btnElement.disabled = true;

    try {
      const patientId = findActivePatientId();
      let patientPayload = {
        medesync_id: patientId || "",
        patient_name: "",
        nom: "",
        prenom: "",
        ramq: "",
        dob: "",
        sex: "",
        dossier: "",
        prescriber_name: extractPrescriberName()
      };

      if (patientId) {
        const basicInfos = await fetchPatientBasicInfos(patientId);
        if (basicInfos) {
          patientPayload.patient_name = basicInfos.fullName || `${basicInfos.firstName || ''} ${basicInfos.lastName || ''}`.trim();
          patientPayload.nom = basicInfos.lastName || "";
          patientPayload.prenom = basicInfos.firstName || "";
          patientPayload.ramq = basicInfos.nam || "";
          patientPayload.dob = basicInfos.dobRaw || "";
          patientPayload.sex = basicInfos.sexeShort || (basicInfos.isMale ? "M" : "F");
          patientPayload.dossier = basicInfos.chartNumber || "";
        }
      }

      // Send to background service worker
      chrome.runtime.sendMessage({
        action: "LAUNCH_GUSTAV",
        patient: patientPayload
      }, (response) => {
        if (chrome.runtime.lastError) {
          alert("Erreur extension GUSTAV : " + chrome.runtime.lastError.message);
        } else if (response && !response.success) {
          alert("Erreur lors du lancement de GUSTAV : " + (response.error || "Inconnue"));
        }
      });

    } catch (err) {
      alert("Erreur GUSTAV : " + err.message);
    } finally {
      setTimeout(() => {
        btnElement.innerHTML = origHtml;
        btnElement.disabled = false;
      }, 1200);
    }
  }

  /**
   * Inject Inline Button in Patient Header
   */
  function injectInlineButton(patientId) {
    if (document.getElementById("gustav-medesync-launcher-btn")) return;

    const targetContainer = 
      document.getElementById("patient_file") || 
      document.querySelector(".patient-section") || 
      document.querySelector("#mainContent .ui-tabs-nav") ||
      document.querySelector(".patient-header");

    if (!targetContainer) return;

    const btn = document.createElement("button");
    btn.id = "gustav-medesync-launcher-btn";
    btn.className = "gustav-btn-medesync";
    btn.style.cssText = "display: inline-flex !important; align-items: center !important; gap: 6px !important; background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important; color: #ffffff !important; border: 1px solid #0284c7 !important; border-radius: 6px !important; padding: 5px 12px !important; font-size: 13px !important; font-weight: 700 !important; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important; cursor: pointer !important; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15) !important; margin: 4px 8px !important; vertical-align: middle !important; z-index: 9999 !important;";
    btn.innerHTML = `
      <span class="gustav-icon">🧪</span>
      <span class="gustav-text">GUSTAV</span>
    `;
    btn.title = "Calculer les tubes et générer la requête dans GUSTAV (Sécurisé)";

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      handleLaunchClick(btn);
    });

    targetContainer.prepend(btn);
    console.log("[GUSTAV] Inline button injected into patient header (Patient ID:", patientId, ")");
  }

  /**
   * Inject Persistent Floating Quick Launcher (in top-level window)
   */
  function injectFloatingLauncher() {
    if (!isTopWindow || document.getElementById("gustav-floating-launcher")) return;

    const parent = document.body || document.documentElement;
    if (!parent) return;

    const pill = document.createElement("div");
    pill.id = "gustav-floating-launcher";
    pill.className = "gustav-floating-pill";
    pill.style.cssText = "position: fixed !important; bottom: 20px !important; right: 20px !important; z-index: 2147483647 !important; display: inline-flex !important; align-items: center !important; gap: 8px !important; background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important; color: #ffffff !important; border: 2px solid #ffffff !important; border-radius: 9999px !important; padding: 10px 18px !important; font-size: 14px !important; font-weight: 800 !important; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important; cursor: pointer !important; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35) !important; text-decoration: none !important; opacity: 1 !important; visibility: visible !important; user-select: none !important;";
    pill.innerHTML = `
      <span class="gustav-icon" style="font-size: 16px;">🧪</span>
      <span class="gustav-text" style="letter-spacing: 0.5px; font-weight: 800;">GUSTAV</span>
    `;
    pill.title = "Ouvrir le Calculateur GUSTAV (Synchronisation automatique Medesync)";

    pill.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      handleLaunchClick(pill);
    });

    parent.appendChild(pill);
    console.log("[GUSTAV] Persistent floating badge successfully injected.");
  }

  /**
   * Main Check & Injection Cycle
   */
  function scanAndInject() {
    injectFloatingLauncher();

    const patientId = findActivePatientId();
    if (patientId) {
      injectInlineButton(patientId);
    }
  }

  // Initial Run
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanAndInject);
  } else {
    scanAndInject();
  }

  // Periodic fallback check
  setInterval(scanAndInject, 1500);

  // Observe SPA route / DOM mutations
  const observer = new MutationObserver(() => {
    scanAndInject();
  });

  const rootTarget = document.body || document.documentElement;
  if (rootTarget) {
    observer.observe(rootTarget, { childList: true, subtree: true });
  }
})();
