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

    def test_critical_delay_tests(self):
        """Tests with short transit delay (< 15-30 min) like blood gases and lactates must be flagged."""
        delay_pids = [
            "gazar", "gaaco", "gaac", "gaca", "gazc", "gacco", "gavcs",
            "gavco", "gazvs", "gazve", "gazvex", "gaoxv", "gaoxvx",
            "lacc", "lacvs", "lacvsx", "lacsc", "lacp", "lacs", "lact", "acdla",
            "osptv", "osptvx", "cynlc", "cynbl"
        ]
        for pid in delay_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertTrue(restr["is_incompatible"], f"Test '{pid}' should be incompatible!")
                self.assertEqual(restr["type"], "DELAI_CRITIQUE")
                self.assertIn("Délai", restr["badge"])
                self.assertTrue(len(restr["reason"]) > 5)

    def test_dynamic_hospital_protocol_tests(self):
        """Dynamic tests and hospital protocols like salt surcharge or clamp must be flagged."""
        protocol_pids = [
            "epr006", "susel", "catvc", "caspi", "epr001", "epr002", "epr003",
            "gnrh1", "ghstc", "stia1", "stico", "stimi", "gluc2",
            "cosco", "coscox", "cosc1", "cosc1x", "ethr1", "ethr3", "ethr5",
            "copdn", "copdnx", "supd4", "supd8", "sudiv", "sucap",
            "eeana", "hyp5h", "hyp2i", "dxy25"
        ]
        for pid in protocol_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertTrue(restr["is_incompatible"], f"Test '{pid}' should be incompatible!")
                self.assertEqual(restr["type"], "PROTOCOLE_HOSPITALIER")
                self.assertIn("Protocole hospitalier", restr["badge"])
                self.assertTrue(len(restr["reason"]) > 5)

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
        hospital_pids = ["bioq", "hem035", "myd88", "pyrlc", "ffa", "hgh", "inhis", "oxneu", "ckmb", "glyce", "aucun", "cyndi", "albbi", "bicuu", "crpod"]
        for pid in hospital_pids:
            with self.subTest(pid=pid):
                restr = get_external_restriction(pid)
                self.assertTrue(restr["is_incompatible"], f"Test '{pid}' should be incompatible!")
                self.assertEqual(restr["type"], "NON_DISPO_EXTERNE")
                self.assertIn("Non dispo", restr["badge"])

    def test_calculate_tubes_includes_incompatibilities(self):
        """calculate_tubes returns structured list of external incompatibilities."""
        # Mix from user screenshot: Gaz artériel, Lactate capillaire, Surcharge sel + Routine FSC
        pids = ["fsc", "gazar", "lacc", "epr006"]
        res = calculate_tubes(pids)
        
        self.assertIn("external_incompatibilities", res)
        incomps = res["external_incompatibilities"]
        self.assertEqual(len(incomps), 3)
        
        incomp_pids = [item["pid"] for item in incomps]
        self.assertIn("gazar", incomp_pids)
        self.assertIn("lacc", incomp_pids)
        self.assertIn("epr006", incomp_pids)
        self.assertNotIn("fsc", incomp_pids)

    def test_search_analyses_includes_restriction_metadata(self):
        """search_analyses returns external_restriction on analysis objects."""
        results = search_analyses("gazar")
        item = next((r for r in results if r.get("pid") == "gazar"), None)
        self.assertIsNotNone(item)
        self.assertTrue(item["external_restriction"]["is_incompatible"])
        self.assertEqual(item["external_restriction"]["type"], "DELAI_CRITIQUE")

if __name__ == "__main__":
    unittest.main()
