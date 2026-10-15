"""Fault regression tests; synthetic fixtures are not model-inference evidence."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

from model_services.agent_service import AgentApplication,GenerationDeadline
from workbench import server,task_jobs
from workbench.agent_bridge import AgentTurn


class SavedTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.session={'id':'abcdef123456','lock':threading.Lock()}
        self.release=threading.Event()
        self.addCleanup(self.release.set)

    def wait(self,job):
        for _ in range(300):
            item=task_jobs.get_job(self.root,job['id'])
            if item['status']!='running':return item
            time.sleep(.01)
        self.fail('Worker did not finish.')

    def test_submit_returns_before_execution_and_duplicate_is_rejected_without_rerun(self):
        calls=[]
        def execute(session,payload,job):
            calls.append(payload['query'])
            task_jobs.publish(self.root,job,phase='Explicit test wait')
            self.release.wait(3)
            return {'id':'test-result','status':'completed'}
        began=time.monotonic()
        job=task_jobs.start_job(self.root,self.session,{'query':'Fixture task','mode':'demo'},execute)
        self.assertLess(time.monotonic()-began,1)
        self.assertEqual(task_jobs.active_job(self.root,self.session['id'])['id'],job['id'])
        with self.assertRaisesRegex(ValueError,'busy'):
            task_jobs.start_job(self.root,self.session,{'query':'Duplicate'},execute)
        self.release.set()
        final=self.wait(job)
        self.assertEqual(calls,['Fixture task'])
        self.assertEqual(final['result']['id'],'test-result')
        # Dropping in-memory registry represents reopening a saved completed job.
        task_jobs.JOBS.pop((str(self.root),job['id']))
        self.assertEqual(task_jobs.get_job(self.root,job['id']),final)
        self.assertFalse(self.session['lock'].locked())

    def test_worker_failure_is_saved_and_releases_session(self):
        def execute(*args,**kwargs):raise ValueError('Explicit fixture failure')
        job=task_jobs.start_job(self.root,self.session,{'query':'Fail'},execute)
        final=self.wait(job)
        self.assertEqual(final['status'],'failed')
        self.assertEqual(final['error'],'Explicit fixture failure')
        self.assertFalse(self.session['lock'].locked())

    def test_restart_marks_running_job_interrupted_and_does_not_claim_completion(self):
        job={'id':'abcdefabcdef','session_id':self.session['id'],'status':'running'}
        task_jobs.publish(self.root,job)
        result=task_jobs.get_job(self.root,job['id'])
        self.assertEqual(result['status'],'interrupted')
        self.assertNotIn('result',result)
        self.assertIn('No inference was automatically repeated',result['error'])

    def test_real_demo_task_is_saved_once_with_job_and_normal_evidence(self):
        with patch.object(server,'DATA',self.root):
            session=server.SESSIONS[server.new_session()['id']]
            job=task_jobs.start_job(self.root,session,{'query':'Extract buildings in the whole image.','mode':'demo'},server._run_task)
            final=self.wait(job)
            result=final['result']
            self.assertEqual(result['metrics']['pixel_area'],75350)
            self.assertEqual(len(session['runs']),1)
            self.assertEqual(json.loads((self.root/session['id']/result['id']/'result.json').read_text())['metrics'],result['metrics'])
            self.assertTrue((self.root/session['id']/result['id']/'mask.png').is_file())

    def test_unsupported_tiled_is_rejected_before_any_agent_or_sam_call(self):
        with patch.object(server,'DATA',self.root),patch.dict(os.environ,{'GEO_REMOTESAM_QUALITY_MODES':'fast'}),patch.object(server,'AgentTurn') as planner,patch.object(server,'post_json') as sam:
            session=server.SESSIONS[server.new_session()['id']]
            result=server.run_task(session,{'query':'Extract buildings.','mode':'live','quality_mode':'accurate'})
            self.assertEqual(result['status'],'failed')
            self.assertIn('does not support tiled',result['message'])
            planner.assert_not_called();sam.assert_not_called()
            self.assertNotIn('metrics',result)

    def test_agent_only_deployment_rejects_masks_before_expensive_planning(self):
        with patch.object(server,'DATA',self.root),patch.dict(os.environ,{'GEO_REMOTESAM_URL':''}),patch.object(server,'AgentTurn') as planner:
            session=server.SESSIONS[server.new_session()['id']]
            result=server.run_task(session,{'query':'Extract buildings.','mode':'live'})
            self.assertEqual(result['status'],'failed')
            self.assertIn('Scene questions require only RemoteAgent',result['message'])
            self.assertNotIn('mask_url',result)
            planner.assert_not_called()


class DeadlineTests(unittest.TestCase):
    def test_cooperative_deadline_stops_and_never_returns_late_text(self):
        with patch('model_services.agent_service.time.monotonic',return_value=11):
            stop=GenerationDeadline(10)
            self.assertTrue(stop(None,None))
            with self.assertRaises(TimeoutError):stop.check()

    def test_timeout_releases_generation_lock_and_next_request_can_run(self):
        class ExplicitDeadlineFixture:
            supports_deadline=True
            metadata={'model_evidence':False,'backend':'explicit-test-only'}
            def __init__(self):self.fail=True
            def complete(self,*args,deadline):
                if self.fail:raise TimeoutError('Explicit deadline fixture')
                return 'Explicit test response',{'completion_tokens':1}
        backend=ExplicitDeadlineFixture()
        application=AgentApplication(backend=backend)
        payload={'model':'RemoteAgent','messages':[],'max_tokens':16}
        with patch('model_services.agent_service.prepare_messages'):
            with self.assertRaises(TimeoutError):application.chat(payload,5)
            self.assertFalse(application.lock.locked())
            backend.fail=False
            self.assertIn('choices',application.chat(payload,5))

    def test_feedback_budget_is_separate_and_restored_after_failure(self):
        turn=AgentTurn.__new__(AgentTurn)
        turn.agent=Mock(request_timeout=3600,max_tokens=512)
        turn.query='fixture';turn.image_path='fixture.png';turn.decision=Mock();turn.context={}
        observed=[]
        def fail(*args,**kwargs):
            observed.append((turn.agent.request_timeout,turn.agent.max_tokens))
            raise ValueError('Explicit reporting timeout')
        turn.agent.continue_with_tool_result.side_effect=fail
        with patch.dict(os.environ,{'GEO_AGENT_FEEDBACK_TIMEOUT_SECONDS':'30'}):
            with self.assertRaises(ValueError):turn.feedback({})
        self.assertEqual(observed,[(30,96)])
        self.assertEqual((turn.agent.request_timeout,turn.agent.max_tokens),(3600,512))


if __name__=='__main__':unittest.main()
