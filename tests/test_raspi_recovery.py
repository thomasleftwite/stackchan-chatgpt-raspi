"""Recovery controller in memory; no real NetworkManager or interface changes."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('ap_recovery', Path(__file__).resolve().parents[1]/'scripts/validate_ap_recovery.py')
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)


class Driver:
    def __init__(self): self.ap = True; self.wired = True; self.checkpoint = False; self.fail_restore = False
    def prepare(self): self.checkpoint = True
    def disconnect(self): self.ap = False
    def restore(self):
        if self.fail_restore: raise ValueError('unavailable')
        self.ap = True
    def check_wired(self):
        if not self.wired: raise ValueError('wired lost')
    def commit(self): self.checkpoint = False
    def rollback(self): self.ap = True; self.checkpoint = False


class RecoveryTests(unittest.TestCase):
    def test_normal_cycle_restores_ap_without_changing_wired(self):
        driver = Driver()
        def pause(_duration): self.assertFalse(driver.ap); self.assertTrue(driver.wired)
        app.cycle(driver, pause)
        self.assertTrue(driver.ap); self.assertTrue(driver.wired); self.assertFalse(driver.checkpoint)

    def test_failure_during_pause_still_restores_ap(self):
        driver = Driver()
        def pause(_duration): raise ValueError('interrupted')
        with self.assertRaises(ValueError): app.cycle(driver, pause)
        self.assertTrue(driver.ap); self.assertTrue(driver.wired)

    def test_failed_explicit_restore_requests_checkpoint_rollback(self):
        driver = Driver(); driver.fail_restore = True
        with self.assertRaises(ValueError): app.cycle(driver, lambda _: None)
        self.assertTrue(driver.ap); self.assertTrue(driver.wired); self.assertFalse(driver.checkpoint)
