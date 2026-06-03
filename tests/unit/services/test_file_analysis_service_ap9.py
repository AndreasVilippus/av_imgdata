#!/usr/bin/env python3
"""Tests für FileAnalysisService: JSON-Schreibvorgänge atomar und nur bei Änderung (AP9)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath("src"))

from services.file_analysis_service import FileAnalysisService


def _append_finding_entry_from_process(args):
    result_path, entry_id = args
    service = FileAnalysisService(result_path)
    return service.appendCheckFindingEntries("duplicate_faces", [{"id": entry_id}])


class TestFileAnalysisServiceAtomicWrites(unittest.TestCase):
    """Tests für AP9: Atomare JSON-Schreibvorgänge."""

    def setUp(self):
        """Erstelle temporäres Verzeichnis für Tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.result_dir = Path(self.temp_dir.name)
        self.result_file = self.result_dir / "file_analysis.json"

    def tearDown(self):
        """Räume auf."""
        self.temp_dir.cleanup()

    def test_writeLatestResult_creates_file(self):
        """
        Test: writeLatestResult() erstellt die Datei mit vollständigem Inhalt.
        """
        service = FileAnalysisService(str(self.result_file))
        
        result = {"key": "value", "timestamp": 123456}
        success = service.writeLatestResult(result)
        
        self.assertTrue(success)
        self.assertTrue(self.result_file.exists())
        
        # Prüfe Inhalt
        with self.result_file.open("r") as f:
            content = json.load(f)
        self.assertEqual(content["key"], "value")

    def test_writeLatestResult_skips_unchanged_content(self):
        """
        Test: Wenn Inhalt unverändert, wird die Datei nicht neu geschrieben.
        """
        service = FileAnalysisService(str(self.result_file))
        
        result = {"key": "value"}
        
        # Erste Schreiboperation
        service.writeLatestResult(result)
        original_mtime = self.result_file.stat().st_mtime
        
        # Kurze Pause
        import time
        time.sleep(0.01)
        
        # Zweite Schreiboperation mit gleichem Inhalt
        service.writeLatestResult(result)
        new_mtime = self.result_file.stat().st_mtime
        
        # Mtime sollte nicht geändert sein
        self.assertEqual(original_mtime, new_mtime)

    def test_writeLatestResult_updates_changed_content(self):
        """
        Test: Wenn Inhalt sich ändert, wird die Datei aktualisiert.
        """
        service = FileAnalysisService(str(self.result_file))
        
        result1 = {"key": "value1"}
        service.writeLatestResult(result1)
        original_mtime = self.result_file.stat().st_mtime
        
        import time
        time.sleep(0.01)
        
        # Änderter Inhalt
        result2 = {"key": "value2"}
        service.writeLatestResult(result2)
        new_mtime = self.result_file.stat().st_mtime
        
        # Mtime sollte sich unterscheiden
        self.assertNotEqual(original_mtime, new_mtime)
        
        # Neuer Wert sollte in Datei sein
        with self.result_file.open("r") as f:
            content = json.load(f)
        self.assertEqual(content["key"], "value2")

    def test_writeLatestResult_atomic_write(self):
        """
        Test: writeLatestResult() schreibt atomar (keine Temp-Datei am Ende).
        """
        service = FileAnalysisService(str(self.result_file))
        
        result = {"key": "value"}
        success = service.writeLatestResult(result)
        
        self.assertTrue(success)
        # Keine temporäre Datei sollte übrig sein
        temp_path = self.result_file.parent / f"{self.result_file.name}.tmp"
        self.assertFalse(temp_path.exists())

    def test_writeCheckFindings_skips_unchanged(self):
        """
        Test: writeCheckFindings() schreibt nicht wenn Inhalt unverändert.
        """
        service = FileAnalysisService(str(self.result_file))
        
        findings = {
            "timestamp": 123456,
            "entries": [
                {"type": "issue", "file": "test.jpg"}
            ]
        }
        
        # Erste Schreiboperation
        service.writeCheckFindings("duplicate_faces", findings)
        findings_path = service._finding_path("duplicate_faces")
        original_mtime = findings_path.stat().st_mtime
        
        import time
        time.sleep(0.01)
        
        # Zweite Schreiboperation mit gleichem Inhalt
        service.writeCheckFindings("duplicate_faces", findings)
        new_mtime = findings_path.stat().st_mtime
        
        # Mtime sollte nicht geändert sein
        self.assertEqual(original_mtime, new_mtime)

    def test_writeCheckFindings_updates_changed(self):
        """
        Test: writeCheckFindings() aktualisiert bei Änderungen.
        """
        service = FileAnalysisService(str(self.result_file))
        
        findings1 = {"count": 1, "entries": []}
        service.writeCheckFindings("duplicate_faces", findings1)
        
        findings2 = {"count": 2, "entries": [{"id": 1}]}
        service.writeCheckFindings("duplicate_faces", findings2)
        
        findings_path = service._finding_path("duplicate_faces")
        with findings_path.open("r") as f:
            content = json.load(f)
        self.assertEqual(content["count"], 2)

    def test_writeRuntimeState_skips_unchanged(self):
        """
        Test: writeRuntimeState() schreibt nicht wenn Inhalt unverändert.
        """
        service = FileAnalysisService(str(self.result_file))
        
        state = {"progress": 50, "processed": 100}
        
        # Erste Schreiboperation
        service.writeRuntimeState("face_match", "progress", state)
        state_path = service._runtime_state_path("face_match", "progress")
        original_mtime = state_path.stat().st_mtime
        
        import time
        time.sleep(0.01)
        
        # Zweite Schreiboperation mit gleichem Inhalt
        service.writeRuntimeState("face_match", "progress", state)
        new_mtime = state_path.stat().st_mtime
        
        # Mtime sollte nicht geändert sein
        self.assertEqual(original_mtime, new_mtime)

    def test_writeRuntimeState_updates_changed(self):
        """
        Test: writeRuntimeState() aktualisiert bei Änderungen.
        """
        service = FileAnalysisService(str(self.result_file))
        
        state1 = {"progress": 50}
        service.writeRuntimeState("face_match", "progress", state1)
        
        state2 = {"progress": 75}
        service.writeRuntimeState("face_match", "progress", state2)
        
        state_path = service._runtime_state_path("face_match", "progress")
        with state_path.open("r") as f:
            content = json.load(f)
        self.assertEqual(content["progress"], 75)

    def test_json_format_unchanged(self):
        """
        Test: JSON-Format bleibt kompatibel (pretty-printed mit sort_keys).
        """
        service = FileAnalysisService(str(self.result_file))
        
        result = {"z_key": "z", "a_key": "a", "nested": {"sub": "value"}}
        service.writeLatestResult(result)
        
        # Lese als Text und prüfe Format
        with self.result_file.open("r") as f:
            content = f.read()
        
        # Sollte Indentation haben (pretty)
        self.assertIn("  ", content)
        # Sollte sortiert sein (a_key vor z_key)
        self.assertLess(content.find("a_key"), content.find("z_key"))

    def test_write_error_handling(self):
        """
        Test: Schreibfehler werden korrekt behandelt und zurückgegeben.
        """
        # Erstelle Service mit read-only Verzeichnis (unmöglich zu schreiben)
        read_only_file = Path("/root/no_permission_file.json")
        service = FileAnalysisService(str(read_only_file))
        
        result = {"key": "value"}
        # Dies sollte False zurückgeben (Permission Denied)
        # Hinweis: In Test-Environment kann dies variieren
        # Daher testen wir mit dem normalen Pfad aber ungültigem Input
        success = service.writeLatestResult(None)  # type: ignore
        self.assertFalse(success)

    def test_readLatestResult_after_write(self):
        """
        Test: readLatestResult() liest korrekt nach writeLatestResult().
        """
        service = FileAnalysisService(str(self.result_file))
        
        original = {"key": "value", "count": 42}
        service.writeLatestResult(original)
        
        read_back = service.readLatestResult()
        self.assertEqual(read_back["key"], "value")
        self.assertEqual(read_back["count"], 42)

    def test_readCheckFindings_after_write(self):
        """
        Test: readCheckFindings() liest korrekt nach writeCheckFindings().
        """
        service = FileAnalysisService(str(self.result_file))
        
        findings = {"entries": [1, 2, 3]}
        service.writeCheckFindings("dimension_issues", findings)
        
        read_back = service.readCheckFindings("dimension_issues")
        self.assertEqual(read_back["entries"], [1, 2, 3])

    def test_readRuntimeState_after_write(self):
        """
        Test: readRuntimeState() liest korrekt nach writeRuntimeState().
        """
        service = FileAnalysisService(str(self.result_file))
        
        state = {"status": "running", "progress": 50}
        service.writeRuntimeState("analysis", "status", state)
        
        read_back = service.readRuntimeState("analysis", "status")
        self.assertEqual(read_back["status"], "running")
        self.assertEqual(read_back["progress"], 50)

    def test_multifile_independent_writes(self):
        """
        Test: Mehrere Dateien werden unabhängig verwaltet.
        """
        service = FileAnalysisService(str(self.result_file))
        
        # Schreibe verschiedene Findings
        findings1 = {"type": "dimension_issues", "count": 5}
        findings2 = {"type": "duplicate_faces", "count": 3}
        
        service.writeCheckFindings("dimension_issues", findings1)
        service.writeCheckFindings("duplicate_faces", findings2)
        
        # Beide sollten unabhängig existieren
        dim_path = service._finding_path("dimension_issues")
        dup_path = service._finding_path("duplicate_faces")
        
        self.assertTrue(dim_path.exists())
        self.assertTrue(dup_path.exists())
        
        # Inhalte sollten unterschiedlich sein
        with dim_path.open("r") as f:
            dim_content = json.load(f)
        with dup_path.open("r") as f:
            dup_content = json.load(f)
        
        self.assertEqual(dim_content["count"], 5)
        self.assertEqual(dup_content["count"], 3)

    def test_unknown_findings_storage_format_falls_back_to_json(self):
        service = FileAnalysisService(str(self.result_file), findings_storage_format="sqlite")

        self.assertEqual(service._findings_storage_format, "json")

    def test_appendCheckFindingEntries_adds_entries_to_existing_json_payload(self):
        service = FileAnalysisService(str(self.result_file))
        service.writeCheckFindings(
            "duplicate_faces",
            {
                "status": "running",
                "count": 1,
                "entries": [{"id": 1}],
            },
        )

        success = service.appendCheckFindingEntries(
            "duplicate_faces",
            [{"id": 2}, {"id": 3}],
        )

        self.assertTrue(success)
        read_back = service.readCheckFindings("duplicate_faces")
        self.assertEqual(read_back["count"], 3)
        self.assertEqual([entry["id"] for entry in read_back["entries"]], [1, 2, 3])

    def test_appendCheckFindingEntries_creates_payload_when_missing(self):
        service = FileAnalysisService(str(self.result_file))

        success = service.appendCheckFindingEntries("dimension_issues", [{"id": 1}])

        self.assertTrue(success)
        read_back = service.readCheckFindings("dimension_issues")
        self.assertEqual(read_back["count"], 1)
        self.assertEqual(read_back["entries"], [{"id": 1}])

    def test_appendCheckFindingEntries_preserves_parallel_updates(self):
        from concurrent.futures import ThreadPoolExecutor

        service = FileAnalysisService(str(self.result_file))

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda entry_id: service.appendCheckFindingEntries(
                    "duplicate_faces",
                    [{"id": entry_id}],
                ),
                range(40),
            ))

        self.assertTrue(all(results))
        read_back = service.readCheckFindings("duplicate_faces")
        self.assertEqual(read_back["count"], 40)
        self.assertEqual(
            sorted(entry["id"] for entry in read_back["entries"]),
            list(range(40)),
        )

    def test_parallel_runtime_writes_use_independent_temp_files(self):
        from concurrent.futures import ThreadPoolExecutor

        service = FileAnalysisService(str(self.result_file))

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda progress: service.writeRuntimeState(
                    "checks_progress",
                    "user_dimension_issues",
                    {"progress": progress},
                ),
                range(40),
            ))

        self.assertTrue(all(results))
        read_back = service.readRuntimeState("checks_progress", "user_dimension_issues")
        self.assertIn(read_back["progress"], range(40))
        self.assertEqual(
            list(service._runtime_dir.glob("*.tmp")),
            [],
        )

    def test_appendCheckFindingEntries_preserves_parallel_process_updates(self):
        from concurrent.futures import ProcessPoolExecutor

        service = FileAnalysisService(str(self.result_file))
        args = [(str(self.result_file), entry_id) for entry_id in range(20)]

        with ProcessPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(_append_finding_entry_from_process, args))

        self.assertTrue(all(results))
        read_back = service.readCheckFindings("duplicate_faces")
        self.assertEqual(read_back["count"], 20)
        self.assertEqual(
            sorted(entry["id"] for entry in read_back["entries"]),
            list(range(20)),
        )


if __name__ == "__main__":
    unittest.main()
