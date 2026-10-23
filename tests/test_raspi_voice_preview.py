"""Audition transport and ALSA lifecycle with synthetic processes; no API or speaker."""
import base64
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import os
from unittest.mock import patch

from raspi.voice_preview import decode_audio, generate_sample, play_pcm

KEY = 'fixture-session-key-long-enough'
MODEL = 'gemini-3.8-live'


@unittest.skipUnless(os.name == 'posix', 'Linux voice backend and file permissions')
class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.cancel = threading.Event(); self.children = []
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs); self.children.append(child); return child
        self.record = patch('raspi.voice_preview.subprocess.Popen', side_effect=spawn)
        self.spawn = self.record.start(); self.addCleanup(self.record.stop)

    def executable(self, body, name='node'):
        path = Path(self.temp.name)/name
        source = ('#!'+sys.executable+'\nimport sys,json,time,base64\n'
            'if "--version" in sys.argv:\n print("v22.23.4");sys.exit(0)\n'+body+'\n')
        path.write_text(source); path.chmod(0o700); return path

    def assert_reaped(self):
        self.assertTrue(self.children)
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_decode_checks_request_frame_size_and_failure_redaction(self):
        audio = {'event': 'preview-audio', 'id': 1, 'pcm': base64.b64encode(b'\0\0').decode()}
        self.assertEqual(decode_audio(audio, 1), bytearray(2))
        for event in ({**audio, 'id': True}, {**audio, 'id': 2}, {**audio, 'pcm': '!'},
                      {**audio, 'pcm': ''}, {**audio, 'pcm': 'YQ=='}, {**audio, 'pcm': 'A'*640001}):
            with self.assertRaisesRegex(ValueError, '^INVALID_AUDIO$'): decode_audio(event, 1)
        with self.assertRaisesRegex(ValueError, '^AUTH$'):
            decode_audio({'event': 'preview-failed', 'code': 'AUTH', 'body': 'PRIVATE'}, 1)
        with self.assertRaisesRegex(ValueError, '^TRANSPORT$'):
            decode_audio({'event': 'preview-failed', 'code': ['PRIVATE']}, 1)

    def test_generate_reads_only_bounded_stdout_and_reaps_child(self):
        node = self.executable('r=json.loads(sys.stdin.readline())\nprint(json.dumps({"event":"preview-audio","id":r["id"],"pcm":"AAAAAA=="}))')
        pcm = generate_sample(KEY, MODEL, 'Kore', 7, self.cancel, node=node)
        self.assertEqual(pcm, bytearray(4)); self.assert_reaped()
        self.assertTrue(self.children[-1].stdout.closed)
        options = self.spawn.call_args.kwargs
        self.assertNotIn(KEY, str(self.spawn.call_args.args))
        self.assertNotIn('GEMINI_API_KEY', options['env'])  # Cleared in the parent after spawn.

    def test_generation_overflow_and_provider_body_are_redacted(self):
        for body, expected in [('sys.stdout.write("x"*650001);sys.stdout.flush();time.sleep(60)', 'INVALID_AUDIO'),
            ('sys.stdin.readline();print(json.dumps({"event":"preview-failed","code":"AUTH","body":"PRIVATE"}));sys.exit(1)', 'AUTH')]:
            node = self.executable(body)
            with self.assertRaisesRegex(ValueError, '^'+expected+'$'):
                generate_sample(KEY, MODEL, 'Kore', 1, self.cancel, node=node)
            self.assert_reaped()

    def test_cancel_during_generation_and_deadline_reap_private_process_group(self):
        node = self.executable('sys.stdin.readline();time.sleep(60)')
        timer = threading.Timer(.2, self.cancel.set); timer.start(); self.addCleanup(timer.join)
        with self.assertRaisesRegex(ValueError, '^CANCELLED$'):
            generate_sample(KEY, MODEL, 'Kore', 1, self.cancel, node=node)
        self.assert_reaped(); self.cancel.clear()
        with patch('raspi.voice_preview.time.monotonic', side_effect=[0, 49]):
            with self.assertRaisesRegex(ValueError, '^TIMEOUT$'):
                generate_sample(KEY, MODEL, 'Kore', 1, self.cancel, node=node)
        self.assert_reaped()

    def test_player_uses_exact_pcm_format_and_no_audio_files(self):
        player = self.executable('pcm=sys.stdin.buffer.read();sys.exit(0 if pcm==b"\\0\\0"*240 else 1)', 'aplay')
        with patch('raspi.voice_preview.shutil.which', return_value=str(player)):
            self.assertTrue(play_pcm(bytearray(480), self.cancel))
        command = self.spawn.call_args.args[0]
        self.assertEqual(command[1:], ['-q','-t','raw','-f','S16_LE','-c','1','-r','24000'])
        self.assert_reaped()
        self.assertEqual(sorted(p.name for p in Path(self.temp.name).iterdir()), ['aplay'])

    def test_player_cancellation_and_failed_device_never_report_completion(self):
        player = self.executable('sys.stdin.buffer.read();time.sleep(60)', 'aplay')
        timer = threading.Timer(.15, self.cancel.set); timer.start(); self.addCleanup(timer.join)
        with patch('raspi.voice_preview.shutil.which', return_value=str(player)):
            self.assertFalse(play_pcm(bytearray(480), self.cancel))
        self.assert_reaped(); self.cancel.clear()
        player = self.executable('sys.exit(1)', 'aplay')
        with patch('raspi.voice_preview.shutil.which', return_value=str(player)):
            self.assertFalse(play_pcm(bytearray(480), self.cancel))
        self.assert_reaped()

    def test_stubborn_generator_is_killed_and_reaped_on_cancel(self):
        node = self.executable('import signal\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nsys.stdin.readline();time.sleep(60)')
        timer = threading.Timer(.25, self.cancel.set); timer.start(); self.addCleanup(timer.join)
        with self.assertRaisesRegex(ValueError, '^CANCELLED$'):
            generate_sample(KEY, MODEL, 'Kore', 1, self.cancel, node=node)
        self.assert_reaped(); self.assertEqual(self.children[-1].returncode, -9)

    def test_absent_audio_invalid_pcm_and_pre_cancel_never_spawn(self):
        for pcm in (b'', b'x', b'\0'*480002):
            with self.assertRaisesRegex(ValueError, '^INVALID_AUDIO$'): play_pcm(pcm, self.cancel)
        with patch('raspi.voice_preview.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, '^PC_AUDIO$'): play_pcm(bytearray(2), self.cancel)
        self.cancel.set(); self.assertFalse(play_pcm(bytearray(2), self.cancel))
        with self.assertRaisesRegex(ValueError, '^CANCELLED$'):
            generate_sample(KEY, MODEL, 'Kore', 1, self.cancel)
        self.assertEqual(self.children, [])


if __name__ == '__main__': unittest.main()
