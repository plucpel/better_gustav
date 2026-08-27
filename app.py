import os
import hmac
import hashlib
import secrets
import uvicorn
from fastapi import FastAPI, Query, Path, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated

from tube_calculator import search_analyses, calculate_tubes, load_catalog
from medical_dictionary import CLINICAL_PANELS
from requisition_filler import (
    generate_filled_requisition_pdf,
    inspect_requisition_selection,
    parse_ramq_barcode_payload
)

app = FastAPI(
    title="Gustav - Calculateur de Tubes Sanguins (CHU de Québec)",
    version="1.0.0",
    docs_url=None, # Disable Swagger UI in production
    redoc_url=None
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")
LOGIN_HTML = os.path.join(STATIC_DIR, "login.html")

# Security & Authentication Configuration
GUSTAV_PIN = os.getenv("GUSTAV_PIN", "415263")
GUSTAV_SECRET_KEY = os.getenv("GUSTAV_SECRET_KEY", secrets.token_hex(32))
COOKIE_NAME = "gustav_session"

def generate_session_token() -> str:
    return hmac.new(GUSTAV_SECRET_KEY.encode(), (GUSTAV_PIN or "").encode(), hashlib.sha256).hexdigest()

def is_authenticated(request: Request) -> bool:
    if not GUSTAV_PIN:  # If PIN is empty or disabled
        return True
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie:
        return False
    expected_token = generate_session_token()
    return secrets.compare_digest(session_cookie, expected_token)

# Security & Authentication Middleware
@app.middleware("http")
async def security_and_auth_middleware(request: Request, call_next):
    # Intercept protected API endpoints (except /api/auth/*)
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/"):
        if not is_authenticated(request):
            return Response(
                content='{"detail": "Non authentifié"}',
                status_code=401,
                media_type="application/json"
            )

    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

class LoginRequest(BaseModel):
    pin: Annotated[str, Field(max_length=50)]

@app.post("/api/auth/login")
async def api_auth_login(req: LoginRequest, response: Response):
    """Vérifier le code PIN et émettre un cookie de session temporaire."""
    if not GUSTAV_PIN or secrets.compare_digest(req.pin.strip(), GUSTAV_PIN):
        token = generate_session_token()
        # Session cookie: no max_age or expires -> automatically destroyed when tab/browser closes
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax"
        )
        return {"status": "success", "message": "Authentifié"}
    raise HTTPException(status_code=401, detail="Code PIN incorrect")

@app.post("/api/auth/logout")
async def api_auth_logout(response: Response):
    """Verrouiller la session en supprimant le cookie."""
    response.delete_cookie(COOKIE_NAME)
    return {"status": "success", "message": "Déconnecté"}

@app.get("/api/auth/status")
async def api_auth_status(request: Request):
    """Vérifier l'état d'authentification."""
    return {"authenticated": is_authenticated(request)}

class CalculateRequest(BaseModel):
    pids: List[Annotated[str, Field(max_length=64)]] = Field(..., max_length=100)
    site: Optional[Annotated[str, Field(max_length=120)]] = "Tous les sites"
    is_pediatric: Optional[bool] = False

class PatientInfo(BaseModel):
    ramq: Optional[Annotated[str, Field(max_length=30)]] = ""
    dossier: Optional[Annotated[str, Field(max_length=30)]] = ""
    room: Optional[Annotated[str, Field(max_length=30)]] = ""
    patient_name: Optional[Annotated[str, Field(max_length=100)]] = ""
    dob: Optional[Annotated[str, Field(max_length=20)]] = ""
    clinical_info: Optional[Annotated[str, Field(max_length=200)]] = ""
    sex: Optional[Annotated[str, Field(max_length=5)]] = ""
    doctor_name: Optional[Annotated[str, Field(max_length=100)]] = ""
    doctor_license: Optional[Annotated[str, Field(max_length=30)]] = ""
    clinic_name: Optional[Annotated[str, Field(max_length=100)]] = ""
    clinic_id: Optional[Annotated[str, Field(max_length=30)]] = ""
    doctor_copy: Optional[Annotated[str, Field(max_length=100)]] = ""
    doctor_copy_license: Optional[Annotated[str, Field(max_length=30)]] = ""
    sample_date: Optional[Annotated[str, Field(max_length=20)]] = ""
    sample_time: Optional[Annotated[str, Field(max_length=15)]] = ""
    nurse_name: Optional[Annotated[str, Field(max_length=100)]] = ""
    sample_location: Optional[Annotated[str, Field(max_length=100)]] = ""

class RequisitionRequest(BaseModel):
    pids: List[Annotated[str, Field(max_length=64)]] = Field(..., max_length=100)
    site: Optional[Annotated[str, Field(max_length=120)]] = "Tous les sites"
    patient_info: Optional[PatientInfo] = None

@app.get("/")
async def serve_index(request: Request):
    if not is_authenticated(request):
        if os.path.exists(LOGIN_HTML):
            with open(LOGIN_HTML, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
        return HTMLResponse(content="<h1>Accès sécurisé requis</h1>", media_type="text/html; charset=utf-8")

    if os.path.exists(INDEX_HTML):
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    return HTMLResponse(content="<h1>Gustav Tube Calculator</h1>", media_type="text/html; charset=utf-8")

@app.get("/api/search")
async def api_search(q: str = Query("", max_length=100, description="Search term, acronym, or panel")):
    """Deterministic instant search endpoint with bounded query length."""
    return search_analyses(q, limit=15)

@app.get("/api/panels")
async def api_panels():
    """Get all pre-configured clinical panels."""
    return CLINICAL_PANELS

@app.get("/api/analysis/{pid}")
async def api_get_analysis(pid: str = Path(..., max_length=64)):
    """Get full details and specimen fiches for an analysis."""
    catalog = load_catalog()
    pid_clean = pid.lower().strip()
    if pid_clean in catalog:
        return catalog[pid_clean]
    raise HTTPException(status_code=404, detail="Analysis not found in Gustav catalog")

@app.post("/api/calculate")
async def api_calculate(req: CalculateRequest):
    """Calculate the required tubes, grouping, and Order of Draw."""
    return calculate_tubes(
        selected_pids=req.pids,
        site=req.site or "Tous les sites",
        is_pediatric=bool(req.is_pediatric)
    )

from profiles_manager import (
    get_all_prescribers,
    upsert_prescriber,
    update_prescriber,
    delete_prescriber,
    get_all_nurses,
    upsert_nurse,
    update_nurse,
    delete_nurse,
    get_all_locations,
    upsert_location,
    update_location,
    delete_location,
    unified_search_prescribers
)

class PrescriberModel(BaseModel):
    doctor_name: Annotated[str, Field(max_length=120)]
    doctor_license: Optional[Annotated[str, Field(max_length=30)]] = ""
    clinic_name: Optional[Annotated[str, Field(max_length=120)]] = ""
    clinic_id: Optional[Annotated[str, Field(max_length=30)]] = ""
    doctor_copy: Optional[Annotated[str, Field(max_length=120)]] = ""
    doctor_copy_license: Optional[Annotated[str, Field(max_length=30)]] = ""

class NurseModel(BaseModel):
    nurse_name: Annotated[str, Field(max_length=120)]
    sample_location: Optional[Annotated[str, Field(max_length=120)]] = ""

class LocationModel(BaseModel):
    name: Annotated[str, Field(max_length=200)]

# ==============================================================================
# PROFILES & DIRECTORY ENDPOINTS
# ==============================================================================

@app.get("/api/prescribers/search")
async def api_search_prescribers(q: str = Query("", max_length=100)):
    """Search unified prescribers across clinic directory and CMQ registry."""
    return unified_search_prescribers(q, limit=20)

@app.get("/api/prescribers")
async def api_get_prescribers():
    """Get all clinic prescribers."""
    return get_all_prescribers()

@app.post("/api/prescribers")
async def api_create_prescriber(req: PrescriberModel):
    """Create or upsert a clinic prescriber."""
    return upsert_prescriber(req.model_dump())

@app.put("/api/prescribers/{prescriber_id}")
async def api_update_prescriber(prescriber_id: str, req: PrescriberModel):
    """Update a specific prescriber."""
    res = update_prescriber(prescriber_id, req.model_dump())
    if not res:
        raise HTTPException(status_code=404, detail="Prescriber not found")
    return res

@app.delete("/api/prescribers/{prescriber_id}")
async def api_delete_prescriber(prescriber_id: str):
    """Delete a prescriber by ID."""
    if not delete_prescriber(prescriber_id):
        raise HTTPException(status_code=404, detail="Prescriber not found")
    return {"status": "success", "deleted_id": prescriber_id}

@app.get("/api/nurses")
async def api_get_nurses():
    """Get all saved nurses/préleveurs."""
    return get_all_nurses()

@app.post("/api/nurses")
async def api_create_nurse(req: NurseModel):
    """Create or upsert a nurse/préleveur."""
    return upsert_nurse(req.model_dump())

@app.put("/api/nurses/{nurse_id}")
async def api_update_nurse(nurse_id: str, req: NurseModel):
    """Update a specific nurse/préleveur."""
    res = update_nurse(nurse_id, req.model_dump())
    if not res:
        raise HTTPException(status_code=404, detail="Nurse not found")
    return res

@app.delete("/api/nurses/{nurse_id}")
async def api_delete_nurse(nurse_id: str):
    """Delete a nurse/préleveur by ID."""
    if not delete_nurse(nurse_id):
        raise HTTPException(status_code=404, detail="Nurse not found")
    return {"status": "success", "deleted_id": nurse_id}

# ==============================================================================
# LOCATIONS ENDPOINTS
# ==============================================================================

@app.get("/api/locations")
async def api_get_locations():
    """Get all sample collection locations."""
    return get_all_locations()

@app.post("/api/locations")
async def api_create_location(req: LocationModel):
    """Create a sample collection location."""
    return upsert_location(req.model_dump())

@app.put("/api/locations/{location_id}")
async def api_update_location(location_id: str, req: LocationModel):
    """Update a sample collection location."""
    res = update_location(location_id, req.model_dump())
    if not res:
        raise HTTPException(status_code=404, detail="Location not found")
    return res

@app.delete("/api/locations/{location_id}")
async def api_delete_location(location_id: str):
    """Delete a sample collection location."""
    if not delete_location(location_id):
        raise HTTPException(status_code=404, detail="Location not found")
    return {"status": "success", "deleted_id": location_id}

from clinics_manager import (
    search_clinics,
    get_available_sites,
    get_available_types,
    get_clinic_by_id
)

# ==============================================================================
# SIL-P CLINICS ENDPOINTS (Microsoft Fabric / Power BI Dataset)
# ==============================================================================

@app.get("/api/clinics/search")
async def api_search_clinics(
    q: str = Query("", max_length=100, description="Recherche par nom, ID SIL-P, ville, code postal ou adresse"),
    site: Optional[str] = Query(None, max_length=150, description="Filtre par site ou centre hospitalier"),
    type: Optional[str] = Query(None, max_length=20, description="Filtre par type d'inscription (E, H, I, etc.)"),
    limit: int = Query(50, ge=1, le=200, description="Nombre de résultats par page"),
    offset: int = Query(0, ge=0, description="Index de départ pour la pagination")
):
    """Recherche ultra-rapide et filtrage des 19 600+ cliniques et établissements SIL-P."""
    return search_clinics(
        query=q,
        site=site,
        clinic_type=type,
        limit=limit,
        offset=offset
    )

@app.get("/api/clinics/sites")
async def api_get_clinic_sites():
    """Obtenir la liste des sites/centres hospitaliers avec leur décompte."""
    return get_available_sites()

@app.get("/api/clinics/types")
async def api_get_clinic_types():
    """Obtenir la liste des types d'inscription avec libellés détaillés et décomptes."""
    return get_available_types()

@app.get("/api/clinics/{clinic_id}")
async def api_get_clinic(clinic_id: str = Path(..., max_length=50)):
    """Obtenir les détails complets d'une clinique par son ID SIL-P."""
    clinic = get_clinic_by_id(clinic_id)
    if not clinic:
        raise HTTPException(status_code=404, detail="Clinique SIL-P non trouvée")
    return clinic

# ==============================================================================
# REQUISITION ENDPOINTS
# ==============================================================================

@app.post("/api/requisition/inspect")
async def api_requisition_inspect(req: RequisitionRequest):
    """Inspect which analyses map to PDF form checkboxes vs 'autres demandes'."""
    return inspect_requisition_selection(
        pids=req.pids,
        site=req.site or "Tous les sites"
    )

@app.post("/api/requisition/pdf")
async def api_requisition_pdf_post(req: RequisitionRequest):
    """Generate and download the pre-filled OPTILAB PDF requisition."""
    patient_dict = req.patient_info.model_dump() if req.patient_info else {}

    # Auto-learning: save/update prescriber & nurse if credentials supplied
    if patient_dict.get("doctor_name") or patient_dict.get("doctor_license"):
        try:
            upsert_prescriber({
                "doctor_name": patient_dict.get("doctor_name", ""),
                "doctor_license": patient_dict.get("doctor_license", ""),
                "clinic_name": patient_dict.get("clinic_name", ""),
                "clinic_id": patient_dict.get("clinic_id", ""),
                "doctor_copy": patient_dict.get("doctor_copy", ""),
                "doctor_copy_license": patient_dict.get("doctor_copy_license", "")
            })
        except Exception as e:
            print(f"[app] Prescriber auto-save skipped: {e}")

    if patient_dict.get("nurse_name") or patient_dict.get("sample_location"):
        try:
            upsert_nurse({
                "nurse_name": patient_dict.get("nurse_name", ""),
                "sample_location": patient_dict.get("sample_location", "")
            })
        except Exception as e:
            print(f"[app] Nurse auto-save skipped: {e}")

    pdf_bytes = generate_filled_requisition_pdf(
        pids=req.pids,
        site=req.site or "Tous les sites",
        patient_info=patient_dict
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="requete_analyses_optilab.pdf"',
            "Content-Type": "application/pdf"
        }
    )

@app.get("/api/requisition/pdf")
async def api_requisition_pdf_get(
    pids: str = Query(..., description="Comma-separated PIDs"),
    site: Optional[str] = Query("Tous les sites")
):
    """Generate and stream the pre-filled OPTILAB PDF requisition via GET."""
    pid_list = [p.strip() for p in pids.split(",") if p.strip()]
    pdf_bytes = generate_filled_requisition_pdf(
        pids=pid_list,
        site=site or "Tous les sites",
        patient_info=None
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="requete_analyses_optilab.pdf"',
            "Content-Type": "application/pdf"
        }
    )

class BarcodeDecodeRequest(BaseModel):
    payload: Annotated[str, Field(max_length=4000)]

class BarcodeImageScanRequest(BaseModel):
    image_base64: str

@app.post("/api/ramq/decode")
async def api_decode_ramq_barcode(req: BarcodeDecodeRequest):
    """Decodes raw barcode payload (1D Code 128 / 2D PDF417) from Quebec RAMQ card."""
    res = parse_ramq_barcode_payload(req.payload)
    return res

@app.post("/api/ramq/scan_image")
async def api_scan_ramq_image(req: BarcodeImageScanRequest):
    """Scans and decodes barcode from base64 image using zxingcpp with multi-pass filters and super-resolution."""
    import base64
    import numpy as np
    import cv2
    import zxingcpp

    try:
        data_str = req.image_base64
        if "," in data_str:
            data_str = data_str.split(",", 1)[1]
        img_bytes = base64.b64decode(data_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Invalid image data"}

        h, w = img.shape[:2]

        # Multi-scale & Region candidates
        candidates = []
        candidates.append(img)

        # Central crop (matching reticle region: center 70% width, center 60% height)
        cx1, cx2 = int(w * 0.15), int(w * 0.85)
        cy1, cy2 = int(h * 0.20), int(h * 0.80)
        crop = img[cy1:cy2, cx1:cx2]
        if crop.size > 0:
            candidates.append(crop)
            # Upscaled crop (2x with Lanczos for sharp barcodes at 35cm focal distance)
            crop_2x = cv2.resize(crop, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_LANCZOS4)
            candidates.append(crop_2x)

        for cand in candidates:
            # 1. Direct scan
            res = zxingcpp.read_barcodes(cand, try_rotate=True)
            for r in res:
                if r.valid and r.text:
                    parsed = parse_ramq_barcode_payload(r.text)
                    return {"success": True, "format": str(r.format), "raw": r.text, **parsed}

            # 2. Grayscale + Sharpening (Unsharp mask to counter webcam focal blur)
            gray = cv2.cvtColor(cand, cv2.COLOR_BGR2GRAY) if len(cand.shape) == 3 else cand
            gaussian = cv2.GaussianBlur(gray, (0, 0), 2.0)
            sharpened = cv2.addWeighted(gray, 2.0, gaussian, -1.0, 0)
            res = zxingcpp.read_barcodes(sharpened, try_rotate=True)
            for r in res:
                if r.valid and r.text:
                    parsed = parse_ramq_barcode_payload(r.text)
                    return {"success": True, "format": str(r.format), "raw": r.text, **parsed}

            # 3. CLAHE (Contrast equalization for specular reflections on plastic card)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(gray)
            res = zxingcpp.read_barcodes(cl, try_rotate=True)
            for r in res:
                if r.valid and r.text:
                    parsed = parse_ramq_barcode_payload(r.text)
                    return {"success": True, "format": str(r.format), "raw": r.text, **parsed}

            # 4. Otsu & Adaptive Thresholds
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            res = zxingcpp.read_barcodes(otsu, try_rotate=True)
            for r in res:
                if r.valid and r.text:
                    parsed = parse_ramq_barcode_payload(r.text)
                    return {"success": True, "format": str(r.format), "raw": r.text, **parsed}

            # 5. Explicit 180° Inverted orientation
            rot180 = cv2.rotate(cand, cv2.ROTATE_180)
            res = zxingcpp.read_barcodes(rot180, try_rotate=True)
            for r in res:
                if r.valid and r.text:
                    parsed = parse_ramq_barcode_payload(r.text)
                    return {"success": True, "format": str(r.format), "raw": r.text, **parsed}

        return {"success": False}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    print("=" * 65)
    print("  🏥 GUSTAV - Calculateur de Tubes de Prélèvement (CHU de Québec)")
    print("  🌐 Serveur local démarré sur : http://127.0.0.1:8000")
    print("=" * 65)
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
