"""Explicit fake protocol responses; these tests do not establish real inference."""
import os
import unittest
from unittest.mock import Mock,patch
from workbench.agent_bridge import AgentTurn,PlannerResponseError,WorkbenchAgent

class FeedbackBudgetDiagnosticsTests(unittest.TestCase):
    def turn(self):
        turn=AgentTurn.__new__(AgentTurn)
        turn.agent=Mock(request_timeout=3600,max_tokens=128)
        turn.query='EXPLICIT-FAKE';turn.image_path='fixture.png';turn.context={};turn.decision=Mock()
        return turn

    def test_reporting_budget_can_exceed_planning_budget_and_is_restored_after_failure(self):
        turn=self.turn();observed=[]
        def fail(*args,**kwargs):
            observed.append((turn.agent.request_timeout,turn.agent.max_tokens))
            raise ValueError('Explicit fake request failure')
        turn.agent.continue_with_tool_result.side_effect=fail
        with patch.dict(os.environ,{'GEO_AGENT_FEEDBACK_MAX_TOKENS':'256','GEO_AGENT_FEEDBACK_TIMEOUT_SECONDS':'3600'},clear=True):
            with self.assertRaises(ValueError):turn.feedback({})
        self.assertEqual(observed,[(3600,256)])
        self.assertEqual((turn.agent.request_timeout,turn.agent.max_tokens),(3600,128))

    def test_invalid_reporting_budgets_make_no_model_call(self):
        for value in ('0','15','1025','-2','256.0','nan','２５６',''):
            with self.subTest(value=value):
                turn=self.turn()
                with patch.dict(os.environ,{'GEO_AGENT_FEEDBACK_MAX_TOKENS':value},clear=True):
                    with self.assertRaisesRegex(ValueError,'FEEDBACK_MAX_TOKENS'):turn.feedback({})
                turn.agent.continue_with_tool_result.assert_not_called()
                self.assertEqual(turn.agent.max_tokens,128)

    def test_truncated_raw_reply_is_diagnostic_and_never_returned_as_completed(self):
        with patch.dict(os.environ,{'GEO_AGENT_BASE_URL':'http://example.invalid/v1','GEO_AGENT_MODEL':'EXPLICIT-FAKE'},clear=True):
            agent=WorkbenchAgent('dense')
        raw='<answer>Explicit fake incomplete measurements'
        response={'choices':[{'message':{'content':raw},'finish_reason':'length'}]}
        with patch('workbench.agent_bridge.request_json',return_value=response):
            with self.assertRaises(PlannerResponseError) as caught:agent._run_llm([])
        self.assertEqual(caught.exception.reason,'truncated_reply')
        self.assertEqual(caught.exception.response_record['status'],'truncated_reply')
        self.assertEqual(caught.exception.response_record['raw_response'],raw)
        self.assertEqual(len(caught.exception.response_record['raw_response_sha256']),64)

if __name__=='__main__':unittest.main()
