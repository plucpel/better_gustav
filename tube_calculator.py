import os
import re
import json
import math
import unicodedata
from collections import defaultdict
from medical_dictionary import CLINICAL_PANELS, SYNONYMS_TO_PID

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "gustav_lab_catalog.json")

def load_catalog():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

CATALOG = load_catalog()

def normalize_str(s):
    """Normalize string for accent-insensitive, case-insensitive comparison."""
    if not s:
        return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    return s.lower().strip()

# Standard nominal tube capacities (mL)
TUBE_NOMINAL_CAPACITY = {
    "HEMOCULTURE": 10.0,
    "CITRATE": 2.7,
    "SERUM_GEL": 5.0,
    "SERUM_PLAIN": 6.0,
    "HEPARINE_LITHIUM": 4.5,
    "HEPARINE_SODIUM": 6.0,
    "EDTA": 4.0,
    "EDTA_ROSE": 6.0,
    "ROYAL_BLUE": 6.0,
    "FLUORURE": 4.0,
    "GAZ_SERINGUE": 2.0,
    "SPECIMEN_DIVERS": 10.0
}

PEDIATRIC_MICRO_CAPACITY = 0.8 # mL per microtube

def parse_volume_ml(qty_str):
    """Parse volume in mL from various quantity string formats."""
    if not qty_str:
        return 0.0
    # Check for "N x M mL" (e.g. 2 x 5 mL)
    m_mult = re.search(r"(\d+)\s*[xX*]\s*(\d+(?:[.,]\d+)?)\s*m[lL]", qty_str)
    if m_mult:
        return float(m_mult.group(1)) * float(m_mult.group(2).replace(",", "."))
    
    # Check for microliters e.g. "375 µl" or "500 ul"
    m_ul = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:µ|u|micro)l", qty_str, re.IGNORECASE)
    if m_ul:
        return float(m_ul.group(1).replace(",", ".")) / 1000.0
        
    # Check for simple "X mL" or "X ml"
    m_ml = re.search(r"(\d+(?:[.,]\d+)?)\s*m[lL]", qty_str)
    if m_ml:
        return float(m_ml.group(1).replace(",", "."))
        
    return 0.0

# Curated external restrictions for high-precision clinical guidance
EXTERNAL_RESTRICTIONS_OVERRIDE = {
    # 1. SUR GLACE
    "ammo": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Spécimen sur glace obligatoire (< 30 min), non réalisable en externe."},
    "ammu": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Spécimen urinaire sur glace obligatoire, non disponible en externe."},
    "ammux": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Spécimen urinaire sur glace obligatoire, non disponible en externe."},
    "acth": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Tube EDTA pré-refroidi et acheminement sur glace obligatoire (< 30 min)."},
    "calci": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Envoi immédiat sur glace requis, non disponible en externe."},
    "gast": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "À jeun 8h, transport des tubes sur glace obligatoire."},
    "metnl": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Prélèvement à l'hôpital seulement, acheminement sur glace (< 30 min)."},
    "3meth": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Prélèvement à l'hôpital seulement, acheminement sur glace (< 30 min)."},
    "vitc": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Acheminer sur glace et à l'abri de la lumière dans les 2 heures."},
    "proap": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Arrivée au laboratoire requise en < 30 min sur glace (Formulaire AH-612)."},
    "yglug": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Tube pré-refroidi à 4°C et transport immédiat sur glace (Hôpital seulement)."},
    "yhiss": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Mettre sur glace immédiatement après le prélèvement et acheminer sans délai."},
    "xsest": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Prélèvement sur glace, transport rapide (Hôpital seulement)."},
    "bio001": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Aviser le laboratoire, mettre immédiatement le spécimen sur glace."},
    "oxap": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Transport immédiat en bain d'eau et glace (sans contact direct), centrifugation < 1h."},
    "osptv": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Transport rapide (< 15 min), sinon impérativement sur glace."},
    "osptvx": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Transport rapide (< 15 min), sinon impérativement sur glace."},
    "yvegf": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Prélèvement sur glace, centrifugation à froid et décantation/congélation < 30 min."},
    "il6": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Prélèvement hospitalier obligatoire, arrivée sur glace < 30 min."},
    "hem031": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Centrifugation à 4°C en < 30 min, congélation et transport sur glace sèche."},
    "ycykn": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Centrifugation à 4°C en < 30 min, congélation et envoi sur glace sèche."},
    "cfbsp": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Centrifugation à 4-8°C, décantation 2 aliquotes et transport sur glace sèche."},
    "fhpr": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Centrifugation à 4-8°C, décantation 2 aliquotes et transport sur glace sèche."},
    "comcf": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Centrifugation à 4-8°C, décantation 2 aliquotes et transport sur glace sèche."},
    "cosco": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Épreuve dynamique : pré-refroidir et maintenir les tubes lavande sur glace."},
    "coscox": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Épreuve dynamique : pré-refroidir et maintenir les tubes lavande sur glace."},
    "sudiv": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Épreuve dynamique : tubes lavande pré-refroidis et transportés sur glace."},
    "supd8": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Épreuve dynamique : tubes lavande sur glace obligatoires."},
    "eeana": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Épreuve d'effort : prélèvement immédiat sur glace."},
    "caspi": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Cathétérisme : tubes lavande sur glace obligatoires."},
    "laclb": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Acheminer sans délai sur glace, non disponible en externe."},
    "laclbx": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Acheminer sans délai sur glace, non disponible en externe."},
    "laclc": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Acheminer sans délai sur glace, non disponible en externe."},
    "laclcx": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Acheminer sans délai sur glace, non disponible en externe."},
    "isu": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Prélèvement sur glace analysé en < 4h (Prélèvement au CHU requis)."},
    "cynba": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "Lavage broncho-alvéolaire : acheminement immédiat sur glace."},
    "cydba": {"type": "SUR_GLACE", "badge": "🧊 Sur glace", "reason": "LBA pédiatrique : acheminement immédiat sur glace/sac réfrigérant."},

    # 2. DECANTE / CONGELE EN EXTERNE
    "chga": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Le spécimen doit impérativement être décanté dans l'heure suivant la ponction."},
    "yqudn": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation et décantation obligatoires en moins de 2 heures."},
    "xah50": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation à 4-8°C, décantation et congélation obligatoire en < 45 min."},
    "xcmbl": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation, décantation et congélation obligatoire en < 45 min."},
    "xcfia": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Double centrifugation et congélation rapide du plasma requises en < 2h."},
    "tt": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Double centrifugation, décantation du plasma et congélation immédiate requises."},
    "porph": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation et congélation immédiate du plasma à l'abri de la lumière."},
    "a21hy": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation obligatoire à 4°C."},
    "xnclc": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation < 1h et décantation obligatoire du culot de globules rouges."},
    "xnclcx": {"type": "DECANTE_CONGELE", "badge": "🔄 Décantation requise", "reason": "Centrifugation < 1h et décantation obligatoire du culot de globules rouges."},
    "damiu": {"type": "DECANTE_CONGELE", "badge": "❄️ Congélation requise", "reason": "Spécimen urinaire à congeler sur réception et à protéger de la lumière."},
    "damiux": {"type": "DECANTE_CONGELE", "badge": "❄️ Congélation requise", "reason": "Spécimen urinaire à congeler sur réception et à protéger de la lumière."},
    "porbu": {"type": "DECANTE_CONGELE", "badge": "❄️ Congélation requise", "reason": "Spécimen urinaire à congeler sur réception et à protéger de la lumière."},
    "poru": {"type": "DECANTE_CONGELE", "badge": "❄️ Congélation requise", "reason": "Spécimen urinaire à congeler sur réception et à protéger de la lumière."},
    "pneug": {"type": "DECANTE_CONGELE", "badge": "🔄 Aliquotage requis", "reason": "Demande externe : 1 aliquote de 0,5 mL distincte requise par test."},
    "tetag": {"type": "DECANTE_CONGELE", "badge": "🔄 Aliquotage requis", "reason": "Demande externe : 1 aliquote de 0,5 mL distincte requise par test."},
    "dipgr": {"type": "DECANTE_CONGELE", "badge": "🔄 Aliquotage requis", "reason": "Demande externe : 1 aliquote de 0,5 mL distincte requise par test."},
    "hinfg": {"type": "DECANTE_CONGELE", "badge": "🔄 Aliquotage requis", "reason": "Demande externe : 1 aliquote de 0,5 mL distincte requise par test."},
    "asspg": {"type": "DECANTE_CONGELE", "badge": "🔄 Aliquotage requis", "reason": "Demande externe : 1 aliquote de 0,5 mL distincte requise par test."},
    "xartv": {"type": "DECANTE_CONGELE", "badge": "❄️ Congélation requise", "reason": "Spécimen à congeler très rapidement à -20°C (Non disponible externe)."},

    # 3. NON DISPONIBLE EN EXTERNE
    "bioq": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Non disponible en externe (CLSC, cliniques) - Corridor CHU interne requis."},
    "hem035": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Non disponible pour la clientèle externe (CLSC, CM...)."},
    "myd88": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Non disponible pour la clientèle externe (CLSC, CM...)."},
    "catvc": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Épreuve dynamique hospitalière, non disponible en externe."},
    "epr006": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Test de surcharge hospitalier, non disponible en externe."},
    "susel": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Test de surcharge hospitalier, non disponible en externe."},
    "pyrlc": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Non disponible en externe (CLSC, cliniques privées, résidences)."},
    "ffa": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Prélèvement à ne faire qu'à l'hôpital, non disponible pour l'externe."},
    "hgh": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Doit être prélevé à l'intérieur du CHU ou en centre hospitalier avec labo."},
    "inhis": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Doit être prélevé à l'intérieur du CHU ou en centre hospitalier avec labo."},
    "oxneu": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Doit être prélevé à l’intérieur du CHUL en avant-midi."},
    "ckmb": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Usage interne seulement, non disponible pour l'externe."},
    "ckmbx": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Usage interne seulement, non disponible pour l'externe."},
    "glyce": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Prélèvement à ne faire qu'à l'hôpital, non disponible pour l'externe."},
    "aucun": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Analyse réservée au laboratoire interne, non disponible en externe."},
    "cyndi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Microscopie dialyse réservée à l'interne (HDQ seulement)."},
    "albbi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "bilbi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "ceabi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "clbi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "chobi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "alpbi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "urebi": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide biologique non disponible pour l'externe (Clinique, CLSC...)."},
    "credp": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide dialyse non disponible pour l'externe (Clinique, CLSC...)."},
    "credpx": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide dialyse non disponible pour l'externe (Clinique, CLSC...)."},
    "urdp": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide dialyse non disponible pour l'externe (Clinique, CLSC...)."},
    "urdpx": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Liquide dialyse non disponible pour l'externe (Clinique, CLSC...)."},
    "bicuu": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Bicarbonates urinaires non disponibles en externe (contenant spécial)."},
    "bircux": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Bicarbonates urinaires non disponibles en externe (contenant spécial)."},
    "crpod": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Créatinine post-dialyse non disponible pour externe."},
    "crpodx": {"type": "NON_DISPO_EXTERNE", "badge": "🚫 Non dispo en externe", "reason": "Créatinine post-dialyse non disponible pour externe."}
}

def get_external_restriction(pid, item=None):
    """
    Evaluates whether a laboratory test has external clinic / CLSC collection restrictions:
    - SUR_GLACE (requires ice bath, dry ice, pre-chilled tubes)
    - DECANTE_CONGELE (requires immediate centrifugation, decantation, or fast freezing)
    - NON_DISPO_EXTERNE (hospital only or strictly unavailable for external clinics)
    """
    if not pid:
        return {"is_incompatible": False, "type": None, "badge": None, "badge_class": None, "reason": None}
    
    pid_clean = pid.lower().strip()
    if pid_clean in EXTERNAL_RESTRICTIONS_OVERRIDE:
        ov = EXTERNAL_RESTRICTIONS_OVERRIDE[pid_clean]
        t = ov["type"]
        b_class = "bg-rose-50 text-rose-700 border-rose-200" if t == "NON_DISPO_EXTERNE" else ("bg-sky-50 text-sky-700 border-sky-200" if t == "SUR_GLACE" else "bg-amber-50 text-amber-700 border-amber-200")
        return {
            "is_incompatible": True,
            "type": t,
            "badge": ov["badge"],
            "badge_class": b_class,
            "reason": ov["reason"]
        }
        
    if item is None:
        cat = load_catalog()
        item = cat.get(pid_clean)
        
    if not item:
        return {"is_incompatible": False, "type": None, "badge": None, "badge_class": None, "reason": None}
        
    prep = item.get("preparation", "")
    inst = item.get("instructions", [])
    alerts = item.get("alerts", [])
    combined = " \n ".join([prep] + inst + alerts)
    
    # Check "Externe (CLSC...)" "Non disponible"
    if re.search(r"Externe\s*\(CLSC[^)]*\)\s*Non\s*disponible|Non\s+disponible\s+(?:en|pour|pour\s+l[\'\’])\s*externe|Prélèvement\s+à\s+ne\s+faire\s+qu[\'\’]à\s+l[\'\’]hôpital", combined, re.IGNORECASE):
        return {
            "is_incompatible": True,
            "type": "NON_DISPO_EXTERNE",
            "badge": "🚫 Non dispo en externe",
            "badge_class": "bg-rose-50 text-rose-700 border-rose-200",
            "reason": "Analyse non réalisable en externe ou réservée au milieu hospitalier."
        }
        
    # Check Ice (exclude explicit negative phrases like "ne pas mettre sur glace")
    if re.search(r"\b(glace|glacée|glacées|ice)\b", combined, re.IGNORECASE) and not re.search(r"ne\s+pas\s+mettre\s+sur\s+(?:la\s+)?glace|pas\s+nécessaire", combined, re.IGNORECASE):
        return {
            "is_incompatible": True,
            "type": "SUR_GLACE",
            "badge": "🧊 Sur glace",
            "badge_class": "bg-sky-50 text-sky-700 border-sky-200",
            "reason": "Spécimen nécessitant un transport ou maintien sur glace."
        }
        
    # Check Decant
    if re.search(r"d[eé]cant|double\s+centrifug|congeler\s+imm[eé]diatement", combined, re.IGNORECASE) and not re.search(r"ne\s+pas\s+(?:centrifuger|congeler)", combined, re.IGNORECASE):
        return {
            "is_incompatible": True,
            "type": "DECANTE_CONGELE",
            "badge": "🔄 Décantation requise",
            "badge_class": "bg-amber-50 text-amber-700 border-amber-200",
            "reason": "Spécimen nécessitant une centrifugation, décantation ou congélation immédiate."
        }

    return {"is_incompatible": False, "type": None, "badge": None, "badge_class": None, "reason": None}

# Comprehensive Specimen & Tube Definitions
TUBE_DEFINITIONS = {
    # 1. BLOOD SPECIMENS (CLSI H3-A6 Standard Order of Draw)
    "HEMOCULTURE": {
        "order": 1,
        "specimen_type": "Sang",
        "name_fr": "Flacons d'hémoculture (Aérobie + Anaérobie)",
        "pediatric_name_fr": "Flacon d'hémoculture pédiatrique",
        "color_code": "#D97706", # Amber
        "cap_color_name": "Jaune / Vert / Rose",
        "additive": "Bouillon de culture SPS + Résine neutralisante",
        "max_volume": "8-10 mL par flacon (adulte) / 1-3 mL (pédiatrique)",
        "special_instructions": "Désinfection cutanée rigoureuse à la chlorhexidine 2%. Prélever impérativement en 1er lieu."
    },
    "CITRATE": {
        "order": 2,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Bleu pâle (Citrate 3.2%)",
        "pediatric_name_fr": "Microtube Bouchon Bleu pâle (Citrate)",
        "color_code": "#0284C7", # Sky Blue
        "cap_color_name": "Bleu pâle",
        "additive": "Citrate de sodium 3.2% (ratio 1:9)",
        "max_volume": "2.7 mL ou 4.5 mL",
        "special_instructions": "CRITIQUE : Remplir impérativement jusqu'au trait noir (ratio sang/anticoagulant 9:1). Homogénéiser doucement (3-4 inversions)."
    },
    "SERUM_GEL": {
        "order": 3,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Doré / Or (Gel séparateur + Activateur)",
        "pediatric_name_fr": "Microtube Bouchon Doré (Gel séparateur)",
        "color_code": "#CA8A04", # Gold
        "cap_color_name": "Doré / Or",
        "additive": "Silice activateur de caillot + Gel polymère (SST)",
        "max_volume": "5.0 mL",
        "special_instructions": "Laisser coaguler 30 minutes à la verticale avant centrifugation. 5 inversions."
    },
    "SERUM_PLAIN": {
        "order": 3,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Rouge (Sec sans gel)",
        "pediatric_name_fr": "Microtube Bouchon Rouge",
        "color_code": "#DC2626", # Red
        "cap_color_name": "Rouge",
        "additive": "Activateur de caillot sans gel (Silice)",
        "max_volume": "6.0 mL",
        "special_instructions": "Dosages médicamenteux spécifiques ou sérologies sans gel. 5 inversions."
    },
    "HEPARINE_LITHIUM": {
        "order": 4,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Menthe (Héparine de Lithium + Gel PST)",
        "pediatric_name_fr": "Microtube Bouchon Vert (Héparine-Lithium)",
        "color_code": "#059669", # Mint
        "cap_color_name": "Menthe / Vert clair",
        "additive": "Héparine de lithium (68 UI) + Gel séparateur PST",
        "max_volume": "4.5 mL",
        "special_instructions": "Tube principal de biochimie de routine au CHU de Québec. 8 à 10 inversions douces."
    },
    "HEPARINE_SODIUM": {
        "order": 4,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Vert foncé (Héparine de Sodium)",
        "pediatric_name_fr": "Microtube Bouchon Vert",
        "color_code": "#15803D", # Dark green
        "cap_color_name": "Vert foncé",
        "additive": "Héparine de sodium (HepNa)",
        "max_volume": "6.0 mL",
        "special_instructions": "Utilisé pour la cytogénétique, HLA ou biochimie spécialisée. 8 à 10 inversions."
    },
    "EDTA": {
        "order": 5,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Lavande / Mauve (K2-EDTA)",
        "pediatric_name_fr": "Microtube Bouchon Lavande (K2-EDTA)",
        "color_code": "#7C3AED", # Purple
        "cap_color_name": "Lavande / Mauve",
        "additive": "K2-EDTA (anticoagulant hématologie)",
        "max_volume": "4.0 mL",
        "special_instructions": "Homogénéiser immédiatement (8-10 inversions). Ne jamais prélever avant les tubes de biochimie (risque de fausse hyperkaliémie)."
    },
    "EDTA_ROSE": {
        "order": 5,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Rose (K2-EDTA - Banque de sang)",
        "pediatric_name_fr": "Microtube Bouchon Rose (Banque de sang)",
        "color_code": "#DB2777", # Pink
        "cap_color_name": "Rose",
        "additive": "K2-EDTA haute pureté",
        "max_volume": "6.0 mL",
        "special_instructions": "Tube dédié Banque de sang. Identification stricte et double vérification d'identité au chevet du patient."
    },
    "ROYAL_BLUE": {
        "order": 5,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Bleu Royal (Oligo-éléments / Métaux)",
        "pediatric_name_fr": "Tube Bouchon Bleu Royal",
        "color_code": "#1E40AF", # Royal Blue
        "cap_color_name": "Bleu Royal",
        "additive": "K2-EDTA certifié sans trace de métaux lourds",
        "max_volume": "6.0 mL",
        "special_instructions": "Purger la ligne veineuse avant le prélèvement pour éviter toute contamination métallique."
    },
    "FLUORURE": {
        "order": 6,
        "specimen_type": "Sang",
        "name_fr": "Tube Bouchon Gris (Fluorure de Sodium / Oxalate)",
        "pediatric_name_fr": "Microtube Bouchon Gris",
        "color_code": "#475569", # Slate
        "cap_color_name": "Gris",
        "additive": "Fluorure de sodium (antiglycolytique) + Oxalate de potassium",
        "max_volume": "4.0 mL",
        "special_instructions": "Inhibiteur de la glycolyse. Utilisé pour lactate strict, alcoolémie médico-légale."
    },
    "GAZ_SERINGUE": {
        "order": 7,
        "specimen_type": "Sang",
        "name_fr": "Seringue héparinée pour Gaz sanguins",
        "pediatric_name_fr": "Seringue héparinée pour Gaz sanguins",
        "color_code": "#0891B2", # Cyan
        "cap_color_name": "Seringue spécifique",
        "additive": "Héparine de lithium lyophilisée équilibrée",
        "max_volume": "1-2 mL",
        "special_instructions": "CRITIQUE : Chasser immédiatement les bulles d'air, boucher et acheminer au laboratoire sur glace fondante en < 15-30 min."
    },

    # 2. URINE SPECIMENS (Prélèvements Urinaires)
    "URINE_STERILE": {
        "order": 10,
        "specimen_type": "Urine",
        "name_fr": "Contenant stérile pour Urine (Bouchon Orange)",
        "pediatric_name_fr": "Sac collecteur pédiatrique / Contenant stérile",
        "color_code": "#F97316", # Orange
        "cap_color_name": "Bouchon Orange",
        "additive": "Stérile sans agent de conservation (Culture, ECBU, PCR)",
        "max_volume": "100 mL (10-20 mL requis)",
        "special_instructions": "Prélèvement d'urine mi-jet après toilette génitale soigneuse. Acheminer rapidement ou réfrigérer à 4°C."
    },
    "URINE_ROUTINE": {
        "order": 11,
        "specimen_type": "Urine",
        "name_fr": "Tube conique / Contenant pour culot urinaire (Bouchon Jaune)",
        "pediatric_name_fr": "Contenant pour urine (Bouchon Jaune)",
        "color_code": "#EAB308", # Yellow
        "cap_color_name": "Bouchon Jaune",
        "additive": "Non stérile (Sommaire et microscopie / SMU / Dépistage)",
        "max_volume": "10-20 mL",
        "special_instructions": "Prélèvement d'urine spontané (miction simple). Utilisé pour SMU, biochimie mictionnelle et toxicologie."
    },
    "URINE_24H": {
        "order": 12,
        "specimen_type": "Urine",
        "name_fr": "Cruche de collecte des urines de 24 heures",
        "pediatric_name_fr": "Cruche de collecte des urines de 24h",
        "color_code": "#854D0E", # Brown / Amber
        "cap_color_name": "Cruche 24h",
        "additive": "Selon l'analyse (Sans préservatif ou avec acide/base)",
        "max_volume": "2 à 3 Litres",
        "special_instructions": "Jeter la 1ère miction du matin, puis recueillir toutes les urines pendant 24h jusqu'au lendemain matin inclus. Conserver au frais."
    },

    # 3. FECAL SPECIMENS (Prélèvements Fécaux / Selles)
    "SELLES_STERILE": {
        "order": 20,
        "specimen_type": "Selles",
        "name_fr": "Contenant stérile pour Selles (Bouchon Orange)",
        "pediatric_name_fr": "Contenant stérile pour Selles (Bouchon Orange)",
        "color_code": "#EA580C", # Vivid Orange
        "cap_color_name": "Bouchon Orange",
        "additive": "Stérile sans milieu liquide (C. difficile, Calprotectine, Élastase, H. pylori)",
        "max_volume": "Pot 60 mL (remplir au tiers ~5-10 g)",
        "special_instructions": "Recueillir les selles sans contact avec l'urine ni l'eau de la cuvette. Ne pas remplir le contenant à plus du tiers."
    },
    "SELLES_CARY_BLAIR": {
        "order": 21,
        "specimen_type": "Selles",
        "name_fr": "Milieu de transport Cary-Blair / EPT (Coproculture)",
        "pediatric_name_fr": "Milieu de transport Cary-Blair (Bouchon Blanc)",
        "color_code": "#64748B", # Slate / White Cap styling
        "cap_color_name": "Bouchon Blanc (Cary-Blair)",
        "additive": "Milieu liquide EPT (Cary-Blair) - GRM 101441",
        "max_volume": "Tube 30 mL avec milieu liquide rose",
        "special_instructions": "Coproculture bactérienne. Prélever un fragment de selle avec la cuillère intégrée jusqu'au trait indicateur. Bien revisser le bouchon blanc."
    },
    "SELLES_SAF": {
        "order": 22,
        "specimen_type": "Selles",
        "name_fr": "Milieu de transport SAF (Parasitologie des selles)",
        "pediatric_name_fr": "Milieu de transport SAF",
        "color_code": "#9333EA", # Purple
        "cap_color_name": "Bouchon SAF",
        "additive": "Fixateur Sodium Acétate Formol (SAF)",
        "max_volume": "Tube avec liquide fixateur",
        "special_instructions": "Recherche de parasites, kystes et amibes. Émulsionner les selles dans le liquide SAF jusqu'au trait."
    },
    "SELLES_FIT": {
        "order": 23,
        "specimen_type": "Selles",
        "name_fr": "Tube de dépistage de sang occulte fécal (RSOSi / FIT)",
        "pediatric_name_fr": "Tube de dépistage RSOSi",
        "color_code": "#E11D48", # Rose / Red
        "cap_color_name": "Tube RSOSi",
        "additive": "Tampon stabilisateur d'hémoglobine humaine",
        "max_volume": "Dispositif avec tige striée",
        "special_instructions": "Piquer la selle en plusieurs points avec la tige striée et refermer hermétiquement."
    },

    # 4. SWABS, CSF & OTHER SPECIMENS
    "SPECIMEN_LCR": {
        "order": 30,
        "specimen_type": "LCR",
        "name_fr": "Tubes stériles pour LCR (Ponction lombaire)",
        "pediatric_name_fr": "Tubes stériles pour LCR",
        "color_code": "#0284C7",
        "cap_color_name": "Tubes LCR #1 à #4",
        "additive": "Tubes stériles coniques numérotés",
        "max_volume": "1 à 2 mL par tube",
        "special_instructions": "Acheminer immédiatement à la main au laboratoire (< 15-30 min)."
    },
    "SPECIMEN_SWAB": {
        "order": 31,
        "specimen_type": "Écouvillon",
        "name_fr": "Écouvillon de transport (UTM-RT / ESwab / M40)",
        "pediatric_name_fr": "Écouvillon pédiatrique",
        "color_code": "#0D9488", # Teal
        "cap_color_name": "Écouvillon",
        "additive": "Milieu liquide de transport",
        "max_volume": "1 tige",
        "special_instructions": "Frotter la zone cible et casser la tige dans le milieu de transport."
    },
    "SPECIMEN_DIVERS": {
        "order": 40,
        "specimen_type": "Divers",
        "name_fr": "Contenant spécialisé / Divers",
        "pediatric_name_fr": "Contenant spécialisé",
        "color_code": "#64748B",
        "cap_color_name": "Contenant spécifique",
        "additive": "Selon l'analyse",
        "max_volume": "Variable",
        "special_instructions": "Consulter la fiche spécifique pour les consignes de prélèvement."
    }
}

def classify_container(container_str, analysis_name="", pid="", thematic="", specimen=""):
    """
    Deterministically classify a Gustav container string and analysis context
    into standardized specimen and tube categories (Blood, Urine, Stool, Swabs, CSF, etc.).
    """
    c_lower = (container_str or "").lower().strip()
    name_lower = (analysis_name or "").lower().strip()
    pid_lower = (pid or "").lower().strip()
    them_lower = (thematic or "").lower().strip()
    spec_lower = (specimen or "").lower().strip()

    # 1. SWABS & TRANSPORT MEDIA (Check early so Tige M40 bouchon rouge is not misclassified as SERUM_PLAIN)
    if any(k in c_lower for k in ["utm", "m6", "m40", "amies", "eswab", "mswab", "tige veloutée", "tige veloutee", "tige sèche", "tige seche", "tige amies"]):
        return "SPECIMEN_SWAB"
    if "tige" in c_lower and not any(k in c_lower for k in ["cruche", "tube", "bouchon"]):
        return "SPECIMEN_SWAB"

    # 2. FECAL SPECIFIC TRANSPORT MEDIA
    if "cary" in c_lower or "ept" in c_lower:
        return "SELLES_CARY_BLAIR"
    if "saf" in c_lower:
        return "SELLES_SAF"
    if any(k in c_lower for k in ["rsosi", "sang occulte"]):
        return "SELLES_FIT"

    # 3. CSF SPECIFIC CONTAINERS
    if "lcr" in c_lower or "céphalo-rachidien" in c_lower or "cephalo-rachidien" in c_lower:
        return "SPECIMEN_LCR"

    # 4. BLOOD SPECIMENS STRICT
    # Blood gas syringe
    if any(k in c_lower for k in ["seringue", "gaz"]):
        return "GAZ_SERINGUE"

    # Blood cultures
    if any(k in c_lower for k in ["hemoculture", "hémoculture", "bactec", "bact-alert", "bouteille d'hémoculture", "bouteille d’hémoculture", "bouteilles d'hémoculture"]):
        return "HEMOCULTURE"

    # Royal Blue
    if "bleu royal" in c_lower:
        return "ROYAL_BLUE"

    # Citrate / Light Blue (ensure not royal blue or orange)
    if any(k in c_lower for k in ["bleu (citrate", "citrate", "bleu pâ"]) or ("bleu" in c_lower and "royal" not in c_lower and "orange" not in c_lower and "m40" not in c_lower):
        return "CITRATE"

    # Pink / Rose (Blood bank - ensure not Vert_HepNa_Collant_rose)
    if "rose" in c_lower and "vert_hepna_collant_rose" not in c_lower and "vert" not in c_lower:
        return "EDTA_ROSE"

    # Lavender / Mauve (EDTA)
    if any(k in c_lower for k in ["lavande", "edta", "mauve"]):
        return "EDTA"

    # Sodium Heparin (Vert HepNa)
    if any(k in c_lower for k in ["vert (hepna)", "heparine_sodium", "hepna", "vert foncé", "vert fonce", "vert héparine sodium", "vert heparine sodium", "vert_hepna"]):
        return "HEPARINE_SODIUM"

    # Lithium Heparin (Menthe / Vert lime / HepLi)
    if any(k in c_lower for k in ["menthe", "pst", "heparine_lithium", "héparine de lithium", "vert lime (hepli)"]) or ("vert" in c_lower and "sodium" not in c_lower and "hepna" not in c_lower and "cary" not in c_lower and "verre" not in c_lower and "rose" not in c_lower):
        return "HEPARINE_LITHIUM"

    # Gold / Or (Serum Gel SST - ensure not orange)
    if "orange" not in c_lower:
        if bool(re.search(r"\b(or|doré|dore|sst)\b", c_lower)) or "or (activateur" in c_lower or "gel activateur" in c_lower or "vert lime (hepli) ou or" in c_lower:
            return "SERUM_GEL"

    # Red / Rouge (Serum plain without gel)
    if any(k in c_lower for k in ["rouge (activateur", "sec sans gel", "rouge (sec", "tube bouchon rouge"]) or (c_lower == "rouge" or c_lower == "tube rouge"):
        return "SERUM_PLAIN"

    # Grey / Gris (Fluoride / Oxalate)
    if any(k in c_lower for k in ["gris", "fluorure", "oxalate"]):
        return "FLUORURE"

    # 5. URINE SPECIFIC CONTAINERS
    # 24h Urine jugs
    if any(k in c_lower for k in ["cruche", "24h", "24 h", "24 heures"]):
        return "URINE_24H"

    # Routine urine containers (yellow cap / conical tube)
    if any(k in c_lower for k in ["culot", "conique bouchon jaune", "pour culot", "contenant non stérile (bouchon jaune)", "pour urine"]):
        return "URINE_ROUTINE"

    # 6. DUAL / GENERIC CONTAINERS (e.g. Bouchon orange, Contenant stérile, Tube conique 15 ml, Cobas-PCR)
    # Check context words using whole words or specific identifiers
    is_stool_context = (
        any(w in spec_lower for w in ["selle", "fecal", "fécal"]) or
        any(re.search(r"\b" + re.escape(w) + r"\b", f"{name_lower} {them_lower}") for w in ["selle", "selles", "fécal", "fecal", "copro", "c. diff", "difficile", "calprotectine", "élastase fécale", "elastase fecale"]) or
        pid_lower in ["closd", "cdtox", "copro", "calpr", "elast"]
    )
    is_urine_context = (
        any(w in spec_lower for w in ["urine", "urinaire"]) or
        any(re.search(r"\b" + re.escape(w) + r"\b", f"{name_lower} {them_lower}") for w in ["urine", "urines", "urinaire", "urinaires", "ecbu", "sommaire", "microscopie", "miction"]) or
        pid_lower in ["anuri", "curi", "uruc", "smu"] or
        "cobas-pcr urine" in c_lower
    )
    is_lcr_context = (
        "lcr" in spec_lower or "céphalo-rachidien" in spec_lower or "cephalo-rachidien" in spec_lower or
        any(re.search(r"\b" + re.escape(w) + r"\b", f"{name_lower} {them_lower}") for w in ["lcr", "céphalo-rachidien", "cephalo-rachidien"]) or
        pid_lower in ["lcr", "plcr"]
    )

    if "orange" in c_lower or "stérile" in c_lower or "contenant" in c_lower or "cobas-pcr" in c_lower:
        if is_stool_context:
            return "SELLES_STERILE"
        if is_urine_context:
            return "URINE_STERILE"
        if is_lcr_context:
            return "SPECIMEN_LCR"
        return "SPECIMEN_DIVERS"

    # 7. FALLBACKS BASED ON SPECIMEN / NAME / PID
    if is_stool_context:
        return "SELLES_STERILE"
    if is_urine_context:
        if any(k in name_lower for k in ["24 h", "24 heures", "24h"]) or "24" in spec_lower:
            return "URINE_24H"
        return "URINE_ROUTINE"
    if is_lcr_context:
        return "SPECIMEN_LCR"

    # Blood fallbacks by test name / keywords
    if any(k in name_lower for k in ["formule sanguine", "plaquettes", "reticulocytes", "frottis", "hba1c", "vitesse de sédimentation"]):
        return "EDTA"
    if any(k in name_lower for k in ["inr", "quick", "ptt", "tca", "fibrinogene", "d-dimere"]):
        return "CITRATE"
    if any(k in name_lower for k in ["troponine", "electrolytes", "creatinine", "uree", "bilirubine", "alt", "ast", "tsh", "acide urique"]):
        return "HEPARINE_LITHIUM"

    return "SPECIMEN_DIVERS"

def search_analyses(query, limit=15):
    """
    Deterministic instant search with prefix priority, synonym expansion,
    clinical panels, and fuzzy matching.
    """
    catalog = load_catalog()

    if not query or len(query.strip()) == 0:
        top_pids = ["fsc", "elec", "uree", "crea", "itrop", "alt", "ptrin", "ptt", "tsh", "ferri", "hba1c", "hc", "gly", "crp", "lacc"]
        results = []
        for pid in top_pids:
            if pid in catalog:
                item = catalog[pid]
                results.append({
                    "type": "analysis",
                    "pid": pid,
                    "name": item["name"],
                    "category": item.get("thematic", "Manuel des prélèvements"),
                    "url": item.get("url", ""),
                    "external_restriction": get_external_restriction(pid, item)
                })
        return results

    q_norm = normalize_str(query)
    results = []
    seen_pids = set()

    # 1. Check clinical panels
    for panel_id, panel in CLINICAL_PANELS.items():
        p_name_norm = normalize_str(panel["name"])
        if any(q_norm in normalize_str(kw) or normalize_str(kw) in q_norm for kw in panel["keywords"]) or q_norm in p_name_norm:
            results.append({
                "type": "panel",
                "panel_id": panel_id,
                "name": f"⭐ Panel: {panel['name']}",
                "description": panel["description"],
                "pids": panel["pids"]
            })

    # 2. Check synonyms
    if q_norm in SYNONYMS_TO_PID:
        target_pid = SYNONYMS_TO_PID[q_norm]
        if target_pid in catalog and target_pid not in seen_pids:
            item = catalog[target_pid]
            results.append({
                "type": "analysis",
                "pid": target_pid,
                "name": item["name"],
                "category": item.get("thematic", "Manuel des prélèvements"),
                "url": item.get("url", ""),
                "external_restriction": get_external_restriction(target_pid, item)
            })
            seen_pids.add(target_pid)

    # 3. Exact PID matches
    if q_norm in catalog and q_norm not in seen_pids:
        item = catalog[q_norm]
        results.append({
            "type": "analysis",
            "pid": q_norm,
            "name": item["name"],
            "category": item.get("thematic", "Manuel des prélèvements"),
            "url": item.get("url", ""),
            "external_restriction": get_external_restriction(q_norm, item)
        })
        seen_pids.add(q_norm)

    # 4. Search in Catalog (Prefix -> Substring -> Keywords)
    prefix_matches = []
    substring_matches = []
    keyword_matches = []

    for pid, item in catalog.items():
        if pid in seen_pids:
            continue
        name_norm = normalize_str(item.get("name", ""))
        
        if name_norm.startswith(q_norm):
            prefix_matches.append(item)
        elif q_norm in name_norm:
            substring_matches.append(item)
        else:
            for kw in item.get("keywords", []):
                if q_norm in normalize_str(kw):
                    keyword_matches.append(item)
                    break

    for item in (prefix_matches + substring_matches + keyword_matches):
        pid = item["pid"]
        if pid not in seen_pids:
            results.append({
                "type": "analysis",
                "pid": pid,
                "name": item["name"],
                "category": item.get("thematic", "Manuel des prélèvements"),
                "url": item.get("url", ""),
                "external_restriction": get_external_restriction(pid, item)
            })
            seen_pids.add(pid)
            if len(results) >= limit:
                break

    return results[:limit]

def calculate_tubes(selected_pids, site="Tous les sites", is_pediatric=False):
    """
    Deterministic tube consolidation and calculation engine.
    Groups shared analyses into minimum number of tubes and sorts by Order of Draw.
    """
    catalog = load_catalog()

    if not selected_pids:
        return {
            "total_tubes": 0,
            "total_bottles": 0,
            "total_urine": 0,
            "total_fecal": 0,
            "total_other": 0,
            "total_containers": 0,
            "tubes": [],
            "special_instructions": [],
            "analyses_included": [],
            "external_incompatibilities": []
        }

    # Deduplicate and expand panel references
    all_pids = []
    for item_id in selected_pids:
        if item_id in CLINICAL_PANELS:
            all_pids.extend(CLINICAL_PANELS[item_id]["pids"])
        else:
            all_pids.append(item_id)
    
    unique_pids = []
    seen = set()
    for p in all_pids:
        if p in catalog and p not in seen:
            unique_pids.append(p)
            seen.add(p)

    grouped_tubes = defaultdict(lambda: {
        "analyses": [],
        "alerts": set(),
        "quantities": [],
        "pediatric_info": []
    })

    structured_global_alerts = []
    analyses_summary = []

    for pid in unique_pids:
        item = catalog[pid]
        analyses_summary.append({
            "pid": pid,
            "name": item["name"],
            "url": item.get("url", "")
        })

        # Check for preparation (e.g. à jeun)
        prep = item.get("preparation", "").strip()
        if prep and "sans particularit" not in prep.lower() and "valeur critique" not in prep.lower():
            # Clean common prefixes
            clean_prep = prep.replace("Commentaires / Instructions particulières :", "").replace("Commentaires / Instructions particulìeres :", "").replace("Fiche complète", "").strip()
            if clean_prep:
                if "jeun" in clean_prep.lower():
                    structured_global_alerts.append(f"🍽️ {item['name']} : {clean_prep}")
                else:
                    structured_global_alerts.append(f"📋 {item['name']} : {clean_prep}")

        for al in item.get("alerts", []):
            al_clean = al.strip()
            if any(k in al_clean.lower() for k in ["glace", "lumière", "délai", "rapidement", "achemin", "attention", "soluté", "minutes", "heure"]):
                if "glace" in al_clean.lower():
                    structured_global_alerts.append(f"🧊 {item['name']} : {al_clean}")
                elif "lumière" in al_clean.lower():
                    structured_global_alerts.append(f"🌑 {item['name']} : {al_clean}")
                elif "minute" in al_clean.lower() or "délai" in al_clean.lower() or "rapidement" in al_clean.lower():
                    structured_global_alerts.append(f"⏱️ {item['name']} : {al_clean}")
                else:
                    structured_global_alerts.append(f"⚠️ {item['name']} : {al_clean}")

        # Determine container for site
        chosen_container_str = ""
        chosen_qty = ""
        chosen_count = "1"
        chosen_specimen = item.get("specimen_type", "")
        
        for c in item.get("containers", []):
            c_sites = normalize_str(c.get("sites", ""))
            site_norm = normalize_str(site)
            if site_norm in c_sites or "tous les sites" in c_sites:
                chosen_container_str = c.get("container", "")
                chosen_qty = c.get("quantity", "")
                chosen_count = c.get("count", "1")
                if c.get("specimen"):
                    chosen_specimen = c.get("specimen")
                break
        
        if not chosen_container_str and item.get("containers"):
            chosen_container_str = item["containers"][0].get("container", "")
            chosen_qty = item["containers"][0].get("quantity", "")
            chosen_count = item["containers"][0].get("count", "1")
            if item["containers"][0].get("specimen"):
                chosen_specimen = item["containers"][0].get("specimen")

        cat_key = classify_container(chosen_container_str, item["name"], pid, item.get("thematic", ""), chosen_specimen)

        # Site adjustments (e.g. HSS using serum gel)
        if ("hss" in normalize_str(site) or "portneuf" in normalize_str(site)) and cat_key == "HEPARINE_LITHIUM":
            for c in item.get("containers", []):
                if "hss" in normalize_str(c.get("sites", "")) and "or" in normalize_str(c.get("container", "")):
                    cat_key = "SERUM_GEL"
                    break

        grouped_tubes[cat_key]["analyses"].append({
            "pid": pid,
            "name": item["name"],
            "raw_container": chosen_container_str,
            "raw_count": chosen_count,
            "quantity": chosen_qty,
            "url": item.get("url", "")
        })
        
        for inst in item.get("instructions", []):
            grouped_tubes[cat_key]["alerts"].add(inst)

        if item.get("pediatric_microtubes"):
            for pc in item["pediatric_microtubes"]:
                grouped_tubes[cat_key]["pediatric_info"].append(pc.get("description", ""))

    # Sort categories by Order of Draw / Specimen Type
    tube_results = []
    total_blood_tubes = 0
    total_bottles_count = 0
    total_urine_count = 0
    total_fecal_count = 0
    total_other_count = 0

    sorted_categories = sorted(
        [k for k in grouped_tubes.keys() if k is not None],
        key=lambda k: TUBE_DEFINITIONS.get(k, {}).get("order", 99)
    )

    for cat_key in sorted_categories:
        tube_def = TUBE_DEFINITIONS.get(cat_key, TUBE_DEFINITIONS["SPECIMEN_DIVERS"])
        group_data = grouped_tubes[cat_key]
        spec_type = tube_def.get("specimen_type", "Divers")

        if cat_key == "HEMOCULTURE":
            if is_pediatric:
                tube_count = 1
                container_display_name = tube_def["pediatric_name_fr"]
                unit_label = "Flacon pédiatrique"
            else:
                tube_count = 2
                container_display_name = tube_def["name_fr"]
                unit_label = "Paire de flacons (2)"
            total_bottles_count += tube_count
        else:
            nominal_cap = PEDIATRIC_MICRO_CAPACITY if is_pediatric else TUBE_NOMINAL_CAPACITY.get(cat_key, 5.0)
            
            if is_pediatric:
                # 1. Check explicit pediatric microtubes count in Gustav
                max_ped_cnt = 0
                for a in group_data["analyses"]:
                    pid_a = a["pid"]
                    item_a = catalog.get(pid_a, {})
                    for pm in item_a.get("pediatric_microtubes", []):
                        try:
                            c = int(pm.get("count", "1"))
                            if c > max_ped_cnt:
                                max_ped_cnt = c
                        except ValueError:
                            pass
                
                if max_ped_cnt > 0:
                    tube_count = max_ped_cnt
                else:
                    max_single_vol = max([parse_volume_ml(a.get("quantity", "")) for a in group_data["analyses"]] + [0.0])
                    tube_count = max(1, math.ceil(max_single_vol / nominal_cap)) if max_single_vol > 0 else 1

                container_display_name = tube_def["pediatric_name_fr"]
            else:
                # Adult mode
                # 1. Max explicit count in Gustav container table (e.g. 2, 3, 8 tubes)
                max_explicit = 1
                for a in group_data["analyses"]:
                    try:
                        cnt = int(a.get("raw_count", "1"))
                        if cnt > max_explicit:
                            max_explicit = cnt
                    except ValueError:
                        pass
                
                # 2. Cumulative volume-based count (for blood tubes)
                if spec_type == "Sang":
                    total_vol = 0.0
                    has_routine_base = False
                    for a in group_data["analyses"]:
                        vol = parse_volume_ml(a.get("quantity", ""))
                        if vol > 1.0:
                            total_vol += vol
                        elif vol > 0.0:
                            if not has_routine_base:
                                total_vol += vol
                                has_routine_base = True
                            else:
                                total_vol += 0.2
                        else:
                            if not has_routine_base:
                                total_vol += 1.0
                                has_routine_base = True
                            else:
                                total_vol += 0.2
                    
                    vol_tubes = math.ceil(total_vol / nominal_cap) if total_vol > 0 else 1
                    tube_count = max(max_explicit, vol_tubes, 1)

                    if vol_tubes > 1 and total_vol > nominal_cap:
                        volume_alert = f"Volume sanguin total requis ({total_vol:g} mL) supérieur à la contenance d'un tube standard ({nominal_cap:g} mL) → {tube_count} tubes nécessaires."
                        group_data["alerts"].add(volume_alert)
                else:
                    # Non-blood specimen: count containers directly
                    tube_count = max(max_explicit, 1)

                container_display_name = tube_def["name_fr"]

            # Assign correct unit label and increment respective counter
            if spec_type == "Sang":
                unit_label = ("Microtube" if tube_count == 1 else "Microtubes") if is_pediatric else ("Tube" if tube_count == 1 else "Tubes")
                total_blood_tubes += tube_count
            elif spec_type == "Urine":
                unit_label = "Cruche 24h" if cat_key == "URINE_24H" else ("Contenant" if tube_count == 1 else "Contenants")
                total_urine_count += tube_count
            elif spec_type == "Selles":
                unit_label = "Pot stérile" if cat_key == "SELLES_STERILE" else ("Tube" if tube_count == 1 else "Tubes")
                total_fecal_count += tube_count
            elif spec_type == "Écouvillon":
                unit_label = "Écouvillon" if tube_count == 1 else "Écouvillons"
                total_other_count += tube_count
            elif spec_type == "LCR":
                unit_label = "Tube LCR" if tube_count == 1 else "Tubes LCR"
                total_other_count += tube_count
            else:
                unit_label = "Contenant" if tube_count == 1 else "Contenants"
                total_other_count += tube_count

        # Clean specific alerts
        clean_alerts = []
        for al in group_data["alerts"]:
            if len(al) > 5 and "Contenant(s)" not in al and "Jour même" not in al and "Valeur" not in al:
                clean_alerts.append(al)

        # Consolidation explanation
        consolidation_note = ""
        if len(group_data["analyses"]) > 1:
            if spec_type == "Sang" and tube_count == 1 and cat_key in ["HEPARINE_LITHIUM", "SERUM_GEL", "EDTA"]:
                consolidation_note = f"Échantillon partagé sur automate : les {len(group_data['analyses'])} analyses de routine sont exécutées à partir du même tube (seuls quelques microlitres par test sont prélevés par l'automate)."
            elif spec_type == "Sang" and tube_count > 1 and not is_pediatric:
                consolidation_note = f"Volume cumulé requis ({total_vol:g} mL) nécessitant {tube_count} tubes."
            elif spec_type in ["Urine", "Selles"]:
                consolidation_note = f"Analyses combinées : ces {len(group_data['analyses'])} analyses sont réalisées à partir du même contenant."

        tube_results.append({
            "category_key": cat_key,
            "specimen_type": spec_type,
            "order_step": tube_def["order"],
            "name": container_display_name,
            "cap_color_name": tube_def["cap_color_name"],
            "color_code": tube_def["color_code"],
            "additive": tube_def["additive"],
            "max_volume": tube_def["max_volume"],
            "tube_count": tube_count,
            "unit_label": unit_label,
            "special_instructions": tube_def["special_instructions"],
            "specific_alerts": clean_alerts,
            "consolidation_note": consolidation_note,
            "analyses": group_data["analyses"],
            "pediatric_notes": list(set(group_data["pediatric_info"])) if is_pediatric else []
        })

    # Clean global alerts deduplicated
    seen_alerts = set()
    dedup_alerts = []
    for al in structured_global_alerts:
        if al not in seen_alerts:
            dedup_alerts.append(al)
            seen_alerts.add(al)

    # Compute external prelevement incompatibilities (on ice, decant, hospital only)
    external_incompatibilities = []
    for pid in unique_pids:
        item = catalog[pid]
        restr = get_external_restriction(pid, item)
        if restr.get("is_incompatible"):
            external_incompatibilities.append({
                "pid": pid,
                "name": item.get("name", pid.upper()),
                "type": restr["type"],
                "badge": restr["badge"],
                "badge_class": restr["badge_class"],
                "reason": restr["reason"],
                "url": item.get("url", "")
            })

    total_all_containers = total_blood_tubes + total_bottles_count + total_urine_count + total_fecal_count + total_other_count

    return {
        "total_tubes": total_blood_tubes,
        "total_bottles": total_bottles_count,
        "total_urine": total_urine_count,
        "total_fecal": total_fecal_count,
        "total_other": total_other_count,
        "total_containers": total_all_containers,
        "tubes": tube_results,
        "special_instructions": dedup_alerts,
        "analyses_included": analyses_summary,
        "external_incompatibilities": external_incompatibilities,
        "site_applied": site,
        "is_pediatric": is_pediatric
    }
