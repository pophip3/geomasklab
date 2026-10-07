"""Client budget tests; mocked HTTP replies are explicitly not model evidence."""
import os
import unittest
from unittest.mock import patch

from workbench.agent_bridge import WorkbenchAgent
from workbench.service_transport import agent_request_settings, inspect_services, request_json


class AgentClientSettingsTests(unittest.TestCase):
    def setUp(self):
        # Clear inherited tuning so route defaults are tested independently of
        # whoever runs this suite or the optional reviewer deployment profile.
        self.environment = patch.dict(os.environ, {
            'GEO_AGENT_BASE_URL': 'http://example.invalid/v1',
            'GEO_AGENT_MODEL': 'EXPLICIT-FAKE-CLIENT-TEST',
            'GEO_AGENT_API_KEY': 'fixture-only-key',
            'GEO_REMOTESAM_URL': 'http://example.invalid/predict',
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_route_defaults_remain_512_dense_1024_internal_with_120_second_chat_timeout(self):
        for route, expected in (('dense', 512), ('internal', 1024)):
            with self.subTest(route=route):
                agent = WorkbenchAgent(route)
                self.assertEqual(agent.max_tokens, expected)
                self.assertEqual(agent.request_timeout, 120)
                self.assertEqual(agent.model_name, 'EXPLICIT-FAKE-CLIENT-TEST')
        self.assertEqual(agent_request_settings(512), (512, 120))

    def test_optional_token_budget_overrides_both_routes_at_inclusive_bounds(self):
        for raw, expected in (('16', 16), ('128', 128), ('1024', 1024), (' 256 ', 256)):
            with self.subTest(raw=raw), patch.dict(os.environ, {'GEO_AGENT_MAX_TOKENS': raw}):
                for route in ('dense', 'internal'):
                    agent = WorkbenchAgent(route)
                    self.assertEqual(agent.max_tokens, expected)
                    self.assertEqual(agent.request_timeout, 120)

    def test_invalid_token_limits_are_rejected_before_any_request(self):
        for value in ('', '15', '1025', '0', '-16', '+16', '16.0', '1e2', 'true', 'NaN', 'Infinity', '１２８'):
            with self.subTest(value=value), patch.dict(os.environ, {'GEO_AGENT_MAX_TOKENS': value}), \
                 patch('workbench.agent_bridge.request_json') as request:
                with self.assertRaisesRegex(ValueError, 'GEO_AGENT_MAX_TOKENS'):
                    WorkbenchAgent()
                request.assert_not_called()

    def test_optional_chat_timeout_accepts_finite_inclusive_bounds_and_fractional_seconds(self):
        for raw, expected in (('5', 5), ('3600', 3600), ('1800', 1800), ('120.5', 120.5)):
            with self.subTest(raw=raw), patch.dict(os.environ, {'GEO_AGENT_TIMEOUT_SECONDS': raw}):
                agent = WorkbenchAgent('internal')
                self.assertEqual(agent.request_timeout, expected)
                self.assertEqual(agent.max_tokens, 1024)

    def test_invalid_timeouts_are_rejected_before_any_request(self):
        for value in ('', '4.99', '3600.01', '0', '-1', 'true', 'NaN', 'nan', 'inf', '-Infinity'):
            with self.subTest(value=value), patch.dict(os.environ, {'GEO_AGENT_TIMEOUT_SECONDS': value}), \
                 patch('workbench.agent_bridge.request_json') as request:
                with self.assertRaisesRegex(ValueError, 'GEO_AGENT_TIMEOUT_SECONDS'):
                    WorkbenchAgent()
                request.assert_not_called()

    def test_actual_chat_request_uses_explicit_budgets_without_changing_model_identity(self):
        messages = [{'role': 'user', 'content': 'Explicit fake test; no image or inference is sent.'}]
        reply = {'choices': [{'message': {'content': '<answer>Explicit fake HTTP fixture.</answer>'}}]}
        with patch.dict(os.environ, {'GEO_AGENT_MAX_TOKENS': '128', 'GEO_AGENT_TIMEOUT_SECONDS': '1800'}), \
             patch('workbench.agent_bridge.request_json', return_value=reply) as request:
            agent = WorkbenchAgent('internal')
            self.assertEqual(agent._run_llm(messages), '<answer>Explicit fake HTTP fixture.</answer>')
            request.assert_called_once_with('http://example.invalid/v1/chat/completions', {
                'model': 'EXPLICIT-FAKE-CLIENT-TEST', 'messages': messages,
                'max_tokens': 128, 'temperature': 0,
            }, timeout=1800, headers={'Authorization': 'Bearer fixture-only-key'})

    def test_default_chat_request_retains_120_second_timeout_and_route_budget(self):
        reply = {'choices': [{'message': {'content': '<answer>Explicit fake fixture.</answer>'}}]}
        with patch('workbench.agent_bridge.request_json', return_value=reply) as request:
            WorkbenchAgent('dense')._run_llm([])
            self.assertEqual(request.call_args.kwargs['timeout'], 120)
            self.assertEqual(request.call_args.args[1]['max_tokens'], 512)

    def test_chat_tuning_does_not_change_health_probe_timeouts_or_sam_transport_default(self):
        with patch.dict(os.environ, {'GEO_AGENT_MAX_TOKENS': '128', 'GEO_AGENT_TIMEOUT_SECONDS': '1800'}), \
             patch('workbench.service_transport.request_json', side_effect=[
                 {'data': [{'id': 'EXPLICIT-FAKE-CLIENT-TEST'}]}, {'ready': True},
             ]) as request:
            result = inspect_services()
            self.assertTrue(result['services_ready'])
            self.assertFalse(result['inference_verified'])
            self.assertEqual([call.kwargs['timeout'] for call in request.call_args_list], [5, 5])
        self.assertEqual(request_json.__defaults__[1], 120)


if __name__ == '__main__':
    unittest.main()
