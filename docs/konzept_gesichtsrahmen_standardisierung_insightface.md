# Konzept: Standardisierung von Gesichtsrahmen mit dem InsightFace-Plugin

## Bereich

`Bereinigung → Gesichtsrahmen standardisieren`

## Ziel

Im Paket **AV_ImgData** soll im Bereich **Bereinigung** eine Funktion entstehen, mit der vorhandene Gesichtsrahmen aus Synology Photos und Metadatenformaten wie ACDSee-XMP, Picasa-XMP oder Sidecar-XMP mithilfe des **InsightFace-Plugins** geprüft, verglichen und standardisiert werden können.

Die Funktion soll nicht blind alle vorhandenen Rahmen ersetzen. Stattdessen soll sie:

1. vorhandene Rahmen aus Photos und/oder Metadaten lesen,
2. InsightFace als Referenzdetektor nutzen,
3. Unterschiede berechnen,
4. Vorschläge erzeugen,
5. eine Vorschau bereitstellen,
6. die zu ersetzenden Rahmen explizit auswählbar machen,
7. erst nach Auswahl in Photos oder Metadaten schreiben,
8. Änderungen protokollieren und rückgängig machbar machen.

---

## Ausgangslage

Gesichtsrahmen werden je nach Quelle unterschiedlich gespeichert.

Synology Photos verwendet typischerweise:

```text
top_left.x
top_left.y
bottom_right.x
bottom_right.y
```

ACDSee-XMP, Picasa-XMP und andere Metadatenformate verwenden dagegen meist Varianten von:

```text
x
y
width
height
```

InsightFace liefert erkannte Bounding Boxes und optional Landmarks. Diese können als technische Referenz für Position und Größe eines Gesichtsrahmens verwendet werden.

Das Paket benötigt daher eine interne Normalform, damit Photos, XMP und InsightFace vergleichbar werden.

---

## Interne Normalform

Alle Quellen sollen intern auf ein gemeinsames Format gebracht werden:

```python
class NormalizedFaceFrame:
    source: str              # photos, acdsee_xmp, picasa_xmp, insightface
    image_id: int | None
    file_path: str
    person_id: int | None
    person_name: str | None
    face_id: int | None

    x: float                 # 0.0 - 1.0
    y: float                 # 0.0 - 1.0
    width: float             # 0.0 - 1.0
    height: float            # 0.0 - 1.0

    confidence: float | None
    landmarks: dict | None
    modified_at: datetime | None

    origin: str | None       # auto, manual, edited, imported, unknown
    origin_confidence: str   # certain, inferred, unknown
```

Synology Photos wird dabei konvertiert zu:

```python
x = top_left.x
y = top_left.y
width = bottom_right.x - top_left.x
height = bottom_right.y - top_left.y
```

---

## Position im Paket

Vorgeschlagene UI-Struktur:

```text
Bereinigung
└── Gesichtsrahmen standardisieren
    ├── Auswahl
    ├── Analyse
    ├── Vorschau
    ├── Standardisierung
    ├── Protokoll
    └── Rollback
```

Vorgeschlagene Backend-Struktur:

```text
src/
├── cleanup/
│   ├── face_frame_cleanup.py
│   ├── face_frame_standardizer.py
│   ├── face_frame_matcher.py
│   ├── face_frame_repository.py
│   └── face_frame_preview.py
├── insightface_plugin/
│   ├── detector.py
│   ├── cache.py
│   └── models.py
├── metadata/
│   ├── photos_regions.py
│   ├── acdsee_regions.py
│   ├── picasa_regions.py
│   ├── xmp_writer.py
│   └── region_normalizer.py
```

Die Logik soll nicht direkt in API-Endpunkten oder Vue-Komponenten implementiert werden, sondern als wiederverwendbare Service-Schicht.

---

## Auswahl nach Änderungen der letzten X Tage

Die Auswahl soll auf Änderungen der letzten **x Tage** begrenzbar sein.

UI-Option:

```text
Zeitraum:
[ ] Alle Bilder
[x] Nur Änderungen der letzten [30] Tage
```

Zusätzlich sollte auswählbar sein, worauf sich der Änderungsfilter bezieht:

```text
Änderungsfilter bezieht sich auf:
( ) Dateiänderungsdatum
( ) Photos-Datensatz geändert
( ) XMP-Datei geändert
( ) Gesichtsdaten geändert, falls verfügbar
```

Empfohlener Standard:

```text
Nur Dateien oder Metadaten, die in den letzten 30 Tagen geändert wurden
```

Backend-Beispiel:

```python
changed_since = now() - timedelta(days=config.changed_days)
```

Mögliche Filterquellen:

| Quelle | Filter |
|---|---|
| Synology Photos DB | `unit`, `live`, `face`, Änderungszeit falls verfügbar |
| Dateisystem | `mtime` der Bilddatei |
| XMP-Sidecar | `mtime` der `.xmp`-Datei |
| eingebettetes XMP | `mtime` der Bilddatei |
| Paket-Cache | letzter Scan / letzte Analyse |

Falls Synology Photos keine verlässliche Änderungszeit für Gesichtsrahmen liefert, muss dies in der UI kenntlich gemacht werden.

Beispielhinweis:

```text
Für Synology Photos wird der Änderungsfilter anhand der Datei- oder Datenbankänderung angewendet. Eine Änderung des einzelnen Gesichtsrahmens ist möglicherweise nicht separat ermittelbar.
```

---

## Herkunft der Photos-Gesichtsrahmen

Für Schreiboperationen nach Synology Photos muss unterschieden werden, ob ein Gesichtsrahmen automatisch von Photos erkannt, manuell angelegt oder nachträglich manuell verändert wurde. Diese Information ist wichtig, weil manuell gesetzte Rahmen in der Regel kuratierte Daten sind und nicht versehentlich durch automatische Standardisierung überschrieben werden dürfen.

Aktueller Kenntnisstand im Paket:

```text
Bekannt:
- Face-ID
- Person-ID
- Personenname
- Bounding Box
- Bild-/Unit-ID

Noch zu prüfen:
- ob Photos ein Feld für automatisch/manuell/editiert speichert
- ob diese Information über API oder nur über Datenbanktabellen ermittelbar ist
- ob manuell angelegte Rahmen eine andere Tabellenstruktur, ein anderes Flag oder andere Zeitstempel erhalten
```

Die Prüfung sollte über kontrollierte Testfälle erfolgen:

```text
1. Bild importieren und Photos automatisch Gesichter erkennen lassen.
2. Datenbank-/API-Zustand sichern.
3. Ein Gesicht manuell hinzufügen.
4. Datenbank-/API-Zustand vergleichen.
5. Einen automatisch erkannten Rahmen manuell verschieben.
6. Datenbank-/API-Zustand erneut vergleichen.
```

Interne Herkunftsklassen:

| Klasse | Bedeutung | Schreibschutz |
|---|---|---|
| `auto` | automatisch von Photos erkannt | kann nach Regel ersetzt werden |
| `manual` | manuell angelegt | standardmäßig geschützt |
| `edited` | automatisch erkannt, aber manuell verändert | standardmäßig geschützt |
| `imported` | aus Metadaten oder anderem System übernommen | abhängig vom Zielmodus |
| `unknown` | Herkunft nicht eindeutig bestimmbar | standardmäßig geschützt |

Falls Photos keine eindeutige Herkunft speichert, darf das Paket nur mit abgeleiteter Sicherheit arbeiten:

```text
origin = auto | manual | edited | imported | unknown
origin_confidence = certain | inferred | unknown
```

Heuristische Herkunft darf nicht wie sichere Herkunft behandelt werden. Die UI muss dann zum Beispiel `vermutlich automatisch`, `vermutlich manuell` oder `unbekannt` anzeigen.

---

## Auswahl des Zielsystems

Die Standardisierung soll wahlweise in Synology Photos oder in einem Metadatenformat erfolgen.

UI-Option:

```text
Ziel der Standardisierung:
[ ] Nur Vorschau / keine Änderung
[ ] Synology Photos
[ ] ACDSee-XMP
[ ] Picasa-XMP
[ ] eingebettetes XMP
[ ] Sidecar-XMP
```

Quellen für Vergleich:

```text
[x] Synology Photos
[x] ACDSee-XMP
[x] Picasa-XMP
[x] InsightFace-Erkennung
```

---

## Betriebsmodi

### Modus A: Nur analysieren

Keine Änderung. Unterschiede werden nur angezeigt.

Beispiel:

```text
Photos-Rahmen weicht 18 % von InsightFace ab.
ACDSee-Rahmen weicht 9 % ab.
Vorschlag: ACDSee übernehmen oder InsightFace-standardisiert verwenden.
```

### Modus B: Photos standardisieren

InsightFace oder ein anderes Format wird als Referenz genutzt. Die Gesichtsrahmen in Synology Photos werden angepasst.

Dieser Modus sollte als Expertenmodus gelten, da Synology Photos interne Daten bei späterer Reindexierung verändern oder überschreiben kann.

### Modus C: XMP standardisieren

Synology Photos bleibt unverändert. Die standardisierten Rahmen werden in ein XMP-Format geschrieben.

Dies ist der sicherere Standardmodus.

### Modus D: Photos zu XMP

Synology Photos gilt als führende Quelle. Die Rahmen werden nach XMP geschrieben.

### Modus E: XMP zu Photos

Vorhandene kuratierte XMP-Rahmen werden nach Photos übernommen oder mit Photos abgeglichen.

### Modus F: InsightFace zu Ziel

InsightFace ist die geometrische Referenz. Bestehende Namen und Personen-Zuordnungen werden beibehalten, aber Position und Größe der Rahmen werden ersetzt oder angepasst.

---

## InsightFace-Erkennungsparameter

InsightFace soll nicht nur als feste Erkennung mit einem hart codierten Standard laufen. Die Erkennungsparameter müssen in der Bereinigung einstellbar sein, weil sie direkten Einfluss darauf haben, ob kleine oder randnahe Gesichter gefunden werden.

Der relevante Parameter ist insbesondere `det_size` aus `FaceAnalysis.prepare(...)`. Im InsightFace-Code wird `prepare(ctx_id, det_thresh=0.5, det_size=None)` verwendet. Wenn `det_size` automatisch bzw. leer ist, werden im aktuellen Code Default-Detektionsgrößen von `(128, 128)` und `(640, 640)` gesetzt. `det_thresh` steht dort standardmäßig auf `0.5`.

### UI-Option: Detektionsgröße

```text
InsightFace-Erkennung
Detektionsgröße:
(x) Standard / automatisch
( ) 640 × 640 – normal
( ) 1280 × 1280 – kleine Gesichter suchen
( ) Benutzerdefiniert: [____] × [____]

Schwellwert det_thresh: [0.50]
Max. Gesichter pro Bild: [0 = unbegrenzt]
```

Empfohlene Profile:

| Profil | `det_size` | Zweck | Hinweis |
|---|---:|---|---|
| Automatisch | `None` | InsightFace-Default | nutzt interne Defaults |
| Standard | `(640, 640)` | normale Erkennung | guter Default für Bereinigung |
| Kleine Gesichter | `(1280, 1280)` | Gruppenbilder, kleine Gesichter, Hintergrundpersonen | deutlich langsamer |
| Schnelltest | `(320, 320)` | schnelle Vorprüfung | kann kleine Gesichter übersehen |
| Benutzerdefiniert | frei | Tests/Expertenmodus | Werte validieren |

`(640, 640)` sollte als normaler Default für gezielte Paketläufe angeboten werden. `(1280, 1280)` sollte als auswählbares Profil vorhanden sein, wenn kleine Gesichter gesucht werden sollen. Für NAS-Hardware muss die UI deutlich machen, dass größere Detektionsgrößen mehr RAM und CPU-Zeit benötigen.

### Mindestgesichtsgröße

Zusätzlich zur Detektionsgröße soll das Paket eine eigene Mindestgesichtsgröße filtern können. Diese Mindestgröße ist kein Ersatz für `det_size`, sondern ein Nachfilter auf erkannte Bounding Boxes.

```text
Mindestgesichtsgröße:
[ ] keine Mindestgröße
[x] Mindestbreite relativ zum Bild: [1.5] %
[x] Mindesthöhe relativ zum Bild:  [1.5] %
[ ] Mindestfläche relativ zum Bild: [0.03] %
```

Interne Konfiguration:

```json
{
  "insightface": {
    "det_size": [640, 640],
    "det_thresh": 0.5,
    "max_num": 0,
    "min_face_width_ratio": 0.015,
    "min_face_height_ratio": 0.015,
    "min_face_area_ratio": null
  }
}
```

Für die Suche nach kleinen oder fehlenden Gesichtern sollte das Profil `small_faces` verwendet werden können:

```json
{
  "insightface_profile": "small_faces",
  "det_size": [1280, 1280],
  "det_thresh": 0.5,
  "min_face_width_ratio": 0.005,
  "min_face_height_ratio": 0.005
}
```

### Bedeutung für die Suche nach fehlenden Gesichtern

Die Detektionsgröße muss nicht nur bei der Standardisierung vorhandener Rahmen, sondern auch bei der Suche nach fehlenden Gesichtern verfügbar sein.

Beispielmodus:

```text
Bereinigung → Fehlende Gesichter suchen

Quelle:
[x] Synology Photos vorhandene Gesichter
[x] XMP vorhandene Gesichter
[x] InsightFace neu erkennen

InsightFace-Profil:
( ) Standard 640 × 640
(x) Kleine Gesichter 1280 × 1280
( ) Benutzerdefiniert

Ergebnis:
[ ] Nur Gesichter zeigen, die in Photos fehlen
[ ] Nur Gesichter zeigen, die in XMP fehlen
[ ] Alle InsightFace-Gesichter ohne Match anzeigen
```

Ein gefundenes InsightFace-Gesicht gilt als „fehlend“, wenn es keinen ausreichend guten Match gegen bestehende Photos- oder XMP-Rahmen hat.

Vorschlagslogik:

```text
InsightFace-Gesicht erkannt
→ gegen Photos-Rahmen matchen
→ gegen XMP-Rahmen matchen
→ wenn kein Match >= Mindest-Score:
   Vorschlag „fehlendes Gesicht“ erzeugen
```

Dabei gelten dieselben Sicherheitsregeln wie bei der Standardisierung:

```text
- keine automatische Schreiboperation ohne Vorschau
- Einzel- und Mehrfachauswahl vor dem Schreiben
- Mindest-Score und Konfliktprüfung
- Zielauswahl Photos/XMP
- Backup und Änderungsprotokoll
```

### Cache-Auswirkung

`det_size`, `det_thresh`, `max_num` und Mindestgrößenfilter müssen Teil des Cache-Keys sein. Eine Erkennung mit `(640, 640)` darf nicht als Ergebnis für `(1280, 1280)` wiederverwendet werden.

Cache-Key:

```text
file_path
file_mtime
file_size
model_name
model_version
det_size
det_thresh
max_num
min_face_width_ratio
min_face_height_ratio
min_face_area_ratio
```

---

## Optionen für Position und Größe der Rahmen

Es sollen mehrere Strategien verfügbar sein, da unterschiedliche Systeme unterschiedlich große oder unterschiedlich zentrierte Rahmen bevorzugen.

### Rahmenstrategie

```text
Rahmenstrategie:
( ) InsightFace exakt übernehmen
( ) Zentriert auf InsightFace, feste Skalierung
( ) Bestehenden Rahmen nur korrigieren
( ) Mittelwert aus Photos/XMP/InsightFace
( ) Größten plausiblen Rahmen verwenden
( ) Kleinsten plausiblen Rahmen verwenden
( ) Benutzerdefinierte Randzugabe
```

---

## Positionsoptionen

### 1. InsightFace-Position exakt übernehmen

```text
x/y/width/height = InsightFace-Bounding-Box
```

Vorteil: technisch klar und reproduzierbar.  
Nachteil: Der Rahmen kann für Photos- oder XMP-Anzeigen zu eng sein.

### 2. Mittelpunkt übernehmen, Größe anpassen

Der Mittelpunkt von InsightFace wird übernommen, Breite und Höhe werden skaliert.

```python
center_x = insight_x + insight_width / 2
center_y = insight_y + insight_height / 2
new_width = insight_width * scale_x
new_height = insight_height * scale_y
```

Beispiel:

```text
Breite: 120 %
Höhe: 140 %
Vertikale Verschiebung: -5 %
```

### 3. Bestehende Position beibehalten, nur Größe standardisieren

Nützlich, wenn Photos oder XMP bereits manuell korrigiert wurden.

```text
Position: vorhandene Quelle
Größe: standardisierte Größe aus InsightFace
```

### 4. Bestehenden Rahmen nur bei starker Abweichung korrigieren

```text
Nur ändern, wenn:
- IoU < 0.70
- Mittelpunktabweichung > 8 %
- Größenabweichung > 20 %
```

Das schützt bereits manuell gute Rahmen.

### 5. Landmark-basierte Ausrichtung

Wenn InsightFace Landmarks liefert, kann der Rahmen anhand von Augen, Nase und Mund ausgerichtet werden.

Optionen:

```text
[x] Augen horizontal zentrieren
[x] Nase als vertikale Mitte berücksichtigen
[x] Kinn-/Mundbereich stärker einbeziehen
```

Für die erste Implementierung reicht jedoch Bounding Box plus Skalierung.

---

## Größenprofile

Vordefinierte Profile:

```text
Rahmengröße:
( ) Eng – nur Gesicht
( ) Normal – Gesicht mit leichtem Rand
( ) Groß – Gesicht mit Haar-/Kinnbereich
( ) Photos-kompatibel
( ) ACDSee-kompatibel
( ) Benutzerdefiniert
```

Beispielwerte:

| Profil | Breite | Höhe | Y-Verschiebung |
|---|---:|---:|---:|
| Eng | 100 % | 100 % | 0 % |
| Normal | 115 % | 125 % | -3 % |
| Groß | 130 % | 150 % | -6 % |
| Photos-kompatibel | 120 % | 135 % | -5 % |
| ACDSee-kompatibel | 110 % | 120 % | -3 % |

Benutzerdefinierte Parameter:

```text
Breite multiplizieren mit: [1.20]
Höhe multiplizieren mit:  [1.35]
X-Verschiebung:           [0.00]
Y-Verschiebung:           [-0.05]
Mindestgröße:             [0.02]
Maximalgröße:             [0.80]
Seitenverhältnis fixieren: [x]
```

---

## Matching zwischen vorhandenen Rahmen und InsightFace

Vor dem Schreiben muss entschieden werden, welcher erkannte InsightFace-Rahmen zu welchem vorhandenen Photos-/XMP-Rahmen gehört.

Kriterien:

1. **IoU / Überlappung**
2. **Mittelpunktabstand**
3. **Größenähnlichkeit**
4. **Personenname / Person-ID**
5. **InsightFace-Embedding**, falls künftig verwendet

Bewertungsmodell:

```text
Score =
  0.50 * IoU
+ 0.25 * Mittelpunktnähe
+ 0.15 * Größenähnlichkeit
+ 0.10 * Namens-/Personenhinweis
```

Schwellwerte:

```text
Score >= 0.80: sicherer Treffer
0.60 - 0.79: unsicher, Vorschau erforderlich
< 0.60: kein automatisches Matching
```

---

## Auswahl der zu ersetzenden Rahmen

Die Bereinigung muss vor dem Schreiben festlegen, **welche einzelnen Rahmen ersetzt werden sollen**. Es darf nicht ausreichen, nur Quelle und Ziel zu wählen. Die Vorschau erzeugt ersetzbare Einträge, und nur diese Einträge dürfen anschließend geschrieben werden.

### Auswahlmodi

```text
Auswahl der Ersetzungen:
( ) Keine automatisch auswählen
( ) Jeden Rahmen einzeln auswählen
( ) Alle sicheren Vorschläge auswählen
( ) Alle sichtbaren Vorschläge auswählen
( ) Alle Vorschläge gemäß Filter auswählen
```

### Einzelersatz

Jeder Vorschlag in der Vorschau bekommt eine eigene Auswahlbox:

```text
[x] ersetzen
[ ] nicht ersetzen
[gesperrt] manuell/geändert/unklare Herkunft
```

Einzelersatz muss immer möglich sein, auch wenn vorher eine automatische Vorauswahl verwendet wurde.

### Automatischer Ersatz

Automatisch ausgewählt werden dürfen nur Vorschläge, die alle aktiven Filter erfüllen:

```text
- Zielsystem passt
- Herkunft passt
- Mindest-Score erreicht
- keine Konflikte mit mehreren möglichen Gesichtern
- keine gesperrte Herkunft, außer ausdrücklich erlaubt
- Änderung liegt im gewählten Zeitraum
```

### Status je Vorschlag

```text
selected      # wird geschrieben
unselected    # wird nicht geschrieben
locked        # darf ohne Expertenfreigabe nicht geschrieben werden
needs_review  # unsicher, Benutzerentscheidung erforderlich
```

### Filter in der Vorschau

```text
[ ] sichere Matches
[ ] unsichere Matches
[ ] starke Abweichungen
[ ] automatisch erkannte Photos-Rahmen
[ ] manuell angelegte Photos-Rahmen
[ ] manuell geänderte Photos-Rahmen
[ ] unbekannte Herkunft
[ ] Ziel: Photos
[ ] Ziel: XMP
```

Wichtige Regel:

```text
Das Backend darf beim Schreiben nur die IDs ersetzen, die in der Vorschau freigegeben wurden. Es darf beim Apply-Schritt nicht erneut eigenständig entscheiden, weitere Rahmen zu ersetzen.
```

---

## Konfliktfälle

```text
Fall 1: Photos hat Gesicht, InsightFace findet keines.
Optionen: unverändert lassen, als veraltet markieren, manuell prüfen.

Fall 2: InsightFace findet Gesicht, Photos/XMP nicht.
Optionen: neuen Rahmen erzeugen, ignorieren, nur als Vorschlag speichern.

Fall 3: Mehrere InsightFace-Gesichter liegen nahe an einem vorhandenen Rahmen.
Optionen: nicht automatisch ändern, manuelle Auswahl.

Fall 4: Rahmen liegt außerhalb des Bildes.
Optionen: automatisch begrenzen, als Fehler protokollieren.
```

---

## Standardisierungsablauf

### Schritt 1: Auswahl

```text
Quelle:
[x] Photos
[x] ACDSee-XMP
[ ] Picasa-XMP
[x] InsightFace

Ziel:
[x] ACDSee-XMP
[ ] Photos

Zeitraum:
[x] Nur letzte 30 Tage

Photos-Herkunft:
[x] Nur automatisch erkannte Rahmen
[ ] Manuell angelegte/geänderte Rahmen einschließen

Rahmenprofil:
Photos-kompatibel

Schreibmodus:
( ) Vorschau
(x) Änderungen nach Bestätigung schreiben
```

### Schritt 2: Kandidaten laden

```python
candidates = repository.find_images(
    changed_since=changed_since,
    sources=["photos", "xmp"],
    include_faces=True,
)
```

### Schritt 3: InsightFace-Erkennung

```python
detections = insightface.detect_faces(
    file_path,
    det_size=config.insightface.det_size,
    det_thresh=config.insightface.det_thresh,
    max_num=config.insightface.max_num,
    min_face_width_ratio=config.insightface.min_face_width_ratio,
    min_face_height_ratio=config.insightface.min_face_height_ratio,
)
```

Optimierung:

```text
- nicht erneut erkennen, wenn Datei unverändert und Ergebnis im Cache liegt
- Cache-Key aus Dateipfad, Größe, mtime, Modellversion und InsightFace-Erkennungsparametern
- Batch-Verarbeitung
- Job-System, damit die UI nicht blockiert
```

### Schritt 4: Normalisieren

```python
photos_frame = normalize_photos_region(...)
acdsee_frame = normalize_acdsee_region(...)
insight_frame = normalize_insightface_bbox(...)
```

### Schritt 5: Vergleichen

```python
matches = matcher.match(existing_frames, insight_frames)
```

### Schritt 6: Vorschau

Die UI sollte eine visuelle Vorschau ermöglichen:

```text
[Originalbild]
- aktueller Photos-Rahmen
- aktueller XMP-Rahmen
- InsightFace-Rahmen
- neuer Zielrahmen
```

### Schritt 7: Schreiben

```python
if target == "photos":
    photos_writer.update_face_frame(...)

if target == "acdsee_xmp":
    acdsee_writer.update_region(...)

if target == "picasa_xmp":
    picasa_writer.update_region(...)
```

Vor jedem Schreiben muss ein Backup oder Änderungsprotokoll erzeugt werden.

---

## Schreibsicherheit und Rollback

Jede Änderung sollte in einer Paket-eigenen Tabelle protokolliert werden:

```sql
CREATE TABLE face_frame_cleanup_log (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    image_id INTEGER,
    face_id INTEGER,
    person_id INTEGER,
    target_format TEXT NOT NULL,
    old_frame_json TEXT NOT NULL,
    new_frame_json TEXT NOT NULL,
    origin TEXT,
    origin_confidence TEXT,
    selection_state TEXT,
    strategy TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL
);
```

Für XMP-Dateien zusätzlich:

```text
filename.xmp.bak
```

oder paketverwaltete Backups:

```text
/var/packages/AV_ImgData/var/backups/xmp/...
```

Rollback-Funktion:

```text
Bereinigung → Protokoll → Änderung zurücknehmen
```

---

## API-Entwurf

### Analyse starten

```http
POST /api/cleanup/face-frames/analyze
```

Payload:

```json
{
  "sources": ["photos", "acdsee_xmp", "insightface"],
  "targets": ["acdsee_xmp"],
  "changed_days": 30,
  "photos_origin_filter": ["auto"],
  "include_unknown_origin": false,
  "replace_selection_mode": "safe_matches",
  "frame_profile": "photos_compatible",
  "insightface_profile": "standard",
  "insightface": {
    "det_size": [640, 640],
    "det_thresh": 0.5,
    "max_num": 0,
    "min_face_width_ratio": 0.015,
    "min_face_height_ratio": 0.015
  },
  "mode": "preview"
}
```

### Vorschau abrufen

```http
GET /api/cleanup/face-frames/preview?job_id=...
```

Antwort:

```json
{
  "items": [
    {
      "item_id": "item-001",
      "file_path": "/volume1/photo/Benno/2025/example.jpg",
      "image_id": 76935,
      "person_name": "Bea",
      "source_frame": {
        "source": "photos",
        "x": 0.5299,
        "y": 0.2836,
        "width": 0.0784,
        "height": 0.1394
      },
      "insight_frame": {
        "x": 0.535,
        "y": 0.290,
        "width": 0.074,
        "height": 0.130
      },
      "target_frame": {
        "x": 0.526,
        "y": 0.276,
        "width": 0.089,
        "height": 0.176
      },
      "match_score": 0.91,
      "origin": "auto",
      "origin_confidence": "certain",
      "selection_state": "selected",
      "action": "update"
    }
  ]
}
```

### Änderungen übernehmen

```http
POST /api/cleanup/face-frames/apply
```

Payload:

```json
{
  "job_id": "abc123",
  "apply_items": "selected_only",
  "selected_item_ids": ["item-001", "item-002"]
}
```

### Rollback

```http
POST /api/cleanup/face-frames/rollback
```

Payload:

```json
{
  "log_ids": [1001, 1002, 1003]
}
```

---

## UI-Konzept

```text
Quellen
[x] Synology Photos
[x] ACDSee-XMP
[ ] Picasa-XMP
[x] InsightFace

Ziel
( ) Nur Vorschau
( ) Synology Photos
(x) ACDSee-XMP
( ) Picasa-XMP
( ) Sidecar-XMP

Zeitraum
( ) Alle
(x) Nur Änderungen der letzten [30] Tage

Rahmenstrategie
( ) InsightFace exakt
(x) Photos-kompatibel
( ) bestehende Rahmen nur korrigieren
( ) Benutzerdefiniert

InsightFace-Erkennung
(x) Standard / automatisch
( ) 640 × 640 – normal
( ) 1280 × 1280 – kleine Gesichter suchen
( ) Benutzerdefiniert
Schwellwert det_thresh: [0.50]
Mindestgesichtsgröße: [1.5] % Breite/Höhe

Automatik
[x] Nur sichere Treffer automatisch auswählen
Mindest-Score: [0.80]
Max. Mittelpunktabweichung: [8] %
Max. Größenabweichung: [25] %

Photos-Herkunft
(x) Nur automatisch erkannte Rahmen
( ) Nur manuell angelegte Rahmen
( ) Nur manuell geänderte Rahmen
( ) Manuell angelegte oder geänderte Rahmen
( ) Alle Rahmen
[ ] Rahmen mit unbekannter Herkunft einschließen

Auswahl der Ersetzungen
( ) Keine automatisch auswählen
( ) Jeden Rahmen einzeln auswählen
(x) Alle sicheren Vorschläge auswählen
( ) Alle sichtbaren Vorschläge auswählen
( ) Alle Vorschläge gemäß Filter auswählen

Schreiben
[x] Backup erzeugen
[x] Änderungsprotokoll speichern
[ ] Photos-Datenbank direkt ändern
```

Der Punkt `Photos-Datenbank direkt ändern` darf nicht vorausgewählt sein und sollte als Expertenmodus markiert werden.

---

## Wiederverwendung bisheriger Paketlogik

### Photos-Zugriff

Wiederverwenden:

```text
photos_db.py
photos.sql
service.py
schema_check.py
```

Für:

- Bild-ID ermitteln
- Dateipfad auflösen
- `folder_id`, `unit`, `live` nutzen
- vorhandene Faces lesen
- Personenzuordnung lesen

### XMP-/Exporter-Logik

Wiederverwenden:

```text
exporter.py
metadata parser
XMP-Face-Matching
```

Für:

- ACDSee-Regionen lesen
- Picasa-Regionen lesen
- vorhandene Namen übernehmen
- Photos-Rahmen mit XMP-Rahmen vergleichen

### API-/UI-Muster

Wiederverwenden:

```text
FastAPI-Endpunkte
Vue-Komponentenstruktur
/api/status-Muster
credentials/include
X-SYNO-TOKEN Handling
```

### Cache und Optimierung

Neuer Cache nach bisherigem Paketstil:

```sql
CREATE TABLE insightface_detection_cache (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_mtime REAL NOT NULL,
    file_size INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    det_size TEXT NOT NULL,
    det_thresh REAL NOT NULL,
    max_num INTEGER NOT NULL,
    min_face_width_ratio REAL,
    min_face_height_ratio REAL,
    min_face_area_ratio REAL,
    detections_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_path, file_mtime, file_size, model_name, model_version, det_size, det_thresh, max_num, min_face_width_ratio, min_face_height_ratio, min_face_area_ratio)
);
```

Dadurch wird InsightFace nicht unnötig erneut ausgeführt.

---

## Optimierungsregeln

### Batch statt Einzelanalyse

InsightFace soll nicht synchron pro UI-Aktion ausgeführt werden.

```text
Job starten → Backend verarbeitet → UI pollt Status
```

### Pagination

Wie bei den Photos-Endpunkten:

```text
offset
limit
total
```

### Nur relevante Bilder laden

Bei geändertem Zeitraum:

```text
changed_since != None
```

Bei Ziel XMP:

```text
nur Bilder mit XMP oder Bilder, für die XMP erzeugt werden darf
```

Bei Ziel Photos:

```text
nur Bilder mit Photos-ID und vorhandenen Face-IDs
```

### Rechenlast begrenzen

Optionen:

```text
Maximale Bilder pro Lauf: [500]
Maximale parallele Prozesse: [1-2]
Nur nachts ausführen: optional später
```

Auf einem NAS sollte InsightFace vorsichtig verwendet werden, besonders ohne GPU.

---

## Empfohlene Default-Einstellungen

Sichere Voreinstellung:

```text
Modus: Vorschau
Quellen: Photos + XMP + InsightFace
Ziel: keine Änderung
Zeitraum: letzte 30 Tage
Rahmenprofil: Photos-kompatibel
InsightFace-Profil: Standard / 640 × 640
Mindestgesichtsgröße: 1.5 % Breite/Höhe
Mindest-Score: 0.80
Automatisch ändern: nein
Automatisch vorauswählen: nur sichere Matches
Photos-Herkunft: nur automatisch erkannte Rahmen
Unbekannte Herkunft einschließen: nein
Backup: ja
Direkte Photos-DB-Änderung: aus
```

Für produktive Nutzung nach Prüfung:

```text
Ziel: ACDSee-XMP oder Sidecar-XMP
Strategie: InsightFace zentriert + Photos-kompatible Größe
Nur sichere Treffer
Backup aktiv
```

Photos direkt zu ändern sollte Expertenmodus bleiben.

---

## Pseudocode

```python
def analyze_face_frame_cleanup(config):
    changed_since = resolve_changed_since(config.changed_days)

    images = repository.find_candidate_images(
        sources=config.sources,
        changed_since=changed_since,
        limit=config.limit,
    )

    results = []

    for image in images:
        existing_frames = []

        if "photos" in config.sources:
            existing_frames += photos_repo.get_face_frames(image)

        if "acdsee_xmp" in config.sources:
            existing_frames += acdsee_repo.get_face_frames(image)

        if "picasa_xmp" in config.sources:
            existing_frames += picasa_repo.get_face_frames(image)

        insight_frames = insight_cache.get_or_detect(image.file_path)

        normalized_existing = normalize_all(existing_frames)
        normalized_insight = normalize_all(insight_frames)

        matches = match_faces(
            existing=normalized_existing,
            detected=normalized_insight,
            min_score=config.min_score,
        )

        for match in matches:
            target_frame = standardizer.create_target_frame(
                match=match,
                strategy=config.strategy,
                profile=config.frame_profile,
            )

            selection_state = decide_selection_state(match, target_frame, config)

            results.append({
                "image": image,
                "match": match,
                "target_frame": target_frame,
                "selection_state": selection_state,
                "action": decide_action(match, config),
            })

    return create_preview_job(results)
```

Beim Schreiben:

```python
def apply_face_frame_cleanup(job_id, selected_item_ids):
    preview_items = preview_repository.get_items(job_id)

    for item in preview_items:
        if item.item_id not in selected_item_ids:
            continue
        if item.selection_state == "locked":
            raise PermissionError("Locked face frame requires explicit expert override")
        writer.write(item)
```

---

## Datenfluss

```text
Photos DB/API
      │
      ├── vorhandene Faces
      │
XMP Parser
      │
      ├── vorhandene Regionen
      │
InsightFace Plugin
      │
      ├── erkannte Gesichter
      │
Normalizer
      │
      ├── einheitliches x/y/w/h Format
      │
Matcher
      │
      ├── Zuordnung vorhandener Rahmen zu InsightFace
      │
Standardizer
      │
      ├── neuer Zielrahmen
      │
Preview
      │
      ├── Benutzerprüfung
      │
Writer
      │
      ├── Photos oder XMP schreiben
      │
Log / Backup
```

---

## Risiken

### Photos direkt ändern

Synology Photos kann interne Daten später durch Reindexierung oder eigene Gesichtserkennung überschreiben.

Gegenmaßnahmen:

```text
- nur mit Backup/Log
- zuerst API nutzen, falls möglich
- direkte DB-Änderung nur Expertenmodus
- schema_check vor Aktivierung
```

### Falsches Matching

Bei Gruppenbildern können Rahmen falsch zugeordnet werden.

Gegenmaßnahmen:

```text
- Mindest-Score
- Vorschaupflicht bei Unsicherheit
- keine automatische Änderung bei mehreren Kandidaten
```

### XMP-Schreibfehler

XMP-Strukturen sind empfindlich.

Gegenmaßnahmen:

```text
- Backup
- validierbarer Writer
- nur bekannte Namespaces ändern
- unbekannte XMP-Blöcke erhalten
```

### Performance

InsightFace kann auf NAS-Hardware rechenintensiv sein.

Gegenmaßnahmen:

```text
- Cache
- Batch
- Limit
- Zeitraumfilter
- Job-System
```

---

## Implementierungsphasen

### Phase 1: Analyse und Vorschau

```text
- Nur Vorschau
- Quellen: Photos + ACDSee-XMP + InsightFace
- Ziel: kein Schreiben
- Zeitraumfilter letzte x Tage
- Normalisierung aller Rahmen auf x/y/w/h
- Matching per IoU + Mittelpunktabstand
- Anzeige der Abweichungen
- InsightFace-Erkennungsprofil `standard` / `small_faces`
- Einzel- und Mehrfachauswahl in der Vorschau
```

### Phase 2: Schreiben nach XMP

```text
- Schreiben nach ACDSee-XMP / Sidecar-XMP
- Backup
- Änderungsprotokoll
- Rollback
- nur ausgewählte Vorschau-IDs schreiben
```

### Phase 3: Photos als Ziel

```text
- Photos als Schreibziel
- Expertenmodus
- Herkunftsprüfung auto/manual/edited/unknown
- schema_check
- optional direkte DB-/API-Aktualisierung
```

### Phase 4: Erweiterungen

```text
- Picasa-XMP
- eingebettetes XMP
- Profile pro Zielsystem
- Batch-Jobs mit Fortschritt
- Suche nach fehlenden Gesichtern mit wählbarer `det_size`
```

---

## Empfehlung

Die Funktion sollte als **vorschlagsbasierte Bereinigung** umgesetzt werden.

Empfohlener Standard:

```text
InsightFace dient als geometrische Referenz.
Photos und XMP liefern vorhandene Namen und Zuordnungen.
Das Paket berechnet daraus einen standardisierten Zielrahmen.
Geschrieben wird zunächst nur in XMP oder Sidecar-XMP.
Photos-Änderungen bleiben Expertenmodus.
Nur in der Vorschau ausgewählte Rahmen werden ersetzt.
```

Damit bleibt die Funktion robust, nachvollziehbar und kompatibel mit der bisherigen Architektur von AV_ImgData.
