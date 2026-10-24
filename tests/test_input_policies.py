"""Security and API contract input policy regression tests."""
import unittest
from casepacks.engine import evaluate


class TestPolicy81(unittest.TestCase):
    """Verify get allowed."""
    def test_get_allowed(self):
        self.assertIs(evaluate(('GET', '/items', 200, 'viewer', 'allow')), True)
