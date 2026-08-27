import json
from collections import defaultdict

with open("data/gustav_lab_catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

print(f"Loaded {len(catalog)} analyses.")

container_types = defaultdict(int)
for item in catalog.values():
    for c in item.get("containers", []):
        container_types[c["container"]] += 1

print("\nTop 30 Container Types:")
for k, v in sorted(container_types.items(), key=lambda x: x[1], reverse=True)[:30]:
    print(f"  {k}: {v}")

print("\nSample analyses:")
for pid in ["fsc", "gly", "iono", "tropi", "tsh", "inr", "creat", "ferrix", "hba1c", "hcp"]:
    if pid in catalog:
        it = catalog[pid]
        print(f"\n[{pid}] {it['name']}:")
        for c in it["containers"]:
            print(f"   - Site: {c['sites'][:40]} | Contenant: {c['container']} | Qty: {c['quantity']}")
        if it.get("pediatric_microtubes"):
            print(f"   - Microtubes: {it['pediatric_microtubes']}")
