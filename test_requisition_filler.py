"""
Unit and integration tests for the OPTILAB PDF Requisition generator feature in Gustav.
"""

import unittest
import io
import fitz
from requisition_filler import (
    inspect_requisition_selection,
    generate_filled_requisition_pdf,
    PID_TO_CHECKBOX,
    CHECKBOX_METADATA
)
from fastapi.testclient import TestClient
from app import app

class TestRequisitionFiller(unittest.TestCase):

    def test_all_pid_to_checkbox_mappings_exist_in_template(self):
        """Ensure every mapped checkbox field name actually exists in the PDF template."""
        doc = fitz.open("/Users/ppelleti/Documents/Gustav/data/requete_analyses_generales_optilab.pdf")
        pdf_checkbox_names = {w.field_name for w in doc[0].widgets() if w.field_type_string == "CheckBox"}
        
        for pid, field_name in PID_TO_CHECKBOX.items():
            self.assertIn(
                field_name,
                pdf_checkbox_names,
                f"Field name '{field_name}' mapped from PID '{pid}' not found in PDF template checkboxes"
            )

    def test_routine_admission_inspection(self):
        """Test inspection of standard emergency/admission panel."""
        pids = ["fsc", "elec", "uree", "crea", "alt", "ast", "bili", "alp", "ggt", "tsh", "ptrin", "ptt", "itrop"]
        res = inspect_requisition_selection(pids, site="Hôpital Saint-François d'Assise (HSFA)")
        
        self.assertEqual(res["total_other"], 0)
        self.assertEqual(res["total_matched"], 13)
        
        matched_fields = {m["field_name"] for m in res["matched_checkboxes"]}
        expected_fields = {"FSC", "ELEC", "UREE", "CREA", "ALT", "AST", "BILI", "ALP", "GGT", "TSH", "PTRIN", "PTT", "ITROP"}
        self.assertEqual(matched_fields, expected_fields)

    def test_troponin_site_variation(self):
        """Test that HEJ selects TTROP while HSFA/CHUL select ITROP."""
        pids = ["tropo"]
        
        # 1. HEJ site
        res_hej = inspect_requisition_selection(pids, site="Hôpital Enfant-Jésus (HEJ)")
        self.assertIn("TTROP", res_hej["checked_fields"])
        self.assertNotIn("ITROP", res_hej["checked_fields"])
        
        # 2. HSFA site
        res_hsfa = inspect_requisition_selection(pids, site="Hôpital Saint-François d'Assise (HSFA)")
        self.assertIn("ITROP", res_hsfa["checked_fields"])
        self.assertNotIn("TTROP", res_hsfa["checked_fields"])

    def test_special_unlisted_analyses_routing(self):
        """Tests that tests not available as checkboxes route cleanly into 'AUTRES ANALYSES'."""
        pids = ["fsc", "elec", "cort", "vitd", "caprs"]
        res = inspect_requisition_selection(pids)
        
        matched_fields = {m["field_name"] for m in res["matched_checkboxes"]}
        self.assertIn("FSC", matched_fields)
        self.assertIn("ELEC", matched_fields)
        
        other_pids = {o["pid"] for o in res["other_analyses"]}
        self.assertIn("cort", other_pids)
        self.assertIn("vitd", other_pids)
        self.assertIn("caprs", other_pids)
        self.assertEqual(res["total_other"], 3)

    def test_pdf_binary_generation_and_widget_states(self):
        """Generate a PDF and re-open it to verify checkbox states and text fields."""
        pids = ["fsc", "elec", "crea", "glu", "tsh", "b12", "hba1c", "cort", "vitd"]
        patient_info = {
            "ramq": "TREJ 8005 1512",
            "dossier": "1234567",
            "room": "Civière 12",
            "patient_name": "Tremblay, Jean",
            "dob": "1980-05-15",
            "sex": "M",
            "clinical_info": "Suspicion diabète et hypothyroïdie",
            "doctor_name": "Dr. Pierre Martin",
            "doctor_license": "12345"
        }
        
        pdf_bytes = generate_filled_requisition_pdf(
            pids=pids,
            site="Hôpital Enfant-Jésus (HEJ)",
            patient_info=patient_info
        )
        
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 50000)
        
        # Verify with PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        
        active_checkboxes = set()
        text_values = {}
        radio_value = None
        
        for w in page.widgets():
            if w.field_type_string == "CheckBox" and w.field_value not in ("", "Off", None):
                active_checkboxes.add(w.field_name)
            elif w.field_type_string == "Text" and w.field_value:
                text_values[w.field_name] = w.field_value
            elif w.field_type_string == "RadioButton" and w.field_name == "Sexe" and w.field_value not in ("Off", None):
                radio_value = w.field_value
                
        expected_checked = {"FSC", "ELEC", "CREA", "GLU", "TSH", "B12", "HBA1C"}
        self.assertEqual(active_checkboxes, expected_checked)
        
        # Verify text fields
        self.assertEqual(text_values.get("Text12"), "TREJ 8005 1512")
        self.assertEqual(text_values.get("Text13"), "1234567")
        self.assertEqual(text_values.get("Text14"), "Hôpital Enfant-Jésus (HEJ)")
        self.assertEqual(text_values.get("Text15"), "Civière 12")
        self.assertEqual(text_values.get("Text16"), "Tremblay, Jean")
        self.assertEqual(text_values.get("Text17"), "1980-05-15")
        self.assertEqual(text_values.get("Text18"), "Suspicion diabète et hypothyroïdie")
        self.assertEqual(text_values.get("Text6"), "Dr. Pierre Martin")
        self.assertEqual(text_values.get("Text7"), "12345")
        
        # Verify 'AUTRES ANALYSES' contains Cortisol and Vitamine D
        other_content = text_values.get("AUTRES ANALYSES OU DEMANDES SPÉCIALES AUTRES", "")
        self.assertIn("CORT", other_content.upper())
        self.assertIn("VITD", other_content.upper())

    def test_clinic_name_sanitization_and_font_scaling(self):
        """Verify that clinic names with 'Centre hospitalier' and trailing parentheses are sanitized on the PDF."""
        patient_info = {
            "doctor_name": "Dr. Jean Gagnon",
            "doctor_license": "54321",
            "clinic_name": "CENTRE HOSPITALIER DE L'UNIVERSITE LAVAL ( 101)",
            "clinic_id": "031000176"
        }
        pdf_bytes = generate_filled_requisition_pdf(
            pids=["fsc"],
            site="Tous les sites",
            patient_info=patient_info
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text_values = {}
        text_fontsizes = {}
        for w in page.widgets():
            if w.field_type_string == "Text" and w.field_value:
                text_values[w.field_name] = w.field_value
                text_fontsizes[w.field_name] = w.text_fontsize

        # Text8 is clinic_name in general requisition
        self.assertEqual(text_values.get("Text8"), "CH DE L'UNIVERSITE LAVAL")
        self.assertEqual(text_values.get("Text9"), "031000176")
        # Ensure fontsize is scaled appropriately (between 6.8 and 8.0)
        self.assertLessEqual(text_fontsizes.get("Text8"), 8.0)
        self.assertGreaterEqual(text_fontsizes.get("Text8"), 6.8)

    def test_api_endpoints_integration(self):
        """Test the FastAPI endpoints for inspection and PDF generation."""
        client = TestClient(app)
        
        # 1. Test POST /api/requisition/inspect
        payload_inspect = {
            "pids": ["fsc", "elec", "uree", "crea", "ptrin", "ptt"],
            "site": "Hôpital Saint-François d'Assise (HSFA)"
        }
        res = client.post("/api/requisition/inspect", json=payload_inspect)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_matched"], 6)
        self.assertEqual(data["total_other"], 0)
        
        # 2. Test POST /api/requisition/pdf
        payload_pdf = {
            "pids": ["fsc", "elec", "uree", "crea", "ptrin", "ptt"],
            "site": "Hôpital Saint-François d'Assise (HSFA)",
            "patient_info": {
                "patient_name": "Tremblay, Jean",
                "ramq": "TREJ 8005 1512"
            }
        }
        res_pdf = client.post("/api/requisition/pdf", json=payload_pdf)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.headers["content-type"], "application/pdf")
        self.assertGreater(len(res_pdf.content), 50000)
        
        # 3. Test GET /api/requisition/pdf
        res_get = client.get("/api/requisition/pdf?pids=fsc,elec,crea&site=Tous+les+sites")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.headers["content-type"], "application/pdf")
        self.assertGreater(len(res_get.content), 50000)

        # 4. Test POST /api/ramq/decode (1D and 2D)
        res_1d = client.post("/api/ramq/decode", json={"payload": "TREJ 8504 1212"})
        self.assertEqual(res_1d.status_code, 200)
        data_1d = res_1d.json()
        self.assertEqual(data_1d["ramq"], "TREJ 8504 1212")
        self.assertEqual(data_1d["dob"], "1985-04-12")
        self.assertEqual(data_1d["sex"], "M")

        res_2d = client.post("/api/ramq/decode", json={"payload": "BELE 9257 1500\nBÉLANGER\nÉLOÏSE\n1992-07-15\nF"})
        self.assertEqual(res_2d.status_code, 200)
        data_2d = res_2d.json()
        self.assertEqual(data_2d["ramq"], "BELE 9257 1500")
        self.assertEqual(data_2d["patient_name"], "Bélanger, Éloïse")
        self.assertEqual(data_2d["dob"], "1992-07-15")
        self.assertEqual(data_2d["sex"], "F")

        # 5. Test POST /api/ramq/scan_image (PDF417 image decoding)
        import zxingcpp
        import numpy as np
        import cv2
        import base64
        gen = zxingcpp.create_barcode("PELLETIER|LUC|PELP81110915|19811109|M", zxingcpp.BarcodeFormat.PDF417)
        img_arr = np.array(zxingcpp.write_barcode_to_image(gen))
        _, buf = cv2.imencode(".jpg", img_arr)
        b64 = base64.b64encode(buf).decode("utf-8")

        res_img = client.post("/api/ramq/scan_image", json={"image_base64": b64})
        self.assertEqual(res_img.status_code, 200)
        data_img = res_img.json()
        self.assertTrue(data_img["success"])
        self.assertEqual(data_img["ramq"], "PELP 8111 0915")
        self.assertEqual(data_img["patient_name"], "Pelletier, Luc")
        self.assertEqual(data_img["dob"], "1981-11-09")
        self.assertEqual(data_img["sex"], "M")

if __name__ == "__main__":
    unittest.main()
