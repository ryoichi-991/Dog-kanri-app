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
            ("get", "/family/growth/add"),
            ("get", "/family/growth/add/{dog_id}"),
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

    def test_growth_post_has_short_timeline_path(self):
        self.assertIn('href="/family/growth/add">＋ 成長記録を追加', SOURCE)
        dedicated = SOURCE[SOURCE.index("def family_growth_add_page"):SOURCE.index('@app.get("/family/dogs/{dog_id}/photo")')]
        self.assertIn('name="return_to" value="timeline"', dedicated)
        self.assertNotIn("プロフィール写真・紹介文", dedicated)
        self.assertIn('destination = "/family/timeline"', SOURCE)

    def test_family_pc_navigation_is_sidebar(self):
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn('<aside class="owner-header">', layout_source)
        for label in ("ホーム", "交流", "設定"):
            self.assertIn(f'class="owner-nav-label">{label}', layout_source)
        self.assertIn("position:fixed;inset:0 auto 0 0", layout_source)
        self.assertIn(".owner-view main{{margin:0 0 0 260px", layout_source)

    def test_business_navigation_uses_two_level_groups(self):
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn('class="nav-home" href="/dashboard"', layout_source)
        self.assertIn("管理画面TOP", layout_source)
        for key, label in (
            ("daily", "日常業務"),
            ("dogs", "犬の管理"),
            ("breeding", "繁殖と血統"),
            ("business", "健康と販売"),
            ("family-admin", "FAMILY管理"),
            ("system", "システム設定"),
        ):
            self.assertIn(f'data-nav-group="{key}"', layout_source)
            self.assertIn(f"</span>{label}</summary>", layout_source)
        self.assertEqual(layout_source.count('class="nav-group"'), 6)

    def test_business_navigation_restores_and_opens_current_group(self):
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        for marker in (
            "active.closest('.nav-group')",
            "current.open=true",
            "localStorage.getItem(key)==='open'",
            "localStorage.setItem(key,group.open?'open':'closed')",
        ):
            self.assertIn(marker, layout_source)
        self.assertIn(".sidebar nav a:hover,.sidebar nav a.active", layout_source)

    def test_business_navigation_stays_two_column_on_mobile(self):
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn(".sidebar .nav-group-links{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))", layout_source)

    def test_authenticated_pages_get_collapsible_usage_guide_automatically(self):
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn("page_usage_guide(title)", layout_source)
        self.assertIn("if user and", layout_source)
        self.assertIn("heading_end = content.find", layout_source)
        self.assertIn("{content}</div>", layout_source)

    def test_usage_guide_has_consistent_beginner_sections(self):
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        segment = ast.get_source_segment(SOURCE, guide)
        for label in ("この画面の使い方を見る", "この画面でできること", "基本的な使い方", "操作上の注意"):
            self.assertIn(label, segment)
        self.assertIn('<details class="page-guide">', segment)
        self.assertIn("html.escape", segment)

    def test_usage_guide_covers_major_business_and_family_features(self):
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        segment = ast.get_source_segment(SOURCE, guide)
        for keyword in ("通知配信履歴", "LINE公式", "健康", "交配", "出産", "販売犬", "顧客", "法令", "FAMILY", "バックアップ"):
            self.assertIn(keyword, segment)
        self.assertIn("今後追加する画面", ast.get_docstring(guide))

    def test_usage_guide_is_single_column_on_mobile(self):
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn(".page-guide-grid{{display:grid;grid-template-columns:repeat(3", layout_source)
        self.assertIn(".page-guide-grid{{grid-template-columns:1fr}}", layout_source)


if __name__ == "__main__":
    unittest.main()
