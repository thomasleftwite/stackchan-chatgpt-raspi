"""Voice forwarding, GUI lifecycle and event monitor without paid API calls."""
import io
import os
import json
import queue
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch

from raspi.host import HostService, child_environment, public_event, voice_candidates
from raspi.host_network import Endpoint, HostError


class VoiceTests(unittest.TestCase):
    def test_catalog_and_live_environment_use_only_validated_selection(self):
        self.assertIn('Puck', voice_candidates('gemini-3.8-live'))
        self.assertEqual(voice_candidates('gemini-unknown'), ())
        env = child_environment('/fixture/node', False, 'fixture-session-key-long-enough', 'gemini-3.8-live', 'Puck')
        self.assertEqual(env['GEMINI_VOICE'], 'Puck')
        for model, voice in [('gemini-unknown', 'Puck'), ('gemini-3.8-live', '../invalid')]:
            with self.assertRaisesRegex(HostError, '^VOICE_INVALID$'):
                child_environment('/fixture/node', False, 'fixture-session-key-long-enough', model, voice)
        self.assertEqual(set(child_environment('/fixture/node', True, '', 'ignored', 'ignored')), {'PATH'})

    def test_voice_acknowledgement_retains_only_safe_request_id(self):
        self.assertEqual(public_event({'event': 'voice-selected', 'id': 2, 'voice': 'PRIVATE', 'pcm': 'PRIVATE'}),
            {'event': 'voice-selected', 'id': 2})
        for value in (True, 0, -1, 'PRIVATE', 2**53):
            self.assertIsNone(public_event({'event': 'voice-selected', 'id': value}))

    def test_command_queue_forwards_only_voice_commands_after_ready(self):
        service = HostService(Endpoint('10.42.0.1', '10.42.0.0/24'), '/fixture/node',
            fixture=False, key='fixture-session-key-long-enough', voice='Kore')
        child = Mock(); child.pid = 98765; child.poll.return_value = None
        child.stdout = io.StringIO('{"event":"ready"}\n{"event":"voice-selected","id":1,"voice":"Puck"}\n')
        commands = queue.Queue()
        commands.put({'id': 1, 'voice': 'Puck', 'type': 'preview', 'key': 'PRIVATE'})
        commands.put({'id': True, 'voice': 'Puck'})
        commands.put({'id': 3, 'voice': 'invalid'})
        events = []
        with patch('raspi.host.subprocess.Popen', return_value=child), patch('raspi.host.os.killpg'):
            self.assertEqual(service.run(threading.Event(), events.append, .4, commands=commands), 0)
        writes = [json.loads(call.args[0]) for call in child.stdin.write.call_args_list]
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[1], {'type': 'voice', 'id': 1, 'voice': 'Puck'})
        self.assertEqual(events.count({'event': 'voice-failed'}), 2)
        self.assertIn({'event': 'voice-selected', 'id': 1}, events)


class ControlsGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from raspi.host_ui import HostWindow
        try: self.root = tk.Tk()
        except tk.TclError: self.skipTest('Tk display unavailable')
        self.root.withdraw(); self.addCleanup(self.root.destroy)
        self.factory = Mock(); self.entered = threading.Event(); self.now = 100.0
        def run(stop, callback, **kwargs):
            self.entered.set(); callback({'event': 'ready'}); stop.wait(5)
            callback({'event': 'stopped'})
        self.factory.return_value.run.side_effect = run
        from raspi.voice_settings import VoiceSettings, REVIEW_REASONS
        from pathlib import Path
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=temp.name, XDG_DATA_HOME=temp.name+'/data'))
        settings = VoiceSettings(Path(temp.name)/'voice-settings.json')
        for voice in ('Kore', 'Puck'):
            settings.decide('gemini-3.8-live', voice, True, REVIEW_REASONS['approved'][0], heard=True)
        self.app = HostWindow(self.root, self.factory, clock=lambda: self.now, settings=settings)
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.app.close()
        if self.app.worker: self.app.worker.join(3)

    def start_live(self):
        self.app.fixture.set(False); self.app.voice.set('Kore')
        self.app.key.set('fixture-session-key-long-enough'); self.app.start()
        self.assertTrue(self.entered.wait(2)); self.app.pump()

    def test_start_stop_restart_and_close_clear_keys_and_prevent_duplicate_start(self):
        self.start_live(); self.app.start()
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.factory.call_args.kwargs['voice'], 'Kore')
        self.assertEqual(self.app.key.get(), 'fixture-session-key-long-enough')
        self.assertEqual(str(self.app.start_button['state']), 'disabled')
        self.app.request_stop()
        self.assertEqual(str(self.app.stop_button['state']), 'disabled')
        self.assertIn('停止処理中', self.app.host_status.get())
        self.app.worker.join(3); self.app.pump()
        self.assertFalse(self.app.running()); self.assertIn('停止中', self.app.device_status.get())
        self.assertEqual(str(self.app.start_button['state']), 'normal')
        self.entered.clear(); self.app.start()
        self.assertTrue(self.entered.wait(2)); self.app.pump()
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(self.factory.call_args.kwargs['key'], 'fixture-session-key-long-enough')
        self.app.close(); self.app.worker.join(3)
        self.assertFalse(self.app.running())
        self.assertTrue(self.app.stop.is_set()); self.assertEqual(self.app.key.get(), '')

    def test_voice_change_is_queued_and_acknowledged_while_running(self):
        self.start_live(); self.app.voice.set('Puck'); self.app.choose_voice()
        self.assertEqual(self.app.commands.get_nowait(), {'id': 1, 'voice': 'Puck'})
        self.app.handle_event({'event': 'voice-selected', 'id': 1, 'voice': 'PRIVATE'})
        self.assertIn('次の質問', self.app.voice_status.get())
        self.app.model.set('gemini-unknown')
        self.assertEqual(self.app.voice.get(), 'サービス既定')

    def test_monitor_marks_unconfirmed_after_timeout_and_recovers_without_claiming_firmware_state(self):
        self.start_live(); self.assertIn('通信待ち', self.app.device_status.get())
        self.app.handle_event({'event': 'device-online'}); self.app.update_monitor()
        self.assertIn('通信を確認', self.app.device_status.get())
        self.now += 31; self.app.update_monitor()
        self.assertIn('接続は判定できません', self.app.device_status.get())
        self.assertNotIn('切断', self.app.device_status.get())
        self.app.handle_event({'event': 'session-busy'}); self.app.update_monitor()
        self.assertIn('処理中', self.app.session_status.get())
        self.assertIn('通信を確認', self.app.device_status.get())
        self.app.handle_event({'event': 'turn-complete'})
        self.assertIn('音声送信中', self.app.session_status.get())
        self.app.handle_event({'event': 'voice-played'})
        self.assertIn('再生完了', self.app.session_status.get())
        self.app.handle_event({'event': 'session-idle'})
        self.assertIn('待機', self.app.session_status.get())

    def test_failure_survives_stop_and_private_payloads_never_enter_history(self):
        for event in ({'event': 'turn-failed', 'code': 'AUTH', 'message': 'PRIVATE'},
                      {'event': 'preview-audio', 'pcm': 'PRIVATE'},
                      {'event': 'failed', 'message': 'PRIVATE'}, {'event': 'stopped'}, {'event': 'finished'}):
            self.app.handle_event(event)
        self.assertIn('失敗', self.app.status.get())
        self.assertIn('エラー', self.app.host_status.get())
        self.assertNotIn('PRIVATE', self.app.history.get('1.0', 'end'))
        for _ in range(100): self.app.handle_event({'event': 'device-online'})
        self.assertLessEqual(int(self.app.history.index('end-1c').split('.')[0]), 81)


if __name__ == '__main__': unittest.main()
