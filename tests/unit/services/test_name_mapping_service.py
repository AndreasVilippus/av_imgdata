#!/usr/bin/env python3
"""Tests für NameMappingService mtime-cache und Lookup-Index (AP2)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from services.name_mapping_service import NameMappingService


class TestNameMappingServiceCache(unittest.TestCase):
    """Tests für AP2: NameMappingService mtime-cache und Lookup-Index."""

    def setUp(self):
        """Erstelle temporäres Mapping-Verzeichnis für Tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mapping_dir = Path(self.temp_dir.name)
        self.mapping_file = self.mapping_dir / "name_mappings.json"

    def tearDown(self):
        """Räume auf."""
        self.temp_dir.cleanup()

    def test_readNameMappings_caches_unchanged_file(self):
        """
        Test: Wenn name_mappings.json sich nicht ändert,
        werden wiederholte readNameMappings()-Aufrufe gecacht.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Mappings schreiben
        test_mappings = [
            {"source_name": "John Doe", "target_name": "John"},
            {"source_name": "Jane Smith", "target_name": "Jane"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings}, f)
        
        # Erste zwei Aufrufe sollten Cache befüllen
        result1 = service.readNameMappings()
        result2 = service.readNameMappings()
        
        # Sollten identisch sein
        self.assertEqual(result1, result2)
        # Cache sollte gefüllt sein
        self.assertIsNotNone(service._cache_mappings)
        self.assertIsNotNone(service._cache_index)

    def test_findNameMapping_uses_index(self):
        """
        Test: findNameMapping() nutzt den Index,
        nicht lineare Suche.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Mappings schreiben
        test_mappings = [
            {"source_name": "John Doe", "target_name": "John"},
            {"source_name": "Jane Smith", "target_name": "Jane"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings}, f)
        
        # Ersten Lookup durchführen
        result1 = service.findNameMapping("John Doe")
        self.assertIsNotNone(result1)
        self.assertEqual(result1["target_name"], "John")
        
        # Zweiten Lookup durchführen - sollte Index nutzen
        result2 = service.findNameMapping("jane smith")
        self.assertIsNotNone(result2)
        self.assertEqual(result2["target_name"], "Jane")

    def test_findNameMapping_returns_copy(self):
        """
        Test: findNameMapping() gibt deepcopy zurück,
        nicht die gecachte Referenz.
        """
        service = NameMappingService(str(self.mapping_file))
        
        test_mappings = [
            {"source_name": "John Doe", "target_name": "John"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings}, f)
        
        result1 = service.findNameMapping("John Doe")
        result1["target_name"] = "MODIFIED"
        
        # Zweiter Aufruf sollte Original haben
        result2 = service.findNameMapping("John Doe")
        self.assertEqual(result2["target_name"], "John")

    def test_readNameMappings_imports_legacy_file_only_once(self):
        """
        Test: Wenn name_mappings.json sich ändert,
        wird der Cache invalidiert und neu geladen.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Erste Mappings schreiben
        test_mappings1 = [
            {"source_name": "John", "target_name": "John"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings1}, f)
        
        result1 = service.readNameMappings()
        self.assertEqual(len(result1), 1)
        
        # Kleine Verzögerung
        time.sleep(0.01)
        
        # Neue Mappings schreiben
        test_mappings2 = [
            {"source_name": "Jane", "target_name": "Jane"},
            {"source_name": "Bob", "target_name": "Bob"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings2}, f)
        
        # Nach erfolgreicher Migration bleibt SQLite die Quelle.
        result2 = service.readNameMappings()
        self.assertEqual(result2, [{"source_name": "John", "target_name": "John"}])

    def test_saveNameMapping_invalidates_cache(self):
        """
        Test: saveNameMapping() invalidiert den Cache.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Mappings schreiben
        test_mappings = [
            {"source_name": "John", "target_name": "John"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings}, f)
        
        # Cache befüllen
        result1 = service.readNameMappings()
        self.assertIsNotNone(service._cache_mappings)
        
        # Neues Mapping speichern
        service.saveNameMapping(source_name="Jane", target_name="Jane")
        
        # Cache sollte invalidiert sein
        self.assertIsNone(service._cache_mappings)
        self.assertIsNone(service._cache_index)

    def test_saveNameMapping_updates_existing(self):
        """
        Test: saveNameMapping() aktualisiert bestehende Mappings.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Initialisiere mit einem Mapping
        service.saveNameMapping(source_name="John", target_name="John")
        
        # Aktualisiere das gleiche Mapping
        service.saveNameMapping(source_name="John", target_name="Jonathan")
        
        # Sollte nur ein Mapping mit aktuellem Wert sein
        result = service.readNameMappings()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["target_name"], "Jonathan")

    def test_saveNameMapping_adds_new(self):
        """
        Test: saveNameMapping() fügt neue Mappings hinzu.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Erstes Mapping speichern
        service.saveNameMapping(source_name="John", target_name="John")
        # Zweites Mapping speichern
        service.saveNameMapping(source_name="Jane", target_name="Jane")
        
        result = service.readNameMappings()
        self.assertEqual(len(result), 2)

    def test_saveNameMapping_writes_sqlite_without_rewriting_legacy_json(self):
        """
        Test: saveNameMapping() schreibt atomar
        (temporäre Datei dann replace).
        """
        service = NameMappingService(str(self.mapping_file))
        
        service.saveNameMapping(source_name="John", target_name="John")
        
        self.assertFalse(self.mapping_file.exists())
        self.assertTrue((self.mapping_dir / "imgdata.sqlite3").exists())

    def test_saveNameMappingsBatch(self):
        """
        Test: saveNameMappingsBatch() speichert mehrere Mappings.
        """
        service = NameMappingService(str(self.mapping_file))
        
        batch = [
            {"source_name": "John", "target_name": "John"},
            {"source_name": "Jane", "target_name": "Jane"},
            {"source_name": "Bob", "target_name": "Robert"}
        ]
        
        success = service.saveNameMappingsBatch(batch)
        self.assertTrue(success)
        
        result = service.readNameMappings()
        self.assertEqual(len(result), 3)

    def test_saveNameMappingsBatch_updates_existing(self):
        """
        Test: saveNameMappingsBatch() aktualisiert bestehende Mappings.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Erste Batch
        batch1 = [
            {"source_name": "John", "target_name": "John"},
            {"source_name": "Jane", "target_name": "Jane"}
        ]
        service.saveNameMappingsBatch(batch1)
        
        # Zweite Batch mit Update
        batch2 = [
            {"source_name": "John", "target_name": "Jonathan"},
            {"source_name": "Bob", "target_name": "Robert"}
        ]
        service.saveNameMappingsBatch(batch2)
        
        result = service.readNameMappings()
        self.assertEqual(len(result), 3)
        
        # John sollte aktualisiert sein
        john_mapping = next((m for m in result if m["source_name"] == "John"), None)
        self.assertIsNotNone(john_mapping)
        self.assertEqual(john_mapping["target_name"], "Jonathan")

    def test_findNameMapping_case_insensitive(self):
        """
        Test: findNameMapping() ist case-insensitiv.
        """
        service = NameMappingService(str(self.mapping_file))
        
        test_mappings = [
            {"source_name": "John Doe", "target_name": "John"}
        ]
        with self.mapping_file.open("w") as f:
            json.dump({"name_mappings": test_mappings}, f)
        
        # Verschiedene Case-Variationen sollten funktionieren
        result1 = service.findNameMapping("john doe")
        result2 = service.findNameMapping("JOHN DOE")
        result3 = service.findNameMapping("John Doe")
        
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)
        self.assertIsNotNone(result3)
        self.assertEqual(result1["target_name"], "John")

    def test_readNameMappings_handles_missing_file(self):
        """
        Test: readNameMappings() arbeitet korrekt, wenn Datei nicht existiert.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Datei existiert nicht
        result = service.readNameMappings()
        
        self.assertEqual(result, [])
        # Cache sollte trotzdem gesetzt sein
        self.assertIsNotNone(service._cache_mappings)

    def test_readNameMappings_handles_corrupted_json(self):
        """
        Test: readNameMappings() arbeitet mit defektem JSON.
        """
        service = NameMappingService(str(self.mapping_file))
        
        # Defektes JSON schreiben
        with self.mapping_file.open("w") as f:
            f.write("{ invalid json }")
        
        result = service.readNameMappings()
        
        # Sollte leere Liste und Error-Message liefern
        self.assertEqual(result, [])
        self.assertIn("Expecting", service._last_read_error)

    def test_deleteNameMapping_invalidates_lookup_cache(self):
        service = NameMappingService(str(self.mapping_file))
        self.assertTrue(service.saveNameMapping(source_name="Alias", target_name="Person"))
        mapping_id = service.listNameMappingsPage(search="Alias")["entries"][0]["id"]
        self.assertIsNotNone(service.findNameMapping("Alias"))

        self.assertTrue(service.deleteNameMapping(mapping_id))

        self.assertIsNone(service.findNameMapping("Alias"))
        self.assertEqual(service.listNameMappingsPage(search="Alias")["total"], 0)

    def test_updateNameMappingTarget_updates_selected_row(self):
        service = NameMappingService(str(self.mapping_file))
        self.assertTrue(service.saveNameMapping(source_name="Alias", target_name="Person"))
        entry = service.listNameMappingsPage(search="Alias")["entries"][0]
        self.assertEqual(service.findNameMapping("Alias")["target_name"], "Person")

        self.assertTrue(service.updateNameMappingTarget(entry["id"], "Updated Person"))

        updated = service.listNameMappingsPage(search="Alias")["entries"][0]
        self.assertEqual(updated["target_name"], "Updated Person")
        self.assertEqual(service.findNameMapping("Alias")["target_name"], "Updated Person")


if __name__ == "__main__":
    unittest.main()
