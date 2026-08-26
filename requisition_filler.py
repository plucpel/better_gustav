"""
OPTILAB Capitale-Nationale General Laboratory Requisition PDF Generator.
Automatically fills the official 'REQUÊTE D'ANALYSES - GÉNÉRALES - LABORATOIRE MULTIDISCIPLINAIRE'
(Version 2026-05) by ticking matching checkboxes and populating 'AUTRES ANALYSES'.
"""

import os
import io
import json
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional
from tube_calculator import load_catalog, normalize_str
from medical_dictionary import CLINICAL_PANELS, SYNONYMS_TO_PID

TEMPLATE_PDF_PATH = os.path.join(os.path.dirname(__file__), "data", "requete_analyses_generales_optilab.pdf")

# Direct mapping from Gustav catalog PIDs, aliases, and synonyms to exact PDF Form CheckBox Field Names
PID_TO_CHECKBOX = {
    # 1. BIOCHIMIE (Menthe / HepLi)
    "acuri": "ACURI",
    "alb": "ALB",
    "albu": "ALB",
    "alt": "ALT",
    "alat": "ALT",
    "sgpt": "ALT",
    "alp": "ALP",
    "pal": "ALP",
    "apob": "APOB",
    "aps": "APS",
    "psa": "APS",
    "ast": "AST",
    "asat": "AST",
    "sgot": "AST",
    "bili": "BILI",
    "bilit": "BILI",
    "ca": "CA",
    "calct": "CA",
    "co2": "CO2",
    "ck": "CK",
    "cktot": "CK",
    "crea": "CREA",
    "creat": "CREA",
    "elec": "ELEC",
    "elecx": "ELEC",
    "ethan": "ETHAN",
    "bilfe": "BILFE",
    "fer": "BILFE",
    "cff": "BILFE",
    "ferri": "FERRI",
    "ferrix": "FERRI",
    "ggt": "GGT",
    "glu": "GLU",
    "gly": "GLU",
    "hcgqt": "HCGQT",
    "ld": "LD",
    "ldh": "LD",
    "lip": "LIP",
    "lipas": "LIP",
    "lipase": "LIP",
    "mg": "MG",
    "magne": "MG",
    "phos": "PHOS",
    "crp": "CRP",
    "prlip": "PRLIP",
    "prlipx": "PRLIP",
    "clip": "PRLIP",
    "cholt": "PRLIP",
    "hdl": "PRLIP",
    "trigl": "PRLIP",
    "prot": "PROT",
    "prott": "PROT",
    "tsh": "TSH",
    "uree": "UREE",
    "bun": "UREE",
    "b12": "B12",

    # 2. GLYCÉMIES (AUTRES)
    "gluj": "GLUJ À jeun 8h",
    "glujx": "GLUJ À jeun 8h",
    "gl2p": "GL2P 2 h PC",
    "gl2px": "GL2P 2 h PC",
    "glu50": "GLU50 1h post 50 g",
    "glu50x": "GLU50 1h post 50 g",
    "hypg2": "HYPG2",
    "hype2": "HYPE2",
    "hype2x": "HYPE2",

    # 3. MÉDICAMENTS (OR / ROUGE)
    "aceta": "ACETA",
    "parac": "ACETA",
    "tylenol": "ACETA",
    "valpt": "VALPT",
    "depakene": "VALPT",
    "epival": "VALPT",
    "carba": "CARBA",
    "tegretol": "CARBA",
    "phenb": "PHENB",
    "phen": "PHEN",
    "dilantin": "PHEN",
    "salic": "SALIC",
    "aspirine": "SALIC",
    "clozn": "CLOZN",
    "cloz": "CLOZN",
    "clozaril": "CLOZN",
    "lamo": "LAMO",
    "lamictal": "LAMO",
    "lith": "LITH",
    "liery": "LIERY Lithium intra érythrocytaire",

    # 4. DROGUES D'ABUS (DE RUE) URINAIRE (CNS)
    "drode": "DRODE",
    "drodex": "DRODE",
    "cdrog": "DRODE",
    "ammed": "AMMED",
    "ammep": "AMMEP",
    "benzu": "BENZU",
    "coctu": "COCTU",
    "ectde": "ECTDE",
    "fentd": "FENTD",
    "metde": "METDE",
    "metg": "METDE",
    "opiad": "OPIAD",
    "oxyde": "OXYDE",
    "thcd": "THCD",
    "cannabis": "THCD",

    # 5. DIVERS / SÉROLOGIES / HORMONES
    "testo": "TESTO",
    "tesbi": "TESBI",
    "fsh": "FSH",
    "lh": "LH",
    "estd": "ESTD",
    "estradiol": "ESTD",
    "prol": "PROL",
    "prl": "PROL",
    "dlpro": "PROL",
    "tpo": "TPO",
    "atpo": "TPO",
    "elep": "ELEP",
    "hba1c": "HBA1C",
    "a1c": "HBA1C",
    "0immu": "0IMMU",
    "immu": "0IMMU",
    "osmol": "OSMOL",
    "osmos": "OSMOL",
    "ttrop": "TTROP",
    "tropt": "TTROP",
    "itrop": "ITROP",
    "itropx": "ITROP",
    "rsosi": "RSOSi",
    "fit": "RSOSi",

    # 6. HÉMATOLOGIE – HÉMOSTASE
    "fsc": "FSC",
    "cbc": "FSC",
    "fs": "FS",
    "fsang": "FS",
    "retic": "RETIC",
    "sedi": "SEDI",
    "vs": "SEDI",
    "ptrin": "PTRIN",
    "inr": "PTRIN",
    "rni": "PTRIN",
    "tp": "PTRIN",
    "ptt": "PTT",
    "tca": "PTT",
    "dd": "DD",
    "ddim": "DD",

    # 7. HÉPATITES
    "hbsag": "HBSAG",
    "hbsag_2": "HBSAG_2",
    "hbsac": "HBSAC",
    "ahbs": "HBSAC",
    "avhct": "AVHCT",
    "hepc": "AVHCT",
    "vham": "VHAM",
    "vhat": "VHAT",

    # 8. MICTION URINAIRE
    "anuri": "ANURI",
    "smu": "ANURI",
    "creur": "CREUR",
    "malu": "MALU",
    "malux": "MALU",
    "osmu": "OSMU",
    "hcgun": "HCGUN",
}

# Metadata descriptions of form checkboxes for UI breakdown inspection
CHECKBOX_METADATA = {
    "ACURI": {"label": "Acide urique", "category": "Biochimie (Menthe)"},
    "ALB": {"label": "Albumine", "category": "Biochimie (Menthe)"},
    "ALT": {"label": "ALT (Transaminase)", "category": "Biochimie (Menthe)"},
    "ALP": {"label": "Phosphatase alcaline", "category": "Biochimie (Menthe)"},
    "APOB": {"label": "Apolipoprotéine B (Apo B)", "category": "Biochimie (Menthe)"},
    "APS": {"label": "PSA", "category": "Biochimie (Menthe)"},
    "AST": {"label": "AST (Transaminase)", "category": "Biochimie (Menthe)"},
    "BILI": {"label": "Bilirubine", "category": "Biochimie (Menthe)"},
    "CA": {"label": "Calcium", "category": "Biochimie (Menthe)"},
    "CO2": {"label": "CO2 total", "category": "Biochimie (Menthe)"},
    "CK": {"label": "CK (Créatine - kinase)", "category": "Biochimie (Menthe)"},
    "CREA": {"label": "Créatinine", "category": "Biochimie (Menthe)"},
    "ELEC": {"label": "Électrolytes (Na, K, Cl)", "category": "Biochimie (Menthe)"},
    "ETHAN": {"label": "Éthanol", "category": "Biochimie (Menthe)"},
    "BILFE": {"label": "Bilan ferrique (FER+Transferrine+% Sat+Ferritine)", "category": "Biochimie (Menthe)"},
    "FERRI": {"label": "Ferritine", "category": "Biochimie (Menthe)"},
    "GGT": {"label": "GGT", "category": "Biochimie (Menthe)"},
    "GLU": {"label": "Glucose", "category": "Biochimie (Menthe)"},
    "HCGQT": {"label": "β-hCG quantitatif", "category": "Biochimie (Menthe)"},
    "LD": {"label": "LDH", "category": "Biochimie (Menthe)"},
    "LIP": {"label": "Lipase", "category": "Biochimie (Menthe)"},
    "MG": {"label": "Magnésium", "category": "Biochimie (Menthe)"},
    "PHOS": {"label": "Phosphore", "category": "Biochimie (Menthe)"},
    "CRP": {"label": "Protéine C réactive", "category": "Biochimie (Menthe)"},
    "PRLIP": {"label": "Bilan lipidique (CHOL + TRIG + HDL + LDL calculé)", "category": "Biochimie (Menthe)"},
    "PROT": {"label": "Protéines totales", "category": "Biochimie (Menthe)"},
    "TSH": {"label": "TSH", "category": "Biochimie (Menthe)"},
    "UREE": {"label": "Urée", "category": "Biochimie (Menthe)"},
    "B12": {"label": "Vitamine B12", "category": "Biochimie (Or)"},

    "GLUJ À jeun 8h": {"label": "Glucose à jeun (8h)", "category": "Glycémies (1ME/OR)"},
    "GL2P 2 h PC": {"label": "Glucose 2 h P.C.", "category": "Glycémies (1ME/OR)"},
    "GLU50 1h post 50 g": {"label": "Dépistage 50 g femme enceinte", "category": "Glycémies (1ME/OR)"},
    "HYPG2": {"label": "HGPO Femme enceinte (75g 0, 1h, 2h)", "category": "Glycémies (3ME/OR)"},
    "HYPE2": {"label": "HGPO Adulte (75g 0, 2h)", "category": "Glycémies (2ME/OR)"},

    "ACETA": {"label": "Acétaminophène", "category": "Médicaments (Or)"},
    "VALPT": {"label": "Acide valproïque (Dépakène, Épival)", "category": "Médicaments (Or)"},
    "CARBA": {"label": "Carbamazépine (Tégrétol)", "category": "Médicaments (Or)"},
    "PHENB": {"label": "Phénobarbital", "category": "Médicaments (Or)"},
    "PHEN": {"label": "Phénytoïne (Dilantin)", "category": "Médicaments (Or)"},
    "SALIC": {"label": "Salicylates", "category": "Médicaments (Or)"},
    "CLOZN": {"label": "Clozapine (Clozaril)", "category": "Médicaments (Rouge)"},
    "LAMO": {"label": "Lamotrigine (Lamictal)", "category": "Médicaments (Rouge)"},
    "LITH": {"label": "Lithium", "category": "Médicaments (Or)"},
    "LIERY Lithium intra érythrocytaire": {"label": "Lithium intra érythrocytaire", "category": "Médicaments (2 LAV+1 OR)"},

    "DRODE": {"label": "Dépistage drogue de rue général", "category": "Drogues urinaires (CNS)"},
    "AMMED": {"label": "Amphétamines / Métamphétamines (CHUL / JH)", "category": "Drogues urinaires (CNS)"},
    "AMMEP": {"label": "Amphétamines / Métamphétamines / Ecstasy", "category": "Drogues urinaires (CNS)"},
    "BENZU": {"label": "Benzodiazépines", "category": "Drogues urinaires (CNS)"},
    "COCTU": {"label": "Cocaïne", "category": "Drogues urinaires (CNS)"},
    "ECTDE": {"label": "Ecstasy (CHUL / JH)", "category": "Drogues urinaires (CNS)"},
    "FENTD": {"label": "Fentanyl", "category": "Drogues urinaires (CNS)"},
    "METDE": {"label": "Méthadone", "category": "Drogues urinaires (CNS)"},
    "OPIAD": {"label": "Opiacés", "category": "Drogues urinaires (CNS)"},
    "OXYDE": {"label": "Oxycodone", "category": "Drogues urinaires (CNS)"},
    "THCD": {"label": "Cannabinoïdes (THC)", "category": "Drogues urinaires (CNS)"},

    "TESTO": {"label": "Testostérone totale", "category": "Divers (Or)"},
    "TESBI": {"label": "Testostérone biodisponible", "category": "Divers (Or)"},
    "FSH": {"label": "FSH", "category": "Divers (Or)"},
    "LH": {"label": "LH", "category": "Divers (Or)"},
    "ESTD": {"label": "Oestradiol", "category": "Divers (Or)"},
    "PROL": {"label": "Prolactine", "category": "Divers (Or)"},
    "TPO": {"label": "Anticorps anti-thyroïdiens (anti-TPO)", "category": "Divers (Or)"},
    "ELEP": {"label": "Électrophorèse des protéines sériques", "category": "Divers (Or)"},
    "HBA1C": {"label": "Hémoglobine glyquée (HbA1c)", "category": "Divers (Lavande foncé)"},
    "0IMMU": {"label": "Immunoglobulines IgA, IgG, IgM", "category": "Divers (Or)"},
    "OSMOL": {"label": "Osmolalité sérique", "category": "Divers (Menthe/Or)"},
    "TTROP": {"label": "Troponine T (HEJ)", "category": "Divers (Menthe/Or)"},
    "ITROP": {"label": "Troponine I (autres centres)", "category": "Divers (Menthe)"},
    "RSOSi": {"label": "Recherche de sang occulte (RSOSi)", "category": "Divers (Trousse RSOSi)"},

    "FSC": {"label": "Formule sanguine complète (FSC)", "category": "Hématologie (Lavande)"},
    "FS": {"label": "Hb + Ht + Plaquettes", "category": "Hématologie (Lavande)"},
    "RETIC": {"label": "Réticulocytes", "category": "Hématologie (Lavande)"},
    "SEDI": {"label": "Sédimentation (VS)", "category": "Hématologie (Lavande)"},
    "PTRIN": {"label": "Temps de Quick (INR - RNI)", "category": "Hémostase (Bleu)"},
    "PTT": {"label": "Temps de céphaline activé (PTT / TCA)", "category": "Hémostase (Bleu)"},
    "DD": {"label": "D-Dimère", "category": "Hémostase (Bleu)"},

    "HBSAG": {"label": "Hépatite B (AgHBs, anti-HBc, anti-HBs)", "category": "Hépatites (Or)"},
    "HBSAG_2": {"label": "Hépatite B (dépistage grossesse)", "category": "Hépatites (Or)"},
    "HBSAC": {"label": "Anti-HBs (statut vaccinal)", "category": "Hépatites (Or)"},
    "AVHCT": {"label": "Hépatite C (Anti-HCV)", "category": "Hépatites (Or)"},
    "VHAM": {"label": "Hépatite A IgM (maladie)", "category": "Hépatites (Or)"},
    "VHAT": {"label": "Hépatite A IgG total (vaccin)", "category": "Hépatites (Or)"},

    "ANURI": {"label": "Sommaire et microscopie (SMU)", "category": "Miction Urinaire (Culot)"},
    "CREUR": {"label": "Créatinine urinaire", "category": "Miction Urinaire (CNS)"},
    "MALU": {"label": "Microalbuminurie (miction)", "category": "Miction Urinaire (CNS)"},
    "OSMU": {"label": "Osmolalité urinaire", "category": "Miction Urinaire (CNS)"},
    "HCGUN": {"label": "Test de grossesse urinaire", "category": "Miction Urinaire (CNS)"}
}

HEADER_FIELD_NAMES = {
    "ramq": "Text12",
    "dossier": "Text13",
    "site": "Text14",
    "room": "Text15",
    "patient_name": "Text16",
    "dob": "Text17",
    "clinical_info": "Text18",
    "sex": "Sexe",
    "doctor_name": "Text6",
    "doctor_license": "Text7",
    "clinic_name": "Text8",
    "clinic_id": "Text9",
    "doctor_copy": "Text10",
    "doctor_copy_license": "Text11",
    "sample_date": "Text2",
    "sample_time": "Text3",
    "nurse_name": "Text4",
    "sample_location": "Text5",
    "other_analyses": "AUTRES ANALYSES OU DEMANDES SPÉCIALES AUTRES"
}

def resolve_pids(input_pids: List[str]) -> List[str]:
    """Expands panel names and resolves synonyms to canonical catalog PIDs."""
    catalog = load_catalog()
    resolved = []
    seen = set()

    for item in input_pids:
        raw_key = item.lower().strip()
        
        # 1. Expand panel
        if raw_key in CLINICAL_PANELS:
            for p in CLINICAL_PANELS[raw_key]["pids"]:
                p_clean = p.lower().strip()
                if p_clean not in seen:
                    resolved.append(p_clean)
                    seen.add(p_clean)
            continue
            
        # 2. Check synonyms
        if raw_key in SYNONYMS_TO_PID:
            target_pid = SYNONYMS_TO_PID[raw_key].lower().strip()
            if target_pid not in seen:
                resolved.append(target_pid)
                seen.add(target_pid)
            continue

        # 3. Direct PID
        if raw_key not in seen:
            resolved.append(raw_key)
            seen.add(raw_key)

    return resolved

def inspect_requisition_selection(pids: List[str], site: str = "Tous les sites") -> Dict[str, Any]:
    """
    Inspects which analyses map to PDF form checkboxes and which will be written in 'AUTRES ANALYSES'.
    """
    catalog = load_catalog()
    resolved_pids = resolve_pids(pids)

    matched_checkboxes = []
    other_analyses = []
    checked_field_names = set()

    # Site-specific troponin adjustment: HEJ uses TTROP, other centres use ITROP
    site_is_hej = "enfant-jésus" in normalize_str(site) or "hej" in normalize_str(site)

    for pid in resolved_pids:
        # Determine analysis display name
        display_name = pid.upper()
        if pid in catalog:
            display_name = catalog[pid]["name"]

        # Check troponin site specificity
        if pid in ["itrop", "itropx", "ttrop", "tropo", "troponine"]:
            target_field = "TTROP" if site_is_hej else "ITROP"
            if target_field not in checked_field_names:
                checked_field_names.add(target_field)
                meta = CHECKBOX_METADATA.get(target_field, {"label": target_field, "category": "Divers"})
                matched_checkboxes.append({
                    "field_name": target_field,
                    "label": meta["label"],
                    "category": meta["category"],
                    "pid": pid,
                    "name": display_name
                })
            continue

        # Check if direct match in PID_TO_CHECKBOX
        checkbox_field = PID_TO_CHECKBOX.get(pid)
        
        if not checkbox_field:
            # Try synonym match
            syn_pid = SYNONYMS_TO_PID.get(pid)
            if syn_pid:
                checkbox_field = PID_TO_CHECKBOX.get(syn_pid)

        if checkbox_field:
            if checkbox_field not in checked_field_names:
                checked_field_names.add(checkbox_field)
                meta = CHECKBOX_METADATA.get(checkbox_field, {"label": checkbox_field, "category": "Général"})
                matched_checkboxes.append({
                    "field_name": checkbox_field,
                    "label": meta["label"],
                    "category": meta["category"],
                    "pid": pid,
                    "name": display_name
                })
        else:
            other_analyses.append({
                "pid": pid,
                "name": display_name
            })

    return {
        "matched_checkboxes": matched_checkboxes,
        "checked_fields": list(checked_field_names),
        "other_analyses": other_analyses,
        "total_matched": len(matched_checkboxes),
        "total_other": len(other_analyses),
        "site": site
    }

def generate_filled_requisition_pdf(
    pids: List[str],
    site: str = "Tous les sites",
    patient_info: Optional[Dict[str, Any]] = None
) -> bytes:
    """
    Generates the pre-filled OPTILAB PDF with checkboxes ticked and metadata populated.
    Returns PDF binary bytes.
    """
    if not os.path.exists(TEMPLATE_PDF_PATH):
        raise FileNotFoundError(f"Template PDF not found at {TEMPLATE_PDF_PATH}")

    inspection = inspect_requisition_selection(pids, site=site)
    checked_fields = set(inspection["checked_fields"])
    other_analyses_list = inspection["other_analyses"]

    # Open PDF document with PyMuPDF
    doc = fitz.open(TEMPLATE_PDF_PATH)
    page = doc[0]

    # Combine other analyses into a clean formatted string
    other_text = ""
    if other_analyses_list:
        other_names = [f"{item['name']} ({item['pid'].upper()})" if item['pid'].upper() not in item['name'].upper() else item['name'] for item in other_analyses_list]
        other_text = " • ".join(other_names)

    patient_dict = patient_info or {}

    # Header fields to populate
    text_values_to_set = {}
    if site and site != "Tous les sites":
        text_values_to_set[HEADER_FIELD_NAMES["site"]] = site

    if patient_dict.get("ramq"):
        text_values_to_set[HEADER_FIELD_NAMES["ramq"]] = str(patient_dict["ramq"]).strip()
    if patient_dict.get("dossier"):
        text_values_to_set[HEADER_FIELD_NAMES["dossier"]] = str(patient_dict["dossier"]).strip()
    if patient_dict.get("room"):
        text_values_to_set[HEADER_FIELD_NAMES["room"]] = str(patient_dict["room"]).strip()
    if patient_dict.get("patient_name"):
        text_values_to_set[HEADER_FIELD_NAMES["patient_name"]] = str(patient_dict["patient_name"]).strip()
    if patient_dict.get("dob"):
        text_values_to_set[HEADER_FIELD_NAMES["dob"]] = str(patient_dict["dob"]).strip()
    if patient_dict.get("clinical_info"):
        text_values_to_set[HEADER_FIELD_NAMES["clinical_info"]] = str(patient_dict["clinical_info"]).strip()

    if patient_dict.get("doctor_name"):
        text_values_to_set[HEADER_FIELD_NAMES["doctor_name"]] = str(patient_dict["doctor_name"]).strip()
    if patient_dict.get("doctor_license"):
        text_values_to_set[HEADER_FIELD_NAMES["doctor_license"]] = str(patient_dict["doctor_license"]).strip()
    if patient_dict.get("clinic_name"):
        text_values_to_set[HEADER_FIELD_NAMES["clinic_name"]] = str(patient_dict["clinic_name"]).strip()
    if patient_dict.get("clinic_id"):
        text_values_to_set[HEADER_FIELD_NAMES["clinic_id"]] = str(patient_dict["clinic_id"]).strip()
    if patient_dict.get("doctor_copy"):
        text_values_to_set[HEADER_FIELD_NAMES["doctor_copy"]] = str(patient_dict["doctor_copy"]).strip()
    if patient_dict.get("doctor_copy_license"):
        text_values_to_set[HEADER_FIELD_NAMES["doctor_copy_license"]] = str(patient_dict["doctor_copy_license"]).strip()

    if patient_dict.get("sample_date"):
        text_values_to_set[HEADER_FIELD_NAMES["sample_date"]] = str(patient_dict["sample_date"]).strip()
    if patient_dict.get("sample_time"):
        text_values_to_set[HEADER_FIELD_NAMES["sample_time"]] = str(patient_dict["sample_time"]).strip()
    if patient_dict.get("nurse_name"):
        text_values_to_set[HEADER_FIELD_NAMES["nurse_name"]] = str(patient_dict["nurse_name"]).strip()
    if patient_dict.get("sample_location"):
        text_values_to_set[HEADER_FIELD_NAMES["sample_location"]] = str(patient_dict["sample_location"]).strip()

    if other_text:
        text_values_to_set[HEADER_FIELD_NAMES["other_analyses"]] = other_text

    sex_val = patient_dict.get("sex", "").strip().upper()

    # Iterate over form widgets and update them
    for widget in page.widgets():
        fname = widget.field_name
        ftype = widget.field_type_string

        if ftype == "CheckBox":
            if fname in checked_fields:
                widget.field_value = "Yes"
                widget.update()
            else:
                widget.field_value = "Off"
                widget.update()
        elif ftype == "Text":
            if fname in text_values_to_set:
                val_str = str(text_values_to_set[fname])
                widget.field_value = val_str
                if fname == HEADER_FIELD_NAMES["other_analyses"]:
                    widget.text_fontsize = 8.5
                elif fname == HEADER_FIELD_NAMES["sample_location"]:
                    if len(val_str) > 65:
                        widget.text_fontsize = 6.2
                    elif len(val_str) > 45:
                        widget.text_fontsize = 6.8
                    else:
                        widget.text_fontsize = 7.5
                elif fname == HEADER_FIELD_NAMES["nurse_name"]:
                    if len(val_str) > 40:
                        widget.text_fontsize = 6.8
                    else:
                        widget.text_fontsize = 7.5
                else:
                    widget.text_fontsize = 8.0
                widget.update()
        elif ftype == "RadioButton" and fname == "Sexe":
            if sex_val in ["M", "F"]:
                if widget.on_state() == sex_val:
                    widget.field_value = sex_val
                    widget.update()

    # Save to memory buffer
    output_stream = io.BytesIO()
    doc.save(output_stream, garbage=3, deflate=True)
    doc.close()

    return output_stream.getvalue()
