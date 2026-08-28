"""
Unit and integration tests for GUSTAV Dymo Tube Label Generator.
"""

import unittest
import io
import fitz
import cv2
import zxingcpp
import numpy as np

from label_generator import (
    prepare_label_items,
    generate_tube_labels_pdf,
    LABEL_FORMATS,
    encode_code128_b,
    format_labels_pdf_filename
)

class TestLabelGenerator(unittest.TestCase):

    def setUp(self):
        self.sample_patient = {
            "patient_name": "Tremblay, Jean",
            "ramq": "TREJ 8005 1512",
            "dob": "1980-05-15",
            "sex": "M",
            "dossier": "1234567",
            "nurse_name": "Julie Gagnon, Inf.",
            "sample_location": "GMF Saint-Vallier",
            "sample_date": "2026-08-28",
            "sample_time": "08:30"
        }

    def test_prepare_label_items_counts_and_expansion(self):
        """Test that tubes are properly expanded into individual labels."""
        # Panel: FSC (EDTA), ELEC (HepLi), CITRATE (INR) -> 3 tubes
        pids = ["fsc", "elec", "ptrin"]
        items = prepare_label_items(
            pids=pids,
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient
        )
        
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["sequence_index"], 1)
        self.assertEqual(items[0]["total_sequence"], 3)
        self.assertEqual(items[0]["tube_index_str"], "Tube 1/3")
        self.assertEqual(items[1]["tube_index_str"], "Tube 2/3")
        self.assertEqual(items[2]["tube_index_str"], "Tube 3/3")
        
        # Check patient demographic mapping
        self.assertEqual(items[0]["patient_name"], "Tremblay, Jean")
        self.assertEqual(items[0]["ramq_raw"], "TREJ80051512")
        self.assertEqual(items[0]["ramq_display"], "TREJ 8005 1512")
        self.assertEqual(items[0]["dob"], "1980-05-15")
        self.assertEqual(items[0]["sex"], "M")
        self.assertEqual(items[0]["dossier"], "1234567")

    def test_blood_cultures_pair_expansion(self):
        """Test that adult blood cultures generate 2 distinct labels (Aérobie & Anaérobie)."""
        pids = ["hc"]
        items = prepare_label_items(
            pids=pids,
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient
        )
        
        self.assertEqual(len(items), 2)
        self.assertIn("Aérobie", items[0]["specimen_title"])
        self.assertIn("Anaérobie", items[1]["specimen_title"])

    def test_blood_bank_alert_and_special_alerts(self):
        """Test high-priority alert for Blood Bank and Sur Glace."""
        # Blood bank (Rose / EDTA_ROSE)
        items_bb = prepare_label_items(
            pids=["bds003"],
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient
        )
        self.assertGreaterEqual(len(items_bb), 1)
        self.assertIn("BANQUE DE SANG", items_bb[0]["alert_str"])

        # Gaz sanguin (Sur glace)
        items_gaz = prepare_label_items(
            pids=["gaaco"],
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient
        )
        self.assertGreaterEqual(len(items_gaz), 1)
        self.assertIn("SUR GLACE", items_gaz[0]["alert_str"])

    def test_pdf_dimensions_dymo_30336(self):
        """Test that generated PDF has exact Dymo 30336 dimensions."""
        pids = ["fsc", "elec", "ptrin", "tsh"]
        pdf_bytes = generate_tube_labels_pdf(
            pids=pids,
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient,
            format_name="30336"
        )
        
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 3) # Citrate (1), Heparin (2), EDTA (1) = 3 tubes
        
        expected_w = LABEL_FORMATS["30336"]["width_pt"]
        expected_h = LABEL_FORMATS["30336"]["height_pt"]
        
        for page in doc:
            self.assertAlmostEqual(page.rect.width, expected_w, places=1)
            self.assertAlmostEqual(page.rect.height, expected_h, places=1)

    def test_pdf_dimensions_dymo_30334(self):
        """Test that generated PDF has exact Dymo 30334 dimensions."""
        pids = ["fsc", "elec"]
        pdf_bytes = generate_tube_labels_pdf(
            pids=pids,
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient,
            format_name="30334"
        )
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        expected_w = LABEL_FORMATS["30334"]["width_pt"]
        expected_h = LABEL_FORMATS["30334"]["height_pt"]
        
        for page in doc:
            self.assertAlmostEqual(page.rect.width, expected_w, places=1)
            self.assertAlmostEqual(page.rect.height, expected_h, places=1)

    def test_simplified_label_content_and_numbering(self):
        """Verify that generated PDF labels contain strictly Name, DOB, RAMQ, and 1/X numbering."""
        pids = ["fsc", "elec", "ptrin"]
        pdf_bytes = generate_tube_labels_pdf(
            pids=pids,
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient,
            format_name="30336"
        )
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 3)
        
        for idx, page in enumerate(doc, 1):
            text = page.get_text()
            # 1. Patient Name
            self.assertIn("TREMBLAY, JEAN", text)
            # 2. Numbering (e.g. 1/3, 2/3, 3/3)
            self.assertIn(f"{idx}/3", text)
            # 3. RAMQ
            self.assertIn("RAMQ : TREJ 8005 1512", text)
            # 4. DOB
            self.assertIn("DDN : 1980-05-15 (M)", text)

    def test_filename_formatting(self):
        """Test clean filename formatting."""
        fname = format_labels_pdf_filename(self.sample_patient)
        self.assertEqual(fname, "Etiquettes - Tremblay, Jean - TREJ 8005 1512.pdf")

if __name__ == "__main__":
    unittest.main()
