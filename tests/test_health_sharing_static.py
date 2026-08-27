import ast
import pathlib
import unittest


SOURCE = pathlib.Path(__file__).parents[1] / "server.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)


class HealthSharingStaticTests(unittest.TestCase):
    def test_health_sharing_routes_exist(self):
        for route in (
            '/modules/health/weights',
            '/modules/health/shares/{record_type}/{record_id}',
            '/family/dogs/{dog_id}/health',
        ):
            self.assertIn(f'"{route}"', TEXT)

    def test_health_records_are_shared_by_dog(self):
        self.assertIn("class HealthRecordShare(Base):", TEXT)
        self.assertIn("HealthRecordShare.dog_id == dog.id", TEXT)
        self.assertIn("HealthRecordShare.owner_visible.is_(True)", TEXT)
        self.assertIn("family_owned_dog(dog_id, user, session)", TEXT)

    def test_owner_health_page_omits_internal_certificate_number(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, function)
        self.assertNotIn("certificate_no", segment)

    def test_sensitive_records_are_not_shared_by_default(self):
        health_create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_create")
        segment = ast.get_source_segment(TEXT, health_create)
        self.assertIn("owner_visible: bool = Form(False)", segment)

    def test_weight_records_support_detailed_past_measurements(self):
        for field in ("recorded_at", "meal_amount_g", "food_name", "stool_condition", "health_condition"):
            self.assertIn(f"{field}:", TEXT)
            self.assertIn(f'name="{field}"', TEXT)
        self.assertIn('type="datetime-local"', TEXT)

    def test_weight_condition_choices_are_validated(self):
        health_create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_create")
        segment = ast.get_source_segment(TEXT, health_create)
        self.assertIn('{"", "良好", "少し悪い", "悪い"}', segment)
        self.assertIn('"やわらかい"', segment)

    def test_owner_shared_weight_includes_detailed_condition(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, function)
        for field in ("meal_amount_g", "food_name", "stool_condition", "health_condition"):
            self.assertIn(f"item.{field}", segment)

    def test_puppies_are_grouped_as_siblings(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_weights_page")
        segment = ast.get_source_segment(TEXT, function)
        self.assertIn("(dog.dam_id, dog.sire_id, dog.birth_date)", segment)
        self.assertIn("兄弟 {len(siblings)}頭", segment)
        self.assertIn("weight-siblings", segment)

    def test_health_forms_have_searchable_dog_pickers(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        segment = ast.get_source_segment(TEXT, function)
        for key in ("health",):
            self.assertIn(f'dog_picker("{key}")', segment)
        self.assertNotIn('dog_picker("vaccine")', segment)
        self.assertNotIn('dog_picker("medication")', segment)
        self.assertNotIn('dog_picker("disease")', segment)
        self.assertIn("呼び名・血統書名・犬種・区分で検索", segment)
        self.assertIn("d.call_name, d.registered_name, d.breed", segment)
        self.assertIn("document.querySelectorAll('.dog-search')", segment)

    def test_health_dog_picker_defaults_to_resident_dogs(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        segment = ast.get_source_segment(TEXT, function)
        self.assertIn('d.status in {"delivered", "transferred"}', segment)
        self.assertIn("販売済み・譲渡済みの犬も検索する", segment)
        self.assertIn("includeAll.checked || option.dataset.nonresident!=='true'", segment)
        self.assertIn("filterDogs();", segment)

    def test_health_dog_picker_does_not_overlap_adjacent_fields(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        segment = ast.get_source_segment(TEXT, function)
        self.assertIn(".dog-picker{grid-column:span 2;min-width:0}", segment)
        self.assertIn("@media(max-width:700px){.dog-picker{grid-column:1/-1}}", segment)

    def test_vaccination_management_is_a_dedicated_page(self):
        self.assertIn('@app.get("/modules/health/vaccinations"', TEXT)
        health_page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        segment = ast.get_source_segment(TEXT, health_page)
        self.assertIn('href="/modules/health/vaccinations"', segment)
        self.assertNotIn('<h2 id="vaccines">', segment)

    def test_vaccination_types_are_counted_separately(self):
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_vaccinations_page")
        segment = ast.get_source_segment(TEXT, function)
        self.assertIn('item.vaccine_type == "rabies"', segment)
        self.assertIn('item.vaccine_type == "mixed"', segment)
        self.assertIn("missing_rabies", segment)
        self.assertIn("missing_mixed", segment)

    def test_vaccination_certificate_is_private_and_size_limited(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "vaccine_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("8 * 1024 * 1024 + 1", segment)
        self.assertIn('"application/pdf"', segment)
        family = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_vaccination_certificate")
        family_segment = ast.get_source_segment(TEXT, family)
        self.assertIn("family_owned_dog", family_segment)
        self.assertIn("share.owner_visible", family_segment)

    def test_vaccination_can_be_shared_and_schedules_todo(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "vaccine_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("owner_visible: bool = Form(False)", segment)
        self.assertIn('record_type="vaccination"', segment)
        self.assertIn("TaskEvent(", segment)

    def test_vaccination_dose_means_puppy_series_not_annual_count(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_vaccinations_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("子犬期の接種順（任意）", segment)
        self.assertIn("成犬の定期接種では入力不要です。", segment)
        for label in ("1回目", "2回目", "3回目", "追加接種"):
            self.assertIn(label, segment)
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "vaccine_create")
        self.assertIn('dose_number not in {"", "1", "2", "3", "4"}', ast.get_source_segment(TEXT, create))

    def test_checkup_management_is_a_dedicated_page(self):
        self.assertIn('@app.get("/modules/health/checkups"', TEXT)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_checkups_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("今年度未受診", "今年度受診済み", "触診", "血液検査", "エコー", "胸部X線"):
            self.assertIn(label, segment)
        self.assertIn('href="/modules/health/checkups"', ast.get_source_segment(TEXT, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")))
        self.assertNotIn('<option value="checkup">健康診断</option>', ast.get_source_segment(TEXT, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")))

    def test_checkup_requires_at_least_one_exam_item(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_checkup_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("not any([physical_exam, blood_test, ultrasound, chest_xray])", segment)
        self.assertIn('category="checkup"', segment)
        self.assertIn("TaskEvent(", segment)

    def test_checkup_attachment_is_private_and_size_limited(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_checkup_create")
        self.assertIn("8 * 1024 * 1024 + 1", ast.get_source_segment(TEXT, create))
        family = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_checkup_attachment")
        segment = ast.get_source_segment(TEXT, family)
        self.assertIn("family_owned_dog", segment)
        self.assertIn("share.owner_visible", segment)

    def test_checkup_is_not_shared_by_default(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "health_checkup_create")
        self.assertIn("owner_visible: bool = Form(False)", ast.get_source_segment(TEXT, create))

    def test_medication_management_is_a_dedicated_page(self):
        self.assertIn('@app.get("/modules/health/medications"', TEXT)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_medications_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("対象犬", "年齢", "誕生日", "投薬回数", "継続中"):
            self.assertIn(label, segment)
        health = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        self.assertIn('href="/modules/health/medications"', ast.get_source_segment(TEXT, health))

    def test_medication_count_is_grouped_by_dog(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_medications_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("counts[item.dog_id]", segment)
        self.assertIn("counts.get(dog.id, 0)", segment)
        self.assertIn("dog.birth_date", segment)

    def test_medication_internal_notes_are_not_shared(self):
        family = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, family)
        medication_segment = segment[segment.index('shared_ids.get("medication")'):segment.index('shared_ids.get("disease")')]
        self.assertIn("item.owner_notes", medication_segment)
        self.assertNotIn("item.notes", medication_segment)

    def test_medication_share_and_next_todo_are_explicit(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "medication_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("owner_visible: bool = Form(False)", segment)
        self.assertIn('record_type="medication"', segment)
        self.assertIn("TaskEvent(", segment)
        self.assertIn('medication_status not in {"single", "ongoing", "completed"}', segment)

    def test_disease_management_is_a_dedicated_page(self):
        self.assertIn('@app.get("/modules/health/diseases"', TEXT)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_diseases_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("対象犬", "年齢", "誕生日", "罹患回数", "治療中", "経過観察", "完治", "慢性"):
            self.assertIn(label, segment)
        health = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        self.assertIn('href="/modules/health/diseases"', ast.get_source_segment(TEXT, health))

    def test_disease_count_is_grouped_by_dog(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_diseases_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("counts[item.dog_id]", segment)
        self.assertIn("counts.get(dog.id, 0)", segment)

    def test_disease_internal_details_are_not_shared(self):
        family = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, family)
        disease_segment = segment[segment.index('shared_ids.get("disease")'):segment.index('shared_ids.get("food")')]
        self.assertIn("item.owner_notes", disease_segment)
        self.assertNotIn("item.details", disease_segment)

    def test_disease_share_and_followup_todo_are_explicit(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "disease_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("owner_visible: bool = Form(False)", segment)
        self.assertIn('record_type="disease"', segment)
        self.assertIn("TaskEvent(", segment)
        self.assertIn('disease_status not in {"treatment", "followup", "recovered", "chronic"}', segment)

    def test_food_management_is_a_dedicated_page(self):
        self.assertIn('@app.get("/modules/health/foods"', TEXT)
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_foods_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("対象犬", "年齢", "誕生日", "利用開始日", "利用終了日", "1日量", "給与回数"):
            self.assertIn(label, segment)
        health = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")
        self.assertIn('href="/modules/health/foods"', ast.get_source_segment(TEXT, health))
        self.assertNotIn('<h2 id="foods">', ast.get_source_segment(TEXT, health))

    def test_food_records_are_linked_to_dogs_and_search_residents(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_foods_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("counts[item.dog_id]", segment)
        self.assertIn("販売済み・譲渡済みの犬も検索する", segment)
        self.assertIn("dog.status not in", segment)
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "food_create")
        self.assertIn("dog = tenant_dog", ast.get_source_segment(TEXT, create))

    def test_food_owner_share_omits_internal_notes(self):
        family = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, family)
        food_segment = segment[segment.index('shared_ids.get("food")'):segment.index("entries.sort")]
        self.assertIn("item.owner_notes", food_segment)
        self.assertNotIn("item.notes", food_segment)

    def test_food_share_is_explicit_and_values_are_validated(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "food_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("owner_visible: bool = Form(False)", segment)
        self.assertIn('record_type="food"', segment)
        self.assertIn('food_status not in {"ongoing", "completed"}', segment)
        self.assertIn("not 1 <= times <= 10", segment)

    def test_owner_health_records_keep_creator_and_tenant_provenance(self):
        self.assertIn("class OwnerHealthRecord(Base):", TEXT)
        model = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "OwnerHealthRecord")
        segment = ast.get_source_segment(TEXT, model)
        for field in ("tenant_id", "dog_id", "owner_id", "share_to_breeder", "created_at", "updated_at"):
            self.assertIn(field, segment)

    def test_owner_health_management_uses_generic_breeder_label(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("うちの子健康管理", segment)
        self.assertIn("ブリーダーへ共有する", segment)
        self.assertIn("共有先：", segment)
        self.assertNotIn("ESTRELLAへ共有", segment)

    def test_owner_can_only_update_records_they_created(self):
        update = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_update")
        segment = ast.get_source_segment(TEXT, update)
        self.assertIn("OwnerHealthRecord.owner_id == user.id", segment)
        self.assertIn("この健康記録を変更する権限がありません", segment)
        self.assertNotIn("session.delete", segment)

    def test_breeder_shared_owner_records_are_read_only(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_owner_records_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("OwnerHealthRecord.share_to_breeder.is_(True)", segment)
        self.assertIn("閲覧のみ", segment)
        self.assertNotIn('<form method="post"', segment)
        self.assertIn('href="/modules/health/owner-records"', ast.get_source_segment(TEXT, next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_page")))

    def test_owner_health_create_requires_active_dog_ownership(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("family_owned_dog(dog_id, user, session)", segment)
        self.assertIn("owner_id=user.id", segment)
        self.assertIn("tenant_id=ownership.tenant_id", segment)

    def test_owner_health_top_matches_breeder_six_card_structure(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_dog_health")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn('/health/{key}', segment)
        for label in ("体重", "ワクチン", "健診", "投薬", "病歴", "フード"):
            self.assertIn(label, segment)
        self.assertIn("category_cards", segment)
        self.assertNotIn("<h2>健康記録を追加</h2>", segment)

    def test_owner_category_page_has_fixed_dog_and_inherited_records(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("対象犬は", segment)
        self.assertIn("に固定されています", segment)
        self.assertIn("ブリーダー記録・閲覧のみ", segment)
        self.assertNotIn("対象犬を検索", segment)
        self.assertIn("過去オーナー記録・変更不可", segment)

    def test_owner_category_forms_have_breeder_equivalent_fields(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        for field in ("weight_kg", "vaccine_name", "physical_exam", "blood_test", "ultrasound", "chest_xray", "medicine_name", "disease_name", "food_name", "amount_g", "times_per_day"):
            self.assertIn(f'name="{field}"', segment)
        self.assertIn("ブリーダーへ共有する", segment)
        self.assertIn("共有先：", segment)

    def test_owner_category_create_validates_ownership_and_category_values(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "family_owner_health_category_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("family_owned_dog(dog_id, user, session)", segment)
        self.assertIn("健診項目を1つ以上選択してください", segment)
        self.assertIn("給与量・回数を確認してください", segment)
        self.assertIn("owner_id=user.id", segment)

    def test_owner_weight_combines_breeder_and_owner_measurements(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn("weight_points", segment)
        self.assertIn("for day, value, _ in inherited", segment)
        self.assertIn("for item in records", segment)
        self.assertIn("weight_points.sort", segment)

    def test_owner_weight_shows_latest_difference_and_range(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("最新体重", "前回との差", "測定回数", "記録範囲"):
            self.assertIn(label, segment)
        self.assertIn("difference = latest - previous", segment)

    def test_owner_weight_has_accessible_timeline_chart(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        self.assertIn('aria-label="体重の時系列推移"', segment)
        self.assertIn("owner-weight-chart", segment)
        self.assertIn("<polyline", segment)

    def test_owner_vaccination_has_status_summary_and_types(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("狂犬病", "混合ワクチン", "最終接種日", "次回予定", "30日以内", "期限超過", "期限間近"):
            self.assertIn(label, segment)
        self.assertIn('name="vaccine_type"', segment)

    def test_owner_vaccine_certificate_is_size_limited_and_private(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "family_owner_health_category_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("8 * 1024 * 1024 + 1", segment)
        self.assertIn('"application/pdf", "image/jpeg", "image/png"', segment)
        owner = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_attachment")
        self.assertIn("family_owned_dog", ast.get_source_segment(TEXT, owner))
        breeder = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_owner_record_attachment")
        breeder_segment = ast.get_source_segment(TEXT, breeder)
        self.assertIn("OwnerHealthRecord.share_to_breeder.is_(True)", breeder_segment)
        self.assertIn('"Cache-Control": "private, no-store"', breeder_segment)

    def test_owner_vaccine_due_items_appear_in_notifications(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_vaccine_due_items")
        segment = ast.get_source_segment(TEXT, helper)
        self.assertIn('OwnerHealthRecord.category == "vaccination"', segment)
        self.assertIn('HealthRecordShare.record_type == "vaccination"', segment)
        self.assertIn("-90 <= days <= 30", segment)
        notifications = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_notifications")
        self.assertIn("family_vaccine_due_items", ast.get_source_segment(TEXT, notifications))

    def test_owner_checkup_has_summary_and_result_attachment(self):
        page = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_owner_health_category_page")
        segment = ast.get_source_segment(TEXT, page)
        for label in ("最終受診日", "次回予定", "要確認の結果", "期限間近・超過", "検査結果（PDF・JPG・PNG／8MBまで）"):
            self.assertIn(label, segment)
        self.assertIn('name="attachment_file"', segment)
        self.assertIn('category == "checkup"', segment)

    def test_owner_checkup_attachment_uses_private_shared_access(self):
        create = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "family_owner_health_category_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn('category in {"vaccination", "checkup"}', segment)
        self.assertIn("attachment_data=attachment_data", segment)
        breeder = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "health_owner_record_attachment")
        self.assertIn("OwnerHealthRecord.share_to_breeder.is_(True)", ast.get_source_segment(TEXT, breeder))

    def test_owner_checkup_due_items_appear_in_notifications(self):
        helper = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_checkup_due_items")
        segment = ast.get_source_segment(TEXT, helper)
        self.assertIn('OwnerHealthRecord.category == "checkup"', segment)
        self.assertIn('HealthRecord.category == "checkup"', segment)
        self.assertIn("-90 <= days <= 30", segment)
        notifications = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "family_notifications")
        self.assertIn("family_checkup_due_items", ast.get_source_segment(TEXT, notifications))


if __name__ == "__main__":
    unittest.main()
