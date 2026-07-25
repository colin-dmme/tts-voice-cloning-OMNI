from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

from omni_tts_core.engines.subprocess_tools import run_worker_process


class SubprocessToolsTest(unittest.TestCase):
    def test_supervisor_can_suspend_and_resume_worker(self) -> None:
        controls = []

        def supervise(control) -> None:
            if controls:
                return
            controls.append(control)
            control.suspend()
            time.sleep(0.1)
            control.resume()

        with tempfile.TemporaryDirectory() as temp:
            completed = run_worker_process(
                [sys.executable, "-c", "import time; time.sleep(0.5); print('ok')"],
                cwd=temp,
                env=os.environ,
                timeout=2.0,
                cancel_event=None,
                supervisor_callback=supervise,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "ok")
        self.assertEqual(len(controls), 1)
        self.assertGreaterEqual(controls[0].total_suspended_seconds, 0.08)


if __name__ == "__main__":
    unittest.main()
