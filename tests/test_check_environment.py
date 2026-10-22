import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "check_environment", Path(__file__).parents[1] / "scripts/check_environment.py"
)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class EnvironmentTests(unittest.TestCase):
    def test_missing_tool(self):
        with patch.object(preflight.shutil, "which", return_value=None):
            self.assertEqual(preflight.check_tool("node"), (False, "node: MISSING"))

    def test_node_version_boundary(self):
        for version, expected in (("22.8.0", False), ("22.9.0", True), ("24.0.0", True)):
            with self.subTest(version=version), \
                 patch.object(preflight.shutil, "which", return_value="/bin/node"), \
                 patch.object(preflight.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 0, "v" + version, "")):
                self.assertEqual(preflight.check_tool("node", (22, 9, 0))[0], expected)

    def test_failure_does_not_disclose_output(self):
        for result in (subprocess.CompletedProcess([], 1, "private-value", "private-value"),
                       subprocess.CompletedProcess([], 0, "private-value", "")):
            with patch.object(preflight.shutil, "which", return_value="/bin/node"), \
                 patch.object(preflight.subprocess, "run", return_value=result):
                self.assertEqual(preflight.check_tool("node"),
                                 (False, "node: version check failed"))

    def test_timeout(self):
        with patch.object(preflight.shutil, "which", return_value="/bin/node"), \
             patch.object(preflight.subprocess, "run", side_effect=
                          subprocess.TimeoutExpired("node", 10)):
            self.assertFalse(preflight.check_tool("node")[0])


if __name__ == "__main__":
    unittest.main()
