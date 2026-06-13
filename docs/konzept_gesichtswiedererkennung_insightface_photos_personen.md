# Konzept: Gesichtswiedererkennung mit InsightFace auf Basis von Photos-Personen

## Bereich

`Bereinigung → Gesichtswiedererkennung aufbauen`

## Ziel

Im Paket **AV_ImgData** soll eine Gesichtswiedererkennung implementiert werden, die zunächst ausschließlich auf den bereits in **Synology Photos** vorhandenen Personen und Gesichtern basiert.

Die erste Ausbaustufe soll:

1. vorhandene Photos-Personen und deren zugeordnete Gesichter auslesen,
2. für diese Gesichter InsightFace-Embeddings berechnen,
3. pro Photos-Person ein internes Wiedererkennungsprofil aufbauen,
4. mögliche Ausreißer in den Referenzgesichtern finden,
5. unbekannte oder fehlende Gesichter gegen diese Profile vergleichen,
6. Vorschläge zur Personenzuordnung erzeugen,
7. die Vorschläge in der UI prüfbar machen,
8. erst nach Freigabe nach Photos oder in Paketdaten schreiben.

Die Funktion ergänzt das Konzept zur Gesichtsrahmen-Standardisierung. Dort werden Rahmenpositionen standardisiert; hier werden erkannte Gesichter Personen zugeordnet.

---

## Abgrenzung

### In der ersten Version enthalten

```text
- Quelle: Synology Photos Personen
- Quelle: Synology Photos vorhandene Face-IDs und Bounding Boxes
- InsightFace-Erkennung und Embedding-Berechnung
- Personenprofile aus bekannten Photos-Gesichtern
- Prüfung möglicher Referenz-Ausreißer mit Fundliste
- Vergleich unbekannter Gesichter gegen bekannte Personenprofile
- Vorschau und manuelle Freigabe
- Cache für Embeddings und Vergleichsergebnisse
```

### In der ersten Version nicht enthalten

```text
- Training aus ACDSee-XMP oder Picasa-XMP
- automatische Erstellung neuer Photos-Personen
- vollautomatisches Schreiben ohne Vorschau
- automatische Änderung bestehender Photos-Zuordnungen
- externe Bildquellen außerhalb der Photos-Bibliothek
- Nutzung von Alters-/Geschlechtsmerkmalen als Entscheidungsgrundlage
```

XMP- und Metadatenformate können später als zusätzliche Referenzquellen genutzt werden, sollen aber für die erste Implementierung bewusst ausgeschlossen bleiben.

---

## Technische Grundlage

InsightFace liefert nach der Gesichtserkennung pro erkanntem Gesicht eine Bounding Box, Landmarks und bei geladenem Recognition-Modul ein Embedding. Der Vergleich zwischen zwei Embeddings erfolgt üblicherweise über Cosine Similarity.

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
- findet mögliche Referenz-Ausreißer
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
    ├── Referenz-Ausreißer prüfen
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
│   ├── reference_outlier_service.py
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

Vor der Nutzung als Referenz muss geprüft werden, ob die bekannten Photos-Gesichter einer Person überhaupt konsistent sind. Genau dafür wird die Ausreißerprüfung als eigener Prüfpunkt eingeführt.

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
    outlier_state: str | None     # normal, suspected, confirmed, excluded, needs_review
    outlier_reason: str | None

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

### Referenz-Ausreißer

```sql
CREATE TABLE recognition_reference_outlier (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER,
    person_id INTEGER NOT NULL,
    person_name TEXT NOT NULL,
    face_id INTEGER NOT NULL,
    image_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    embedding_id INTEGER NOT NULL,
    average_similarity REAL,
    similarity_to_centroid REAL,
    nearest_other_person_id INTEGER,
    nearest_other_person_name TEXT,
    nearest_other_person_score REAL,
    outlier_score REAL NOT NULL,
    reason TEXT NOT NULL,
    review_state TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
```

Ein Eintrag in dieser Tabelle bedeutet nicht automatisch, dass Synology Photos falsch ist. Er bedeutet nur, dass das Referenzgesicht für den Profilaufbau auffällig ist und in einer Fundliste geprüft werden sollte.

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

Bei bekannten Photos-Gesichtern sollte der vorhandene Photos-Rahmen als Zuschnitt oder Matching-Anker genutzt werden. Wenn InsightFace auf dem Bild mehrere Gesichter erkennt, muss das InsightFace-Gesicht gewählt werden, dessen Bounding Box am besten zum Photos-Rahmen passt.

### Schritt 4: Ausreißer prüfen

Nicht jedes einer Person zugeordnete Photos-Gesicht ist zwingend korrekt. Deshalb läuft eine Ausreißerprüfung als eigener Prüfpunkt mit Fundliste.

```text
1. Embeddings je Person berechnen.
2. Paarweise Similarity innerhalb der Person berechnen.
3. Durchschnittliche Similarity je Face bestimmen.
4. Similarity zum Personen-Centroid bestimmen.
5. Nächstähnliche andere Person bestimmen.
6. Auffällige Gesichter in die Fundliste schreiben.
7. Je nach Review-Status in das Profil aufnehmen oder ausschließen.
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

## Prüfung möglicher Referenz-Ausreißer

Die Ausreißerprüfung ist ein eigener Prüfpunkt im Bereich **Bereinigung**. Sie dient dazu, mögliche falsche Zuordnungen innerhalb der bereits vorhandenen Synology-Photos-Personen zu finden.

Typischer Fall:

```text
Photos-Person „Bea“ hat 80 Gesichter.
79 Gesichter sind untereinander ähnlich.
1 Gesicht passt deutlich schlechter zu Bea und ähnelt stärker einer anderen Person.
→ Fundlisteneintrag „möglicher Referenz-Ausreißer“.
```

Typische Fundgründe:

```text
- geringe durchschnittliche Similarity zu anderen Gesichtern derselben Person
- geringe Similarity zum Personen-Centroid
- höhere Similarity zu einer anderen Photos-Person
- starker Abstand zum Medoid der eigenen Person
- sehr schlechte Bild-/Face-Qualität
- sehr kleine oder unvollständige Bounding Box
```

### UI-Fundliste

```text
Bereinigung → Gesichtswiedererkennung aufbauen → Referenz-Ausreißer prüfen

Filter:
[ ] Nur starke Ausreißer
[ ] Nur mögliche Verwechslungen mit anderer Person
[ ] Nur schlechte Qualität
[ ] Nur kleine Gesichter
[ ] Bereits geprüfte ausblenden

Tabelle:
Person | Bild | Face-ID | Grund | Score eigene Person | nächstähnliche Person | Aktion
```

Mögliche Aktionen pro Fund:

```text
[ ] Als korrekt bestätigen
[ ] Nur aus Wiedererkennungsprofil ausschließen
[ ] Später prüfen
[ ] In Photos prüfen/öffnen
[ ] Als mögliche Fehlzuordnung markieren
```

Wichtig: Die erste Implementierung soll Ausreißer **nicht automatisch aus Synology Photos entfernen** und auch keine Photos-Zuordnung automatisch ändern. Ein Ausschluss betrifft zunächst nur das interne Wiedererkennungsprofil.

### Statusmodell

```text
suspected       # automatisch als auffällig erkannt
confirmed       # Benutzer bestätigt: gehört korrekt zu dieser Person
excluded        # Benutzer schließt Face aus dem Profil aus
needs_review    # unklar, später prüfen
ignored         # bewusst ignoriert
```

### Entscheidungslogik

Ein Referenzgesicht wird als möglicher Ausreißer vorgeschlagen, wenn mindestens eine der folgenden Bedingungen erfüllt ist:

```text
- average_similarity_to_same_person < outlier_similarity_threshold
- similarity_to_centroid < centroid_threshold
- nearest_other_person_score > similarity_to_own_person + conflict_margin
- quality_score < min_reference_quality
```

Startwerte, konfigurierbar:

| Parameter | Startwert | Bedeutung |
|---|---:|---|
| `outlier_similarity_threshold` | `0.35` | unterhalb davon auffällig innerhalb derselben Person |
| `centroid_threshold` | `0.40` | unterhalb davon schwacher Bezug zum Personenprofil |
| `conflict_margin` | `0.05` | andere Person ist merklich ähnlicher |
| `min_reference_quality` | optional | nur nutzen, wenn Quality-Score belastbar ist |

Die Werte sind Startwerte und müssen anhand der eigenen Photos-Bibliothek kalibriert werden.

### Nutzung beim Profilaufbau

Beim Profilaufbau wird unterschieden:

```text
normal / confirmed: darf in das Profil einfließen
suspected: standardmäßig aus Profil ausschließen, aber in Fundliste anzeigen
excluded: nicht in das Profil aufnehmen
needs_review: je nach Einstellung ausschließen oder mit geringerem Gewicht verwenden
```

Empfohlener Default:

```text
Mögliche Ausreißer aus dem Profil ausschließen.
Fundliste erzeugen.
Keine Änderung in Synology Photos.
```

### API-Entwurf

```http
POST /api/recognition/outliers/analyze
```

```json
{
  "source": "photos_person_faces",
  "min_faces_per_person": 3,
  "outlier_similarity_threshold": 0.35,
  "centroid_threshold": 0.40,
  "conflict_margin": 0.05,
  "include_hidden_persons": false,
  "include_unnamed_persons": false
}
```

```http
GET /api/recognition/outliers?job_id=...
```

```json
{
  "items": [
    {
      "outlier_id": 1001,
      "person_id": 19431,
      "person_name": "Bea",
      "face_id": 66485,
      "image_id": 76935,
      "file_path": "/volume1/photo/Benno/2025/example.jpg",
      "average_similarity": 0.28,
      "similarity_to_centroid": 0.31,
      "nearest_other_person_id": 19432,
      "nearest_other_person_name": "Asta",
      "nearest_other_person_score": 0.49,
      "reason": "nearest_other_person_higher",
      "review_state": "suspected",
      "action": "exclude_from_profile"
    }
  ]
}
```

```http
POST /api/recognition/outliers/review
```

```json
{
  "outlier_id": 1001,
  "review_state": "excluded",
  "action": "exclude_from_profile"
}
```

### Pseudocode

```python
def analyze_reference_outliers(person_profiles):
    outliers = []

    for profile in person_profiles:
        embeddings = profile.reference_embeddings
        if len(embeddings) < 3:
            continue

        for embedding in embeddings:
            same_person_score = average_similarity(
                embedding,
                embeddings,
                exclude_self=True,
            )
            centroid_score = cosine_similarity(
                embedding,
                profile.centroid_embedding,
            )
            nearest_other = matcher.find_nearest_other_person(
                embedding,
                profile.person_id,
            )

            reason = decide_outlier_reason(
                same_person_score=same_person_score,
                centroid_score=centroid_score,
                nearest_other=nearest_other,
            )

            if reason:
                outliers.append(create_outlier_item(embedding, profile, reason))

    return outlier_repository.create_job(outliers)
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

Die Werte sind konservative Startwerte und müssen mit den eigenen Photos-Daten kalibriert werden.

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

Ausreißer dürfen nicht gelöscht werden. Sie werden nur für das Wiedererkennungsprofil ausgeschlossen oder zur Prüfung markiert.

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

### Referenz-Ausreißer prüfen

```text
Bereinigung → Gesichtswiedererkennung aufbauen → Referenz-Ausreißer prüfen

Prüfung:
[x] mögliche falsche Photos-Zuordnungen suchen
[x] schlechte Referenzgesichter markieren
[x] Ausreißer beim Profilaufbau ausschließen

Schwellwerte:
Min. Similarity zur eigenen Person: [0.35]
Min. Similarity zum Centroid: [0.40]
Konfliktabstand zu anderer Person: [0.05]

Aktionen:
[Fundliste erzeugen]
[Markierte aus Profil ausschließen]
[Als geprüft markieren]
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
- Fundlisten anzeigen
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
- Referenz-Ausreißer automatisch aus Photos entfernen
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

        outliers = reference_outlier_service.analyze(person, embeddings)
        valid_embeddings = reference_outlier_service.filter_for_profile(embeddings, outliers)

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
- Referenz-Ausreißer werden nicht automatisch in Photos geändert.
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
- Ausreißerprüfung pro Person bündeln
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
Alle Photos-Personen → alle Referenzgesichter → alle Embeddings prüfen → Ausreißer prüfen → Profile neu bilden
```

### Inkrementeller Neuaufbau

```text
Nur Personen neu berechnen, bei denen:
- neue Faces hinzugekommen sind
- Faces entfernt wurden
- Person umbenannt wurde
- Face-Rahmen geändert wurde
- Modell/Parameter geändert wurden
- Ausreißer-Review geändert wurde
```

### Cache behalten oder verwerfen

```text
[ ] Embedding-Cache behalten
[ ] Personenprofile neu berechnen
[ ] Ausreißerprüfung neu berechnen
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

### Phase 1b: Referenz-Ausreißer prüfen

```text
- paarweise Similarity je Person berechnen
- mögliche falsche Photos-Zuordnungen erkennen
- Fundliste erzeugen
- Ausreißer nicht automatisch in Photos ändern
- Ausschluss einzelner Referenzfaces nur für internes Profil erlauben
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
- Outlier-UI erweitern
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
Mögliche Ausreißer werden als eigene Fundliste angezeigt.
Ausreißer werden nur intern aus Profilen ausgeschlossen, nicht automatisch in Photos geändert.
Daraus werden Personenprofile gebildet.
Unbekannte Photos-Gesichter werden gegen diese Profile verglichen.
Das Paket erzeugt nur Vorschläge.
Geschrieben wird erst nach expliziter Auswahl.
```

Damit entsteht eine kontrollierbare Wiedererkennung, ohne externe Metadaten, automatische Personenanlage oder automatische Korrekturen an Synology Photos einzubeziehen.
