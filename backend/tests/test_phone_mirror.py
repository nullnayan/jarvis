import unittest
from unittest.mock import MagicMock, patch

from tools.phone_link import PhoneLink


class PhoneMirrorTests(unittest.TestCase):
    def setUp(self):
        self.link = PhoneLink()

    def test_mirror_fails_when_disconnected(self):
        self.link.state = "disconnected"
        ok, msg = self.link.launch_scrcpy()
        self.assertFalse(ok)
        self.assertIn("connect", msg.lower())

    @patch.object(PhoneLink, "_scrcpy_binary", return_value=r"C:\scrcpy\scrcpy.exe")
    @patch("subprocess.Popen")
    def test_mirror_launches_scrcpy_with_correct_args(self, mock_popen, mock_scrcpy_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.50:5555"
        mock_proc = MagicMock()
        mock_proc.pid = 9876
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        ok, msg = self.link.launch_scrcpy(audio=False)
        self.assertTrue(ok)
        self.assertIn("Mirroring", msg)
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd[0], r"C:\scrcpy\scrcpy.exe")
        self.assertIn("-s", cmd)
        self.assertIn("192.168.1.50:5555", cmd)
        self.assertIn("--window-title", cmd)
        self.assertIn("Jarvis Phone", cmd)
        self.assertIn("--no-audio", cmd)

    @patch("subprocess.run")
    def test_stop_scrcpy_terminates_process(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.pid = 4321
        mock_proc.poll.return_value = None
        self.link._scrcpy_proc = mock_proc

        msg = self.link.stop_scrcpy()
        self.assertIn("Stopped", msg)
        self.assertIsNone(self.link._scrcpy_proc)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["taskkill", "/PID", "4321", "/T", "/F"])

    @patch("subprocess.run")
    def test_disconnect_cleans_up_running_scrcpy(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.pid = 4321
        mock_proc.poll.return_value = None
        self.link._scrcpy_proc = mock_proc
        self.link.state = "connected"

        self.link.disconnect()
        self.assertIsNone(self.link._scrcpy_proc)
        self.assertEqual(self.link.state, "disconnected")


if __name__ == "__main__":
    unittest.main()
