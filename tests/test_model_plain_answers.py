"""Display-only replies cannot relax the executable dense-call contract."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from workbench.agent_bridge import WorkbenchAgent


class PlainAnswerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / 'image.png'
        Image.new('RGB', (3, 2)).save(self.image)
        env = patch.dict(os.environ, {'GEO_AGENT_BASE_URL': 'http://example.invalid/v1',
                                     'GEO_AGENT_MODEL': 'EXPLICIT-FAKE'}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_plain_scene_is_a_real_text_reply_and_dense_prose_does_not_execute(self):
        for route, expected in [('internal', 'completed'), ('dense', 'unparsed')]:
            with self.subTest(route=route):
                agent = WorkbenchAgent(route)
                with patch.object(agent, '_run_llm', return_value='A park with trees.'):
                    reply = agent.plan('Describe this image.', self.image)
                self.assertEqual(reply.status, expected)
                self.assertIsNone(reply.tool_call)

    def test_malformed_markup_and_any_call_never_become_plain_answers(self):
        agent = WorkbenchAgent('internal')
        for text in ['<answer>Incomplete', 'T_call(semantic_segmentation, "x", ["building"])']:
            with patch.object(agent, '_run_llm', return_value=text):
                reply = agent.plan('Describe the image.', self.image)
            self.assertNotEqual(reply.status, 'completed')
            self.assertIsNone(reply.tool_call)

    def test_feedback_hash_lists_are_bounded_and_exact_measurements_and_source_are_preserved(self):
        agent = WorkbenchAgent('dense')
        payload = {'metrics': {'pixel_area': 17, 'area_ratio': 17 / 91, 'candidates': list(range(10000))},
                   'service_metadata': {'source_files_sha256': {str(i): 'a' * 64 for i in range(10000)}}}
        original = copy.deepcopy(payload)
        with patch.object(agent, '_run_llm', side_effect=[
            'T_call(semantic_segmentation, "ignored", ["building"])', 'Recorded pixel_area=17.',
        ]) as model:
            decision = agent.plan('Extract buildings.', self.image)
            answer = agent.continue_with_tool_result('Extract buildings.', self.image, decision, payload)
        self.assertEqual(answer.status, 'completed')
        text = model.call_args_list[1].args[0][-1]['content']
        self.assertLess(len(text), 1000)
        self.assertIn('0.18681318681318682', text)
        self.assertEqual(payload, original)

    def test_truncated_http_reply_is_rejected(self):
        agent = WorkbenchAgent('internal')
        reply = {'choices': [{'message': {'content': 'An unfinished scene'}, 'finish_reason': 'length'}]}
        with patch('workbench.agent_bridge.request_json', return_value=reply), self.assertRaisesRegex(ValueError, 'truncated'):
            agent.plan('Describe.', self.image)


if __name__ == '__main__':
    unittest.main()
