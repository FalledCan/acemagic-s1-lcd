import unittest
from unittest.mock import Mock, patch

import usb.core
from lcd import BUFFER_SIZE, INTERFACE, S1LCD


class InitTests(unittest.TestCase):
    def setUp(self):
        self.dev = Mock()
        self.dev.is_kernel_driver_active.return_value = False
        self.dev.write.return_value = BUFFER_SIZE
        for name, kwargs in (
            ("core.find", {"return_value": self.dev}),
            ("util.claim_interface", {}),
            ("util.dispose_resources", {}),
        ):
            mock = self.enterContext(patch(f"lcd.usb.{name}", **kwargs))
            setattr(self, name.split(".")[-1], mock)
        self.enterContext(patch("lcd.time.sleep"))

    def test_success(self):
        self.assertIs(S1LCD().dev, self.dev)
        self.claim_interface.assert_called_once_with(self.dev, INTERFACE)
        self.dispose_resources.assert_not_called()

    def test_exception_after_claim(self):
        with patch.object(S1LCD, "set_orientation", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                S1LCD()
        self.dispose_resources.assert_called_once_with(self.dev)

    def test_orientation_write(self):
        self.dev.write.side_effect = usb.core.USBError("orientation failed")
        with self.assertRaises(usb.core.USBError):
            S1LCD()
        self.dispose_resources.assert_called_once_with(self.dev)

    def test_first_heartbeat_and_retry(self):
        self.dev.write.side_effect = [BUFFER_SIZE, usb.core.USBTimeoutError("timeout")]
        with self.assertRaises(usb.core.USBTimeoutError):
            S1LCD()
        self.dev.write.side_effect = None
        self.assertIs(S1LCD().dev, self.dev)
        self.assertEqual(self.claim_interface.call_count, 2)
        self.dispose_resources.assert_called_once_with(self.dev)
