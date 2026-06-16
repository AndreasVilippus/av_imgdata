# Konzept: Gesichtswiedererkennung mit InsightFace auf Basis von Photos-Personen

## Bereich

`Bereinigung → Gesichtswiedererkennung aufbauen`

## Ziel

Im Paket **AV_ImgData** soll eine Gesichtswiedererkennung entstehen, die zunächst ausschließlich auf den bereits in **Synology Photos** vorhandenen Personen und deren zugeordneten Gesichtern basiert.

Die Funktion soll bekannte Photos-Personen als Referenzbasis verwenden, daraus InsightFace-Embeddings erzeugen und unbekannte Photos-Gesichter gegen diese Profile vergleichen.

Die Implementierung muss sich in die vorhandene Paketstruktur einfügen:

```text
app/main.py
→ src/api/imgdata_api.py
→ src/imgdata.py / ImgDataService
→ src/services/*
→ FileAnalysisService / SQLite / PersistedFindingsRepository
→ Vue App.vue / CleanupView / cleanupMixin oder FaceMatchView
```

Keine automatische Personenanlage, keine automatische Korrektur bestehender Photos-Zuordnungen, kein Schreiben ohne Vorschau.

---

## Aktueller Bestand, der genutzt werden soll

### FastAPI- und Service-Struktur

`app/main.py` erzeugt die FastAPI-App, setzt `src/` in den Importpfad und bindet den Router aus `api.imgdata_api` ein. Neue API-Funktionen sollen deshalb in `src/api/imgdata_api.py` ergänzt werden.

`src/api/imgdata_api.py` verwendet bereits:

```python
router = APIRouter(prefix="/api")
IMGDATA = ImgDataService(SESSION_MANAGER)
```

Neue Endpunkte sollen dieselben Helfer nutzen:

```text
_prepare_session_request(request)
_read_request_body(request)
_run_backend_call(...)
_operation_exception_response(...)
_session_exception_response(...)
backend_debug_log(...)
```

### ImgDataService als Fassade

`src/imgdata.py` ist die zentrale Orchestrierungsschicht. In `ImgDataService.__init__()` sind bereits eingebunden:

```text
self.photos
self.files
self.metadata_parser
self.face_matcher
self.file_analysis
self.face_match_findings
self.runtime_operations
self.runtime_state
self.checks_workflow
self.face_match_workflow
self.write_locks
```

Die Wiedererkennung soll als neuer Service an dieser Stelle eingebunden werden:

```python
from services.face_recognition_service import FaceRecognitionService
from services.reference_outlier_service import ReferenceOutlierService

self.face_recognition = FaceRecognitionService(self)
self.reference_outliers = ReferenceOutlierService(self)
```

Die eigentliche Logik darf nicht direkt in `imgdata_api.py` landen.

### Bestehendes Face-Matching

`src/api/imgdata_api.py` kennt bereits die API-Action:

```text
/api/face_matching_action
```

und akzeptiert u. a. die Action:

```text
search_missing_faces_insightface
```

Außerdem existieren:

```text
/api/face_matching_progress
/api/face_matching_stop
/api/face_matching_findings_status
/api/face_assign_match
```

Für die Gesichtswiedererkennung gibt es zwei Einbindungsbereiche:

1. Profilaufbau und Referenz-Ausreißerprüfung bleiben im Cleanup-Menü, weil sie vorbereitende Bereinigungs-/Prüffunktionen sind.
2. Vorschläge für unbekannte Gesichter gehören in den bestehenden Face-Matching-Workflow, weil dort bereits die Entscheidung, Fundlisten-Verarbeitung und Photos-Zuordnung stattfinden.

Dabei bleiben zwei Fälle getrennt:

```text
search_missing_faces_insightface  = zusätzliche, in Photos noch fehlende Gesichter im Bild finden
recognition_analyze_unknown_faces = vorhandene Photos-Gesichter ohne Namen einer Person zuordnen
```

Empfehlung:

```text
Phase 1: Profilaufbau und Ausreißerprüfung über Cleanup-Actions starten.
Phase 2: Wiedererkennungsvorschläge im Face-Match-Bereich anzeigen/anwenden.
```

### Bestehende Findings und Runtime-State

`FileAnalysisService` nutzt SQLite und speichert Findings über `PersistedFindingsRepository`. Vorhandene Methoden:

```text
readCheckFindings(...)
writeCheckFindings(...)
appendCheckFindingEntries(...)
deleteCheckFindings(...)
readRuntimeState(...)
writeRuntimeState(...)
```

`ChecksWorkflowService` bietet bereits:

```text
build_scan_payload(...)
write_findings(...)
get_finding_entries(...)
get_candidate_paths(... changed_since_days ...)
```

Für die erste Implementierung sollen Wiedererkennungsdaten nicht sofort in neue Spezialtabellen geschrieben werden, sondern als `persisted_findings` und `app_state` starten. Relationale Tabellen folgen erst, wenn die Datenmenge oder Auswertung dies erfordert.

---

## Neue Finding-Typen

```text
recognition_profiles
recognition_reference_outliers
recognition_suggestions
recognition_profile_quality
```

### recognition_profiles

Speichert den aktuellen Stand der gebildeten Personenprofile als Metadaten/Fundliste.

### recognition_reference_outliers

Speichert mögliche falsche Referenzgesichter innerhalb bestehender Photos-Personen.

### recognition_suggestions

Speichert Vorschläge für unbekannte Photos-Gesichter.

### recognition_profile_quality

Speichert Personen mit zu wenigen, zu schlechten oder widersprüchlichen Referenzgesichtern.

---

## UI-Einbindung

### Aktueller UI-Aufbau

`ui/src/App.vue` bindet aktuell u. a. ein:

```text
StatusView
FaceMatchView
ChecksView
CleanupView
ConfigurationView
ExternalLibrariesView
DatabaseListsView
```

`CleanupView.vue` enthält aktuell einen Action-Selector mit nur einer Action:

```text
normalize_names
```

`cleanupMixin.js` steuert:

```text
selectedCleanupAction
cleanupTargets
cleanupProgress
cleanup_start
cleanup_progress
cleanup_stop
Polling
```

### Neue Cleanup-Actions

```text
recognition_build_profiles
recognition_check_reference_outliers
recognition_rebuild_profiles
```

### Empfohlene Komponenten

```text
ui/src/components/cleanup/RecognitionProfileOptions.vue
ui/src/components/cleanup/RecognitionOutlierFindingsTable.vue
ui/src/components/cleanup/RecognitionSuggestionTable.vue
ui/src/components/cleanup/InsightFaceRecognitionOptions.vue
```

`CleanupView.vue` sollte nur die passende Unterkomponente je Action anzeigen.

### UI-State in cleanupMixin.js

```javascript
recognitionOptions: {
  include_hidden_persons: false,
  include_unnamed_persons: false,
  min_faces_per_person: 3,
  exclude_outliers: true,
  changed_since_days: 30,
  safe_score: 0.55,
  review_score: 0.45,
  min_margin: 0.08,
  insightface: {
    profile: 'standard',
    det_size: [640, 640],
    det_thresh: 0.5,
    max_num: 0,
    min_face_width_ratio: 0.015,
    min_face_height_ratio: 0.015,
  },
}
```

### Verbindlicher UI-Vertrag

Die Oberfläche verwendet die bereits eingeführten Standards aus `ChecksView`,
`FaceMatchView` und der Gesichtsrahmen-Standardisierung. Es werden keine eigenen
abweichenden Formular-, Status- oder Vorschaukonzepte eingeführt.

Bezeichnung:

```text
In der UI wird "Wiedererkennungsprofile aufbauen" statt "Gesichtslernen"
verwendet. InsightFace wird nicht trainiert; aus vorhandenen Embeddings werden
interne Personenprofile gebildet.
```

Cleanup-Actions und Reihenfolge:

```text
recognition_build_profiles
recognition_check_reference_outliers
```

`recognition_rebuild_profiles` ist kein eigener dauerhaft sichtbarer Menüpunkt.
Ein erneuter vollständiger Aufbau wird über `recognition_build_profiles` und
die Option `rebuild_all` gestartet.

#### Betriebsarten

Die prüfende Action `recognition_check_reference_outliers` verwendet dieselben
drei Betriebsarten wie die Gesichtsrahmen-Standardisierung:

```text
immediate  = Scan starten und beim ersten manuell zu prüfenden Fund anhalten
save_only  = Scan vollständig ausführen und Funde nur persistent speichern
findings   = bestehende persistente Fundliste abarbeiten
```

`immediate` verwendet nur den aktiven Laufzustand des aktuellen Reviews. Es
liest keine alte persistente Fundliste als Arbeitsliste und schreibt auch keine
persistente Fundliste. Ein internes Fortsetzen nach einer manuellen Entscheidung
ist nur mit `resume_existing = true` zulässig und bezieht sich ausschließlich
auf diesen aktiven Laufzustand.

Der Profilaufbau verwendet keine manuelle Einzelprüfung während des Laufs. Er
schreibt ausschließlich interne Profile und Qualitäts-Findings. Für ihn gelten:

```text
incremental = vorhandene passende Profile und Embeddings wiederverwenden
rebuild_all = Profile für alle ausgewählten Personen neu aufbauen
```

#### Entscheidung und automatische Verarbeitung

Für Wiedererkennungsvorschläge:

```text
review_all = jeder Vorschlag muss manuell entschieden werden
safe_only  = decision=accept wird ausgewählt; review/ambiguous/reject bleibt offen
```

Eine automatische Auswahl ist noch keine Photos-Schreiboperation. Eine
Zuweisung nach Photos erfolgt nur über Apply und nur auf Basis eines
persistierten Vorschlags.

Für Referenz-Ausreißer:

```text
review_all        = jeder Ausreißer muss manuell entschieden werden
exclude_confirmed = eindeutig bestätigte Ausreißer intern automatisch ausschließen
```

Ausreißer-Aktionen ändern Synology Photos niemals.

#### Layout

Der erste Panel enthält immer:

```text
- Bereichstitel und Beschreibung
- Action-Selector
- action-spezifische Optionen
- Start/Stop-Schaltfläche
- Schema-v1-Status mit Fortschritt, Zählern und aktuellem Kontext
```

Eine manuelle Prüfung wird als zweites, gleichrangiges
`panel face-match-split-panel` unterhalb des Action-Panels dargestellt. Es wird
keine vollständige Ergebnistabelle während der Prüfung angezeigt.

Referenz-Ausreißer:

```text
links:  verdächtiges Referenzgesicht mit Photos-Rahmen
rechts: Medoid beziehungsweise repräsentatives Gesicht des Personenprofils
Mitte:  Ausschließen-Icon
Zusatzaktionen: als Referenz bestätigen, später prüfen, ignorieren
```

Wiedererkennungsvorschlag:

```text
links:  unbekanntes Photos-Gesicht
rechts: vorgeschlagene bestehende Person mit repräsentativem Profilbild
Mitte:  face_to_left.png für die Zuweisung zur vorgeschlagenen Person
Zusatzaktionen: weiteren Kandidaten wählen, überspringen
```

Die Vorschau zeigt standardmäßig den Gesichtsausschnitt. Ein Umschalter kann
analog zum Gesichtsabgleich auf das vollständige Bild wechseln.

#### Zustände und Listenfortschritt

Persistierte Findings behalten während einer Prüfung eine feste Gesamtzahl.
Entscheidungen erhöhen `status.progress.current`; sie verringern nicht
`status.progress.total`.

```text
selection_state: review | selected | skipped
review_state:    suspected | confirmed | excluded | needs_review | ignored
write_state:     pending | written | skipped | stale | failed | internal_only
decision:        accept | review | ambiguous | reject
```

`stale` bedeutet, dass sich das Photos-Gesicht seit der Analyse geändert hat.
Die UI zeigt den Fund als nicht anwendbar und verlangt einen neuen Scan.

#### Optionen und Formularstandard

Alle Auswahlfelder verwenden `sm-form-select`. Alle Zahlenfelder verwenden
`sm-form-input sm-form-number-input` und besitzen sichtbare Titel, Grenzen,
Schrittweite und bei erklärungsbedürftigen Werten einen `sm-form-hint`.
Schwellwerte werden im Abschnitt "Erweiterte Bewertung" zusammengefasst.

Große Profil- und Fundlisten werden nicht vollständig im Action-Panel
gerendert. Spätere Übersichtslisten müssen serverseitige Paginierung sowie
Suche/Filter nach Person, Zustand und Entscheidung unterstützen.

#### Fehler- und Verfügbarkeitszustände

Vor dem Start wird geprüft:

```text
- InsightFace-Paket installiert
- aktives Modell enthält Detection und Recognition
- gemeinsamer Photos-Ordner erreichbar
- Photos-Personen und zugehörige Faces lesbar
```

Fehlende Voraussetzungen werden als expliziter Status angezeigt. Eine
Wiedererkennungsaction darf niemals auf eine andere Cleanup-Action
zurückfallen.

---

## InsightFace-Erweiterung

### Bestehender Detector

Vorhanden:

```text
src/services/face_detector.py
```

Die Klasse `InsightFaceDetector` lädt aktuell:

```python
FaceAnalysis(allowed_modules=["detection"])
```

und gibt nur Detektionsdaten zurück:

```text
x, y, w, h, bbox, center, score
```

### Neuer Embedder

Für Wiedererkennung wird ein zusätzlicher Service benötigt:

```text
src/services/face_embedder.py
```

oder eine Erweiterung der bestehenden Datei:

```python
class InsightFaceEmbedder:
    def __init__(self, model_name="", model_root=None, ctx_id=-1, det_size=(640, 640), det_thresh=0.5): ...
    def embed_matched_face(self, image_path: Path, photos_bbox: BoundingBox) -> dict: ...
    def detect_and_embed(self, image_path: Path) -> List[dict]: ...
```

Wichtig: Für Embeddings darf `allowed_modules` nicht nur `detection` enthalten. Entweder:

```python
FaceAnalysis(allowed_modules=["detection", "recognition"])
```

oder kein `allowed_modules`, wenn das Modellpaket korrekt ist.

### Matching Photos-Rahmen → InsightFace-Face

Bei bekannten Photos-Gesichtern soll nicht irgendein InsightFace-Face verwendet werden, sondern das erkannte InsightFace-Gesicht, das zum Photos-Rahmen passt.

Dafür wird wiederverwendet:

```text
services.bbox_normalizer.from_photos(...)
services.face_matcher.compute(...)
```

Ablauf:

```text
1. Photos-Face mit from_photos(...) in BoundingBox umwandeln.
2. InsightFace alle Gesichter im Bild erkennen lassen.
3. InsightFace-Bounding-Boxes in BoundingBox umwandeln.
4. IoU berechnen.
5. Face mit höchster IoU wählen.
6. Nur verwenden, wenn IoU >= threshold, sonst Finding `recognition_profile_quality` erzeugen.
```

---

## Datenfluss für Profilaufbau

```text
PhotosHandler / Photos DB/API
      │
      ├── Personenliste
      ├── Faces je Person
      ├── Bildpfade
      │
BBox-Normalisierung
      │
      ├── Photos bbox → BoundingBox
      │
InsightFaceEmbedder
      │
      ├── detect + recognition embedding
      │
EmbeddingCache
      │
      ├── pro face_id / bbox_hash / model_version
      │
ReferenceOutlierService
      │
      ├── mögliche Ausreißer
      │
PersonProfileBuilder
      │
      ├── Centroid / Medoid
      │
PersistedFindings + AppState
```

---

## Datenfluss für unbekannte Gesichter

```text
Photos Unknown Faces
      │
      ├── face_id / image_id / bbox / image_path
      │
InsightFaceEmbedder
      │
      ├── Embedding des unbekannten Faces
      │
FaceRecognitionMatcher
      │
      ├── Vergleich gegen Personenprofile
      │
DecisionService
      │
      ├── accept / review / ambiguous / reject
      │
PersistedFindings recognition_suggestions
      │
      ├── UI-Vorschau
      │
Apply
      │
      ├── face_assign_match oder PhotosHandler-Zuordnung
```

---

## Persistence-Strategie

### Phase 1: JSON in app_state und persisted_findings

Embeddings sind groß. Für den Anfang:

```text
app_state:
- recognition:embedding_cache:<hash>
- recognition:profile:<person_id>:<model_key>

persisted_findings:
- recognition_profiles
- recognition_reference_outliers
- recognition_suggestions
- recognition_profile_quality
```

Das passt zum bestehenden `FileAnalysisService`, weil dieser `app_state` und `persisted_findings` bereits in SQLite kapselt.

### Phase 2: eigene Repositories

Wenn Performance oder Datenmenge es erfordert:

```text
src/av_imgdata/db/repositories/face_embeddings.py
src/av_imgdata/db/repositories/person_recognition_profiles.py
src/av_imgdata/db/repositories/recognition_suggestions.py
src/av_imgdata/db/repositories/reference_outliers.py
```

Dann Migration in:

```text
src/av_imgdata/db/migrations.py
```

Neue Migration z. B.:

```text
RECOGNITION_EMBEDDINGS_MIGRATION = 6
RECOGNITION_EMBEDDINGS_MIGRATION_NAME = "recognition_embeddings_and_profiles"
```

---

## Finding-Format: Referenzprofil

Finding-Typ:

```text
recognition_profiles
```

Entry:

```json
{
  "person_id": 19431,
  "person_name": "Bea",
  "profile_key": "buffalo_l:640x640:det0.5",
  "reference_count": 42,
  "used_count": 39,
  "outlier_count": 3,
  "quality": "good",
  "intra_person_similarity": 0.62,
  "model_name": "buffalo_l",
  "model_version": "unknown",
  "det_size": [640, 640],
  "status": "active"
}
```

---

## Finding-Format: Referenz-Ausreißer

Finding-Typ:

```text
recognition_reference_outliers
```

Entry:

```json
{
  "outlier_id": "out-001",
  "image_path": "/volume1/photo/Benno/2025/example.jpg",
  "person_id": 19431,
  "person_name": "Bea",
  "face_id": 66485,
  "image_id": 76935,
  "average_similarity": 0.28,
  "similarity_to_centroid": 0.31,
  "nearest_other_person_id": 19432,
  "nearest_other_person_name": "Asta",
  "nearest_other_person_score": 0.49,
  "outlier_score": 0.72,
  "reason": "nearest_other_person_higher",
  "review_state": "suspected",
  "action": "exclude_from_profile",
  "write_state": "internal_only"
}
```

Regel:

```text
Ausreißer-Findings ändern Synology Photos nicht.
Sie steuern nur, ob ein Referenzface in interne Profile einfließt.
```

---

## Finding-Format: Wiedererkennungsvorschlag

Finding-Typ:

```text
recognition_suggestions
```

Entry:

```json
{
  "suggestion_id": "rec-001",
  "image_path": "/volume1/photo/Benno/2025/example.jpg",
  "image_id": 76935,
  "unknown_face_id": 12345,
  "bbox": {"x1": 0.42, "y1": 0.18, "x2": 0.51, "y2": 0.34},
  "best_person_id": 19431,
  "best_person_name": "Bea",
  "best_score": 0.68,
  "second_person_id": 19432,
  "second_person_name": "Asta",
  "second_score": 0.51,
  "score_margin": 0.17,
  "decision": "accept",
  "selection_state": "selected",
  "write_state": "pending",
  "profile_key": "buffalo_l:640x640:det0.5"
}
```

---

## Referenz-Ausreißerprüfung als eigener Prüfpunkt

Die Ausreißerprüfung ist kein Nebeneffekt, sondern eine eigene Prüfung.

Neue Cleanup-Action:

```text
recognition_check_reference_outliers
```

Ablauf:

```text
1. Personenprofile laden oder temporär erzeugen.
2. Embeddings je Person vergleichen.
3. Similarity zur eigenen Person berechnen.
4. Similarity zum eigenen Centroid berechnen.
5. nächste andere Person berechnen.
6. auffällige Faces als Findings speichern.
7. UI zeigt Fundliste.
8. Benutzer bestätigt, ignoriert oder schließt nur intern aus.
```

Review-Status:

```text
suspected
confirmed
excluded
needs_review
ignored
```

Aktionen:

```text
confirm_reference
exclude_from_profile
mark_needs_review
ignore
open_in_photos
```

Der Status wird nicht in Synology Photos geschrieben. Er wird in `persisted_findings` oder später in einer eigenen Tabelle gespeichert und beim Profilaufbau berücksichtigt.

---

## Vergleichslogik

### Profilbildung

Für Phase 1:

```python
centroid = normalize(mean(valid_embeddings))
medoid = embedding with highest average similarity
```

Valid sind:

```text
- nicht excluded
- nicht suspected, wenn exclude_outliers=true
- ausreichend gute Face-/Embedding-Qualität
- passend zum Photos-Rahmen erkannt
```

### Kandidatenvergleich

```python
score = cosine_similarity(candidate_embedding, profile.centroid_embedding)
margin = best_score - second_score
```

Startwerte:

| Entscheidung | Bedingung |
|---|---|
| sicherer Vorschlag | `best_score >= 0.55` und `margin >= 0.08` |
| prüfen | `best_score >= 0.45` und `margin >= 0.04` |
| unklar | `best_score >= 0.45` und `margin < 0.04` |
| ablehnen | `best_score < 0.45` |

Die Werte sind Startwerte und müssen mit der eigenen Photos-Bibliothek kalibriert werden.

---

## API-Erweiterung

### Cleanup-basiert

```http
POST /api/cleanup_start
```

Payload für Profilaufbau:

```json
{
  "action": "recognition_build_profiles",
  "options": {
    "include_hidden_persons": false,
    "include_unnamed_persons": false,
    "min_faces_per_person": 3,
    "exclude_outliers": true,
    "insightface": {
      "profile": "standard",
      "det_size": [640, 640],
      "det_thresh": 0.5,
      "max_num": 0,
      "min_face_width_ratio": 0.015,
      "min_face_height_ratio": 0.015
    }
  }
}
```

Payload für Ausreißerprüfung:

```json
{
  "action": "recognition_check_reference_outliers",
  "options": {
    "min_faces_per_person": 3,
    "outlier_similarity_threshold": 0.35,
    "centroid_threshold": 0.40,
    "conflict_margin": 0.05
  }
}
```

Payload für unbekannte Gesichter im Gesichtsabgleich:

```json
{
  "action": "recognition_analyze_unknown_faces",
  "options": {
    "operation_mode": "immediate",
    "selection_mode": "review_all",
    "changed_since_days": 30,
    "safe_score": 0.55,
    "review_score": 0.45,
    "min_margin": 0.08
  }
}
```

Die bestehende Action `search_missing_faces_insightface` bleibt separat fuer
fehlende zusaetzliche Gesichter im Bild. Sie kann optional `recognize_persons`
nutzen, um ein neu erkanntes fehlendes Gesicht direkt gegen vorhandene
Wiedererkennungsprofile zu pruefen.

### Eigene Apply-Endpunkte

Für Apply und Review sind eigene Endpunkte sinnvoll:

```http
POST /api/recognition_outliers_review
POST /api/recognition_suggestions_apply
POST /api/recognition_findings
```

Review-Payload:

```json
{
  "outlier_id": "out-001",
  "review_state": "excluded",
  "action": "exclude_from_profile"
}
```

Apply-Payload:

```json
{
  "finding_type": "recognition_suggestions",
  "selected_suggestion_ids": ["rec-001", "rec-002"],
  "apply_items": "selected_only"
}
```

Regel:

```text
Apply darf nur persistierte Vorschläge verwenden.
Apply darf nicht neu erkennen, nicht neu scoren und keine zusätzlichen Vorschläge anwenden.
```

---

## Apply nach Photos

Für die Zuweisung eines unbekannten Photos-Gesichts zu einer bestehenden Person soll möglichst bestehende Logik wiederverwendet werden.

Vorhanden:

```text
/api/face_assign_match
```

Diese API liest bereits:

```text
face_id
person_id
person_name
save_mapping
source_name
```

Die Wiedererkennung kann entweder:

1. intern dieselbe ImgDataService-Funktion verwenden, die `face_assign_match` nutzt,
2. oder zunächst UI-seitig den bestehenden Assign-Flow wiederverwenden.

Sicherheitsregel:

```text
Vor Apply muss geprüft werden, ob die unknown_face_id noch existiert und noch nicht anderweitig zugeordnet wurde.
```

Dafür sollen bestehende Schutzfunktionen aus `ImgDataService` genutzt werden:

```text
_readPhotosFaceOnItem(...)
_validatePhotosFaceOnItem(...)
_raisePhotosFaceChanged(...)
_photosFaceWriteLockKey(face_id)
```

---

## Runtime-State und Fortschritt

Neue Runs nutzen denselben Stil wie Cleanup-Progress.

Runtime-State-Key:

```text
runtime:cleanup_progress:<user_key>:recognition_build_profiles
runtime:cleanup_progress:<user_key>:recognition_check_reference_outliers
runtime:cleanup_progress:<user_key>:recognition_analyze_unknown_faces
```

Progress-Payload:

```json
{
  "running": true,
  "action": "recognition_build_profiles",
  "operation_id": "...",
  "revision": 9,
  "persons_scanned": 12,
  "persons_total": 80,
  "faces_scanned": 340,
  "profiles_built": 11,
  "outliers_found": 3,
  "status": {
    "schema_version": 1,
    "progress": {
      "kind": "persons",
      "current": 12,
      "total": 80
    },
    "counters": [
      {"key": "profiles", "value": 11, "label_key": "cleanup:label_profiles", "fallback_label": "Profiles"},
      {"key": "outliers", "value": 3, "label_key": "cleanup:label_outliers", "fallback_label": "Outliers"}
    ]
  }
}
```

`cleanupMixin.js` kann `status.schema_version == 1`, `progress` und `counters` bereits auswerten.

---

## Neue Services

```text
src/services/face_embedder.py
src/services/face_recognition_service.py
src/services/person_profile_builder.py
src/services/reference_outlier_service.py
src/services/face_recognition_matcher.py
src/services/recognition_decision_service.py
```

### FaceRecognitionService

Orchestriert:

```text
- Profilaufbau
- Ausreißerprüfung
- Unknown-Face-Analyse
- Persistieren von Findings
- Apply vorbereiten
```

### FaceEmbedder

Kapselt InsightFace Recognition:

```text
- Modell laden
- detect + embedding
- Photos-BBox gegen InsightFace-BBox matchen
- Embedding-Cache lesen/schreiben
```

### PersonProfileBuilder

```text
- Embeddings sammeln
- Ausreißer ausschließen
- Centroid/Medoid berechnen
- Profilqualität bestimmen
```

### ReferenceOutlierService

```text
- intra-person Similarity
- centroid Similarity
- nearest-other-person Konflikt
- Findings erzeugen
- Review-Status berücksichtigen
```

### FaceRecognitionMatcher

```text
- unbekanntes Embedding gegen Profile vergleichen
- Top-N Treffer liefern
- Score und Margin berechnen
```

---

## Änderungen an bestehenden Dateien

```text
src/imgdata.py
- FaceRecognitionService und ReferenceOutlierService instanziieren
- startCleanupRun/action dispatch erweitern
- Apply-/Review-Methoden ergänzen

src/api/imgdata_api.py
- cleanup_start um neue Actions erweitern
- recognition_outliers_review ergänzen
- recognition_suggestions_apply ergänzen
- recognition_findings ergänzen

src/services/face_detector.py
- InsightFace Detection-Parameter ergänzen
- neuen InsightFaceEmbedder oder Recognition-Modus ergänzen

src/services/bbox_normalizer.py
- Helper für InsightFace-BBox → BoundingBox ergänzen
- bbox_hash helper ergänzen

src/services/face_matcher.py
- compute(...) weiterverwenden
- optional Top-N IoU matching ergänzen

src/services/checks_workflow_service.py
- get_findings_status um neue Typen erweitern oder separate Recognition-Statusmethode bauen

ui/src/views/CleanupView.vue
- action-spezifische Unterkomponenten anzeigen

ui/src/mixins/cleanupMixin.js
- neue selectedCleanupAction Werte
- recognitionOptions
- Payload-Building je Action
```

---

## Implementierungsphasen

### Umsetzungsstand

Die Phasen 1 bis 3 sind im ersten funktionsfähigen Umfang umgesetzt:

```text
- InsightFaceEmbedder lädt Detection und Recognition
- Photos-Personen, Items, Gesichter, Bounding-Boxes und Bildpfade werden gelesen
- InsightFace wird pro Bild nur einmal ausgeführt und das passende Gesicht per IoU gewählt
- Centroid und Medoid werden je Person gebildet
- Profile und Embeddings werden über app_state persistiert
- Profilqualität, Referenz-Ausreißer und Wiedererkennungsvorschläge werden als Findings persistiert
- immediate, save_only und findings folgen dem bestehenden Prüfprinzip
- Referenz-Ausreißer können intern bestätigt, ausgeschlossen, zurückgestellt oder ignoriert werden
- unbekannte Gesichter werden gegen ausreichend große Profile verglichen
- Apply verwendet ausschließlich persistierte ausgewählte Vorschläge
- Apply verwendet die bestehende validierte Photos-Zuordnung mit Write-Lock und Vor-/Nachprüfung
```

Phase 4 mit relationalen Spezialtabellen bleibt eine optionale spätere
Optimierung. Die aktuelle Persistence über `app_state` und
`persisted_findings` entspricht der für den ersten Umfang festgelegten
Strategie.

### Phase 1: Embedding-Grundlage

```text
- InsightFaceEmbedder ergänzen
- Photos-Face → InsightFace-Face per IoU matchen
- Embedding-Cache in app_state oder einfachem Repository speichern
- Recognition-Profil-Findings erzeugen
- keine Schreiboperation
```

### Phase 1b: Referenz-Ausreißerprüfung

```text
- Finding-Typ recognition_reference_outliers
- ReferenceOutlierService
- UI-Fundliste
- Review-Status persisted speichern
- excluded nur intern aus Profilen ausschließen
```

### Phase 2: Unknown-Face-Vorschläge

```text
- Photos Unknown Faces laden
- Embeddings erzeugen
- gegen Profile vergleichen
- recognition_suggestions persistieren
- UI-Vorschau mit selected/unselected/needs_review/ambiguous
```

### Phase 3: Apply nach Photos

```text
- selected_suggestion_ids anwenden
- bestehende Face-Assign-Logik wiederverwenden
- Face vor Apply validieren
- Write-Lock verwenden
- write_state aktualisieren
```

### Phase 4: relationale Persistence

```text
- face_embedding_cache Tabelle
- person_recognition_profile Tabelle
- recognition_reference_outlier Tabelle
- recognition_suggestion Tabelle
- Migration in migrations.py
```

### Phase 5: Erweiterungen

```text
- Multi-Cluster pro Person
- Metadaten als schwache Zusatzquelle
- Kalibrierungsansicht für Schwellenwerte
- Vergleich mit fehlenden InsightFace-Gesichtern aus search_missing_faces_insightface
```

---

## Sicherheitsregeln

```text
- Photos-Personen sind in Phase 1 die einzige Referenzquelle.
- Keine neue Person automatisch anlegen.
- Keine bestehende Photos-Zuordnung automatisch ändern.
- Ausreißerprüfung ändert Photos nicht.
- Unknown-Face-Apply nur für selected_suggestion_ids.
- Apply verwendet persistierte Vorschläge, keine Neuberechnung.
- Face-ID vor Apply erneut validieren.
- Bei ambiguous oder needs_review kein Auto-Apply.
- Embeddings verschiedener Modelle/Parameter nicht mischen.
```

---

## Ergebnis

Die Gesichtswiedererkennung wird dadurch nicht als Fremdsystem neben AV_ImgData aufgebaut, sondern als Erweiterung der bestehenden Paketmechanik:

```text
ImgDataService als Fassade
imgdata_api.py als API-Schicht
FileAnalysisService und PersistedFindingsRepository für Fundlisten
Runtime-State für Fortschritt
CleanupView/cleanupMixin für Start/Stop/Polling
FaceMatch-Apply-Mechanik für spätere Zuordnung
bbox_normalizer und face_matcher für Rahmenzuordnung
InsightFaceDetector/Embedder für Detection und Embeddings
```

Die erste Version bleibt bewusst konservativ: Profile aus Photos-Personen, Ausreißer als Fundliste, Vorschläge für unbekannte Gesichter, Schreiben nur nach expliziter Auswahl.
