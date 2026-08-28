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

    def test_business_calendar_combines_manual_and_automatic_schedules(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "calendar_page")
        segment = ast.get_source_segment(SOURCE, route)
        for model in ("TaskEvent", "HeatCycle", "BreedingRecord", "Litter", "Vaccination", "HealthRecord", "Medication", "DiseaseHistory", "LegalDocument"):
            self.assertIn(model, segment)
        for source in ("Todo", "ヒート記録", "交配記録", "ワクチン", "健診", "投薬", "再診・経過確認", "法令・行政"):
            self.assertIn(source, segment)
        self.assertNotIn("今後、ヒート・交配", segment)

    def test_business_calendar_is_tenant_scoped_and_validates_filters(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "calendar_page")
        segment = ast.get_source_segment(SOURCE, route)
        self.assertGreaterEqual(segment.count("tenant.id"), 9)
        for marker in ("allowed_categories", "allowed_states", "表示月を確認してください", "検索条件を確認してください"):
            self.assertIn(marker, segment)
        for field in ("month", "calendar_category", "calendar_state"):
            self.assertIn(f'name="{field}"', segment)
        self.assertIn('name="show_all"', segment)
        self.assertIn("show_all or first_day <= item[0] <= month_end", segment)

    def test_business_calendar_calculates_predictions_and_states(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "calendar_page")
        segment = ast.get_source_segment(SOURCE, route)
        self.assertIn("item.start_date + timedelta(days=180)", segment)
        self.assertIn("item.mating_date + timedelta(days=63)", segment)
        self.assertIn('"overdue" if day < date.today()', segment)
        self.assertIn('item.status == "completed"', segment)
        self.assertIn("item.id in completed_breedings", segment)
        self.assertIn("event_keys", segment)
        self.assertIn("if key in event_keys", segment)
        self.assertIn('task_category = item.category if item.category in {"breeding", "health", "legal", "sales"}', segment)

    def test_business_calendar_has_mobile_cards(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "calendar_page")
        segment = ast.get_source_segment(SOURCE, route)
        self.assertIn("calendar-mobile-card", segment)
        self.assertIn("calendar-desktop-only", segment)
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn(".calendar-mobile-only{{display:none}}", layout_source)
        self.assertIn(".health-mobile-only,.calendar-mobile-only{{display:block}}", layout_source)

    def test_dashboard_priority_items_are_tenant_scoped_and_incomplete(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "dashboard_priority_items")
        segment = ast.get_source_segment(SOURCE, helper)
        self.assertIn("TaskEvent.tenant_id == tenant_id", segment)
        self.assertIn("TaskEvent.completed.is_(False)", segment)
        self.assertIn("LegalDocument.tenant_id == tenant_id", segment)
        self.assertIn('LegalDocument.status != "completed"', segment)
        self.assertIn("today + timedelta(days=7)", segment)
        self.assertIn("return items[:50]", segment)

    def test_dashboard_shows_overdue_today_and_week_priorities(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "dashboard")
        segment = ast.get_source_segment(SOURCE, route)
        self.assertIn("dashboard_priority_items(tenant.id, session)", segment)
        for marker in ("overdue_count", "today_count", "week_count", "期限超過", "本日の予定", "7日以内", "今日の要対応"):
            self.assertIn(marker, segment)
        self.assertIn("priority_items[:10]", segment)
        self.assertIn("calendar_state=overdue&show_all=true", segment)

    def test_dashboard_has_quick_actions_and_mobile_priority_layout(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "dashboard")
        segment = ast.get_source_segment(SOURCE, route)
        for label in ("業務カレンダー", "Todoを登録", "健康管理"):
            self.assertIn(label, segment)
        layout_source = SOURCE[SOURCE.index("def layout"):SOURCE.index("def family_layout")]
        self.assertIn(".priority-list{{display:grid", layout_source)
        self.assertIn(".priority-item{{align-items:flex-start;flex-direction:column}}", layout_source)


if __name__ == "__main__":
    unittest.main()
