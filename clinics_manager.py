"""
clinics_manager.py - Directory & Search Management for SIL-P Clinics (Microsoft Fabric Dataset).

Provides:
1. In-memory loading and caching of the 19,600+ SIL-P healthcare institutions and clinics from data/silp_clinics.json.
2. Ultra-fast (< 2ms) multi-attribute search (SIL-P ID, Clinic Name, Address, City, Postal Code, Facility).
3. Faceted filtering by Site (hospital complex/external) and Type (Admission / External / Inscribed).
4. Diacritic-insensitive and ranked relevance matching.
"""

import os
import json
import re
import unicodedata
import threading
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SILP_CLINICS_FILE = os.path.join(DATA_DIR, "silp_clinics.json")

_file_lock = threading.Lock()
_CLINICS_CACHE: Optional[List[Dict[str, Any]]] = None
_CLINICS_MTIME: float = 0
_CLINICS_BY_ID: Dict[str, Dict[str, Any]] = {}

TYPE_DESCRIPTIONS: Dict[str, str] = {
    "A": "A - Admis sans ADT",
    "E": "E - Enregistré (Externe / Clinique privée / GMF)",
    "H": "H - Admis (Hospitalisé ou hébergement)",
    "I": "I - Inscrit - Autre",
    "Q": "Q - Contrôle qualité",
    "R": "R - Recherche",
    "T": "T - Test",
    "U": "U - Inscrit - Urgent",
    "V": "V - Service sans frais",
    "X": "X - Annulation patient ou séjour",
    "Y": "Y - Inscrits - Urgent sans ADT",
    "Z": "Z - Services vendus"
}

def sanitize_clinic_name(name: Optional[str]) -> str:
    """
    Sanitizes and shortens a clinic name for high legibility on forms:
    1. Abbreviates 'Centre hospitalier' / 'Ctre hospitalier' to 'CH'.
    2. Strips trailing parentheses and their content (e.g. ' ( LEBOURGNEUF)' -> '').
    3. Cleans trailing punctuation and normalizes spacing.
    """
    if not name:
        return ""
    cleaned = str(name).strip()

    # 1. Abbreviate 'centre hospitalier' / 'ctre hospitalier' (case-insensitive)
    cleaned = re.sub(r'(?i)\b(centre|ctre)\s+hospitalier\b', 'CH', cleaned)

    # 2. Repeatedly remove trailing parentheses: e.g. '( LEBOURGNEUF)' or '(QUEBEC)'
    while re.search(r'\s*\([^)]*\)\s*$', cleaned):
        cleaned = re.sub(r'\s*\([^)]*\)\s*$', '', cleaned).strip()

    # 3. Clean any dangling trailing punctuation like ' -' or ' ,' or ' /'
    cleaned = re.sub(r'[\s\-,/]+$', '', cleaned).strip()

    # 4. Normalize spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def normalize_text(text: Optional[str]) -> str:
    """Normalize text by lowercasing, removing accents, punctuation, and multiple spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    clean = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    tokens = clean.split()
    return " ".join(tokens)

def _load_clinics() -> List[Dict[str, Any]]:
    """Loads and pre-indexes the SIL-P clinics dataset with pre-normalized search fields."""
    global _CLINICS_CACHE, _CLINICS_MTIME, _CLINICS_BY_ID

    if not os.path.exists(SILP_CLINICS_FILE):
        return []

    mtime = os.path.getmtime(SILP_CLINICS_FILE)
    if _CLINICS_CACHE is not None and mtime == _CLINICS_MTIME:
        return _CLINICS_CACHE

    with _file_lock:
        if _CLINICS_CACHE is not None and mtime == _CLINICS_MTIME:
            return _CLINICS_CACHE

        try:
            with open(SILP_CLINICS_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as e:
            print(f"[clinics_manager] Error reading {SILP_CLINICS_FILE}: {e}")
            return []

        processed = []
        by_id = {}
        for item in raw_data:
            c_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            site = str(item.get("site") or "").strip()
            city = str(item.get("city") or "").strip()
            postal_code = str(item.get("postal_code") or "").strip()
            address = str(item.get("address") or "").strip()
            facility = str(item.get("facility") or "").strip()
            c_type = str(item.get("type") or "").strip()

            entry = {
                "id": c_id,
                "name": name,
                "site": site,
                "city": city,
                "postal_code": postal_code,
                "address": address,
                "facility": facility,
                "type": c_type,
                "type_label": TYPE_DESCRIPTIONS.get(c_type, c_type),
                # Pre-normalized fields for fast search
                "_id_norm": c_id.lower().replace(" ", "").replace("-", ""),
                "_name_norm": normalize_text(name),
                "_city_norm": normalize_text(city),
                "_postal_norm": postal_code.lower().replace(" ", ""),
                "_address_norm": normalize_text(address),
                "_facility_norm": normalize_text(facility),
                "_search_blob": f"{c_id.lower()} {normalize_text(name)} {normalize_text(city)} {postal_code.lower().replace(' ', '')} {normalize_text(address)} {normalize_text(facility)}"
            }
            processed.append(entry)
            if c_id and c_id.lower() not in by_id:
                by_id[c_id.lower()] = entry

        _CLINICS_CACHE = processed
        _CLINICS_BY_ID = by_id
        _CLINICS_MTIME = mtime
        return _CLINICS_CACHE

def get_clinic_by_id(clinic_id: str) -> Optional[Dict[str, Any]]:
    """Returns a single clinic by SIL-P ID."""
    if not clinic_id:
        return None
    _load_clinics()
    cid_clean = clinic_id.strip().lower()
    c = _CLINICS_BY_ID.get(cid_clean)
    return _clean_clinic_response(c) if c else None

def get_available_sites() -> List[Dict[str, Any]]:
    """Returns all unique sites with their counts, sorted by frequency."""
    clinics = _load_clinics()
    counts: Dict[str, int] = {}
    for c in clinics:
        site = c["site"] or "Sans site spécifié"
        counts[site] = counts.get(site, 0) + 1

    sorted_sites = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [{"site": s, "count": cnt} for s, cnt in sorted_sites]

def get_available_types() -> List[Dict[str, Any]]:
    """Returns all unique types with descriptive labels and counts."""
    clinics = _load_clinics()
    counts: Dict[str, int] = {}
    for c in clinics:
        t = c["type"] or "N/D"
        counts[t] = counts.get(t, 0) + 1

    result = []
    for t, cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        result.append({
            "type": t,
            "label": TYPE_DESCRIPTIONS.get(t, t),
            "count": cnt
        })
    return result

def search_clinics(
    query: str = "",
    site: Optional[str] = None,
    clinic_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    High-performance ranked multi-field search and filtering over the SIL-P clinics dataset.
    Returns:
        {
            "total": int,
            "limit": int,
            "offset": int,
            "clinics": List[Dict[str, Any]]
        }
    """
    clinics = _load_clinics()
    q_norm = normalize_text(query)
    q_raw = query.strip().lower().replace(" ", "").replace("-", "")
    q_tokens = q_norm.split()

    site_filter = site.strip() if site and site.strip() and site.strip() != "Tous les sites" and site.strip() != "all" else None
    type_filter = clinic_type.strip() if clinic_type and clinic_type.strip() and clinic_type.strip() != "all" else None

    # Step 1: Filter by site / type
    candidates = clinics
    if site_filter or type_filter:
        filtered = []
        for c in candidates:
            if site_filter:
                c_site = c["site"] or "Sans site spécifié"
                if site_filter != c_site:
                    continue
            if type_filter and c["type"] != type_filter:
                continue
            filtered.append(c)
        candidates = filtered

    # Step 2: Search matching and ranking
    if not q_norm and not q_raw:
        total = len(candidates)
        paged = candidates[offset:offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "clinics": [_clean_clinic_response(c) for c in paged]
        }

    tier_exact_id = []
    tier_prefix_id = []
    tier_contains_id = []
    tier_exact_name = []
    tier_prefix_name = []
    tier_all_tokens = []
    tier_any_token = []

    for c in candidates:
        id_norm = c["_id_norm"]
        name_norm = c["_name_norm"]
        blob = c["_search_blob"]

        # 1. Exact ID
        if q_raw and id_norm == q_raw:
            tier_exact_id.append(c)
            continue

        # 2. Prefix ID
        if q_raw and id_norm.startswith(q_raw):
            tier_prefix_id.append(c)
            continue

        # 3. Substring in ID
        if q_raw and q_raw in id_norm:
            tier_contains_id.append(c)
            continue

        # 4. Exact Name
        if q_norm and name_norm == q_norm:
            tier_exact_name.append(c)
            continue

        # 5. Prefix Name
        if q_norm and name_norm.startswith(q_norm):
            tier_prefix_name.append(c)
            continue

        # 6. All query tokens present in search blob
        if q_tokens and all(tok in blob for tok in q_tokens):
            tier_all_tokens.append(c)
            continue

        # 7. For non-numeric multi-character queries, match if at least first token matches name
        if len(q_tokens) > 1 and q_tokens[0] in name_norm:
            tier_any_token.append(c)

    matched = (
        tier_exact_id +
        tier_prefix_id +
        tier_contains_id +
        tier_exact_name +
        tier_prefix_name +
        tier_all_tokens +
        tier_any_token
    )

    total = len(matched)
    paged = matched[offset:offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "clinics": [_clean_clinic_response(c) for c in paged]
    }

def _clean_clinic_response(c: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a public representation of the clinic record without internal indexing keys."""
    raw_name = c["name"]
    return {
        "id": c["id"],
        "name": raw_name,
        "name_sanitized": sanitize_clinic_name(raw_name),
        "site": c["site"],
        "city": c["city"],
        "postal_code": c["postal_code"],
        "address": c["address"],
        "facility": c["facility"],
        "type": c["type"],
        "type_label": c["type_label"]
    }
