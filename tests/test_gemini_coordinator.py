"""No device, network, API key or audio. Exercise the real coordinator entry."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_gemini_device as app


class SerialFailure:
    def __init__(self, *args, **kwargs):
        raise app.serial.SerialException('SECRET_DEVICE_PATH SECRET_TOKEN')


class Child:
    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(json.dumps({'event':'ready','preflight':True,'port':12345}) + '\n')
        self.code = None
    def poll(self): return self.code
    def wait(self, timeout=None): self.code = 0; return 0
    def terminate(self): self.code = -15


class CoordinatorTest(unittest.TestCase):
    def test_usb_failure_has_safe_stage_and_cause_in_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / '.pio').mkdir()
            report = root / '.pio/test.json'
            output = io.StringIO()
            with patch.object(app, 'ROOT', root), patch.object(app, 'choose_host', return_value='192.168.1.2'), \
                 patch.object(app.shutil, 'which', return_value='node'), \
                 patch.object(app.subprocess, 'Popen', return_value=Child()), \
                 patch.object(app.serial, 'Serial', SerialFailure), \
                 patch.object(sys, 'stdin', io.StringIO()), \
                 patch.object(sys, 'argv', ['run', '--port', 'COM4', '--report', str(report)]), \
                 contextlib.redirect_stdout(output):
                try:
                    app.main()
                except (ValueError, OSError):
                    pass
            result = json.loads(report.read_text())
            self.assertEqual(result.get('exit', {}).get('reason'), 'serial_error')
            self.assertEqual(result['exit']['stage'], 'serial_open')
            self.assertNotIn('SECRET', output.getvalue() + report.read_text())


class SerialLinesTest(unittest.TestCase):
    def reader(self, chunks):
        class Device:
            in_waiting = 1
            def read(self, size): return next(parts, b'')
        parts = iter(chunks)
        return app.SerialLines(Device())

    def test_burst_uses_bounded_bulk_reads(self):
        class Device:
            def __init__(self): self.data = ((app.READY+'\n')*6).encode(); self.operations = 0
            @property
            def in_waiting(self): return len(self.data)
            def read(self, size):
                self.operations += 1; result,self.data = self.data[:size],self.data[size:]; return result
            def read_until(self, end, size):
                # Model pyserial's existing one-byte read_until implementation.
                result = b''
                while len(result)<size and self.data:
                    result += self.read(1)
                    if result.endswith(end): break
                return result
        d=Device(); r=app.SerialLines(d)
        self.assertEqual([r.read() for _ in range(6)], [app.READY]*6)
        self.assertLessEqual(d.operations, 2)

    def test_timeout_fragments_preserve_one_status(self):
        r = self.reader([b'GEM RESULT PA', b'', b'SS gen=1 input=24000 output=12001 frames=26 ms=2605 played=1\r\n'])
        self.assertEqual(r.read(), '')
        self.assertEqual(r.read(), '')
        line = r.read()
        self.assertTrue(app.STATUS.fullmatch(line))

    def test_oversized_line_does_not_join_next_status(self):
        r = self.reader([b'X'*200]*3 + [b'ignored\n', (app.READY+'\n').encode()])
        for _ in range(4): self.assertEqual(r.read(), '')
        self.assertEqual(r.read(), app.READY)


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): self.now += 0.25; return self.now


class SessionTest(unittest.TestCase):
    def run_case(self, scenario):
        writes = []
        self.last_writes = writes
        class Device:
            def __init__(self, *args, **kwargs):
                self.ready = self.stopping = False
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset_input_buffer(self): pass
            def write(self, data):
                writes.append(data)
                if data == b'GEM STOP\n': self.stopping = True
                if scenario == 'write_error' and data.startswith(b'GEM CONFIG'):
                    raise app.serial.SerialTimeoutException('SECRET_TOKEN')
            in_waiting = 1
            def read(self, size):
                if not self.ready:
                    if scenario == 'no_firmware': return b''
                    self.ready = True; return (app.READY+'\n').encode()
                if self.stopping:
                    if scenario == 'no_stop_reply': return b''
                    return b'GEM PC OFFLINE\n'
                if scenario == 'keyboard_interrupt': raise KeyboardInterrupt()
                if scenario == 'usb_error': raise app.serial.SerialException('ClearCommError failed SECRET_AUDIO')
                return b''
        class Thread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self):
                if self.target.__name__ == 'read_server' or scenario in ('user_stop','stdin_closed'):
                    self.target()
        child = Child()
        if scenario == 'server_exit': child.code = 7
        if scenario == 'bad_event': child.stdout = io.StringIO('[]\n')
        if scenario == 'cleanup_error':
            def failed_wait(timeout=None): child.code = 9; return 9
            child.wait = failed_wait
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / '.pio').mkdir(); report = root / '.pio/test.json'
            output = io.StringIO()
            with patch.object(app,'ROOT',root), patch.object(app,'choose_host',return_value='192.168.1.2'), \
                 patch.object(app.shutil,'which',return_value='node'), \
                 patch.object(app.subprocess,'Popen',return_value=child), \
                 patch.object(app.serial,'Serial',Device), patch.object(app.threading,'Thread',Thread), \
                 patch.object(app.time,'monotonic',Clock()), \
                 patch.object(sys,'stdin',io.StringIO('stop\n' if scenario=='user_stop' else '')), \
                 patch.object(sys,'argv',['run','--port','COM4','--seconds','30','--report',str(report)]), \
                 contextlib.redirect_stdout(output):
                code = app.main()
            data = report.read_text()
            self.assertNotIn('SECRET', data+output.getvalue())
            return code, json.loads(data)['exit']

    def test_deadline_is_success_and_device_stop_is_confirmed(self):
        code, result = self.run_case('deadline')
        self.assertEqual(code, 0); self.assertEqual(result['reason'], 'duration_limit')
        self.assertTrue(result['deviceStopConfirmed'])
    def test_user_stop(self):
        code, result = self.run_case('user_stop')
        self.assertEqual((code,result['reason']), (0,'user_stop'))
    def test_stdin_closed_is_explicit(self):
        code, result = self.run_case('stdin_closed')
        self.assertEqual((code,result['reason']), (0,'stdin_closed'))
    def test_server_exit_notifies_device_before_serial_close(self):
        code, result = self.run_case('server_exit')
        self.assertEqual(code, 1)
        self.assertTrue(any(value == b'GEM STOP\n' for value in self.last_writes), 'device stop notification missing')
        self.assertTrue(result['deviceStopConfirmed'])

    def test_keyboard_interrupt_notifies_device_before_serial_close(self):
        code, result = self.run_case('keyboard_interrupt')
        self.assertEqual((code,result['reason']), (0,'keyboard_interrupt'))
        self.assertTrue(any(value == b'GEM STOP\n' for value in self.last_writes))
        self.assertTrue(result['deviceStopConfirmed'])

    def test_server_exit_is_distinct(self):
        code, result = self.run_case('server_exit')
        self.assertEqual((code,result['reason'],result['serverCode']), (1,'server_exit',7))
    def test_monitor_usb_error(self):
        code, result = self.run_case('usb_error')
        self.assertEqual((code,result['reason'],result['stage']), (1,'serial_error','monitor'))
        self.assertEqual(result['serialDetail'], 'status')
    def test_serial_write_deadline(self):
        code, result = self.run_case('write_error')
        self.assertEqual((code,result['reason'],result['stage']), (1,'serial_error','configure'))
        self.assertEqual(result['serialDetail'], 'timeout')
    def test_no_firmware(self):
        code, result = self.run_case('no_firmware')
        self.assertEqual((code,result['reason']), (1,'firmware_no_response'))
    def test_no_stop_ack_is_not_success(self):
        code, result = self.run_case('no_stop_reply')
        self.assertEqual((code,result['reason']), (1,'device_stop_unconfirmed'))
    def test_nonzero_cleanup_is_not_success(self):
        code, result = self.run_case('cleanup_error')
        self.assertEqual((code,result['reason']), (1,'server_shutdown_error'))
    def test_gui_callback_stop_uses_explicit_runtime_without_console_stdin(self):
        import threading
        stop = threading.Event(); stop.set()
        class Device:
            in_waiting = 1
            def __init__(self,*args,**kwargs): self.stopping=False; self.readied=False
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def reset_input_buffer(self): pass
            def write(self,data):
                if data==b'GEM STOP\n': self.stopping=True
            def read(self,size):
                if self.stopping: return b'GEM PC OFFLINE\n'
                if not self.readied: self.readied=True; return (app.READY+'\n').encode()
                return b''
        messages=[]
        with patch.object(app,'choose_host',return_value='192.168.1.2'), \
             patch.object(app.subprocess,'Popen',return_value=Child()) as spawned, \
             patch.object(app.serial,'Serial',Device), patch.object(sys,'stdin',None), \
             patch.object(app.shutil,'which',side_effect=AssertionError('PATH must not be used')):
            code=app.main(['--port','COM4'],runtime_root=Path('portable'),node_path=Path('portable/node.exe'),
                stop_event=stop,on_status=messages.append,child_env={'GEMINI_MODEL':'gemini-3.8-live'})
        self.assertEqual(code,0)
        self.assertTrue(any('user_stop' in message for message in messages))
        self.assertEqual(spawned.call_args.args[0][0],str(Path('portable/node.exe')))

    def test_invalid_server_event(self):
        code, result = self.run_case('bad_event')
        self.assertEqual((code,result['reason']), (1,'server_not_ready'))


if __name__ == '__main__': unittest.main()
