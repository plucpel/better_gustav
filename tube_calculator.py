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

# Standard Order of Draw Definitions
TUBE_DEFINITIONS = {
    "HEMOCULTURE": {
        "order": 1,
        "name_fr": "Flacons d'hémoculture (Aérobie + Anaérobie)",
        "pediatric_name_fr": "Flacon d'hémoculture pédiatrique",
        "color_code": "#D97706", # Amber / Gold
        "cap_color_name": "Jaune / Vert / Rose",
        "additive": "Bouillon de culture SPS + Résine neutralisante",
        "max_volume": "8-10 mL par flacon (adulte) / 1-3 mL (pédiatrique)",
        "special_instructions": "Désinfection cutanée rigoureuse à la chlorhexidine 2%. Prélever impérativement en 1er lieu."
    },
    "CITRATE": {
        "order": 2,
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
        "name_fr": "Tube Bouchon Doré / Or (Gel séparateur + Activateur)",
        "pediatric_name_fr": "Microtube Bouchon Doré (Gel séparateur)",
        "color_code": "#CA8A04", # Gold / Yellow
        "cap_color_name": "Doré / Or",
        "additive": "Silice activateur de caillot + Gel polymère",
        "max_volume": "5.0 mL",
        "special_instructions": "Laisser coaguler 30 minutes à la verticale avant centrifugation. 5 inversions."
    },
    "SERUM_PLAIN": {
        "order": 3,
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
        "name_fr": "Tube Bouchon Menthe (Héparine de Lithium + Gel PST)",
        "pediatric_name_fr": "Microtube Bouchon Vert (Héparine-Lithium)",
        "color_code": "#059669", # Mint / Emerald green
        "cap_color_name": "Menthe / Vert clair",
        "additive": "Héparine de lithium (68 UI) + Gel séparateur PST",
        "max_volume": "4.5 mL",
        "special_instructions": "Tube principal de biochimie de routine au CHU de Québec. 8 à 10 inversions douces."
    },
    "HEPARINE_SODIUM": {
        "order": 4,
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
        "name_fr": "Tube Bouchon Lavande / Mauve (K2-EDTA)",
        "pediatric_name_fr": "Microtube Bouchon Lavande (K2-EDTA)",
        "color_code": "#7C3AED", # Purple / Lavender
        "cap_color_name": "Lavande / Mauve",
        "additive": "K2-EDTA (anticoagulant hématologie)",
        "max_volume": "4.0 mL",
        "special_instructions": "Homogénéiser immédiatement (8-10 inversions). Ne jamais prélever avant les tubes de biochimie (risque de fausse hyperkaliémie)."
    },
    "EDTA_ROSE": {
        "order": 5,
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
        "name_fr": "Seringue héparinée pour Gaz sanguins",
        "pediatric_name_fr": "Seringue héparinée pour Gaz sanguins",
        "color_code": "#0891B2", # Cyan
        "cap_color_name": "Seringue spécifique",
        "additive": "Héparine de lithium lyophilisée équilibrée",
        "max_volume": "1-2 mL",
        "special_instructions": "CRITIQUE : Chasser immédiatement les bulles d'air, boucher et acheminer au laboratoire sur glace fondante en < 15-30 min."
    },
    "SPECIMEN_DIVERS": {
        "order": 8,
        "name_fr": "Contenant spécial / Stérile / Urines / LCR",
        "pediatric_name_fr": "Contenant spécial",
        "color_code": "#EA580C", # Orange
        "cap_color_name": "Orange / Jaune",
        "additive": "Selon l'analyse",
        "max_volume": "Variable",
        "special_instructions": "Consulter la fiche spécifique pour les consignes de prélèvement."
    }
}

def classify_container(container_str, analysis_name="", pid=""):
    """Classify a Gustav container string into standardized tube categories."""
    c_lower = container_str.lower()
    name_lower = analysis_name.lower()
    pid_lower = pid.lower()

    if any(k in c_lower for k in ["hemoculture", "hémoculture", "bactec", "bact-alert", "bouteille"]):
        return "HEMOCULTURE"
    if any(k in c_lower for k in ["bleu (citrate", "citrate", "bleu"]):
        if "bleu royal" in c_lower:
            return "ROYAL_BLUE"
        return "CITRATE"
    if "bleu royal" in c_lower:
        return "ROYAL_BLUE"
    if "rose" in c_lower or any(k in name_lower for k in ["groupe sanguin", "coombs", "rai", "compatibilite"]):
        return "EDTA_ROSE"
    if any(k in c_lower for k in ["lavande", "edta", "mauve"]):
        return "EDTA"
    if any(k in c_lower for k in ["menthe", "menthe_heparine_lithium", "heparine_lithium", "pst"]):
        return "HEPARINE_LITHIUM"
    if any(k in c_lower for k in ["vert (hepna)", "heparine_sodium", "hepna", "vert foncé"]):
        return "HEPARINE_SODIUM"
    if any(k in c_lower for k in ["vert", "vert_heparine_lithium"]):
        return "HEPARINE_LITHIUM"
    if any(k in c_lower for k in ["or (activateur caillot)", "or", "dore", "doré", "gel activateur"]):
        return "SERUM_GEL"
    if any(k in c_lower for k in ["rouge", "sec sans gel"]):
        return "SERUM_PLAIN"
    if any(k in c_lower for k in ["gris", "fluorure", "oxalate"]):
        return "FLUORURE"
    if any(k in c_lower for k in ["seringue", "gaz"]) or "gaz" in pid_lower or "gaz" in name_lower:
        return "GAZ_SERINGUE"
    
    # Fallback based on analysis name
    if any(k in name_lower for k in ["formule sanguine", "plaquettes", "reticulocytes", "frottis", "hba1c"]):
        return "EDTA"
    if any(k in name_lower for k in ["inr", "quick", "ptt", "tca", "fibrinogene", "d-dimere"]):
        return "CITRATE"
    if any(k in name_lower for k in ["troponine", "electrolytes", "creatinine", "uree", "bilirubine", "alt", "ast", "tsh"]):
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
                    "url": item.get("url", "")
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
                "url": item.get("url", "")
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
            "url": item.get("url", "")
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
                "url": item.get("url", "")
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
            "total_containers": 0,
            "tubes": [],
            "special_instructions": [],
            "analyses_included": []
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
        
        for c in item.get("containers", []):
            c_sites = normalize_str(c.get("sites", ""))
            site_norm = normalize_str(site)
            if site_norm in c_sites or "tous les sites" in c_sites:
                chosen_container_str = c.get("container", "")
                chosen_qty = c.get("quantity", "")
                chosen_count = c.get("count", "1")
                break
        
        if not chosen_container_str and item.get("containers"):
            chosen_container_str = item["containers"][0].get("container", "")
            chosen_qty = item["containers"][0].get("quantity", "")
            chosen_count = item["containers"][0].get("count", "1")

        cat_key = classify_container(chosen_container_str, item["name"], pid)

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

    # Sort categories by Order of Draw
    tube_results = []
    total_tubes_count = 0
    total_bottles_count = 0

    sorted_categories = sorted(
        [k for k in grouped_tubes.keys() if k is not None],
        key=lambda k: TUBE_DEFINITIONS.get(k, {}).get("order", 99)
    )

    for cat_key in sorted_categories:
        tube_def = TUBE_DEFINITIONS.get(cat_key, TUBE_DEFINITIONS["SPECIMEN_DIVERS"])
        group_data = grouped_tubes[cat_key]

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

                unit_label = "Microtube" if tube_count == 1 else "Microtubes"
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
                
                # 2. Cumulative volume-based count (e.g. 7 mL ANA + 5 mL ACOCH = 12 mL -> 3 tubes)
                total_vol = 0.0
                has_routine_base = False
                for a in group_data["analyses"]:
                    vol = parse_volume_ml(a.get("quantity", ""))
                    if vol > 1.0:
                        # Dedicated / high-volume / sendout test requirement (e.g. 5 mL, 7 mL, 12 mL)
                        total_vol += vol
                    elif vol > 0.0:
                        if not has_routine_base:
                            total_vol += vol
                            has_routine_base = True
                        else:
                            # Routine tests sharing serum on analyzer
                            total_vol += 0.2
                    else:
                        if not has_routine_base:
                            total_vol += 1.0
                            has_routine_base = True
                        else:
                            total_vol += 0.2
                
                vol_tubes = math.ceil(total_vol / nominal_cap) if total_vol > 0 else 1
                
                tube_count = max(max_explicit, vol_tubes, 1)
                unit_label = "Tube" if tube_count == 1 else "Tubes"
                container_display_name = tube_def["name_fr"]

                if vol_tubes > 1 and total_vol > nominal_cap:
                    volume_alert = f"Volume sanguin total requis ({total_vol:g} mL) supérieur à la contenance d'un tube standard ({nominal_cap:g} mL) → {tube_count} tubes nécessaires."
                    group_data["alerts"].add(volume_alert)

            total_tubes_count += tube_count

        # Clean specific alerts
        clean_alerts = []
        for al in group_data["alerts"]:
            if len(al) > 5 and "Contenant(s)" not in al and "Jour même" not in al and "Valeur" not in al:
                clean_alerts.append(al)

        # Consolidation explanation
        consolidation_note = ""
        if len(group_data["analyses"]) > 1:
            if tube_count == 1 and cat_key in ["HEPARINE_LITHIUM", "SERUM_GEL", "EDTA"]:
                consolidation_note = f"Échantillon partagé sur automate : les {len(group_data['analyses'])} analyses de routine sont exécutées à partir du même tube (seuls quelques microlitres par test sont prélevés par l'automate)."
            elif tube_count > 1 and not is_pediatric:
                consolidation_note = f"Volume cumulé requis ({total_vol:g} mL) nécessitant {tube_count} tubes."

        tube_results.append({
            "category_key": cat_key,
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

    return {
        "total_tubes": total_tubes_count,
        "total_bottles": total_bottles_count,
        "total_containers": total_tubes_count + total_bottles_count,
        "tubes": tube_results,
        "special_instructions": dedup_alerts,
        "analyses_included": analyses_summary,
        "site_applied": site,
        "is_pediatric": is_pediatric
    }
