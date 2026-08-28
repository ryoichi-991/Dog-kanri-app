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

    def test_paid_invoice_creates_one_ledger_income_entry(self):
        route = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "invoice_status_update")
        segment = ast.get_source_segment(SOURCE, route)
        for marker in ('status_value == "paid"', "not invoice.ledger_entry_id", "FinancialEntry", 'entry_type="income"', 'category="sale"', "invoice.ledger_entry_id = entry.id"):
            self.assertIn(marker, segment)
        self.assertIn('invoice.status == "paid" and status_value != "paid"', segment)

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
        for route_name in ("finance_create", "finance_cashflow_complete", "finance_account_assign", "finance_account_transfer", "invoice_status_update", "cost_allocate"):
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


if __name__ == "__main__":
    unittest.main()
