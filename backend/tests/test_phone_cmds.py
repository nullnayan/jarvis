import unittest
from unittest.mock import MagicMock, patch

from tools.phone_link import PhoneLink


class PhoneCmdsTests(unittest.TestCase):
    def setUp(self):
        self.link = PhoneLink()

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_adb_pair_command_construction(self, mock_run, mock_adb_bin):
        mock_run.return_value = MagicMock(returncode=0, stdout="Successfully paired to 192.168.1.15:4321", stderr="")
        ok, msg = self.link.pair("192.168.1.15", "4321", "123456")
        self.assertTrue(ok)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], r"C:\platform-tools\adb.exe")
        self.assertEqual(args[1:], ["pair", "192.168.1.15:4321", "123456"])

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_adb_connect_command_construction(self, mock_run, mock_adb_bin):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="List of devices attached\n", stderr=""),
            MagicMock(returncode=0, stdout="connected to 192.168.1.15:5555", stderr=""),
            MagicMock(returncode=0, stdout="Pixel 8 Pro", stderr=""),
        ]
        ok, msg = self.link.connect("192.168.1.15", "5555")
        self.assertTrue(ok)
        self.assertEqual(self.link.state, "connected")
        self.assertEqual(self.link.device_serial, "192.168.1.15:5555")
        self.assertEqual(self.link.device_model, "Pixel 8 Pro")

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_screencap_command_construction(self, mock_run, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "emulator-5554"
        mock_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_png_bytes, stderr=b"")

        ok, raw, err = self.link.screencap_png()
        self.assertTrue(ok)
        self.assertEqual(raw, mock_png_bytes)
        args = mock_run.call_args[0][0]
        self.assertEqual(args, [r"C:\platform-tools\adb.exe", "-s", "emulator-5554", "exec-out", "screencap", "-p"])

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_open_app_youtube_with_query(self, mock_run, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.15:5555"
        mock_run.return_value = MagicMock(returncode=0, stdout="Starting: Intent", stderr="")
        ok, msg = self.link.open_app("youtube", query="starboy")
        self.assertTrue(ok)
        self.assertIn("starboy", msg.lower())
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], r"C:\platform-tools\adb.exe")
        self.assertTrue(args[-1].startswith("https://www.youtube.com/watch?v=") or "search_query" in args[-1])

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_open_app_instagram_with_query(self, mock_run, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.15:5555"
        mock_run.return_value = MagicMock(returncode=0, stdout="Starting: Intent", stderr="")
        ok, msg = self.link.open_app("instagram", query="owner")
        self.assertTrue(ok)
        self.assertIn("owner", msg.lower())
        args = mock_run.call_args[0][0]
        self.assertIn("https://instagram.com/_u/owner", args[-1])

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch.object(PhoneLink, "_get_screen_size", return_value=(1080, 2400))
    @patch("subprocess.run")
    def test_input_action_like(self, mock_run, mock_size, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.15:5555"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, msg = self.link.input_action("like")
        self.assertTrue(ok)
        self.assertEqual(mock_run.call_count, 2)  # Double tap

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_input_action_back_and_home(self, mock_run, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.15:5555"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, msg = self.link.input_action("back")
        self.assertTrue(ok)
        args = mock_run.call_args[0][0]
        self.assertIn("4", args)  # KEYCODE_BACK

        ok, msg = self.link.input_action("home")
        self.assertTrue(ok)
        args = mock_run.call_args[0][0]
        self.assertIn("3", args)  # KEYCODE_HOME

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch("subprocess.run")
    def test_make_call_direct_number(self, mock_run, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.15:5555"
        mock_run.return_value = MagicMock(returncode=0, stdout="Starting: Intent", stderr="")
        ok, msg = self.link.make_call("+919876543210")
        self.assertTrue(ok)
        self.assertIn("calling", msg.lower())
        args = mock_run.call_args_list[0][0][0]
        self.assertIn("tel:+919876543210", args[-1])

    @patch.object(PhoneLink, "_adb_binary", return_value=r"C:\platform-tools\adb.exe")
    @patch.object(PhoneLink, "_lookup_contact_number", return_value=("9998887776", "Mom"))
    @patch("subprocess.run")
    def test_make_call_resolved_contact(self, mock_run, mock_lookup, mock_adb_bin):
        self.link.state = "connected"
        self.link.device_serial = "192.168.1.15:5555"
        mock_run.return_value = MagicMock(returncode=0, stdout="Starting: Intent", stderr="")
        ok, msg = self.link.make_call("Mom")
        self.assertTrue(ok)
        self.assertIn("calling mom", msg.lower())
        args = mock_run.call_args_list[0][0][0]
        self.assertIn("tel:9998887776", args[-1])


if __name__ == "__main__":
    unittest.main()
