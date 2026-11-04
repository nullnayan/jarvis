import unittest
from unittest.mock import MagicMock, patch

from tools.phone_link import PhoneLink


class PhoneLinkStateTests(unittest.TestCase):
    def setUp(self):
        self.link = PhoneLink()

    def test_init_starts_disconnected(self):
        """Must strictly start disconnected — never auto-connect on boot."""
        self.assertEqual(self.link.state, "disconnected")
        self.assertIsNone(self.link.device_serial)
        self.assertIsNone(self.link.device_model)
        self.assertIsNone(self.link._scrcpy_proc)

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_disconnect_kills_server_and_clears_state(self, mock_run, mock_adb_bin):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.100:5555"
        self.link.device_model = "Pixel 8"

        res = self.link.disconnect()
        self.assertEqual(self.link.state, "disconnected")
        self.assertIsNone(self.link.device_serial)
        self.assertIsNone(self.link.device_model)
        self.assertIn("Disconnected", res)

        # Verify adb disconnect and adb kill-server were executed
        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        flattened = [" ".join(cmd) for cmd in called_cmds]
        self.assertTrue(any("disconnect" in cmd for cmd in flattened))
        self.assertTrue(any("kill-server" in cmd for cmd in flattened))

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_disconnect_is_idempotent(self, mock_run, mock_adb_bin):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        res = self.link.disconnect()
        self.assertEqual(self.link.state, "disconnected")
        self.assertIn("Disconnected", res)

    def test_status_when_disconnected(self):
        self.assertEqual(self.link.status(), "Your phone is not connected, boss.")

    def test_status_when_connected(self):
        self.link.state = "connected"
        self.link.device_model = "Galaxy S24"
        self.link.device_serial = "192.168.1.50:5555"
        status = self.link.status()
        self.assertIn("Galaxy S24", status)
        self.assertIn("192.168.1.50:5555", status)


if __name__ == "__main__":
    unittest.main()
