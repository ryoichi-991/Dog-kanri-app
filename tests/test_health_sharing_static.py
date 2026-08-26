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
        for key in ("health", "vaccine", "medication", "disease"):
            self.assertIn(f'dog_picker("{key}")', segment)
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


if __name__ == "__main__":
    unittest.main()
