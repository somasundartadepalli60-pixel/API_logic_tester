"""Security and API contract input policy regression tests."""
import unittest
from casepacks.engine import evaluate


class TestPolicy81(unittest.TestCase):
    """Verify get allowed."""
    def test_get_allowed(self):
        self.assertIs(evaluate(('GET', '/items', 200, 'viewer', 'allow')), True)

class TestPolicy82(unittest.TestCase):
    """Verify post allowed."""
    def test_post_allowed(self):
        self.assertIs(evaluate(('POST', '/items', 201, 'editor', 'allow')), True)

class TestPolicy83(unittest.TestCase):
    """Verify put allowed."""
    def test_put_allowed(self):
        self.assertIs(evaluate(('PUT', '/items/1', 200, 'editor', 'allow')), True)

class TestPolicy84(unittest.TestCase):
    """Verify patch allowed."""
    def test_patch_allowed(self):
        self.assertIs(evaluate(('PATCH', '/items/1', 204, 'editor', 'allow')), True)
