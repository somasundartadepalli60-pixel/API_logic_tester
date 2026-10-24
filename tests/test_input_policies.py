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

class TestPolicy85(unittest.TestCase):
    """Verify delete allowed."""
    def test_delete_allowed(self):
        self.assertIs(evaluate(('DELETE', '/items/1', 204, 'admin', 'allow')), True)

class TestPolicy86(unittest.TestCase):
    """Verify head allowed."""
    def test_head_allowed(self):
        self.assertIs(evaluate(('HEAD', '/items', 200, 'guest', 'allow')), True)

class TestPolicy87(unittest.TestCase):
    """Verify options allowed."""
    def test_options_allowed(self):
        self.assertIs(evaluate(('OPTIONS', '/items', 204, 'service', 'allow')), True)

class TestPolicy88(unittest.TestCase):
    """Verify lowercase method rejected."""
    def test_lowercase_method_rejected(self):
        self.assertIs(evaluate(('get', '/items', 200, 'viewer', 'allow')), False)

class TestPolicy89(unittest.TestCase):
    """Verify unknown method rejected."""
    def test_unknown_method_rejected(self):
        self.assertIs(evaluate(('TRACE', '/items', 200, 'viewer', 'allow')), False)

class TestPolicy90(unittest.TestCase):
    """Verify relative path rejected."""
    def test_relative_path_rejected(self):
        self.assertIs(evaluate(('GET', 'items', 200, 'viewer', 'allow')), False)

class TestPolicy91(unittest.TestCase):
    """Verify double slash rejected."""
    def test_double_slash_rejected(self):
        self.assertIs(evaluate(('GET', '//items', 200, 'viewer', 'allow')), False)

class TestPolicy92(unittest.TestCase):
    """Verify internal double slash rejected."""
    def test_internal_double_slash_rejected(self):
        self.assertIs(evaluate(('GET', '/items//1', 200, 'viewer', 'allow')), False)

class TestPolicy93(unittest.TestCase):
    """Verify status below range rejected."""
    def test_status_below_range_rejected(self):
        self.assertIs(evaluate(('GET', '/items', 99, 'viewer', 'allow')), False)

class TestPolicy94(unittest.TestCase):
    """Verify status above range rejected."""
    def test_status_above_range_rejected(self):
        self.assertIs(evaluate(('GET', '/items', 600, 'viewer', 'allow')), False)

class TestPolicy95(unittest.TestCase):
    """Verify string status rejected."""
    def test_string_status_rejected(self):
        self.assertIs(evaluate(('GET', '/items', '200', 'viewer', 'allow')), False)

class TestPolicy96(unittest.TestCase):
    """Verify unknown role rejected."""
    def test_unknown_role_rejected(self):
        self.assertIs(evaluate(('GET', '/items', 200, 'root', 'allow')), False)

class TestPolicy97(unittest.TestCase):
    """Verify guest role accepted."""
    def test_guest_role_accepted(self):
        self.assertIs(evaluate(('GET', '/public', 200, 'guest', 'deny')), True)

class TestPolicy98(unittest.TestCase):
    """Verify service role accepted."""
    def test_service_role_accepted(self):
        self.assertIs(evaluate(('POST', '/jobs', 202, 'service', 'review')), True)

class TestPolicy99(unittest.TestCase):
    """Verify unknown decision rejected."""
    def test_unknown_decision_rejected(self):
        self.assertIs(evaluate(('GET', '/items', 200, 'viewer', 'maybe')), False)
