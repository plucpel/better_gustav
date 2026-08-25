import json

with open("data/gustav_lab_catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

keywords = ["sodium", "potassium", "électrolyte", "troponine", "inr", "créatinine", "urée", "tsh", "ferritine", "lactate", "hémoculture"]

for kw in keywords:
    print(f"\n--- Matches for '{kw}' in Catalog ---")
    count = 0
    for pid, item in catalog.items():
        name = item.get("name", "")
        if kw.lower() in name.lower() or kw.lower() in pid.lower():
            print(f"  [{pid}] {name}")
            count += 1
            if count >= 6:
                break
