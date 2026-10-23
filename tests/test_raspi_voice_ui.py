"""Actual Tk controls with injected generation/playback and a private temporary store."""
from pathlib import Path
import queue
import tempfile
import threading
import unittest
import os
from unittest.mock import Mock, patch

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
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=self.temp.name, XDG_DATA_HOME=self.temp.name+'/data'))
        self.store = VoiceSettings(Path(self.temp.name)/'voice-settings.json')
        self.pcm = bytearray(b'\x01\x00'*24)
        self.generator = Mock(return_value=self.pcm); self.player = Mock(return_value=True)
        self.factory = Mock()
        self.app = HostWindow(self.root, self.factory, settings=self.store, generator=self.generator, player=self.player)
        self.app.fixture.set(False); self.app.preview_target.set('Pi（ローカル）'); self.app.controls()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.app.close()
        if self.app.preview_worker: self.app.preview_worker.join(3)
        if self.app.worker: self.app.worker.join(3)

    def preview(self):
        self.app.sleep_confirmed.set(True); self.app.key.set('fixture-session-key-long-enough')
        self.app.start_preview(MODEL, 'Kore')
        self.assertEqual(self.app.key.get(), 'fixture-session-key-long-enough')
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
        self.assertEqual(str(self.app.clear_key_button['state']), 'disabled')
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

    def test_review_dialog_is_owned_positioned_and_reused(self):
        import tkinter as tk
        self.root.deiconify(); self.root.geometry('760x760+20+20'); self.root.update_idletasks()
        self.app.review_voices(); self.root.update_idletasks()
        dialogs = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        dialog = dialogs[0]
        self.assertEqual(str(dialog.transient()), str(self.root))
        self.assertGreaterEqual(dialog.winfo_rootx(), 0)
        self.assertLessEqual(dialog.winfo_rootx()+dialog.winfo_width(), self.root.winfo_screenwidth())
        self.app.review_voices()
        self.assertEqual([w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)], dialogs)
        # The registered close command cancels any audition.
        self.root.tk.call(dialog.protocol('WM_DELETE_WINDOW'))
        self.app.review_voices()
        self.assertEqual(len([w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]), 1)

    def test_reopen_moves_existing_dialog_back_inside_screen(self):
        self.root.deiconify(); self.root.geometry('760x760+20+20')
        self.app.review_voices(); self.root.update_idletasks()
        dialog = self.app.review_dialog
        dialog.geometry(f'700x640+{self.root.winfo_screenwidth()+100}+40')
        self.root.update_idletasks(); self.app.review_voices(); self.root.update_idletasks()
        self.assertIs(self.app.review_dialog, dialog)
        self.assertLessEqual(dialog.winfo_rootx()+dialog.winfo_width(), self.root.winfo_screenwidth())

    def test_unheard_adoption_disabled_and_candidate_survives_close_and_reopen(self):
        self.app.review_voices()
        candidate = getattr(self.app, 'preview_candidate', None)
        self.assertIsNotNone(candidate)
        candidate.set('Kore'); self.app.controls()
        self.assertEqual(str(self.app.adopt_button['state']), 'disabled')
        self.root.tk.call(self.app.review_dialog.protocol('WM_DELETE_WINDOW'))
        self.app.review_voices(); self.root.update_idletasks()
        self.assertEqual(self.app.preview_candidate.get(), 'Kore')
        self.preview(); self.app.controls()
        self.assertEqual(str(self.app.adopt_button['state']), 'normal')
        self.app.adopt_button.invoke()
        self.assertEqual(VoiceSettings(self.store.path).selected(MODEL), 'Kore')

    def test_repeated_close_reopen_and_minimized_parent_restore_usable_dialog(self):
        self.root.deiconify(); self.app.review_voices()
        self.app.preview_candidate.set('Kore')
        for _ in range(10):
            self.root.tk.call(self.app.review_dialog.protocol('WM_DELETE_WINDOW'))
            self.app.review_voices(); self.root.update_idletasks()
            self.assertEqual(self.app.preview_candidate.get(), 'Kore')
            self.assertEqual(len([w for w in self.root.winfo_children() if w.winfo_class() == 'Toplevel']), 1)
        self.root.withdraw(); self.app.review_dialog.withdraw()
        self.app.review_voices(); self.root.update_idletasks()
        self.assertEqual(self.root.state(), 'normal')
        self.assertEqual(self.app.review_dialog.state(), 'normal')
        for button in (self.app.prepare_preview_button, self.app.sample_button, self.app.adopt_button):
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),
                self.app.review_dialog.winfo_rooty()+self.app.review_dialog.winfo_height())

    def test_terminal_trigger_instruction_waits_for_device_listening_gate(self):
        self.app.preview_job = (1, MODEL, 'Kore', '端末')
        self.app.preview_event({'internal': 'preview-waiting', 'id': 1})
        self.assertIn('Listening', self.app.preview_status.get())
        self.assertIn('ビープ', self.app.preview_status.get())
        self.assertIn('待', self.app.preview_status.get())
        self.app.preview_job = None

    def test_multiple_adopted_voices_remain_selectable_in_default_fixture_after_restart(self):
        for voice in ('Kore', 'Puck'):
            self.app.sleep_confirmed.set(True); self.app.key.set('fixture-session-key-long-enough')
            self.app.start_preview(MODEL, voice); self.app.preview_worker.join(3); self.app.pump()
            self.app.decide_voice(MODEL, voice, True, REASON)
        import tkinter as tk
        from raspi.host_ui import HostWindow
        root = tk.Tk(); root.withdraw()
        try:
            factory = Mock()
            restored = HostWindow(root, factory, settings=VoiceSettings(self.store.path))
            self.assertTrue(restored.fixture.get())
            self.assertEqual(set(restored.voice_box['values']), {'サービス既定', 'Kore', 'Puck'})
            self.assertEqual(str(restored.voice_box['state']), 'readonly')
            self.assertIn('2件', restored.voice_label.get())
            restored.voice.set('Kore'); restored.choose_voice()
            self.assertEqual(VoiceSettings(self.store.path).selected(MODEL), 'Kore')
            self.assertEqual(set(VoiceSettings(self.store.path).approved(MODEL)), {'Kore', 'Puck'})
            factory.assert_not_called(); restored.close()
        finally: root.destroy()

    def test_fixture_running_cannot_send_voice_change_but_stop_unlocks_choices(self):
        self.store.decide(MODEL, 'Kore', True, REASON, heard=True)
        self.app.refresh_voices(); self.app.fixture.set(True)
        self.app.worker = Mock(); self.app.worker.is_alive.return_value = True
        self.app.controls()
        self.assertEqual(str(self.app.voice_box['state']), 'disabled')
        self.app.voice.set('Kore'); self.app.choose_voice()
        self.assertTrue(self.app.commands.empty())
        self.app.worker = None; self.app.controls()
        self.assertEqual(str(self.app.voice_box['state']), 'readonly')

    def test_dialog_can_prepare_from_running_fixture_without_api_generation(self):
        entered = threading.Event()
        self.factory.return_value.run.side_effect = lambda stop, *_args, **_kwargs: (entered.set(), stop.wait(3))
        self.app.fixture.set(True); self.app.start(); self.assertTrue(entered.wait(1))
        self.app.review_voices()
        button = getattr(self.app, 'prepare_preview_button', None)
        self.assertIsNotNone(button, '試聴画面内にホスト停止・準備の操作が必要')
        button.invoke(); self.app.worker.join(3); self.app.pump()
        self.assertFalse(self.app.running()); self.assertFalse(self.app.fixture.get())
        self.generator.assert_not_called(); self.player.assert_not_called()
        self.app.sleep_confirmed.set(True); self.app.key.set('fixture-session-key-long-enough')
        self.app.start_preview(MODEL, 'Kore'); self.app.preview_worker.join(3); self.app.pump()
        self.app.decide_voice(MODEL, 'Kore', True, REASON)
        self.assertEqual(VoiceSettings(self.store.path).selected(MODEL), 'Kore')

    def test_review_dialog_reuses_masked_key_until_explicit_clear_or_close(self):
        self.app.review_voices()
        entry = getattr(self.app, 'preview_key_box', None)
        self.assertIsNotNone(entry)
        self.assertEqual(str(entry['textvariable']), str(self.app.key))
        self.assertTrue(str(entry['show']))
        entry.insert(0, 'fixture-session-key-long-enough')
        self.app.sleep_confirmed.set(True); self.app.start_preview(MODEL, 'Kore')
        self.app.preview_worker.join(3); self.app.pump()
        self.assertEqual(entry.get(), 'fixture-session-key-long-enough')
        self.assertIn((MODEL, 'Kore'), self.app.heard)
        self.app.start_preview(MODEL, 'Puck'); self.app.preview_worker.join(3); self.app.pump()
        self.assertEqual(self.generator.call_count, 2)
        self.app.clear_key_button.invoke()
        self.assertEqual(entry.get(), '')
        self.assertEqual(self.app.key_box.get(), '')
        self.app.start_preview(MODEL, 'Kore')
        self.assertEqual(self.generator.call_count, 2)
        self.assertEqual(set(self.store.data), {'version', 'records', 'selected'})

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
