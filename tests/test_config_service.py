#!/usr/bin/env python3
"""Tests für ConfigService mtime-cache (AP1)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from services.config_service import ConfigService


class TestConfigServiceMtimeCache(unittest.TestCase):
    """Tests für AP1: ConfigService mtime-cache."""

    def setUp(self):
        """Erstelle temporäre Config-Verzeichnis für Tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)
        self.config_file = self.config_dir / "config.json"
        self.ignore_list_dir = self.config_dir / "ignore_lists"
        self.ignore_list_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Räume auf."""
        self.temp_dir.cleanup()

    def test_readMergedConfig_caches_unchanged_file(self):
        """
        Test: Wenn config.json sich nicht ändert,
        werden wiederholte readMergedConfig()-Aufrufe gecacht.
        """
        service = ConfigService(str(self.config_file))
        
        # Erste Calls sollten Cache befüllen
        config1 = service.readMergedConfig()
        config2 = service.readMergedConfig()
        
        # Sollten identische Objekte sein (außer deepcopy)
        self.assertEqual(config1, config2)
        # Cache sollte gefüllt sein
        self.assertIsNotNone(service._merged_config_cache)
        self.assertIsNotNone(service._merged_config_cache_signature)

    def test_readMergedConfig_detects_file_change(self):
        """
        Test: Wenn config.json sich ändert,
        wird der Cache invalidiert und neu geladen.
        """
        service = ConfigService(str(self.config_file))
        
        # Erste Config lesen
        config1 = service.readMergedConfig()
        
        # Datei schreiben
        test_config = {
            "photos": {"MAX_PHOTOS_PERSONS": 1000}
        }
        with self.config_file.open("w") as f:
            json.dump(test_config, f)
        
        # Kleine Verzögerung für mtime-Unterschied
        time.sleep(0.01)
        
        # Zweite Config lesen - sollte neu laden
        config2 = service.readMergedConfig()
        
        # Wert sollte sich geändert haben
        self.assertEqual(config2["photos"]["MAX_PHOTOS_PERSONS"], 1000)

    def test_readMergedConfig_detects_ignore_list_change(self):
        """
        Test: Wenn eine Ignore-List sich ändert,
        wird der Cache invalidiert.
        """
        service = ConfigService(str(self.config_file))
        
        # Erste Config lesen
        config1 = service.readMergedConfig()
        signature1 = service._merged_config_cache_signature
        
        # Ignore-List ändern
        ignore_path = self.ignore_list_dir / "checks_ignore_duplicate_faces.txt"
        with ignore_path.open("w") as f:
            f.write("test_token\n")
        
        time.sleep(0.01)
        
        # Zweite Config lesen - Signature sollte sich unterscheiden
        config2 = service.readMergedConfig()
        signature2 = service._merged_config_cache_signature
        
        self.assertNotEqual(signature1, signature2)

    def test_writeConfig_invalidates_cache(self):
        """
        Test: writeConfig() invalidiert den Cache.
        """
        service = ConfigService(str(self.config_file))
        
        # Config lesen und cachen
        config1 = service.readMergedConfig()
        self.assertIsNotNone(service._merged_config_cache)
        
        # Config schreiben
        test_config = {"photos": {"MAX_PHOTOS_PERSONS": 2000}}
        service.writeConfig(test_config)
        
        # Cache sollte invalidiert sein
        self.assertIsNone(service._merged_config_cache)
        self.assertIsNone(service._merged_config_cache_signature)

    def test_writeChecksIgnoreList_invalidates_cache(self):
        """
        Test: writeChecksIgnoreList() invalidiert den Cache.
        """
        service = ConfigService(str(self.config_file))
        
        # Config lesen und cachen
        config1 = service.readMergedConfig()
        self.assertIsNotNone(service._merged_config_cache)
        
        # Ignore-List schreiben
        service.writeChecksIgnoreList("duplicate_faces", ["token1", "token2"])
        
        # Cache sollte invalidiert sein
        self.assertIsNone(service._merged_config_cache)
        self.assertIsNone(service._merged_config_cache_signature)

    def test_appendChecksIgnoreToken_invalidates_cache(self):
        """
        Test: appendChecksIgnoreToken() invalidiert den Cache.
        """
        service = ConfigService(str(self.config_file))
        
        # Config lesen und cachen
        config1 = service.readMergedConfig()
        self.assertIsNotNone(service._merged_config_cache)
        
        # Token anhängen
        service.appendChecksIgnoreToken("duplicate_faces", "test_token")
        
        # Cache sollte invalidiert sein
        self.assertIsNone(service._merged_config_cache)
        self.assertIsNone(service._merged_config_cache_signature)

    def test_clearChecksIgnoreList_invalidates_cache(self):
        """
        Test: clearChecksIgnoreList() invalidiert den Cache.
        """
        service = ConfigService(str(self.config_file))
        
        # Config lesen und cachen
        config1 = service.readMergedConfig()
        self.assertIsNotNone(service._merged_config_cache)
        
        # Ignore-List leeren
        service.clearChecksIgnoreList("duplicate_faces")
        
        # Cache sollte invalidiert sein
        self.assertIsNone(service._merged_config_cache)
        self.assertIsNone(service._merged_config_cache_signature)

    def test_deepcopy_protects_against_mutation(self):
        """
        Test: readMergedConfig() gibt deepcopy zurück,
        so dass Mutationen nicht den Cache beeinflussen.
        """
        service = ConfigService(str(self.config_file))
        
        config1 = service.readMergedConfig()
        config1["photos"]["MAX_PHOTOS_PERSONS"] = 9999
        
        # Zweiter Aufruf sollte Originalwert haben
        config2 = service.readMergedConfig()
        self.assertEqual(
            config2["photos"]["MAX_PHOTOS_PERSONS"],
            ConfigService.defaultConfig()["photos"]["MAX_PHOTOS_PERSONS"]
        )

    def test_config_signature_includes_main_config(self):
        """
        Test: _config_signature() enthält Pfad und mtime der Hauptconfig.
        """
        service = ConfigService(str(self.config_file))
        
        # Datei schreiben
        test_config = {"photos": {"MAX_PHOTOS_PERSONS": 1000}}
        with self.config_file.open("w") as f:
            json.dump(test_config, f)
        
        signature = service._config_signature()
        
        # Sollte mehrere Elemente enthalten
        self.assertGreater(len(signature), 1)
        # Erstes Element sollte der Pfad sein
        self.assertEqual(signature[0], str(self.config_file))

    def test_config_signature_handles_missing_files(self):
        """
        Test: _config_signature() arbeitet korrekt, wenn Dateien nicht existieren.
        """
        service = ConfigService(str(self.config_file))
        
        # Datei existiert nicht
        signature = service._config_signature()
        
        # Sollte keine Exception werfen
        self.assertIsInstance(signature, tuple)
        self.assertGreater(len(signature), 0)


class TestConfigServiceDefaults(unittest.TestCase):
    """Tests für Kompatibilität mit bestehenden Defaults."""

    def setUp(self):
        """Erstelle temporäre Config-Verzeichnis für Tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)
        self.config_file = self.config_dir / "config.json"

    def tearDown(self):
        """Räume auf."""
        self.temp_dir.cleanup()

    def test_readMergedConfig_returns_defaults_when_no_file(self):
        """
        Test: readMergedConfig() liefert Defaults,
        wenn keine config.json existiert.
        """
        service = ConfigService(str(self.config_file))
        config = service.readMergedConfig()
        
        # Sollte alle Default-Keys enthalten
        self.assertIn("photos", config)
        self.assertIn("face_match", config)
        self.assertIn("files", config)
        self.assertIn("metadata", config)
        self.assertIn("analysis", config)
        self.assertIn("review", config)

    def test_readMergedConfig_merges_custom_config(self):
        """
        Test: Benutzerdefinierte Config wird mit Defaults gemergt.
        """
        service = ConfigService(str(self.config_file))
        
        # Custom Config schreiben
        custom = {"photos": {"MAX_PHOTOS_PERSONS": 3000}}
        with self.config_file.open("w") as f:
            json.dump(custom, f)
        
        config = service.readMergedConfig()
        
        # Custom-Wert sollte überschreiben
        self.assertEqual(config["photos"]["MAX_PHOTOS_PERSONS"], 3000)
        # Andere Defaults sollten erhalten sein
        self.assertIn("face_match", config)


if __name__ == "__main__":
    unittest.main()
