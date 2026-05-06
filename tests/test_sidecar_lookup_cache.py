#!/usr/bin/env python3
"""Tests für FileHandler SidecarLookupCache (AP3)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from handler.file_handler import FileHandler, SidecarLookupCache
from services.config_service import ConfigService


class TestSidecarLookupCache(unittest.TestCase):
    """Tests für AP3: Sidecar-Verzeichnis-Cache."""

    def setUp(self):
        """Erstelle temporäres Verzeichnis-Setup."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.config = ConfigService()
        self.handler = FileHandler(self.config)

    def tearDown(self):
        """Räume auf."""
        self.temp_dir.cleanup()

    def _create_test_files(self, filenames: list):
        """Erstelle Test-Dateien."""
        for filename in filenames:
            (self.test_dir / filename).touch()

    def test_cache_indexes_directory(self):
        """
        Test: Cache indexiert ein Verzeichnis nur einmal.
        """
        self._create_test_files([
            "image1.jpg",
            "image1.xmp",
            "image2.jpg",
            "image2.xmp"
        ])
        
        cache = SidecarLookupCache()
        
        # Erste Suche sollte Verzeichnis indexieren
        result1 = cache.find_xmp_for_image(
            str(self.test_dir / "image1.jpg"),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        self.assertIsNotNone(result1)
        
        # Cache sollte gefüllt sein
        self.assertTrue(len(cache._dir_cache) > 0)

    def test_cache_same_dir_stem(self):
        """
        Test: Cache findet XMP im selben Ordner mit Stem-Variante.
        """
        self._create_test_files([
            "photo.jpg",
            "photo.xmp"
        ])
        
        cache = SidecarLookupCache()
        result = cache.find_xmp_for_image(
            str(self.test_dir / "photo.jpg"),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("photo.xmp"))

    def test_cache_same_dir_filename(self):
        """
        Test: Cache findet XMP im selben Ordner mit Filename-Variante.
        """
        self._create_test_files([
            "photo.jpg",
            "photo.jpg.xmp"
        ])
        
        cache = SidecarLookupCache()
        result = cache.find_xmp_for_image(
            str(self.test_dir / "photo.jpg"),
            ["same_dir_filename"],
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("photo.jpg.xmp"))

    def test_cache_xmp_dir_stem(self):
        """
        Test: Cache findet XMP im xmp-Unterverzeichnis mit Stem.
        """
        xmp_subdir = self.test_dir / "xmp"
        xmp_subdir.mkdir()
        
        (self.test_dir / "photo.jpg").touch()
        (xmp_subdir / "photo.xmp").touch()
        
        cache = SidecarLookupCache()
        result = cache.find_xmp_for_image(
            str(self.test_dir / "photo.jpg"),
            ["xmp_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("photo.xmp"))

    def test_cache_case_insensitive(self):
        """
        Test: Cache ist case-insensitiv.
        """
        self._create_test_files([
            "PHOTO.JPG",
            "PHOTO.XMP"
        ])
        
        cache = SidecarLookupCache()
        result = cache.find_xmp_for_image(
            str(self.test_dir / "photo.jpg"),  # Kleinbuchstaben eingabe
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNotNone(result)

    def test_cache_avoids_directory_rescan(self):
        """
        Test: Mehrere Bilder im selben Ordner scannen Verzeichnis nur einmal.
        """
        self._create_test_files([
            "image1.jpg",
            "image1.xmp",
            "image2.jpg",
            "image2.xmp",
            "image3.jpg",
            "image3.xmp"
        ])
        
        cache = SidecarLookupCache()
        
        # Mehrere Lookups
        result1 = cache.find_xmp_for_image(
            str(self.test_dir / "image1.jpg"),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        result2 = cache.find_xmp_for_image(
            str(self.test_dir / "image2.jpg"),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        result3 = cache.find_xmp_for_image(
            str(self.test_dir / "image3.jpg"),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        
        # Alle sollten erfolgreich sein
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)
        self.assertIsNotNone(result3)
        
        # Nur ein Verzeichnis sollte im Cache sein
        self.assertEqual(len(cache._dir_cache), 1)

    def test_cache_handles_missing_xmp(self):
        """
        Test: Cache gibt None zurück wenn XMP nicht existiert.
        """
        (self.test_dir / "image.jpg").touch()
        # Keine image.xmp Datei
        
        cache = SidecarLookupCache()
        result = cache.find_xmp_for_image(
            str(self.test_dir / "image.jpg"),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNone(result)

    def test_cache_handles_missing_directory(self):
        """
        Test: Cache gibt None zurück wenn Verzeichnis nicht existiert.
        """
        nonexistent = self.test_dir / "nonexistent" / "image.jpg"
        
        cache = SidecarLookupCache()
        result = cache.find_xmp_for_image(
            str(nonexistent),
            ["same_dir_stem"],
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNone(result)

    def test_handler_findXmpForImage_with_cache(self):
        """
        Test: FileHandler.findXmpForImage() nutzt optionalen Cache.
        """
        self._create_test_files([
            "photo.jpg",
            "photo.xmp"
        ])
        
        cache = SidecarLookupCache()
        
        # Mit Cache
        result_with_cache = self.handler.findXmpForImage(
            str(self.test_dir / "photo.jpg"),
            lookup_cache=cache
        )
        
        self.assertIsNotNone(result_with_cache)

    def test_handler_findXmpForImage_without_cache(self):
        """
        Test: FileHandler.findXmpForImage() funktioniert ohne Cache.
        """
        self._create_test_files([
            "photo.jpg",
            "photo.xmp"
        ])
        
        # Ohne Cache (Fallback auf alte Logik)
        result_without_cache = self.handler.findXmpForImage(
            str(self.test_dir / "photo.jpg"),
            lookup_cache=None
        )
        
        self.assertIsNotNone(result_without_cache)

    def test_handler_backward_compatibility(self):
        """
        Test: FileHandler.findXmpForImage() ist backward-compatible.
        """
        self._create_test_files([
            "photo.jpg",
            "photo.xmp"
        ])
        
        # Alter Code ohne Cache-Parameter sollte funktionieren
        result = self.handler.findXmpForImage(str(self.test_dir / "photo.jpg"))
        
        self.assertIsNotNone(result)

    def test_cache_multiple_variants(self):
        """
        Test: Cache prüft mehrere Lookup-Varianten.
        """
        self._create_test_files([
            "photo.jpg",
            "photo.xmp"  # Stem-Variante
        ])
        
        cache = SidecarLookupCache()
        
        # Varianten sind in dieser Reihenfolge konfiguriert
        variants = ["same_dir_stem", "same_dir_filename", "xmp_dir_stem"]
        
        result = cache.find_xmp_for_image(
            str(self.test_dir / "photo.jpg"),
            variants,
            self.handler._findCaseInsensitivePath
        )
        
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("photo.xmp"))

    def test_cache_thread_safe(self):
        """
        Test: Cache verwendet Lock für Thread-Sicherheit.
        """
        cache = SidecarLookupCache()
        
        # Lock sollte existieren
        self.assertIsNotNone(cache._lock)
        
        # Lock sollte acquireable sein
        cache._lock.acquire()
        cache._lock.release()


class TestSidecarLookupCacheIntegration(unittest.TestCase):
    """Integrationstests für SidecarLookupCache mit FileHandler."""

    def setUp(self):
        """Erstelle temporäres Verzeichnis-Setup."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.config = ConfigService()
        self.handler = FileHandler(self.config)

    def tearDown(self):
        """Räume auf."""
        self.temp_dir.cleanup()

    def test_real_world_scenario(self):
        """
        Test: Reales Szenario mit mehreren Bildern und XMPs in einem Ordner.
        """
        # Erstelle Ordnerstruktur
        sub_dir = self.test_dir / "2024_vacation"
        sub_dir.mkdir()
        xmp_dir = sub_dir / "xmp"
        xmp_dir.mkdir()
        
        # Erstelle Test-Dateien
        files_to_create = [
            ("DSC_0001.jpg", "DSC_0001.xmp"),  # same_dir_stem
            ("DSC_0002.jpg", "DSC_0002.xmp"),
            ("DSC_0003.jpg", "DSC_0003.xmp"),
        ]
        
        for jpg, xmp in files_to_create:
            (sub_dir / jpg).touch()
            (xmp_dir / xmp).touch()
        
        cache = SidecarLookupCache()
        
        # Suche XMPs für alle Bilder
        results = []
        for jpg, expected_xmp in files_to_create:
            result = self.handler.findXmpForImage(
                str(sub_dir / jpg),
                lookup_cache=cache
            )
            results.append(result)
            self.assertIsNotNone(result, f"XMP für {jpg} nicht gefunden")
        
        # Cache sollte nur 2 Verzeichnisse haben (sub_dir und xmp_dir)
        self.assertLessEqual(len(cache._dir_cache), 3)  # 3 wegen Indexierung


if __name__ == "__main__":
    unittest.main()
