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

    def test_missing_photos_item_reindex_is_disabled_by_default(self):
        photos = ConfigService.defaultConfig()["photos"]

        self.assertFalse(photos["REINDEX_MISSING_ITEMS"])

    def test_native_face_processor_config_defaults_and_normalization(self):
        service = ConfigService(str(self.config_file))
        service.writeConfig({
            "native_processors": {
                "FACE_PROCESSOR": {
                    "TIMEOUT_SECONDS": 99999,
                    "MAX_IMAGE_BYTES": 1,
                    "ORT_INTRA_THREADS": 999,
                    "ORT_GRAPH_OPT_LEVEL": "invalid",
                    "INSIGHTFACE_LICENSE_ACKNOWLEDGED": 1,
                },
            },
        })

        face_processor = service.readMergedConfig()["native_processors"]["FACE_PROCESSOR"]

        self.assertEqual(face_processor["TIMEOUT_SECONDS"], 3600)
        self.assertEqual(face_processor["MAX_IMAGE_BYTES"], 1048576)
        self.assertEqual(face_processor["ORT_INTRA_THREADS"], 64)
        self.assertEqual(face_processor["ORT_GRAPH_OPT_LEVEL"], "all")
        self.assertTrue(face_processor["INSIGHTFACE_LICENSE_ACKNOWLEDGED"])
        self.assertNotIn("ENABLED", face_processor)
        self.assertNotIn("PATH", face_processor)
        self.assertNotIn("FALLBACK_TO_PYTHON", face_processor)

    def test_optional_vips_image_processor_config_defaults_and_normalization(self):
        service = ConfigService(str(self.config_file))
        service.writeConfig({
            "native_processors": {
                "IMAGE_PROCESSOR_VIPS": {
                    "ENABLED": 1,
                    "PREFERRED": 0,
                    "PATH": "/tmp/native-vips",
                    "TIMEOUT_SECONDS": 99999,
                    "MAX_IMAGE_BYTES": 1,
                    "SUPPORTED_FORMATS": [".JPG", "png", "jpg", ""],
                    "ALLOW_FALLBACK_TO_DEFAULT": 0,
                },
            },
        })

        image_processor = service.readMergedConfig()["native_processors"]["IMAGE_PROCESSOR_VIPS"]

        self.assertTrue(image_processor["ENABLED"])
        self.assertFalse(image_processor["PREFERRED"])
        self.assertEqual(image_processor["PATH"], "/tmp/native-vips")
        self.assertEqual(image_processor["TIMEOUT_SECONDS"], 3600)
        self.assertEqual(image_processor["MAX_IMAGE_BYTES"], 1048576)
        self.assertEqual(image_processor["SUPPORTED_FORMATS"], ["jpg", "png"])
        self.assertFalse(image_processor["ALLOW_FALLBACK_TO_DEFAULT"])

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

    def test_ignore_list_is_independent_from_merged_config_cache(self):
        service = ConfigService(str(self.config_file))

        service.readMergedConfig()
        signature1 = service._merged_config_cache_signature
        service.writeChecksIgnoreList("duplicate_faces", ["test_token"])
        service.readMergedConfig()
        signature2 = service._merged_config_cache_signature

        self.assertEqual(signature1, signature2)
        self.assertEqual(service.readChecksIgnoreList("duplicate_faces"), ["test_token"])

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

    def test_default_config_no_longer_contains_python_insightface_pip_packages(self):
        self.assertNotIn("pip_packages", ConfigService.defaultConfig())

    def test_legacy_pip_packages_config_is_not_merged_back(self):
        service = ConfigService(str(self.config_file))
        service.writeConfig({
            "pip_packages": {
                "INSIGHTFACE": {
                    "INSTALL_ON_START": True,
                    "WHEELHOUSE_ENABLED": False,
                    "WHEELHOUSE_MANIFEST_URL": "https://example.invalid/releases/download/dsm7-x86_64-python38/wheelhouse-manifest.json",
                    "WHEELHOUSE_TARGET": "dsm7-x86_64-python38",
                    "REQUIREMENTS_FILE": "requirements-optional-insightface.txt",
                },
            },
        })

        merged = service.readMergedConfig()

        self.assertNotIn("pip_packages", merged)

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

    def test_getChecksIgnoreListsStatus_returns_paths_and_counts(self):
        service = ConfigService(str(self.config_file))
        service.writeChecksIgnoreList("duplicate_faces", ["token1", "token2"])

        statuses = service.getChecksIgnoreListsStatus()

        self.assertEqual(statuses["duplicate_faces"]["count"], 2)
        self.assertEqual(statuses["duplicate_faces"]["path"], str(self.config_dir / "imgdata.sqlite3"))
        self.assertEqual(statuses["duplicate_faces"]["storage"], "sqlite")
        self.assertEqual(statuses["position_deviations"]["count"], 0)

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
        self.assertNotIn("runtime", config)
        self.assertIn("debug", config)
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

    def test_runtime_findings_storage_format_is_removed(self):
        service = ConfigService(str(self.config_file))

        config = service.readMergedConfig()

        self.assertNotIn("runtime", config)

    def test_legacy_runtime_findings_storage_format_is_discarded(self):
        service = ConfigService(str(self.config_file))
        with self.config_file.open("w") as f:
            json.dump({"runtime": {"FINDINGS_STORAGE_FORMAT": "sqlite"}}, f)

        config = service.readMergedConfig()

        self.assertNotIn("runtime", config)

    def test_debug_io_metrics_defaults_to_disabled(self):
        service = ConfigService(str(self.config_file))

        config = service.readMergedConfig()

        self.assertFalse(config["debug"]["IO_METRICS_ENABLED"])
        self.assertFalse(config["debug"]["BACKEND_DEBUG_ENABLED"])
        self.assertEqual(config["debug"]["BACKEND_DEBUG_LOG_PATH"], "")
        self.assertEqual(config["debug"]["BACKEND_DEBUG_LOG_MAX_BYTES"], 1048576)
        self.assertEqual(config["debug"]["BACKEND_DEBUG_LOG_BACKUPS"], 3)

    def test_backend_debug_config_is_normalized(self):
        service = ConfigService(str(self.config_file))
        with self.config_file.open("w") as f:
            json.dump({
                "debug": {
                    "BACKEND_DEBUG_ENABLED": 1,
                    "BACKEND_DEBUG_LOG_PATH": "/tmp/av-debug.log",
                    "BACKEND_DEBUG_LOG_MAX_BYTES": 1,
                    "BACKEND_DEBUG_LOG_BACKUPS": 99,
                },
            }, f)

        config = service.readMergedConfig()

        self.assertTrue(config["debug"]["BACKEND_DEBUG_ENABLED"])
        self.assertEqual(config["debug"]["BACKEND_DEBUG_LOG_PATH"], "/tmp/av-debug.log")
        self.assertEqual(config["debug"]["BACKEND_DEBUG_LOG_MAX_BYTES"], 65536)
        self.assertEqual(config["debug"]["BACKEND_DEBUG_LOG_BACKUPS"], 10)

    def test_exiftool_persistent_timeout_is_normalized(self):
        service = ConfigService(str(self.config_file))
        with self.config_file.open("w") as f:
            json.dump({"files": {"EXIFTOOL_PERSISTENT_ENABLED": False, "EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS": 5000}}, f)

        config = service.readMergedConfig()

        self.assertFalse(config["files"]["EXIFTOOL_PERSISTENT_ENABLED"])
        self.assertEqual(config["files"]["EXIFTOOL_PERSISTENT_TIMEOUT_SECONDS"], 300)
        self.assertNotIn("EXIFTOOL_BATCH_READ_ENABLED", ConfigService.defaultConfig()["files"])
        self.assertNotIn("EXIFTOOL_BATCH_SIZE", ConfigService.defaultConfig()["files"])

    def test_image_decoder_config_is_normalized(self):
        service = ConfigService(str(self.config_file))
        with self.config_file.open("w") as f:
            json.dump({
                "files": {
                    "IMAGE_DECODER_ENABLED": 1,
                    "IMAGE_DECODER_EXTENSIONS": [".HEIC", "heif", "", ".HEIC"],
                    "IMAGE_DECODER_ORDER": ["pillow-heif", "invalid", "ffmpeg"],
                    "IMAGE_DECODER_TIMEOUT_SECONDS": 0,
                    "IMAGE_DECODER_MAX_EDGE": 50000,
                    "RECOGNITION_IMAGE_MAX_EDGE": "bad",
                },
            }, f)

        config = service.readMergedConfig()

        self.assertTrue(config["files"]["IMAGE_DECODER_ENABLED"])
        self.assertEqual(config["files"]["IMAGE_DECODER_EXTENSIONS"], ["heic", "heif"])
        self.assertEqual(config["files"]["IMAGE_DECODER_ORDER"], ["pillow-heif", "ffmpeg"])
        self.assertEqual(config["files"]["IMAGE_DECODER_TIMEOUT_SECONDS"], 1)
        self.assertEqual(config["files"]["IMAGE_DECODER_MAX_EDGE"], 20000)
        self.assertEqual(config["files"]["RECOGNITION_IMAGE_MAX_EDGE"], 4096)


if __name__ == "__main__":
    unittest.main()
