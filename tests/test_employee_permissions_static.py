import ast
import pathlib
import unittest


SOURCE = pathlib.Path(__file__).parents[1] / "server.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)


def function_source(name: str) -> str:
    node = next(item for item in TREE.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    return ast.get_source_segment(TEXT, node)


class EmployeePermissionsStaticTests(unittest.TestCase):
    def test_permission_storage_and_safe_migration_exist(self):
        membership = next(item for item in TREE.body if isinstance(item, ast.ClassDef) and item.name == "Membership")
        self.assertIn("permissions_json", ast.get_source_segment(TEXT, membership))
        self.assertIn("ALTER TABLE IF EXISTS tenant_memberships ADD COLUMN IF NOT EXISTS permissions_json TEXT", TEXT)

    def test_permission_matrix_has_all_required_actions(self):
        for action in ("view", "edit", "delete", "export", "approve"):
            self.assertIn(f'"{action}"', TEXT[TEXT.index("EMPLOYEE_PERMISSION_ACTIONS"):TEXT.index("PREFECTURES")])

    def test_employee_routes_enforce_server_side_permissions(self):
        dependency = function_source("require_tenant_user")
        self.assertIn("permission_group_for_path(request.url.path)", dependency)
        self.assertIn("permission_action_for_request(request)", dependency)
        self.assertIn("if not employee_can", dependency)

    def test_admin_can_edit_only_current_tenant_employee(self):
        page = function_source("employee_permissions_edit")
        update = function_source("employee_permissions_update")
        for segment in (page, update):
            self.assertIn("Membership.tenant_id == tenant.id", segment)
            self.assertIn("Membership.role == Role.employee", segment)
        self.assertIn("with_for_update()", update)
        self.assertIn('form.get("confirmed")', update)

    def test_new_employee_receives_safe_default(self):
        add = function_source("membership_add")
        self.assertIn('employee_permission_defaults("general")', add)
        general = TEXT[TEXT.index('"general":'):TEXT.index('"care":')]
        self.assertNotIn('"finance"', general)
        self.assertNotIn('"legal"', general)

    def test_legacy_employees_keep_existing_access_until_saved(self):
        parser = function_source("membership_permissions")
        page = function_source("employee_permissions_edit")
        self.assertIn("legacy employee", parser)
        self.assertIn("従来どおり全機能を利用できます", page)

    def test_employee_navigation_and_dashboard_are_filtered(self):
        layout = function_source("layout")
        dashboard = function_source("dashboard")
        self.assertIn("permitted_nav_link", layout)
        self.assertIn("employee_can", layout)
        self.assertIn("employee_can", dashboard)

    def test_approved_employee_can_review_expense_requests(self):
        page = function_source("finance_expense_requests_page")
        approve = function_source("finance_expense_request_approve")
        reject = function_source("finance_expense_request_reject")
        self.assertIn('employee_can(user, "finance", "approve")', page)
        self.assertIn("Depends(require_tenant_user)", approve)
        self.assertIn("Depends(require_tenant_user)", reject)

    def test_delete_permission_controls_dog_archiving(self):
        dogs_page = function_source("dogs_page")
        archive = function_source("dog_archive")
        action = function_source("permission_action_for_request")
        self.assertIn('employee_can(user, "dogs", "delete")', dogs_page)
        self.assertIn("Depends(require_tenant_user)", archive)
        self.assertIn('"/archive"', action)


if __name__ == "__main__":
    unittest.main()
