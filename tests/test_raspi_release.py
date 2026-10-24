"""Release install/update/rollback: temporary roots only, no API or user settings."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
import subprocess
from unittest.mock import patch

from raspi.release_install import install, rollback, verify, shortcuts, ReleaseError


class ReleaseInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.prefix = self.root/'application'

    def bundle(self, version):
        bundle = self.root/('bundle-'+version); bundle.mkdir()
        files = {'bin/stackchan-raspi': b'#!/bin/sh\nexit 0\n', 'LICENSE': b'test license\n'}
        records = {}
        for name, raw in files.items():
            path = bundle/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            mode = 0o755 if name.startswith('bin/') else 0o644; path.chmod(mode)
            records[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'mode': mode}
        (bundle/'release-manifest.json').write_text(json.dumps({'schema': 1, 'version': version,
            'platform': 'linux-arm64', 'files': records}))
        return bundle

    def test_install_update_and_rollback_keep_settings_and_previous_release(self):
        private = self.root/'private-settings'; private.mkdir(); (private/'sentinel').write_bytes(b'fixture-private-value')
        first = self.bundle('0.1.0-rc.1'); second = self.bundle('0.1.0-rc.2')
        install(first, self.prefix); self.assertEqual((self.prefix/'current').resolve().name, '0.1.0-rc.1')
        install(second, self.prefix); self.assertEqual((self.prefix/'current').resolve().name, '0.1.0-rc.2')
        rollback(self.prefix); self.assertEqual((self.prefix/'current').resolve().name, '0.1.0-rc.1')
        self.assertEqual((private/'sentinel').read_bytes(), b'fixture-private-value')
        self.assertEqual(list(self.prefix.glob('.stage-*')), [])

    def test_tampering_extra_secret_file_and_symlinks_fail_before_install(self):
        bundle = self.bundle('0.1.0-rc.1')
        (bundle/'LICENSE').write_bytes(b'changed')
        with self.assertRaises(ReleaseError): install(bundle, self.prefix)
        self.assertFalse((self.prefix/'current').exists())
        (bundle/'LICENSE').write_bytes(b'test license\n')
        (bundle/'secrets.json').write_bytes(b'fixture-private-value')
        with self.assertRaises(ReleaseError): verify(bundle)
        (bundle/'secrets.json').unlink(); (bundle/'LICENSE').unlink()
        (bundle/'LICENSE').symlink_to('/etc/passwd')
        with self.assertRaises(ReleaseError): verify(bundle)

    def test_manifest_traversal_and_unsafe_prefix_are_rejected(self):
        bundle = self.bundle('0.1.0-rc.1')
        path = bundle/'release-manifest.json'; manifest = json.loads(path.read_text())
        manifest['files']['../outside'] = manifest['files']['LICENSE']; path.write_text(json.dumps(manifest))
        with self.assertRaises(ReleaseError): verify(bundle)
        path.write_text(json.dumps({**manifest, 'files': {'LICENSE': manifest['files']['LICENSE']}}))
        other = self.root/'other'; other.mkdir(); self.prefix.symlink_to(other, target_is_directory=True)
        with self.assertRaises(ReleaseError): install(bundle, self.prefix)

    def test_existing_version_cannot_be_silently_overwritten(self):
        bundle = self.bundle('0.1.0-rc.1'); install(bundle, self.prefix)
        target = (self.prefix/'current').resolve(); (target/'LICENSE').write_bytes(b'corrupt')
        with self.assertRaises(ReleaseError): install(bundle, self.prefix)

    def test_shortcuts_are_manual_quote_spaces_and_preserve_unmanaged_files(self):
        self.prefix = self.root/'application with spaces'
        bundle = self.bundle('0.1.0-rc.1'); install(bundle, self.prefix)
        applications = self.root/'applications'; bin_directory = self.root/'bin'; desktop = self.root/'Desktop'
        shortcuts(self.prefix, applications, bin_directory, desktop)
        entry = (desktop/'stackchan-raspi.desktop').read_text()
        self.assertIn('Exec="'+str(self.prefix), entry)
        self.assertNotIn('Autostart', entry); self.assertIn('Terminal=false', entry)
        self.assertTrue((bin_directory/'stackchan-raspi').resolve().is_file())
        (applications/'stackchan-raspi.desktop').write_text('unmanaged')
        with self.assertRaises(ReleaseError): shortcuts(self.prefix, applications, bin_directory)
        self.assertEqual((applications/'stackchan-raspi.desktop').read_text(), 'unmanaged')

    def test_diagnostics_never_read_credentials_or_echo_raw_network_errors(self):
        from raspi.diagnostics import main
        output = io.StringIO()
        with patch('raspi.key_store.KeyStore.load', side_effect=AssertionError('must not read')) as private, \
                patch('raspi.host.resolve_node', return_value=Path('/fixture/node')), \
                patch('raspi.diagnostics.subprocess.run', return_value=subprocess.CompletedProcess([], 1, 'PRIVATE_NETWORK_BODY', 'PRIVATE_NETWORK_BODY')), \
                patch('raspi.host_network.discover_ap', side_effect=ValueError('PRIVATE_NETWORK_BODY')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main(network=True), 1)
            private.assert_not_called()
        self.assertNotIn('PRIVATE', output.getvalue())
        self.assertIn('DEDICATED_AP: FAIL', output.getvalue())
        self.assertIn('WIRED_DEFAULT_ONLY: FAIL', output.getvalue())

    def test_generated_launcher_runs_through_user_bin_symlink(self):
        from raspi.release_build import LAUNCHER
        app = self.root/'app with spaces'; (app/'bin').mkdir(parents=True); (app/'raspi').mkdir()
        (app/'raspi/launcher.py').write_text('print("LAUNCH_PASS")\n')
        executable = app/'bin/stackchan-raspi'; executable.write_text(LAUNCHER); executable.chmod(0o755)
        user_bin = self.root/'user-bin'; user_bin.mkdir()
        link = user_bin/'stackchan-raspi'; link.symlink_to(executable)
        result = subprocess.run([str(link)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'LAUNCH_PASS')


if __name__ == '__main__': unittest.main()
