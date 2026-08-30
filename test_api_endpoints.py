import os
import shutil
import json
from starlette.testclient import TestClient
from app import app
from profiles_manager import PRESCRIBERS_FILE, NURSES_FILE, LOCATIONS_FILE

client = TestClient(app)

def test_app():
    # Backup live files
    bak_files = []
    for f in [PRESCRIBERS_FILE, NURSES_FILE, LOCATIONS_FILE]:
        if os.path.exists(f):
            bak = f + ".testbak"
            shutil.copy2(f, bak)
            bak_files.append((f, bak))

    try:
        _run_all_endpoint_tests()
    finally:
        # Restore live files
        for orig, bak in bak_files:
            if os.path.exists(bak):
                shutil.move(bak, orig)

def _run_all_endpoint_tests():
    print("=== 0. Testing PIN & Session Authentication Flow ===")
    # 0a. Initial unauthenticated access
    r_unauth = client.get("/")
    assert r_unauth.status_code == 200
    assert "Authentification requise" in r_unauth.text
    print("  -> Unauthenticated GET / serves PIN login page correctly.")

    r_api_unauth = client.get("/api/panels")
    assert r_api_unauth.status_code == 401
    print("  -> Unauthenticated API request blocked with 401 Unauthorized.")

    # 0b. Invalid PIN attempt
    r_bad_login = client.post("/api/auth/login", json={"pin": "000000"})
    assert r_bad_login.status_code == 401
    print("  -> Invalid PIN rejected with 401.")

    # 0c. Valid PIN attempt
    r_good_login = client.post("/api/auth/login", json={"pin": "415263"})
    assert r_good_login.status_code == 200
    assert "gustav_session" in client.cookies
    print("  -> Valid PIN accepted with 200 and session cookie established.")

    print("\n=== 1. Testing GET / (Authenticated) ===")
    r = client.get("/")
    assert r.status_code == 200
    assert "GUSTAV" in r.text
    assert "Manuel des prélèvements" in r.text
    print("  -> Authenticated UI served successfully.")

    print("\n=== 2. Testing GET /api/panels (Authenticated) ===")
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

    print("\n=== 9. Testing Acide urique (sang) -> Blood tube (Menthe), NOT Urine ===")
    acuri_payload = {"pids": ["acuri"]}
    r = client.post("/api/calculate", json=acuri_payload)
    assert r.status_code == 200
    acuri_data = r.json()
    assert acuri_data["total_tubes"] == 1, f"Acide urique (sang) must require 1 blood tube, got {acuri_data['total_tubes']}"
    assert acuri_data["total_urine"] == 0, f"Acide urique (sang) must NOT require a urine container, got {acuri_data['total_urine']}"
    assert acuri_data["tubes"][0]["category_key"] == "HEPARINE_LITHIUM"
    print(f"  -> Verified Acide urique (sang): 1 Tube {acuri_data['tubes'][0]['name']} ({acuri_data['tubes'][0]['cap_color_name']}), 0 urine containers.")

    print("\n=== 10. Testing POST /api/prescribers/bulk and Search ===")
    # Login again for authenticated test
    client.post("/api/auth/login", json={"pin": "415263"})
    
    test_docs = [
        {"doctor_name": "Alexandra Lambert", "doctor_license": "16350", "clinic_name": "Clinique Saint-Vallier"},
        {"firstname": "Jean", "lastname": "Tremblay", "number": "99887", "clinic": "GMF Lebourgneuf"}
    ]
    r_bulk = client.post("/api/prescribers/bulk", json=test_docs)
    assert r_bulk.status_code == 200
    bulk_data = r_bulk.json()
    assert bulk_data["status"] == "success"
    assert bulk_data["added"] >= 1 or bulk_data["updated"] >= 1
    print(f"  -> Bulk import successful: {bulk_data}")

    # Search by license
    r_search_lic = client.get("/api/prescribers/search?q=16350")
    assert r_search_lic.status_code == 200
    found_lic = r_search_lic.json()
    assert len(found_lic) > 0
    assert "16350" in found_lic[0]["doctor_license"]
    print(f"  -> Search by license '16350' found: {found_lic[0]['doctor_name']} ({found_lic[0]['doctor_license']})")

    # Search by inverted name order
    r_search_rev = client.get("/api/prescribers/search?q=Lambert+Alexandra")
    assert r_search_rev.status_code == 200
    found_rev = r_search_rev.json()
    assert len(found_rev) > 0
    assert "Lambert" in found_rev[0]["doctor_name"]
    print(f"  -> Inverted name search 'Lambert Alexandra' found: {found_rev[0]['doctor_name']}")

    print("\n=== 11. Testing POST /api/labels/preview and /api/labels/pdf (Dymo 30336) ===")
    label_req = {
        "pids": ["fsc", "elec", "ptrin"],
        "site": "Hôpital Enfant-Jésus (HEJ)",
        "is_pediatric": False,
        "format": "30336",
        "patient_info": {
            "patient_name": "Tremblay, Jean",
            "ramq": "TREJ 8005 1512",
            "dob": "1980-05-15",
            "sex": "M",
            "dossier": "1234567",
            "nurse_name": "Julie Gagnon, Inf.",
            "sample_location": "GMF Saint-Vallier"
        }
    }
    r_prev = client.post("/api/labels/preview", json=label_req)
    assert r_prev.status_code == 200
    prev_data = r_prev.json()
    assert prev_data["total_labels"] == 3
    assert len(prev_data["labels"]) == 3
    assert prev_data["format"]["name"].startswith("Dymo 30336")
    print(f"  -> /api/labels/preview generated {prev_data['total_labels']} labels successfully.")

    r_pdf = client.post("/api/labels/pdf", json=label_req)
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert len(r_pdf.content) > 1000
    print(f"  -> /api/labels/pdf returned valid PDF binary ({len(r_pdf.content)} bytes).")

    print("\n=== 13. Testing POST /api/context/launch and /api/context/consume (Medesync Extension Flow) ===")
    launch_payload = {
        "patient_name": "Patient Test",
        "ramq": "TEST74613019",
        "dob": "1974-11-30",
        "sex": "M",
        "dossier": "3",
        "medesync_id": 35660746,
        "doctor_license": "16350"
    }

    # 13.1 Rejection without secret
    r_no_sec = client.post("/api/context/launch", json=launch_payload)
    assert r_no_sec.status_code == 401
    print("  -> Rejected launch without extension secret (401).")

    # 13.2 Valid launch with secret
    r_launch = client.post(
        "/api/context/launch",
        json=launch_payload,
        headers={"X-Gustav-Secret": "gustav_ext_secret_chatterbox_2026"}
    )
    assert r_launch.status_code == 200
    launch_res = r_launch.json()
    assert "launch_token" in launch_res
    token = launch_res["launch_token"]
    print(f"  -> Generated single-use launch token: {token[:12]}...")

    # 13.3 GET /?launch=<token> sets session cookie and serves index
    unauth_client = TestClient(app)
    r_get_launch = unauth_client.get(f"/?launch={token}")
    assert r_get_launch.status_code == 200
    assert "gustav_session" in unauth_client.cookies
    print("  -> GET /?launch=<token> instantly granted session cookie (PIN bypassed).")

    # 13.4 Consume token
    r_consume = unauth_client.post("/api/context/consume", json={"launch_token": token})
    assert r_consume.status_code == 200
    consumed = r_consume.json()
    assert consumed["patient_info"]["ramq"] == "TEST74613019"
    assert consumed["patient_info"]["patient_name"] == "Patient Test"
    print("  -> Token consumed successfully with patient demographic context.")

    # 13.5 Second consume attempt fails (Single-use strict)
    r_consume_again = unauth_client.post("/api/context/consume", json={"launch_token": token})
    assert r_consume_again.status_code == 404
    print("  -> Re-using consumed token rejected (404 single-use verified).")

    print("\n🎉 ALL API, AUTH, CALCULATION & DYMO LABEL TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_app()
