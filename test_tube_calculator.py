import json
from tube_calculator import search_analyses, calculate_tubes
from medical_dictionary import CLINICAL_PANELS

print("=== 1. TESTING DETERMINISTIC SEARCH AND AUTOCOMPLETE ===")
queries = ["fsc", "iono", "tropo", "créat", "inr", "bilan hepatique", "gaz", "tsh", "fer"]
for q in queries:
    res = search_analyses(q, limit=3)
    print(f"\nQuery: '{q}' -> {len(res)} results:")
    for r in res:
        if r["type"] == "panel":
            print(f"  [PANEL] {r['name']} ({r['description']})")
        else:
            print(f"  [ANALYSIS] {r['name']} (PID: {r['pid']})")

print("\n=== 2. TESTING CLINICAL CASE 1: ROUTINE ER ADMISSION (FSC, Iono, Urée, Créat, Tropo, Bilan hépatique, INR, PTT, TSH) ===")
test_order_1 = ["fsc", "elec", "uree", "crea", "itrop", "alt", "ast", "bili", "alp", "ptrin", "ptt", "tsh"]
calc_1 = calculate_tubes(test_order_1, site="HEJ", is_pediatric=False)

print(f"Total Containers: {calc_1['total_containers']} (Tubes: {calc_1['total_tubes']}, Bottles: {calc_1['total_bottles']})")
print("\nGenerated Tubes in Order of Draw:")
for t in calc_1["tubes"]:
    print(f"\n  [Step {t['order_step']}] {t['tube_count']}x {t['name']} ({t['cap_color_name']})")
    print(f"    Additive: {t['additive']}")
    print(f"    Analyses ({len(t['analyses'])}): {', '.join([a['name'] for a in t['analyses']])}")
    print(f"    Instructions: {t['special_instructions']}")

print("\n=== 3. TESTING CLINICAL CASE 2: SEPSIS PROTOCOL + BLOOD GAS (Hémocultures, FSC, Lactate, Iono, Gaz, CRP) ===")
test_order_2 = ["hc", "fsc", "lacc", "elec", "gazar", "crp"]
calc_2 = calculate_tubes(test_order_2, site="CHUL", is_pediatric=False)

print(f"Total Containers: {calc_2['total_containers']} (Tubes: {calc_2['total_tubes']}, Bottles: {calc_2['total_bottles']})")
for t in calc_2["tubes"]:
    print(f"\n  [Step {t['order_step']}] {t['tube_count']}x {t['name']} ({t['cap_color_name']})")
    print(f"    Analyses ({len(t['analyses'])}): {', '.join([a['name'] for a in t['analyses']])}")

print("\n=== 4. TESTING CLINICAL CASE 3: PEDIATRIC CASE (CHUL, is_pediatric=True) ===")
test_order_3 = ["fsc", "iono", "bilit", "hcp"]
calc_3 = calculate_tubes(test_order_3, site="CHUL", is_pediatric=True)
print(f"Total Containers: {calc_3['total_containers']} (Tubes: {calc_3['total_tubes']}, Bottles: {calc_3['total_bottles']})")
for t in calc_3["tubes"]:
    print(f"\n  [Step {t['order_step']}] {t['tube_count']}x {t['name']} ({t['cap_color_name']})")
    print(f"    Analyses: {', '.join([a['name'] for a in t['analyses']])}")
