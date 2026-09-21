import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('HUB_TEST_IMPORT_ROOT', str(root)))
from hub.features import missions as M
from hub import agent_knowledge, decide

spec = importlib.util.spec_from_file_location('hub.features.voice', root / 'hub/features/voice.py')
V = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = V
spec.loader.exec_module(V)

class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.network = patch.object(decide, '_ollama_raw', AsyncMock(side_effect=AssertionError('Unexpected model/network call')))
        self.network.start(); self.addCleanup(self.network.stop)
        self.start = patch.object(M, '_ensure_ollama', AsyncMock(return_value=False))
        self.start.start(); self.addCleanup(self.start.stop)

    async def test_compound_greeting_answers_question(self):
        result = await V.chat('Hello, how are you my friend?')
        self.assertEqual(result['say'], "I'm operational. How may I assist?")

    async def test_greetings_are_warm_without_sarcasm(self):
        h = [{'role':'assistant','text':V.INTRO}]
        for phrase in ['Hello', 'Hello again', 'How are you?', 'Thank you']:
            r = await V.chat(phrase, h)
            self.assertNotIn(r['say'], ['Yes?', 'Go ahead.', 'Running fine, and nothing is on fire.'])

    async def test_repeated_okay_does_not_wait_for_model(self):
        r = await V.chat('Okay, okay, okay.')
        self.assertEqual(r['backend'], 'rules')
        self.assertIsNone(r['action'])

    async def test_voice_pc_switch_runs_on_explicit_request(self):
        for text, state in [('enable PC control','on'),('start PC control','on'),('turn PC control off','off'),('please switch PC control on','on'),('disable PC control','off')]:
            with self.subTest(text=text):
                r = await V.chat(text)
                self.assertFalse(r['confirm'])
                self.assertEqual(r['action'], {'id':'pc_control','args':{'state':state},'label':'Switch PC control '+state})

    async def test_direct_browser_request_is_gated_when_pc_control_is_off(self):
        with patch('hub.features.mcp.servers', return_value=[{'name':'windows','installed':True,'enabled':False}]):
            r = await V.chat('Please open a browser')
        self.assertIsNone(r['action'])
        self.assertIn('PC control is off', r['say'])

    async def test_direct_browser_request_uses_bounded_action_when_enabled(self):
        with patch('hub.features.mcp.servers', return_value=[{'name':'windows','installed':True,'enabled':True}]):
            r = await V.chat('Open YouTube')
        self.assertEqual(r['action']['id'], 'pc_direct')
        self.assertEqual(r['action']['args']['value'], 'https://www.youtube.com/')

    async def test_enable_pc_control_then_youtube_search_is_one_direct_action(self):
        with patch('hub.features.mcp.servers', return_value=[{'name':'windows','installed':True,'enabled':False}]):
            r = await V.chat('Start PC control then search YouTube for Agent Smith scenes')
        self.assertEqual(r['action']['id'], 'pc_direct')
        self.assertEqual(r['action']['args']['state'], 'on')
        self.assertIn('youtube.com/results?search_query=agent+smith+scenes', r['action']['args']['value'])

    async def test_direct_browser_action_launches_edge_without_quick_chat(self):
        with patch('hub.features.mcp.servers', return_value=[{'name':'windows','installed':True,'enabled':True}]), patch.object(V, '_launch_edge') as launch:
            r = await V.run_action('pc_direct', {'kind':'url','value':'https://www.youtube.com/','label':'YouTube'})
        launch.assert_called_once_with('https://www.youtube.com/')
        self.assertEqual(r['say'], 'Opening YouTube in Edge.')

    async def test_status_rule_does_not_execute_tools(self):
        r = await V.chat('what MCP tools are available')
        self.assertEqual(r['action']['id'],'mcp_status')

    async def test_hub_navigation_and_pause_still_work(self):
        self.assertEqual((await V.chat('open missions'))['url'],'/missions')
        self.assertTrue((await V.chat('pause all agents'))['confirm'])

    async def test_model_pc_state_survives_schema_and_parsing(self):
        async def response(body):
            self.assertEqual(body['format']['properties']['state']['enum'],['on','off'])
            return {'message':{'content':json.dumps({'say':'Enable PC control?','action':'pc_control','state':'on'})}}
        with patch.object(agent_knowledge,'model_chain',return_value=['ollama/test']), patch.object(decide,'_ollama_raw',response):
            r = await V.chat('Let the agents use the desktop')
        self.assertEqual(r['action']['args']['state'],'on')
        self.assertFalse(r['confirm'])

    async def test_missing_switch_direction_does_not_default_to_off(self):
        with patch.object(V,'_llm',AsyncMock(return_value={'say':'Switch it','action':'pc_control'})):
            r = await V.chat('Change desktop access')
        self.assertIsNone(r['action'])

    async def test_action_rejects_missing_pc_direction(self):
        from hub.features import mcp
        with patch.object(mcp,'set_enabled') as toggle:
            r = await V.run_action('pc_control', {})
            toggle.assert_not_called()
        self.assertIn('on or off', r['say'])

    async def test_model_timeout_returns_retryable_reply(self):
        wait = asyncio.wait_for
        async def stalled(*args): await asyncio.sleep(60)
        with patch.object(V,'_llm',stalled), patch.object(asyncio,'wait_for',lambda coro,timeout:wait(coro,.01)):
            r = await V.chat('Please explain something complex')
        self.assertIn('too long',r['say'])

    async def test_empty_spoken_text_with_action_is_accepted(self):
        with patch.object(V,'_llm',AsyncMock(return_value={'say':'','action':'list_agents'})):
            r = await V.chat('Who is on the team')
        self.assertEqual(r['action']['id'],'list_agents')

    async def test_invented_mission_is_rejected(self):
        with patch.object(V,'_llm',AsyncMock(return_value={'say':'Applying','action':'apply','mission':'missing-id'})):
            r = await V.chat('Apply the invented task')
        self.assertIsNone(r['action'])

if __name__ == '__main__': unittest.main(verbosity=2)

