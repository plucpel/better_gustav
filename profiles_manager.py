"""
profiles_manager.py - Directory & Profile Management for Gustav.

Handles:
1. Server-side storage for saved Prescribers (data/prescribers.json) and Nurses (data/nurses.json).
2. Master CMQ (Collège des médecins du Québec) Physician Registry (data/cmq_physicians.json).
3. High-speed autocomplete & search across both custom clinic prescribers and the official CMQ registry.
4. Auto-learning on requisition submission with normalized fuzzy duplicate & typo protection.
5. Thread-safe atomic file persistence.
"""

import os
import json
import uuid
import unicodedata
import threading
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

PRESCRIBERS_FILE = os.path.join(DATA_DIR, "prescribers.json")
NURSES_FILE = os.path.join(DATA_DIR, "nurses.json")
CMQ_PHYSICIANS_FILE = os.path.join(DATA_DIR, "cmq_physicians.json")

_file_lock = threading.Lock()

# In-memory cache for CMQ registry
_CMQ_REGISTRY: Optional[List[Dict[str, Any]]] = None
_CMQ_MTIME: float = 0

def normalize_text(text: Optional[str]) -> str:
    """Normalize text by lowercasing, removing accents, punctuation, titles, and suffixes."""
    if not text:
        return ""
    # Normalize unicode accents (é -> e, ç -> c)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    
    # Remove punctuation and split tokens
    clean = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    tokens = clean.split()
    
    # Filter out common medical titles and suffixes
    stop_tokens = {"dr", "docteur", "inf", "infirmiere", "infirmier", "md", "rn"}
    filtered = [t for t in tokens if t not in stop_tokens]
    return " ".join(filtered) if filtered else clean.strip()

def _load_json(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[profiles_manager] Error reading {file_path}: {e}")
        return []

def _save_json(file_path: str, data: List[Dict[str, Any]]) -> None:
    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, file_path)

# ==============================================================================
# CMQ REGISTRY CACHE & SEARCH
# ==============================================================================

def load_cmq_registry() -> List[Dict[str, Any]]:
    """Loads and caches the CMQ physicians list from data/cmq_physicians.json."""
    global _CMQ_REGISTRY, _CMQ_MTIME
    
    if not os.path.exists(CMQ_PHYSICIANS_FILE):
        return []
        
    mtime = os.path.getmtime(CMQ_PHYSICIANS_FILE)
    if _CMQ_REGISTRY is None or mtime != _CMQ_MTIME:
        with _file_lock:
            _CMQ_REGISTRY = _load_json(CMQ_PHYSICIANS_FILE)
            _CMQ_MTIME = mtime
            
    return _CMQ_REGISTRY or []

def search_cmq_physicians(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Searches the official CMQ registry by name or license number.
    Returns matched doctor records.
    """
    q_norm = normalize_text(query)
    q_raw = query.strip().lower()
    if not q_norm and not q_raw:
        return []
        
    registry = load_cmq_registry()
    if not registry:
        return []

    is_numeric = q_raw.isdigit()
    exact_matches = []
    prefix_matches = []
    fuzzy_matches = []

    for doc in registry:
        doc_lic = str(doc.get("doctor_license", "")).strip()
        doc_name_norm = normalize_text(doc.get("doctor_name", ""))
        doc_last_norm = normalize_text(doc.get("lastname", ""))
        doc_first_norm = normalize_text(doc.get("firstname", ""))

        if is_numeric and doc_lic:
            if doc_lic == q_raw:
                exact_matches.append(doc)
            elif doc_lic.startswith(q_raw) or q_raw in doc_lic:
                prefix_matches.append(doc)
        else:
            if doc_name_norm == q_norm or doc_last_norm == q_norm:
                exact_matches.append(doc)
            elif doc_last_norm.startswith(q_norm) or doc_name_norm.startswith(q_norm) or q_norm in doc_name_norm:
                prefix_matches.append(doc)
            elif len(q_norm) >= 4:
                # Fuzzy match for typos
                sim = SequenceMatcher(None, q_norm, doc_name_norm).ratio()
                if sim >= 0.85:
                    fuzzy_matches.append((sim, doc))

    fuzzy_sorted = [d for _, d in sorted(fuzzy_matches, key=lambda x: x[0], reverse=True)]
    results = exact_matches + prefix_matches + fuzzy_sorted
    return results[:limit]

# ==============================================================================
# PRESCRIBERS (MÉDECINS / CLINIQUES)
# ==============================================================================

def get_all_prescribers() -> List[Dict[str, Any]]:
    """Returns all custom / clinic prescribers from data/prescribers.json."""
    with _file_lock:
        return _load_json(PRESCRIBERS_FILE)

def find_prescriber_duplicate(doc_license: str, doctor_name: str, prescribers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Finds if a prescriber already exists using license # or fuzzy name matching.
    """
    lic_clean = doc_license.strip().replace(" ", "").replace("-", "") if doc_license else ""
    name_norm = normalize_text(doctor_name)

    for p in prescribers:
        p_lic = str(p.get("doctor_license", "")).strip().replace(" ", "").replace("-", "")
        # Exact license match
        if lic_clean and p_lic and lic_clean == p_lic:
            return p
        
        # Name comparison
        p_name_norm = normalize_text(p.get("doctor_name", ""))
        if name_norm and p_name_norm:
            if name_norm == p_name_norm:
                return p
            # Typo similarity check
            if len(name_norm) >= 5 and len(p_name_norm) >= 5:
                if SequenceMatcher(None, name_norm, p_name_norm).ratio() >= 0.88:
                    return p
                    
    return None

def upsert_prescriber(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds or updates a prescriber with duplicate and typo protection.
    """
    doc_name = str(data.get("doctor_name", "")).strip()
    doc_lic = str(data.get("doctor_license", "")).strip()
    
    if not doc_name and not doc_lic:
        raise ValueError("Doctor name or license number required")

    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        existing = find_prescriber_duplicate(doc_lic, doc_name, prescribers)

        if existing:
            # Update non-empty fields
            if doc_name:
                existing["doctor_name"] = doc_name
            if doc_lic:
                existing["doctor_license"] = doc_lic
            if data.get("clinic_name"):
                existing["clinic_name"] = str(data["clinic_name"]).strip()
            if data.get("clinic_id"):
                existing["clinic_id"] = str(data["clinic_id"]).strip()
            if data.get("doctor_copy"):
                existing["doctor_copy"] = str(data["doctor_copy"]).strip()
            if data.get("doctor_copy_license"):
                existing["doctor_copy_license"] = str(data["doctor_copy_license"]).strip()
            existing["updated_at"] = data.get("updated_at") or uuid.uuid4().hex[:8]
            _save_json(PRESCRIBERS_FILE, prescribers)
            return existing
        else:
            p_id = data.get("id") or (f"lic_{doc_lic}" if doc_lic else f"doc_{uuid.uuid4().hex[:8]}")
            new_item = {
                "id": str(p_id),
                "doctor_name": doc_name,
                "doctor_license": doc_lic,
                "clinic_name": str(data.get("clinic_name", "")).strip(),
                "clinic_id": str(data.get("clinic_id", "")).strip(),
                "doctor_copy": str(data.get("doctor_copy", "")).strip(),
                "doctor_copy_license": str(data.get("doctor_copy_license", "")).strip(),
                "created_at": uuid.uuid4().hex[:8]
            }
            prescribers.insert(0, new_item)
            _save_json(PRESCRIBERS_FILE, prescribers)
            return new_item

def update_prescriber(prescriber_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates an existing prescriber by ID."""
    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        for i, p in enumerate(prescribers):
            if p.get("id") == prescriber_id:
                for k in ["doctor_name", "doctor_license", "clinic_name", "clinic_id", "doctor_copy", "doctor_copy_license"]:
                    if k in data:
                        p[k] = str(data[k]).strip()
                _save_json(PRESCRIBERS_FILE, prescribers)
                return p
    return None

def delete_prescriber(prescriber_id: str) -> bool:
    """Deletes a prescriber by ID."""
    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        initial_len = len(prescribers)
        prescribers = [p for p in prescribers if p.get("id") != prescriber_id]
        if len(prescribers) < initial_len:
            _save_json(PRESCRIBERS_FILE, prescribers)
            return True
    return False

# ==============================================================================
# NURSES / PRÉLEVEURS
# ==============================================================================

def get_all_nurses() -> List[Dict[str, Any]]:
    """Returns all saved nurses/préleveurs from data/nurses.json."""
    with _file_lock:
        return _load_json(NURSES_FILE)

def find_nurse_duplicate(nurse_name: str, nurses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Finds if a nurse/préleveur already exists using normalized name matching."""
    name_norm = normalize_text(nurse_name)
    if not name_norm:
        return None

    for n in nurses:
        n_name_norm = normalize_text(n.get("nurse_name", ""))
        if n_name_norm:
            if name_norm == n_name_norm:
                return n
            if len(name_norm) >= 4 and len(n_name_norm) >= 4:
                if SequenceMatcher(None, name_norm, n_name_norm).ratio() >= 0.88:
                    return n
    return None

def upsert_nurse(data: Dict[str, Any]) -> Dict[str, Any]:
    """Adds or updates a nurse/préleveur with typo/duplicate protection."""
    nurse_name = str(data.get("nurse_name", "")).strip()
    sample_loc = str(data.get("sample_location", "")).strip()

    if not nurse_name and not sample_loc:
        raise ValueError("Nurse name or location required")

    with _file_lock:
        nurses = _load_json(NURSES_FILE)
        existing = find_nurse_duplicate(nurse_name, nurses) if nurse_name else None

        if existing:
            if nurse_name:
                existing["nurse_name"] = nurse_name
            if sample_loc:
                existing["sample_location"] = sample_loc
            _save_json(NURSES_FILE, nurses)
            return existing
        else:
            n_id = data.get("id") or f"nurse_{uuid.uuid4().hex[:8]}"
            new_item = {
                "id": str(n_id),
                "nurse_name": nurse_name,
                "sample_location": sample_loc,
                "created_at": uuid.uuid4().hex[:8]
            }
            nurses.insert(0, new_item)
            _save_json(NURSES_FILE, nurses)
            return new_item

def update_nurse(nurse_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a nurse/préleveur by ID."""
    with _file_lock:
        nurses = _load_json(NURSES_FILE)
        for i, n in enumerate(nurses):
            if n.get("id") == nurse_id:
                if "nurse_name" in data:
                    n["nurse_name"] = str(data["nurse_name"]).strip()
                if "sample_location" in data:
                    n["sample_location"] = str(data["sample_location"]).strip()
                _save_json(NURSES_FILE, nurses)
                return n
    return None

def delete_nurse(nurse_id: str) -> bool:
    """Deletes a nurse/préleveur by ID."""
    with _file_lock:
        nurses = _load_json(NURSES_FILE)
        initial_len = len(nurses)
        nurses = [n for n in nurses if n.get("id") != nurse_id]
        if len(nurses) < initial_len:
            _save_json(NURSES_FILE, nurses)
            return True
    return False

# ==============================================================================
# UNIFIED PRACTITIONER SEARCH
# ==============================================================================

def unified_search_prescribers(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Searches both clinic-saved prescribers and the official CMQ registry.
    Custom clinic prescribers take priority and include clinic/copy metadata.
    """
    q_norm = normalize_text(query)
    q_raw = query.strip().lower()
    if not q_norm and not q_raw:
        # Return recent clinic prescribers if empty query
        return get_all_prescribers()[:limit]

    clinic_prescribers = get_all_prescribers()
    matched_clinic = []
    seen_licenses = set()

    for p in clinic_prescribers:
        lic = str(p.get("doctor_license", "")).strip().lower()
        name_norm = normalize_text(p.get("doctor_name", ""))
        clinic_norm = normalize_text(p.get("clinic_name", ""))
        
        if (lic and (lic == q_raw or lic.startswith(q_raw))) or \
           (q_norm in name_norm) or (q_norm in clinic_norm):
            matched_clinic.append({**p, "source": "clinic"})
            if lic:
                seen_licenses.add(lic)

    # Search CMQ registry for remaining slots
    remaining = limit - len(matched_clinic)
    matched_cmq = []
    if remaining > 0:
        cmq_results = search_cmq_physicians(query, limit=remaining + 5)
        for doc in cmq_results:
            lic = str(doc.get("doctor_license", "")).strip().lower()
            if lic and lic in seen_licenses:
                continue
            matched_cmq.append({**doc, "source": "cmq"})
            if len(matched_clinic) + len(matched_cmq) >= limit:
                break

    return matched_clinic + matched_cmq
