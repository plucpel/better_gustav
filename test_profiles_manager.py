"""
Automated unit & integration tests for profiles_manager and practitioner directory.
"""

import os
import json
import unittest
from fastapi.testclient import TestClient

from app import app
import profiles_manager
from profiles_manager import (
    normalize_text,
    upsert_prescriber,
    get_all_prescribers,
    update_prescriber,
    delete_prescriber,
    upsert_nurse,
    get_all_nurses,
    update_nurse,
    delete_nurse,
    unified_search_prescribers,
    PRESCRIBERS_FILE,
    NURSES_FILE
)

class TestProfilesManager(unittest.TestCase):

    def setUp(self):
        # Backup test files if exist
        self.prescribers_bak = PRESCRIBERS_FILE + ".bak"
        self.nurses_bak = NURSES_FILE + ".bak"
        
        if os.path.exists(PRESCRIBERS_FILE):
            os.rename(PRESCRIBERS_FILE, self.prescribers_bak)
        if os.path.exists(NURSES_FILE):
            os.rename(NURSES_FILE, self.nurses_bak)
            
        with open(PRESCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        with open(NURSES_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

    def tearDown(self):
        # Restore backups
        if os.path.exists(self.prescribers_bak):
            os.rename(self.prescribers_bak, PRESCRIBERS_FILE)
        elif os.path.exists(PRESCRIBERS_FILE):
            os.remove(PRESCRIBERS_FILE)

        if os.path.exists(self.nurses_bak):
            os.rename(self.nurses_bak, NURSES_FILE)
        elif os.path.exists(NURSES_FILE):
            os.remove(NURSES_FILE)

    def test_normalize_text(self):
        self.assertEqual(normalize_text("Dr. Pierre Martin, MD"), "pierre martin")
        self.assertEqual(normalize_text("Docteur Éloïse Bélanger"), "eloise belanger")
        self.assertEqual(normalize_text("Julie Gagnon, Inf."), "julie gagnon")
        self.assertEqual(normalize_text("Infirmière Marie-Ève Côté"), "marie eve cote")

    def test_prescriber_crud_and_duplicate_protection(self):
        # 1. Add doctor
        doc1 = upsert_prescriber({
            "doctor_name": "Dr. Pierre Martin",
            "doctor_license": "12345",
            "clinic_name": "Clinique Saint-Vallier",
            "clinic_id": "SIL-999"
        })
        self.assertEqual(doc1["doctor_license"], "12345")
        
        # 2. Add with slight typo / variation -> should update existing, not duplicate
        doc2 = upsert_prescriber({
            "doctor_name": "Dr Pierre Martin",
            "doctor_license": "12345",
            "clinic_name": "GMF Saint-Vallier (Mis à jour)"
        })
        all_docs = get_all_prescribers()
        self.assertEqual(len(all_docs), 1)
        self.assertEqual(all_docs[0]["clinic_name"], "GMF Saint-Vallier (Mis à jour)")

        # 3. Add second doctor
        doc3 = upsert_prescriber({
            "doctor_name": "Dr. Sophie Roy",
            "doctor_license": "67890",
            "clinic_name": "Clinique Montcalm"
        })
        self.assertEqual(len(get_all_prescribers()), 2)

        # 4. Search
        search_res = unified_search_prescribers("67890")
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["doctor_name"], "Dr. Sophie Roy")

        # 5. Delete
        self.assertTrue(delete_prescriber(doc3["id"]))
        self.assertEqual(len(get_all_prescribers()), 1)

    def test_nurse_crud_and_duplicate_protection(self):
        # 1. Add nurse
        n1 = upsert_nurse({
            "nurse_name": "Julie Gagnon, Inf.",
            "sample_location": "Prélèvements externes HEJ"
        })
        self.assertEqual(n1["nurse_name"], "Julie Gagnon, Inf.")

        # 2. Add with minor typo / punctuation difference -> merge
        n2 = upsert_nurse({
            "nurse_name": "Julie Gagnon",
            "sample_location": "Prélèvements externes HSFA"
        })
        all_nurses = get_all_nurses()
        self.assertEqual(len(all_nurses), 1)
        self.assertEqual(all_nurses[0]["sample_location"], "Prélèvements externes HSFA")

        # 3. Delete
        self.assertTrue(delete_nurse(all_nurses[0]["id"]))
        self.assertEqual(len(get_all_nurses()), 0)

    def test_api_rest_endpoints(self):
        client = TestClient(app)

        # 1. Create Prescriber via API
        res = client.post("/api/prescribers", json={
            "doctor_name": "Dr. Jean Tremblay",
            "doctor_license": "99999",
            "clinic_name": "Clinique Université Laval"
        })
        self.assertEqual(res.status_code, 200)
        doc_id = res.json()["id"]

        # 2. Search Prescriber
        res_search = client.get("/api/prescribers/search?q=Tremblay")
        self.assertEqual(res_search.status_code, 200)
        self.assertGreaterEqual(len(res_search.json()), 1)

        # 3. Create Nurse via API
        res_nurse = client.post("/api/nurses", json={
            "nurse_name": "Marc Lavoie",
            "sample_location": "CHUL Unité 3"
        })
        self.assertEqual(res_nurse.status_code, 200)
        nurse_id = res_nurse.json()["id"]

        # 4. Auto-learning via Requisition PDF generation
        payload_pdf = {
            "pids": ["fsc", "elec"],
            "site": "Hôpital Enfant-Jésus (HEJ)",
            "patient_info": {
                "patient_name": "Dupont, Guy",
                "doctor_name": "Dr. Caroline Belzile",
                "doctor_license": "88888",
                "clinic_name": "Clinique des Rivières",
                "nurse_name": "Éric Gagnon",
                "sample_location": "Soins Intensifs HEJ"
            }
        }
        res_pdf = client.post("/api/requisition/pdf", json=payload_pdf)
        self.assertEqual(res_pdf.status_code, 200)

        # Verify Caroline Belzile & Éric Gagnon were auto-saved on server
        prescribers = client.get("/api/prescribers").json()
        self.assertTrue(any(p["doctor_license"] == "88888" for p in prescribers))

        nurses = client.get("/api/nurses").json()
        self.assertTrue(any("Gagnon" in n["nurse_name"] for n in nurses))

if __name__ == "__main__":
    unittest.main()
