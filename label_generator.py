"""
GUSTAV - Dymo Tube Label Generator (Optilab / CHU de Québec Standard).
Generates high-contrast, clean 3-line vector PDF labels for Dymo LabelWriter thermal printers (Rolls 30336 and 30334).
Format per label:
Line 1: Stephan Gilbert (GHA-2568)  [Bold]
Line 2: GILS 6607 0514              [Regular]
Line 3: 5 juillet 1966 , M          [Regular]
"""

import io
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional
from datetime import datetime

from tube_calculator import calculate_tubes
from requisition_filler import format_dob_str, extract_ramq_info

# Standard Dymo Roll Dimensions (in Points: 72 points = 1 inch = 25.4 mm)
LABEL_FORMATS = {
    "30336": {
        "name": "Dymo 30336 (1\" x 2-1/8\") - Standard Tubes",
        "width_mm": 54.0,
        "height_mm": 25.4,
        "width_pt": 54.0 * 72.0 / 25.4,   # 153.07 pt
        "height_pt": 25.4 * 72.0 / 25.4,  # 72.0 pt
    },
    "30334": {
        "name": "Dymo 30334 (1-1/4\" x 2-1/4\") - Polyvalent / Urines / Selles",
        "width_mm": 57.15,
        "height_mm": 31.75,
        "width_pt": 57.15 * 72.0 / 25.4,  # 162.0 pt
        "height_pt": 31.75 * 72.0 / 25.4, # 90.0 pt
    }
}

def format_ramq_display(raw_ramq: Optional[str]) -> str:
    """Formats RAMQ string into standard 4-4-4 format: 'GILS 6607 0514'."""
    if not raw_ramq:
        return ""
    clean = re.sub(r"[^A-Za-z0-9]", "", str(raw_ramq)).upper()
    if len(clean) == 12:
        return f"{clean[:4]} {clean[4:8]} {clean[8:12]}"
    return clean

def format_french_dob(dob_str: Optional[str]) -> str:
    """
    Formats ISO date (YYYY-MM-DD) into French text format:
    '1966-07-05' -> '5 juillet 1966'
    '1966-02-19' -> '19 février 1966'
    """
    if not dob_str:
        return ""
    parts = str(dob_str).strip().split("-")
    if len(parts) != 3:
        return str(dob_str)
    year, month, day = parts
    try:
        d = int(day)
        m = int(month)
        y = int(year)
    except ValueError:
        return str(dob_str)
    
    months_fr = [
        "", "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"
    ]
    if 1 <= m <= 12:
        return f"{d} {months_fr[m]} {y}"
    return str(dob_str)

def format_patient_line_1(pname: str, dossier: str) -> str:
    """
    Formats first line: 'Stephan Gilbert (GHA-2568)' or 'Bruno Giguère ()'.
    Converts 'Nom, Prénom' to 'Prénom Nom'.
    """
    pname = pname.strip()
    if "," in pname:
        parts = [p.strip() for p in pname.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            formatted_name = f"{parts[1]} {parts[0]}"
        else:
            formatted_name = pname
    else:
        formatted_name = pname
        
    dos_clean = str(dossier or "").strip()
    return f"{formatted_name} ({dos_clean})"

def prepare_label_items(
    pids: List[str],
    site: str = "Tous les sites",
    is_pediatric: bool = False,
    patient_info: Optional[Dict[str, Any]] = None,
    custom_quantity: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Computes tubes and converts them into an ordered list of individual label payloads.
    Generates one label per tube calculated (or custom_quantity if provided).
    """
    calc_res = calculate_tubes(selected_pids=pids, site=site, is_pediatric=is_pediatric)
    tubes = calc_res.get("tubes", [])
    
    total_tubes = sum(max(1, t.get("tube_count", 1)) for t in tubes)
    if custom_quantity and custom_quantity > 0:
        label_count = custom_quantity
    else:
        label_count = max(1, total_tubes)
    
    pdict = patient_info or {}
    raw_ramq = str(pdict.get("ramq", "")).strip()
    ramq_clean = re.sub(r"[^A-Za-z0-9]", "", raw_ramq).upper()
    ramq_disp = format_ramq_display(raw_ramq)
    
    # Demographic extraction
    ramq_info = extract_ramq_info(raw_ramq)
    raw_dob = pdict.get("dob") or ramq_info.get("dob", "")
    formatted_dob = format_dob_str(raw_dob)
    french_dob = format_french_dob(raw_dob)
    
    sex = str(pdict.get("sex") or ramq_info.get("sex", "")).strip().upper()
    if sex in ["MASCULIN", "HOMME"]:
        sex = "M"
    elif sex in ["FEMININ", "FEMME"]:
        sex = "F"
        
    pname = str(pdict.get("patient_name", "")).strip()
    if not pname:
        nom = str(pdict.get("nom", "")).strip()
        prenom = str(pdict.get("prenom", "")).strip()
        if nom and prenom:
            pname = f"{prenom} {nom}"
        elif nom:
            pname = nom
        elif prenom:
            pname = prenom
        elif pdict.get("nom_prenom"):
            pname = str(pdict.get("nom_prenom")).strip()
        else:
            pname = "Patient"
    dossier = str(pdict.get("dossier", "")).strip()
    
    line1 = format_patient_line_1(pname, dossier)
    line2 = ramq_disp
    
    line3_parts = []
    if french_dob:
        line3_parts.append(french_dob)
    if sex:
        line3_parts.append(f", {sex}")
    line3 = " ".join(line3_parts).strip()
    
    final_labels = []
    for seq_i in range(1, label_count + 1):
        final_labels.append({
            "sequence_index": seq_i,
            "total_sequence": label_count,
            "patient_name": pname,
            "dossier": dossier,
            "ramq_raw": ramq_clean,
            "ramq_display": ramq_disp,
            "dob": formatted_dob,
            "french_dob": french_dob,
            "sex": sex,
            "line1": line1,
            "line2": line2,
            "line3": line3
        })
        
    return final_labels

def _draw_single_dymo_page(page: fitz.Page, label_data: Dict[str, Any], format_name: str = "30336"):
    """
    Renders the exact 3-line patient label matching the phlebotomist standard:
    Line 1: Stephan Gilbert (GHA-2568)  [Bold 8.5pt]
    Line 2: GILS 6607 0514              [Regular 8.5pt]
    Line 3: 5 juillet 1966 , M          [Regular 8.5pt]
    """
    cfg = LABEL_FORMATS.get(format_name, LABEL_FORMATS["30336"])
    w = cfg["width_pt"]
    h = cfg["height_pt"]
    
    # 0. Clean white background
    page.draw_rect(fitz.Rect(0, 0, w, h), color=(1, 1, 1), fill=(1, 1, 1))
    
    # 1. Line 1: Name (Dossier)
    line1 = label_data.get("line1")
    if not line1:
        pname = str(label_data.get("patient_name", "")).strip()
        dossier = str(label_data.get("dossier", "")).strip()
        line1 = format_patient_line_1(pname, dossier)
    
    # 2. Line 2: RAMQ (4-4-4)
    line2 = label_data.get("line2")
    if not line2:
        line2 = label_data.get("ramq_display") or label_data.get("ramq_raw", "")
        
    # 3. Line 3: French Date of Birth + Sex
    line3 = label_data.get("line3")
    if not line3:
        raw_dob = label_data.get("dob", "")
        french_dob = format_french_dob(raw_dob)
        sex = str(label_data.get("sex", "")).strip().upper()
        if sex in ["MASCULIN", "HOMME"]:
            sex = "M"
        elif sex in ["FEMININ", "FEMME"]:
            sex = "F"
        line3_parts = []
        if french_dob:
            line3_parts.append(french_dob)
        if sex:
            line3_parts.append(f", {sex}")
        line3 = " ".join(line3_parts).strip()
        
    # Coordinate layout (aligned with Dymo 30336 margin)
    # Left margin: 10 pt
    # Line 1: y = 22 pt, Helvetica-Bold 8.5 pt
    # Line 2: y = 37 pt, Helvetica-Regular 8.5 pt
    # Line 3: y = 51 pt, Helvetica-Regular 8.5 pt
    page.insert_text(fitz.Point(10, 22), line1, fontname="hebo", fontsize=8.5, color=(0, 0, 0))
    if line2:
        page.insert_text(fitz.Point(10, 37), line2, fontname="helv", fontsize=8.5, color=(0, 0, 0))
    if line3:
        page.insert_text(fitz.Point(10, 51), line3, fontname="helv", fontsize=8.5, color=(0, 0, 0))

def generate_tube_labels_pdf(
    pids: List[str],
    site: str = "Tous les sites",
    is_pediatric: bool = False,
    patient_info: Optional[Dict[str, Any]] = None,
    format_name: str = "30336",
    custom_quantity: Optional[int] = None
) -> bytes:
    """
    Generates a multi-page vector PDF where each page is sized to the exact Dymo label format (54x25.4mm).
    """
    label_items = prepare_label_items(
        pids=pids,
        site=site,
        is_pediatric=is_pediatric,
        patient_info=patient_info,
        custom_quantity=custom_quantity
    )
    
    cfg = LABEL_FORMATS.get(format_name, LABEL_FORMATS["30336"])
    w = cfg["width_pt"]
    h = cfg["height_pt"]
    
    doc = fitz.open()
    
    if not label_items:
        # Fallback single label
        page = doc.new_page(width=w, height=h)
        page.insert_text(fitz.Point(10, 22), "Patient ()", fontname="hebo", fontsize=8.5)
    else:
        for item in label_items:
            page = doc.new_page(width=w, height=h)
            _draw_single_dymo_page(page, item, format_name=format_name)
            
    output_stream = io.BytesIO()
    doc.save(output_stream, garbage=3, deflate=True)
    doc.close()
    
    return output_stream.getvalue()

def format_labels_pdf_filename(patient_info: Optional[Dict[str, Any]] = None) -> str:
    """Constructs filename for downloaded Dymo labels PDF."""
    if not patient_info:
        return "Etiquettes_Dymo_30336.pdf"
    pname = str(patient_info.get("patient_name") or "").strip()
    ramq = str(patient_info.get("ramq") or "").strip()
    parts = ["Etiquettes"]
    if pname:
        parts.append(pname)
    if ramq:
        parts.append(ramq)
    base_name = " - ".join(parts)
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', base_name).strip()
    return f"{safe_name}.pdf"
