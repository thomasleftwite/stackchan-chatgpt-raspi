"""Only bounded calibration numbers may leave the USB coordinator."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from run_gemini_device import STATUS


class EnrollmentStatusTests(unittest.TestCase):
    def test_calibration_numbers_are_accepted(self):
        self.assertIsNotNone(STATUS.fullmatch('GEM ENROLL CAL rms=1600 threshold=4800 ms=1100 gap=700'))
        self.assertIsNotNone(STATUS.fullmatch('GEM ENROLL CAL NONE'))
        self.assertIsNotNone(STATUS.fullmatch('GEM ENROLL result=NONE'))
        self.assertIsNotNone(STATUS.fullmatch('GEM BUILD enrollment=3'))
        self.assertIsNotNone(STATUS.fullmatch('GEM BUILD enrollment=4'))
        self.assertIsNotNone(STATUS.fullmatch('GEM BUILD enrollment=5'))
        self.assertIsNotNone(STATUS.fullmatch('GEM BUILD enrollment=6'))
        self.assertIsNotNone(STATUS.fullmatch('GEM BUILD enrollment=7'))
        self.assertIsNotNone(STATUS.fullmatch('GEM CAPTURE TIMING NONE'))
        self.assertIsNotNone(STATUS.fullmatch('GEM CAPTURE TIMING prep=1040 gap=700'))
        for step in ('record1', 'record2', 'record3', 'check', 'save', 'retry'):
            self.assertIsNotNone(STATUS.fullmatch('GEM ENROLL STEP ' + step))
        self.assertIsNotNone(STATUS.fullmatch('GEM ENROLL STEP verify'))
        self.assertIsNotNone(STATUS.fullmatch('GEM ENROLL AUDIO samples=9600 voiced=3200 ms=600'))

    def test_wifi_diagnostics_only_accept_fixed_events(self):
        for value in ('GEM PAIR READY','GEM PAIR REQUIRED','GEM LINK TLS','GEM LINK USB'):
            self.assertIsNotNone(STATUS.fullmatch(value))
        for event in ('SETUP','AP_JOIN','AP_LEAVE','AP_STOP'):
            self.assertIsNotNone(STATUS.fullmatch('GEM WIFI '+event))
            self.assertIsNone(STATUS.fullmatch('GEM WIFI '+event+' private-data'))

    def test_extra_text_and_unbounded_values_are_rejected(self):
        for value in ('GEM ENROLL CAL rms=quiet threshold=4800 ms=1100 gap=700',
                      'GEM ENROLL CAL rms=1600 threshold=4800 ms=1100 gap=700 extra=data',
                      'GEM ENROLL CAL rms=160000 threshold=4800 ms=1100 gap=700',
                      'GEM BUILD enrollment=3 extra=data',
                      'GEM ENROLL STEP arbitrary-data',
                      'GEM ENROLL STEP record4',
                      'GEM CAPTURE TIMING prep=1000000 gap=700',
                      'GEM CAPTURE TIMING prep=1000 gap=700 extra=data',
                      'GEM ENROLL AUDIO samples=100000 voiced=3200 ms=600'):
            with self.subTest(value=value):
                self.assertIsNone(STATUS.fullmatch(value))


if __name__ == '__main__':
    unittest.main()
