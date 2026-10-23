"""Linux host tests: no provider connection, real child only in fixture mode."""
import io
import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import threading
import unittest
import urllib.request
from unittest.mock import Mock, patch

from raspi.host import HostService, child_environment, main, public_event, resolve_node, ROOT
from raspi.host_network import Endpoint, HostError, discover_ap, parse_ap


class ApDiscoveryTests(unittest.TestCase):
    def addresses(self, address='10.42.0.1', prefix=24):
        return [{'addr_info': [{'family': 'inet', 'local': address, 'prefixlen': prefix}]}]

    def test_ap_returns_its_address_and_actual_subnet(self):
        self.assertEqual(parse_ap('ap', 'shared', self.addresses()), Endpoint('10.42.0.1', '10.42.0.0/24'))

    def test_upstream_public_loopback_broad_and_ambiguous_addresses_are_rejected(self):
        for mode, method, addresses in [
            ('infrastructure', 'auto', self.addresses()), ('ap', 'manual', self.addresses()),
            ('ap', 'shared', self.addresses('8.8.8.8')), ('ap', 'shared', self.addresses('127.0.0.1', 32)),
            ('ap', 'shared', self.addresses(prefix=8)), ('ap', 'shared', self.addresses('10.42.0.0')),
            ('ap', 'shared', self.addresses('10.42.0.255')), ('ap', 'shared', self.addresses()*2),
        ]:
            with self.subTest(mode=mode, method=method), self.assertRaises(HostError):
                parse_ap(mode, method, addresses)

    def test_discovery_failure_does_not_disclose_command_output(self):
        with patch('raspi.host_network.subprocess.run', return_value=subprocess.CompletedProcess([], 1, 'PRIVATE_BODY', 'PRIVATE_BODY')):
            with self.assertRaisesRegex(HostError, '^AP_REQUIRED$'): discover_ap()


class HostUnitTests(unittest.TestCase):
    def test_failure_classification_survives_without_provider_text(self):
        self.assertEqual(public_event({'event':'turn-failed', 'code':'QUOTA', 'status':429, 'message':'PRIVATE_BODY'}),
            {'event':'turn-failed', 'code':'QUOTA', 'status':429})
        self.assertEqual(public_event({'event':'turn-failed', 'code':'PRIVATE_BODY', 'status':True}), {'event':'turn-failed'})
        self.assertIsNone(public_event({'event': ['PRIVATE_BODY']}))

    def test_fixture_ignores_inherited_keys_config_and_node_injection(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'PRIVATE_BODY', 'NODE_OPTIONS': 'PRIVATE_BODY', 'NODE_PATH': 'PRIVATE_BODY'}):
            self.assertEqual(set(child_environment('/fixture/node', True, '', 'ignored')), {'PATH'})

    def test_live_requires_explicit_valid_key_and_model(self):
        with self.assertRaisesRegex(HostError, '^KEY_REQUIRED$'):
            child_environment('/fixture/node', False, '', 'gemini-3.8-live')
        with self.assertRaisesRegex(HostError, '^MODEL_INVALID$'):
            child_environment('/fixture/node', False, 'fixture-session-key-long-enough', '../bad')
        env = child_environment('/fixture/node', False, 'fixture-session-key-long-enough', 'gemini-3.8-live')
        self.assertEqual(set(env), {'PATH', 'GEMINI_API_KEY', 'GEMINI_MODEL'})

    def test_node_version_boundary_and_private_output(self):
        for output, ok in [('v22.8.0', False), ('v22.9.0', True), ('v24.0.0', True), ('PRIVATE_BODY', False)]:
            with patch('raspi.host.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                if ok: self.assertIsInstance(resolve_node('/fixture/node'), Path)
                else:
                    with self.assertRaisesRegex(HostError, '^NODE_REQUIRED$'): resolve_node('/fixture/node')

    def test_pre_cancelled_start_does_not_spawn(self):
        service = HostService(Endpoint('127.0.0.1', '127.0.0.1/32'), '/fixture/node')
        stop = threading.Event(); stop.set()
        with patch('raspi.host.subprocess.Popen') as spawn:
            self.assertEqual(service.run(stop, lambda _: None), 0); spawn.assert_not_called()

    def test_stop_escalates_only_its_own_process_group_and_clears_key(self):
        service = HostService(Endpoint('10.42.0.1', '10.42.0.0/24'), '/fixture/node', key='fixture-session-key-long-enough')
        child = Mock(); child.pid = 98765; child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired([], 5), subprocess.TimeoutExpired([], 5), 0]
        service.child = child
        with patch('raspi.host.os.killpg') as kill:
            service._stop()
            self.assertTrue(all(call.args[0] == 98765 for call in kill.call_args_list))
            self.assertIn((98765, signal.SIGTERM), [call.args for call in kill.call_args_list])
            self.assertIn((98765, signal.SIGKILL), [call.args for call in kill.call_args_list])
        self.assertEqual(service.key, '')

    def test_events_drop_provider_fields_and_raw_pcm(self):
        service = HostService(Endpoint('127.0.0.1', '127.0.0.1/32'), '/fixture/node')
        child = Mock(); child.pid = 98765; child.poll.return_value = None
        child.stdout = io.StringIO('{"event":"ready","apiKey":"PRIVATE_BODY"}\n'
            '{"event":"turn-failed","pcm":"PRIVATE_BODY","message":"PRIVATE_BODY"}\n')
        events = []
        with patch('raspi.host.subprocess.Popen', return_value=child), patch('raspi.host.os.killpg'):
            self.assertEqual(service.run(threading.Event(), events.append, duration=.1), 0)
        self.assertEqual(events, [{'event':'ready'}, {'event':'turn-failed'}, {'event':'stopped'}])

    @unittest.skipIf(sys.platform == 'win32', 'Linux signal handling')
    def test_cli_sigterm_sets_stop_and_restores_previous_handler(self):
        old = signal.getsignal(signal.SIGTERM); service = Mock()
        def run(stop, callback, duration):
            signal.raise_signal(signal.SIGTERM); self.assertTrue(stop.is_set()); return 0
        service.run.side_effect = run
        with patch('sys.argv', ['host', '--fixture']), patch('raspi.host.make_service', return_value=service):
            self.assertEqual(main(), 0)
        self.assertEqual(signal.getsignal(signal.SIGTERM), old)

    def test_key_prompt_can_be_cancelled_before_starting_service(self):
        with patch('sys.argv', ['host', '--live']), patch('raspi.host.getpass.getpass', side_effect=KeyboardInterrupt), \
             patch('sys.stdin.isatty', return_value=True), patch('raspi.host.make_service') as factory:
            self.assertEqual(main(), 130); factory.assert_not_called()

    def test_live_refuses_non_terminal_key_input(self):
        with patch('sys.argv', ['host', '--live']), patch('sys.stdin.isatty', return_value=False), \
             patch('raspi.host.getpass.getpass') as prompt, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(), 1); prompt.assert_not_called()


@unittest.skipIf(sys.platform == 'win32', 'Linux process groups')
class HostProcessTests(unittest.TestCase):
    def test_real_child_stops_and_can_restart_on_same_port(self):
        try: node = resolve_node()
        except HostError: self.skipTest('Node >=22.9.0 not installed')
        if not (ROOT/'server/dist/wireless-host.js').is_file(): self.skipTest('Build server first')
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0)); port = reserved.getsockname()[1]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(2):
            service = HostService(Endpoint('127.0.0.1', '127.0.0.1/32'), node, port=port)
            stop = threading.Event(); events = queue.Queue(); result = []
            def run():
                try: result.append(service.run(stop, events.put))
                except Exception as error: result.append(type(error).__name__)
            worker = threading.Thread(target=run); worker.start()
            try:
                self.assertEqual(events.get(timeout=10), {'event':'ready'})
                with opener.open(f'http://127.0.0.1:{port}/healthz', timeout=3) as response:
                    self.assertEqual(response.status, 200)
            finally:
                stop.set(); worker.join(timeout=18)
                if worker.is_alive(): service._stop(); worker.join(timeout=3)
            self.assertFalse(worker.is_alive()); self.assertEqual(result, [0])
            self.assertEqual(service.child.returncode, 0)


class HostGuiTests(unittest.TestCase):
    def test_default_is_offline_and_key_is_cleared_before_start(self):
        import tkinter as tk
        from raspi.host_ui import HostWindow
        try: root = tk.Tk()
        except tk.TclError: self.skipTest('Tk display unavailable')
        root.withdraw(); factory = Mock(); entered = threading.Event()
        def run(stop, callback): entered.set(); stop.wait(2)
        factory.return_value.run.side_effect = run
        try:
            app = HostWindow(root, factory)
            self.assertTrue(app.fixture.get())
            app.fixture.set(False); app.key.set('fixture-session-key-long-enough'); app.start()
            self.assertTrue(entered.wait(2)); self.assertEqual(app.key.get(), '')
            self.assertEqual(factory.call_args.kwargs['key'], 'fixture-session-key-long-enough')
            app.close(); app.worker.join(timeout=3)
            self.assertFalse(app.worker.is_alive())
        finally: root.destroy()
