# Konzept: Standardisierung von Gesichtsrahmen mit dem InsightFace-Plugin

## Bereich

`Bereinigung → Gesichtsrahmen standardisieren`

## Ziel

Im Paket **AV_ImgData** soll eine Bereinigungsfunktion entstehen, mit der Gesichtsrahmen aus Synology Photos, XMP-Metadaten und InsightFace-Erkennungen verglichen, bewertet und nach expliziter Auswahl standardisiert werden können.

Die Funktion muss sich in die bestehende Architektur einfügen:

```text
FastAPI app/main.py
→ APIRouter in src/api/imgdata_api.py mit Prefix /api
→ ImgDataService in src/imgdata.py als zentrale Orchestrierung
→ bestehende Services unter src/services/
→ SQLite über FileAnalysisService / PersistedFindingsRepository
→ Vue UI über CleanupView + cleanupMixin
```

Ziel ist eine vorschlagsbasierte Bereinigung. Das Backend erzeugt eine Fundliste bzw. Vorschau. Geschrieben wird nur, was die UI explizit freigibt.

---

## Aktueller Bestand, der wiederverwendet werden soll

### Backend-Einstieg

`app/main.py` erzeugt die FastAPI-App, macht `src/` importierbar und bindet `api.imgdata_api.router` ein. Neue API-Endpunkte sollen deshalb in `src/api/imgdata_api.py` landen und nicht als zweiter Router parallel aufgebaut werden.

Bestehendes Muster:

```python
router = APIRouter(prefix="/api")
IMGDATA = ImgDataService(SESSION_MANAGER)
```

Neue Endpunkte sollen dasselbe Muster verwenden:

```python
@router.post("/cleanup_start")
@router.post("/cleanup_progress")
@router.post("/cleanup_stop")
```

oder für detaillierte Vorschau-/Apply-Aktionen:

```python
@router.post("/cleanup_face_frames_preview")
@router.post("/cleanup_face_frames_apply")
@router.post("/cleanup_face_frames_findings")
```

### Session- und Fehlerbehandlung

Alle neuen Endpunkte sollen folgende bestehenden Helfer nutzen:

```text
_prepare_session_request(request)
_read_request_body(request)
_run_backend_call(...)
_operation_exception_response(...)
_session_exception_response(...)
backend_debug_log(...)
```

Damit bleiben DSM-Cookies, `X-SYNO-TOKEN`, Session-Key und Backend-Debug-Logging konsistent.

### Zentrale Orchestrierung

`ImgDataService` ist bereits die zentrale Fassade. Dort sind u. a. vorhanden:

```text
self.photos
self.files
self.metadata_parser
self.face_matcher
self.file_analysis
self.runtime_operations
self.runtime_state
self.checks_workflow
self.face_match_workflow
self.write_locks
```

Die Gesichtsrahmen-Standardisierung soll deshalb als Service in `src/services/` ergänzt und in `ImgDataService.__init__()` verdrahtet werden, z. B.:

```python
from services.face_frame_standardization_service import FaceFrameStandardizationService

self.face_frame_standardization = FaceFrameStandardizationService(self)
```

Die neue Logik soll nicht direkt in `imgdata_api.py` implementiert werden.

### Bestehende Bounding-Box-Normalisierung

Vorhanden:

```text
src/services/bbox_normalizer.py
```

Darin existieren bereits:

```python
from_photos(face_dict)
from_xmp(face_dict)
to_display_face(face_like)
normalize_xmp_face(face_dict)
denormalize_xmp_face(face_dict)
```

Diese Datei soll erweitert werden, statt eine zweite Normalisierung aufzubauen.

Ergänzungen:

```python
def to_xywh(box: BoundingBox) -> dict:
    ...

def from_xywh(face_dict: dict) -> BoundingBox:
    ...

def clamp_bbox(box: BoundingBox) -> BoundingBox:
    ...

def scale_bbox_about_center(box: BoundingBox, scale_x: float, scale_y: float, shift_x: float = 0.0, shift_y: float = 0.0) -> BoundingBox:
    ...
```

### Bestehendes IoU-Matching

Vorhanden:

```text
src/services/face_matcher.py
```

Darin existieren:

```python
compute(left: BoundingBox, right: BoundingBox) -> float
FaceMatcher.match(...)
```

Die Standardisierung soll `compute()` für IoU wiederverwenden. Für den neuen Anwendungsfall ist ein zusätzlicher Matcher sinnvoll:

```text
src/services/face_frame_matcher.py
```

Dieser kann intern `compute()` nutzen und zusätzliche Kriterien berechnen:

```text
- IoU
- Mittelpunktabstand
- Größenabweichung
- Zielsystem
- Herkunft auto/manual/edited/unknown
- Konfliktstatus
```

### Bestehender InsightFace-Detector

Vorhanden:

```text
src/services/face_detector.py
```

Darin existiert bereits:

```python
class InsightFaceDetector:
    def __init__(..., det_size=(640, 640))
    def detect(image_path: Path) -> List[Dict[str, Any]]
```

Die Klasse nutzt derzeit `allowed_modules = ["detection"]` und gibt normalisierte Bounding Boxes mit `bbox`, `center` und optional `score` zurück.

Für die Gesichtsrahmen-Standardisierung reicht Detection. Ergänzt werden soll:

```python
class InsightFaceDetector:
    def __init__(..., det_size=(640, 640), det_thresh=0.5, max_num=0, min_face_width_ratio=None, min_face_height_ratio=None, min_face_area_ratio=None)
```

und in `_load_app()`:

```python
app.prepare(ctx_id=self.ctx_id, det_size=self.det_size, det_thresh=self.det_thresh)
```

falls die installierte InsightFace-Version `det_thresh` unterstützt. Bei `TypeError` muss der bestehende Fallback erhalten bleiben.

Nach `app.get(image)` soll der Nachfilter für Mindestgesichtsgröße greifen.

### Bestehende Persistence

Vorhanden:

```text
src/services/file_analysis_service.py
src/av_imgdata/db/repositories/persisted_findings.py
src/av_imgdata/db/repositories/app_state.py
```

`FileAnalysisService` speichert Analyseergebnisse und Runtime-State bereits in `${SYNOPKG_PKGVAR}/imgdata.sqlite3`. Neue Fundlisten sollen zuerst als `persisted_findings` umgesetzt werden, nicht sofort als neue Spezialtabellen.

Neue Finding-Typen:

```text
face_frame_standardization
face_frame_origin_probe
missing_faces_insightface
```

Spätere Spezialtabellen können in einer Migration ergänzt werden, wenn die Daten dauerhaft relational ausgewertet werden müssen.

### Bestehender Check-/Findings-Workflow

Vorhanden:

```text
src/services/checks_workflow_service.py
```

Dort existieren bereits:

```python
get_candidate_paths(..., changed_since_days=...)
build_scan_payload(...)
write_findings(...)
get_finding_entries(...)
```

Die Standardisierung soll diese Mechanismen nutzen, damit Fundlisten, Status, Fortschritt, Resume und `changed_since_days` einheitlich bleiben.

---

## UI-Einbindung

### Aktueller Cleanup-Bereich

Vorhanden:

```text
ui/src/views/CleanupView.vue
ui/src/mixins/cleanupMixin.js
```

Aktuell gibt es im Cleanup-Bereich nur:

```text
selectedCleanupAction = normalize_names
cleanupTargets = ACD, MICROSOFT, MWG_REGIONS
/api/cleanup_start
/api/cleanup_progress
/api/cleanup_stop
```

Die neuen Funktionen sollen als weitere `selectedCleanupAction` eingebunden werden:

```text
normalize_names
standardize_face_frames
find_missing_faces_insightface
probe_photos_face_origins
```

### UI-Struktur

`CleanupView.vue` soll nicht zu einer sehr großen Einzelkomponente werden. Empfohlen:

```text
ui/src/views/CleanupView.vue
ui/src/components/cleanup/CleanupActionSelector.vue
ui/src/components/cleanup/FaceFrameStandardizationOptions.vue
ui/src/components/cleanup/FaceFrameFindingsTable.vue
ui/src/components/cleanup/InsightFaceDetectionOptions.vue
```

`cleanupMixin.js` bleibt zuständig für:

```text
- Start/Stop/Polling
- cleanupProgress
- selectedCleanupAction
- Backend-Aufrufe
```

Spezifische Optionen können in verschachtelte Objekte ausgelagert werden:

```javascript
faceFrameStandardizationOptions: {
  sources: { photos: true, acdsee: true, mwg: true, insightface: true },
  target: 'preview',
  changed_since_days: 30,
  frame_profile: 'photos_compatible',
  selection_mode: 'safe_matches',
  photos_origin_filter: ['auto'],
  include_unknown_origin: false,
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

---

## API-Erweiterung

### Variante A: bestehendes Cleanup-Muster erweitern

Empfohlen für erste Implementierung.

`/api/cleanup_start` erhält neue `action`:

```json
{
  "action": "standardize_face_frames",
  "options": {
    "mode": "preview",
    "changed_since_days": 30,
    "sources": ["photos", "acdsee_xmp", "mwg_regions", "insightface"],
    "target": "acdsee_xmp",
    "frame_profile": "photos_compatible",
    "selection_mode": "safe_matches",
    "photos_origin_filter": ["auto"],
    "include_unknown_origin": false,
    "insightface": {
      "det_size": [640, 640],
      "det_thresh": 0.5,
      "max_num": 0,
      "min_face_width_ratio": 0.015,
      "min_face_height_ratio": 0.015
    }
  }
}
```

`ImgDataService.startCleanupRun(...)` bzw. die vorhandene Cleanup-Start-Methode soll auf die Action verzweigen:

```python
if action == "standardize_face_frames":
    return self.face_frame_standardization.start_preview(...)
```

### Variante B: eigene Endpunkte für Vorschau und Apply

Für Apply sinnvoll, weil hier IDs aus der Vorschau geschrieben werden.

```http
POST /api/cleanup_face_frames_findings
POST /api/cleanup_face_frames_apply
POST /api/cleanup_face_frames_rollback
```

Apply-Payload:

```json
{
  "finding_type": "face_frame_standardization",
  "selected_item_ids": ["ff-001", "ff-002"],
  "target": "acdsee_xmp",
  "expert_override": false
}
```

Wichtige Regel:

```text
Der Apply-Schritt darf nicht neu scannen und nicht neu entscheiden.
Er darf ausschließlich persistierte Findings anhand ihrer IDs schreiben.
```

---

## Finding-Format

Die Fundliste soll in `persisted_findings` mit `finding_type = face_frame_standardization` gespeichert werden.

Ein Entry:

```json
{
  "item_id": "ff-001",
  "image_path": "/volume1/photo/Benno/2025/example.jpg",
  "item_id_photos": 76935,
  "face_id": 66485,
  "person_id": 19431,
  "person_name": "Bea",
  "source_frame": {
    "source": "photos",
    "bbox": {"x1": 0.5299, "y1": 0.2836, "x2": 0.6083, "y2": 0.4230}
  },
  "insightface_frame": {
    "bbox": {"x1": 0.535, "y1": 0.290, "x2": 0.609, "y2": 0.420},
    "score": 0.91,
    "det_size": [640, 640]
  },
  "target_frame": {
    "bbox": {"x1": 0.526, "y1": 0.276, "x2": 0.615, "y2": 0.452},
    "profile": "photos_compatible"
  },
  "match": {
    "iou": 0.82,
    "center_distance": 0.012,
    "size_delta": 0.18,
    "score": 0.91,
    "decision": "safe"
  },
  "origin": {
    "value": "auto",
    "confidence": "unknown"
  },
  "selection_state": "selected",
  "write_state": "pending",
  "target": "acdsee_xmp",
  "warnings": []
}
```

Pflichtfelder für UI und Apply:

```text
item_id
image_path
source_frame
target_frame
match.decision
selection_state
write_state
target
```

---

## Photos-Herkunft auto/manual/edited

Bisher ist nicht bestätigt, ob Synology Photos die Herkunft eines Face-Rahmens eindeutig speichert. Deshalb muss die Implementierung zweistufig sein.

### Phase A: Probe-Action

Neue Action:

```text
probe_photos_face_origins
```

Ablauf:

```text
1. definierte Testbilder mit automatisch erkannten Gesichtern erfassen
2. manuell ein Gesicht hinzufügen
3. automatisch erkanntes Gesicht manuell verschieben
4. Photos-API/list_face und lokale DB-Zustände vergleichen
5. Ergebnis als Finding `face_frame_origin_probe` speichern
```

Bis diese Prüfung belastbar ist:

```text
origin.value = unknown
origin.confidence = unknown
```

und Photos-Schreiboperationen mit unbekannter Herkunft sind standardmäßig gesperrt.

### Phase B: Herkunftsfilter

Sobald die Herkunft belastbar erkannt wird:

```text
photos_origin_filter:
- auto
- manual
- edited
- imported
- unknown
```

Default:

```text
Nur auto, unbekannte Herkunft nicht einschließen.
```

---

## InsightFace-Detektionsparameter

Die vorhandene Klasse `InsightFaceDetector` hat bereits `det_size=(640, 640)` als Konstruktorparameter und ruft `app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)` auf.

Zu ergänzen:

```text
det_thresh
max_num
min_face_width_ratio
min_face_height_ratio
min_face_area_ratio
profile
```

Profile:

| Profil | det_size | Zweck |
|---|---:|---|
| standard | 640 × 640 | normale Bereinigung |
| small_faces | 1280 × 1280 | kleine Gesichter / Gruppenbilder |
| fast_test | 320 × 320 | schnelle Vorprüfung |
| custom | frei | Expertenmodus |

Die Suche nach fehlenden Gesichtern via bestehender Face-Matching-Action `search_missing_faces_insightface` soll dieselben Parameter erhalten. Der bestehende API-Pfad `/api/face_matching_action` kennt diese Action bereits; die Payload muss um `insightface`-Optionen ergänzt werden. Optional kann die Action mit `recognize_persons=true` neu erkannte fehlende Gesichter gegen vorhandene Wiedererkennungsprofile prüfen und als Photos-Person im Gesichtsabgleich vorschlagen. Unbekannte vorhandene Photos-Gesichter ohne Namen bleiben fachlich getrennt und laufen ueber `recognition_analyze_unknown_faces`.

---

## Standardisierungsstrategien

Die Standardisierung soll neue Zielrahmen auf Basis vorhandener `BoundingBox`-Objekte berechnen.

Strategien:

```text
insightface_exact
insightface_scaled
keep_existing_center_scale_size
correct_only_if_deviation
average_sources
largest_plausible
custom_margin
```

Empfohlene Implementierung:

```text
src/services/face_frame_standardizer.py
```

Kernfunktionen:

```python
def build_target_frame(source_frame, insight_frame, strategy, profile): ...
def apply_frame_profile(box, profile): ...
def validate_target_frame(box): ...
def frame_delta(left, right): ...
```

Profile:

| Profil | scale_x | scale_y | shift_y |
|---|---:|---:|---:|
| tight | 1.00 | 1.00 | 0.00 |
| normal | 1.15 | 1.25 | -0.03 |
| photos_compatible | 1.20 | 1.35 | -0.05 |
| acdsee_compatible | 1.10 | 1.20 | -0.03 |
| custom | UI-Werte | UI-Werte | UI-Werte |

---

## Schreibziele

### XMP/Metadaten

Für XMP soll bestehende ExifTool-/Metadata-Logik genutzt werden:

```text
ExifToolService
ExifToolHandler
MetadataParser
bbox_normalizer.denormalize_xmp_face(...)
_writeOperationLock("metadata:<path>")
```

Zielwerte:

```text
ACD
MICROSOFT
MWG_REGIONS
Sidecar-XMP
```

Schreibregel:

```text
Vor jedem Schreiben File-Snapshot aufnehmen.
Nach dem Schreiben Änderung validieren.
Finding write_state aktualisieren.
```

### Synology Photos

Photos-Schreiben bleibt Expertenmodus.

Bestehende Schutzmechanismen aus `ImgDataService` sollen genutzt werden:

```text
_photosFaceWriteLockKey(face_id)
_validatePhotosFaceOnItem(...)
_raisePhotosFaceChanged(...)
```

Regel:

```text
Vor dem Schreiben Face-ID und erwartete Person-ID erneut gegen Photos prüfen.
Wenn sich das Face inzwischen geändert hat: abbrechen.
```

---

## Runtime-State und Fortschritt

Neue Runs sollen denselben Stil wie vorhandene Face-Matching- und Cleanup-Runs verwenden.

Runtime-State-Key:

```text
runtime:cleanup_progress:<user_key>:standardize_face_frames
```

Neustart und Fortsetzen:

```text
Ein expliziter Start eines Scans in `immediate` oder `save_only` beginnt mit
leerem Worker-Zustand bei Datei 0. Eine alte persistente Teilliste wird dabei
nicht als aktuelle Arbeitsliste übernommen.

`immediate` verwendet für die manuelle Vorschau nur den aktiven Laufzustand.
Dieser Zustand ist keine persistente Fundliste. Eine persistente Fundliste wird
nur bei `operation_mode = save_only` geschrieben und nur bei
`operation_mode = findings` abgearbeitet.

Fortsetzen ist nur in zwei Fällen zulässig:

1. `operation_mode = findings` arbeitet die bestehende persistente Fundliste ab.
2. Die UI startet nach einer manuellen Einzelentscheidung intern den nächsten
   Scanabschnitt mit `resume_existing = true`; dabei wird nur der aktive
   Laufzustand fortgesetzt, nicht eine persistente Fundliste.

`resume_existing` ist eine interne Startoption und wird nicht als normale
Benutzereinstellung gespeichert.
```

Progress-Payload:

```json
{
  "running": true,
  "action": "standardize_face_frames",
  "operation_id": "...",
  "revision": 12,
  "files_scanned": 120,
  "total_files": 500,
  "findings_count": 17,
  "selected_count": 9,
  "written_count": 0,
  "status": {
    "schema_version": 1,
    "progress": {
      "kind": "files",
      "current": 120,
      "total": 500
    },
    "counters": [
      {"key": "findings", "value": 17, "label_key": "cleanup:label_findings", "fallback_label": "Findings"},
      {"key": "selected", "value": 9, "label_key": "cleanup:label_selected", "fallback_label": "Selected"}
    ]
  }
}
```

Das vorhandene `cleanupMixin.js` kann `status.schema_version == 1`, `progress` und `counters` bereits anzeigen.

---

## Implementierungsdateien

### Neue Dateien

```text
src/services/face_frame_standardization_service.py
src/services/face_frame_standardizer.py
src/services/face_frame_matcher.py
src/services/face_frame_origin_probe_service.py
src/av_imgdata/db/repositories/face_frame_cache.py      # optional Phase 2
ui/src/components/cleanup/FaceFrameStandardizationOptions.vue
ui/src/components/cleanup/FaceFrameFindingsTable.vue
ui/src/components/cleanup/InsightFaceDetectionOptions.vue
```

### Zu ändernde Dateien

```text
src/imgdata.py
src/api/imgdata_api.py
src/services/face_detector.py
src/services/bbox_normalizer.py
src/services/checks_workflow_service.py
ui/src/views/CleanupView.vue
ui/src/mixins/cleanupMixin.js
src/av_imgdata/db/migrations.py                         # erst bei Spezialtabellen
```

---

## Implementierungsphasen

### Phase 1: Preview ohne Schreiben

```text
- InsightFaceDetector um det_thresh/min-size erweitern
- Finding-Typ face_frame_standardization anlegen
- Kandidaten über ChecksWorkflowService.get_candidate_paths(... changed_since_days ...)
- Photos/XMP/InsightFace-Rahmen normalisieren
- IoU/Delta berechnen
- target_frame berechnen
- Findings persistieren
- UI-Fundliste anzeigen
```

### Phase 2: XMP schreiben

```text
- Apply-Endpunkt
- selected_item_ids aus persisted_findings laden
- XMP-Ziel schreiben
- write_state aktualisieren
- File-Snapshot und Backup berücksichtigen
```

### Phase 3: Fehlende Gesichter mit InsightFace

```text
- bestehende face_matching_action search_missing_faces_insightface um det_size/det_thresh/min-size und optionale Personenerkennung erweitern
- Finding-Typ missing_faces_insightface nutzen
- gleiche Vorschau-/Auswahlregeln anwenden
```

### Phase 4: Photos-Ziel

```text
- Herkunftsprobe auswerten
- Photos-Schreiben nur für sichere Herkunft oder Expertenfreigabe
- _validatePhotosFaceOnItem vor Apply verwenden
- Schreibprotokoll und Rollback-Konzept ergänzen
```

### Phase 5: relationale Spezialtabellen

Nur wenn Findings/JSON nicht mehr reichen:

```text
face_frame_detection_cache
face_frame_cleanup_log
```

Dann Migration in `src/av_imgdata/db/migrations.py` ergänzen.

---

## Sicherheitsregeln

```text
- Kein Apply ohne persistierte Vorschau.
- Apply schreibt nur selected_item_ids.
- Apply scannt nicht erneut.
- Photos-Ziel ist Expertenmodus.
- Herkunft unknown ist standardmäßig locked.
- Manuell gesetzte oder geänderte Photos-Rahmen sind standardmäßig locked.
- XMP-Schreiben nur mit Write-Lock und File-Snapshot.
- Face-ID vor Photos-Schreiben erneut validieren.
- InsightFace-Parameter sind Teil des Cache-/Finding-Kontexts.
```

---

## Ergebnis

Die Gesichtsrahmen-Standardisierung wird dadurch kein isolierter neuer Mechanismus, sondern nutzt die vorhandenen Paketmuster:

```text
ImgDataService als Fassade
FastAPI-Router mit Session-Kontext
Runtime-State für Fortschritt
PersistedFindingsRepository für Fundlisten
ChecksWorkflowService für Scan/Resume/changed_since_days
bbox_normalizer und face_matcher für Geometrie
InsightFaceDetector für Detection
CleanupView/cleanupMixin für UI und Polling
```

Damit bleibt die Funktion konsistent mit dem bestehenden Paket und kann schrittweise von reiner Vorschau zu XMP-Apply und später Photos-Apply ausgebaut werden.
