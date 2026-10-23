"""Private Linux preferences: admission, revision, corruption and atomic writes."""
import copy
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from raspi.voice_settings import VoiceSettings, REVIEW_REASONS, settings_path

MODEL = 'gemini-3.8-live'
REASON = REVIEW_REASONS['approved'][0]


@unittest.skipUnless(os.name == 'posix', 'Linux voice backend and file permissions')
class VoiceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'private/voice-settings.json'
        self.store = VoiceSettings(self.path)

    def approve(self, voice='Kore'):
        self.store.decide(MODEL, voice, True, REASON, heard=True)

    def test_xdg_absolute_and_relative_fallback(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name}):
            self.assertEqual(settings_path(), Path(self.temp.name)/'stackchan-raspi/voice-settings.json')
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
            self.assertEqual(settings_path(), Path.home()/'.config/stackchan-raspi/voice-settings.json')

    def test_only_heard_approved_voices_are_selected_and_survive_restart(self):
        with self.assertRaisesRegex(ValueError, 'JAPANESE_REVIEW_REQUIRED'):
            self.store.decide(MODEL, 'Kore', True, REASON)
        self.assertFalse(self.path.exists())
        with self.assertRaisesRegex(ValueError, 'VOICE_NOT_APPROVED'): self.store.select(MODEL, 'Kore')
        self.approve(); restored = VoiceSettings(self.path)
        self.assertEqual(restored.approved(MODEL), ('Kore',))
        self.assertEqual(restored.selected(MODEL), 'Kore')
        self.assertEqual(restored.approved('gemini-unknown'), ())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(set(json.loads(self.path.read_text())), {'version', 'records', 'selected'})

    def test_exclusion_and_revision_change_invalidate_selection(self):
        self.approve(); catalog = copy.deepcopy(self.store.catalog); catalog['revision'] = 'future-revision'
        changed = VoiceSettings(self.path, catalog=catalog)
        self.assertEqual(changed.approved(MODEL), ()); self.assertEqual(changed.selected(MODEL), '')
        self.store.decide(MODEL, 'Kore', False, REVIEW_REASONS['excluded'][0])
        self.assertEqual(VoiceSettings(self.path).approved(MODEL), ())
        self.assertEqual(VoiceSettings(self.path).selected(MODEL), '')

    def test_corrupt_original_is_preserved_before_explicit_recovery(self):
        self.path.parent.mkdir(mode=0o700); self.path.write_bytes(b'{broken'); self.path.chmod(0o600)
        self.store = VoiceSettings(self.path); self.assertTrue(self.store.load_error)
        with self.assertRaisesRegex(ValueError, 'SETTINGS_RECOVERY_REQUIRED'): self.store.select(MODEL, '')
        self.approve()
        backups = list(self.path.parent.glob('voice-settings.json.invalid-*'))
        self.assertEqual(len(backups), 1); self.assertEqual(backups[0].read_bytes(), b'{broken')
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
        self.assertEqual(VoiceSettings(self.path).selected(MODEL), 'Kore')

    def test_symlink_permissive_files_and_directories_fail_closed(self):
        self.approve(); original = self.path.read_bytes(); target = self.path.with_name('target')
        self.path.rename(target); self.path.symlink_to(target)
        self.store = VoiceSettings(self.path); self.assertTrue(self.store.load_error)
        with self.assertRaises(ValueError): self.approve()
        self.assertEqual(target.read_bytes(), original)
        self.path.unlink(); target.rename(self.path); self.path.chmod(0o644)
        self.store = VoiceSettings(self.path); self.assertTrue(self.store.load_error)
        with self.assertRaises(ValueError): self.approve()
        self.path.chmod(0o600); self.path.parent.chmod(0o755)
        self.assertTrue(VoiceSettings(self.path).load_error)
        with self.assertRaises(ValueError): self.approve()

    def test_atomic_failure_keeps_prior_file_and_in_memory_state(self):
        self.approve(); original = self.path.read_bytes(); state = copy.deepcopy(self.store.data)
        with patch('raspi.voice_settings.os.replace', side_effect=OSError('PRIVATE')):
            with self.assertRaises(OSError): self.store.select(MODEL, '')
        self.assertEqual(self.path.read_bytes(), original); self.assertEqual(self.store.data, state)
        self.assertEqual(list(self.path.parent.glob('.voice-*')), [])

    def test_cli_reads_saved_voice_and_explicit_override_without_api_calls(self):
        from raspi.host import main
        self.approve()
        for extra, expected in [([], 'Kore'), (['--voice', 'Puck'], 'Puck')]:
            service = Mock(); service.run.return_value = 0
            with patch('sys.argv', ['host', '--live']+extra), patch('sys.stdin.isatty', return_value=True), \
                 patch('raspi.host.getpass.getpass', return_value='fixture-session-key-long-enough'), \
                 patch('raspi.key_store.KeyStore.load', return_value='fixture-session-key-long-enough'), \
                 patch('raspi.voice_settings.settings_path', return_value=self.path), \
                 patch('raspi.host.make_service', return_value=service) as factory:
                self.assertEqual(main(), 0)
                self.assertEqual(factory.call_args.kwargs['voice'], expected)

    def test_unknown_fields_and_oversized_data_are_not_loaded_or_overwritten(self):
        self.approve(); data = json.loads(self.path.read_text()); data['apiKey'] = 'not-a-real-key'
        self.path.write_text(json.dumps(data)); self.assertTrue(VoiceSettings(self.path).load_error)
        self.path.write_bytes(b'['*2000+b']'*2000)
        self.assertTrue(VoiceSettings(self.path).load_error)
        self.path.write_bytes(b'x'*65537)
        self.store = VoiceSettings(self.path); self.assertTrue(self.store.load_error)
        with self.assertRaises(ValueError): self.approve()
        self.assertEqual(self.path.stat().st_size, 65537)


if __name__ == '__main__': unittest.main()
