"""
Automated unit and integration test suite for multi-requisition PDF form support and concatenation.
"""

import os
import unittest
import fitz
from fastapi.testclient import TestClient

from app import app
from requisition_filler import (
    inspect_multi_requisitions,
    generate_multi_form_requisition_pdf,
    REQUISITION_FORMS
)

class TestMultiRequisitions(unittest.TestCase):

    def setUp(self):
        self.patient_info = {
            "patient_name": "Bélanger, Éloïse",
            "ramq": "BELE 1234 5678",
            "dossier": "9876543",
            "dob": "1992-07-15",
            "sex": "F",
            "doctor_name": "Dr. Jean Gagnon",
            "doctor_license": "76076",
            "clinic_name": "Clinique Médicale Lebourgneuf",
            "clinic_id": "SIL-1234",
            "doctor_copy": "Dr. Marc Dupont",
            "doctor_copy_license": "55443",
            "nurse_name": "Stéphanie Gagnon OIIQ:2111799 RAMQ:821838",
            "sample_location": "Soins infirmiers Isabelle Lechasseur, 120-777 boul. Lebourgneuf, Québec, G2J 1C3",
            "sample_date": "2026-08-26",
            "sample_time": "09:15",
            "clinical_info": "Bilan de contrôle annuel"
        }

    def test_single_form_general(self):
        pids = ["fsc", "elec", "uree", "crea"]
        inspection = inspect_multi_requisitions(pids)
        
        self.assertEqual(inspection["total_pages"], 1)
        self.assertEqual(len(inspection["active_forms"]), 1)
        self.assertEqual(inspection["active_forms"][0]["form_id"], "general")
        self.assertEqual(inspection["active_forms"][0]["matched_count"], 4)

        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 1)

    def test_specialized_multidisciplinary_form(self):
        pids = ["gazar", "homo", "c34sp", "anpch", "plach"]
        inspection = inspect_multi_requisitions(pids)
        
        self.assertEqual(inspection["total_pages"], 1)
        self.assertEqual(inspection["active_forms"][0]["form_id"], "spec_multi")
        self.assertEqual(inspection["active_forms"][0]["matched_count"], 5)

        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 1)

        # Check GAZAR and HOMO Glace are ticked
        page = doc[0]
        fields = {w.field_name: w.field_value for w in page.widgets() if w.field_value and str(w.field_value) != "Off"}
        self.assertEqual(fields.get("GAZAR"), "On")
        self.assertEqual(fields.get("HOMO Glace"), "On")
        self.assertEqual(fields.get("ANPCH"), "On")
        self.assertEqual(fields.get("PLACH"), "On")

    def test_microbiology_general_form(self):
        pids = ["hc", "selle", "closd", "curi", "vagi"]
        inspection = inspect_multi_requisitions(pids)
        
        self.assertEqual(inspection["total_pages"], 1)
        self.assertEqual(inspection["active_forms"][0]["form_id"], "micro_gen")
        self.assertGreaterEqual(inspection["active_forms"][0]["matched_count"], 4)

        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 1)

    def test_microbiology_molecular_form(self):
        pids = ["adeng", "cvvih", "inabv", "mepan"]
        inspection = inspect_multi_requisitions(pids)
        
        self.assertEqual(inspection["total_pages"], 1)
        self.assertEqual(inspection["active_forms"][0]["form_id"], "micro_mol")
        self.assertEqual(inspection["active_forms"][0]["matched_count"], 4)

        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 1)

    def test_multi_form_concatenation_and_shared_metadata(self):
        # 1 analysis from each of the 4 forms + 1 uncheckboxed analysis
        pids = [
            "fsc",          # General
            "gazar",        # Spec Multi
            "hc",           # Micro Gen
            "adeng",        # Micro Mol
            "custom_gene"   # Other
        ]
        inspection = inspect_multi_requisitions(pids)
        
        self.assertEqual(inspection["total_pages"], 4)
        self.assertEqual(len(inspection["active_forms"]), 4)
        form_ids = [f["form_id"] for f in inspection["active_forms"]]
        self.assertIn("general", form_ids)
        self.assertIn("spec_multi", form_ids)
        self.assertIn("micro_gen", form_ids)
        self.assertIn("micro_mol", form_ids)

        # Generate combined PDF
        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 4)

        # Assert every single page has the identical clinician and patient metadata
        for page_idx, page in enumerate(doc):
            fields = {w.field_name: w.field_value for w in page.widgets() if w.field_value}
            
            # Check doctor name
            self.assertTrue(
                any("Gagnon" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing doctor name"
            )
            # Check license
            self.assertTrue(
                any("76076" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing doctor license"
            )
            # Check nurse with OIIQ & RAMQ
            self.assertTrue(
                any("2111799" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing nurse OIIQ"
            )
            # Check sample location
            self.assertTrue(
                any("Lebourgneuf" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing sample location"
            )
            # Check patient name & RAMQ
            self.assertTrue(
                any("Bélanger" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing patient name"
            )
            self.assertTrue(
                any("BELE" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing patient RAMQ"
            )

    def test_api_endpoints_multi_requisition(self):
        client = TestClient(app)
        client.post("/api/auth/login", json={"pin": "415263"})
        
        # Test inspection endpoint
        res_inspect = client.post("/api/requisition/inspect", json={
            "pids": ["fsc", "gazar", "hc"],
            "site": "Hôpital de l'Enfant-Jésus (HEJ)"
        })
        self.assertEqual(res_inspect.status_code, 200)
        data = res_inspect.json()
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(len(data["active_forms"]), 3)

        # Test PDF generation endpoint
        res_pdf = client.post("/api/requisition/pdf", json={
            "pids": ["fsc", "gazar", "hc"],
            "site": "Hôpital de l'Enfant-Jésus (HEJ)",
            "patient_info": self.patient_info
        })
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.headers["content-type"], "application/pdf")
        
        doc = fitz.open(stream=res_pdf.content, filetype="pdf")
        self.assertEqual(len(doc), 3)

    def test_banque_de_sang_form_checkboxes(self):
        pids = [
            "bds001",  # Coombs direct
            "bds002",  # Groupe sanguin
            "bds003",  # Groupe sanguin et recherche d'anticorps
            "bds004",  # Phénotype érythrocytaire
            "bds005",  # Titrage agglutinines froides
            "bds006",  # Titrage d'anticorps immuns
            "bds007",  # Investigation réaction transfusionnelle
            "bds008"   # 2e détermination ABO Rh
        ]
        inspection = inspect_multi_requisitions(pids)
        self.assertEqual(inspection["total_pages"], 1)
        self.assertEqual(inspection["active_forms"][0]["form_id"], "banque_sang")
        self.assertEqual(inspection["active_forms"][0]["matched_count"], 8)

        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 1)

        page = doc[0]
        fields = {w.field_name: w.field_value for w in page.widgets() if w.field_value and str(w.field_value) not in ["Off", ""]}
        
        # Verify checkable analyses are checked
        self.assertEqual(fields.get("COOMBS DIRECT"), "Yes")
        self.assertEqual(fields.get("GROUPE SANGUIN (ABO Rh)"), "Yes")
        self.assertEqual(fields.get("GROUPE SANGUIN ET RECHERCHE D’ANTICORPS"), "Yes")
        self.assertEqual(fields.get("PHÉNOTYPES ÉRYTHROCYTAIRES"), "Yes")
        self.assertEqual(fields.get("TITRAGE AGGLUTININES FROIDES"), "Yes")
        self.assertEqual(fields.get("TITRAGE D’ANTICORPS IMMUNS"), "Yes")
        self.assertEqual(fields.get("INVESTIGATION RÉACTION TRANSFUSIONNELLE"), "Yes")
        self.assertEqual(fields.get("2e DÉTERMINATION ABO Rh"), "Yes")

        # Verify headers
        self.assertIn("Gagnon", fields.get("doctor_name", ""))
        self.assertEqual(fields.get("doctor_license"), "76076")
        self.assertIn("2111799", fields.get("nurse_name", ""))
        self.assertIn("Lebourgneuf", fields.get("sample_location", ""))
        self.assertEqual(fields.get("ramq"), "BELE 1234 5678")
        self.assertEqual(fields.get("Sexe_F"), "Yes")
        self.assertEqual(fields.get("patient_name"), "Bélanger")
        self.assertEqual(fields.get("patient_firstname"), "Éloïse")

    def test_banque_de_sang_multi_page_merge(self):
        # General + Spec Multi + Blood Bank
        pids = ["fsc", "gazar", "bds003", "bds008"]
        inspection = inspect_multi_requisitions(pids)
        self.assertEqual(inspection["total_pages"], 3)
        form_ids = [f["form_id"] for f in inspection["active_forms"]]
        self.assertIn("general", form_ids)
        self.assertIn("spec_multi", form_ids)
        self.assertIn("banque_sang", form_ids)

        pdf_bytes = generate_multi_form_requisition_pdf(pids, patient_info=self.patient_info)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 3)

        # Assert every single page has the doctor, nurse, and patient info
        for page_idx, page in enumerate(doc):
            fields = {w.field_name: w.field_value for w in page.widgets() if w.field_value}
            self.assertTrue(
                any("Gagnon" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing doctor name"
            )
            self.assertTrue(
                any("BELE" in str(v) for v in fields.values()),
                f"Page {page_idx+1} is missing patient RAMQ"
            )

if __name__ == "__main__":
    unittest.main()

