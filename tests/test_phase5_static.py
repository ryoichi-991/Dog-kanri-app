import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "server.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


class Phase5StaticTests(unittest.TestCase):
    def test_required_routes_exist(self):
        expected = {
            ("post", "/family/backups/download"),
            ("post", "/family/push-test"),
            ("post", "/api/v1/auth/token"),
            ("get", "/api/v1/dogs"),
            ("get", "/api/v1/timeline"),
        }
        routes = set()
        for node in ast.walk(TREE):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
                    continue
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    routes.add((decorator.func.attr, decorator.args[0].value))
        self.assertTrue(expected <= routes, expected - routes)

    def test_security_controls_are_present(self):
        for marker in ("class AuthThrottle", "security_headers_and_origin", "auth_throttle_blocked", "ensure_vapid_keys"):
            self.assertIn(marker, SOURCE)

    def test_backup_excludes_credentials(self):
        backup = SOURCE[SOURCE.index("def family_backup_download"):SOURCE.index("def require_mobile_user")]
        self.assertIn('{"password_hash"}', backup)
        self.assertNotIn("MobileApiToken", backup)
        self.assertNotIn("LoginSession", backup)


if __name__ == "__main__":
    unittest.main()