"""
GUSTAV - Dymo Tube Label Generator (Optilab / CHU de Québec Standard).
Generates high-resolution vector PDF labels (300 DPI) for Dymo LabelWriter thermal printers (Rolls 30336 and 30334).
"""

import io
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional
from datetime import datetime

from tube_calculator import calculate_tubes, load_catalog
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

# Code 128 Pattern Table (Values 0 to 106)
CODE128_PATTERNS = [
    '212222', '222122', '222221', '121223', '121322', '131222', '122213', '122312', '132212', '221213',
    '221312', '231212', '112232', '122132', '122231', '113222', '123122', '123221', '223211', '221132',
    '221231', '213212', '223112', '312131', '311222', '321122', '321221', '312212', '322112', '322211',
    '212123', '212321', '232121', '111323', '131123', '131321', '112313', '132113', '132311', '211313',
    '231113', '231311', '112133', '112331', '132131', '113123', '113321', '133121', '313121', '211331',
    '231131', '213113', '213311', '213131', '311123', '311321', '331121', '312113', '312311', '332111',
    '314111', '221411', '431111', '111224', '111422', '121124', '121421', '141122', '141221', '112214',
    '112412', '122114', '122411', '142112', '142211', '241211', '221114', '413111', '241112', '134111',
    '111242', '121142', '121241', '114212', '124112', '124211', '411212', '421112', '421211', '212141',
    '214121', '412121', '111143', '111341', '131141', '114113', '114311', '411113', '411311', '113141',
    '114131', '311141', '411131', '211412', '211214', '211232', '2331112'
]

def encode_code128_b(text: str) -> List[int]:
    """Encodes ASCII string into Code 128 (Subset B) binary modules array."""
    clean_text = ''.join([c for c in text if 32 <= ord(c) <= 126])
    if not clean_text:
        return []
    values = [104]  # Start B
    for c in clean_text:
        values.append(ord(c) - 32)
    checksum = values[0]
    for i, v in enumerate(values[1:], 1):
        checksum += v * i
    values.append(checksum % 103)
    values.append(106)  # Stop

    modules = []
    for v in values:
        pat = CODE128_PATTERNS[v]
        is_bar = True
        for digit in pat:
            width = int(digit)
            modules.extend([1 if is_bar else 0] * width)
            is_bar = not is_bar
    return modules

def format_ramq_display(raw_ramq: Optional[str]) -> str:
    """Formats RAMQ string into standard 4-4-4 format: 'TREJ 8005 1512'."""
    if not raw_ramq:
        return ""
    clean = re.sub(r"[^A-Za-z0-9]", "", str(raw_ramq)).upper()
    if len(clean) == 12:
        return f"{clean[:4]} {clean[4:8]} {clean[8:12]}"
    return clean

def extract_primary_alert(tube: Dict[str, Any], cat_key: str) -> str:
    """Extracts high-priority alert for label badge (Sur glace, Abri lumière, Délai, Banque de sang)."""
    if cat_key == "EDTA_ROSE":
        return "⚠️ BANQUE DE SANG : INITIALES & DATE"
    
    specific_alerts = tube.get("specific_alerts", [])
    for al in specific_alerts:
        al_lower = al.lower()
        if "glace" in al_lower:
            return "🧊 SUR GLACE"
        if "lumière" in al_lower or "lumiere" in al_lower:
            return "🌑 ABRI DE LA LUMIÈRE"
        if "30 min" in al_lower or "immédiat" in al_lower or "délai" in al_lower:
            return "⏱️ DÉLAI D'ACHEMINEMENT CRITIQUE"
            
    special_inst = tube.get("special_instructions", "")
    if "glace" in special_inst.lower():
        return "🧊 SUR GLACE"
    if "lumière" in special_inst.lower() or "lumiere" in special_inst.lower():
        return "🌑 ABRI DE LA LUMIÈRE"
        
    return ""

def prepare_label_items(
    pids: List[str],
    site: str = "Tous les sites",
    is_pediatric: bool = False,
    patient_info: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Computes tubes and converts them into an ordered list of individual label payloads.
    Expands tube counts (e.g. 2 x Citrate -> 2 separate labels).
    """
    calc_res = calculate_tubes(selected_pids=pids, site=site, is_pediatric=is_pediatric)
    tubes = calc_res.get("tubes", [])
    
    pdict = patient_info or {}
    raw_ramq = str(pdict.get("ramq", "")).strip()
    ramq_clean = re.sub(r"[^A-Za-z0-9]", "", raw_ramq).upper()
    ramq_disp = format_ramq_display(raw_ramq)
    
    # Demographic extraction
    ramq_info = extract_ramq_info(raw_ramq)
    raw_dob = pdict.get("dob") or ramq_info.get("dob", "")
    formatted_dob = format_dob_str(raw_dob)
    sex = str(pdict.get("sex") or ramq_info.get("sex", "")).strip().upper()
    if sex in ["MASCULIN", "HOMME"]:
        sex = "M"
    elif sex in ["FEMININ", "FEMME"]:
        sex = "F"
        
    pname = str(pdict.get("patient_name", "")).strip()
    if not pname:
        pname = "PATIENT (NON NOMMÉ)"
    dossier = str(pdict.get("dossier", "")).strip()
    
    sample_date = str(pdict.get("sample_date", "")).strip()
    sample_time = str(pdict.get("sample_time", "")).strip()
    if not sample_date and not sample_time:
        now_dt = datetime.now()
        datetime_str = now_dt.strftime("%Y-%m-%d %H:%M")
    else:
        datetime_str = f"{sample_date} {sample_time}".strip()
        
    nurse_name = str(pdict.get("nurse_name", "")).strip()
    sample_loc = str(pdict.get("sample_location", "")).strip()
    
    total_individual_labels = 0
    expanded_items = []
    
    for t_idx, tube in enumerate(tubes, 1):
        cat_key = tube.get("category_key", "SPECIMEN_DIVERS")
        count = max(1, tube.get("tube_count", 1))
        analyses_list = [a["name"].split(" (")[0] for a in tube.get("analyses", [])]
        analyses_pids = [a["pid"].upper() for a in tube.get("analyses", [])]
        
        # Build concise test acronyms string
        if len(analyses_pids) <= 8:
            analyses_str = ", ".join(analyses_pids)
        else:
            analyses_str = ", ".join(analyses_pids[:7]) + f" (+{len(analyses_pids)-7})"
            
        cap_name = tube.get("cap_color_name", "Bouchon standard")
        max_vol = tube.get("max_volume", "")
        alert_str = extract_primary_alert(tube, cat_key)
        
        for sub_i in range(1, count + 1):
            total_individual_labels += 1
            
            # Specific label naming for blood cultures
            if cat_key == "HEMOCULTURE" and count == 2:
                bottle_type = "Aérobie (Vert/Bleu)" if sub_i == 1 else "Anaérobie (Jaune/Violet)"
                specimen_title = f"Hémoculture {sub_i}/2 ({bottle_type})"
            elif count > 1:
                specimen_title = f"{tube.get('name', 'Tube')} ({sub_i}/{count})"
            else:
                specimen_title = tube.get("name", "Tube")
                
            expanded_items.append({
                "category_key": cat_key,
                "order_step": tube.get("order_step", 99),
                "specimen_title": specimen_title,
                "cap_color_name": cap_name,
                "color_code": tube.get("color_code", "#0284C7"),
                "max_volume": max_vol,
                "analyses_str": analyses_str,
                "analyses_full_count": len(analyses_list),
                "alert_str": alert_str,
                "sub_index": sub_i,
                "sub_count": count
            })
            
    # Assign overall sequence index (e.g. "Tube 1/3", "Tube 2/3")
    final_label_payloads = []
    for seq_i, item in enumerate(expanded_items, 1):
        final_label_payloads.append({
            "sequence_index": seq_i,
            "total_sequence": total_individual_labels,
            "tube_index_str": f"Tube {seq_i}/{total_individual_labels}",
            "patient_name": pname,
            "ramq_raw": ramq_clean,
            "ramq_display": ramq_disp,
            "dob": formatted_dob,
            "sex": sex,
            "dossier": dossier,
            "time_str": datetime_str,
            "nurse_str": nurse_name,
            "location_str": sample_loc,
            **item
        })
        
    return final_label_payloads

def _draw_single_dymo_page(page: fitz.Page, label_data: Dict[str, Any], format_name: str = "30336"):
    """Renders a pixel-perfect, high-contrast 300 DPI vector label on a single PyMuPDF page."""
    cfg = LABEL_FORMATS.get(format_name, LABEL_FORMATS["30336"])
    w = cfg["width_pt"]
    h = cfg["height_pt"]
    
    # 0. Clean white background
    page.draw_rect(fitz.Rect(0, 0, w, h), color=(1, 1, 1), fill=(1, 1, 1))
    
    # 1. ZONE 1: PATIENT HEADER (Top row)
    pname = str(label_data.get("patient_name", "")).strip()[:24]
    ramq_display = label_data.get("ramq_display", "")
    
    # Left: Patient Name (Bold)
    page.insert_text(fitz.Point(4, 9.5), pname, fontname="helv", fontsize=7.2, color=(0, 0, 0))
    # Right: RAMQ Display
    if ramq_display:
        page.insert_text(fitz.Point(w - 4 - len(ramq_display) * 3.9, 9.5), ramq_display, fontname="helv", fontsize=6.8, color=(0, 0, 0))
        
    # Row 2: DOB, Sex & Chart
    dob = label_data.get("dob", "")
    sex = label_data.get("sex", "")
    dob_str = f"DDN: {dob}" if dob else ""
    sex_str = f" ({sex})" if sex else ""
    demo_left = f"{dob_str}{sex_str}".strip()
    chart = label_data.get("dossier", "")
    chart_str = f"Dos: {chart}" if chart else ""
    
    if demo_left:
        page.insert_text(fitz.Point(4, 16.5), demo_left, fontname="helv", fontsize=5.8, color=(0.1, 0.1, 0.1))
    if chart_str:
        page.insert_text(fitz.Point(w - 4 - len(chart_str) * 3.2, 16.5), chart_str, fontname="helv", fontsize=5.8, color=(0.1, 0.1, 0.1))
        
    # Hairline divider
    page.draw_line(fitz.Point(4, 18.5), fitz.Point(w - 4, 18.5), color=(0.7, 0.7, 0.7), width=0.4)
    
    # 2. ZONE 2: CODE 128 BARCODE (RAMQ)
    ramq_raw = label_data.get("ramq_raw", "")
    if ramq_raw:
        mods = encode_code128_b(ramq_raw)
        if mods:
            mod_w = min(0.68, (w - 20) / len(mods))
            total_bw = len(mods) * mod_w
            bx_start = (w - total_bw) / 2.0
            by_top = 20.5
            bh = 11.5
            
            i = 0
            while i < len(mods):
                if mods[i] == 1:
                    start_i = i
                    while i < len(mods) and mods[i] == 1:
                        i += 1
                    end_i = i
                    r = fitz.Rect(bx_start + start_i * mod_w, by_top, bx_start + end_i * mod_w, by_top + bh)
                    page.draw_rect(r, color=None, fill=(0, 0, 0))
                else:
                    i += 1
                    
            # Text under barcode
            btext = ramq_raw
            tw = len(btext) * 3.2
            page.insert_text(fitz.Point((w - tw) / 2.0, by_top + bh + 4.8), btext, fontname="helv", fontsize=5.0, color=(0, 0, 0))
    else:
        # Fallback if no RAMQ: print clear notice
        page.insert_text(fitz.Point(w / 2.0 - 30, 28), "[ AUCUN CODE RAMQ ]", fontname="helv", fontsize=5.5, color=(0.4, 0.4, 0.4))
        
    # 3. ZONE 3: TUBE & SPECIMEN IDENTIFICATION
    seq_str = label_data.get("tube_index_str", "Tube 1/1")
    cap_info = label_data.get("cap_color_name", "")
    max_vol = label_data.get("max_volume", "")
    
    tube_left = f"{seq_str} • {cap_info}"[:32]
    page.insert_text(fitz.Point(4, 43.5), tube_left, fontname="helv", fontsize=6.2, color=(0, 0, 0))
    
    if max_vol and "mL" in max_vol:
        vol_clean = max_vol.split("par")[0].strip()
        page.insert_text(fitz.Point(w - 4 - len(vol_clean) * 3.2, 43.5), vol_clean, fontname="helv", fontsize=5.8, color=(0.2, 0.2, 0.2))
        
    # Analyses list line
    analyses_str = f"Analyses: {label_data.get('analyses_str', '')}"
    if len(analyses_str) > 42:
        analyses_str = analyses_str[:40] + "..."
    page.insert_text(fitz.Point(4, 51.5), analyses_str, fontname="helv", fontsize=5.6, color=(0.1, 0.1, 0.1))
    
    # 4. ZONE 4: FOOTER (Traceability & Critical Alert Badge)
    alert = label_data.get("alert_str", "")
    time_s = label_data.get("time_str", "")
    nurse_s = label_data.get("nurse_str", "")
    
    if alert:
        # Draw high-contrast solid black badge
        alert_text = alert[:38]
        alert_w = min(w - 8, len(alert_text) * 4.2 + 8)
        page.draw_rect(fitz.Rect(4, 55.5, 4 + alert_w, 67.5), color=None, fill=(0, 0, 0))
        page.insert_text(fitz.Point(8, 64.0), alert_text, fontname="helv", fontsize=5.6, color=(1, 1, 1))
        if time_s:
            page.insert_text(fitz.Point(w - 4 - len(time_s) * 3.0, 64.0), time_s, fontname="helv", fontsize=5.0, color=(0.2, 0.2, 0.2))
    else:
        trace_parts = [p for p in [time_s, nurse_s] if p]
        trace_str = " • ".join(trace_parts)[:42]
        page.insert_text(fitz.Point(4, 64.0), trace_str, fontname="helv", fontsize=5.2, color=(0.3, 0.3, 0.3))

def generate_tube_labels_pdf(
    pids: List[str],
    site: str = "Tous les sites",
    is_pediatric: bool = False,
    patient_info: Optional[Dict[str, Any]] = None,
    format_name: str = "30336"
) -> bytes:
    """
    Generates a multi-page vector PDF where each page is sized to the exact Dymo label format.
    """
    label_items = prepare_label_items(
        pids=pids,
        site=site,
        is_pediatric=is_pediatric,
        patient_info=patient_info
    )
    
    cfg = LABEL_FORMATS.get(format_name, LABEL_FORMATS["30336"])
    w = cfg["width_pt"]
    h = cfg["height_pt"]
    
    doc = fitz.open()
    
    if not label_items:
        # Empty fallback single label
        page = doc.new_page(width=w, height=h)
        page.insert_text(fitz.Point(w / 2.0 - 45, h / 2.0), "Aucun tube requis", fontname="helv", fontsize=8.0)
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
        return "Etiquettes_Tubes_Dymo_30336.pdf"
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
