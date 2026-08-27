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
        disease_segment = segment[segment.index('shared_ids.get("disease")'):segment.index("entries.sort")]
        self.assertIn("item.owner_notes", disease_segment)
        self.assertNotIn("item.details", disease_segment)

    def test_disease_share_and_followup_todo_are_explicit(self):
        create = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "disease_create")
        segment = ast.get_source_segment(TEXT, create)
        self.assertIn("owner_visible: bool = Form(False)", segment)
        self.assertIn('record_type="disease"', segment)
        self.assertIn("TaskEvent(", segment)
        self.assertIn('disease_status not in {"treatment", "followup", "recovered", "chronic"}', segment)


if __name__ == "__main__":
    unittest.main()
