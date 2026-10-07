"""Reporting-turn contracts use explicit fake replies, never inference evidence."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from workbench.agent_bridge import WorkbenchAgent
from workbench.planner_protocol import PlannerProtocol


class LegacyExplicitFakePlanner(PlannerProtocol):
    """Minimal existing-style adapter without a reporting prompt override."""
    def __init__(self):
        super().__init__(model_name='EXPLICIT-FAKE-LEGACY',
            allowed_tools={'semantic_segmentation'}, max_tokens=128)
        self.requests = []
        self.replies = iter(['T_call(semantic_segmentation, "ignored.png", ["building"])',
                             '<answer>Explicit fake legacy response.</answer>'])

    def _runtime_system_prompt(self):
        return 'Explicit fake legacy system contract.'

    def _run_llm(self, messages):
        self.requests.append(messages)
        return next(self.replies)


class ModelFeedbackPromptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / 'explicit-fake-image.png'
        Image.new('RGB', (13, 7), 'white').save(self.image)
        environment = patch.dict(os.environ, {
            'GEO_AGENT_BASE_URL': 'http://example.invalid/v1',
            'GEO_AGENT_MODEL': 'EXPLICIT-FAKE-CONTRACT-ONLY',
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.metrics = {'pixel_area': 17, 'area_ratio': 17 / 91,
                        'scope_area_pixels': 42, 'scope_area_ratio': 17 / 42}
        self.tool_result = {'status': 'success', 'metrics': self.metrics,
                            'image': 'binary image omitted', 'mask': 'binary mask omitted'}

    def conversation(self, final='<answer>pixel_area=17; area_ratio=0.18681318681318682.</answer>'):
        agent = WorkbenchAgent('dense')
        with patch.object(agent, '_run_llm', side_effect=[
            'T_call(semantic_segmentation, "ignored.png", ["building"])', final,
        ]) as model:
            decision = agent.plan('Extract all buildings.', self.image)
            answer = agent.continue_with_tool_result('Extract all buildings.', self.image, decision, self.tool_result)
        return agent, decision, answer, [call.args[0] for call in model.call_args_list]

    def test_first_dense_prompt_retains_tool_contract_and_second_system_is_reporting_only(self):
        agent, decision, answer, requests = self.conversation()
        self.assertEqual(decision.status, 'tool_call')
        self.assertEqual(answer.status, 'completed')
        first_system = requests[0][0]['content']
        final_system = requests[1][0]['content']
        self.assertEqual(first_system, agent._runtime_system_prompt())
        self.assertIn('exactly ONE plain T_call', first_system)
        self.assertIn('no <think>, <answer>', first_system)
        self.assertEqual(final_system, agent._feedback_system_prompt())
        self.assertIn('only these deployed tools are available: none', final_system)
        self.assertIn('exactly one concise <answer>...</answer>', final_system)
        self.assertNotIn('exactly ONE plain T_call', final_system)
        self.assertNotIn('no <think>, <answer>', final_system)
        self.assertIn('exactly as supplied', final_system)
        self.assertIn('subject to review', final_system)

    def test_reporting_history_retains_one_bound_image_prior_call_and_exact_measured_values(self):
        _, decision, answer, requests = self.conversation()
        feedback = requests[1]
        self.assertEqual([message['role'] for message in feedback], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(feedback[1], requests[0][1])
        self.assertEqual(feedback[2]['content'], decision.raw_response)
        result_text = feedback[3]['content'].split('\n', 1)[1].rsplit('\n', 1)[0]
        bounded = json.loads(result_text)
        self.assertEqual(bounded['metrics'], self.metrics)
        self.assertNotIn('image', bounded)
        self.assertNotIn('mask', bounded)
        self.assertNotIn('base64', feedback[3]['content'])
        self.assertEqual([item['round'] for item in answer.history], [1, 2])

    def test_repeated_tool_in_feedback_is_rejected_and_cannot_authorize_a_followup(self):
        _, _, answer, _ = self.conversation('T_call(semantic_segmentation, "ignored.png", ["building"])')
        self.assertEqual(answer.status, 'rejected_tool')
        self.assertIsNone(answer.tool_call)
        self.assertNotEqual(answer.status, 'completed')

    def test_truncated_answer_is_unparsed_in_reporting_turn(self):
        _, _, answer, _ = self.conversation('<answer>Explicit fake truncated response')
        self.assertEqual(answer.status, 'unparsed')
        self.assertIsNone(answer.tool_call)

    def test_error_reporting_uses_same_no_tool_prompt_with_no_invented_statistics(self):
        agent = WorkbenchAgent('dense')
        with patch.object(agent, '_run_llm', side_effect=[
            'T_call(semantic_segmentation, "ignored.png", ["building"])',
            '<answer>Explicit fake service failed.</answer>',
        ]) as model:
            decision = agent.plan('Extract all buildings.', self.image)
            answer = agent.continue_with_tool_result('Extract all buildings.', self.image, decision,
                {'status': 'error', 'message': 'Explicit fake service unavailable.', 'artifacts_created': False})
        messages = model.call_args_list[1].args[0]
        self.assertIn('For an error', messages[0]['content'])
        self.assertIn('"artifacts_created": false', messages[-1]['content'])
        self.assertNotIn('pixel_area', messages[-1]['content'])
        self.assertEqual(answer.status, 'completed')

    def test_protocol_default_remains_compatible_with_existing_adapter_system_prompt(self):
        agent = LegacyExplicitFakePlanner()
        decision = agent.plan('Extract buildings.', self.image)
        answer = agent.continue_with_tool_result('Extract buildings.', self.image, decision, self.tool_result)
        self.assertEqual(agent.requests[0][0], agent.requests[1][0])
        self.assertEqual(agent.requests[1][0]['content'], agent._runtime_system_prompt())
        self.assertEqual(answer.status, 'completed')

    def test_feedback_rejects_a_non_tool_decision_without_an_extra_model_request(self):
        agent = WorkbenchAgent('internal')
        with patch.object(agent, '_run_llm', return_value='<answer>Explicit fake scene.</answer>') as model:
            decision = agent.plan('Describe the scene.', self.image)
            with self.assertRaisesRegex(ValueError, 'No pending tool'):
                agent.continue_with_tool_result('Describe the scene.', self.image, decision, self.tool_result)
        model.assert_called_once()


if __name__ == '__main__':
    unittest.main()
