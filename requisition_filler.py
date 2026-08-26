"""
OPTILAB Capitale-Nationale Multi-Requisition PDF Generator.
Supports all 4 official CHU de Québec / Optilab requisition forms:
1. Requête d'analyses - Générales - Laboratoire Multidisciplinaire (Version 2026-05)
2. Requête d'analyses - Spécialisées - Laboratoire Multidisciplinaire (Version 2026-03)
3. Requête d'analyses - Microbiologie (Version 2026-02)
4. Requête d'analyses - Spécialisées Microbiologie – Biologie Moléculaire (Version 2026-02)
"""

import os
import io
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Set
from tube_calculator import load_catalog, normalize_str
from medical_dictionary import CLINICAL_PANELS, SYNONYMS_TO_PID

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ==============================================================================
# FORM DEFINITIONS & TEMPLATES
# ==============================================================================

REQUISITION_FORMS = {
    "general": {
        "id": "general",
        "title": "Requête Générale (Biochimie, Hématologie, Miction)",
        "pdf_path": os.path.join(DATA_DIR, "requete_analyses_generales_optilab.pdf"),
        "headers": {
            "sample_date": "Text2",
            "sample_time": "Text3",
            "nurse_name": "Text4",
            "sample_location": "Text5",
            "doctor_name": "Text6",
            "doctor_license": "Text7",
            "clinic_name": "Text8",
            "clinic_id": "Text9",
            "doctor_copy": "Text10",
            "doctor_copy_license": "Text11",
            "ramq": "Text12",
            "dossier": "Text13",
            "site": "Text14",
            "room": "Text15",
            "patient_name": "Text16",
            "dob": "Text17",
            "clinical_info": "Text18",
            "sex": "Sexe",
            "other_analyses": "AUTRES ANALYSES OU DEMANDES SPÉCIALES AUTRES"
        },
        "checkboxes": {
            # 1. BIOCHIMIE
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
            "prlip": "PRLIP",
            "tsh": "TSH",
            "uree": "UREE",
            "bun": "UREE",
            "urea": "UREE",
            "b12": "B12",
            "vitb12": "B12",

            # 2. SUIVI PHARMACOLOGIQUE / TOXICOLOGIE
            "lithi": "LITH",
            "lith": "LITH",
            "carba": "CARBA",
            "lamo": "LAMO",
            "valpt": "VALPT",
            "phen": "PHEN",
            "phenb": "PHENB",
            "salic": "SALIC",
            "aceta": "ACETA",
            "clozn": "CLOZN",

            # 3. PROTÉINES / HORMONES / IMMUNO
            "crp": "CRP",
            "0immu": "0IMMU",
            "immu": "0IMMU",
            "prot": "PROT",
            "tpo": "TPO",
            "fsh": "FSH",
            "lh": "LH",
            "prol": "PROL",
            "testo": "TESTO",
            "tesbi": "TESBI",
            "estd": "ESTD",

            # 4. DIVERS
            "hba1c": "HBA1C",
            "a1c": "HBA1C",
            "osmol": "OSMOL",
            "osmos": "OSMOL",
            "ttrop": "TTROP",
            "tropt": "TTROP",
            "itrop": "ITROP",
            "itropx": "ITROP",
            "rsosi": "RSOSi",
            "fit": "RSOSi",

            # 5. HÉMATOLOGIE – HÉMOSTASE
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

            # 6. HÉPATITES
            "hbsag": "HBSAG",
            "hbsag_2": "HBSAG_2",
            "hbsac": "HBSAC",
            "ahbs": "HBSAC",
            "avhct": "AVHCT",
            "hepc": "AVHCT",
            "vham": "VHAM",
            "vhat": "VHAT",

            # 7. MICTION URINAIRE
            "anuri": "ANURI",
            "smu": "ANURI",
            "smuc": "ANURI",
            "elep": "ELEP",
            "creur": "CREUR",
            "osmu": "OSMU",
            "hcgun": "HCGUN",
            "pgu": "HCGUN"
        }
    },

    "spec_multi": {
        "id": "spec_multi",
        "title": "Requête Spécialisée (Laboratoire Multidisciplinaire)",
        "pdf_path": os.path.join(DATA_DIR, "requete_specialisees_multidisciplinaire.pdf"),
        "headers": {
            "sample_date": "Text23",
            "sample_time": "Text24",
            "nurse_name": "Text25",
            "sample_location": "Text26",
            "doctor_name": "Text27",
            "doctor_license": "Text28",
            "clinic_name": "Text29",
            "clinic_id": "Text30",
            "doctor_copy": "Text31",
            "doctor_copy_license": "Text32",
            "patient_name": "Text33",
            "dob": "Text34",
            "ramq": "Text35",
            "clinical_info": "Text37",
            "sex": "Sexe",
            "other_analyses": "AUTRES ANALYSES OU DEMANDES SPÉCIALES"
        },
        "checkboxes": {
            # Gaz sanguins
            "gazar": "GAZAR",
            "gaaco": "GAACO",
            "gazc": "GAZC",
            "gacco": "GACCO",
            "gazve": "GAZVE",
            "gavco": "GAVCO",
            "caion": "CAION",
            # Divers
            "homo": "HOMO Glace",
            "bcaro": "BCARO Noiceur",
            "folat": "FOLAT",
            "retin": "RETIN Noiceur",
            "vite": "VITE Noiceur",
            "vitc": "VITC Glace",
            # Immunologie
            "fiac": "FIAC",
            "ana": "ANA",
            "aatgl": "AATGL",
            "c34sp": "C34SP",
            "c3": "C34SP",
            "c4": "C34SP",
            "ra": "RA",
            "ac50": "AC50",
            "9c1i": "9C1i",
            # Sérologie / Maladies infectieuses
            "cmvig": "CMVIG",
            "cmvim": "CMVIM",
            "helig": "HELIG",
            "hs12g": "HS12G",
            "aso": "ASO",
            "mono": "MONO",
            "syp": "SYP",
            "parvg": "PARVG",
            "parvm": "PARVM",
            "vzvg": "VZVG",
            "vzvm": "VZVM",
            "oreg": "OREG",
            "rougg": "ROUGG",
            "rubeo": "RUBEO",
            "rubem": "RUBEM",
            "toxg": "TOXG",
            "toxm": "TOXM",
            # Accident de travail
            "acc_travail": "Accident de travail  contact avec liquide biologique HORSCHU",
            # Hémostase spécialisée
            "fii": "FII",
            "fv": "FV",
            "fvii": "FVII",
            "fx": "FX",
            "f8g": "F8G",
            "fix": "FIX",
            "fxi": "FXI",
            "fxii": "FXII",
            "cargm": "CARGM",
            "b2gp": "B2GP",
            "anlup": "ANLUP",
            "fvw": "FVW",
            "fxiii": "FXIII",
            "atac": "ATAC",
            "pros": "PROS",
            "proc": "PROC",
            "dosan": "DOSAN Dosage antiXa",
            "axahb": "DOSAN Dosage antiXa",
            "anpch": "ANPCH",
            "plach": "PLACH",
            "cryof": "CRYOF",
            # Urines 24h
            "catuc": "CATUC",
            "clcra": "CLCRA",
            "creuc": "CREUC",
            "eleuc": "ELEUC",
            "mapuc": "MAPUC",
            "osmuc": "OSMUC",
            "mtnuc": "MTNUC",
            "prtuc": "PRTUC"
        }
    },

    "micro_gen": {
        "id": "micro_gen",
        "title": "Requête Microbiologie Générale",
        "pdf_path": os.path.join(DATA_DIR, "requete_microbiologie.pdf"),
        "headers": {
            "sample_date": "Text220",
            "sample_time": "Text221",
            "nurse_name": "Text222",
            "sample_location": "Text223",
            "doctor_name": "Text224",
            "doctor_license": "Text225",
            "clinic_name": "Text226",
            "clinic_id": "Text227",
            "doctor_copy": "Text228",
            "doctor_copy_license": "Text229",
            "patient_name": "Text230",
            "dob": "Text231",
            "ramq": "Text232",
            "clinical_info": "Text233",
            "sex": "Sexe",
            "other_analyses": "Acheminer les échantillons au laboratoire de microbiologie dédié à votre corridor de s ervice"
        },
        "checkboxes": {
            "hc": "Check Box1",
            "hcp": "Check Box2",
            "hcaep": "Check Box3",
            "selle": "Check Box4",
            "closd": "Check Box5",
            "hpylo": "Check Box6",
            "rotag": "Check Box7",
            "curi": "Check Box8",
            "strb": "Check Box13",
            "vagi": "Check Box14",
            "ccaur": "Check Box21",
            "bgnr": "ESWB",
            "sarmx": "ESWB_2",
            "cerv": "ESWB_3",
            "pusp": "M40B_4",
            "pupra": "M40B_5",
            "liqbi": "CSC_2",
            "gorge": "M40B_6",
            "cbron": "CSD",
            "cvri": "CSD_2",
            "csinu": "M40B_7",
            "stau": "M40B_8",
            "oeil": "M40B_9",
            "oreil": "M40B_10",
            "cgva": "Check Box38",
            "cgcol": "Endocol CGCOL",
            "cggo": "Check Box37",
            "cgre": "Check Box39",
            "cgoe": "Check Box36",
            "cgu": "Check Box35",
            "gono": "Check Box34",
            "cmyco": "Check Box27",
            "clev": "Check Box23",
            "oxyx": "OXA",
            "helm": "CSC",
            "arth": "CSA"
        }
    },

    "micro_mol": {
        "id": "micro_mol",
        "title": "Requête Microbiologie – Biologie Moléculaire (TAAN)",
        "pdf_path": os.path.join(DATA_DIR, "requete_microbiologie_moleculaire.pdf"),
        "headers": {
            "sample_date": "Text187",
            "sample_time": "Text188",
            "nurse_name": "Text189",
            "sample_location": "Text190",
            "doctor_name": "Text196",
            "doctor_license": "Text197",
            "clinic_name": "Text198",
            "clinic_id": "Text199",
            "doctor_copy": "Text200",
            "doctor_copy_license": "Text201",
            "patient_name": "Text192",
            "dob": "Text193",
            "ramq": "Text194",
            "clinical_info": "Text195",
            "sex": "Sexe",
            "other_analyses": "Acheminer les échantillons au laboratoire de microbiologie dédié à votre corridor de s ervice"
        },
        "checkboxes": {
            "adeng": "Check Box202",
            "cvcmv": "Check Box203",
            "ebvt": "EBVT Virus Epstein Barr",
            "bkjc": "BKJC Polyomavirus BKJC",
            "cvvih": "CVVIH Charge virale VIH",
            "hbadn": "HBADN Charge virale hépatite B",
            "hcarn": "HCARN Charge virale hépatite C",
            "inabv": "INABV SARSCOV2 Influenza A B et RSV",
            "hsvzv": "HSVZV Herpès HSV1 HSV2 et virus varicellezona VZV",
            "hsvlr": "HSVLR HERPES HSV1HSV2Particularité  LCR",
            "xhsvc": "XHSVC HERPES HSV1HSV2",
            "rougp": "ROUGP Virus de la rougeole",
            "borde": "BORDE Bordetella pertussis B parapertussis B holmesii",
            "mychp": "MYCHP Ch",
            "depc": "DEPC Dépistage EPC en contexte déclosion uniquement",
            "stect": "STECT Escherichia coli producteur de ShigaToxinesSTEC",
            "trwh": "TRWH Tropheryma whipplei",
            "cgva": "Vagin CGVA",
            "cgcol": "Endocol CGCOL",
            "cggo": "Gorge CGGO",
            "cgre": "Anus CGRE",
            "cgoe": "Œil CGOE",
            "cgu": "Urine CGU",
            "tmva": "Vagin TMVA",
            "tmco": "Col TMCO",
            "tmu": "Urine TMU",
            "tva": "Vagin TVA",
            "tco": "Col TCO",
            "tu": "Urine TU",
            "mva": "Vagin MVA",
            "mco": "Col MCO",
            "mu": "Urine MU",
            "cmvra": "CMVRA CMVRésistanceaux antiviraux",
            "hsvra": "HSVRA Herpes  Résistance aux antiviraux",
            "bkx": "Check Box204",
            "pcrtb": "Check Box205",
            "pcrbk": "PCRBK Mycobactéries TAAN détection de TB et résistance à la",
            "pneut": "PNEUT Pneumocystis jirovecii TAAN quantitatif",
            "mepan": "MEPAN",
            "pares": "PARES 9 cibles virales",
            "pardr": "PARDR 15 cibles virales et bactériennes",
            "pgese": "PGESE Multiplex pathogènes entériques",
            "mala": "MALA Détection de Plasmodium par LAMP Pays visité",
            "parat": "PARAT Multiplex parasite par TAAN 4 cibles G lamblia",
            "paras": "PARAS Parasitologie intestinale parmicroscopie"
        }
    }
}

# Legacy aliases for backward compatibility
PID_TO_CHECKBOX = REQUISITION_FORMS["general"]["checkboxes"]
HEADER_FIELD_NAMES = REQUISITION_FORMS["general"]["headers"]
TEMPLATE_PDF_PATH = REQUISITION_FORMS["general"]["pdf_path"]

# ==============================================================================
# PID RESOLUTION & PANEL EXPANSION
# ==============================================================================

def resolve_pids(input_pids: List[str]) -> List[str]:
    """Expands panel names and resolves synonyms to canonical catalog PIDs."""
    catalog = load_catalog()
    resolved = []
    seen = set()

    for item in input_pids:
        raw_key = item.lower().strip()
        
        # 1. Expand panel
        if raw_key in CLINICAL_PANELS:
            panel_data = CLINICAL_PANELS[raw_key]
            for child in panel_data.get("pids", []):
                child_norm = child.lower().strip()
                if child_norm and child_norm not in seen:
                    seen.add(child_norm)
                    resolved.append(child_norm)
            continue

        # 2. Check synonym dictionary
        if raw_key in SYNONYMS_TO_PID:
            canonical = SYNONYMS_TO_PID[raw_key]
            if canonical not in seen:
                seen.add(canonical)
                resolved.append(canonical)
            continue

        # 3. Direct match or keyword match in catalog
        if raw_key in catalog:
            if raw_key not in seen:
                seen.add(raw_key)
                resolved.append(raw_key)
            continue

        # Fallback: keep raw key
        if raw_key and raw_key not in seen:
            seen.add(raw_key)
            resolved.append(raw_key)

    return resolved

# ==============================================================================
# MULTI-REQUISITION INSPECTION
# ==============================================================================

def inspect_multi_requisitions(input_pids: Optional[List[str]] = None, site: str = "Tous les sites", pids: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Analyzes selected analyses against all 4 requisition forms.
    Determines which forms are needed, which checkboxes are ticked on each form,
    and which uncheckboxed analyses go to 'Autres demandes'.
    """
    raw_pids = pids if pids is not None else (input_pids or [])
    catalog = load_catalog()
    expanded_pids = resolve_pids(raw_pids)

    form_matched_map: Dict[str, List[Dict[str, Any]]] = {
        "general": [],
        "spec_multi": [],
        "micro_gen": [],
        "micro_mol": []
    }
    form_seen_fields: Dict[str, Set[str]] = {
        "general": set(),
        "spec_multi": set(),
        "micro_gen": set(),
        "micro_mol": set()
    }
    
    handled_pids: Set[str] = set()

    # Priority 1: Check Specialized Multidisciplinary (spec_multi)
    for pid in expanded_pids:
        if pid in REQUISITION_FORMS["spec_multi"]["checkboxes"]:
            cb_field = REQUISITION_FORMS["spec_multi"]["checkboxes"][pid]
            cat_entry = catalog.get(pid, {})
            name = cat_entry.get("name", pid.upper())
            if cb_field not in form_seen_fields["spec_multi"]:
                form_seen_fields["spec_multi"].add(cb_field)
                form_matched_map["spec_multi"].append({
                    "pid": pid,
                    "field_name": cb_field,
                    "name": name
                })
            handled_pids.add(pid)

    # Priority 2: Check Molecular Microbiology (micro_mol)
    for pid in expanded_pids:
        if pid in REQUISITION_FORMS["micro_mol"]["checkboxes"]:
            cb_field = REQUISITION_FORMS["micro_mol"]["checkboxes"][pid]
            cat_entry = catalog.get(pid, {})
            name = cat_entry.get("name", pid.upper())
            if cb_field not in form_seen_fields["micro_mol"]:
                form_seen_fields["micro_mol"].add(cb_field)
                form_matched_map["micro_mol"].append({
                    "pid": pid,
                    "field_name": cb_field,
                    "name": name
                })
            handled_pids.add(pid)

    # Priority 3: Check General Microbiology (micro_gen)
    for pid in expanded_pids:
        if pid not in handled_pids and pid in REQUISITION_FORMS["micro_gen"]["checkboxes"]:
            cb_field = REQUISITION_FORMS["micro_gen"]["checkboxes"][pid]
            cat_entry = catalog.get(pid, {})
            name = cat_entry.get("name", pid.upper())
            if cb_field not in form_seen_fields["micro_gen"]:
                form_seen_fields["micro_gen"].add(cb_field)
                form_matched_map["micro_gen"].append({
                    "pid": pid,
                    "field_name": cb_field,
                    "name": name
                })
            handled_pids.add(pid)

    # Troponin site-specific selection for CHU de Québec: HEJ/HDQ use Troponine T (TTROP), others use Troponine I (ITROP)
    is_hej_site = any(s in site.upper() for s in ["HEJ", "ENFANT-JÉSUS", "ENFANT-JESUS", "HDQ", "HÔTEL-DIEU", "HOTEL-DIEU"])
    tropo_field_pref = "TTROP" if is_hej_site else "ITROP"

    # Priority 4: Check General Requisition (general)
    for pid in expanded_pids:
        if pid not in handled_pids and pid in REQUISITION_FORMS["general"]["checkboxes"]:
            cb_field = REQUISITION_FORMS["general"]["checkboxes"][pid]
            # Override for generic troponin pid
            if pid in ["tropo", "itrop", "ttrop"]:
                cb_field = tropo_field_pref

            cat_entry = catalog.get(pid, {})
            name = cat_entry.get("name", pid.upper())
            if cb_field not in form_seen_fields["general"]:
                form_seen_fields["general"].add(cb_field)
                form_matched_map["general"].append({
                    "pid": pid,
                    "field_name": cb_field,
                    "name": name
                })
            handled_pids.add(pid)

    # Unhandled PIDs go to 'Other' on the general form (or active form)
    other_analyses = []
    for pid in expanded_pids:
        if pid not in handled_pids:
            cat_entry = catalog.get(pid, {})
            name = cat_entry.get("name", pid.upper())
            other_analyses.append({
                "pid": pid,
                "name": name
            })

    # Active forms are those with matched checkboxes or the general form if other_analyses exist
    active_forms = []
    all_matched_checkboxes = []

    # If general has matches OR if unmapped analyses exist (and no other form claimed them), include general
    if form_matched_map["general"] or (other_analyses and not any(len(form_matched_map[k]) > 0 for k in ["spec_multi", "micro_gen", "micro_mol"])):
        f_info = REQUISITION_FORMS["general"]
        active_forms.append({
            "form_id": "general",
            "title": f_info["title"],
            "matched_count": len(form_matched_map["general"]),
            "matched_checkboxes": form_matched_map["general"],
            "other_count": len(other_analyses) if f_info["id"] == "general" else 0,
            "other_analyses": other_analyses if f_info["id"] == "general" else []
        })
        all_matched_checkboxes.extend(form_matched_map["general"])

    for form_id in ["spec_multi", "micro_gen", "micro_mol"]:
        if form_matched_map[form_id]:
            f_info = REQUISITION_FORMS[form_id]
            # If general wasn't added and other_analyses exist, attach them to the first active form
            assigned_others = []
            if other_analyses and not any(f["form_id"] == "general" for f in active_forms) and len(active_forms) == 0:
                assigned_others = other_analyses

            active_forms.append({
                "form_id": form_id,
                "title": f_info["title"],
                "matched_count": len(form_matched_map[form_id]),
                "matched_checkboxes": form_matched_map[form_id],
                "other_count": len(assigned_others),
                "other_analyses": assigned_others
            })
            all_matched_checkboxes.extend(form_matched_map[form_id])

    # If nothing matched and no other analyses, default to 1 empty general form
    if not active_forms:
        active_forms.append({
            "form_id": "general",
            "title": REQUISITION_FORMS["general"]["title"],
            "matched_count": 0,
            "matched_checkboxes": [],
            "other_count": len(other_analyses),
            "other_analyses": other_analyses
        })

    return {
        "site": site,
        "total_requested": len(expanded_pids),
        "total_matched": len(all_matched_checkboxes),
        "total_other": len(other_analyses),
        "matched_checkboxes": all_matched_checkboxes,
        "checked_fields": [m["field_name"] for m in all_matched_checkboxes],
        "other_analyses": other_analyses,
        "active_forms": active_forms,
        "total_pages": len(active_forms)
    }

# Backward compatible aliases
def inspect_requisition(input_pids: List[str], site: str = "Tous les sites") -> Dict[str, Any]:
    return inspect_multi_requisitions(input_pids, site)

inspect_requisition_selection = inspect_multi_requisitions

# ==============================================================================
# SINGLE & MULTI-PAGE REQUISITION PDF GENERATION
# ==============================================================================

def _fill_single_form_page(form_config: Dict[str, Any], matched_cbs: List[str], other_items: List[Dict[str, Any]], site: str, patient_info: Optional[Dict[str, Any]]) -> fitz.Document:
    """Fills a single requisition template and returns the populated PyMuPDF Document."""
    template_path = form_config["pdf_path"]
    headers = form_config["headers"]
    
    doc = fitz.open(template_path)
    page = doc[0]

    other_text = ""
    if other_items:
        other_names = [f"{item['name']} ({item['pid'].upper()})" if item['pid'].upper() not in item['name'].upper() else item['name'] for item in other_items]
        other_text = " • ".join(other_names)

    patient_dict = patient_info or {}
    text_values_to_set = {}

    if site and site != "Tous les sites" and "site" in headers:
        text_values_to_set[headers["site"]] = site

    if patient_dict.get("ramq") and "ramq" in headers:
        text_values_to_set[headers["ramq"]] = str(patient_dict["ramq"]).strip()
    if patient_dict.get("dossier") and "dossier" in headers:
        text_values_to_set[headers["dossier"]] = str(patient_dict["dossier"]).strip()
    if patient_dict.get("room") and "room" in headers:
        text_values_to_set[headers["room"]] = str(patient_dict["room"]).strip()
    if patient_dict.get("patient_name") and "patient_name" in headers:
        text_values_to_set[headers["patient_name"]] = str(patient_dict["patient_name"]).strip()
    if patient_dict.get("dob") and "dob" in headers:
        text_values_to_set[headers["dob"]] = str(patient_dict["dob"]).strip()
    if patient_dict.get("clinical_info") and "clinical_info" in headers:
        text_values_to_set[headers["clinical_info"]] = str(patient_dict["clinical_info"]).strip()

    if patient_dict.get("doctor_name") and "doctor_name" in headers:
        text_values_to_set[headers["doctor_name"]] = str(patient_dict["doctor_name"]).strip()
    if patient_dict.get("doctor_license") and "doctor_license" in headers:
        text_values_to_set[headers["doctor_license"]] = str(patient_dict["doctor_license"]).strip()
    if patient_dict.get("clinic_name") and "clinic_name" in headers:
        text_values_to_set[headers["clinic_name"]] = str(patient_dict["clinic_name"]).strip()
    if patient_dict.get("clinic_id") and "clinic_id" in headers:
        text_values_to_set[headers["clinic_id"]] = str(patient_dict["clinic_id"]).strip()
    if patient_dict.get("doctor_copy") and "doctor_copy" in headers:
        text_values_to_set[headers["doctor_copy"]] = str(patient_dict["doctor_copy"]).strip()
    if patient_dict.get("doctor_copy_license") and "doctor_copy_license" in headers:
        text_values_to_set[headers["doctor_copy_license"]] = str(patient_dict["doctor_copy_license"]).strip()

    if patient_dict.get("sample_date") and "sample_date" in headers:
        text_values_to_set[headers["sample_date"]] = str(patient_dict["sample_date"]).strip()
    if patient_dict.get("sample_time") and "sample_time" in headers:
        text_values_to_set[headers["sample_time"]] = str(patient_dict["sample_time"]).strip()
    if patient_dict.get("nurse_name") and "nurse_name" in headers:
        text_values_to_set[headers["nurse_name"]] = str(patient_dict["nurse_name"]).strip()
    if patient_dict.get("sample_location") and "sample_location" in headers:
        text_values_to_set[headers["sample_location"]] = str(patient_dict["sample_location"]).strip()

    if other_text and "other_analyses" in headers:
        text_values_to_set[headers["other_analyses"]] = other_text

    sex_val = patient_dict.get("sex", "").strip().upper()
    checked_set = set(matched_cbs)

    for widget in page.widgets():
        fname = widget.field_name
        ftype = widget.field_type_string

        if ftype == "CheckBox":
            if fname in checked_set:
                widget.field_value = "Yes"
                widget.update()
            else:
                widget.field_value = "Off"
                widget.update()

        elif ftype == "Text":
            if fname in text_values_to_set:
                val_str = str(text_values_to_set[fname])
                widget.field_value = val_str
                if "other_analyses" in headers and fname == headers["other_analyses"]:
                    widget.text_fontsize = 8.5
                elif "sample_location" in headers and fname == headers["sample_location"]:
                    if len(val_str) > 65:
                        widget.text_fontsize = 6.2
                    elif len(val_str) > 45:
                        widget.text_fontsize = 6.8
                    else:
                        widget.text_fontsize = 7.5
                elif "nurse_name" in headers and fname == headers["nurse_name"]:
                    if len(val_str) > 40:
                        widget.text_fontsize = 6.8
                    else:
                        widget.text_fontsize = 7.5
                else:
                    widget.text_fontsize = 8.0
                widget.update()

        elif ftype == "RadioButton" and fname == headers.get("sex"):
            if sex_val in ["M", "F"]:
                if widget.on_state() == sex_val:
                    widget.field_value = sex_val
                    widget.update()

    return doc

def generate_multi_form_requisition_pdf(pids: List[str], site: str = "Tous les sites", patient_info: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Generates and merges all required requisition form pages into a single printable PDF.
    """
    inspection = inspect_multi_requisitions(pids, site)
    active_forms = inspection.get("active_forms", [])

    if not active_forms:
        active_forms = [{"form_id": "general", "matched_checkboxes": [], "other_analyses": []}]

    merged_doc = fitz.open()

    for form_meta in active_forms:
        form_id = form_meta["form_id"]
        form_config = REQUISITION_FORMS[form_id]
        matched_cb_names = [m["field_name"] for m in form_meta.get("matched_checkboxes", [])]
        other_items = form_meta.get("other_analyses", [])

        single_doc = _fill_single_form_page(
            form_config=form_config,
            matched_cbs=matched_cb_names,
            other_items=other_items,
            site=site,
            patient_info=patient_info
        )

        merged_doc.insert_pdf(single_doc)
        single_doc.close()

    output_stream = io.BytesIO()
    merged_doc.save(output_stream, garbage=3, deflate=True)
    merged_doc.close()

    return output_stream.getvalue()

# Backward compatible aliases
CHECKBOX_METADATA = {k: {"field_name": v} for k, v in REQUISITION_FORMS["general"]["checkboxes"].items()}

def generate_filled_requisition_pdf(pids: List[str], site: str = "Tous les sites", patient_info: Optional[Dict[str, Any]] = None) -> bytes:
    return generate_multi_form_requisition_pdf(pids, site, patient_info)

