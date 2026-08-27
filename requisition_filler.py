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
import re
from datetime import datetime
import fitz  # PyMuPDF
from typing import List, Dict, Any, Optional, Set
from tube_calculator import load_catalog, normalize_str
from medical_dictionary import CLINICAL_PANELS, SYNONYMS_TO_PID

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def format_dob_str(raw_dob: Any) -> str:
    """Standardizes various date of birth formats to YYYY-MM-DD."""
    if not raw_dob:
        return ""
    s = str(raw_dob).strip()
    # YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD-MM-YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # YYMMDD (6 digits)
    m = re.match(r"^(\d{2})(\d{2})(\d{2})$", s)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        curr_yy = int(datetime.now().strftime("%y"))
        full_yr = 2000 + yy if yy <= curr_yy else 1900 + yy
        return f"{full_yr:04d}-{mm:02d}-{dd:02d}"
    # YYYYMMDD (8 digits)
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s

def extract_ramq_info(ramq_str: Any) -> Dict[str, str]:
    """Extracts date of birth (YYYY-MM-DD) and sex (M/F) from Quebec RAMQ format."""
    if not ramq_str:
        return {}
    clean = re.sub(r"[^A-Za-z0-9]", "", str(ramq_str)).upper()
    if len(clean) >= 10 and clean[:4].isalpha() and clean[4:10].isdigit():
        yy = int(clean[4:6])
        mm_raw = int(clean[6:8])
        dd = int(clean[8:10])
        is_female = mm_raw > 50
        mm = mm_raw - 50 if is_female else mm_raw
        curr_yy = int(datetime.now().strftime("%y"))
        full_year = 2000 + yy if yy <= curr_yy else 1900 + yy
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return {
                "dob": f"{full_year:04d}-{mm:02d}-{dd:02d}",
                "sex": "F" if is_female else "M"
            }
    return {}

def parse_ramq_barcode_payload(payload_str: Any) -> Dict[str, Any]:
    """Decodes 1D (Code 128 / Code 39) or 2D (DataMatrix / PDF417) barcode payload from Quebec RAMQ card."""
    if not payload_str:
        return {}
    raw = str(payload_str).strip()

    # 1. Check for AAMVA tags (e.g. DCS, DAC, DAQ, DBB, DBC)
    aamva_last = re.search(r'(?:DCS|DAB|DCSLAST)[:\s]*([A-Za-zÀ-ÿ\-]+)', raw, re.IGNORECASE)
    aamva_first = re.search(r'(?:DAC|DAD|DCSFIRST)[:\s]*([A-Za-zÀ-ÿ\-]+)', raw, re.IGNORECASE)
    aamva_ramq = re.search(r'(?:DAQ|NAM|RAMQ)[:\s]*([A-Za-z]{4}\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{2}?)', raw, re.IGNORECASE)
    aamva_dob = re.search(r'(?:DBB|DBA)[:\s]*(\d{8}|\d{4}[-/.]\d{2}[-/.]\d{2})', raw, re.IGNORECASE)
    aamva_sex = re.search(r'(?:DBC)[:\s]*([12MF])', raw, re.IGNORECASE)
    
    # 2. Extract RAMQ pattern (4 letters + 6 or 8 digits)
    ramq_raw = ""
    ramq_clean = ""

    if aamva_ramq:
        clean_daq = re.sub(r'[^A-Za-z0-9]', '', aamva_ramq.group(1)).upper()
        if len(clean_daq) >= 10:
            ramq_raw = clean_daq.ljust(12, '0')
            ramq_clean = f'{ramq_raw[:4]} {ramq_raw[4:8]} {ramq_raw[8:12]}'
    else:
        ramq_candidates = re.findall(r'([A-Za-z]{4})\s?(\d{2})\s?(\d{2})\s?(\d{2})\s?(\d{2})?', raw)
        for r in ramq_candidates:
            letters = r[0].upper()
            if letters not in ['ANSI', 'AAMV', 'CARD', 'CARTE', 'QUEB', 'QC']:
                p1, p2, p3 = r[1], r[2], r[3]
                p4 = r[4] or '00'
                ramq_raw = f"{letters}{p1}{p2}{p3}{p4}"
                ramq_clean = f"{letters} {p1}{p2} {p3}{p4}"
                break
        if not ramq_raw:
            m10 = re.search(r'([A-Za-z]{4})\s?(\d{6})', raw)
            if m10 and m10.group(1).upper() not in ['ANSI', 'AAMV']:
                letters = m10.group(1).upper()
                digits = m10.group(2)
                ramq_raw = f"{letters}{digits}00"
                ramq_clean = f"{letters} {digits[:4]} {digits[4:]}00"

    dob = ""
    sex = ""
    last_prefix = ""
    first_prefix = ""
    if ramq_raw and len(ramq_raw) >= 10:
        last_prefix = ramq_raw[:3]
        first_prefix = ramq_raw[3]
        yy = int(ramq_raw[4:6])
        mm_raw = int(ramq_raw[6:8])
        dd = int(ramq_raw[8:10])
        is_female = mm_raw > 50
        mm = mm_raw - 50 if is_female else mm_raw
        curr_yy = int(datetime.now().strftime("%y"))
        full_year = 2000 + yy if yy <= curr_yy else 1900 + yy
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            dob = f"{full_year:04d}-{mm:02d}-{dd:02d}"
            sex = "F" if is_female else "M"

    # Explicit DOB override
    if aamva_dob:
        s_dob = re.sub(r'[^0-9]', '', aamva_dob.group(1))
        if len(s_dob) == 8:
            dob = f"{s_dob[:4]}-{s_dob[4:6]}-{s_dob[6:]}"

    # Explicit Sex override
    if aamva_sex:
        s_sex = aamva_sex.group(1).upper()
        if s_sex in ['1', 'M']:
            sex = 'M'
        elif s_sex in ['2', 'F']:
            sex = 'F'

    # 3. Extract Name
    last_name = ""
    first_name = ""

    if aamva_last:
        last_name = aamva_last.group(1).capitalize()
    if aamva_first:
        first_name = aamva_first.group(1).capitalize()

    if not last_name or not first_name:
        # Split tokens (delimiters: newline, pipe, caret, comma, semicolon, tab, slash)
        tokens = [t.strip() for t in re.split(r"[\r\n|^,;\t/]+", raw) if t.strip()]
        clean_ramq_full = re.sub(r"[^A-Z0-9]", "", ramq_raw)
        
        candidates = []
        for t in tokens:
            clean_t = re.sub(r"[^A-Za-zÀ-ÿ\-]", "", t).strip()
            if not clean_t or len(clean_t) < 2:
                continue
            upper_t = clean_t.upper()
            
            # Skip if token is the RAMQ or part of RAMQ or metadata keyword
            if upper_t == ramq_raw[:4] or upper_t == clean_ramq_full:
                continue
            if len(upper_t) <= 4 and (upper_t == ramq_raw[:3] or upper_t == ramq_raw[:4]):
                continue
            if upper_t in ["RAMQ", "QC", "QUEBEC", "EXP", "NAM", "CARD", "CARTE", "HOMME", "FEMME", "ANSI", "AAMVA"]:
                continue
                
            candidates.append(clean_t)

        # Match candidates with last_prefix and first_prefix
        for c in candidates:
            c_upper = c.upper()
            if last_prefix and c_upper.startswith(last_prefix) and not last_name:
                last_name = c.capitalize()
            elif first_prefix and c_upper.startswith(first_prefix) and not first_name:
                first_name = c.capitalize()
            elif not last_name:
                last_name = c.capitalize()
            elif not first_name and c.capitalize() != last_name:
                first_name = c.capitalize()

    patient_name = ""
    if last_name and first_name:
        patient_name = f"{last_name}, {first_name}"
    elif last_name:
        patient_name = last_name

    return {
        "ramq": ramq_clean,
        "patient_name": patient_name,
        "last_name": last_name,
        "first_name": first_name,
        "dob": dob,
        "sex": sex,
        "raw": raw
    }

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
    },

    "banque_sang": {
        "id": "banque_sang",
        "title": "Requête de Banque de Sang (Immuno-hématologie)",
        "pdf_path": os.path.join(DATA_DIR, "requete_banque_de_sang.pdf"),
        "headers": {
            "sample_date": "sample_date",
            "sample_time": "sample_time",
            "nurse_name": "nurse_name",
            "sample_location": "sample_location",
            "doctor_name": "doctor_name",
            "doctor_license": "doctor_license",
            "clinic_name": "clinic_name",
            "doctor_copy": "doctor_copy",
            "doctor_copy_license": "doctor_copy_license",
            "clinic_copy_name": "clinic_copy_name",
            "prescriber_clinical_info": "prescriber_clinical_info",
            "ramq": "ramq",
            "dossier": "dossier",
            "site": "site",
            "dob": "dob",
            "patient_name": "patient_name",
            "patient_firstname": "patient_firstname",
            "clinical_info": "diagnostic",
            "mother_name": "mother_name",
            "address_street": "address_street",
            "address_apt": "address_apt",
            "postal_code": "postal_code",
            "phone": "phone",
            "sex_m": "Sexe_M",
            "sex_f": "Sexe_F",
            "other_analyses": "AUTRES ANALYSES OU DEMANDES SPÉCIALES"
        },
        "checkboxes": {
            "bds003": "GROUPE SANGUIN ET RECHERCHE D’ANTICORPS",
            "typage_depistage": "GROUPE SANGUIN ET RECHERCHE D’ANTICORPS",
            "bds008": "2e DÉTERMINATION ABO Rh",
            "bds002": "GROUPE SANGUIN (ABO Rh)",
            "bds001": "COOMBS DIRECT",
            "bds007": "INVESTIGATION RÉACTION TRANSFUSIONNELLE",
            "bds006": "TITRAGE D’ANTICORPS IMMUNS",
            "bds006_immuns": "TITRAGE D’ANTICORPS IMMUNS",
            "bds006_naturels": "TITRAGE D’ANTICORPS NATURELS (anti-A, anti-B)",
            "bds005": "TITRAGE AGGLUTININES FROIDES",
            "bds004": "PHÉNOTYPES ÉRYTHROCYTAIRES"
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
        "micro_mol": [],
        "banque_sang": []
    }
    form_seen_fields: Dict[str, Set[str]] = {
        "general": set(),
        "spec_multi": set(),
        "micro_gen": set(),
        "micro_mol": set(),
        "banque_sang": set()
    }
    
    handled_pids: Set[str] = set()

    # Priority 1: Check Blood Bank (banque_sang)
    for pid in expanded_pids:
        if pid in REQUISITION_FORMS["banque_sang"]["checkboxes"]:
            cb_field = REQUISITION_FORMS["banque_sang"]["checkboxes"][pid]
            cat_entry = catalog.get(pid, {})
            name = cat_entry.get("name", pid.upper())
            if cb_field not in form_seen_fields["banque_sang"]:
                form_seen_fields["banque_sang"].add(cb_field)
                form_matched_map["banque_sang"].append({
                    "pid": pid,
                    "field_name": cb_field,
                    "name": name
                })
            handled_pids.add(pid)

    # Priority 2: Check Specialized Multidisciplinary (spec_multi)
    for pid in expanded_pids:
        if pid not in handled_pids and pid in REQUISITION_FORMS["spec_multi"]["checkboxes"]:
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

    # Priority 3: Check Molecular Microbiology (micro_mol)
    for pid in expanded_pids:
        if pid not in handled_pids and pid in REQUISITION_FORMS["micro_mol"]["checkboxes"]:
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

    # Priority 4: Check General Microbiology (micro_gen)
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

    # Priority 5: Check General Requisition (general)
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
    if form_matched_map["general"] or (other_analyses and not any(len(form_matched_map[k]) > 0 for k in ["banque_sang", "spec_multi", "micro_gen", "micro_mol"])):
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

    for form_id in ["banque_sang", "spec_multi", "micro_gen", "micro_mol"]:
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

    # Fallback extraction from RAMQ
    ramq_val = str(patient_dict.get("ramq", "")).strip()
    ramq_info = extract_ramq_info(ramq_val)

    # Patient name handling (combined vs separated Nom / Prénom)
    if "patient_firstname" in headers and "patient_name" in headers:
        raw_pname = str(patient_dict.get("patient_name", "")).strip()
        raw_fname = str(patient_dict.get("patient_firstname", "")).strip()
        if raw_fname:
            text_values_to_set[headers["patient_name"]] = raw_pname
            text_values_to_set[headers["patient_firstname"]] = raw_fname
        elif "," in raw_pname:
            parts = [p.strip() for p in raw_pname.split(",", 1)]
            text_values_to_set[headers["patient_name"]] = parts[0]
            text_values_to_set[headers["patient_firstname"]] = parts[1]
        elif " " in raw_pname:
            parts = raw_pname.rsplit(" ", 1)
            text_values_to_set[headers["patient_name"]] = parts[1]
            text_values_to_set[headers["patient_firstname"]] = parts[0]
        elif raw_pname:
            text_values_to_set[headers["patient_name"]] = raw_pname
    elif patient_dict.get("patient_name") and "patient_name" in headers:
        text_values_to_set[headers["patient_name"]] = str(patient_dict["patient_name"]).strip()

    # DOB resolution (any field alias or RAMQ fallback)
    raw_dob = (
        patient_dict.get("dob")
        or patient_dict.get("date_naissance")
        or patient_dict.get("birth_date")
        or patient_dict.get("birthdate")
        or patient_dict.get("patient_dob")
        or ramq_info.get("dob")
    )
    formatted_dob = format_dob_str(raw_dob)
    if formatted_dob and "dob" in headers:
        text_values_to_set[headers["dob"]] = formatted_dob

    if patient_dict.get("clinical_info") and "clinical_info" in headers:
        text_values_to_set[headers["clinical_info"]] = str(patient_dict["clinical_info"]).strip()
    if patient_dict.get("mother_name") and "mother_name" in headers:
        text_values_to_set[headers["mother_name"]] = str(patient_dict["mother_name"]).strip()
    if patient_dict.get("address_street") and "address_street" in headers:
        text_values_to_set[headers["address_street"]] = str(patient_dict["address_street"]).strip()
    if patient_dict.get("address_apt") and "address_apt" in headers:
        text_values_to_set[headers["address_apt"]] = str(patient_dict["address_apt"]).strip()
    if patient_dict.get("postal_code") and "postal_code" in headers:
        text_values_to_set[headers["postal_code"]] = str(patient_dict["postal_code"]).strip()
    if patient_dict.get("phone") and "phone" in headers:
        text_values_to_set[headers["phone"]] = str(patient_dict["phone"]).strip()

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
    if patient_dict.get("clinic_copy_name") and "clinic_copy_name" in headers:
        text_values_to_set[headers["clinic_copy_name"]] = str(patient_dict["clinic_copy_name"]).strip()
    if patient_dict.get("prescriber_clinical_info") and "prescriber_clinical_info" in headers:
        text_values_to_set[headers["prescriber_clinical_info"]] = str(patient_dict["prescriber_clinical_info"]).strip()

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

    sex_val = str(patient_dict.get("sex") or ramq_info.get("sex") or "").strip().upper()
    checked_set = set(matched_cbs)

    if "sex_m" in headers and sex_val in ["M", "MASCULIN", "HOMME"]:
        checked_set.add(headers["sex_m"])
    if "sex_f" in headers and sex_val in ["F", "FEMININ", "FEMME"]:
        checked_set.add(headers["sex_f"])

    for widget in page.widgets():
        fname = widget.field_name
        ftype = widget.field_type_string

        if ftype == "CheckBox":
            if fname in checked_set:
                widget.field_value = "Yes"
                widget.button_caption = "8" # ZapfDingbats '8' = 'X'
                widget.update()
                # If this is a sex checkbox (e.g. Banque de sang), draw a crisp vector 'X'
                if ("sex_m" in headers and fname == headers["sex_m"]) or ("sex_f" in headers and fname == headers["sex_f"]):
                    r = widget.rect
                    cx = (r.x0 + r.x1) / 2.0
                    cy = (r.y0 + r.y1) / 2.0
                    hw, hh = 3.8, 3.8
                    box = fitz.Rect(cx - hw, cy - hh, cx + hw, cy + hh)
                    page.draw_line(box.tl, box.br, color=(0, 0, 0), width=1.2)
                    page.draw_line(box.bl, box.tr, color=(0, 0, 0), width=1.2)
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
                    widget.button_caption = "8" # ZapfDingbats cross 'X'
                    widget.update()
                    
                    # Draw a crisp, high-contrast vector 'X' for clear printing
                    r = widget.rect
                    cx = (r.x0 + r.x1) / 2.0
                    cy = (r.y0 + r.y1) / 2.0
                    hw, hh = 3.6, 3.6
                    box = fitz.Rect(cx - hw, cy - hh, cx + hw, cy + hh)
                    page.draw_line(box.tl, box.br, color=(0, 0, 0), width=1.2)
                    page.draw_line(box.bl, box.tr, color=(0, 0, 0), width=1.2)
                else:
                    widget.field_value = "Off"
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

