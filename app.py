import os
import uvicorn
from fastapi import FastAPI, Query, Path, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated

from tube_calculator import search_analyses, calculate_tubes, load_catalog
from medical_dictionary import CLINICAL_PANELS
from requisition_filler import generate_filled_requisition_pdf, inspect_requisition_selection

app = FastAPI(
    title="Gustav - Calculateur de Tubes Sanguins (CHU de Québec)",
    version="1.0.0",
    docs_url=None, # Disable Swagger UI in production
    redoc_url=None
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")

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
async def serve_index():
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

if __name__ == "__main__":
    print("=" * 65)
    print("  🏥 GUSTAV - Calculateur de Tubes de Prélèvement (CHU de Québec)")
    print("  🌐 Serveur local démarré sur : http://127.0.0.1:8000")
    print("=" * 65)
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
