#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "bin" / "mana_coordinator"

class CoordinatorWrapperTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mana-coordinator-test-")
        self.root = Path(self.temp.name)
        self.fake_bin = self.root / "fake-mana" / "bin"
        self.fake_bin.mkdir(parents=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.capture = self.root / "args.txt"
        shutil.copy2(WRAPPER, self.fake_bin / "mana_coordinator")
        os.chmod(self.fake_bin / "mana_coordinator", 0o755)
        fake = self.fake_bin / "dmtcp_coordinator"
        fake.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$@" > "$MANA_TEST_CAPTURE"\n'
            'previous=""\nstatus_file=""\n'
            'for argument in "$@"; do\n'
            '  if [ "$previous" = "--status-file" ]; then status_file="$argument"; fi\n'
            '  previous="$argument"\n'
            'done\n'
            'if [ -n "$status_file" ]; then printf "Host: localhost\\nPort: 7780\\n" > "$status_file"; fi\n'
            'exit 0\n', encoding="utf-8")
        os.chmod(fake, 0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_wrapper(self, *args):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["MANA_TEST_CAPTURE"] = str(self.capture)
        env.pop("SLURM_JOB_ID", None)
        result = subprocess.run([str(self.fake_bin / "mana_coordinator"), *args], env=env, text=True, capture_output=True, check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.capture.read_text(encoding="utf-8").splitlines()

    def test_default_includes_exit_on_last(self):
        self.assertIn("--exit-on-last", self.run_wrapper())

    def test_persistent_omits_exit_on_last(self):
        self.assertNotIn("--exit-on-last", self.run_wrapper("--persistent"))

    def test_options_preserved(self):
        args = self.run_wrapper("--persistent", "--port", "7780", "--interval", "0")
        for item in ("--port", "7780", "--interval", "0"):
            self.assertIn(item, args)

    def test_status_file_created(self):
        self.run_wrapper("--persistent")
        rc = self.home / ".mana.rc"
        self.assertTrue(rc.is_file())
        self.assertIn("Host: localhost", rc.read_text(encoding="utf-8"))

    def test_option_with_spaces(self):
        path = str(self.root / "checkpoint files")
        args = self.run_wrapper("--persistent", "--ckptdir", path)
        self.assertEqual(args[args.index("--ckptdir") + 1], path)

    def test_waits_for_daemon_status(self):
        fake = self.fake_bin / "dmtcp_coordinator"
        contents = fake.read_text()
        contents = contents.replace(
            'if [ -n "$status_file" ]; then printf',
            'if [ -n "$status_file" ]; then (sleep 0.2; printf'
        ).replace('> "$status_file"; fi', '> "$status_file") >/dev/null 2>&1 & fi')
        fake.write_text(contents)
        self.run_wrapper("--persistent")
        self.assertIn("Port: 7780", (self.home / ".mana.rc").read_text())

if __name__ == "__main__":
    unittest.main()
