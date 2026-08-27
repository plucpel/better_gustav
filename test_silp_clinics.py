"""
test_silp_clinics.py - Unit tests for SIL-P Clinics dataset, indexing, searching, and API endpoints.
"""

import unittest
from fastapi.testclient import TestClient
from app import app
from clinics_manager import (
    search_clinics,
    get_available_sites,
    get_available_types,
    get_clinic_by_id,
    normalize_text
)

class TestSilpClinics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_normalize_text(self):
        self.assertEqual(normalize_text("Hôpital Saint-François d'Assise"), "hopital saint francois d assise")
        self.assertEqual(normalize_text("Éléphant & Co."), "elephant co")
        self.assertEqual(normalize_text(""), "")

    def test_sanitize_clinic_name(self):
        from clinics_manager import sanitize_clinic_name
        self.assertEqual(
            sanitize_clinic_name("PHARM. UNIPRIX SANTE N.D.L.B. ( LEBOURGNEUF)"),
            "PHARM. UNIPRIX SANTE N.D.L.B."
        )
        self.assertEqual(
            sanitize_clinic_name("CENTRE HOSPITALIER DE L'UNIVERSITE LAVAL ( 101)"),
            "CH DE L'UNIVERSITE LAVAL"
        )
        self.assertEqual(
            sanitize_clinic_name("CENTRE HOSPITALIER REGIONAL DU GRAND-PORTAGE"),
            "CH REGIONAL DU GRAND-PORTAGE"
        )
        self.assertEqual(
            sanitize_clinic_name("GMF MACLINIQUE LEBOURGNEUF 2 ( RESEAU)"),
            "GMF MACLINIQUE LEBOURGNEUF 2"
        )
        self.assertEqual(
            sanitize_clinic_name("SOINS INFIRMIERS ISABELLE DESCHENES - RESEAU INFIRMIA ( BEAUPORT)"),
            "SOINS INFIRMIERS ISABELLE DESCHENES - RESEAU INFIRMIA"
        )
        self.assertEqual(
            sanitize_clinic_name("Centre Hospitalier Universitaire"),
            "CH Universitaire"
        )
        self.assertEqual(
            sanitize_clinic_name("Ctre Hospitalier de Granby ( 012)"),
            "CH de Granby"
        )

    def test_dataset_loaded(self):
        sites = get_available_sites()
        self.assertGreater(len(sites), 10)
        types = get_available_types()
        self.assertGreater(len(types), 5)

    def test_search_by_silp_id(self):
        # Search by exact ID
        res = search_clinics("031000176")
        self.assertGreaterEqual(res["total"], 1)
        first = res["clinics"][0]
        self.assertEqual(first["id"], "031000176")
        self.assertIn("MYRIADE", first["name"].upper())

    def test_search_by_name(self):
        res = search_clinics("Lebourgneuf")
        self.assertGreaterEqual(res["total"], 1)
        # Verify that all results contain Lebourgneuf in name or address or search blob
        for c in res["clinics"][:5]:
            matched = "lebourgneuf" in c["name"].lower() or "lebourgneuf" in c["address"].lower() or "lebourgneuf" in c["city"].lower()
            self.assertTrue(matched)

    def test_filter_by_site(self):
        res = search_clinics("", site="CA101 - Pavillon Centre hospitalier de l'Université Laval", limit=20)
        self.assertGreater(res["total"], 0)
        for c in res["clinics"]:
            self.assertEqual(c["site"], "CA101 - Pavillon Centre hospitalier de l'Université Laval")

    def test_filter_by_type(self):
        res = search_clinics("clinique", clinic_type="E", limit=20)
        self.assertGreater(res["total"], 0)
        for c in res["clinics"]:
            self.assertEqual(c["type"], "E")

    def test_get_clinic_by_id(self):
        clinic = get_clinic_by_id("031000176")
        self.assertIsNotNone(clinic)
        self.assertEqual(clinic["id"], "031000176")
        self.assertEqual(clinic["city"], "QUEBEC")

        not_found = get_clinic_by_id("INVALID_ID_999999")
        self.assertIsNone(not_found)

    def test_api_endpoints(self):
        # 1. Search endpoint
        resp = self.client.get("/api/clinics/search?q=Lebourgneuf&limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("clinics", data)
        self.assertLessEqual(len(data["clinics"]), 10)

        # 2. Sites endpoint
        resp_sites = self.client.get("/api/clinics/sites")
        self.assertEqual(resp_sites.status_code, 200)
        sites_data = resp_sites.json()
        self.assertIsInstance(sites_data, list)
        self.assertGreater(len(sites_data), 0)

        # 3. Types endpoint
        resp_types = self.client.get("/api/clinics/types")
        self.assertEqual(resp_types.status_code, 200)
        types_data = resp_types.json()
        self.assertIsInstance(types_data, list)
        self.assertGreater(len(types_data), 0)

        # 4. Single clinic endpoint
        resp_single = self.client.get("/api/clinics/031000176")
        self.assertEqual(resp_single.status_code, 200)
        single_data = resp_single.json()
        self.assertEqual(single_data["id"], "031000176")

        # 5. Not found single clinic
        resp_404 = self.client.get("/api/clinics/NON_EXISTENT_ID_999")
        self.assertEqual(resp_404.status_code, 404)

if __name__ == "__main__":
    unittest.main()
