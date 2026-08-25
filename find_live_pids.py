import requests

BASE_URL = "https://gustavguideext.chudequebec.ca/AcePtmApi/Api/"
headers = {"Temoin": "defaultSiteId=2&defaultdisciplineId=5"}

queries = ["inr", "rni", "tsh", "creatinine", "uree", "troponine", "potassium", "sodium", "bicarbonate", "plaquettes", "ptc", "tca", "ptt", "dimere", "culture urine", "sommaire"]

for q in queries:
    r = requests.get(f"{BASE_URL}Search/All/true/true", headers={**headers, "PTM-SearchTerms": q})
    if r.status_code == 200:
        items = r.json().get("ResultItems", [])
        print(f"\n--- Query '{q}' -> {len(items)} items ---")
        for it in items[:4]:
            print(f"  [{it.get('PID')}] {it.get('Name')} | Thematic: {it.get('Thematic')}")
