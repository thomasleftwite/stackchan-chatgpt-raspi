"""Terminal audition: whitelisted events, actual fixture child and Tk controls."""
from pathlib import Path
import queue
import socket
import subprocess
import tempfile
import threading
import unittest
import os
from unittest.mock import Mock, patch

from raspi.host import HostService, ROOT, public_event, resolve_node, child_environment
from raspi.host_network import Endpoint, HostError
from raspi.voice_settings import VoiceSettings


@unittest.skipUnless(os.name == 'posix', 'Linux host backend')
class DeviceEventsTests(unittest.TestCase):
    def test_events_keep_only_matching_protocol_fields_and_safe_classification(self):
        self.assertEqual(public_event({'event':'preview-failed','id':3,'code':'AUTH','status':401,
            'voice':'PRIVATE','pcm':'PRIVATE','apiKey':'PRIVATE','body':'PRIVATE'}),
            {'event':'preview-failed','id':3,'code':'AUTH','status':401})
        self.assertIsNone(public_event({'event':'preview-played','id':True}))
        self.assertIsNone(public_event({'event':'preview-played','id':0}))

    def test_actual_fixture_child_delivers_audio_and_is_reaped_after_terminal_played(self):
        try: node = resolve_node()
        except HostError: self.skipTest('Node unavailable')
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1',0)); port = reserve.getsockname()[1]
        service = HostService(Endpoint('127.0.0.1','127.0.0.1/32'), node, port=port, preview_id=9)
        stop = threading.Event(); events = queue.Queue(); outcome = []
        def run():
            try: outcome.append(service.run(stop,events.put,duration=6))
            except Exception as error: outcome.append(type(error).__name__)
        worker = threading.Thread(target=run); worker.start()
        seen = []
        try:
            self.assertEqual(events.get(timeout=10),{'event':'ready'})
            script = ('import {runGeminiProtocolProbe} from '+repr((ROOT/'server/dist/gemini-probe-client.js').as_uri())+';'
                f'await runGeminiProtocolProbe("ws://127.0.0.1:{port}/live","",Buffer.alloc(640));')
            probe = subprocess.run([str(node),'--input-type=module','-e',script],
                env=child_environment(node,True,'',''),capture_output=True,timeout=8)
            self.assertEqual(probe.returncode,0); self.assertEqual(probe.stdout,b''); self.assertEqual(probe.stderr,b'')
            while not any(e['event']=='session-idle' for e in seen): seen.append(events.get(timeout=5))
            self.assertIn({'event':'preview-played','id':9},seen)
            self.assertNotIn('pcm',str(seen)); self.assertNotIn('voice',str(seen))
        finally:
            stop.set(); worker.join(18)
            if worker.is_alive(): service._stop(); worker.join(3)
        self.assertFalse(worker.is_alive()); self.assertEqual(outcome,[0]); self.assertEqual(service.child.returncode,0)


@unittest.skipUnless(os.name == 'posix', 'Linux GUI')
class DeviceGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from raspi.host_ui import HostWindow
        try: self.root = tk.Tk()
        except tk.TclError: self.skipTest('Tk display unavailable')
        self.root.withdraw(); self.addCleanup(self.root.destroy)
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=temp.name, XDG_DATA_HOME=temp.name+'/data'))
        self.factory = Mock(); self.generator = Mock(); self.player = Mock()
        self.app = HostWindow(self.root,settings=VoiceSettings(Path(temp.name)/'voice-settings.json'),
            generator=self.generator,player=self.player,device_factory=self.factory)
        self.app.fixture.set(False); self.app.key.set('fixture-session-key-long-enough')
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.app.close()
        if self.app.preview_worker: self.app.preview_worker.join(3)

    def finish(self):
        self.app.preview_worker.join(3); self.assertFalse(self.app.preview_worker.is_alive()); self.app.pump()

    def test_default_terminal_mode_needs_no_sleeping_and_adopts_only_after_played(self):
        self.assertEqual(self.app.preview_target.get(),'端末')
        def run(stop, callback, duration):
            callback({'event':'ready'}); callback({'event':'preview-generating','id':1})
            callback({'event':'preview-output','id':1})
            self.assertFalse(stop.is_set()); callback({'event':'preview-played','id':1})
            self.assertFalse(stop.is_set()); callback({'event':'session-idle'})
            self.assertTrue(stop.is_set()); return 0
        self.factory.return_value.run.side_effect=run
        self.app.start_preview('gemini-3.8-live','Kore'); self.finish()
        self.assertIn(('gemini-3.8-live','Kore'),self.app.heard)
        self.assertIn('端末の再生完了',self.app.preview_status.get())
        self.generator.assert_not_called();self.player.assert_not_called()
        self.assertEqual(self.factory.call_args.kwargs['voice'],'Kore')
        self.assertEqual(self.app.key.get(),'fixture-session-key-long-enough')

    def test_wrong_id_disconnect_and_provider_failure_never_admit_voice(self):
        for event in ({'event':'preview-played','id':999},
            {'event':'preview-failed','id':1,'code':'INTERRUPTED'},
            {'event':'preview-failed','id':1,'code':'AUTH','body':'PRIVATE'}):
            self.app.preview_id=0
            def run(stop, callback, duration): callback({'event':'ready'});callback(event);return 0
            self.factory.return_value.run.side_effect=run
            self.app.start_preview('gemini-3.8-live','Kore');self.finish()
            self.assertNotIn(('gemini-3.8-live','Kore'),self.app.heard)
            self.assertNotIn('PRIVATE',self.app.preview_status.get())

    def test_stop_cancels_dedicated_service_and_blocks_host_start_until_reaped(self):
        entered=threading.Event()
        def run(stop, callback, duration): callback({'event':'ready'});entered.set();stop.wait(3);return 0
        self.factory.return_value.run.side_effect=run
        self.app.start_preview('gemini-3.8-live','Kore');self.assertTrue(entered.wait(2));self.app.pump()
        self.assertIn('端末試聴',self.app.host_status.get())
        self.assertEqual(str(self.app.start_button['state']),'disabled')
        self.app.stop_preview();self.finish()
        self.assertNotIn(('gemini-3.8-live','Kore'),self.app.heard)
        self.assertIn('停止中',self.app.host_status.get())
        self.assertEqual(str(self.app.start_button['state']),'normal')


if __name__=='__main__':unittest.main()
