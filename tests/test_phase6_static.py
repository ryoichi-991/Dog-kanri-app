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

    def test_finance_module_has_tenant_scoped_ledger_model_and_routes(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinancialEntry")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "occurred_on", "entry_type", "category", "description", "amount"):
            self.assertIn(marker, model_source)
        for route_name in ("finance_page", "finance_create"):
            self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == route_name for node in TREE.body))
        self.assertIn('"finance": ("収支・経費台帳"', SOURCE)

    def test_finance_page_calculates_monthly_totals_and_sales_receivables(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancialEntry.tenant_id == tenant.id", "income_total", "expense_total", "balance", "unpaid_total", "PuppySale.tenant_id == tenant.id", "category_totals"):
            self.assertIn(marker, segment)
        for label in ("当月入金", "当月経費", "当月収支", "販売未入金", "当月の経費内訳"):
            self.assertIn(label, segment)

    def test_finance_filters_and_create_validation_are_bounded(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_page")
        page_source = ast.get_source_segment(SOURCE, page)
        for field in ("month", "entry_type", "finance_category"):
            self.assertIn(f'name="{field}"', page_source)
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create")
        create_source = ast.get_source_segment(SOURCE, create)
        for marker in ('entry_type not in {"income", "expense"}', "category not in FINANCE_CATEGORIES", "amount <= 0", "len(clean_description) > 200", "tenant_id=tenant.id"):
            self.assertIn(marker, create_source)

    def test_finance_navigation_guide_and_mobile_cards_exist(self):
        self.assertIn('href="/modules/finance"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("収支", "経費", "税務申告用の会計帳簿"):
            self.assertIn(marker, guide_source)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_page")
        page_source = ast.get_source_segment(SOURCE, page)
        self.assertIn("calendar-mobile-card", page_source)
        self.assertIn("calendar-mobile-only", page_source)

    def test_invoice_model_and_routes_are_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "Invoice")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "puppy_sale_id", "invoice_no", "issued_on", "due_on", "amount", "status", "ledger_entry_id"):
            self.assertIn(marker, model_source)
        for route_name in ("invoices_page", "invoice_create", "invoice_status_update", "invoice_pdf"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))

    def test_invoice_creation_is_linked_to_sales_and_validated(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoice_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("PuppySale.id == sale_id", "PuppySale.tenant_id == tenant.id", 'PuppySale.status != "cancelled"', "amount <= 0", "due_day < issue_day", "secrets.token_hex", "tenant_id=tenant.id"):
            self.assertIn(marker, segment)
        self.assertIn('"invoices": ("請求書管理"', SOURCE)

    def test_paid_invoice_requires_receivable_settlement(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoice_status_update")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ('status_value == "paid"', "not invoice.ledger_entry_id", "売掛金・請求書入金消込から実行してください"):
            self.assertIn(marker, segment)
        self.assertIn('invoice.status == "paid" and status_value != "paid"', segment)
        self.assertNotIn("FinancialEntry(", segment)

    def test_invoice_pdf_is_private_and_contains_business_fields(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "build_invoice_pdf")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("invoice_pdf_font", "請 求 書", "請求番号", "ご請求金額（税込）", "請求内容", "お支払期限", "お支払い案内・備考"):
            self.assertIn(marker, segment)
        font_helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoice_pdf_font")
        font_source = ast.get_source_segment(SOURCE, font_helper)
        for marker in ("NotoSansJP", "NotoSansCJK-Regular.ttc", "TTFont", "HeiseiKakuGo-W5"):
            self.assertIn(marker, font_source)
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("fonts-noto-cjk", dockerfile)
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoice_pdf")
        route_source = ast.get_source_segment(SOURCE, route)
        self.assertIn('media_type="application/pdf"', route_source)
        self.assertIn('"Cache-Control": "private, no-store"', route_source)

    def test_invoice_page_has_guide_navigation_and_mobile_cards(self):
        self.assertIn('href="/modules/invoices"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertLess(guide_source.index('(("請求書",)'), guide_source.index('(("収支", "経費", "原価", "請求")'))
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoices_page")
        page_source = ast.get_source_segment(SOURCE, page)
        self.assertIn("calendar-mobile-card", page_source)
        self.assertIn("calendar-mobile-only", page_source)

    def test_cost_allocation_model_and_routes_are_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "CostAllocation")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "financial_entry_id", "dog_id", "litter_id", "amount", "notes"):
            self.assertIn(marker, model_source)
        for route_name in ("costs_page", "cost_allocate"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))
        self.assertIn('"costs": ("原価・利益管理"', SOURCE)

    def test_cost_allocation_rejects_cross_tenant_and_over_allocation(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "cost_allocate")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancialEntry.tenant_id == tenant.id", 'FinancialEntry.entry_type == "expense"', "Dog.tenant_id == tenant.id", "Litter.tenant_id == tenant.id", "CostAllocation.tenant_id == tenant.id", "bool(dog) == bool(litter)", "allocated + amount >", "amount <= 0"):
            self.assertIn(marker, segment)

    def test_costs_page_calculates_litter_revenue_cost_and_profit(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "costs_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("dog.dam_id == litter.dam_id", "dog.birth_date == litter.birth_date", "planned", "received", "unpaid", "litter_cost", "dog_cost", "profit", "realized_profit", "unallocated_total"):
            self.assertIn(marker, segment)
        for label in ("販売予定額", "配賦済み原価", "予定利益", "入金基準利益", "未配賦経費", "出産回別の採算"):
            self.assertIn(label, segment)

    def test_costs_page_has_specific_guide_navigation_and_mobile_cards(self):
        self.assertIn('href="/modules/costs"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertLess(guide_source.index('(("原価", "利益", "採算")'), guide_source.index('(("収支", "経費", "原価", "請求")'))
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "costs_page")
        page_source = ast.get_source_segment(SOURCE, page)
        self.assertIn("calendar-mobile-card", page_source)
        self.assertIn("calendar-mobile-only", page_source)

    def test_finance_document_model_and_routes_are_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceDocument")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "financial_entry_id", "document_type", "issued_by", "document_no", "filename", "content_type", "file_data"):
            self.assertIn(marker, model_source)
        for route_name in ("finance_documents_page", "finance_document_create", "finance_document_file"):
            route = next(node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))
        self.assertIn('"finance/documents": ("領収書・証憑管理"', SOURCE)

    def test_finance_document_upload_validates_type_size_and_filename(self):
        route = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "finance_document_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancialEntry.tenant_id == tenant.id", '"application/pdf"', '"image/jpeg"', '"image/png"', '"image/webp"', "8 * 1024 * 1024 + 1", "len(content) > 8 * 1024 * 1024", "Path(document_file.filename", "allowed_extensions", "suffix not in allowed_extensions", "tenant_id=tenant.id"):
            self.assertIn(marker, segment)

    def test_finance_document_file_is_private_and_nosniff(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_document_file")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinanceDocument.tenant_id == tenant.id", '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"', "Content-Disposition", "quote(item.filename)"):
            self.assertIn(marker, segment)

    def test_finance_documents_have_search_guide_navigation_and_mobile_cards(self):
        self.assertIn('href="/modules/finance/documents"', SOURCE)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_documents_page")
        page_source = ast.get_source_segment(SOURCE, page)
        for marker in ('name="document_type"', 'name="document_keyword"', "calendar-mobile-card", "calendar-mobile-only"):
            self.assertIn(marker, page_source)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("領収書", "証憑", "個人情報や口座情報"):
            self.assertIn(marker, guide_source)

    def test_finance_reports_are_tenant_scoped_and_year_bounded(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_reports_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancialEntry.tenant_id == tenant.id", "PuppySale.tenant_id == tenant.id", "Invoice.tenant_id == tenant.id", "FinanceDocument.tenant_id == tenant.id", "report_year < 2000", "report_year > 2100"):
            self.assertIn(marker, segment)
        self.assertIn('"finance/reports": ("経営収益ダッシュボード"', SOURCE)

    def test_finance_reports_aggregate_management_indicators(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_reports_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("monthly", "annual_income", "annual_expense", "annual_balance", "unpaid_total", "overdue_invoices", "overdue_total", "document_rate", "missing_documents", "category_totals"):
            self.assertIn(marker, segment)
        for label in ("年間入金", "年間経費", "年間収支", "販売未入金", "期限超過請求", "経費証憑保管率", "月別推移", "年間の経費構成"):
            self.assertIn(label, segment)

    def test_finance_reports_have_guide_navigation_and_mobile_cards(self):
        self.assertIn('href="/modules/finance/reports"', SOURCE)
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_reports_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ('name="year"', "calendar-mobile-card", "calendar-mobile-only", 'href="/modules/invoices"', 'href="/modules/finance/documents"', 'href="/modules/costs"'):
            self.assertIn(marker, segment)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("経営収益", guide_source)
        self.assertIn("決算・税務申告", guide_source)

    def test_finance_export_routes_require_tenant_admin_and_password(self):
        for route_name in ("finance_export_page", "finance_export_download"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            segment = ast.get_source_segment(SOURCE, route)
            self.assertIn("require_tenant_admin", segment)
            self.assertIn("tenant.", segment)
        download = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_download")
        segment = ast.get_source_segment(SOURCE, download)
        for marker in ("passwords.verify", "not confirmed", "year < 2000", "year > 2100", "FinancialEntry.tenant_id == tenant.id", "Invoice.tenant_id == tenant.id", "CostAllocation.tenant_id == tenant.id", "FinanceDocument.tenant_id == tenant.id"):
            self.assertIn(marker, segment)

    def test_finance_export_contains_csv_documents_and_checksums(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_csv")
        helper_source = ast.get_source_segment(SOURCE, helper)
        for marker in ('startswith(("=", "+", "-", "@"))', '"\\ufeff"', 'replace("\\x00", "")'):
            self.assertIn(marker, helper_source)
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_download")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("ledger.csv", "invoices.csv", "cost-allocations.csv", "documents.csv", "manifest.json", "hashlib.sha256", "zipfile.ZIP_DEFLATED", "document_files", "record_operation"):
            self.assertIn(marker, segment)

    def test_finance_export_has_safety_limits_private_response_and_guide(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_download")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("200 * 1024 * 1024", "len(documents) > 5000", 'media_type="application/zip"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)
        self.assertIn('"finance/export": ("会計・証憑一括出力"', SOURCE)
        self.assertIn('href="/modules/finance/export"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("会計・証憑一括出力", guide_source)
        self.assertIn("安全な共有方法", guide_source)

    def test_finance_budget_model_and_routes_are_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceBudget")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "year", "month", "entry_type", "category", "amount", "uq_finance_budget_period_category"):
            self.assertIn(marker, model_source)
        for route_name in ("finance_budgets_page", "finance_budget_save"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))
        self.assertIn('"finance/budgets": ("予算管理・予実比較"', SOURCE)

    def test_finance_budget_save_validates_and_upserts(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_budget_save")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("year < 2000", "year > 2100", "month < 1", "month > 12", 'entry_type not in {"income", "expense"}', "category not in FINANCE_CATEGORIES", "amount < 0", "amount > 999999999", "FinanceBudget.tenant_id == tenant.id", "item.amount = amount"):
            self.assertIn(marker, segment)

    def test_finance_budgets_compare_monthly_actuals_and_mobile(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_budgets_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("monthly", "income_budget", "expense_budget", "income_actual", "expense_actual", "income_rate", "expense_rate", "income_gap", "expense_gap", "FinancialEntry.tenant_id == tenant.id"):
            self.assertIn(marker, segment)
        for label in ("年間入金目標", "入金実績・達成率", "年間経費予算", "経費実績・消化率", "月別予実"):
            self.assertIn(label, segment)
        self.assertIn("calendar-mobile-card", segment)
        self.assertIn("calendar-mobile-only", segment)

    def test_finance_budgets_have_specific_guide_and_navigation(self):
        self.assertIn('href="/modules/finance/budgets"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("予算管理", guide_source)
        self.assertIn("予実比較", guide_source)
        self.assertIn("経営判断用の目安", guide_source)

    def test_cashflow_model_and_routes_are_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceCashPlan")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "due_on", "entry_type", "category", "description", "amount", "status", "ledger_entry_id"):
            self.assertIn(marker, model_source)
        for route_name in ("finance_cashflow_page", "finance_cashflow_create", "finance_cashflow_complete"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))
        self.assertIn('"finance/cashflow": ("資金繰り・90日予測"', SOURCE)

    def test_cashflow_forecast_combines_plans_invoices_and_balance(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_cashflow_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("current_balance", "FinanceCashPlan.status == \"planned\"", 'Invoice.status == "issued"', "events.sort", "projected(30)", "projected(60)", "projected(90)", "expected_income", "expected_expense", "running_balance"):
            self.assertIn(marker, segment)
        for label in ("現在の台帳残高", "30日後", "60日後", "90日後", "90日以内の入金予定", "90日以内の支払予定"):
            self.assertIn(label, segment)

    def test_cashflow_create_is_bounded_and_complete_is_idempotent(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_cashflow_create")
        create_source = ast.get_source_segment(SOURCE, create)
        for marker in ("due_day < date.today()", "timedelta(days=730)", 'entry_type not in {"income", "expense"}', "category not in FINANCE_CATEGORIES", "amount <= 0", "amount > 999999999", "len(clean_description) > 200"):
            self.assertIn(marker, create_source)
        complete = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_cashflow_complete")
        complete_source = ast.get_source_segment(SOURCE, complete)
        for marker in ("FinanceCashPlan.tenant_id == tenant.id", 'plan.status != "planned"', "plan.ledger_entry_id", "FinancialEntry", 'plan.status = "completed"', "plan.ledger_entry_id = entry.id"):
            self.assertIn(marker, complete_source)

    def test_cashflow_has_guide_navigation_and_mobile_cards(self):
        self.assertIn('href="/modules/finance/cashflow"', SOURCE)
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_cashflow_page")
        segment = ast.get_source_segment(SOURCE, route)
        self.assertIn("calendar-mobile-card", segment)
        self.assertIn("calendar-mobile-only", segment)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("資金繰り", guide_source)
        self.assertIn("二重計上", guide_source)

    def test_recurring_finance_models_and_routes_are_tenant_scoped(self):
        for model_name in ("FinanceRecurringRule", "FinanceRecurringPosting"):
            model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == model_name)
            self.assertIn("tenant_id", ast.get_source_segment(SOURCE, model))
        posting = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceRecurringPosting")
        self.assertIn("uq_finance_recurring_rule_period", ast.get_source_segment(SOURCE, posting))
        for route_name in ("finance_recurring_page", "finance_recurring_create", "finance_recurring_stop"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))

    def test_recurring_generator_is_month_end_safe_and_idempotent(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "generate_due_finance_recurring")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("calendar.monthrange", "min(rule.day_of_month, last_day)", "target_day < posting_day", "posting_day < rule.start_on", "posting_day > rule.end_on", "FinanceRecurringPosting.period == period", "if exists", "FinancialEntry", "FinanceRecurringPosting", "session.commit()"):
            self.assertIn(marker, segment)
        scheduler = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "dispatch_scheduled_emails")
        self.assertIn("generate_due_finance_recurring(session, date.today())", ast.get_source_segment(SOURCE, scheduler))

    def test_recurring_create_validation_stop_and_mobile_guide(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_recurring_create")
        segment = ast.get_source_segment(SOURCE, create)
        for marker in ("day_of_month < 1", "day_of_month > 31", 'entry_type not in {"income", "expense"}', "category not in FINANCE_CATEGORIES", "amount <= 0", "amount > 999999999", "end_day < start_day", "generate_due_finance_recurring"):
            self.assertIn(marker, segment)
        stop = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_recurring_stop")
        self.assertIn("rule.active = False", ast.get_source_segment(SOURCE, stop))
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_recurring_page")
        page_source = ast.get_source_segment(SOURCE, page)
        self.assertIn("calendar-mobile-card", page_source)
        self.assertIn("calendar-mobile-only", page_source)
        self.assertIn('href="/modules/finance/recurring"', SOURCE)
        self.assertIn('"finance/recurring": ("定期収支・自動登録"', SOURCE)

    def test_finance_account_models_and_routes_are_tenant_scoped(self):
        for model_name in ("FinanceAccount", "FinanceAccountEntry", "FinanceAccountTransfer"):
            model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == model_name)
            self.assertIn("tenant_id", ast.get_source_segment(SOURCE, model))
        assignment = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceAccountEntry")
        self.assertIn("uq_finance_account_entry", ast.get_source_segment(SOURCE, assignment))
        for route_name in ("finance_accounts_page", "finance_account_create", "finance_account_assign", "finance_account_transfer"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))

    def test_finance_account_balances_include_entries_and_transfers(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_accounts_page")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("opening_balance", "FinanceAccountEntry", "entry.entry_type == \"income\"", "transfer.from_account_id", "transfer.to_account_id", "unassigned", "assigned_ids"):
            self.assertIn(marker, segment)
        for label in ("口座・現金残高管理", "台帳記録を口座へ割り当て", "口座間振替", "直近の振替履歴"):
            self.assertIn(label, segment)

    def test_finance_account_assignment_and_transfer_are_validated(self):
        assign = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_account_assign")
        assign_source = ast.get_source_segment(SOURCE, assign)
        for marker in ("FinancialEntry.tenant_id == tenant.id", "FinanceAccount.tenant_id == tenant.id", "FinanceAccount.active.is_(True)", "FinanceAccountEntry.financial_entry_id == financial_entry_id", "if not entry or not account or exists"):
            self.assertIn(marker, assign_source)
        transfer = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_account_transfer")
        transfer_source = ast.get_source_segment(SOURCE, transfer)
        for marker in ("source.id == destination.id", "amount <= 0", "amount > 999999999", "len(notes) > 500", "FinanceAccountTransfer"):
            self.assertIn(marker, transfer_source)

    def test_finance_accounts_have_guide_and_navigation(self):
        self.assertIn('href="/modules/finance/accounts"', SOURCE)
        self.assertIn('"finance/accounts": ("口座・現金残高管理"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("口座・現金", guide_source)
        self.assertIn("収益・経費へ計上されません", guide_source)

    def test_finance_period_close_model_and_admin_routes(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinancePeriodClose")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("uq_finance_period_close", "tenant_id", "year", "month", "income_total", "expense_total", "closed_by_id", "closed_at"):
            self.assertIn(marker, model_source)
        for route_name in ("finance_close_period", "finance_reopen_period"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("require_tenant_admin", ast.get_source_segment(SOURCE, route))

    def test_finance_closing_dashboard_checks_unfinished_items(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("FinanceAccountEntry", "FinanceDocument", "unassigned_count", "missing_document_count", "口座未割当", "経費証憑未保管", "この月を締める"):
            self.assertIn(marker, segment)

    def test_closed_finance_period_blocks_new_postings_and_account_changes(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "ensure_finance_period_open")
        self.assertIn("status_code=409", ast.get_source_segment(SOURCE, helper))
        for route_name in ("finance_create", "finance_cashflow_complete", "finance_account_assign", "finance_account_transfer", "finance_receivable_settle", "finance_statement_settle_invoice", "cost_allocate"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("ensure_finance_period_open", ast.get_source_segment(SOURCE, route))
        recurring = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "generate_due_finance_recurring")
        self.assertIn("finance_period_close", ast.get_source_segment(SOURCE, recurring))

    def test_finance_closing_has_guide_and_navigation(self):
        self.assertIn('href="/modules/finance/closing', SOURCE)
        self.assertIn('"finance/closing": ("月次締め・会計期間ロック"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("会計期間ロック", guide_source)
        self.assertIn("締めた月", guide_source)

    def test_finance_reconciliation_model_and_routes_are_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceAccountReconciliation")
        model_source = ast.get_source_segment(SOURCE, model)
        for marker in ("uq_finance_account_reconciliation", "tenant_id", "account_id", "statement_on", "ledger_balance", "actual_balance", "difference", "checked_by_id"):
            self.assertIn(marker, model_source)
        for route_name in ("finance_reconciliation_page", "finance_reconciliation_save"):
            route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == route_name)
            self.assertIn("tenant.id", ast.get_source_segment(SOURCE, route))

    def test_finance_reconciliation_calculates_historical_account_balance(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_account_balance_on")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("opening_balance", "FinanceAccountEntry", "FinancialEntry.occurred_on <= target_day", "FinanceAccountTransfer.transferred_on <= target_day", "transfer.to_account_id"):
            self.assertIn(marker, segment)

    def test_finance_reconciliation_validates_difference_and_upserts(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_reconciliation_save")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("actual_balance - ledger_balance", "difference and not notes.strip()", "FinanceAccount.active.is_(True)", "item.checked_at", "FinanceAccountReconciliation("):
            self.assertIn(marker, segment)
        for label in ("口座残高照合・差額チェック", "通帳・現金の実残高", "照合履歴", "差額がある場合は必須"):
            self.assertIn(label, SOURCE)

    def test_monthly_close_surfaces_unreconciled_accounts(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("FinanceAccountReconciliation", "reconciliation_day", "unreconciled_count", "月末残高未照合・差額あり", "口座残高を照合"):
            self.assertIn(marker, segment)

    def test_finance_reconciliation_has_guide_and_navigation(self):
        self.assertIn('href="/modules/finance/reconciliation', SOURCE)
        self.assertIn('"finance/reconciliation": ("口座残高照合・差額チェック"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("口座残高照合", guide_source)
        self.assertIn("架空取引", guide_source)

    def test_finance_statement_models_are_tenant_scoped_and_deduplicated(self):
        imported = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceStatementImport")
        import_source = ast.get_source_segment(SOURCE, imported)
        for marker in ("uq_finance_statement_import_hash", "tenant_id", "account_id", "content_hash", "row_count", "matched_count", "imported_by_id"):
            self.assertIn(marker, import_source)
        line = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceStatementLine")
        line_source = ast.get_source_segment(SOURCE, line)
        for marker in ("uq_finance_statement_line_row", "tenant_id", "transacted_on", "entry_type", "amount", "status", "financial_entry_id"):
            self.assertIn(marker, line_source)

    def test_statement_csv_import_is_bounded_and_supports_japanese_files(self):
        route = next(node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "finance_statement_import")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("2 * 1024 * 1024", '"utf-8-sig", "cp932"', "csv.DictReader", "row_no > 1001", "日付", "摘要", "入金額", "出金額", "content_hash"):
            self.assertIn(marker, segment)
        self.assertIn("同じ口座へ同じCSVが取り込み済みです", segment)

    def test_statement_import_auto_matches_only_one_safe_ledger_candidate(self):
        route = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "finance_statement_import")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancialEntry.occurred_on == transaction_day", "FinancialEntry.entry_type == entry_type", "FinancialEntry.amount == amount", "len(usable) == 1", "FinanceStatementLine.financial_entry_id == candidate.id", "finance_period_close", "FinanceAccountEntry"):
            self.assertIn(marker, segment)

    def test_unmatched_statement_line_posts_once_to_open_ledger_period(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statement_line_post")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ('FinanceStatementLine.status == "unmatched"', "category not in FINANCE_CATEGORIES", "ensure_finance_period_open", "FinancialEntry(", "FinanceAccountEntry(", 'line.status = "matched"'):
            self.assertIn(marker, segment)

    def test_finance_statements_have_mobile_ui_guide_and_navigation(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statements_page")
        segment = ast.get_source_segment(SOURCE, page)
        for label in ("銀行明細CSV取込・自動照合", "照合済み", "未処理", "CSVを取り込む", "取込明細", "取込履歴", "calendar-mobile-card"):
            self.assertIn(label, segment)
        self.assertIn('href="/modules/finance/statements', SOURCE)
        self.assertIn('"finance/statements": ("銀行明細CSV取込・自動照合"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("銀行明細CSV", guide_source)
        self.assertIn("重複取込", guide_source)

    def test_monthly_close_surfaces_unmatched_statement_lines(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("FinanceStatementLine", 'FinanceStatementLine.status == "unmatched"', "statement_unmatched_count", "銀行明細未処理", "銀行明細の未処理"):
            self.assertIn(marker, segment)

    def test_finance_categorization_rule_is_tenant_scoped_and_unique(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceCategorizationRule")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ("uq_finance_categorization_rule", "tenant_id", "keyword", "entry_type", "category", "priority", "active", "created_by_id"):
            self.assertIn(marker, segment)

    def test_finance_rule_matching_prefers_priority_then_specific_keyword(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_rule_suggestion")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("line.description.casefold()", "rule.keyword.casefold()", 'rule.entry_type in {"any", line.entry_type}', "-rule.priority", "-len(rule.keyword)"):
            self.assertIn(marker, segment)

    def test_finance_rule_routes_validate_upsert_and_stop_per_tenant(self):
        save = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_rule_save")
        save_source = ast.get_source_segment(SOURCE, save)
        for marker in ('entry_type not in {"any", "income", "expense"}', "category not in FINANCE_CATEGORIES", "priority < 0", "priority > 999", "FinanceCategorizationRule.tenant_id == tenant.id", "rule.active = True"):
            self.assertIn(marker, save_source)
        stop = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_rule_stop")
        stop_source = ast.get_source_segment(SOURCE, stop)
        for marker in ("FinanceCategorizationRule.tenant_id == tenant.id", "FinanceCategorizationRule.active.is_(True)", "rule.active = False"):
            self.assertIn(marker, stop_source)

    def test_statement_suggestions_require_confirmation_and_respect_locks(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statement_apply_suggestions")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("if not confirmed", "len(selected_ids) > 500", "FinanceStatementLine.tenant_id == tenant.id", "FinanceStatementLine.id.in_(selected_ids)", 'FinanceStatementLine.status == "unmatched"', ".limit(500)", "FinanceAccount.tenant_id == tenant.id", "finance_period_close", "finance_rule_suggestion", "FinancialEntry(", "FinanceAccountEntry(", 'line.status = "matched"'):
            self.assertIn(marker, segment)

    def test_finance_rules_have_management_ui_guide_and_candidate_actions(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_rules_page")
        page_source = ast.get_source_segment(SOURCE, page)
        for marker in ("摘要ルール・自動仕訳候補", "摘要キーワード", "優先度", "calendar-mobile-card", "再登録すると有効"):
            self.assertIn(marker, page_source)
        statements = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statements_page")
        statement_source = ast.get_source_segment(SOURCE, statements)
        for marker in ("候補で登録", "費目を選んで登録", "仕訳候補を一括登録", 'name="confirmed"', 'name="line_ids"', 'form="suggestion-batch"'):
            self.assertIn(marker, statement_source)
        self.assertIn('href="/modules/finance/rules"', SOURCE)
        self.assertIn('"finance/rules": ("摘要ルール・自動仕訳候補"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        self.assertIn("確認なしに自動計上されません", guide_source)

    def test_finance_tax_classification_model_is_tenant_scoped_and_unique(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceTaxClassification")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ("uq_finance_tax_classification_entry", "tenant_id", "financial_entry_id", "tax_category", "tax_rate", "invoice_status", "invoice_registration_no", "checked_by_id", "checked_at"):
            self.assertIn(marker, segment)

    def test_estimated_included_tax_uses_tax_inclusive_formula(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "estimated_included_tax")
        segment = ast.get_source_segment(SOURCE, helper)
        self.assertIn("amount * tax_rate // (100 + tax_rate)", segment)
        self.assertIn("if tax_rate else 0", segment)

    def test_input_tax_credit_applies_invoice_transitional_rates_by_date(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_input_tax_credit")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ('invoice_status in {"qualified", "not_required"}', 'invoice_status != "nonqualified"', "date(2023, 10, 1)", "date(2026, 10, 1)", "tax_amount * 80 // 100", "date(2029, 10, 1)", "tax_amount * 50 // 100"):
            self.assertIn(marker, segment)

    def test_finance_tax_page_is_monthly_tenant_scoped_and_mobile(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("FinancialEntry.tenant_id == tenant.id", "FinanceTaxClassification.tenant_id == tenant.id", ".limit(10000)", "taxable_sales", "taxable_expenses", "output_tax", "input_tax", "deductible_input_tax", "estimated_tax_due", "sales_by_rate", "expenses_by_rate", "category_totals", "unclassified_count", "invoice_unconfirmed_count", "calendar-mobile-card", "calendar-mobile-only"):
            self.assertIn(marker, segment)
        for label in ("課税売上（税込）", "課税仕入（税込）", "控除対象仕入税額", "納付見込", "税率別集計", "課税区分別集計", "税区分未分類", "インボイス未確認"):
            self.assertIn(label, segment)

    def test_finance_tax_save_validates_invoice_and_period_lock(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_save")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancialEntry.tenant_id == tenant.id", "ensure_finance_period_open", 'tax_rate not in {8, 10}', 'tax_rate != 0', 're.fullmatch(r"T\\d{13}"', 'invoice_status == "qualified" and not registration_no', "FinanceTaxClassification.tenant_id == tenant.id", "item.checked_at", "session.commit()"):
            self.assertIn(marker, segment)

    def test_tax_journal_accounts_are_standard_and_backfilled_safely(self):
        initialize = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_chart_accounts_initialize"))
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_journal_accounts"))
        for marker in ('"仮払消費税"', '"input_tax"', '"仮受消費税"', '"output_tax"'):
            self.assertIn(marker, initialize)
            self.assertIn(marker, helper)
        for marker in ("FinanceChartAccount.tenant_id == tenant_id", "used_codes", "while str(code_number) in used_codes", "session.flush()"):
            self.assertIn(marker, helper)

    def test_tax_classification_posts_idempotent_balanced_reclassification(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_apply_tax_journal"))
        for marker in ('f"消費税振替：台帳#{entry.id}"', 'FinanceJournalEntry.status == "posted"', "estimated_included_tax", "finance_input_tax_credit", "finance_category_account", 'entry.entry_type == "income"', '("debit", mapped.id, tax_amount)', '("credit", output_tax.id, tax_amount)', '("debit", input_tax.id, tax_amount)', '("credit", mapped.id, tax_amount)', "current_lines", "== desired", "finance_reverse_accrual_journal", 'finance_journal_voucher(session, tenant_id, "TX"', '"tax_journal"'):
            self.assertIn(marker, helper)
        save = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_save"))
        for marker in ("finance_apply_tax_journal", "exc.status_code != 409", "消費税仕訳を保留"):
            self.assertIn(marker, save)

    def test_tax_page_exposes_double_entry_status_and_cautions(self):
        page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_page"))
        for marker in ("tax_descriptions", "FinanceJournalEntry.tenant_id == tenant.id", 'FinanceJournalEntry.status == "posted"', "journaled_entry_ids", "複式仕訳済み", "振替なし", "仮受消費税・仮払消費税", "控除できない部分は費用に残します", "旧仕訳を取消仕訳"):
            self.assertIn(marker, page)

    def test_finance_tax_is_in_close_checks_navigation_and_guide(self):
        closing = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        closing_source = ast.get_source_segment(SOURCE, closing)
        for marker in ("FinanceTaxClassification", "tax_unclassified_count", "invoice_unconfirmed_count", "消費税区分未分類", "インボイス未確認"):
            self.assertIn(marker, closing_source)
        self.assertIn('href="/modules/finance/tax', SOURCE)
        self.assertIn('"finance/tax": ("消費税集計・インボイス確認"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("消費税区分", "インボイス確認", "自動照会しません", "税理士と原資料"):
            self.assertIn(marker, guide_source)

    def test_tax_report_data_is_tenant_period_scoped_bounded_and_aggregated(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_report_data"))
        for marker in ("FinancialEntry.tenant_id == tenant_id", "FinancialEntry.occurred_on >= period_start", "FinancialEntry.occurred_on <= period_end", ".limit(20000)", "FinanceTaxClassification.tenant_id == tenant_id", "monthly", "rate_totals", "finance_input_tax_credit", "unclassified_count", "invoice_unconfirmed_count"):
            self.assertIn(marker, helper)

    def test_tax_annual_report_uses_fiscal_year_monthly_rates_and_admin_scope(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_report_page"))
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "finance_fiscal_period", "finance_fiscal_months", "finance_tax_report_data", "output_total", "credit_total", "年間納付見込", "月別集計", "税率別集計", "/modules/finance/tax/report.csv"):
            self.assertIn(marker, route)

    def test_tax_monthly_and_annual_csv_are_private_and_formula_safe(self):
        monthly = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_csv"))
        annual = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_tax_report_csv"))
        for segment in (monthly, annual):
            for marker in ("finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
                self.assertIn(marker, segment)
        for marker in ("require_tenant_user", "finance_tax_report_data", "finance_input_tax_credit", "控除対象税額"):
            self.assertIn(marker, monthly)
        for marker in ("require_tenant_admin", "finance_fiscal_period", "finance_fiscal_months", "finance_tax_report_data", "年度未分類件数"):
            self.assertIn(marker, annual)

    def test_finance_vendor_and_payable_models_are_tenant_scoped(self):
        vendor = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceVendor")
        vendor_source = ast.get_source_segment(SOURCE, vendor)
        for marker in ("uq_finance_vendor_name", "tenant_id", "invoice_registration_no", "notes", "active", "created_at"):
            self.assertIn(marker, vendor_source)
        payable = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinancePayable")
        payable_source = ast.get_source_segment(SOURCE, payable)
        for marker in ("tenant_id", "vendor_id", "received_on", "due_on", "category", "invoice_no", "status", "paid_on", "account_id", "financial_entry_id", "unique=True", "created_by_id"):
            self.assertIn(marker, payable_source)

    def test_finance_payables_page_has_status_totals_actions_and_mobile_ui(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_payables_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ('payable_status not in {"", "unpaid", "paid", "cancelled"}', "FinanceVendor.tenant_id == tenant.id", "FinanceAccount.tenant_id == tenant.id", "FinancePayable.tenant_id == tenant.id", "unpaid_total", "overdue_total", "due_soon", 'name="confirmed"', "calendar-desktop-only", "calendar-mobile-card"):
            self.assertIn(marker, segment)
        for label in ("未払総額", "期限超過", "30日以内の支払", "支払済みにする", "取引先を登録"):
            self.assertIn(label, segment)

    def test_finance_vendor_routes_validate_upsert_and_stop_per_tenant(self):
        save = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_vendor_save")
        save_source = ast.get_source_segment(SOURCE, save)
        for marker in ('re.fullmatch(r"T\\d{13}"', "FinanceVendor.tenant_id == tenant.id", "FinanceVendor.name == clean_name", "vendor.active = True", "session.commit()"):
            self.assertIn(marker, save_source)
        stop = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_vendor_stop")
        stop_source = ast.get_source_segment(SOURCE, stop)
        for marker in ("FinanceVendor.tenant_id == tenant.id", "FinanceVendor.active.is_(True)", "vendor.active = False"):
            self.assertIn(marker, stop_source)

    def test_finance_payable_create_validates_vendor_dates_and_amount(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_payable_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinanceVendor.tenant_id == tenant.id", "FinanceVendor.active.is_(True)", "received_day > date.today()", "due_day < received_day", "timedelta(days=730)", "category not in FINANCE_CATEGORIES", "amount <= 0", "amount > 999999999", "FinancePayable(", 'status="unpaid"', "created_by_id=user.id"):
            self.assertIn(marker, segment)

    def test_finance_payable_payment_is_confirmed_locked_and_posted_once(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_payable_pay")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancePayable.tenant_id == tenant.id", "FinanceAccount.tenant_id == tenant.id", "not confirmed", 'payable.status != "unpaid"', "payable.financial_entry_id", "ensure_finance_period_open", "FinancialEntry(", 'entry_type="expense"', "FinanceAccountEntry(", 'payable.status = "paid"', "payable.financial_entry_id = entry.id"):
            self.assertIn(marker, segment)

    def test_finance_payable_cancel_is_confirmed_and_non_destructive(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_payable_cancel")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinancePayable.tenant_id == tenant.id", "not confirmed", 'payable.status != "unpaid"', "payable.financial_entry_id", 'payable.status = "cancelled"', "session.commit()"):
            self.assertIn(marker, segment)
        self.assertNotIn("session.delete", segment)

    def test_unpaid_payables_feed_cashflow_closing_navigation_and_guide(self):
        cashflow = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_cashflow_page")
        cashflow_source = ast.get_source_segment(SOURCE, cashflow)
        for marker in ("FinancePayable.tenant_id == tenant.id", 'FinancePayable.status == "unpaid"', "FinancePayable.due_on <= horizon", "FinanceVendor.tenant_id == tenant.id", '"買掛金", -item.id', "plan_id < 0", "買掛金を確認", "期限超過・今後90日間"):
            self.assertIn(marker, cashflow_source)
        closing = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        closing_source = ast.get_source_segment(SOURCE, closing)
        for marker in ("FinancePayable.tenant_id == tenant.id", 'FinancePayable.status == "unpaid"', "due_payable_count", "期限到来未払", "買掛・未払確認"):
            self.assertIn(marker, closing_source)
        self.assertIn('href="/modules/finance/payables', SOURCE)
        self.assertIn('"finance/payables": ("取引先・買掛金・支払管理"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("買掛金", "支払期限", "口座と収支台帳へ一度だけ", "重複登録しない"):
            self.assertIn(marker, guide_source)

    def test_finance_receivable_settlement_model_is_one_to_one_and_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceReceivableSettlement")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ("uq_finance_receivable_invoice", "tenant_id", "invoice_id", "received_on", "account_id", "financial_entry_id", "statement_line_id", "unique=True", "created_by_id", "created_at"):
            self.assertIn(marker, segment)

    def test_finance_receivables_page_summarizes_open_overdue_and_history(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_receivables_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("FinanceAccount.tenant_id == tenant.id", "Invoice.tenant_id == tenant.id", "FinanceReceivableSettlement.tenant_id == tenant.id", 'item.status == "issued"', "not item.ledger_entry_id", "overdue", "due_soon", "received_this_month", 'name="confirmed"', "calendar-mobile-card", "calendar-mobile-only"):
            self.assertIn(marker, segment)
        for label in ("未入金総額", "期限超過", "30日以内の入金期限", "当月入金消込", "最近の入金履歴"):
            self.assertIn(label, segment)

    def test_receivable_helper_posts_once_and_updates_invoice_sale_and_statement(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "settle_invoice_receivable")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("FinancialEntry(", 'entry_type="income"', 'category="sale"', "FinanceAccountEntry(", "FinanceReceivableSettlement(", 'invoice.status = "paid"', "invoice.ledger_entry_id = entry.id", 'statement_line.status = "matched"', "PuppySale.tenant_id == tenant_id", "sale.paid_amount = max", 'sale.status = "paid"'):
            self.assertIn(marker, segment)

    def test_manual_receivable_settlement_is_confirmed_tenant_scoped_and_locked(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_receivable_settle")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("Invoice.tenant_id == tenant.id", "FinanceAccount.tenant_id == tenant.id", "FinanceReceivableSettlement.tenant_id == tenant.id", "not confirmed", 'invoice.status != "issued"', "invoice.ledger_entry_id", "existing", "received_day < invoice.issued_on", "received_day > date.today()", "ensure_finance_period_open", "settle_invoice_receivable", "session.commit()"):
            self.assertIn(marker, segment)

    def test_statement_invoice_settlement_checks_exact_income_and_amount(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statement_settle_invoice")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinanceStatementLine.tenant_id == tenant.id", "Invoice.tenant_id == tenant.id", "FinanceAccount.tenant_id == tenant.id", "FinanceReceivableSettlement.tenant_id == tenant.id", "not confirmed", 'line.entry_type != "income"', 'invoice.status != "issued"', "invoice.ledger_entry_id", "invoice.amount != line.amount", "line.transacted_on < invoice.issued_on", "ensure_finance_period_open", "settle_invoice_receivable", "session.commit()"):
            self.assertIn(marker, segment)

    def test_statements_offer_receivable_candidates_and_link_auto_matches(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statements_page")
        page_source = ast.get_source_segment(SOURCE, page)
        for marker in ("Invoice.tenant_id == tenant.id", 'Invoice.status == "issued"', "Invoice.ledger_entry_id.is_(None)", 'item.entry_type == "income"', "invoice.amount == item.amount", "invoice.issued_on <= item.transacted_on", "settle-invoice", "請求書へ入金消込"):
            self.assertIn(marker, page_source)
        imported = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "finance_statement_import")
        import_source = ast.get_source_segment(SOURCE, imported)
        for marker in ("FinanceReceivableSettlement.tenant_id == tenant.id", "FinanceReceivableSettlement.financial_entry_id == matched_entry.id", "settlement.statement_line_id = statement_line.id"):
            self.assertIn(marker, import_source)

    def test_receivables_are_in_closing_navigation_invoices_and_guide(self):
        closing = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        closing_source = ast.get_source_segment(SOURCE, closing)
        for marker in ("Invoice.tenant_id == tenant.id", 'Invoice.status == "issued"', "Invoice.ledger_entry_id.is_(None)", "due_receivable_count", "期限到来未入金", "売掛・未入金確認"):
            self.assertIn(marker, closing_source)
        invoices = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoices_page")
        invoice_source = ast.get_source_segment(SOURCE, invoices)
        for marker in ('key != "paid"', "/modules/finance/receivables", "売掛・入金消込"):
            self.assertIn(marker, invoice_source)
        self.assertIn('"finance/receivables": ("売掛金・請求書入金消込"', SOURCE)
        self.assertIn('href="/modules/finance/receivables', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("売掛金", "入金消込", "銀行明細", "一度だけ", "請求番号とお客様名"):
            self.assertIn(marker, guide_source)

    def test_finance_entry_correction_model_is_audited_and_tenant_scoped(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceEntryCorrection")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ("uq_finance_correction_original", "tenant_id", "original_entry_id", "reversal_entry_id", "replacement_entry_id", "correction_type", "reason", "corrected_by_id", "corrected_at", "unique=True"):
            self.assertIn(marker, segment)

    def test_finance_correction_source_guard_covers_linked_workflows(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_source_entry_ids")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("FinanceCashPlan", "FinanceRecurringPosting", "FinancePayable", "Invoice", "FinanceReceivableSettlement", "model.tenant_id == tenant_id", "column.is_not(None)"):
            self.assertIn(marker, segment)

    def test_finance_corrections_page_filters_entries_and_has_admin_mobile_ui(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_corrections_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("FinancialEntry.tenant_id == tenant.id", "FinanceEntryCorrection.tenant_id == tenant.id", "corrected_ids", "reversal_ids", "blocked_source_ids", "role_is_admin", 'name="confirmed"', "calendar-desktop-only", "calendar-mobile-card"):
            self.assertIn(marker, segment)
        for label in ("仕訳訂正・取消履歴", "元記録を残し", "反対仕訳", "訂正理由", "管理者のみ"):
            self.assertIn(label, segment)

    def test_finance_correction_create_is_confirmed_scoped_and_period_locked(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_correction_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinancialEntry.tenant_id == tenant.id", "FinanceEntryCorrection.tenant_id == tenant.id", "finance_source_entry_ids", "not confirmed", "existing", "original_entry_id in reversal_ids", 'correction_type not in {"cancel", "replace"}', "correction_day < original.occurred_on", "correction_day > date.today()", "ensure_finance_period_open"):
            self.assertIn(marker, segment)
        for marker in ('replacement_type not in {"income", "expense"}', "replacement_category not in FINANCE_CATEGORIES", "replacement_amount <= 0", "replacement_amount > 999999999", "len(clean_description) > 200", "len(clean_reason) > 500"):
            self.assertIn(marker, segment)

    def test_finance_correction_posts_opposite_and_optional_replacement_without_delete(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_correction_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ('"expense" if original.entry_type == "income" else "income"', "amount=original.amount", "FinanceAccountEntry.tenant_id == tenant.id", "account_id=assignment.account_id", 'if correction_type == "replace"', "FinanceEntryCorrection(", "replacement_entry_id=replacement.id if replacement else None", "corrected_by_id=user.id"):
            self.assertIn(marker, segment)
        self.assertNotIn("session.delete", segment)

    def test_finance_corrections_feed_close_export_navigation_and_guide(self):
        closing = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        closing_source = ast.get_source_segment(SOURCE, closing)
        for marker in ("FinanceEntryCorrection.tenant_id == tenant.id", "correction_count", "当月訂正・取消", "/modules/finance/corrections"):
            self.assertIn(marker, closing_source)
        export = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_download")
        export_source = ast.get_source_segment(SOURCE, export)
        for marker in ("FinanceEntryCorrection.tenant_id == tenant.id", "FinanceEntryCorrection.original_entry_id.in_(entry_ids)", "entry-corrections.csv", '"corrections": len(corrections)'):
            self.assertIn(marker, export_source)
        self.assertIn('"finance/corrections": ("仕訳訂正・取消履歴"', SOURCE)
        self.assertIn('href="/modules/finance/corrections"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("仕訳訂正", "元記録は削除されません", "訂正理由", "実行者", "他機能から作られた記録"):
            self.assertIn(marker, guide_source)

    def test_finance_expense_request_model_keeps_approval_audit_and_ledger_link(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceExpenseRequest")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ("tenant_id", "requested_by_id", "expense_on", "category", "description", "amount", "notes", "status", "reviewed_by_id", "reviewed_at", "review_comment", "account_id", "financial_entry_id", "unique=True", "created_at"):
            self.assertIn(marker, segment)

    def test_finance_expense_requests_page_separates_admin_and_employee_scope(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_requests_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ('role not in {Role.admin, Role.employee}', "FinanceExpenseRequest.tenant_id == tenant.id", "role != Role.admin", "FinanceExpenseRequest.requested_by_id == user.id", "FinanceAccount.tenant_id == tenant.id", 'item.status == "pending" and role == Role.admin', 'name="confirmed"', "calendar-desktop-only", "calendar-mobile-card"):
            self.assertIn(marker, segment)
        for label in ("経費申請・承認管理", "承認待ち", "承認して台帳計上", "却下", "申請を取り消す"):
            self.assertIn(label, segment)

    def test_finance_expense_request_create_validates_business_role_and_fields(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ('not in {Role.admin, Role.employee}', "date.fromisoformat", "expense_day < date(2000, 1, 1)", "expense_day > date.today()", "category not in FINANCE_CATEGORIES", "amount <= 0", "amount > 999999999", "len(clean_description) > 200", "len(notes) > 500", "requested_by_id=user.id", 'status="pending"'):
            self.assertIn(marker, segment)
        self.assertNotIn("FinancialEntry(", segment)

    def test_finance_expense_approval_is_admin_confirmed_locked_and_posted_once(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_approve")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceExpenseRequest.tenant_id == tenant.id", ".with_for_update()", "FinanceAccount.tenant_id == tenant.id", "not confirmed", 'item.status != "pending"', "item.financial_entry_id", "len(review_comment) > 500", "ensure_finance_period_open", "FinancialEntry(", 'entry_type="expense"', "FinanceAccountEntry(", 'item.status = "approved"', "item.reviewed_by_id = user.id", "item.reviewed_at", "item.account_id = account.id", "item.financial_entry_id = entry.id"):
            self.assertIn(marker, segment)

    def test_finance_expense_reject_and_requester_cancel_are_non_destructive(self):
        reject = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_reject")
        reject_source = ast.get_source_segment(SOURCE, reject)
        for marker in ("require_tenant_admin", "FinanceExpenseRequest.tenant_id == tenant.id", "not confirmed", 'item.status != "pending"', "not clean_comment", "len(clean_comment) > 500", 'item.status = "rejected"', "item.reviewed_by_id = user.id", "item.reviewed_at"):
            self.assertIn(marker, reject_source)
        cancel = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_cancel")
        cancel_source = ast.get_source_segment(SOURCE, cancel)
        for marker in ("FinanceExpenseRequest.tenant_id == tenant.id", "FinanceExpenseRequest.requested_by_id == user.id", "not confirmed", 'item.status != "pending"', 'item.status = "cancelled"'):
            self.assertIn(marker, cancel_source)
        self.assertIn(".with_for_update()", reject_source + cancel_source)
        self.assertNotIn("session.delete", reject_source + cancel_source)

    def test_finance_expense_requests_feed_corrections_close_and_export(self):
        source_guard = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_source_entry_ids")
        self.assertIn("FinanceExpenseRequest.financial_entry_id", ast.get_source_segment(SOURCE, source_guard))
        closing = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page")
        closing_source = ast.get_source_segment(SOURCE, closing)
        for marker in ("FinanceExpenseRequest.tenant_id == tenant.id", 'FinanceExpenseRequest.status == "pending"', "pending_expense_request_count", "経費申請の承認待ち", "/modules/finance/expense-requests"):
            self.assertIn(marker, closing_source)
        export = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_download")
        export_source = ast.get_source_segment(SOURCE, export)
        for marker in ("FinanceExpenseRequest.tenant_id == tenant.id", "expense-requests.csv", '"expense_requests": len(expense_requests)', "reviewed_by_id", "reviewed_at"):
            self.assertIn(marker, export_source)

    def test_finance_expense_requests_have_navigation_module_and_guide(self):
        self.assertIn('"finance/expense-requests": ("経費申請・承認管理"', SOURCE)
        self.assertIn('href="/modules/finance/expense-requests"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("経費申請", "従業員", "管理者", "承認者", "申請だけでは台帳へ計上されません", "重複登録"):
            self.assertIn(marker, guide_source)

    def test_finance_expense_document_model_is_tenant_scoped_and_one_per_request(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceExpenseDocument")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ('__tablename__ = "finance_expense_documents"', 'UniqueConstraint("expense_request_id"', "tenant_id", "expense_request_id", "uploaded_by_id", "filename", "content_type", "file_data", "uploaded_at"):
            self.assertIn(marker, segment)

    def test_finance_expense_document_upload_validates_owner_state_type_extension_and_size(self):
        route = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "finance_expense_request_document_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinanceExpenseRequest.tenant_id == tenant.id", "FinanceExpenseRequest.requested_by_id == user.id", ".with_for_update()", 'item.status != "pending"', "FinanceExpenseDocument.tenant_id == tenant.id", "document_file.content_type not in allowed_types", "allowed_extensions", "8 * 1024 * 1024 + 1", "len(content) > 8 * 1024 * 1024", "Path(document_file.filename", "uploaded_by_id=user.id"):
            self.assertIn(marker, segment)

    def test_finance_expense_document_view_is_tenant_and_role_protected(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_document_file")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinanceExpenseRequest.tenant_id == tenant.id", "role not in {Role.admin, Role.employee}", "item.requested_by_id != user.id", "FinanceExpenseDocument.tenant_id == tenant.id", '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)

    def test_finance_expense_approval_requires_and_archives_document(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_approve")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("FinanceExpenseDocument.tenant_id == tenant.id", "FinanceExpenseDocument.expense_request_id == request_id", "not document", "FinanceDocument(", 'document_type="receipt"', "file_data=document.file_data"):
            self.assertIn(marker, segment)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_requests_page")
        page_source = ast.get_source_segment(SOURCE, page)
        for marker in ("defer(FinanceExpenseDocument.file_data)", "documents_by_request", "証憑未登録", "申請者の証憑登録後に承認できます", 'enctype="multipart/form-data"'):
            self.assertIn(marker, page_source)

    def test_finance_export_includes_expense_request_documents_and_checksums(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_download")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("expense_documents", "expense-request-documents/request-", '"expense_request_documents": len(expense_documents)', "document_bytes", "expense_document_files", "checksums"):
            self.assertIn(marker, segment)

    def test_finance_audit_model_records_actor_action_target_and_time(self):
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceAuditEvent")
        segment = ast.get_source_segment(SOURCE, model)
        for marker in ('__tablename__ = "finance_audit_events"', "tenant_id", "actor_user_id", "action", "entity_type", "entity_id", "summary", "details", "created_at", "index=True"):
            self.assertIn(marker, segment)

    def test_finance_audit_helper_is_append_only_and_bounded(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "record_finance_audit")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("FinanceAuditEvent(", "actor_user_id=actor_user_id", "action=action[:40]", "entity_type=entity_type[:40]", "summary=summary[:300]", 'details=(details or "")[:1000]'):
            self.assertIn(marker, segment)
        self.assertNotIn("session.delete", segment)

    def test_finance_audit_page_is_admin_tenant_scoped_filtered_and_mobile(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_audit_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceAuditEvent.tenant_id == tenant.id", "FinanceAuditEvent.created_at >= start_at", "FinanceAuditEvent.created_at < end_at", "FinanceAuditEvent.action == action", ".limit(1000)", "actor_user_id", "calendar-desktop-only", "calendar-mobile-card", "監査ログは画面から変更・削除できません"):
            self.assertIn(marker, segment)

    def test_finance_audit_csv_is_private_bounded_and_formula_safe(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_audit_csv")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceAuditEvent.tenant_id == tenant.id", ".limit(10000)", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)
        safe = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_export_csv")
        self.assertIn('startswith(("=", "+", "-", "@"))', ast.get_source_segment(SOURCE, safe))

    def test_finance_audit_filters_are_validated_and_year_bounded(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_audit_filters")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("action not in FINANCE_AUDIT_ACTIONS", "date.fromisoformat", "start > end", "end > date.today()", "> 366"):
            self.assertIn(marker, segment)

    def test_critical_finance_actions_write_actor_audit_events(self):
        expected = {
            "finance_close_period": "period_close", "finance_reopen_period": "period_reopen",
            "finance_expense_request_create": "expense_submit", "finance_expense_request_document_create": "expense_document",
            "finance_expense_request_approve": "expense_approve", "finance_expense_request_reject": "expense_reject",
            "finance_expense_request_cancel": "expense_cancel", "finance_correction_create": "entry_correction",
            "finance_tax_save": "tax_update", "finance_payable_pay": "payable_payment",
            "finance_receivable_settle": "receivable_settlement", "finance_account_transfer": "account_transfer",
            "finance_statement_import": "statement_import", "finance_export_download": "finance_export",
        }
        functions = {node.name: node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name, action in expected.items():
            segment = ast.get_source_segment(SOURCE, functions[name])
            self.assertIn("record_finance_audit", segment, name)
            self.assertIn(f'"{action}"', segment, name)
            self.assertIn("user.id", segment, name)

    def test_finance_audit_has_module_navigation_and_guide(self):
        self.assertIn('"finance/audit": ("会計操作ログ・監査証跡"', SOURCE)
        self.assertIn('href="/modules/finance/audit"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("会計操作ログ", "監査証跡", "実行者", "CSV", "追記専用"):
            self.assertIn(marker, guide_source)

    def test_finance_book_filters_validate_year_month_type_category_and_account(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_book_filters")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("int(year)", "int(month)", "int(account_id)", "selected_year < 2000", "selected_year > 2100", "selected_month < 0", "selected_month > 12", 'entry_type not in {"", "income", "expense"}', 'category not in {"", *FINANCE_CATEGORIES}', "selected_account_id < 0"):
            self.assertIn(marker, segment)

    def test_finance_book_data_is_tenant_scoped_bounded_and_account_filtered(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_book_data")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("FinanceAccount.tenant_id == tenant_id", "FinanceAccountEntry.tenant_id == tenant_id", "FinancialEntry.tenant_id == tenant_id", "FinancialEntry.occurred_on >= first_day", "FinancialEntry.occurred_on <= last_day", "FinanceAccountTransfer.tenant_id == tenant_id", "FinanceAccountTransfer.from_account_id == account_id", "FinanceAccountTransfer.to_account_id == account_id", ".limit(10000)", "account_by_entry"):
            self.assertIn(marker, segment)

    def test_finance_books_page_is_admin_only_and_has_ledgers_mobile_and_totals(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_books_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "finance_book_filters", "finance_book_data", "income_total", "expense_total", "category_totals", "仕訳帳", "科目別元帳", "口座間振替", "calendar-desktop-only", "calendar-mobile-card", "/modules/finance/books.csv"):
            self.assertIn(marker, segment)

    def test_finance_books_csv_is_private_formula_safe_and_includes_transfers(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_books_csv")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "finance_book_filters", "finance_book_data", "book_rows.extend", '"口座振替"', "book_rows.sort", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)

    def test_finance_books_have_module_navigation_and_guide(self):
        self.assertIn('"finance/books": ("仕訳帳・科目別元帳"', SOURCE)
        self.assertIn('href="/modules/finance/books"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("仕訳帳", "科目別元帳", "口座別", "CSV", "複式簿記", "税理士"):
            self.assertIn(marker, guide_source)

    def test_fiscal_setting_and_year_close_models_are_tenant_scoped(self):
        setting = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceFiscalSetting")
        setting_source = ast.get_source_segment(SOURCE, setting)
        for marker in ('__tablename__ = "finance_fiscal_settings"', 'UniqueConstraint("tenant_id"', "start_month", "updated_by_id", "updated_at"):
            self.assertIn(marker, setting_source)
        close = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceYearClose")
        close_source = ast.get_source_segment(SOURCE, close)
        for marker in ('__tablename__ = "finance_year_closes"', 'UniqueConstraint("tenant_id", "start_year"', "period_start", "period_end", "income_total", "expense_total", "entry_count", "closed_by_id", "closed_at", "notes"):
            self.assertIn(marker, close_source)

    def test_year_close_checklist_model_is_tenant_year_item_unique_and_audited(self):
        model = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceYearCloseChecklist"))
        for marker in ('__tablename__ = "finance_year_close_checklists"', 'UniqueConstraint("tenant_id", "start_year", "item_key"', "completed", "notes", "checked_by_id", "checked_at"):
            self.assertIn(marker, model)
        for marker in ("inventory", "receivables", "payables", "fixed_assets", "tax", "documents", "accountant"):
            self.assertIn(f'"{marker}"', SOURCE)

    def test_year_checklist_complete_requires_exact_standard_keys(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_checklist_complete"))
        for marker in ("FinanceYearCloseChecklist.tenant_id == tenant_id", "FinanceYearCloseChecklist.start_year == start_year", "FinanceYearCloseChecklist.completed.is_(True)", "set(FINANCE_YEAR_CHECKLIST_ITEMS).issubset(completed_keys)"):
            self.assertIn(marker, helper)

    def test_year_checklist_page_is_admin_scoped_bounded_and_links_reports(self):
        page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_checklist_page"))
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "FinanceYearCloseChecklist.tenant_id == tenant.id", ".limit(100)", "FinanceYearClose.tenant_id == tenant.id", "completed_count", "/modules/finance/export", "/modules/finance/tax/report", "年度締め済み"):
            self.assertIn(marker, page)

    def test_year_checklist_update_validates_locks_upserts_and_audits(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_checklist_update"))
        for marker in ("require_tenant_admin", "not confirmed", "item_key not in FINANCE_YEAR_CHECKLIST_ITEMS", "len(notes) > 500", "FinanceYearClose.tenant_id == tenant.id", "FinanceYearCloseChecklist.tenant_id == tenant.id", ".with_for_update()", "item.completed = completed", "FinanceYearCloseChecklist(", '"year_checklist_update"'):
            self.assertIn(marker, route)

    def test_fiscal_period_supports_non_calendar_business_years(self):
        period = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fiscal_period")
        self.assertIn("date(start_year + 1, start_month, 1)", ast.get_source_segment(SOURCE, period))
        months = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fiscal_months")
        segment = ast.get_source_segment(SOURCE, months)
        for marker in ("range(12)", "month_index // 12", "month_index % 12 + 1"):
            self.assertIn(marker, segment)

    def test_year_end_page_is_admin_scoped_and_checks_twelve_months_and_open_items(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_end_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "FinancePeriodClose.tenant_id == tenant.id", "FinanceExpenseRequest.tenant_id == tenant.id", 'FinanceExpenseRequest.status == "pending"', "FinanceStatementLine.tenant_id == tenant.id", 'FinanceStatementLine.status == "unmatched"', "FinanceAccountEntry.tenant_id == tenant.id", "FinanceJournalEntry.tenant_id == tenant.id", "FinanceYearCloseChecklist.tenant_id == tenant.id", "checklist_completed_count", "unjournaled_count", "monthly_closed_count == 12", "unassigned_count == 0", "unjournaled_count == 0", "12か月の締め状況"):
            self.assertIn(marker, segment)

    def test_fiscal_setting_is_validated_locked_after_year_close_and_audited(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fiscal_setting_save")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "start_month < 1", "start_month > 12", ".with_for_update()", "FinanceYearClose.tenant_id == tenant.id", "item.start_month != start_month", "record_finance_audit", '"fiscal_setting"'):
            self.assertIn(marker, segment)

    def test_year_close_requires_all_months_and_no_open_items_then_snapshots(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_close")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "not confirmed", "finance_fiscal_period", "finance_fiscal_months", "FinancePeriodClose.tenant_id == tenant.id", "any(month not in monthly_closed", "pending", "unmatched", "entry_ids - assigned_ids", "FinanceJournalEntry.source_entry_id.in_(entry_ids)", "entry_ids - journaled_ids", "finance_year_checklist_complete", "FinanceYearClose(", "income_total=sum", "expense_total=sum", "record_finance_audit", '"year_close"'):
            self.assertIn(marker, segment)

    def test_year_reopen_is_confirmed_locked_and_audited_without_reopening_months(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_reopen")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", ".with_for_update()", "not confirmed", "record_finance_audit", '"year_reopen"', "session.delete(close_item)"):
            self.assertIn(marker, segment)
        self.assertNotIn("session.delete(month", segment)

    def test_year_close_blocks_postings_and_month_reopen_until_released(self):
        guard = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "ensure_finance_period_open")
        guard_source = ast.get_source_segment(SOURCE, guard)
        for marker in ("FinanceYearClose.tenant_id == tenant_id", "FinanceYearClose.period_start <= target_day", "FinanceYearClose.period_end >= target_day", "年度締め済み"):
            self.assertIn(marker, guard_source)
        reopen = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_reopen_period")
        self.assertIn("先に年度締めを解除してください", ast.get_source_segment(SOURCE, reopen))

    def test_year_end_has_module_navigation_guide_and_audit_actions(self):
        self.assertIn('"finance/year-end": ("会計年度設定・年度締め"', SOURCE)
        self.assertIn('href="/modules/finance/year-end"', SOURCE)
        self.assertIn('"fiscal_setting": "会計年度設定"', SOURCE)
        self.assertIn('"year_close": "年度締め"', SOURCE)
        self.assertIn('"year_reopen": "年度締め解除"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("会計年度", "事業年度", "12か月", "月次締め", "年度締めを解除"):
            self.assertIn(marker, guide_source)

    def test_year_checklist_has_module_navigation_guide_and_audit_action(self):
        self.assertIn('"finance/year-end-checklist": ("決算前チェックリスト"', SOURCE)
        self.assertIn('href="/modules/finance/year-end-checklist"', SOURCE)
        self.assertIn('"year_checklist_update": "決算前チェック更新"', SOURCE)
        guide = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide"))
        for marker in ("決算前チェックリスト", "棚卸", "売掛", "買掛", "固定資産", "消費税", "証憑", "税理士"):
            self.assertIn(marker, guide)

    def test_trial_balance_period_uses_fiscal_year_and_validates_month(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_trial_balance_period")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("finance_fiscal_period", "date.fromisoformat", "period_end", "fiscal_end", "selected_month < period_start", "period_end > fiscal_end", "試算表の表示期間"):
            self.assertIn(marker, segment)

    def test_trial_balance_data_is_tenant_scoped_and_calculates_account_balances(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_trial_balance_data")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("finance_double_entry_data", "journal_by_id", "line.journal_entry_id", 'voucher_no.startswith("OB-")', 'voucher_no.startswith("CF-")', 'line.side == "debit"', "opening_debit", "period_debit", "max(0, signed)", "type_totals"):
            self.assertIn(marker, segment)

    def test_trial_balance_page_is_admin_only_mobile_and_has_management_warning(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_trial_balance_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "finance_trial_balance_period", "finance_trial_balance_data", "debit_total", "credit_total", "ending_debit_total", "ending_credit_total", "当期借方合計", "当期貸方合計", "当期貸借差額", "期末貸借差額", "勘定科目別残高試算表", "科目区分別当期増減", "calendar-desktop-only", "calendar-mobile-card", "/modules/finance/general-ledger", "/modules/finance/statements-report", "/modules/finance/trial-balance.csv"):
            self.assertIn(marker, segment)

    def test_trial_balance_csv_is_private_and_formula_safe(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_trial_balance_csv")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "finance_trial_balance_period", "finance_trial_balance_data", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)

    def test_trial_balance_has_module_navigation_and_guide(self):
        self.assertIn('"finance/trial-balance": ("月次・年度複式試算表"', SOURCE)
        self.assertIn('href="/modules/finance/trial-balance"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("月次・年度複式試算表", "期首残高", "当期増減", "期末残高", "借方", "貸方", "CSV", "税理士"):
            self.assertIn(marker, guide_source)

    def test_statement_report_data_is_tenant_scoped_bounded_and_complete(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statement_report_data")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("finance_double_entry_data", "signed_balances", 'line.amount if line.side == "debit" else -line.amount', "statement_balances", 'account.account_type in {"asset", "expense"}', "accounts, subaccounts, journals, lines"):
            self.assertIn(marker, segment)

    def test_statement_report_page_is_admin_only_fiscal_mobile_and_warns_estimate(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statements_report_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "finance_trial_balance_period", "finance_statement_report_data", "income_total", "expense_total", "equity_total", "equation_difference", "損益計算書", "貸借対照表", "当期利益", "資産合計", "負債・純資産・当期利益合計", "貸借差額", "calendar-desktop-only", "calendar-mobile-card", "正式な決算書・税務申告", "/modules/finance/statements-report.csv", "/modules/finance/general-ledger"):
            self.assertIn(marker, segment)

    def test_statement_report_csv_is_private_formula_safe_and_has_both_reports(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statements_report_csv")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "finance_trial_balance_period", "finance_statement_report_data", '"損益計算書"', '"貸借対照表"', 'item.account_type == "equity"', "equity_total", '"貸借差額"', "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)

    def test_statement_reports_have_module_navigation_and_guide(self):
        self.assertIn('"finance/statements-report": ("損益計算書・貸借対照表"', SOURCE)
        self.assertIn('href="/modules/finance/statements-report"', SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("損益計算書", "貸借対照表", "収益", "費用", "資産", "負債", "純資産", "複式仕訳"):
            self.assertIn(marker, guide_source)

    def test_chart_account_models_are_tenant_scoped_unique_and_audited(self):
        account = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceChartAccount")
        account_source = ast.get_source_segment(SOURCE, account)
        for marker in ('__tablename__ = "finance_chart_accounts"', 'UniqueConstraint("tenant_id", "code"', "account_type", "normal_side", "system_key", "active", "created_by_id"):
            self.assertIn(marker, account_source)
        sub = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceSubaccount")
        sub_source = ast.get_source_segment(SOURCE, sub)
        for marker in ('__tablename__ = "finance_subaccounts"', 'UniqueConstraint("account_id", "code"', "tenant_id", "account_id", "active", "created_by_id"):
            self.assertIn(marker, sub_source)
        mapping = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceCategoryAccountMap")
        mapping_source = ast.get_source_segment(SOURCE, mapping)
        for marker in ('__tablename__ = "finance_category_account_maps"', 'UniqueConstraint("tenant_id", "entry_type", "category"', "account_id", "updated_by_id", "updated_at"):
            self.assertIn(marker, mapping_source)

    def test_chart_accounts_page_is_admin_scoped_bounded_mobile_and_maps_categories(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_chart_accounts_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceChartAccount.tenant_id == tenant.id", "FinanceSubaccount.tenant_id == tenant.id", "FinanceCategoryAccountMap.tenant_id == tenant.id", ".limit(1000)", ".limit(2000)", "calendar-desktop-only", "calendar-mobile-card", "既存費目との対応", "標準科目を一括作成"):
            self.assertIn(marker, segment)

    def test_standard_chart_initialization_is_confirmed_idempotent_and_maps_legacy_categories(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_chart_accounts_initialize")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "not confirmed", "FinanceChartAccount.tenant_id == tenant.id", '"cash"', '"receivable"', '"fixed_asset"', '"accumulated_depreciation"', '"depreciation_expense"', '"payable"', '"equity"', '"sales"', "for category in FINANCE_CATEGORIES", "FinanceCategoryAccountMap(", 'entry_type="income"', 'entry_type="expense"', '"chart_initialize"'):
            self.assertIn(marker, segment)

    def test_chart_account_create_validates_code_type_normal_side_and_duplicate(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_chart_account_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", 're.fullmatch(r"[A-Z0-9-]{1,20}"', "FinanceChartAccount.tenant_id == tenant.id", "account_type not in FINANCE_ACCOUNT_TYPES", "normal_side not in FINANCE_NORMAL_SIDES", "normal_side != expected_side", "duplicate", '"chart_account_create"'):
            self.assertIn(marker, segment)

    def test_subaccount_create_and_stop_are_confirmed_and_tenant_scoped(self):
        create = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_subaccount_create"))
        stop = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_subaccount_stop"))
        for marker in ("require_tenant_admin", "FinanceChartAccount.tenant_id == tenant.id", "FinanceSubaccount.tenant_id == tenant.id", "duplicate", '"subaccount_create"'):
            self.assertIn(marker, create)
        for marker in ("require_tenant_admin", "FinanceSubaccount.tenant_id == tenant.id", ".with_for_update()", "not confirmed", 'item.active = False', '"subaccount_stop"'):
            self.assertIn(marker, stop)

    def test_category_map_upserts_only_matching_revenue_or_expense_accounts(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_category_account_map")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceChartAccount.tenant_id == tenant.id", 'expected_type = "revenue" if entry_type == "income" else "expense"', "category not in FINANCE_CATEGORIES", "account.account_type != expected_type", "FinanceCategoryAccountMap.tenant_id == tenant.id", ".with_for_update()", '"category_account_map"'):
            self.assertIn(marker, segment)

    def test_chart_account_stop_preserves_system_mapped_and_active_subaccounts(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_chart_account_stop")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceChartAccount.tenant_id == tenant.id", ".with_for_update()", "FinanceCategoryAccountMap.tenant_id == tenant.id", "FinanceSubaccount.tenant_id == tenant.id", "item.system_key", "mapped", "active_sub", 'item.active = False', '"chart_account_stop"'):
            self.assertIn(marker, segment)

    def test_chart_accounts_have_navigation_guide_and_audit_actions(self):
        self.assertIn('"finance/chart-accounts": ("勘定科目・補助科目管理"', SOURCE)
        self.assertIn('href="/modules/finance/chart-accounts"', SOURCE)
        for marker in ('"chart_initialize": "標準勘定科目作成"', '"chart_account_create": "勘定科目登録"', '"chart_account_stop": "勘定科目停止"', '"subaccount_create": "補助科目登録"', '"subaccount_stop": "補助科目停止"', '"category_account_map": "費目対応設定"'):
            self.assertIn(marker, SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("勘定科目", "補助科目", "科目マスター", "借方", "貸方", "標準科目", "税理士"):
            self.assertIn(marker, guide_source)

    def test_journal_models_are_tenant_scoped_voucher_source_and_line_unique(self):
        entry = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceJournalEntry")
        entry_source = ast.get_source_segment(SOURCE, entry)
        for marker in ('__tablename__ = "finance_journal_entries"', 'UniqueConstraint("tenant_id", "voucher_no"', 'UniqueConstraint("source_entry_id"', "entry_date", "reversal_of_id", "status", "created_by_id"):
            self.assertIn(marker, entry_source)
        line = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceJournalLine")
        line_source = ast.get_source_segment(SOURCE, line)
        for marker in ('__tablename__ = "finance_journal_lines"', 'UniqueConstraint("journal_entry_id", "line_no"', "tenant_id", "side", "account_id", "subaccount_id", "amount"):
            self.assertIn(marker, line_source)

    def test_journal_helper_requires_balance_and_valid_tenant_accounts_and_subaccounts(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create_journal")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("debit_total", "credit_total", "debit_total != credit_total", "len(lines) > max_lines", 'side not in {"debit", "credit"}', "FinanceChartAccount.tenant_id == tenant_id", "FinanceSubaccount.tenant_id == tenant_id", "subaccounts[sub_id].account_id != account_id", "FinanceJournalEntry(", "FinanceJournalLine(", "enumerate(lines, 1)"):
            self.assertIn(marker, segment)

    def test_journal_page_is_admin_scoped_bounded_mobile_and_shows_unlinked(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_journals_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceJournalEntry.tenant_id == tenant.id", "FinanceJournalLine.tenant_id == tenant.id", "FinanceChartAccount.tenant_id == tenant.id", "FinanceSubaccount.tenant_id == tenant.id", ".limit(1000)", ".limit(20000)", "unlinked_count", "calendar-desktop-only", "calendar-mobile-card", "取消仕訳", "/modules/finance/journals.csv"):
            self.assertIn(marker, segment)

    def test_manual_journal_is_confirmed_validated_period_locked_and_audited(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_journal_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "not confirmed", "entry_day > date.today()", "amount > 999999999", "ensure_finance_period_open", "finance_journal_voucher", "finance_create_journal", '"debit"', '"credit"', '"journal_create"'):
            self.assertIn(marker, segment)

    def test_legacy_sync_is_confirmed_idempotent_mapped_bounded_and_locked(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_journals_sync")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "not confirmed", 'FinanceChartAccount.system_key == "cash"', "FinanceCategoryAccountMap.tenant_id == tenant.id", "FinanceJournalEntry.source_entry_id", "FinancialEntry.tenant_id == tenant.id", ".limit(100)", "mapping_by_key", "finance_non_cash_entry_ids", "item.id not in non_cash_ids", "ensure_finance_period_open", 'f"LG-{item.id}"', "source_entry_id=item.id", '"journal_sync"'):
            self.assertIn(marker, segment)

    def test_journal_reversal_swaps_sides_is_idempotent_locked_and_audited(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_journal_reverse")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceJournalEntry.tenant_id == tenant.id", ".with_for_update()", "reversal_of_id == journal_id", 'original.status != "posted"', "original.reversal_of_id is not None", "existing", "ensure_finance_period_open", '"credit" if item.side == "debit" else "debit"', "reversal_of_id=original.id", 'original.status = "reversed"', '"journal_reverse"'):
            self.assertIn(marker, segment)

    def test_journal_csv_is_private_bounded_and_formula_safe(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_journals_csv")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "first_day < date(2000, 1, 1)", "first_day > date(2100, 12, 1)", "FinanceJournalEntry.tenant_id == tenant.id", "FinanceJournalLine.tenant_id == tenant.id", ".limit(1000)", ".limit(20000)", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)

    def test_journal_usage_blocks_account_stop_and_business_source_correction(self):
        stop = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_chart_account_stop"))
        source = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_source_entry_ids"))
        self.assertIn("FinanceJournalLine.tenant_id == tenant.id", stop)
        self.assertIn("journal_line", stop)
        self.assertIn("FinancePayable", source)
        self.assertIn("FinanceExpenseRequest", source)
        self.assertNotIn("FinanceJournalEntry", source)

    def test_journals_have_navigation_guide_and_audit_actions(self):
        self.assertIn('"finance/journals": ("複式簿記仕訳"', SOURCE)
        self.assertIn('href="/modules/finance/journals"', SOURCE)
        for marker in ('"journal_create": "複式仕訳登録"', '"journal_sync": "収支複式仕訳連携"', '"journal_reverse": "複式仕訳取消"'):
            self.assertIn(marker, SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("複式簿記", "仕訳伝票", "借方", "貸方", "貸借不一致", "取消仕訳", "締め済み期間"):
            self.assertIn(marker, guide_source)

    def test_opening_and_carryforward_models_are_tenant_scoped_and_unique(self):
        opening = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceOpeningBalance"))
        for marker in ('__tablename__ = "finance_opening_balances"', 'UniqueConstraint("tenant_id", "start_year", "account_id", "subaccount_id"', "balance", "journal_entry_id", "created_by_id"):
            self.assertIn(marker, opening)
        carry = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceYearCarryforward"))
        for marker in ('__tablename__ = "finance_year_carryforwards"', 'UniqueConstraint("tenant_id", "source_start_year"', 'UniqueConstraint("tenant_id", "target_start_year"', "source_year_close_id", "journal_entry_id", "debit_total", "credit_total"):
            self.assertIn(marker, carry)

    def test_journal_balance_helper_is_tenant_period_scoped_signed_and_bounded(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_journal_balances"))
        for marker in ("FinanceJournalEntry.tenant_id == tenant_id", "FinanceJournalEntry.entry_date >= period_start", "FinanceJournalEntry.entry_date <= period_end", "FinanceJournalLine.tenant_id == tenant_id", ".limit(20000)", 'line.amount if line.side == "debit" else -line.amount'):
            self.assertIn(marker, helper)

    def test_opening_page_is_admin_scoped_bounded_and_exports_csv(self):
        page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_opening_balances_page"))
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "FinanceChartAccount.tenant_id == tenant.id", "FinanceSubaccount.tenant_id == tenant.id", "FinanceOpeningBalance.tenant_id == tenant.id", "FinanceYearCarryforward.tenant_id == tenant.id", ".limit(1000)", ".limit(2000)", ".limit(100)", "/modules/finance/opening-balances.csv"):
            self.assertIn(marker, page)

    def test_manual_opening_is_balanced_validated_locked_unique_and_audited(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_opening_balance_create"))
        for marker in ("require_tenant_admin", "not confirmed", "ensure_finance_period_open", "FinanceYearCarryforward.target_start_year == start_year", "FinanceChartAccount.tenant_id == tenant.id", 'account.account_type not in {"asset", "liability"}', 'FinanceChartAccount.system_key == "equity"', "FinanceSubaccount.tenant_id == tenant.id", "duplicate", "finance_create_journal", "opposite", "FinanceOpeningBalance(", '"opening_balance_create"'):
            self.assertIn(marker, route)

    def test_carryforward_requires_close_no_existing_opening_and_balances_equity(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_carryforward"))
        for marker in ("require_tenant_admin", "not confirmed", "FinanceYearClose.tenant_id == tenant.id", ".with_for_update()", "FinanceYearCarryforward.target_start_year == target_year", "FinanceOpeningBalance.start_year == target_year", "ensure_finance_period_open", "FinancialEntry.tenant_id == tenant.id", "source_entry_ids - journaled_source_ids", "finance_journal_balances", 'account_type in {"asset", "liability", "equity"}', "active_subaccount_ids != subaccount_ids", "- sum(carried.values())", "max_lines=500", "debit_total", "credit_total", "FinanceYearCarryforward(", '"year_carryforward"'):
            self.assertIn(marker, route)

    def test_year_reopen_is_blocked_after_carryforward(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_reopen"))
        for marker in ("FinanceYearCarryforward.tenant_id == tenant.id", "FinanceYearCarryforward.source_start_year == start_year", "carryforward"):
            self.assertIn(marker, route)

    def test_opening_csv_is_private_bounded_and_formula_safe(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_opening_balances_csv"))
        for marker in ("require_tenant_admin", "start_year < 2000", "start_year > 2099", "FinanceOpeningBalance.tenant_id == tenant.id", ".limit(2000)", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, route)

    def test_opening_balances_have_navigation_guide_and_audit_actions(self):
        self.assertIn('"finance/opening-balances": ("期首残高・年度繰越"', SOURCE)
        self.assertIn('href="/modules/finance/opening-balances"', SOURCE)
        self.assertIn('"opening_balance_create": "期首残高登録"', SOURCE)
        self.assertIn('"year_carryforward": "年度残高繰越"', SOURCE)
        guide = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide"))
        for marker in ("期首残高", "年度繰越", "資産", "負債", "純資産", "当期損益", "税理士"):
            self.assertIn(marker, guide)

    def test_double_entry_data_is_tenant_period_scoped_ordered_and_bounded(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_double_entry_data"))
        for marker in ("FinanceChartAccount.tenant_id == tenant_id", ".limit(1000)", "FinanceSubaccount.tenant_id == tenant_id", ".limit(2000)", "FinanceJournalEntry.tenant_id == tenant_id", "FinanceJournalEntry.entry_date >= period_start", "FinanceJournalEntry.entry_date <= period_end", ".limit(10000)", "FinanceJournalLine.tenant_id == tenant_id", ".limit(50000)", "journal_order", "lines.sort", "item.line_no"):
            self.assertIn(marker, helper)

    def test_general_ledger_page_is_admin_fiscal_scoped_and_balances_debits_credits(self):
        page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_general_ledger_page"))
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "finance_fiscal_period", "finance_double_entry_data", "selected_account_id not in account_by_id", "debit_grand", "credit_grand", "line.side == \"debit\"", "running", "counterparts", "貸借差額", "複式残高試算表", "総勘定元帳", "/modules/finance/general-ledger.csv"):
            self.assertIn(marker, page)

    def test_general_ledger_csv_is_admin_scoped_private_formula_safe_and_filterable(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_general_ledger_csv"))
        for marker in ("require_tenant_admin", "FinanceFiscalSetting.tenant_id == tenant.id", "finance_fiscal_period", "finance_double_entry_data", "account_id not in account_by_id", "line.account_id != account_id", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, route)

    def test_general_ledger_has_module_navigation_and_guide(self):
        self.assertIn('"finance/general-ledger": ("総勘定元帳・複式試算表"', SOURCE)
        self.assertIn('href="/modules/finance/general-ledger"', SOURCE)
        guide = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide"))
        for marker in ("総勘定元帳", "複式試算表", "借方合計", "貸方合計", "貸借一致", "期首残高", "年度繰越", "取消仕訳", "税理士"):
            self.assertIn(marker, guide)

    def test_fixed_asset_models_are_tenant_scoped_and_depreciation_is_unique(self):
        asset = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceFixedAsset")
        asset_source = ast.get_source_segment(SOURCE, asset)
        for marker in ('__tablename__ = "finance_fixed_assets"', "tenant_id", "acquired_on", "acquisition_cost", "useful_life_years", "business_use_percent", "disposed_on", "created_by_id"):
            self.assertIn(marker, asset_source)
        posting = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "FinanceDepreciationPosting")
        posting_source = ast.get_source_segment(SOURCE, posting)
        for marker in ('__tablename__ = "finance_depreciation_postings"', 'UniqueConstraint("asset_id", "start_year"', "tenant_id", "amount", "financial_entry_id", "posted_by_id"):
            self.assertIn(marker, posting_source)

    def test_depreciation_calculation_caps_remaining_and_prorates_months(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_depreciation_amount")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("business_use_percent", "remaining", "asset.useful_life_years", "calculation_start", "calculation_end", "months", "annual * max(0, months) // 12", "min(remaining"):
            self.assertIn(marker, segment)

    def test_depreciation_journal_accounts_ensure_expense_and_contra_asset(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_depreciation_journal_accounts")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ('system_key == "depreciation_expense"', 'system_key == "accumulated_depreciation"', "available_code", 'name="減価償却費"', 'account_type="expense"', 'normal_side="debit"', 'name="減価償却累計額"', 'account_type="asset"', 'normal_side="credit"'):
            self.assertIn(marker, segment)

    def test_accrual_helpers_create_balanced_receivable_and_payable_journals(self):
        invoice = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create_invoice_accrual_journal"))
        for marker in ('"receivable"', '"income", "sale"', 'f"AR-{invoice.id}"', '("debit", receivable.id', '("credit", sales.id'):
            self.assertIn(marker, invoice)
        payable = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create_payable_accrual_journal"))
        for marker in ('"expense", payable.category', '"payable"', 'f"AP-{payable.id}"', '("debit", expense.id', '("credit", payable_account.id'):
            self.assertIn(marker, payable)

    def test_accrual_settlement_clears_balance_sheet_accounts(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create_accrual_settlement_journal"))
        for marker in ('"cash"', 'account_key == "receivable"', '("debit", cash.id', '("credit", accrual.id', '("debit", accrual.id', '("credit", cash.id', 'source_entry_id=entry.id'):
            self.assertIn(marker, helper)

    def test_invoice_issue_and_payable_creation_post_accrual_journals(self):
        invoice_status = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoice_status_update"))
        for marker in ("with_for_update", 'invoice.status == "draft"', 'status_value == "issued"', "ensure_finance_period_open", "finance_create_invoice_accrual_journal", '"receivable_accrual"'):
            self.assertIn(marker, invoice_status)
        payable_create = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_payable_create"))
        for marker in ("ensure_finance_period_open", "session.flush()", "finance_create_payable_accrual_journal", '"payable_accrual"'):
            self.assertIn(marker, payable_create)

    def test_receivable_and_payable_settlement_create_clearing_journals(self):
        receivable = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "settle_invoice_receivable"))
        self.assertIn('finance_create_accrual_settlement_journal(session, tenant_id, user_id, entry, invoice.amount, "receivable"', receivable)
        payable = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_payable_pay"))
        self.assertIn('finance_create_accrual_settlement_journal(session, tenant.id, user.id, entry, payable.amount, "payable"', payable)

    def test_cash_basis_helper_is_balanced_linked_and_idempotent(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create_cash_basis_journal"))
        for marker in ("FinanceJournalEntry.tenant_id == tenant_id", "FinanceJournalEntry.source_entry_id == entry.id", 'finance_system_account(session, tenant_id, "cash")', "finance_category_account", 'entry.entry_type == "income"', '("debit", cash.id', '("credit", mapped.id', '("debit", mapped.id', '("credit", cash.id', "source_entry_id=entry.id"):
            self.assertIn(marker, helper)

    def test_expense_approval_posts_double_entry_and_keeps_document_link(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_expense_request_approve"))
        for marker in ("with_for_update", "FinanceAccountEntry(", "FinanceDocument(", "finance_create_cash_basis_journal", 'f"経費申請#{item.id}"', '"EX"', "journal={journal.id}"):
            self.assertIn(marker, route)

    def test_recurring_generation_posts_or_defers_double_entry_safely(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "generate_due_finance_recurring"))
        for marker in ("Membership.tenant_id == rule.tenant_id", "Membership.role == Role.admin", ".limit(1)", "finance_create_cash_basis_journal", 'f"定期収支ルール#{rule.id}"', '"RC"', "except HTTPException as exc", "exc.status_code != 409", '"recurring_journal"'):
            self.assertIn(marker, helper)

    def test_recurring_page_shows_double_entry_status_and_recovery_path(self):
        page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_recurring_page"))
        for marker in ("FinanceJournalEntry.tenant_id == tenant.id", "posting_entry_ids", "journaled_entry_ids", "複式仕訳済み", "仕訳未連携", "複式簿記仕訳画面から補完"):
            self.assertIn(marker, page)

    def test_cashflow_completion_posts_balanced_journal_once_and_audits(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_cashflow_complete"))
        for marker in ("with_for_update", "ensure_finance_period_open", "FinancialEntry(", "session.flush()", "finance_create_cash_basis_journal", 'f"資金繰り予定#{plan.id}"', '"CFP"', '"cashflow_journal"', "journal={journal.id}"):
            self.assertIn(marker, route)

    def test_statement_suggestion_batch_posts_double_entry_and_audits(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statement_apply_suggestions"))
        for marker in ("user, tenant = access", "FinanceStatementLine.tenant_id == tenant.id", ".limit(500)", "finance_period_close", "FinanceAccountEntry(", "finance_create_cash_basis_journal", '"BST"', '"statement_journal_batch"'):
            self.assertIn(marker, route)

    def test_statement_manual_post_is_locked_journaled_and_audited(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_statement_line_post"))
        for marker in ("user, tenant = access", "with_for_update", "ensure_finance_period_open", "FinanceAccountEntry(", "finance_create_cash_basis_journal", 'f"銀行明細#{line.import_id}/{line.row_no}"', '"statement_journal"', "journal={journal.id}"):
            self.assertIn(marker, route)

    def test_direct_ledger_entry_posts_double_entry_and_audits(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create"))
        for marker in ("ensure_finance_period_open", "FinancialEntry(", "session.flush()", "finance_create_cash_basis_journal", '"収支台帳直接入力"', '"LG"', '"ledger_journal"', "journal={journal.id}"):
            self.assertIn(marker, route)

    def test_correction_reverses_original_journal_and_posts_replacement(self):
        route = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_correction_create"))
        for marker in ("with_for_update", "finance_create_cash_basis_journal", "original_journal", "finance_reverse_accrual_journal", "source_entry_id=reversal.id", "reversal_journal", "replacement_journal", '"CR"', "original_journal={original_journal.id}"):
            self.assertIn(marker, route)

    def test_direct_journal_link_does_not_block_supported_correction(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_source_entry_ids"))
        self.assertNotIn("FinanceJournalEntry", helper)
        for marker in ("FinanceCashPlan", "FinanceRecurringPosting", "FinancePayable", "FinanceExpenseRequest", "Invoice", "FinanceReceivableSettlement", "FinanceDepreciationPosting"):
            self.assertIn(marker, helper)

    def test_reversal_helper_can_link_correction_ledger_entry(self):
        helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_reverse_accrual_journal"))
        for marker in ("source_entry_id: int | None = None", "source_entry_id=source_entry_id", "reversal_of_id=original.id", 'original.status = "reversed"'):
            self.assertIn(marker, helper)

    def test_depreciation_journal_is_balanced_linked_and_idempotent(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_create_depreciation_journal")
        segment = ast.get_source_segment(SOURCE, helper)
        for marker in ("FinanceJournalEntry.tenant_id == tenant_id", "FinanceJournalEntry.source_entry_id == entry.id", "finance_depreciation_journal_accounts", 'f"DP-{entry.id}"', '("debit", expense.id', '("credit", accumulated.id', "source_entry_id=entry.id"):
            self.assertIn(marker, segment)

    def test_fixed_asset_page_is_admin_tenant_scoped_mobile_and_warns_tax_review(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fixed_assets_page")
        segment = ast.get_source_segment(SOURCE, page)
        for marker in ("require_tenant_admin", "FinanceFixedAsset.tenant_id == tenant.id", "FinanceDepreciationPosting.tenant_id == tenant.id", "FinanceJournalEntry.source_entry_id", ".limit(1000)", "finance_depreciation_amount", "unjournaled_count", "複式仕訳済み", "仕訳未連携", "/modules/finance/fixed-assets/sync-journals", "calendar-desktop-only", "calendar-mobile-card", "税理士", "終了前の事業年度は経費計上できません"):
            self.assertIn(marker, segment)

    def test_fixed_asset_create_validates_fields_and_writes_audit(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fixed_asset_create")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "asset_type not in FINANCE_ASSET_TYPES", "acquired_day > date.today()", "acquisition_cost > 999999999", "useful_life_years > 50", "business_use_percent > 100", "FinanceFixedAsset(", "record_finance_audit", '"fixed_asset_create"'):
            self.assertIn(marker, segment)

    def test_fixed_asset_csv_is_admin_scoped_bounded_and_private(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fixed_assets_csv")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceFixedAsset.tenant_id == tenant.id", "FinanceDepreciationPosting.tenant_id == tenant.id", ".limit(1000)", "finance_depreciation_amount", "finance_export_csv", 'media_type="text/csv; charset=utf-8"', '"Cache-Control": "private, no-store"', '"X-Content-Type-Options": "nosniff"'):
            self.assertIn(marker, segment)

    def test_depreciation_post_is_locked_idempotent_and_links_ledger(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fixed_asset_depreciate")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceFixedAsset.tenant_id == tenant.id", ".with_for_update()", "FinanceDepreciationPosting.tenant_id == tenant.id", "existing", "period_end > date.today()", "ensure_finance_period_open", "FinancialEntry(", 'entry_type="expense"', 'category="facility"', "FinanceDepreciationPosting(", "financial_entry_id=entry.id", "finance_create_depreciation_journal", '"depreciation_post"'):
            self.assertIn(marker, segment)

    def test_legacy_depreciation_sync_is_admin_scoped_bounded_and_audited(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fixed_asset_sync_journals")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "not confirmed", "FinanceDepreciationPosting.tenant_id == tenant.id", ".limit(100)", "FinanceJournalEntry.source_entry_id", "FinanceFixedAsset.tenant_id == tenant.id", "FinancialEntry.tenant_id == tenant.id", "ensure_finance_period_open", "finance_create_depreciation_journal", '"depreciation_journal_sync"'):
            self.assertIn(marker, segment)

    def test_depreciation_is_non_cash_and_exempt_from_account_close_checks(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_non_cash_entry_ids")
        helper_source = ast.get_source_segment(SOURCE, helper)
        for marker in ("FinanceDepreciationPosting.financial_entry_id", "FinanceDepreciationPosting.tenant_id == tenant_id", ".in_(entry_ids)"):
            self.assertIn(marker, helper_source)
        year_page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_end_page"))
        year_close = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_year_close"))
        month_page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_closing_page"))
        accounts_page = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_accounts_page"))
        for segment in (year_page, year_close, month_page, accounts_page):
            self.assertIn("finance_non_cash_entry_ids", segment)
        self.assertIn("entry_ids - assigned_ids - non_cash_ids", year_close)
        self.assertIn("item.id not in non_cash_ids", accounts_page)
        source_helper = ast.get_source_segment(SOURCE, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_source_entry_ids"))
        self.assertIn("FinanceDepreciationPosting", source_helper)

    def test_fixed_asset_dispose_is_confirmed_scoped_and_audited(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "finance_fixed_asset_dispose")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ("require_tenant_admin", "FinanceFixedAsset.tenant_id == tenant.id", ".with_for_update()", "not confirmed", 'asset.status != "active"', "disposed_day < asset.acquired_on", "disposed_day > date.today()", 'asset.status = "disposed"', '"fixed_asset_dispose"'):
            self.assertIn(marker, segment)

    def test_fixed_assets_have_navigation_guide_and_audit_actions(self):
        self.assertIn('"finance/fixed-assets": ("固定資産台帳・減価償却"', SOURCE)
        self.assertIn('href="/modules/finance/fixed-assets"', SOURCE)
        for marker in ('"fixed_asset_create": "固定資産登録"', '"fixed_asset_dispose": "固定資産除却"', '"depreciation_post": "減価償却計上"', '"depreciation_journal_sync": "減価償却仕訳連携"'):
            self.assertIn(marker, SOURCE)
        guide = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "page_usage_guide")
        guide_source = ast.get_source_segment(SOURCE, guide)
        for marker in ("固定資産", "減価償却", "取得価額", "耐用年数", "減価償却累計額", "複式仕訳", "税理士", "定額法"):
            self.assertIn(marker, guide_source)


if __name__ == "__main__":
    unittest.main()
