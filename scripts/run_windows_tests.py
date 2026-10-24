"""Windows product/portable regressions; excludes Pi-only process and fcntl modules."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tests'))
SUITES = ('test_desktop_host', 'test_enrollment_status', 'test_gemini_coordinator',
          'test_voice_features', 'test_wireless_host')

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromNames(SUITES)
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
