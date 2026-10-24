"""Offline validation of API contract cases."""
import importlib
import re

def evaluate(case):
    method, path, status, role, expected = case
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return False
    if not path.startswith("/") or "//" in path:
        return False
    if not isinstance(status, int) or status < 100 or status > 599:
        return False
    if role not in ("guest", "viewer", "editor", "admin", "service"):
        return False
    return expected in ("allow", "deny", "review")

def validate_pack(number):
    module = importlib.import_module(f"casepacks.pack_{number:03d}")
    return sum(evaluate(case) for case in module.CASES), len(module.CASES)
