/**
 * GUSTAV - Medesync Content Script (Manifest V3)
 * Injects GUSTAV launch triggers into Medesync EMR across top window and frames.
 */

(function () {
  const isTopWindow = (window === window.top);
  console.log(`[GUSTAV] Content script loaded on: ${window.location.href} (isTop: ${isTopWindow})`);

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

    const pill = document.createElement("div");
    pill.id = "gustav-floating-launcher";
    pill.className = "gustav-floating-pill";
    pill.innerHTML = `
      <span class="gustav-icon">🧪</span>
      <span class="gustav-text">GUSTAV</span>
    `;
    pill.title = "Ouvrir le Calculateur GUSTAV (Synchronisation automatique Medesync)";

    pill.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      handleLaunchClick(pill);
    });

    document.body.appendChild(pill);
    console.log("[GUSTAV] Persistent floating badge successfully injected.");
  }

  /**
   * Main Check & Injection Cycle
   */
  function scanAndInject() {
    // 1. Always ensure the persistent floating pill is on screen in the top window
    injectFloatingLauncher();

    // 2. Look for patient chart container
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

  // Observe SPA route / DOM mutations
  const observer = new MutationObserver(() => {
    scanAndInject();
  });

  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    window.addEventListener("load", () => {
      if (document.body) observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();
