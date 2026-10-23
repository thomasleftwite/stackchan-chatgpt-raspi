"""API-free persistence, corruption, filesystem boundaries and GUI/CLI integration."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from raspi.key_store import KeyStore, KeyStoreError

KEY = 'fixture-key-for-encrypted-store-only'
NEW_KEY = 'fixture-replacement-key-for-store-only'


class StoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=str(self.base/'config'), XDG_DATA_HOME=str(self.base/'data')))
        self.store = KeyStore()
        self.cipher = self.store.config/'gemini-key.enc'
        self.master = self.store.data/'key-encryption.key'

    def test_new_process_restore_replace_delete_and_private_ciphertext_only(self):
        self.assertEqual(self.store.load(), '')
        self.store.save(KEY); before = self.cipher.read_bytes()
        for path in (self.cipher, self.master):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn(KEY.encode(), path.read_bytes())
        result = subprocess.run([sys.executable, '-c',
            "from raspi.key_store import KeyStore; assert KeyStore().load() == 'fixture-key-for-encrypted-store-only'"],
            capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout, b''); self.assertEqual(result.stderr, b'')
        self.store.save(KEY); self.assertEqual(self.cipher.read_bytes(), before)
        self.store.save(NEW_KEY); self.assertEqual(KeyStore().load(), NEW_KEY)
        self.assertNotEqual(self.cipher.read_bytes(), before)
        self.store.delete(); self.assertEqual(KeyStore().load(), '')

    def test_corruption_and_missing_master_never_silently_replace(self):
        self.store.save(KEY)
        raw = self.cipher.read_bytes(); broken = raw[:-1]+bytes([raw[-1]^1]); self.cipher.write_bytes(broken)
        for operation in (self.store.load, lambda: self.store.save(NEW_KEY)):
            with self.assertRaisesRegex(KeyStoreError, '^KEY_STORE_UNAVAILABLE$'): operation()
        self.assertEqual(self.cipher.read_bytes(), broken)
        self.store.delete(); self.store.save(KEY); self.master.unlink()
        for operation in (self.store.load, lambda: self.store.save(NEW_KEY)):
            with self.assertRaises(KeyStoreError): operation()
        self.assertFalse(self.master.exists())

    def test_permissions_symlinks_and_hardlinks_are_rejected(self):
        self.store.save(KEY)
        for path in (self.cipher, self.master, self.store.config/'.api-key.lock', self.store.config, self.store.data):
            original = path.stat().st_mode & 0o777
            path.chmod(original | 0o044)
            with self.assertRaises(KeyStoreError): self.store.load()
            path.chmod(original)
        for path in (self.cipher, self.master):
            backup = path.with_suffix('.held'); path.rename(backup); path.symlink_to(backup)
            with self.assertRaises(KeyStoreError): self.store.load()
            with self.assertRaises(KeyStoreError): self.store.save(NEW_KEY)
            path.unlink(); os.link(backup, path)
            with self.assertRaises(KeyStoreError): self.store.load()
            path.unlink(); backup.rename(path)
        self.store.config.rename(self.base/'held'); self.store.config.symlink_to(self.base/'held', target_is_directory=True)
        with self.assertRaises(KeyStoreError): self.store.load()

    def test_atomic_failure_preserves_previous_value_and_cleans_temp(self):
        self.store.save(KEY)
        with patch('raspi.key_store.os.replace', side_effect=OSError('PRIVATE_ERROR')):
            with self.assertRaisesRegex(KeyStoreError, '^KEY_STORE_UNAVAILABLE$'): self.store.save(NEW_KEY)
        self.assertEqual(KeyStore().load(), KEY)
        self.assertEqual(list(self.store.config.glob('.key-write-*')), [])

    def test_invalid_or_oversized_values_do_not_write_and_errors_are_fixed(self):
        for key in ('', 'short', 'a'*257, KEY+'\n', None):
            with self.assertRaisesRegex(KeyStoreError, '^KEY_STORE_UNAVAILABLE$'): self.store.save(key)
        self.assertFalse(self.cipher.exists())
        self.store.save(KEY); self.cipher.write_bytes(b'x'*1025)
        with self.assertRaises(KeyStoreError): self.store.load()

    def test_concurrent_process_updates_leave_valid_ciphertext(self):
        code = "from raspi.key_store import KeyStore; KeyStore().save('fixture-key-for-encrypted-store-only')"
        workers = [subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
        for worker in workers:
            out, err = worker.communicate(timeout=10)
            self.assertEqual(worker.returncode, 0); self.assertEqual(out+err, b'')
        self.assertEqual(KeyStore().load(), KEY)

    def test_cli_uses_saved_key_without_prompt_and_fixture_never_reads_store(self):
        from raspi.host import main
        self.store.save(KEY)
        service = Mock(); service.run.return_value = 0
        with patch.object(sys, 'argv', ['host', '--live']), patch('raspi.host.make_service', return_value=service) as factory, \
                patch('raspi.host.getpass.getpass') as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0); prompt.assert_not_called()
            self.assertEqual(factory.call_args.kwargs['key'], KEY)
        with patch.object(sys, 'argv', ['host', '--fixture']), patch('raspi.host.make_service', return_value=service), \
                patch.object(KeyStore, 'load', side_effect=AssertionError('fixture must not read secrets')):
            self.assertEqual(main(), 0)

    def test_gui_restart_retains_saved_key_close_clears_memory_delete_removes_saved_key(self):
        import tkinter as tk
        from raspi.host_ui import HostWindow
        try: root = tk.Tk()
        except tk.TclError: self.skipTest('Tk display unavailable')
        root.withdraw()
        try:
            app = HostWindow(root); app.key.set(KEY)
            self.assertTrue(app.save_key()); app.close()
            self.assertEqual(app.key.get(), '')
        finally: root.destroy()
        root = tk.Tk(); root.withdraw()
        try:
            app = HostWindow(root); self.assertEqual(app.key.get(), KEY)
            self.assertEqual(str(app.key_box['show']), '●')
            app.clear_key_button.invoke(); self.assertEqual(app.key.get(), '')
            self.assertEqual(KeyStore().load(), '')
            app.fixture.set(False); app.key.set(NEW_KEY)
            app.key_store = Mock(); app.key_store.save.side_effect = OSError('PRIVATE_ERROR')
            app.factory = Mock(); app.start(); app.factory.assert_not_called()
            self.assertNotIn('PRIVATE', app.key_status.get())
            app.close()
        finally: root.destroy()
