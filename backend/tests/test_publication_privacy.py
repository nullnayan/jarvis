import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cloud import deal_db
from scrapers.card_offers import get_latlon
from scrapers import card_offers


class PublicationPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_installation_has_no_location_or_personal_watches(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(deal_db, 'DB_PATH', str(Path(folder)/'test.db')):
                database=deal_db.DealDB()
                self.assertEqual(await database.get_pincodes(), [])
                await database.set_global_toggle(True)
                self.assertEqual(await database.get_active_watches(), [])
                await database.set_pincodes(['110001'])
                self.assertEqual(await database.get_pincodes(), ['110001'])

    async def test_user_watch_preferences_are_not_overwritten_by_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(deal_db, 'DB_PATH', str(Path(folder)/'test.db')):
                database=deal_db.DealDB()
                await database.add_watch('phone','example product',12345,'{}')
                await database.init_db()
                watches=await database.get_active_watches()
                self.assertEqual(watches[0]['query'],'example product')
                self.assertEqual(watches[0]['max_price'],12345)

    def test_location_requires_user_configuration(self):
        with self.assertRaises(ValueError):get_latlon('')

    def test_location_can_be_configured_in_private_runtime_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'locations.json'
            path.write_text(json.dumps({'100000':[1.0,2.0]}))
            with patch.object(card_offers,'PRIVATE_LOCATIONS_PATH',path):
                self.assertEqual(get_latlon('100000'),(1.0,2.0))

    def test_private_runtime_files_are_not_tracked(self):
        root=Path(__file__).resolve().parents[2]
        paths=subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split('\0')
        for name in filter(None,paths):
            self.assertFalse(name.startswith(('backend/data/','.security/','.claude/')))
            self.assertNotEqual(name,'.env')
            self.assertFalse(name.endswith(('.db','.enc','.vault','.apk','.zip')))


if __name__=='__main__':unittest.main()
