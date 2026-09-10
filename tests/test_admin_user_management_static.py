import ast
import pathlib
import unittest


SOURCE = pathlib.Path(__file__).parents[1] / "server.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)


def function_source(name: str) -> str:
    node = next(item for item in TREE.body if isinstance(item, ast.FunctionDef) and item.name == name)
    return ast.get_source_segment(TEXT, node)


class AdminUserManagementStaticTests(unittest.TestCase):
    def test_registered_user_search_is_a_separate_confirmation_step(self):
        self.assertIn('@app.post("/admin/users/search"', TEXT)
        page = function_source("render_user_management")
        self.assertIn("登録ユーザーを検索", page)
        self.assertIn("検索結果", page)
        self.assertIn("現在の所属", page)
        self.assertIn("アカウント状態", page)

    def test_email_lookup_is_normalized_and_case_insensitive(self):
        search = function_source("user_search")
        add = function_source("membership_add")
        for segment in (search, add):
            self.assertIn("normalize_email(email)", segment)
            self.assertIn("func.lower(User.email) == normalized", segment)

    def test_membership_add_requires_confirmation_and_active_account(self):
        add = function_source("membership_add")
        self.assertIn("confirmed: bool = Form(False)", add)
        self.assertIn("if not account.active", add)
        self.assertIn("if not confirmed", add)

    def test_customer_record_without_login_account_is_explained(self):
        page = function_source("render_user_management")
        self.assertIn("顧客台帳には同じメールアドレスがあります", page)
        self.assertIn('href="/register"', page)


if __name__ == "__main__":
    unittest.main()
