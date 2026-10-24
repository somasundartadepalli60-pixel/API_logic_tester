import unittest
from casepacks.engine import evaluate, validate_pack
class CasepackTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(evaluate(("GET", "/items", 200, "viewer", "allow")))
    def test_invalid(self):
        self.assertFalse(evaluate(("WRONG", "/items", 200, "viewer", "allow")))
    def test_pack_one(self):
        self.assertEqual(validate_pack(1), (5100, 5100))
if __name__ == "__main__": unittest.main()
