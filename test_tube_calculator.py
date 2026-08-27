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

print("\n=== 5. TESTING CLINICAL CASE 4: ACIDE URIQUE (SANG vs URINES) ===")
calc_acuri_sang = calculate_tubes(["acuri"], site="HEJ")
assert calc_acuri_sang["total_tubes"] == 1, "Acide urique (sang) must be a blood tube!"
assert calc_acuri_sang["total_urine"] == 0, "Acide urique (sang) must NOT be urine!"
assert calc_acuri_sang["tubes"][0]["category_key"] == "HEPARINE_LITHIUM"
print(f"Acide urique (sang): {calc_acuri_sang['tubes'][0]['name']} (Tubes: {calc_acuri_sang['total_tubes']}, Urine: {calc_acuri_sang['total_urine']}) -> PASS")

calc_acuri_24h = calculate_tubes(["uruc"], site="HEJ")
assert calc_acuri_24h["total_urine"] == 1, "Acide urique 24h must be a urine jug!"
assert calc_acuri_24h["tubes"][0]["category_key"] == "URINE_24H"
print(f"Acide urique (24h): {calc_acuri_24h['tubes'][0]['name']} (Tubes: {calc_acuri_24h['total_tubes']}, Urine: {calc_acuri_24h['total_urine']}) -> PASS")

calc_acuri_miction = calculate_tubes(["aurul"], site="HEJ")
assert calc_acuri_miction["total_urine"] == 1, "Acide urique (miction) must be a urine container!"
assert calc_acuri_miction["tubes"][0]["category_key"] == "URINE_ROUTINE"
print(f"Acide urique (miction): {calc_acuri_miction['tubes'][0]['name']} (Tubes: {calc_acuri_miction['total_tubes']}, Urine: {calc_acuri_miction['total_urine']}) -> PASS")
