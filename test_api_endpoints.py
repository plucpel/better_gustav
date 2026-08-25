import json
from starlette.testclient import TestClient
from app import app

client = TestClient(app)

def test_app():
    print("=== 1. Testing GET / ===")
    r = client.get("/")
    assert r.status_code == 200
    assert "GUSTAV" in r.text
    print("  -> UI served successfully.")

    print("\n=== 2. Testing GET /api/panels ===")
    r = client.get("/api/panels")
    assert r.status_code == 200
    panels = r.json()
    assert "bilan_base" in panels
    print(f"  -> Panels retrieved: {len(panels)} panels found.")

    print("\n=== 3. Testing GET /api/search?q=fsc ===")
    r = client.get("/api/search?q=fsc")
    assert r.status_code == 200
    res = r.json()
    assert len(res) > 0
    print(f"  -> Search 'fsc' returned {len(res)} items (top: {res[0]['name']}).")

    print("\n=== 4. Testing POST /api/calculate with Case 1 (FSC + Iono + Urée + Créat + Tropo + Bilan hépatique + INR + PTT) ===")
    payload = {
        "pids": ["fsc", "elec", "uree", "crea", "itrop", "alt", "ast", "bili", "alp", "ptrin", "ptt", "tsh"],
        "site": "Hôpital Enfant-Jésus (HEJ)",
        "is_pediatric": False
    }
    r = client.post("/api/calculate", json=payload)
    assert r.status_code == 200
    data = r.json()
    print(f"  -> Total Containers: {data['total_containers']} (Tubes: {data['total_tubes']}, Bottles: {data['total_bottles']})")
    assert data['total_tubes'] == 3
    print("  -> Verified exact tube count: 3 tubes (Bleu pâle, Menthe, Lavande).")
    for t in data["tubes"]:
        print(f"     Step {t['order_step']} : {t['tube_count']}x {t['name']} ({len(t['analyses'])} analyses)")

    print("\n=== 5. Testing Pediatric Case (CHUL, is_pediatric=True) ===")
    ped_payload = {
        "pids": ["fsc", "elec", "bili", "hc"],
        "site": "Centre hospitalier Université Laval (CHUL)",
        "is_pediatric": True
    }
    r = client.post("/api/calculate", json=ped_payload)
    assert r.status_code == 200
    ped_data = r.json()
    assert ped_data["total_bottles"] == 1
    assert ped_data["total_tubes"] == 2
    print(f"  -> Pediatric Output: {ped_data['total_tubes']} Microtubes + {ped_data['total_bottles']} Flacon pédiatrique.")

    print("\n=== 6. Testing GET /api/analysis/fsc ===")
    r = client.get("/api/analysis/fsc")
    assert r.status_code == 200
    fsc_data = r.json()
    assert fsc_data["pid"] == "fsc"
    print(f"  -> Analysis detail for FSC: {fsc_data['name']} retrieved.")

    print("\n=== 7. Testing Fecal Analyses (C. diff + Calprotectine + Coproculture) ===")
    fecal_payload = {"pids": ["closd", "caprs", "selle"]}
    r = client.post("/api/calculate", json=fecal_payload)
    assert r.status_code == 200
    f_data = r.json()
    assert f_data["total_tubes"] == 0, "Fecal analyses must NOT recommend blood tubes!"
    assert f_data["total_fecal"] == 2
    print(f"  -> Verified Fecal output: {f_data['total_fecal']} Contenants de selles (0 Blood Tubes).")
    for t in f_data["tubes"]:
        print(f"     • {t['tube_count']}x {t['name']} ({t['cap_color_name']})")

    print("\n=== 8. Testing Urine Analyses (SMU + ECBU + Urines 24h) ===")
    urine_payload = {"pids": ["anuri", "curi", "uruc"]}
    r = client.post("/api/calculate", json=urine_payload)
    assert r.status_code == 200
    u_data = r.json()
    assert u_data["total_tubes"] == 0, "Urine analyses must NOT recommend blood tubes!"
    assert u_data["total_urine"] == 3
    print(f"  -> Verified Urine output: {u_data['total_urine']} Contenants d'urines (0 Blood Tubes).")
    for t in u_data["tubes"]:
        print(f"     • {t['tube_count']}x {t['name']} ({t['cap_color_name']})")

    print("\n ALL API & CALCULATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_app()
