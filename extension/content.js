/**
 * GUSTAV - Medesync Content Script (Manifest V3)
 * Injects one-click GUSTAV launcher into Medesync patient charts.
 */

(function () {
  console.log("[GUSTAV] Content script initialized on Medesync.");

  function getPatientIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get("id") || params.get("idPatient") || params.get("IdPatient");
  }

  async function fetchPatientBasicInfos(patientId) {
    try {
      const resp = await fetch(`/api/v3/patients/getBasicInfos/${patientId}`, {
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

  function extractPrescriberName() {
    try {
      // Look for Medesync global variables or UI elements
      if (window.__logon_user_code) {
        return String(window.__logon_user_code).replace(/-/g, " ");
      }
    } catch (e) {}
    return "";
  }

  function injectGustavButton(patientId) {
    if (document.getElementById("gustav-medesync-launcher-btn")) return;

    // Search for ideal container in Medesync DOM
    const targetContainer = 
      document.getElementById("patient_file") || 
      document.querySelector(".patient-section") || 
      document.querySelector("#mainContent .ui-tabs-nav") ||
      document.querySelector("body");

    if (!targetContainer) return;

    const btn = document.createElement("button");
    btn.id = "gustav-medesync-launcher-btn";
    btn.className = "gustav-btn-medesync";
    btn.innerHTML = `
      <span class="gustav-icon">🧪</span>
      <span class="gustav-text">GUSTAV</span>
    `;
    btn.title = "Calculer les tubes et générer la requête dans GUSTAV (Sécurisé)";

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="gustav-spinner"></span> Lancement...`;
      btn.disabled = true;

      try {
        let basicInfos = await fetchPatientBasicInfos(patientId);

        let patientPayload = {
          medesync_id: patientId,
          patient_name: "",
          nom: "",
          prenom: "",
          ramq: "",
          dob: "",
          sex: "",
          dossier: "",
          prescriber_name: extractPrescriberName()
        };

        if (basicInfos) {
          patientPayload.patient_name = basicInfos.fullName || `${basicInfos.firstName || ''} ${basicInfos.lastName || ''}`.trim();
          patientPayload.nom = basicInfos.lastName || "";
          patientPayload.prenom = basicInfos.firstName || "";
          patientPayload.ramq = basicInfos.nam || "";
          patientPayload.dob = basicInfos.dobRaw || "";
          patientPayload.sex = basicInfos.sexeShort || (basicInfos.isMale ? "M" : "F");
          patientPayload.dossier = basicInfos.chartNumber || "";
        }

        // Send to background service worker
        chrome.runtime.sendMessage({
          action: "LAUNCH_GUSTAV",
          patient: patientPayload
        }, (response) => {
          if (chrome.runtime.lastError) {
            alert("Erreur de connexion avec l'extension GUSTAV : " + chrome.runtime.lastError.message);
          } else if (response && !response.success) {
            alert("Erreur lors du lancement de GUSTAV : " + (response.error || "Inconnue"));
          }
        });

      } catch (err) {
        alert("Erreur GUSTAV : " + err.message);
      } finally {
        setTimeout(() => {
          btn.innerHTML = origHtml;
          btn.disabled = false;
        }, 1200);
      }
    });

    // Insertion
    if (targetContainer.id === "patient_file" || targetContainer.classList.contains("patient-section")) {
      targetContainer.prepend(btn);
    } else {
      targetContainer.appendChild(btn);
    }

    console.log("[GUSTAV] Launcher button successfully injected for patient ID:", patientId);
  }

  // Observer & Auto-check on route changes in Medesync SPA
  function checkAndInject() {
    const patientId = getPatientIdFromUrl();
    if (patientId) {
      injectGustavButton(patientId);
    }
  }

  checkAndInject();

  // Periodic check / MutationObserver to support client-side navigation
  const observer = new MutationObserver(() => {
    checkAndInject();
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
