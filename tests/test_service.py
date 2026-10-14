"""Service loop: wait for the device at login, reconnect after an unplug.

unittest-style; connect/present are fakes, so no hardware is needed.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestDeviceLoop(unittest.TestCase):
    """main.run_device_loop: unplugged at boot, unplug/replug, no-wait exit."""

    def _run(self, connect_plan, present_plan, wait):
        import threading
        from macro.main import run_device_loop
        from midifighter.ports import DeviceNotFoundError
        stop = threading.Event()
        log, calls = [], {"connect": 0, "disconnect": 0}

        def connect():
            calls["connect"] += 1
            ok = connect_plan.pop(0) if connect_plan else True
            if not ok:
                raise DeviceNotFoundError("not here")
            return object(), None

        def present():
            ok = present_plan.pop(0) if present_plan else True
            if not present_plan and not connect_plan:
                stop.set()
            return ok

        def disconnect(_device, _leds, gone):
            calls["disconnect"] += 1

        code = run_device_loop(connect, disconnect, present, wait=wait,
                               stop=stop, poll=0.001, log=log.append)
        return code, calls, log

    def test_waits_for_device_at_boot(self):
        code, calls, log = self._run([False, False, True], [True], wait=True)
        self.assertEqual(code, 0)
        self.assertEqual(calls["connect"], 3)
        self.assertEqual(log.count("[device] not plugged in; waiting"), 1)
        self.assertIn("[device] connected", log)

    def test_reconnects_after_unplug(self):
        code, calls, log = self._run([True, True], [False, True], wait=True)
        self.assertEqual(code, 0)
        self.assertEqual(calls["connect"], 2)
        self.assertIn("[device] unplugged", log)

    def test_without_wait_a_missing_device_exits_1(self):
        code, calls, _ = self._run([False], [], wait=False)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
