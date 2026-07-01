from pathlib import Path


def _concept() -> str:
    return Path("dev/status-concept-integrated.md").read_text(encoding="utf-8")


def test_status_concept_defines_state_ownership_and_mode_identity():
    concept = _concept()

    assert "Zustandsbesitz und Reconnect-Regeln" in concept
    assert "`mode` ist Teil der Identität des Zustands" in concept
    assert "`scan` und `findings` dürfen nicht gegenseitig als Fortsetzung interpretiert werden" in concept
    assert "Backend-Progress darf nicht unbesehen in die UI geschrieben werden" in concept
    assert "Progress zunächst lesen können, ohne ihn sofort anzuwenden" in concept
    assert "InsightFace-Prozesse und darauf aufbauende Bereinigungen" in concept
    assert "`immediate` verwendet nur den aktiven Laufzustand" in concept
    assert "`save_only` schreibt eine persistente Fundliste" in concept
    assert "`findings` arbeitet ausschließlich eine explizit ausgewählte persistente Fundliste ab" in concept
    assert "Eine gespeicherte Fundliste wird von `immediate` oder `save_only` nicht gelesen" in concept


def test_status_concept_scopes_stop_requested_to_operation_and_mode():
    concept = _concept()

    assert "`stop_requested` gilt nur für die Operation" in concept
    assert "Ein `stop_requested` aus einem Scan darf nicht als Stop-Zustand einer Fundlisten-Abarbeitung dargestellt werden" in concept
    assert "`stop_requested` wird nur im passenden `operation`/`mode`-Kontext angezeigt" in concept


def test_status_concept_covers_prioritized_operation_review_list():
    concept = _concept()

    expected_regressions = [
        "Checks + gespeicherte Fundliste bleibt nach View-Wechsel in `findings`",
        "Checks + gespeicherte Fundliste zeigt keinen Scan-Stop-Zustand",
        "FaceMatch + gespeicherte Fundliste wird analog gegen Scan-/Suchprogress geprüft",
        "Cleanup und File-Analysis übernehmen persistierten Runtime-State nur für ihre eigene Operation",
    ]
    for expected in expected_regressions:
        assert expected in concept


def test_status_concept_keeps_mode_matrix_for_checks_and_face_match_findings():
    concept = _concept()

    assert "### 3. Gespeicherte Fundliste abarbeiten" in concept
    assert "| `operation` | `checks` |" in concept
    assert "| `operation` | `face_match` |" in concept
    assert "| `mode` | `findings` |" in concept
    assert "| Progress | `entries` |" in concept


def test_status_concept_defines_stale_stopping_as_non_blocking():
    concept = _concept()

    assert "Ein `running: true`-Status mit `phase: \"stopping\"`" in concept
    assert "`checks:progress_stopping`, `face_match:progress_stopping` oder `cleanup:progress_stopping`" in concept
    assert "darf eine neue Operation nicht dauerhaft blockieren" in concept
    assert "älter als das definierte Stale-Timeout" in concept
    assert "gilt er nicht mehr als blockierende laufende Operation" in concept


def test_status_concept_defines_saved_findings_as_source_of_truth_after_save_only_run():
    concept = _concept()

    assert "Persistierte Fundlisten und abgeschlossener Progress" in concept
    assert "Runtime-Progress ist nicht die Quelle der Wahrheit" in concept
    assert "Die Fundliste selbst ist persistent" in concept
    assert "`progress.findings_count` nicht als aktuelle Fundlistenanzahl" in concept
    assert "die aktuelle Anzahl aus der gespeicherten Fundliste ableiten" in concept
    assert "älterer `face_match_progress` oder `checks_progress` noch eine historische Fundzahl enthält" in concept


def test_status_concept_defines_save_only_findings_streaming_persistence():
    concept = _concept()

    assert "Save-only-Scans dürfen gefundene Fundlisten-Einträge nicht nur im Worker-Speicher halten" in concept
    assert "Während des laufenden `scan` werden neue Fundlisten-Einträge debounced in die persistente Fundliste geschrieben" in concept
    assert "Bei `stopped`, `failed` oder `finished` wird die aktuell bekannte Fundliste erzwungen geschrieben" in concept
    assert "Nur ein expliziter Resume eines Save-only-Scans lädt die bereits persistierte Fundliste derselben Aktion und hängt neue Treffer daran an" in concept
    assert "Resume-Skip-Listen müssen aus dem Resume-Cursor und aus den bereits persistierten Einträgen aufgebaut werden" in concept
    assert "`findings_count` eines Save-only-Scans beschreibt die Anzahl der persistierten offenen Fundlisten-Einträge" in concept


def test_status_concept_lists_recent_runtime_regressions():
    concept = _concept()

    assert "Abgeschlossener FaceMatch-save-only-Progress nutzt die aktuelle gespeicherte Fundlistenanzahl" in concept
    assert "Ein stale Stop-Zustand mit `running: true` blockiert nach Timeout keine neue Operation mehr" in concept
    assert "FaceMatch-Fundlistenposition bleibt bei `Nächster` und erfolgreichem `Übernehmen` monoton" in concept
    assert "FaceMatch blendet den Scan-Fortschrittsbalken bei `phase: finished` aus" in concept
    assert "darf keinen laufenden Fortschrittsbalken nur wegen vorhandener `progress`-Werte" in concept
    assert "FaceMatch beendet den UI-Loading-/Stop-Zustand auch dann" in concept
    assert "Start-/Fortsetzungsantwort final mit `running: false` zurückkommt" in concept
    assert "FaceMatch-Fundzustände zeigen keine generische Abschlussmeldung" in concept
    assert "FaceMatch-Ergebnisaktionen sperren Transfer-, Umbenennungs-, Vorschlags- und Weiter-Buttons sofort" in concept
    assert "Automatisch erfolgreich übertragene Treffer dürfen den Fundlisten-Zähler nicht erhöhen" in concept


def test_status_concept_defines_monotonic_face_match_findings_review_position():
    concept = _concept()

    assert "Die angezeigte Fundlistenposition ist ein eigener UI-Review-Zustand" in concept
    assert "`entries.current` darf nach `Nächster` oder nach erfolgreichem `Übernehmen` nicht sinken" in concept
    assert "Nach erfolgreichem `Übernehmen` zählt der entfernte Eintrag als erledigt" in concept
    assert "erledigte Einträge + aktuelle Position in der verbleibenden Liste" in concept
    assert "Legacy-Felder wie `transferred_count` oder `findings_count` dürfen die laufende Fundlistenposition nicht zurücksetzen" in concept


def test_status_concept_defines_live_face_match_partial_scan_progress_base():
    concept = _concept()

    assert "interaktiven Live-Scan startet die UI technisch einen neuen Teilscan mit erweiterten Skip-Listen" in concept
    assert "Dieser Teilscan darf im Backend wieder bei `status.progress.current = 0` beginnen" in concept
    assert "Die UI muss den bereits angezeigten Fortschritt als lokale Basis erhalten" in concept
    assert "sichtbare Fortschrittszähler nicht zurückspringen" in concept


def test_status_concept_requires_preparing_status_for_file_list_scans():
    concept = _concept()

    assert "Dateilistenbasierte Scan-Aktionen müssen bereits vor dem eigentlichen Dateilauf eine vorbereitende Statusmeldung setzen" in concept
    assert "Gesichtsabgleich-Aktionen, die Bilddateien auflisten" in concept
    assert "`listImageFiles`-Schritt nicht als hängender Start erscheint" in concept
