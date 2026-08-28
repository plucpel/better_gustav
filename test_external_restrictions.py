import unittest
from tube_calculator import get_external_restriction, calculate_tubes, search_analyses

class TestExternalRestrictions(unittest.TestCase):
    
    def test_routine_tests_not_restricted(self):
        """Standard routine tests must NOT have any external restrictions."""
        routine_pids = [
            "fsc", "elec", "uree", "crea", "alt", "ast", "tsh",
            "ferri", "ptrin", "ptt", "itrop", "hba1c", "crp",
            "b12", "folat", "cholt", "hdl", "trigl", "magne",
            "phos", "calct", "albu", "bili", "ggt", "lip",
            "anuri", "curi", "closd", "selle", "hc"
        ]
        for pid in routine_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertFalse(
                    restr["is_incompatible"],
                    f"Routine analysis '{pid}' should NOT be restricted, but got: {restr}"
                )

    def test_ice_restricted_tests(self):
        """Tests requiring ice must be flagged with SUR_GLACE."""
        ice_pids = ["ammo", "ammu", "acth", "calci", "gast", "metnl", "3meth", "vitc", "proap", "yvegf", "yglug", "yhiss", "xsest", "bio001", "oxap", "il6"]
        for pid in ice_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertTrue(restr["is_incompatible"], f"Test '{pid}' should be incompatible!")
                self.assertEqual(restr["type"], "SUR_GLACE")
                self.assertIn("Sur glace", restr["badge"])
                self.assertTrue(len(restr["reason"]) > 5)

    def test_decant_restricted_tests(self):
        """Tests requiring decantation/centrifugation/fast freezing must be flagged with DECANTE_CONGELE."""
        decant_pids = ["chga", "yqudn", "xah50", "xcmbl", "xcfia", "tt", "porph", "a21hy", "xnclc", "damiu", "porbu", "pneug", "xartv"]
        for pid in decant_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertTrue(restr["is_incompatible"], f"Test '{pid}' should be incompatible!")
                self.assertEqual(restr["type"], "DECANTE_CONGELE")
                self.assertTrue(len(restr["reason"]) > 5)

    def test_hospital_only_restricted_tests(self):
        """Tests reserved for hospital / CHU corridor must be flagged with NON_DISPO_EXTERNE."""
        hospital_pids = ["bioq", "hem035", "myd88", "catvc", "epr006", "susel", "pyrlc", "ffa", "hgh", "inhis", "oxneu", "ckmb", "glyce", "aucun", "cyndi", "albbi", "bicuu", "crpod"]
        for pid in hospital_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertTrue(restr["is_incompatible"], f"Test '{pid}' should be incompatible!")
                self.assertEqual(restr["type"], "NON_DISPO_EXTERNE")
                self.assertIn("Non dispo", restr["badge"])

    def test_calculate_tubes_includes_incompatibilities(self):
        """calculate_tubes returns a structured list of external incompatibilities."""
        # Mix of routine and restricted
        pids = ["fsc", "elec", "ammo", "bioq", "yvegf"]
        res = calculate_tubes(pids)
        
        self.assertIn("external_incompatibilities", res)
        incomps = res["external_incompatibilities"]
        self.assertEqual(len(incomps), 3)
        
        incomp_pids = [item["pid"] for item in incomps]
        self.assertIn("ammo", incomp_pids)
        self.assertIn("bioq", incomp_pids)
        self.assertIn("yvegf", incomp_pids)
        self.assertNotIn("fsc", incomp_pids)
        self.assertNotIn("elec", incomp_pids)

    def test_search_analyses_includes_restriction_metadata(self):
        """search_analyses returns external_restriction on analysis objects."""
        results = search_analyses("ammoniac")
        ammo_item = next((r for r in results if r.get("pid") == "ammo"), None)
        self.assertIsNotNone(ammo_item)
        self.assertTrue(ammo_item["external_restriction"]["is_incompatible"])
        self.assertEqual(ammo_item["external_restriction"]["type"], "SUR_GLACE")

if __name__ == "__main__":
    unittest.main()
