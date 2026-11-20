import unittest
from unittest.mock import Mock

import usb.core
from lcd import BUFFER_SIZE, EP_OUT, S1LCD


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.lcd = S1LCD.__new__(S1LCD)
        self.lcd.dev = Mock()
        self.frame = b"\x55\xa1\xf2" + bytes(BUFFER_SIZE - 3)

    def test_complete(self):
        self.lcd.dev.write.return_value = BUFFER_SIZE
        self.lcd._send(bytearray(self.frame))
        self.lcd.dev.write.assert_called_once_with(EP_OUT, self.frame, timeout=1000)

    def test_short(self):
        self.lcd.dev.write.return_value = 64
        with self.assertRaisesRegex(usb.core.USBError, "64/4104.*55a1f2"):
            self.lcd._send(self.frame)

    def test_usb_error(self):
        self.assert_passthrough(usb.core.USBError("device unavailable"))

    def test_timeout(self):
        self.assert_passthrough(usb.core.USBTimeoutError("transmission timeout"))

    def assert_passthrough(self, error):
        self.lcd.dev.write.side_effect = error
        with self.assertRaises(type(error)) as context:
            self.lcd._send(self.frame)
        self.assertIs(error, context.exception)
