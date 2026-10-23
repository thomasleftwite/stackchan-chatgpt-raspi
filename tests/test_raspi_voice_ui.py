"""Actual Tk controls with injected generation/playback and a private temporary store."""
from pathlib import Path
import queue
import tempfile
import threading
import unittest
import os
from unittest.mock import Mock

from raspi.voice_settings import VoiceSettings, REVIEW_REASONS

MODEL = 'gemini-3.8-live'
REASON = REVIEW_REASONS['approved'][0]


@unittest.skipUnless(os.name == 'posix', 'Linux voice backend and file permissions')
class VoiceGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from raspi.host_ui import HostWindow
        try: self.root = tk.Tk()
        except tk.TclError: self.skipTest('Tk display unavailable')
        self.root.withdraw(); self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = VoiceSettings(Path(self.temp.name)/'voice-settings.json')
        self.pcm = bytearray(b'\x01\x00'*24)
        self.generator = Mock(return_value=self.pcm); self.player = Mock(return_value=True)
        self.factory = Mock()
        self.app = HostWindow(self.root, self.factory, settings=self.store, generator=self.generator, player=self.player)
        self.app.fixture.set(False); self.app.controls()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.app.close()
        if self.app.preview_worker: self.app.preview_worker.join(3)
        if self.app.worker: self.app.worker.join(3)

    def preview(self):
        self.app.sleep_confirmed.set(True); self.app.key.set('fixture-session-key-long-enough')
        self.app.start_preview(MODEL, 'Kore')
        self.assertEqual(self.app.key.get(), '')
        self.app.preview_worker.join(3); self.app.pump()

    def test_full_audition_adoption_selection_and_restart(self):
        self.assertEqual(tuple(self.app.voice_box['values']), ('サービス既定',))
        self.app.decide_voice(MODEL, 'Kore', True, REASON)
        self.assertFalse(self.store.path.exists())
        self.preview()
        self.assertEqual(self.pcm, bytearray(48))
        self.assertIn((MODEL, 'Kore'), self.app.heard)
        self.app.decide_voice(MODEL, 'Kore', True, REASON)
        self.assertIn('Kore', self.app.voice_box['values'])
        self.assertEqual(self.app.voice.get(), 'Kore')
        self.assertEqual(VoiceSettings(self.store.path).selected(MODEL), 'Kore')
        import tkinter as tk
        from raspi.host_ui import HostWindow
        root2 = tk.Tk(); root2.withdraw()
        try:
            restored = HostWindow(root2, settings=VoiceSettings(self.store.path))
            self.assertEqual(restored.voice.get(), 'Kore')
            restored.close()
        finally: root2.destroy()

    def test_sleep_key_and_host_guards_never_trigger_generation(self):
        self.app.start_preview(MODEL, 'Kore'); self.generator.assert_not_called()
        self.app.sleep_confirmed.set(True)
        self.app.start_preview(MODEL, 'Kore'); self.generator.assert_not_called()
        self.app.key.set('fixture-session-key-long-enough')
        self.app.worker = Mock(); self.app.worker.is_alive.return_value = True
        self.app.start_preview(MODEL, 'Kore'); self.generator.assert_not_called()
        self.app.worker = None
        self.app.fixture.set(True); self.app.start_preview(MODEL, 'Kore')
        self.generator.assert_not_called()

    def test_stop_prevents_adoption_and_waits_before_host_start(self):
        entered = threading.Event()
        def generate(key, model, voice, request_id, cancel):
            entered.set(); cancel.wait(3); raise ValueError('CANCELLED')
        self.generator.side_effect = generate
        self.app.sleep_confirmed.set(True); self.app.key.set('fixture-session-key-long-enough')
        self.app.start_preview(MODEL, 'Kore'); self.assertTrue(entered.wait(2))
        self.app.start(); self.factory.assert_not_called()
        self.assertEqual(str(self.app.start_button['state']), 'disabled')
        self.app.stop_preview(); self.app.preview_worker.join(3); self.app.pump()
        self.assertNotIn((MODEL, 'Kore'), self.app.heard)
        self.player.assert_not_called()
        self.assertEqual(str(self.app.start_button['state']), 'normal')

    def test_failed_player_wipes_audio_and_never_marks_heard(self):
        self.player.return_value = False; self.preview()
        self.assertNotIn((MODEL, 'Kore'), self.app.heard)
        self.assertEqual(self.pcm, bytearray(48)); self.assertIn('音声出力先', self.app.preview_status.get())
        self.app.decide_voice(MODEL, 'Kore', True, REASON)
        self.assertFalse(self.store.path.exists())

    def test_excluding_active_voice_stops_host_and_removes_saved_selection(self):
        self.preview(); self.app.decide_voice(MODEL, 'Kore', True, REASON)
        self.app.worker = Mock(); self.app.worker.is_alive.return_value = True
        self.app.decide_voice(MODEL, 'Kore', False, REVIEW_REASONS['excluded'][0])
        self.assertTrue(self.app.stop.is_set()); self.assertTrue(self.app.stopping)
        self.assertNotIn('Kore', self.app.voice_box['values'])
        self.assertEqual(self.store.selected(MODEL), '')
        self.app.worker = None

    def test_close_cancels_preview_and_drops_private_errors(self):
        self.generator.side_effect = ValueError('PRIVATE_PROVIDER_BODY')
        self.preview(); self.assertNotIn('PRIVATE', self.app.preview_status.get())
        entered = threading.Event()
        def generate(key, model, voice, request_id, cancel):
            entered.set(); cancel.wait(3); raise ValueError('CANCELLED')
        self.generator.side_effect = generate
        self.app.key.set('fixture-session-key-long-enough'); self.app.start_preview(MODEL, 'Kore')
        self.assertTrue(entered.wait(2)); self.app.close(); self.app.preview_worker.join(3)
        self.assertFalse(self.app.preview_worker.is_alive()); self.assertTrue(self.app.preview_cancel.is_set())
        self.assertEqual(self.app.key.get(), '')


if __name__ == '__main__': unittest.main()
