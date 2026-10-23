"""Offline tests for device setup and restoration; no real credentials or Wi-Fi."""
import io
import json
import subprocess
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from raspi.provision import Credentials, ProvisionError, WifiManagerPortal, provision, main
from raspi.provision_network import NetworkManagerSetup

TARGET = Credentials('fixture-host', 'fixture-host-password')
SETUP = Credentials('fixture-device', 'fixture-device-password')
FORM = b"<form method='POST' action='/wifisave'><input name='s'><input name='p'></form>"


class Response(io.BytesIO):
    status = 200


class ProvisionTests(unittest.TestCase):
    def network(self):
        network = Mock(); network.prepare.return_value = TARGET
        return network

    def test_success_restores_ap_after_post(self):
        network = self.network(); portal = Mock(); calls = Mock()
        calls.attach_mock(network, 'network'); calls.attach_mock(portal, 'portal')
        result = provision(network, SETUP, portal)
        self.assertEqual(result, {'event': 'complete', 'saved': True, 'apRestored': True})
        self.assertEqual([call[0] for call in calls.mock_calls],
            ['network.prepare', 'network.connect_setup', 'network.check_setup_route', 'portal.save', 'network.restore_ap'])

    def test_connect_route_and_save_failures_all_restore_ap(self):
        for stage in ('connect_setup', 'check_setup_route', 'save'):
            with self.subTest(stage=stage):
                network = self.network(); portal = Mock()
                getattr(portal if stage == 'save' else network, stage).side_effect = OSError('PRIVATE_BODY')
                with self.assertRaisesRegex(ProvisionError, '^SETUP_FAILED$'):
                    provision(network, SETUP, portal)
                network.restore_ap.assert_called_once()
                if stage != 'save': portal.save.assert_not_called()

    def test_unavailable_wired_route_prevents_switch_or_post(self):
        network = self.network(); network.prepare.side_effect = ProvisionError('WIRED_REQUIRED'); portal = Mock()
        with self.assertRaisesRegex(ProvisionError, '^WIRED_REQUIRED$'):
            provision(network, SETUP, portal)
        network.connect_setup.assert_not_called(); portal.save.assert_not_called()
        network.restore_ap.assert_not_called()

    def test_restore_failure_is_reported_even_after_successful_save(self):
        network = self.network(); network.restore_ap.side_effect = ProvisionError('AP_RESTORE_FAILED')
        with self.assertRaisesRegex(ProvisionError, '^AP_RESTORE_FAILED$'):
            provision(network, SETUP, Mock())

    def test_invalid_credentials_do_not_touch_network(self):
        for credentials in (Credentials('', 'fixture-password'), Credentials('x', 'short'), Credentials('x\n', 'fixture-password')):
            network = self.network()
            with self.assertRaises(ProvisionError): provision(network, credentials, Mock())
            network.prepare.assert_not_called()

    def test_helper_errors_do_not_disclose_input_or_provider_messages(self):
        with patch('sys.argv', ['provision', '--execute-stdin']), \
             patch('sys.stdin', io.StringIO(json.dumps({'ssid': SETUP.ssid, 'password': SETUP.password}))), \
             patch('raspi.provision_network.NetworkManagerSetup', side_effect=RuntimeError('PRIVATE_BODY')), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(main(), 1)
            self.assertEqual(json.loads(output.getvalue()), {'event': 'failed', 'code': 'SETUP_FAILED'})
        self.assertNotIn(SETUP.password, repr(SETUP))


class PortalTests(unittest.TestCase):
    def test_legacy_relative_save_action_uses_fixed_post_endpoint(self):
        opener = Mock(); opener.open.side_effect = [Response(FORM.replace(b'/wifisave', b'wifisave')), Response(b'saved')]
        WifiManagerPortal(opener).save(TARGET)
        self.assertEqual(opener.open.call_args_list[1].args[0].full_url, 'http://192.168.4.1/wifisave')

    def test_credentials_only_in_post_body_to_fixed_save_path(self):
        opener = Mock(); opener.open.side_effect = [Response(FORM), Response(b'saved')]
        WifiManagerPortal(opener).save(TARGET)
        self.assertEqual(opener.open.call_args_list[0].args[0], 'http://192.168.4.1/0wifi')
        request = opener.open.call_args_list[1].args[0]
        self.assertEqual(request.full_url, 'http://192.168.4.1/wifisave')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(parse_qs(request.data.decode()), {'s': [TARGET.ssid], 'p': [TARGET.password]})
        self.assertNotIn(TARGET.password, request.full_url)

    def test_unexpected_or_oversized_form_never_sends_credentials(self):
        for page in (b'<form action="https://example.invalid/wifisave"><input name="s"><input name="p"></form>', b'x' * 65537, b'<html>wrong page</html>'):
            opener = Mock(); opener.open.return_value = Response(page)
            with self.assertRaises(ProvisionError): WifiManagerPortal(opener).save(TARGET)
            self.assertEqual(opener.open.call_count, 1)

    def test_transport_error_is_redacted(self):
        opener = Mock(); opener.open.side_effect = OSError('PRIVATE_BODY')
        with self.assertRaisesRegex(ProvisionError, '^PORTAL_REQUEST_FAILED$'):
            WifiManagerPortal(opener).save(TARGET)

    def test_default_opener_disables_proxies_and_redirects(self):
        opener = WifiManagerPortal().opener
        self.assertFalse(any(getattr(handler, 'proxies', {}) for handler in opener.handlers))
        handler = next(handler for handler in opener.handlers if hasattr(handler, 'redirect_request'))
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'http://example.invalid/'))


class NetworkTests(unittest.TestCase):
    def network(self):
        value = NetworkManagerSetup.__new__(NetworkManagerSetup)
        value.manager = Mock(); value.settings = Mock(); value.temporary = None
        value.device = '/device'; value.original = '/ap'; value.original_uuid = 'original-id'; value.checkpoint = '/checkpoint'
        value._run = Mock(); value._wait = Mock(); value._wired = Mock(); value._connection = Mock()
        class DBus:
            Boolean = staticmethod(bool); ByteArray = staticmethod(bytes)
            @staticmethod
            def Dictionary(value, signature): return value
        value.dbus = DBus
        return value

    def test_prepare_checkpoints_only_wifi_without_global_connection_deletion(self):
        network = self.network(); network._run.return_value = 'original-id'
        network.settings.ListConnections.return_value = ['/ap']
        network._connection.return_value.GetSettings.return_value = {
            'connection': {'uuid': 'original-id'}, '802-11-wireless': {'mode': 'ap', 'ssid': TARGET.ssid.encode()}}
        network._connection.return_value.GetSecrets.return_value = {
            '802-11-wireless-security': {'psk': TARGET.password}}
        network.manager.GetDeviceByIpIface.return_value = '/device'
        self.assertEqual(network.prepare().ssid, TARGET.ssid)
        network.manager.CheckpointCreate.assert_called_once_with(['/device'], 180, 0)

    def test_setup_profile_is_unsaved_and_cannot_be_default_or_dns(self):
        network = self.network(); network.connect_setup(SETUP)
        profile = network.settings.AddConnectionUnsaved.call_args.args[0]
        self.assertFalse(profile['connection']['autoconnect'])
        self.assertTrue(profile['ipv4']['never-default']); self.assertTrue(profile['ipv4']['ignore-auto-dns'])
        self.assertEqual(profile['ipv6']['method'], 'disabled')
        network.settings.AddConnection.assert_not_called()

    def test_wrong_interface_route_blocks_secret_submission(self):
        network = self.network(); network._run.return_value = '[{"dev":"eth0"}]'
        with self.assertRaisesRegex(ProvisionError, '^SETUP_ROUTE_FAILED$'): network.check_setup_route()

    def test_restore_failure_requests_checkpoint_rollback(self):
        network = self.network(); network.temporary = '/temporary'
        network.manager.ActivateConnection.side_effect = OSError('PRIVATE_BODY')
        with self.assertRaisesRegex(ProvisionError, '^AP_RESTORE_FAILED$'): network.restore_ap()
        network._connection.return_value.Delete.assert_called_once()
        network.manager.CheckpointRollback.assert_called_once_with('/checkpoint')

    def test_restore_deletes_temporary_profile_and_verifies_wired_before_commit(self):
        network = self.network(); network.temporary = '/temporary'; network.restore_ap()
        network.manager.ActivateConnection.assert_called_once_with('/ap', '/device', '/')
        network._connection.assert_called_once_with('/temporary')
        network._connection.return_value.Delete.assert_called_once()
        network._wired.assert_called_once()
        network.manager.CheckpointDestroy.assert_called_once_with('/checkpoint')


class SetupUiTests(unittest.TestCase):
    def test_setup_button_passes_secret_only_over_stdin_and_clears_entry(self):
        import tkinter as tk
        from tkinter import ttk
        from raspi import provision_ui
        try: root = tk.Tk()
        except tk.TclError: self.skipTest('Tk display unavailable')
        root.withdraw()
        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)
        def interact():
            entries = [widget for widget in widgets(root) if isinstance(widget, ttk.Entry)]
            entries[0].delete(0, 'end'); entries[0].insert(0, SETUP.ssid)
            entries[1].insert(0, SETUP.password)
            button = next(widget for widget in widgets(root) if isinstance(widget, ttk.Button))
            button.invoke()
            deadline = time.monotonic() + 3
            while button.instate(['disabled']) and time.monotonic() < deadline:
                root.update(); time.sleep(.01)
            self.assertFalse(button.instate(['disabled']))
            self.assertEqual(entries[1].get(), '')
        result = subprocess.CompletedProcess([], 0, '{"event":"complete"}', '')
        try:
            with patch.object(provision_ui.tk, 'Tk', return_value=root), \
                 patch.object(root, 'mainloop', side_effect=interact), \
                 patch.object(provision_ui.subprocess, 'run', return_value=result) as run:
                provision_ui.main()
                self.assertNotIn(SETUP.password, ' '.join(run.call_args.args[0]))
                self.assertEqual(json.loads(run.call_args.kwargs['input']),
                    {'ssid': SETUP.ssid, 'password': SETUP.password})
        finally: root.destroy()
