"""
Gustav laboratory analyses crawler and parser for CHU de Québec.
Extracts all biological analyses, specimen containers, quantities, sites,
and clean preparation/alert directives in proper UTF-8.
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://gustavguideext.chudequebec.ca/AcePtmApi/Api/"
DEFAULT_HEADERS = {"Temoin": "defaultSiteId=2&defaultdisciplineId=5"}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(DATA_DIR, "gustav_lab_catalog.json")

def discover_all_analysis_pids():
    """Discover all analysis items under Manuel des prélèvements."""
    print("Discovering all lab analyses from Gustav API (full comprehensive sweep)...")
    discovered = {}
    
    chars = "abcdefghijklmnopqrstuvwxyz0123456789éàè"
    prefixes = list(chars) + [c1 + c2 for c1 in chars[:26] for c2 in chars[:26]]
    
    def fetch_prefix(prefix):
        results = []
        try:
            r = requests.get(
                f"{BASE_URL}Search/All/true/true",
                headers={**DEFAULT_HEADERS, "PTM-SearchTerms": prefix},
                timeout=10
            )
            if r.status_code == 200:
                # Proper UTF-8 decoding
                raw_bytes = r.content
                data = json.loads(raw_bytes.decode('utf-8', errors='replace'))
                for it in data.get("ResultItems", []):
                    pid = it.get("PID")
                    thematic = it.get("Thematic", "")
                    if pid and "Manuel des prélèvements" in thematic:
                        results.append(it)
        except Exception:
            pass
        return results

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_prefix, p) for p in prefixes]
        for f in as_completed(futures):
            for it in f.result():
                pid = it.get("PID")
                if pid not in discovered:
                    discovered[pid] = it

    print(f"Total unique lab analyses discovered: {len(discovered)}")
    return discovered

def parse_fiche_html(pid, doc_name, thematic=""):
    """Fetch and parse the detailed specimen collection sheet for an analysis in clean UTF-8."""
    try:
        r = requests.get(
            f"{BASE_URL}Document/Read/{pid}",
            headers=DEFAULT_HEADERS,
            allow_redirects=True,
            timeout=10
        )
        if r.status_code != 200:
            return None
        
        # Proper UTF-8 decode
        html_content = r.content.decode('utf-8', errors='replace')
        soup = BeautifulSoup(html_content, "html.parser")
        
        entry = {
            "pid": pid,
            "name": doc_name,
            "thematic": thematic,
            "url": f"https://gustavguideext.chudequebec.ca/aceptm/#document/{pid}",
            "containers": [],
            "pediatric_microtubes": [],
            "specimen_type": "Sang",
            "preparation": "",
            "instructions": [],
            "alerts": [],
            "keywords": []
        }
        
        # 1. Extract Alerte / Directive
        for h in soup.find_all(["h1", "h2", "h3"]):
            if "Alerte / Directive" in h.get_text():
                sib = h.find_next_sibling()
                if sib:
                    txt = sib.get_text(separator=" ", strip=True)
                    if txt and "FICHE DE PRÉLÈVEMENT" not in txt and len(txt) < 400:
                        entry["alerts"].append(txt)

        # 2. Extract sections (Préparation, Commentaires / Instructions, Synonymes)
        for p in soup.find_all(["p", "div"]):
            txt = p.get_text(separator=" ", strip=True)
            
            # Préparation (ex: À jeun)
            if "Préparation de l'usager :" in txt or txt.startswith("Préparation de l'usager"):
                sib = p.find_next_sibling()
                prep_txt = sib.get_text(separator=" ", strip=True) if sib else txt.split(":")[-1].strip()
                if prep_txt and prep_txt.lower() != "sans particularité" and "FICHE DE" not in prep_txt and len(prep_txt) < 200:
                    entry["preparation"] = prep_txt
            
            # Instructions particulières
            if "Instructions particulières :" in txt or "Instructions particulìeres :" in txt:
                sib = p.find_next_sibling()
                inst_txt = sib.get_text(separator=" ", strip=True) if sib else txt.split(":")[-1].strip()
                # Clean up "Fiche complète" boilerplate
                inst_txt = inst_txt.replace("Fiche complète", "").strip()
                if inst_txt and len(inst_txt) < 300 and inst_txt not in entry["instructions"] and "Contenant(s) :" not in inst_txt:
                    entry["instructions"].append(inst_txt)

            # Synonymes
            if "Synonymes :" in txt:
                sib = p.find_next_sibling()
                syn_txt = sib.get_text(separator=" ", strip=True) if sib else txt.split("Synonymes :")[-1].strip()
                if syn_txt and len(syn_txt) < 250:
                    for s in re.split(r"[,;]", syn_txt):
                        s_clean = s.strip()
                        if len(s_clean) > 1 and s_clean not in entry["keywords"]:
                            entry["keywords"].append(s_clean)

        # 3. Parse container table
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            header_cols = []
            if rows:
                header_cols = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
            
            if any("contenant" in c for c in header_cols) or any("nbre de tubes" in c for c in header_cols):
                for tr in rows[1:]:
                    tds = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
                    if len(tds) >= 3:
                        entry["containers"].append({
                            "sites": tds[0] if len(tds) > 0 else "Tous les sites",
                            "container": tds[1] if len(tds) > 1 else "",
                            "count": tds[2] if len(tds) > 2 else "1",
                            "specimen": tds[3] if len(tds) > 3 else "Sang",
                            "quantity": tds[4] if len(tds) > 4 else ""
                        })

            if any("microtube" in c for c in header_cols) or (len(header_cols) == 2 and "description" in header_cols[1]):
                for tr in rows[1:]:
                    tds = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
                    if len(tds) >= 2:
                        entry["pediatric_microtubes"].append({
                            "count": tds[0],
                            "description": tds[1]
                        })

        return entry
    except Exception as e:
        print(f"Error parsing {pid}: {e}")
        return None

def build_lab_catalog():
    """Main function to discover, download and parse all lab tests."""
    discovered = discover_all_analysis_pids()
    catalog = {}
    
    print(f"Downloading and parsing {len(discovered)} lab fiches in clean UTF-8...")
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {
            executor.submit(parse_fiche_html, it["PID"], it.get("Name", ""), it.get("Thematic", "")): it["PID"]
            for it in discovered.values()
        }
        done = 0
        for f in as_completed(futures):
            res = f.result()
            if res:
                catalog[res["pid"]] = res
            done += 1
            if done % 150 == 0 or done == len(futures):
                print(f"  Processed {done}/{len(futures)} analyses...")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(catalog, out, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(catalog)} clean parsed lab analyses to {OUTPUT_FILE}")
    return catalog

if __name__ == "__main__":
    build_lab_catalog()
