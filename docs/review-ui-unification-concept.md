# Review UI Unification Concept

## Ziel

Die verschiedenen Review-Ansichten sollen schrittweise vereinheitlicht werden, ohne die fachliche Logik in die GUI zu verlagern. Das Backend bleibt fuer Status, Prozesszustand, Resume-Faehigkeit, erlaubte Aktionen und fachliche Entscheidungen verantwortlich. Die UI rendert diese Informationen einheitlich und loest nur explizit angebotene Aktionen aus.

Betroffene Bereiche sind insbesondere:

- Gesichtsabgleich und unbekannte Gesichter mit InsightFace
- Personen-/Gruppenzuordnung aus Synology Photos
- Pruefansichten unter Checks
- Face-Frame-/Bounding-Box-Reviews
- Findings mit Speichern, Speichern als, Ueberspringen, Fortsetzen und Weitersuchen

## Ausgangslage

Es gibt bereits gemeinsame Bausteine, aber keine konsequent zentrale Review-Schicht:

- Die Status-Matrix ist die gemeinsame Absicherung fuer Prozesszustand, Resume und UI-Erwartungen.
- `RecognitionFindingsReview.vue` kapselt bereits einen Teil der InsightFace-Review-Darstellung.
- `ChecksFacePane.vue` wird fuer Vergleichs- und Pruefpanes wiederverwendet.
- `FaceMatchView.vue`, `ChecksView.vue` und `FaceFrameFindingsTable.vue` enthalten weiterhin eigene Review-Ablaeufe, Aktionsleisten, Auswahlzustand und teils eigene Preview-/Personenlogik.
- Mixins koordinieren Statusabruf und UI-Zustand, duerfen aber keine fachliche Wahrheit ueber laufende Aktionen oder erlaubte Mutationen rekonstruieren.

Die Folge ist, dass Basisfunktionen wie Finden, Person auswaehlen, neue Person anlegen, Speichern, Speichern als, Weitersuchen und Fortsetzen je Prozess unterschiedlich abgesichert sind.

## Prinzipien

1. Backend ist die Quelle der Wahrheit.
   Prozessidentitaet, Phase, aktueller Fund, Zielauswahl, erlaubte Mutationen, Resume-Cursor und Fehlerzustand kommen aus dem Backend.

2. Die UI hat nur Darstellungs- und Eingabezustand.
   Sie darf Filter, aktuell markierte Auswahl oder sichtbare Tabs halten, aber keine laufende Aktion, Counter, Resume-Faehigkeit oder erlaubte Prozessaktion ableiten, wenn das Backend diese Felder liefert.

3. Jeder Review-Prozess beschreibt seine Faehigkeiten explizit.
   Ob alternative Personenwahl, Gruppenauswahl, Neuanlage, Speichern als, Ueberspringen oder Weitersuchen moeglich ist, wird pro Review-Status geliefert und in der Matrix geprueft.

4. Vereinheitlichung erfolgt inkrementell.
   Bestehende Endpunkte und Komponenten werden nicht in einem grossen Umbau ersetzt. Zuerst entsteht ein gemeinsamer Vertrag, danach gemeinsame UI-Bausteine, danach werden einzelne Views angepasst.

## Backend-Vertrag

Langfristig soll jeder Review-Prozess einen normalisierten Review-Status liefern. Der bestehende Prozessstatus bleibt erhalten, wird aber um eine klar abgegrenzte Review-Struktur ergaenzt.

Vorgeschlagene Struktur:

```json
{
  "action": "recognition_analyze_unknown_faces",
  "operation": "face_match_recognition",
  "phase": "review",
  "state": "running",
  "resume_available": true,
  "resume_cursor": "opaque",
  "review": {
    "type": "person_assignment",
    "entry_id": "opaque-entry-id",
    "position": 12,
    "total": 48,
    "source": {
      "kind": "unknown_face",
      "label": "Unbekanntes Gesicht",
      "image_url": "/api/file_image?...",
      "bbox": {
        "left": 0.21,
        "top": 0.18,
        "width": 0.16,
        "height": 0.22,
        "unit": "relative"
      }
    },
    "target": {
      "kind": "photos_person",
      "id": 42923,
      "name": "Teodor Vilippus"
    },
    "candidate_targets": [
      {
        "kind": "photos_person",
        "id": 42923,
        "name": "Teodor Vilippus",
        "score": 0.82
      }
    ],
    "target_selector": {
      "kind": "photos_person_or_group",
      "allow_existing": true,
      "allow_create": true,
      "allow_clear": false
    },
    "allowed_actions": {
      "save": true,
      "save_as": true,
      "skip": true,
      "continue_search": true,
      "mark_outlier": true
    }
  }
}
```

Die Feldnamen sind als Zielbild zu verstehen. Bestehende Endpunkte koennen diese Struktur schrittweise liefern oder serverseitig aus ihren bisherigen Feldern ableiten.

## Gemeinsame UI-Bausteine

Die UI sollte aus kleinen, fachlich neutralen Review-Komponenten bestehen:

- `ReviewShell`
  Titel, Prozessstatus, Zaehler, Fehlerhinweise, Resume-Hinweis und globale Aktionsflaechen.

- `ReviewSplitPane`
  Einheitliche Anzeige von Quelle und Ziel inklusive Preview, Orientierung, Bounding Box, Ladezustand und leerem Zustand.

- `ReviewTargetSelector`
  Auswahl einer vorhandenen Photos-Person oder Photos-Gruppe, Anzeige von Vorschlaegen und optionales Anlegen eines neuen Zielobjekts, wenn das Backend `allow_create` liefert.

- `ReviewActionBar`
  Speichern, Speichern als, Ueberspringen, Weitersuchen, Fortsetzen, Outlier-Markierung und weitere Aktionen ausschliesslich auf Basis von `allowed_actions`.

- Prozessadapter
  Schlanke Adapter pro Prozess, die bestehende Backend-Antworten in die gemeinsamen Component-Props ueberfuehren. Diese Adapter duerfen keine fachlichen Entscheidungen treffen.

## Matrix-Abdeckung

Die Status-Matrix muss breit genug sein, um jede Review-Faehigkeit pro Prozess explizit abzusichern.

Pflichtfaelle pro Review-Prozess:

- kein Fund, Suche laeuft
- Fund vorhanden, vorgeschlagener Zieltreffer vorhanden
- Fund vorhanden, kein Zieltreffer vorhanden
- alternative Person/Gruppe auswaehlbar
- neue Person/Gruppe anlegbar, falls fachlich erlaubt
- Speichern erfolgreich
- Speichern als erfolgreich
- Ueberspringen erfolgreich
- Weitersuchen nach Mutation
- Browser-Neuoeffnung mit Resume-Cursor
- Backend idle ohne Resume-Cursor
- Fehlerzustand mit stabiler Anzeige
- Preview mit Orientierung und Bounding Box

Jeder Matrix-Fall muss mindestens pruefen:

- `action`
- `operation`
- `phase`
- `state`
- `resume_available`
- `resume_cursor`
- `review.type`
- `review.entry_id`
- `review.source`
- `review.target_selector`
- `review.allowed_actions`

Damit sollen Fehler wie "keine laufende Aktion" trotz aktivem Prozess, fehlendes Fortsetzen, fehlende Personenauswahl oder fehlende Neuanlage als Vertragsbruch sichtbar werden.

## Migrationsplan

### Phase 1: Inventar und Vertrag

- Alle Review-Ansichten und ihre Aktionen erfassen.
- Fuer jeden Prozess die unterstuetzten Review-Faehigkeiten dokumentieren.
- Status-Matrix um alle Pflichtfaelle erweitern.
- Bestehende HAR-/Log-Fehler als Regressionen in Matrix- oder Contract-Tests abbilden.

### Phase 2: Gemeinsame Darstellung ohne Verhaltensaenderung

- `ReviewSplitPane` aus bestehenden Preview-Panes herausloesen.
- Orientierung, Bounding Box und Ladezustand zentral behandeln.
- Bestehende Views weiterhin nutzen, aber Preview-Darstellung vereinheitlichen.

### Phase 3: Zielauswahl zentralisieren

- `ReviewTargetSelector` fuer Photos-Personen und Photos-Gruppen einfuehren.
- Neuanlage nur anzeigen, wenn der Backend-Status sie erlaubt.
- Vorschlaege und manuelle Auswahl ueber denselben UI-Baustein fuehren.

### Phase 4: Aktionslogik zentralisieren

- `ReviewActionBar` einfuehren.
- Buttons nur aus `allowed_actions` ableiten.
- Speichern, Speichern als, Ueberspringen und Weitersuchen pro Prozess ueber Backend-Mutationen ausloesen.

### Phase 5: Prozessadapter vereinfachen

- Doppelte Mixin- und View-Logik entfernen.
- Prozessadapter auf reine Feldabbildung reduzieren.
- Views behalten nur Navigation, Layout und prozessspezifische Einbettung.

## Reihenfolge der Kandidaten

1. `RecognitionFindingsReview.vue`
   Bereits nah am Zielmodell und geeignet als erster Adapter fuer `ReviewShell`, `ReviewSplitPane` und `ReviewTargetSelector`.

2. `FaceFrameFindingsTable.vue`
   Gut geeignet, um Preview, Bounding Box und Review-Aktionen zu vereinheitlichen.

3. `ChecksFacePane.vue`
   Als Basis fuer `ReviewSplitPane` geeignet, muss aber von Check-spezifischen Entscheidungen getrennt werden.

4. `FaceMatchView.vue`
   Groesster Sonderfall. Sollte erst nach stabilen gemeinsamen Bausteinen umgestellt werden.

## Risiken und Gegenmassnahmen

- Risiko: Ein zentraler Renderer wird zu allgemein und verdeckt fachliche Unterschiede.
  Gegenmassnahme: Gemeinsame Komponenten bleiben klein; fachliche Unterschiede bleiben im Backend-Vertrag und in Prozessadaptern sichtbar.

- Risiko: Bestehende Prozesse verlieren Sonderfunktionen.
  Gegenmassnahme: Jede Funktion wird vor der Umstellung in der Matrix als Faehigkeit festgehalten.

- Risiko: UI rekonstruiert wieder Backend-Zustand.
  Gegenmassnahme: Contract-Tests pruefen, dass Resume, laufende Aktion und erlaubte Aktionen aus Backend-Feldern stammen.

- Risiko: Vorschau, Orientierung oder Bounding Box unterscheiden sich zwischen Views.
  Gegenmassnahme: Ein gemeinsamer Preview-Baustein und Tests fuer Orientierung plus Bounding-Box-Koordinaten.

## Akzeptanzkriterien

- Alle Review-Prozesse zeigen laufende Aktion, Resume und Fehlerzustand konsistent an.
- Jeder Fund kann, sofern vom Backend erlaubt, gespeichert, als andere Person/Gruppe gespeichert, uebersprungen oder weitergesucht werden.
- Neue Personen/Gruppen werden nur angeboten, wenn der jeweilige Backend-Status dies erlaubt.
- Preview-Orientierung und Bounding Box stimmen in allen Review-Ansichten ueberein.
- Browser-Neuoeffnung erkennt fortsetzbare Review-Prozesse unabhaengig von der gerade vorausgewaehlten UI-Aktion.
- Matrix- und Contract-Tests decken die Review-Faehigkeiten breit ab.
