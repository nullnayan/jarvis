"""Publication cleanup checks without live providers, ADB, or user credentials."""
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from cloud import telegram_notifier

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('jarvis_installer', ROOT / 'download_and_install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerSecurityTests(unittest.TestCase):
    def test_missing_credentials_never_downloads_or_runs_adb(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(installer.httpx, 'Client') as client:
            with patch.object(installer.subprocess, 'run') as run:
                self.assertEqual(installer.main(), 1)
                client.assert_not_called()
                run.assert_not_called()

    def test_selects_only_authorized_unambiguous_devices(self):
        output = 'List of devices attached\na\tdevice\nb\tunauthorized\n'
        self.assertEqual(installer.select_device(output), 'a')
        with self.assertRaises(ValueError):
            installer.select_device(output, 'b')
        with self.assertRaises(ValueError):
            installer.select_device(output + 'c\tdevice\n')

    def test_artifact_cannot_extract_other_paths(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('../../app-debug.apk', b'example apk')
            archive.writestr('../unexpected.txt', b'do not extract')
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            apk = installer.extract_apk(content.getvalue(), destination)
            self.assertEqual(apk, destination / 'app-debug.apk')
            self.assertEqual(apk.read_bytes(), b'example apk')
            self.assertEqual([p.name for p in destination.iterdir()], ['app-debug.apk'])


class TelegramSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_configuration_does_not_contact_telegram(self):
        with patch.object(telegram_notifier, 'TELEGRAM_BOT_TOKEN', ''):
            with patch.object(telegram_notifier.httpx, 'AsyncClient') as client:
                self.assertFalse(await telegram_notifier.send_telegram_status_update('hello'))
                client.assert_not_called()

    async def test_exception_urls_cannot_leak_token_to_logs(self):
        sensitive = 'private-value-for-log-test'
        fake = AsyncMock()
        fake.__aenter__.return_value.post.side_effect = RuntimeError('https://example.com/' + sensitive)
        with patch.object(telegram_notifier, 'TELEGRAM_BOT_TOKEN', sensitive):
            with patch.object(telegram_notifier, 'TELEGRAM_CHAT_ID', 'local-test-recipient'):
                with patch.object(telegram_notifier.httpx, 'AsyncClient', return_value=fake):
                    with self.assertLogs(telegram_notifier.logger, level='ERROR') as captured:
                        self.assertFalse(await telegram_notifier.send_telegram_status_update('hello'))
                    self.assertNotIn(sensitive, '\n'.join(captured.output))


if __name__ == '__main__':
    unittest.main()
