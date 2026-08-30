import os
import hmac
import hashlib
import secrets
import urllib.parse
import uvicorn
from fastapi import FastAPI, Query, Path, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated, Dict, Any

from tube_calculator import search_analyses, calculate_tubes, load_catalog
from medical_dictionary import CLINICAL_PANELS
from requisition_filler import (
    generate_filled_requisition_pdf,
    format_requisition_pdf_filename,
    inspect_requisition_selection,
    parse_ramq_barcode_payload
)
from label_generator import (
    generate_tube_labels_pdf,
    prepare_label_items,
    format_labels_pdf_filename,
    LABEL_FORMATS
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

import time

# Security & Authentication Configuration
GUSTAV_PIN = os.getenv("GUSTAV_PIN", "415263")
GUSTAV_SECRET_KEY = os.getenv("GUSTAV_SECRET_KEY", secrets.token_hex(32))
GUSTAV_EXTENSION_SECRET = os.getenv("GUSTAV_EXTENSION_SECRET", "gustav_ext_secret_chatterbox_2026")
COOKIE_NAME = "gustav_session"

# Ephemeral launch tokens storage (token -> { "payload": dict, "created_at": float })
LAUNCH_TOKENS: Dict[str, Dict[str, Any]] = {}
LAUNCH_TOKEN_TTL_SECONDS = 60.0

def purge_expired_launch_tokens():
    now = time.time()
    expired = [k for k, v in LAUNCH_TOKENS.items() if now - v.get("created_at", 0) > LAUNCH_TOKEN_TTL_SECONDS]
    for k in expired:
        LAUNCH_TOKENS.pop(k, None)

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
    # Intercept protected API endpoints (except /api/auth/*, /api/context/*, and /api/extension/download)
    path = request.url.path
    if path.startswith("/api/") and not (
        path.startswith("/api/auth/") or 
        path.startswith("/api/context/") or 
        path == "/api/extension/download"
    ):
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

class ContextLaunchRequest(BaseModel):
    secret: Optional[str] = ""
    extension_secret: Optional[str] = ""
    patient_name: Optional[str] = ""
    nom: Optional[str] = ""
    prenom: Optional[str] = ""
    ramq: Optional[str] = ""
    dob: Optional[str] = ""
    sex: Optional[str] = ""
    dossier: Optional[str] = ""
    medesync_id: Optional[Any] = ""
    doctor_license: Optional[str] = ""
    doctor_name: Optional[str] = ""
    prescriber_name: Optional[str] = ""
    nurse_name: Optional[str] = ""
    nurse_license: Optional[str] = ""
    preleveur_name: Optional[str] = ""
    site: Optional[str] = ""
    pids: Optional[List[str]] = []
    clinical_info: Optional[str] = ""

class ContextConsumeRequest(BaseModel):
    launch_token: str

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

@app.post("/api/context/launch")
async def api_context_launch(req: ContextLaunchRequest, request: Request):
    """
    Reçoit le contexte patient depuis l'extension Chrome sécurisée par clé secrète.
    Génère un jeton éphémère (60s) à usage unique.
    """
    secret_candidate = (
        request.headers.get("X-Gustav-Secret") or 
        request.headers.get("x-gustav-secret") or 
        req.secret or 
        req.extension_secret
    )
    if GUSTAV_EXTENSION_SECRET:
        if not secret_candidate or not secrets.compare_digest(secret_candidate.strip(), GUSTAV_EXTENSION_SECRET):
            raise HTTPException(status_code=401, detail="Clé d'extension non autorisée")

    purge_expired_launch_tokens()

    token = secrets.token_urlsafe(32)
    LAUNCH_TOKENS[token] = {
        "payload": req.model_dump(),
        "created_at": time.time()
    }

    return {
        "status": "success",
        "launch_token": token,
        "launch_url": f"/?launch={token}"
    }

@app.post("/api/context/consume")
async def api_context_consume(req: ContextConsumeRequest, response: Response):
    """
    Consomme le jeton éphémère, accorde la session (Bypass du PIN),
    détruit immédiatement le jeton et retourne le contexte patient.
    """
    purge_expired_launch_tokens()

    token = req.launch_token.strip()
    if not token or token not in LAUNCH_TOKENS:
        raise HTTPException(status_code=404, detail="Jeton de lancement invalide ou expiré")

    token_data = LAUNCH_TOKENS.pop(token)  # Single use strict destruction
    now = time.time()
    if now - token_data.get("created_at", 0) > LAUNCH_TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=410, detail="Jeton de lancement expiré")

    # Émettre le cookie de session authentifié (Bypass instantané du PIN)
    session_token = generate_session_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax"
    )

    return {
        "status": "success",
        "authenticated": True,
        "patient_info": token_data.get("payload", {})
    }

import zipfile
import io

@app.get("/api/extension/download")
async def api_download_extension():
    """Package the extension/ directory into a zip archive for clinic installation."""
    extension_dir = os.path.join(os.path.dirname(__file__), "extension")
    if not os.path.exists(extension_dir):
        raise HTTPException(status_code=404, detail="Dossier d'extension introuvable")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(extension_dir):
            for file in files:
                if file.startswith("."):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, extension_dir)
                zip_file.write(file_path, arcname)

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=gustav-medesync-extension.zip"
        }
    )

@app.get("/api/extension/info")
async def api_extension_info(request: Request):
    """Fournir l'URL et la clé secrète configurée pour l'extension."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "server_url": base_url,
        "extension_secret": GUSTAV_EXTENSION_SECRET
    }

class CalculateRequest(BaseModel):
    pids: List[Annotated[str, Field(max_length=64)]] = Field(..., max_length=100)
    site: Optional[Annotated[str, Field(max_length=120)]] = "Tous les sites"
    is_pediatric: Optional[bool] = False

class PatientInfo(BaseModel):
    ramq: Optional[Annotated[str, Field(max_length=30)]] = ""
    dossier: Optional[Annotated[str, Field(max_length=30)]] = ""
    room: Optional[Annotated[str, Field(max_length=30)]] = ""
    patient_name: Optional[Annotated[str, Field(max_length=100)]] = ""
    nom: Optional[Annotated[str, Field(max_length=50)]] = ""
    prenom: Optional[Annotated[str, Field(max_length=50)]] = ""
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
async def serve_index(request: Request, launch: Optional[str] = None):
    # If a valid single-use launch token is provided, authenticate immediately and serve main app
    if launch:
        token = launch.strip()
        if token in LAUNCH_TOKENS:
            token_data = LAUNCH_TOKENS.get(token, {})
            now = time.time()
            if now - token_data.get("created_at", 0) <= LAUNCH_TOKEN_TTL_SECONDS:
                session_token = generate_session_token()
                if os.path.exists(INDEX_HTML):
                    with open(INDEX_HTML, "r", encoding="utf-8") as f:
                        resp = HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
                        resp.set_cookie(
                            key=COOKIE_NAME,
                            value=session_token,
                            httponly=True,
                            samesite="lax"
                        )
                        return resp

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
    bulk_import_prescribers,
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

@app.post("/api/prescribers/bulk")
async def api_bulk_import_prescribers(items: List[Dict[str, Any]]):
    """High-performance bulk import of multiple prescribers in a single atomic operation."""
    return bulk_import_prescribers(items)

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
    filename = format_requisition_pdf_filename(patient_dict)
    ascii_safe_name = filename.encode("ascii", "ignore").decode("ascii").strip() or "Requete_Optilab.pdf"
    encoded_filename = urllib.parse.quote(filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{ascii_safe_name}"; filename*=UTF-8\'\'{encoded_filename}',
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
            "Content-Disposition": 'inline; filename="Requete_Optilab.pdf"; filename*=UTF-8\'\'Requete_Optilab.pdf',
            "Content-Type": "application/pdf"
        }
    )

# ==============================================================================
# DYMO TUBE LABELS ENDPOINTS
# ==============================================================================

class LabelsRequest(BaseModel):
    pids: List[Annotated[str, Field(max_length=64)]] = Field(..., max_length=100)
    site: Optional[Annotated[str, Field(max_length=120)]] = "Tous les sites"
    is_pediatric: Optional[bool] = False
    format: Optional[Annotated[str, Field(max_length=20)]] = "30336"
    quantity: Optional[int] = None
    patient_info: Optional[PatientInfo] = None

@app.post("/api/labels/preview")
async def api_labels_preview(req: LabelsRequest):
    """Returns structured label metadata for interactive web rendering and Dymo preview."""
    patient_dict = req.patient_info.model_dump() if req.patient_info else {}
    format_key = req.format if req.format in LABEL_FORMATS else "30336"
    labels = prepare_label_items(
        pids=req.pids,
        site=req.site or "Tous les sites",
        is_pediatric=bool(req.is_pediatric),
        patient_info=patient_dict,
        custom_quantity=req.quantity
    )
    return {
        "status": "success",
        "total_labels": len(labels),
        "format": LABEL_FORMATS[format_key],
        "format_key": format_key,
        "labels": labels
    }

@app.post("/api/labels/pdf")
async def api_labels_pdf_post(req: LabelsRequest):
    """Generate and stream the high-resolution vector PDF for Dymo thermal printers."""
    patient_dict = req.patient_info.model_dump() if req.patient_info else {}
    format_key = req.format if req.format in LABEL_FORMATS else "30336"
    
    # Auto-learning: save/update prescriber & nurse if credentials supplied
    if patient_dict.get("nurse_name") or patient_dict.get("sample_location"):
        try:
            upsert_nurse({
                "nurse_name": patient_dict.get("nurse_name", ""),
                "sample_location": patient_dict.get("sample_location", "")
            })
        except Exception as e:
            print(f"[app] Nurse auto-save skipped: {e}")

    pdf_bytes = generate_tube_labels_pdf(
        pids=req.pids,
        site=req.site or "Tous les sites",
        is_pediatric=bool(req.is_pediatric),
        patient_info=patient_dict,
        format_name=format_key,
        custom_quantity=req.quantity
    )
    filename = format_labels_pdf_filename(patient_dict)
    ascii_safe_name = filename.encode("ascii", "ignore").decode("ascii").strip() or "Etiquettes_Dymo_30336.pdf"
    encoded_filename = urllib.parse.quote(filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{ascii_safe_name}"; filename*=UTF-8\'\'{encoded_filename}',
            "Content-Type": "application/pdf"
        }
    )

@app.get("/api/labels/pdf")
async def api_labels_pdf_get(
    pids: str = Query(..., description="Comma-separated PIDs"),
    site: Optional[str] = Query("Tous les sites"),
    is_pediatric: Optional[bool] = Query(False),
    format: Optional[str] = Query("30336")
):
    """Generate and stream Dymo tube labels PDF via GET."""
    pid_list = [p.strip() for p in pids.split(",") if p.strip()]
    format_key = format if format in LABEL_FORMATS else "30336"
    pdf_bytes = generate_tube_labels_pdf(
        pids=pid_list,
        site=site or "Tous les sites",
        is_pediatric=bool(is_pediatric),
        patient_info=None,
        format_name=format_key
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="Etiquettes_Dymo_30336.pdf"; filename*=UTF-8\'\'Etiquettes_Dymo_30336.pdf',
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
