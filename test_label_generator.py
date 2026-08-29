"""
Unit and integration tests for GUSTAV Dymo Tube Label Generator.
"""

import unittest
import io
import fitz

from label_generator import (
    prepare_label_items,
    generate_tube_labels_pdf,
    LABEL_FORMATS,
    format_french_dob,
    format_patient_line_1,
    format_labels_pdf_filename
)

class TestLabelGenerator(unittest.TestCase):

    def setUp(self):
        self.sample_patient = {
            "patient_name": "Stephan Gilbert",
            "ramq": "GILS 6607 0514",
            "dob": "1966-07-05",
            "sex": "M",
            "dossier": "GHA-2568",
            "nurse_name": "Julie Gagnon, Inf.",
            "sample_location": "GMF Saint-Vallier",
            "sample_date": "2026-08-28",
            "sample_time": "08:30"
        }

    def test_french_dob_formatting(self):
        """Verify French text formatting for dates of birth."""
        self.assertEqual(format_french_dob("1966-07-05"), "5 juillet 1966")
        self.assertEqual(format_french_dob("1966-02-19"), "19 février 1966")
        self.assertEqual(format_french_dob("1994-05-31"), "31 mai 1994")
        self.assertEqual(format_french_dob("2000-01-01"), "1 janvier 2000")

    def test_patient_line_1_formatting(self):
        """Verify formatting of line 1 (Name and Dossier)."""
        self.assertEqual(
            format_patient_line_1("Stephan Gilbert", "GHA-2568"),
            "Stephan Gilbert (GHA-2568)"
        )
        self.assertEqual(
            format_patient_line_1("Gilbert, Stephan", "GHA-2568"),
            "Stephan Gilbert (GHA-2568)"
        )
        self.assertEqual(
            format_patient_line_1("Bruno Giguère", ""),
            "Bruno Giguère ()"
        )

    def test_prepare_label_items_3_lines(self):
        """Test that prepared labels have the exact 3-line format."""
        pids = ["fsc", "elec", "ptrin"]
        items = prepare_label_items(
            pids=pids,
            site="Tous les sites",
            is_pediatric=False,
            patient_info=self.sample_patient
        )
        
        self.assertEqual(len(items), 3)
        for item in items:
            self.assertEqual(item["line1"], "Stephan Gilbert (GHA-2568)")
            self.assertEqual(item["line2"], "GILS 6607 0514")
            self.assertEqual(item["line3"], "5 juillet 1966 , M")

    def test_custom_quantity(self):
        """Test custom label quantity."""
        items = prepare_label_items(
            pids=["fsc"],
            patient_info=self.sample_patient,
            custom_quantity=5
        )
        self.assertEqual(len(items), 5)

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
        self.assertEqual(len(doc), 3)
        
        expected_w = LABEL_FORMATS["30336"]["width_pt"]
        expected_h = LABEL_FORMATS["30336"]["height_pt"]
        
        for page in doc:
            self.assertAlmostEqual(page.rect.width, expected_w, places=1)
            self.assertAlmostEqual(page.rect.height, expected_h, places=1)

    def test_label_text_content_in_pdf(self):
        """Verify that generated PDF labels contain strictly the 3 exact lines."""
        pdf_bytes = generate_tube_labels_pdf(
            pids=["fsc", "elec"],
            patient_info=self.sample_patient,
            format_name="30336"
        )
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text = page.get_text()
            self.assertIn("Stephan Gilbert (GHA-2568)", text)
            self.assertIn("GILS 6607 0514", text)
            self.assertIn("5 juillet 1966 , M", text)

    def test_filename_formatting(self):
        """Test clean filename formatting."""
        fname = format_labels_pdf_filename(self.sample_patient)
        self.assertEqual(fname, "Etiquettes - Stephan Gilbert - GILS 6607 0514.pdf")

if __name__ == "__main__":
    unittest.main()
