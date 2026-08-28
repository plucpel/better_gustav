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
LOCATIONS_FILE = os.path.join(DATA_DIR, "locations.json")
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
    Supports multi-token and reverse name search (e.g., 'Lambert Alexandra').
    """
    q_norm = normalize_text(query)
    q_raw = query.strip().lower()
    if not q_norm and not q_raw:
        return []
        
    registry = load_cmq_registry()
    if not registry:
        return []

    q_tokens = q_norm.split()
    q_digits = "".join(c for c in q_raw if c.isdigit())
    
    exact_matches = []
    prefix_matches = []
    token_matches = []
    fuzzy_matches = []

    for doc in registry:
        doc_lic = str(doc.get("doctor_license", "")).strip().lower()
        doc_lic_digits = "".join(c for c in doc_lic if c.isdigit())
        doc_name_norm = normalize_text(doc.get("doctor_name", ""))
        doc_last_norm = normalize_text(doc.get("lastname", ""))
        doc_first_norm = normalize_text(doc.get("firstname", ""))
        full_blob = f"{doc_name_norm} {doc_first_norm} {doc_last_norm}"

        if q_digits and doc_lic_digits:
            if doc_lic_digits == q_digits:
                exact_matches.append(doc)
            elif doc_lic_digits.startswith(q_digits) or q_digits in doc_lic_digits:
                prefix_matches.append(doc)
        else:
            if doc_name_norm == q_norm or doc_last_norm == q_norm:
                exact_matches.append(doc)
            elif doc_last_norm.startswith(q_norm) or doc_name_norm.startswith(q_norm) or q_norm in doc_name_norm:
                prefix_matches.append(doc)
            elif q_tokens and all(t in full_blob for t in q_tokens):
                token_matches.append(doc)
            elif len(q_norm) >= 4:
                # Fuzzy match for typos
                sim = SequenceMatcher(None, q_norm, doc_name_norm).ratio()
                if sim >= 0.85:
                    fuzzy_matches.append((sim, doc))

    fuzzy_sorted = [d for _, d in sorted(fuzzy_matches, key=lambda x: x[0], reverse=True)]
    results = exact_matches + prefix_matches + token_matches + fuzzy_sorted
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
    CRITICAL RULE: If both records have license numbers and they differ, they are NEVER duplicates.
    """
    lic_clean = doc_license.strip().replace(" ", "").replace("-", "") if doc_license else ""
    name_norm = normalize_text(doctor_name)

    for p in prescribers:
        p_lic = str(p.get("doctor_license", "")).strip().replace(" ", "").replace("-", "")
        
        # 1. Exact license match
        if lic_clean and p_lic:
            if lic_clean == p_lic:
                return p
            else:
                # Different license numbers -> strictly different doctors, do NOT match by name!
                continue
        
        # 2. Match by name only when at least one license is missing
        p_name_norm = normalize_text(p.get("doctor_name", ""))
        if name_norm and p_name_norm:
            if name_norm == p_name_norm:
                return p
            # High-confidence typo similarity check
            if len(name_norm) >= 6 and len(p_name_norm) >= 6:
                if SequenceMatcher(None, name_norm, p_name_norm).ratio() >= 0.92:
                    return p
                    
    return None

def upsert_prescriber(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds or updates a prescriber with duplicate, typo, and inactive physician protection.
    IMMUTABLE IDENTITY: NEVER overwrites doctor_name or doctor_license of an existing entry.
    """
    if is_inactive_or_ex_doctor(data):
        raise ValueError("Cannot upsert inactive or ex-physician")

    doc_name = str(data.get("doctor_name", "")).strip()
    doc_lic = str(data.get("doctor_license", "")).strip()

    # Extract clean digits for Quebec physician permit (4-6 digits)
    digits_lic = "".join(c for c in doc_lic if c.isdigit())
    if digits_lic and len(digits_lic) in [4, 5, 6]:
        doc_lic = digits_lic
    
    if not doc_name and not doc_lic:
        raise ValueError("Doctor name or license number required")

    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        existing = find_prescriber_duplicate(doc_lic, doc_name, prescribers)

        if existing:
            # IMMUTABLE IDENTITY: NEVER overwrite existing name or license!
            if not existing.get("doctor_name") and doc_name:
                existing["doctor_name"] = doc_name
            if not existing.get("doctor_license") and doc_lic:
                existing["doctor_license"] = doc_lic

            # Update complementary metadata
            if data.get("clinic_name"):
                existing["clinic_name"] = str(data["clinic_name"]).strip()
            if data.get("clinic_id"):
                existing["clinic_id"] = str(data["clinic_id"]).strip()
            if data.get("doctor_copy"):
                existing["doctor_copy"] = str(data["doctor_copy"]).strip()
            if data.get("doctor_copy_license"):
                existing["doctor_copy_license"] = str(data["doctor_copy_license"]).strip()
            if data.get("specialty") and not existing.get("specialty"):
                existing["specialty"] = str(data["specialty"]).strip()
            if data.get("city") and not existing.get("city"):
                existing["city"] = str(data["city"]).strip()

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
    """
    Updates an existing prescriber by ID, license, or name.
    Sanitizes clinic name and auto-resolves SIL-P ID if omitted.
    """
    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        unquoted_id = unicodedata.normalize("NFKD", str(prescriber_id)).strip()
        
        target = None
        # 1. Exact ID match
        for p in prescribers:
            p_id = str(p.get("id", "")).strip()
            if p_id == prescriber_id or p_id == unquoted_id:
                target = p
                break
                
        # 2. Match by license
        if not target and unquoted_id:
            for p in prescribers:
                p_lic = str(p.get("doctor_license", "")).strip()
                if p_lic and (p_lic == unquoted_id or p_lic.replace(" ", "").replace("-", "") == unquoted_id.replace(" ", "").replace("-", "")):
                    target = p
                    break

        # 3. Match by incoming data license or name
        if not target:
            new_lic = str(data.get("doctor_license", "")).strip().replace(" ", "").replace("-", "")
            new_name_norm = normalize_text(data.get("doctor_name", ""))
            if new_lic:
                for p in prescribers:
                    if str(p.get("doctor_license", "")).strip().replace(" ", "").replace("-", "") == new_lic:
                        target = p
                        break
            if not target and new_name_norm:
                for p in prescribers:
                    if normalize_text(p.get("doctor_name", "")) == new_name_norm:
                        target = p
                        break

        # Prepare sanitized clinic info
        clinic_name = str(data.get("clinic_name", "")).strip()
        clinic_id = str(data.get("clinic_id", "")).strip()
        try:
            from clinics_manager import sanitize_clinic_name, search_clinics
            if clinic_name:
                clinic_name = sanitize_clinic_name(clinic_name)
                if not clinic_id:
                    silp_res = search_clinics(clinic_name, limit=1)
                    if silp_res and silp_res.get("clinics"):
                        clinic_id = str(silp_res["clinics"][0].get("id") or "")
        except Exception:
            pass

        if target:
            target["doctor_name"] = str(data.get("doctor_name", target.get("doctor_name", ""))).strip()
            if "doctor_license" in data:
                target["doctor_license"] = str(data["doctor_license"]).strip()
            target["clinic_name"] = clinic_name
            target["clinic_id"] = clinic_id
            if "doctor_copy" in data:
                target["doctor_copy"] = str(data["doctor_copy"]).strip()
            if "doctor_copy_license" in data:
                target["doctor_copy_license"] = str(data["doctor_copy_license"]).strip()
            target["updated_at"] = uuid.uuid4().hex[:8]
            _save_json(PRESCRIBERS_FILE, prescribers)
            return target
            
    # Fallback: if not found, upsert as new record
    return upsert_prescriber({**data, "clinic_name": clinic_name, "clinic_id": clinic_id})

def delete_prescriber(prescriber_id: str) -> bool:
    """Deletes a prescriber by ID or license."""
    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        initial_len = len(prescribers)
        unquoted_id = str(prescriber_id).strip()
        prescribers = [
            p for p in prescribers
            if str(p.get("id")) != prescriber_id and
               str(p.get("id")) != unquoted_id and
               str(p.get("doctor_license", "")).strip() != unquoted_id
        ]
        if len(prescribers) < initial_len:
            _save_json(PRESCRIBERS_FILE, prescribers)
            return True
    return False

def is_inactive_or_ex_doctor(raw: Dict[str, Any]) -> bool:
    """
    Identifies whether a physician record represents an inactive, retired,
    deceased, or ex-doctor (no valid prescribing rights).
    """
    if not isinstance(raw, dict):
        return True

    # 1. Check license string for 'ex-médecin', 'ex-', 'inactif', etc.
    lic = str(raw.get("doctor_license") or raw.get("license") or raw.get("number") or raw.get("no_permis") or raw.get("permis") or "").strip().lower()
    if "ex-m" in lic or "ex m" in lic or "ex-" in lic or "inactif" in lic or "retrait" in lic or "radi" in lic:
        return True

    # 2. Check explicit status / state fields
    status = str(raw.get("status") or raw.get("statut") or raw.get("etat") or raw.get("type") or raw.get("statut_exercice") or "").strip().lower()
    if status in ["ex-médecin", "ex-medecin", "inactif", "retraité", "retraite", "radié", "radie", "décédé", "decede", "non inscrit", "démissionnaire", "demissionnaire"]:
        return True

    # 3. Check name or full payload string for 'ex-médecin' indicators
    name = str(raw.get("doctor_name") or raw.get("name") or raw.get("lastname") or "").strip().lower()
    if "ex-m" in name or "ex m" in name or "retraité" in name or "retraite" in name or "radié" in name:
        return True

    # 4. Check entire dict string representation for strong ex-doctor patterns
    raw_str = " ".join(str(v) for v in raw.values()).lower()
    if "ex-médecin" in raw_str or "ex-medecin" in raw_str or "ex médecin" in raw_str:
        return True

    return False

def purge_inactive_prescribers() -> int:
    """
    Purges all inactive and ex-doctors from data/prescribers.json.
    Returns the number of purged records.
    """
    with _file_lock:
        prescribers = _load_json(PRESCRIBERS_FILE)
        initial_count = len(prescribers)
        active_prescribers = [p for p in prescribers if not is_inactive_or_ex_doctor(p)]
        purged_count = initial_count - len(active_prescribers)
        if purged_count > 0:
            _save_json(PRESCRIBERS_FILE, active_prescribers)
        return purged_count

def extract_doctor_fields(raw: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Extracts standardized doctor fields from various JSON/CSV schema formats.
    Returns None if the record is an ex-doctor or inactive.
    """
    if is_inactive_or_ex_doctor(raw):
        return None

    name = (
        raw.get("doctor_name") or
        raw.get("name") or
        raw.get("nom_complet") or
        raw.get("nom_medecin") or
        raw.get("medecin") or
        ""
    )
    if not name:
        first = raw.get("firstname") or raw.get("first_name") or raw.get("prenom") or ""
        last = raw.get("lastname") or raw.get("last_name") or raw.get("nom") or ""
        if first or last:
            name = f"{first} {last}".strip()
            
    name = str(name).strip()

    lic = (
        raw.get("doctor_license") or
        raw.get("license") or
        raw.get("number") or
        raw.get("no_permis") or
        raw.get("permis") or
        raw.get("matricule") or
        raw.get("cp") or
        ""
    )
    lic_str = str(lic).strip()
    digits_lic = "".join(c for c in lic_str if c.isdigit())
    if digits_lic and len(digits_lic) in [4, 5, 6]:
        lic = digits_lic
    else:
        lic = lic_str

    clinic_name = (
        raw.get("clinic_name") or
        raw.get("clinic") or
        raw.get("clinique") or
        raw.get("etablissement") or
        raw.get("installation") or
        raw.get("workplace") or
        ""
    )
    clinic_name = str(clinic_name).strip()

    try:
        from clinics_manager import sanitize_clinic_name, search_clinics
        clinic_name = sanitize_clinic_name(clinic_name)
    except Exception:
        pass

    clinic_id = (
        raw.get("clinic_id") or
        raw.get("id_clinique") or
        raw.get("silp_id") or
        raw.get("id_silp") or
        ""
    )
    clinic_id = str(clinic_id).strip()

    # If clinic_name is provided but clinic_id is missing, auto-resolve from SIL-P registry
    if clinic_name and not clinic_id:
        try:
            from clinics_manager import search_clinics
            silp_res = search_clinics(clinic_name, limit=1)
            if silp_res and silp_res.get("clinics"):
                clinic_id = str(silp_res["clinics"][0].get("id") or "")
        except Exception:
            pass

    copy_name = raw.get("doctor_copy") or raw.get("medecin_copie") or ""
    copy_lic = raw.get("doctor_copy_license") or raw.get("permis_copie") or ""
    specialty = raw.get("specialty") or raw.get("specialite") or ""
    city = raw.get("city") or raw.get("ville") or ""

    return {
        "doctor_name": name,
        "doctor_license": lic,
        "clinic_name": clinic_name,
        "clinic_id": clinic_id,
        "doctor_copy": str(copy_name).strip(),
        "doctor_copy_license": str(copy_lic).strip(),
        "specialty": str(specialty).strip(),
        "city": str(city).strip()
    }

def bulk_import_prescribers(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    High-performance bulk import of prescribers in a single atomic disk operation.
    Automatically filters out Ex-médecins and inactive physicians.
    """
    if not isinstance(items, list):
        raise ValueError("Payload must be a list of doctor records")

    with _file_lock:
        existing_list = _load_json(PRESCRIBERS_FILE)
        
        # Purge existing inactives if any remain in memory
        existing_list = [p for p in existing_list if not is_inactive_or_ex_doctor(p)]

        # Build quick lookup indices
        by_license = {}
        by_name = {}
        ordered_list = []

        for p in existing_list:
            lic = str(p.get("doctor_license", "")).strip().replace(" ", "").replace("-", "")
            name_norm = normalize_text(p.get("doctor_name", ""))
            ordered_list.append(p)
            if lic:
                by_license[lic] = p
            if name_norm:
                by_name[name_norm] = p

        added_count = 0
        updated_count = 0
        skipped_inactive_count = 0

        for raw in items:
            if not isinstance(raw, dict):
                continue
                
            fields = extract_doctor_fields(raw)
            if fields is None:
                skipped_inactive_count += 1
                continue

            name = fields["doctor_name"]
            lic = fields["doctor_license"]

            if not name and not lic:
                continue

            if name and not name.lower().startswith("dr.") and not name.lower().startswith("dr "):
                formatted_name = f"Dr. {name}"
            else:
                formatted_name = name

            clean_lic = lic.replace(" ", "").replace("-", "")
            norm_name = normalize_text(name)

            existing_record = None
            if clean_lic and clean_lic in by_license:
                existing_record = by_license[clean_lic]
            elif norm_name and norm_name in by_name:
                cand = by_name[norm_name]
                cand_lic = str(cand.get("doctor_license", "")).strip().replace(" ", "").replace("-", "")
                # Match by name only if candidate has no license or matching license
                if not cand_lic or (clean_lic and cand_lic == clean_lic):
                    existing_record = cand

            if existing_record:
                # IMMUTABLE IDENTITY: NEVER overwrite existing doctor_name or doctor_license!
                if not existing_record.get("doctor_name") and formatted_name:
                    existing_record["doctor_name"] = formatted_name
                if not existing_record.get("doctor_license") and lic:
                    existing_record["doctor_license"] = lic
                if fields["clinic_name"]:
                    existing_record["clinic_name"] = fields["clinic_name"]
                if fields["clinic_id"]:
                    existing_record["clinic_id"] = fields["clinic_id"]
                if fields["doctor_copy"]:
                    existing_record["doctor_copy"] = fields["doctor_copy"]
                if fields["doctor_copy_license"]:
                    existing_record["doctor_copy_license"] = fields["doctor_copy_license"]
                if fields["specialty"]:
                    existing_record["specialty"] = fields["specialty"]
                if fields["city"]:
                    existing_record["city"] = fields["city"]
                existing_record["updated_at"] = uuid.uuid4().hex[:8]
                updated_count += 1
            else:
                p_id = raw.get("id") or (f"lic_{clean_lic}" if clean_lic else f"doc_{uuid.uuid4().hex[:8]}")
                new_item = {
                    "id": str(p_id),
                    "doctor_name": formatted_name,
                    "doctor_license": lic,
                    "clinic_name": fields["clinic_name"],
                    "clinic_id": fields["clinic_id"],
                    "doctor_copy": fields["doctor_copy"],
                    "doctor_copy_license": fields["doctor_copy_license"],
                    "created_at": uuid.uuid4().hex[:8]
                }
                if fields["specialty"]:
                    new_item["specialty"] = fields["specialty"]
                if fields["city"]:
                    new_item["city"] = fields["city"]

                ordered_list.append(new_item)
                if clean_lic:
                    by_license[clean_lic] = new_item
                if norm_name:
                    by_name[norm_name] = new_item
                added_count += 1

        _save_json(PRESCRIBERS_FILE, ordered_list)

        return {
            "status": "success",
            "added": added_count,
            "updated": updated_count,
            "skipped_inactive": skipped_inactive_count,
            "total_processed": len(items),
            "total_records": len(ordered_list)
        }

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

def unified_search_prescribers(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    High-speed, multi-token, ranked search across prescribers and CMQ registry.
    Handles:
    - Order-independent multi-word search (e.g. 'Lambert Alexandra' or 'Alexandra Lambert')
    - License number search (exact, prefix, stripped non-digits)
    - Clinic, city, and specialty matching
    """
    q_raw = query.strip().lower()
    q_norm = normalize_text(query)
    if not q_norm and not q_raw:
        return get_all_prescribers()[:limit]

    q_tokens = q_norm.split()
    q_digits = "".join(c for c in q_raw if c.isdigit())

    clinic_prescribers = get_all_prescribers()

    exact_license_matches = []
    prefix_license_matches = []
    full_name_matches = []
    token_matches = []
    fuzzy_matches = []
    seen_ids = set()

    for p in clinic_prescribers:
        p_id = p.get("id") or ""
        lic = str(p.get("doctor_license", "")).strip().lower()
        lic_digits = "".join(c for c in lic if c.isdigit())
        name = str(p.get("doctor_name", ""))
        name_norm = normalize_text(name)
        clinic_norm = normalize_text(p.get("clinic_name", ""))
        spec_norm = normalize_text(p.get("specialty", ""))
        city_norm = normalize_text(p.get("city", ""))

        full_blob = f"{name_norm} {clinic_norm} {spec_norm} {city_norm}"

        # 1. Exact license match
        if q_digits and lic_digits and q_digits == lic_digits:
            exact_license_matches.append({**p, "source": "clinic"})
            seen_ids.add(p_id)
            continue

        # 2. License prefix / substring match
        if q_digits and lic_digits and (lic_digits.startswith(q_digits) or q_digits in lic_digits):
            prefix_license_matches.append({**p, "source": "clinic"})
            seen_ids.add(p_id)
            continue

        # 3. Exact full name match
        if q_norm and (name_norm == q_norm or q_norm in name_norm):
            full_name_matches.append({**p, "source": "clinic"})
            seen_ids.add(p_id)
            continue

        # 4. Multi-token match (all query words present in name or blob)
        if q_tokens and all(t in full_blob for t in q_tokens):
            token_matches.append({**p, "source": "clinic"})
            seen_ids.add(p_id)
            continue

        # 5. Fuzzy match for typos if query length >= 4
        if len(q_norm) >= 4 and name_norm:
            sim = SequenceMatcher(None, q_norm, name_norm).ratio()
            if sim >= 0.82:
                fuzzy_matches.append((sim, {**p, "source": "clinic"}))
                seen_ids.add(p_id)

    fuzzy_sorted = [p for _, p in sorted(fuzzy_matches, key=lambda x: x[0], reverse=True)]
    ranked_clinic = exact_license_matches + full_name_matches + prefix_license_matches + token_matches + fuzzy_sorted

    if len(ranked_clinic) >= limit:
        return ranked_clinic[:limit]

    # Search CMQ registry for remaining slots
    remaining = limit - len(ranked_clinic)
    cmq_results = search_cmq_physicians(query, limit=remaining + 10)
    matched_cmq = []
    seen_licenses = {"".join(c for c in str(p.get("doctor_license", "")).lower() if c.isdigit()) for p in ranked_clinic if p.get("doctor_license")}

    for doc in cmq_results:
        doc_lic = "".join(c for c in str(doc.get("doctor_license", "")).lower() if c.isdigit())
        if doc_lic and doc_lic in seen_licenses:
            continue
        matched_cmq.append({**doc, "source": "cmq"})
        if len(ranked_clinic) + len(matched_cmq) >= limit:
            break

    return (ranked_clinic + matched_cmq)[:limit]

# ==============================================================================
# SAMPLE LOCATIONS (LIEUX DE PRÉLÈVEMENT)
# ==============================================================================

def get_all_locations() -> List[Dict[str, Any]]:
    """Returns all saved sample collection locations from data/locations.json."""
    with _file_lock:
        return _load_json(LOCATIONS_FILE)

def upsert_location(data: Dict[str, Any]) -> Dict[str, Any]:
    """Adds or updates a sample collection location."""
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Location name required")

    with _file_lock:
        locations = _load_json(LOCATIONS_FILE)
        for loc in locations:
            if loc.get("name", "").strip().lower() == name.lower():
                return loc

        loc_id = data.get("id") or f"loc_{uuid.uuid4().hex[:8]}"
        new_item = {
            "id": str(loc_id),
            "name": name
        }
        locations.append(new_item)
        _save_json(LOCATIONS_FILE, locations)
        return new_item

def update_location(location_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a location by ID."""
    with _file_lock:
        locations = _load_json(LOCATIONS_FILE)
        for loc in locations:
            if loc.get("id") == location_id:
                if "name" in data:
                    loc["name"] = str(data["name"]).strip()
                _save_json(LOCATIONS_FILE, locations)
                return loc
    return None

def delete_location(location_id: str) -> bool:
    """Deletes a location by ID."""
    with _file_lock:
        locations = _load_json(LOCATIONS_FILE)
        initial_len = len(locations)
        locations = [l for l in locations if l.get("id") != location_id]
        if len(locations) < initial_len:
            _save_json(LOCATIONS_FILE, locations)
            return True
    return False
