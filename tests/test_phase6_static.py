import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "server.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


class Phase6StaticTests(unittest.TestCase):
    def test_operations_routes_exist(self):
        expected = {
            ("get", "/admin/operations"),
            ("post", "/admin/operations/diagnose"),
            ("post", "/family/backups/verify"),
        }
        routes = set()
        for node in ast.walk(TREE):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app":
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            routes.add((decorator.func.attr, decorator.args[0].value))
        self.assertTrue(expected <= routes, expected - routes)

    def test_delivery_events_are_recorded(self):
        self.assertIn("class OperationEvent", SOURCE)
        email = SOURCE[SOURCE.index("def deliver_email"):SOURCE.index("def queue_email")]
        push = SOURCE[SOURCE.index("def send_web_push"):SOURCE.index("def platform_admin_exists")]
        self.assertIn('record_operation(session, "email", "failed"', email)
        self.assertIn('record_operation(session, "push", "failed"', push)

    def test_backup_integrity_controls(self):
        backup = SOURCE[SOURCE.index("def family_backup_download"):SOURCE.index("def require_mobile_user")]
        for marker in ('manifest["checksums"]', "hashlib.sha256", "zipfile.BadZipFile", "100 * 1024 * 1024"):
            self.assertIn(marker, backup)

    def test_family_home_does_not_duplicate_global_navigation(self):
        home = SOURCE[SOURCE.index("def family_home"):SOURCE.index("def family_notifications")]
        for path in ("/family/notifications", "/family/messages", "/family/announcements", "/family/timeline"):
            self.assertNotIn(f'href="{path}"', home)
        self.assertIn('class="family-home-card"', home)
        self.assertIn('class="family-home-photo"', home)
        self.assertIn('class="family-home-info"', home)


if __name__ == "__main__":
    unittest.main()
