"""The actual UI target labels must pass the same guard as typed tasks."""
from pathlib import Path
import re
import unittest
from workbench.agent_bridge import LABELS
from workbench.v07_contract import has_target_intent, target_intent, validate_target_intent


class QuickTargetIntentTests(unittest.TestCase):
    def test_every_actual_quick_selector_label_routes_to_its_declared_target(self):
        source=(Path(__file__).resolve().parents[1]/'workbench/web/app.js').read_text(encoding='utf-8')
        literal=re.search(r'const targetNames = \{([^}]+)\}',source).group(1)
        labels=dict(re.findall(r"(\w+):'([^']+)'",literal))
        self.assertEqual(set(labels),set(LABELS))
        for target,label in labels.items():
            query='Extract only '+label.lower()+' in the whole image.'
            with self.subTest(target=target):
                validate_target_intent(query);self.assertTrue(has_target_intent(query));self.assertEqual(target_intent(query),target)

    def test_all_agent_label_aliases_match_the_workbench_guard(self):
        for target,aliases in LABELS.items():
            for alias in aliases:
                with self.subTest(alias=alias):
                    query='Extract only '+alias+' in the whole image.'
                    validate_target_intent(query);self.assertEqual(target_intent(query),target)

    def test_mixed_categories_rejected_and_word_fragments_not_targets(self):
        with self.assertRaises(ValueError):validate_target_intent('Extract buildings and vegetation.')
        self.assertIsNone(target_intent('shipbuilding and vegetational discussion'))
