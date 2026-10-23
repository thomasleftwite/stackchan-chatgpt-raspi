"""Portable-host settings/UI contract tests; no real keys, USB, or API."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from settings import valid_key,valid_model,save_settings,load_settings,VERSION
from network import is_lan
from host_app import runtime_env, HostApp
from build_windows import fresh_stage,OUT

class HostSettingsTest(unittest.TestCase):
    def test_distribution_folder_matches_application_version(self):
        self.assertEqual(OUT.name,f'StackchanHost-{VERSION}-win-x64')

    def test_wifi_failure_identifies_device_network(self):
        text=HostApp.friendly(None, 'Gemini device session exit {"reason":"wifi_failed"}')
        self.assertIn("端末がWi-Fiに接続できません",text)

    def folder(self):
        root=Path(__file__).resolve().parents[1]/'.pio/desktop-tests'
        root.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)
    def test_key_and_model_validation(self):
        self.assertTrue(valid_key('packaging-key-for-test-0123456'))
        self.assertFalse(valid_key('line\nbreak-key-0123456789'))
        self.assertTrue(valid_model('gemini-3.8-live')); self.assertFalse(valid_model('../model'))
    def test_addresses_are_private_ipv4_only(self):
        self.assertTrue(is_lan('192.168.1.20')); self.assertTrue(is_lan('10.1.2.3'))
        for value in ('127.0.0.1','0.0.0.0','8.8.8.8','::1','bad'): self.assertFalse(is_lan(value))
    @unittest.skipUnless(os.name=='nt','DPAPI requires Windows')
    def test_key_is_encrypted_and_can_be_read_by_current_user(self):
        with self.folder() as d:
            path=Path(d)/'settings.json'; key='packaging-test-key-0123456789'
            save_settings(path,model='gemini-3.8-live',port='COM4',host='192.168.1.2',key=key,remember=True)
            self.assertNotIn(key,path.read_text()); self.assertEqual(load_settings(path)['key'],key)
    @unittest.skipUnless(os.name=='nt','DPAPI requires Windows')
    def test_session_only_removes_previously_saved_key(self):
        with self.folder() as d:
            path=Path(d)/'settings.json'; key='packaging-test-key-0123456789'
            for remember in (True,False):
                save_settings(path,model='gemini-3.8-live',port='COM4',host='192.168.1.2',key=key,remember=remember)
            self.assertNotIn(key,path.read_text()); self.assertNotIn('protectedKey',load_settings(path))
    def test_bad_settings_do_not_create_files(self):
        with self.folder() as d:
            path=Path(d)/'settings.json'
            with self.assertRaises(ValueError): save_settings(path,model='../bad',port='',host='')
            self.assertFalse(path.exists())
    def test_child_environment_drops_external_node_injection_and_old_key(self):
        with patch.dict(os.environ,{'NODE_OPTIONS':'--fake','NODE_PATH':'private','GEMINI_API_KEY':'old-key'},clear=False):
            env=runtime_env('packaging-test-key-0123456789')
        self.assertNotIn('NODE_OPTIONS',env); self.assertNotIn('NODE_PATH',env)
        self.assertEqual(env['GEMINI_API_KEY'],'packaging-test-key-0123456789')
    def test_offline_selftest_cannot_use_inherited_key(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'existing-private-value'},clear=False):
            self.assertNotIn('GEMINI_API_KEY',runtime_env())
    def test_rebuild_uses_empty_stage_and_preserves_prior_files_outside_payload(self):
        with self.folder() as d:
            build=Path(d); stage=build/'stage/runtime'; stage.mkdir(parents=True)
            (stage/'prior-recording.raw').write_bytes(b'fixture-only')
            fresh_stage(stage,build)
            self.assertEqual(list(stage.iterdir()),[])
            prior=list((build/'prior-stages').iterdir())
            self.assertEqual(len(prior),1)
            self.assertEqual((prior[0]/'prior-recording.raw').read_bytes(),b'fixture-only')
            (stage/'old-module.js').write_text('fixture-only')
            fresh_stage(stage,build)
            self.assertEqual(list(stage.iterdir()),[])
            self.assertEqual(len(list((build/'prior-stages').iterdir())),2)
    def test_stage_rotation_rejects_paths_outside_named_build_folder(self):
        with self.folder() as d:
            build=Path(d)
            for stage in (build,build.parent/'outside-runtime'):
                with self.assertRaises(ValueError): fresh_stage(stage,build)
            self.assertEqual(list(build.iterdir()),[])

if __name__=='__main__': unittest.main()
