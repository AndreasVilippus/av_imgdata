# Konzept: Gesichtswiedererkennung mit InsightFace auf Basis von Photos-Personen

## Bereich

`Bereinigung → Gesichtswiedererkennung aufbauen`

## Ziel

Im Paket **AV_ImgData** soll eine Gesichtswiedererkennung implementiert werden, die zunächst ausschließlich auf den bereits in **Synology Photos** vorhandenen Personen und Gesichtern basiert.

Ziel ist nicht, sofort neue Personen automatisch zu erzeugen oder externe Metadaten als Trainingsquelle zu verwenden. Die erste Ausbaustufe soll:

1. vorhandene Photos-Personen und deren zugeordnete Gesichter auslesen,
2. für diese Gesichter InsightFace-Embeddings berechnen,
3. pro Photos-Person ein internes Wiedererkennungsprofil aufbauen,
4. unbekannte oder fehlende Gesichter gegen diese Profile vergleichen,
5. Vorschläge zur Personenzuordnung erzeugen,
6. die Vorschläge in der UI prüfbar machen,
7. erst nach Freigabe nach Photos oder in Paketdaten schreiben.

Die Funktion ergänzt das Konzept zur Gesichtsrahmen-Standardisierung, ist aber fachlich getrennt: Dort werden Rahmenpositionen standardisiert, hier werden erkannte Gesichter Personen zugeordnet.

---

## Abgrenzung der ersten Version

Enthalten:

```text
- Quelle: Synology Photos Personen
- Quelle: Synology Photos vorhandene Face-IDs und Bounding Boxes
- InsightFace-Erkennung und Embedding-Berechnung
- Personenprofile aus bekannten Photos-Gesichtern
- Vergleich unbekannter Gesichter gegen bekannte Personenprofile
- Vorschau und manuelle Freigabe
- Cache für Embeddings und Vergleichsergebnisse
```

Nicht enthalten:

```text
- Training aus ACDSee-XMP oder Picasa-XMP
- automatische Erstellung neuer Photos-Personen
- vollautomatisches Schreiben ohne Vorschau
- externe Bildquellen außerhalb der Photos-Bibliothek
- Nutzung von Alters-/Geschlechtsmerkmalen als Entscheidungsgrundlage
```

XMP- und Metadatenformate können später als zusätzliche Referenzquellen genutzt werden, sollen aber für die erste Implementierung bewusst ausgeschlossen bleiben.

---

## Technische Grundlage

InsightFace liefert nach der Gesichtserkennung pro erkanntem Gesicht eine Bounding Box, Landmarks und bei geladenem Recognition-Modul ein Embedding. Der Vergleich zwischen zwei Embeddings erfolgt über eine Ähnlichkeitsfunktion, praktisch Cosine Similarity.

Rollenverteilung:

```text
Synology Photos:
- liefert bekannte Personen
- liefert bekannte Face-IDs
- liefert vorhandene Bounding Boxes
- liefert unbekannte oder nicht zugeordnete Gesichter

InsightFace:
- erkennt Gesichter im Bild
- berechnet pro Gesicht ein Embedding
- ermöglicht Ähnlichkeitsvergleich zwischen Gesichtern

AV_ImgData:
- verbindet Photos-Face-ID mit InsightFace-Embedding
- bildet Personenprofile
- erzeugt Zuordnungsvorschläge
- verwaltet Cache, Vorschau, Freigabe und Protokoll
```

---

## Position im Paket

Vorgeschlagene UI-Struktur:

```text
Bereinigung
├── Gesichtsrahmen standardisieren
└── Gesichtswiedererkennung aufbauen
    ├── Referenzprofile
    ├── Unbekannte Gesichter prüfen
    ├── Vorschläge
    ├── Freigabe
    ├── Protokoll
    └── Einstellungen
```

Vorgeschlagene Backend-Struktur:

```text
src/
├── recognition/
│   ├── photos_person_repository.py
│   ├── face_embedding_service.py
│   ├── person_profile_builder.py
│   ├── face_recognition_matcher.py
│   ├── recognition_job_service.py
│   ├── recognition_preview.py
│   └── recognition_writer.py
├── insightface_plugin/
│   ├── detector.py
│   ├── embedder.py
│   ├── cache.py
│   └── models.py
├── cleanup/
│   └── face_frame_matcher.py
└── metadata/
    └── region_normalizer.py
```

Die Wiedererkennungslogik soll als eigenständiger Bereich umgesetzt werden, aber bestehende Normalisierung, Bounding-Box-Matching, Cache- und Job-Mechanismen wiederverwenden.

---

## Datenquellen aus Synology Photos

Die erste Version basiert nur auf Photos-Daten.

Benötigt werden:

```text
- Personenliste
- Person-ID
- Personenname
- zugeordnete Face-IDs je Person
- Bild-ID / Unit-ID je Face
- Bounding Box je Face
- Dateipfad je Bild
- optional Cover-/Favoriteninformation
- unbekannte oder nicht zugeordnete Faces
```

Bekannte Tabellen und Konzepte aus bisherigen Paketarbeiten:

```text
person
face
unit
live
folder
many_unit_has_many_person
```

Photos-API und Datenbankzugriffe sollten dieselbe Repository-Schicht nutzen, die bereits für Personenstatistik, Unknown-Faces und Face-Rahmen verwendet wird.

---

## Grundprinzip

Die Photos-Personen dienen als initiale Wahrheit.

```text
Photos-Person „Bea“
├── Face-ID 1001 → InsightFace-Embedding A
├── Face-ID 1002 → InsightFace-Embedding B
├── Face-ID 1003 → InsightFace-Embedding C
└── Personenprofil Bea = robuste Zusammenfassung aus A, B, C
```

Ein unbekanntes Gesicht wird gegen alle bekannten Personenprofile verglichen:

```text
Unbekanntes Face 9001
├── Similarity zu Bea: 0.71
├── Similarity zu Benno: 0.42
├── Similarity zu Asta: 0.38
└── Vorschlag: Bea, falls Schwellwert erfüllt und Abstand zum zweitbesten Treffer groß genug ist
```

---

## Interne Datenmodelle

```python
class PhotosPerson:
    person_id: int
    name: str
    face_count: int
    hidden: bool | None
    cover_face_id: int | None

class KnownFaceReference:
    person_id: int
    person_name: str
    face_id: int
    image_id: int
    file_path: str
    bbox: NormalizedFaceFrame
    source: str = "photos"
    quality_score: float | None
    embedding_id: int | None

class FaceEmbedding:
    embedding_id: int
    face_id: int | None
    image_id: int
    file_path: str
    bbox: NormalizedFaceFrame
    model_name: str
    model_version: str
    det_size: tuple[int, int]
    det_thresh: float
    embedding: list[float]
    embedding_norm: float
    quality_score: float | None
    created_at: datetime

class PersonRecognitionProfile:
    person_id: int
    person_name: str
    model_name: str
    model_version: str
    embedding_count: int
    centroid_embedding: list[float]
    medoid_embedding_id: int | None
    quality: str              # good, weak, mixed, disabled
    intra_person_similarity: float | None
    created_at: datetime
    updated_at: datetime

class RecognitionCandidate:
    candidate_id: str
    unknown_face_id: int | None
    image_id: int
    file_path: str
    bbox: NormalizedFaceFrame
    best_person_id: int | None
    best_person_name: str | None
    best_score: float
    second_person_id: int | None
    second_score: float | None
    score_margin: float | None
    decision: str             # accept, review, reject, ambiguous
    selection_state: str      # selected, unselected, locked, needs_review
```

---

## Datenbanktabellen

### Embedding-Cache

```sql
CREATE TABLE face_embedding_cache (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    face_id INTEGER,
    image_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_mtime REAL NOT NULL,
    file_size INTEGER NOT NULL,
    bbox_json TEXT NOT NULL,
    bbox_hash TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    det_size TEXT NOT NULL,
    det_thresh REAL NOT NULL,
    embedding_json TEXT NOT NULL,
    embedding_norm REAL NOT NULL,
    quality_score REAL,
    created_at TEXT NOT NULL,
    UNIQUE(source, face_id, image_id, file_mtime, file_size, bbox_hash, model_name, model_version, det_size, det_thresh)
);
```

### Personenprofile

```sql
CREATE TABLE person_recognition_profile (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    person_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    embedding_count INTEGER NOT NULL,
    centroid_embedding_json TEXT NOT NULL,
    medoid_embedding_id INTEGER,
    quality TEXT NOT NULL,
    intra_person_similarity REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(person_id, model_name, model_version)
);
```

### Profil-Zuordnung zu Referenzgesichtern

```sql
CREATE TABLE person_recognition_profile_face (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    embedding_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    face_id INTEGER NOT NULL,
    included INTEGER NOT NULL DEFAULT 1,
    exclusion_reason TEXT,
    quality_score REAL,
    created_at TEXT NOT NULL
);
```

### Wiedererkennungsvorschläge

```sql
CREATE TABLE recognition_suggestion (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL,
    image_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    unknown_face_id INTEGER,
    bbox_json TEXT NOT NULL,
    embedding_id INTEGER NOT NULL,
    best_person_id INTEGER,
    best_person_name TEXT,
    best_score REAL NOT NULL,
    second_person_id INTEGER,
    second_score REAL,
    score_margin REAL,
    decision TEXT NOT NULL,
    selection_state TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

---

## Aufbau der Referenzprofile

### Schritt 1: Personen laden

```python
persons = photos_repo.list_persons(show_hidden=False)
```

Optionen:

```text
[ ] Versteckte Personen einschließen
[ ] Personen ohne Namen einschließen
[ ] Personen mit weniger als n Gesichtern einschließen
```

Empfohlener Default:

```text
- nur sichtbare Personen
- nur Personen mit Namen
- mindestens 3 Referenzgesichter pro Person
```

### Schritt 2: Referenzgesichter laden

```python
faces = photos_repo.list_faces_for_person(person_id)
```

Filter:

```text
- Bounding Box gültig
- Bilddatei vorhanden
- Gesicht nicht zu klein
- Gesicht nicht zu unscharf, falls Quality-Score verfügbar
```

### Schritt 3: InsightFace-Embedding erzeugen

```python
embedding = insightface.embed_face(
    file_path=file_path,
    bbox=photos_bbox,
    det_size=config.det_size,
    det_thresh=config.det_thresh,
)
```

Bei bekannten Photos-Gesichtern sollte vorrangig der vorhandene Photos-Rahmen als Zuschnitt oder Matching-Anker genutzt werden. Wenn InsightFace auf dem Bild mehrere Gesichter erkennt, muss das InsightFace-Gesicht gewählt werden, dessen Bounding Box am besten zum Photos-Rahmen passt.

### Schritt 4: Ausreißer entfernen

Nicht jedes einer Person zugeordnete Photos-Gesicht ist zwingend korrekt. Deshalb sollten Referenzprofile robuste Ausreißerbehandlung erhalten.

```text
1. Embeddings je Person berechnen.
2. Paarweise Similarity innerhalb der Person berechnen.
3. Durchschnittliche Similarity je Face bestimmen.
4. Gesichter mit stark unterdurchschnittlicher Similarity als Ausreißer markieren.
5. Ausreißer nicht in das Profil aufnehmen, aber in der UI anzeigen.
```

### Schritt 5: Profil bilden

Empfehlung für Phase 1:

```text
Centroid + Medoid speichern
```

Centroid:

```python
centroid = normalize(mean(valid_embeddings))
```

Medoid:

```python
medoid = embedding mit höchster mittlerer Similarity zu allen anderen Embeddings dieser Person
```

---

## Multi-Cluster pro Person

Für Phase 1 reicht ein einzelner Centroid. Für Phase 2 sollte optional ein Multi-Cluster-Profil vorgesehen werden, weil Personen je nach Alter, Blickwinkel, Licht, Brille oder Bart deutlich unterschiedlich aussehen können.

```text
Person Bea
├── Cluster 1: frontal, hell
├── Cluster 2: seitlich
└── Cluster 3: ältere Bilder
```

Vergleich:

```python
score = max(cosine_similarity(candidate, cluster_centroid) for cluster in person.clusters)
```

---

## Erkennung unbekannter Gesichter

### Kandidatenquellen

Zunächst ausschließlich Photos:

```text
- unbekannte Photos-Gesichter
- nicht zugeordnete Faces aus Photos
- optional: Gesichter aus neu erkannten InsightFace-Detektionen ohne Photos-Match
```

Hauptmodus Phase 1:

```text
Photos Unknown Faces → InsightFace Embedding → Vergleich mit Photos-Personenprofilen
```

### Ablauf

```python
unknown_faces = photos_repo.list_unknown_faces(limit=..., offset=...)
profiles = recognition_repo.list_profiles(model_name, model_version)

for face in unknown_faces:
    embedding = embedding_service.get_or_create_embedding(face)
    candidates = matcher.match_embedding_to_profiles(embedding, profiles)
    suggestion = decision_service.create_suggestion(candidates)
```

---

## Vergleichslogik

Basisscore:

```python
score = cosine_similarity(candidate_embedding, person_profile.centroid_embedding)
```

Abstand zum zweitbesten Treffer:

```python
margin = best_score - second_score
```

Startwerte, die in der UI konfigurierbar sein müssen:

| Entscheidung | Bedingung |
|---|---|
| sicherer Vorschlag | `best_score >= 0.55` und `margin >= 0.08` |
| prüfen | `best_score >= 0.45` und `margin >= 0.04` |
| unklar | `best_score >= 0.45` aber `margin < 0.04` |
| ablehnen | `best_score < 0.45` |

Die Werte sind bewusst konservativ und müssen mit den eigenen Photos-Daten kalibriert werden.

---

## Qualitätssicherung

### Mindestanzahl je Person

```text
Mindestanzahl Referenzgesichter pro Person: [3]
```

| Referenzgesichter | Profilqualität |
|---:|---|
| 0-1 | deaktiviert |
| 2 | schwach |
| 3-9 | nutzbar |
| 10+ | gut |

### Ausreißeranzeige

```text
Person: Bea
Referenzen: 42
Verwendet: 39
Ausreißer: 3
Profilqualität: gut
```

Ausreißer dürfen nicht gelöscht werden. Sie werden nur für das Wiedererkennungsprofil ausgeschlossen.

### Manuelles Ausschließen

```text
[ ] Dieses Referenzgesicht für Wiedererkennung verwenden
```

Das ist wichtig, wenn Photos einer Person versehentlich ein falsches Gesicht zugeordnet hat.

---

## InsightFace-Erkennungsparameter

Die Wiedererkennung soll dieselben InsightFace-Optionen verwenden wie das Konzept zur Gesichtsrahmen-Standardisierung.

```text
InsightFace-Profil:
(x) Standard / 640 × 640
( ) Kleine Gesichter / 1280 × 1280
( ) Schnelltest / 320 × 320
( ) Benutzerdefiniert

Schwellwert det_thresh: [0.50]
Max. Gesichter pro Bild: [0 = unbegrenzt]
Mindestgesichtsgröße: [1.5] % Breite/Höhe
```

Referenzprofile und Kandidaten müssen mit kompatiblen Modellen und Parametern aufgebaut werden. Eine Änderung von Modell, Modellversion oder relevanten Detektionsparametern muss getrennt gecacht und getrennt bewertet werden.

---

## Cache-Strategie

Cache-Key:

```text
file_path
file_mtime
file_size
image_id
face_id
bbox_hash
model_name
model_version
det_size
det_thresh
recognition_model
```

Regeln:

```text
- Ändert sich die Datei, wird das Embedding neu berechnet.
- Ändert sich der Face-Rahmen, wird das Embedding neu berechnet.
- Ändert sich das Modell, wird das Embedding neu berechnet.
- Unterschiedliche det_size-Profile dürfen nicht vermischt werden.
```

---

## UI-Konzept

### Referenzprofile aufbauen

```text
Bereinigung → Gesichtswiedererkennung aufbauen → Referenzprofile

Personenquelle:
[x] Synology Photos Personen
[ ] versteckte Personen einschließen
[ ] unbenannte Personen einschließen

Referenzfilter:
Mindestgesichter pro Person: [3]
Mindestgesichtsgröße: [1.5] %
Ausreißer automatisch ausschließen: [x]

InsightFace:
Profil: [Standard 640 × 640]
det_thresh: [0.50]

Aktion:
[Profile analysieren]
[Profile neu aufbauen]
[Cache behalten]
[Cache verwerfen]
```

### Unbekannte Gesichter prüfen

```text
Bereinigung → Gesichtswiedererkennung aufbauen → Unbekannte Gesichter

Quelle:
[x] Photos unbekannte Gesichter
[ ] InsightFace-Gesichter ohne Photos-Match

Zeitraum:
( ) Alle
(x) Nur Änderungen der letzten [30] Tage

Vorschläge:
Sicher ab Score: [0.55]
Review ab Score: [0.45]
Mindestabstand zum zweiten Treffer: [0.08]

Auswahl:
( ) Keine automatisch auswählen
(x) Sichere Vorschläge automatisch auswählen
( ) Alle sichtbaren Vorschläge auswählen
```

### Vorschautabelle

```text
Bild | Gesicht | Vorschlag | Score | Abstand | Status | Aktion
```

Status:

```text
selected      # wird geschrieben
unselected    # wird nicht geschrieben
needs_review  # unsicher
ambiguous      # mehrere ähnliche Personen
locked         # darf nicht automatisch geschrieben werden
```

---

## Schreibstrategie

### Phase 1: Kein automatisches Schreiben

```text
- Vorschläge anzeigen
- manuell auswählen
- optional später nach Photos schreiben
```

### Phase 2: Freigegebene Zuordnung nach Photos schreiben

Wenn die Photos-API oder der bisherige Paketmechanismus eine Zuordnung zu bestehender Person unterstützt, soll nur diese Aktion erfolgen:

```text
Unknown Face-ID → bestehende Photos Person-ID zuordnen
```

Nicht erlaubt in Phase 2:

```text
- neue Person automatisch anlegen
- vorhandene Person automatisch zusammenführen
- manuell gesetzte Zuordnung überschreiben
```

### Phase 3: halbautomatische Massenübernahme

Nur mit starken Grenzen:

```text
- nur sichere Vorschläge
- Mindestscore erfüllt
- ausreichender Abstand zum zweitbesten Treffer
- keine Konflikte
- Protokoll aktiviert
- Rückgängig möglich
```

---

## API-Entwurf

### Profile analysieren

```http
POST /api/recognition/profiles/analyze
```

```json
{
  "source": "photos",
  "include_hidden_persons": false,
  "include_unnamed_persons": false,
  "min_faces_per_person": 3,
  "exclude_outliers": true,
  "insightface_profile": "standard",
  "insightface": {
    "det_size": [640, 640],
    "det_thresh": 0.5,
    "max_num": 0,
    "min_face_width_ratio": 0.015,
    "min_face_height_ratio": 0.015
  }
}
```

### Profile aufbauen

```http
POST /api/recognition/profiles/build
```

```json
{
  "analysis_job_id": "profile-analysis-001",
  "rebuild_existing": false,
  "keep_cache": true
}
```

### Unbekannte Gesichter analysieren

```http
POST /api/recognition/suggestions/analyze
```

```json
{
  "source": "photos_unknown_faces",
  "changed_days": 30,
  "safe_score": 0.55,
  "review_score": 0.45,
  "min_margin": 0.08,
  "selection_mode": "safe_only"
}
```

### Vorschläge abrufen

```http
GET /api/recognition/suggestions?job_id=...
```

```json
{
  "items": [
    {
      "suggestion_id": "rec-001",
      "file_path": "/volume1/photo/Benno/2025/example.jpg",
      "image_id": 76935,
      "unknown_face_id": 12345,
      "best_person_id": 19431,
      "best_person_name": "Bea",
      "best_score": 0.68,
      "second_person_id": 19432,
      "second_score": 0.51,
      "score_margin": 0.17,
      "decision": "accept",
      "selection_state": "selected"
    }
  ]
}
```

### Auswahl übernehmen

```http
POST /api/recognition/suggestions/apply
```

```json
{
  "job_id": "recognition-001",
  "apply_items": "selected_only",
  "selected_suggestion_ids": ["rec-001", "rec-002"]
}
```

---

## Pseudocode

### Profile aufbauen

```python
def build_person_profiles(config):
    persons = photos_repo.list_persons(
        include_hidden=config.include_hidden_persons,
        include_unnamed=config.include_unnamed_persons,
    )

    for person in persons:
        references = photos_repo.list_faces_for_person(person.person_id)
        references = filter_reference_faces(references, config)

        embeddings = []
        for ref in references:
            embedding = embedding_service.get_or_create_from_photos_face(
                file_path=ref.file_path,
                image_id=ref.image_id,
                face_id=ref.face_id,
                bbox=ref.bbox,
                insightface=config.insightface,
            )
            embeddings.append(embedding)

        valid_embeddings, outliers = remove_outliers(embeddings, config)

        if len(valid_embeddings) < config.min_faces_per_person:
            profile_quality = "disabled"
        else:
            profile = profile_builder.build_centroid_profile(person, valid_embeddings)
            recognition_repo.save_profile(profile, valid_embeddings, outliers)
```

### Vorschläge erzeugen

```python
def analyze_unknown_faces(config):
    profiles = recognition_repo.list_active_profiles()
    unknown_faces = photos_repo.list_unknown_faces(
        changed_since=resolve_changed_since(config.changed_days),
    )

    suggestions = []

    for face in unknown_faces:
        embedding = embedding_service.get_or_create_from_photos_face(
            file_path=face.file_path,
            image_id=face.image_id,
            face_id=face.face_id,
            bbox=face.bbox,
            insightface=config.insightface,
        )

        matches = matcher.match_embedding_to_profiles(embedding, profiles)
        suggestion = decision_service.decide(matches, config)
        suggestions.append(suggestion)

    return preview_repository.create_job(suggestions)
```

### Schreiben

```python
def apply_recognition_suggestions(job_id, selected_suggestion_ids):
    suggestions = preview_repository.get_suggestions(job_id)

    for suggestion in suggestions:
        if suggestion.id not in selected_suggestion_ids:
            continue
        if suggestion.decision not in ["accept", "review"]:
            continue
        if suggestion.selection_state in ["locked", "ambiguous"]:
            continue

        photos_writer.assign_face_to_person(
            face_id=suggestion.unknown_face_id,
            person_id=suggestion.best_person_id,
        )

        recognition_repo.log_apply(suggestion)
```

---

## Sicherheitsregeln

```text
- Kein automatisches Schreiben ohne Vorschau.
- Keine neue Person automatisch anlegen.
- Keine vorhandene manuelle Zuordnung überschreiben.
- Unklare Vorschläge bleiben unselected oder needs_review.
- Bei ähnlichem Score zu mehreren Personen wird der Vorschlag als ambiguous markiert.
- Alle Schreibvorgänge werden protokolliert.
```

---

## Wiederverwendung bisheriger Paketlogik

Wiederverwendet werden sollen:

```text
photos_db.py
photos.sql
service.py
schema_check.py
FastAPI-Jobmuster
Vue-Komponentenstruktur
Unknown-Faces-Abfragen
Bounding-Box-Normalisierung
InsightFace-Erkennungsparameter
Cache-Mechanismen
Protokoll-/Rollback-Muster
```

Besonders wichtig ist die Wiederverwendung des Matchings zwischen Photos-Rahmen und InsightFace-Rahmen aus dem Gesichtsrahmen-Konzept. Bei bekannten Photos-Gesichtern muss genau das erkannte InsightFace-Gesicht verwendet werden, das zum vorhandenen Photos-Rahmen gehört.

---

## Performance

```text
- Referenzprofile inkrementell aufbauen
- Embeddings cachen
- Profile nur neu berechnen, wenn Referenzfaces geändert wurden
- Unknown-Faces paginiert analysieren
- Job-System mit Fortschritt verwenden
- NAS-Hardware schonen
```

UI-Optionen:

```text
Maximale Bilder pro Lauf: [500]
Maximale Personen pro Lauf: [50]
Maximale parallele Prozesse: [1]
Niedrige Priorität verwenden: [x]
```

---

## Änderungs- und Neuaufbau-Strategie

### Vollständiger Neuaufbau

```text
Alle Photos-Personen → alle Referenzgesichter → alle Embeddings prüfen → Profile neu bilden
```

### Inkrementeller Neuaufbau

```text
Nur Personen neu berechnen, bei denen:
- neue Faces hinzugekommen sind
- Faces entfernt wurden
- Person umbenannt wurde
- Face-Rahmen geändert wurde
- Modell/Parameter geändert wurden
```

### Cache behalten oder verwerfen

```text
[ ] Embedding-Cache behalten
[ ] Personenprofile neu berechnen
[ ] Embedding-Cache vollständig verwerfen
```

---

## Implementierungsphasen

### Phase 1: Referenzprofile aus Photos

```text
- Photos-Personen laden
- Faces je Person laden
- InsightFace-Embedding je Face erzeugen
- Cache speichern
- Centroid je Person berechnen
- Profilqualität anzeigen
- keine Schreiboperation
```

### Phase 2: Vorschläge für unbekannte Photos-Gesichter

```text
- Unknown-Faces aus Photos laden
- Embeddings erzeugen
- gegen Personenprofile vergleichen
- Vorschläge mit Score und Abstand erzeugen
- UI-Vorschau mit Einzel-/Mehrfachauswahl
```

### Phase 3: Freigegebene Zuordnung nach Photos

```text
- ausgewählte Vorschläge übernehmen
- Unknown Face bestehender Photos-Person zuordnen
- Protokoll schreiben
- keine automatische Neuanlage von Personen
```

### Phase 4: Verbesserung der Profilqualität

```text
- Outlier-UI
- manuelles Ausschließen einzelner Referenzfaces
- Multi-Cluster pro Person
- Kalibrierung der Schwellwerte
```

### Phase 5: Erweiterung auf Metadaten

```text
- ACDSee-XMP als zusätzliche Referenzquelle
- Picasa-XMP als zusätzliche Referenzquelle
- Importierte Namen als schwache Hinweise
- Abgleich Photos ↔ XMP
```

---

## Empfehlung

Die erste Version sollte streng konservativ sein:

```text
Photos-Personen sind die einzige Referenzquelle.
InsightFace erzeugt Embeddings für bekannte Photos-Gesichter.
Daraus werden Personenprofile gebildet.
Unbekannte Photos-Gesichter werden gegen diese Profile verglichen.
Das Paket erzeugt nur Vorschläge.
Geschrieben wird erst nach expliziter Auswahl.
```

Damit entsteht eine kontrollierbare Wiedererkennung, ohne externe Metadaten oder automatische Personenanlage einzubeziehen.
