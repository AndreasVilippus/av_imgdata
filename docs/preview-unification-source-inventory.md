# Bestandsaufnahme aus dem Quellcode zur Vereinheitlichung der Previews

## Zweck

Dieses Dokument ergänzt `docs/preview-unification-technical-concept.md` um eine konkrete Ist-Aufnahme aus dem aktuellen Quellcode. Ziel ist, vor der Umsetzung klar zu trennen zwischen:

- bereits vorhandener Infrastruktur, die weiterverwendet werden soll,
- mehrfach vorhandener Logik, die vereinheitlicht werden soll,
- fehlenden Verträgen bzw. Komponenten, die neu geschaffen werden müssen.

Damit soll die technische Umsetzung möglichst mechanisch und in kleinen Schritten erfolgen können.

---

## 1. Wesentliche Erkenntnis

Die Preview-Infrastruktur ist bereits teilweise zentralisiert. Insbesondere existieren schon:

- ein zentraler Backend-Endpunkt für lokale Dateibilder,
- eine zentrale UI-Funktion zur Erzeugung dieses Preview-URLs,
- ein Bilddecoder mit Preview-Pfad und EXIF-Ausrichtung,
- RAW-/HEIC-Unterstützung über Decoder bzw. eingebettete JPEG-Previews,
- eine Bounding-Box-Normalisierung im Backend,
- `display_bbox` bzw. `display_normalized` für UI-taugliche Koordinaten,
- Synology-Photos-Thumbnails für Bilder und Personen,
- Browser-Kompatibilitätsprüfung für Bildformate,
- Fallback-Logik bei fehlgeschlagenen Bild-URLs,
- bestehende Tests für Preview-URL, Decoder-Fallback und Bounding-Box-Ausrichtung.

Daraus folgt: Die Vereinheitlichung sollte nicht mit einem neuen Preview-Backend beginnen. Der erste Schritt kann primär in der UI und in Adapterfunktionen erfolgen.

---

## 2. Bestehende zentrale lokale Preview-URL

In `ui/src/App.vue` existiert bereits:

```js
getBackendImagePreviewUrl(path) {
    const normalized = String(path || '').trim();
    return normalized
        ? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(normalized)}`
        : '';
}
```

Diese Funktion wird bereits von mehreren Bereichen verwendet:

- `faceMatchMixin.js`
- `checksMixin.js`
- `cleanupMixin.js`

### Konsequenz

Der geplante `PreviewResolver` muss diesen Pfad übernehmen und darf keine neue parallele URL-Erzeugung einführen.

Empfehlung:

```text
getBackendImagePreviewUrl()
        ↓
previewResolver.resolveLocalFile()
```

Später kann die bestehende Funktion selbst intern auf den Resolver delegieren, um Rückwärtskompatibilität während der Migration zu behalten.

---

## 3. Backend-Endpunkt `/api/file_image`

In `src/api/imgdata_api.py` existiert bereits:

```text
GET /api/file_image?path=<path>&preview=<flag>
```

Der Parameter `preview` wird als aktiv erkannt bei:

```text
1
true
yes
preview
```

Wenn Preview angefordert wird, wird der vorhandene `ImageDecodeService` verwendet.

### Bedeutung

Der Endpunkt ist bereits der geeignete zentrale Einstieg für lokale Dateipreviews. Eine neue API wie `/api/preview` ist für Phase 1 nicht notwendig.

Eine spätere API-Vereinheitlichung sollte eher diesen Endpunkt erweitern oder intern kapseln, statt ihn parallel zu ersetzen.

---

## 4. Bestehender Preview-Decoder

`src/services/image_decode_service.py` besitzt bereits zwei unterschiedliche Pfade:

```text
decode_to_jpeg()
preview_to_jpeg()
```

`preview_to_jpeg()`:

- verwendet Pillow,
- führt `ImageOps.exif_transpose()` aus,
- normalisiert das Bild für JPEG,
- begrenzt die maximale Kantenlänge,
- verwendet LANCZOS-Resampling,
- erzeugt JPEG mit Quality 88,
- liefert einen strukturierten `ImageDecodeResult`.

Der maximale Preview-Rahmen ist intern auf höchstens 4096 begrenzt.

### Konsequenz

Die im technischen Konzept vorgesehene Orientierungskorrektur muss für lokale Bilder nicht erneut in JavaScript implementiert werden.

Für Backend-Previews gilt künftig möglichst:

```text
Datei
  ↓
ImageDecodeService.preview_to_jpeg()
  ↓
EXIF-orientiertes JPEG
  ↓
Browser
```

Damit können Bounding Boxes gegen bereits orientierte Bilder gerendert werden.

---

## 5. Decoder-Kette für Spezialformate

Der `ImageDecodeService` besitzt bereits eine konfigurierbare Decoder-Kette.

Standardmäßig werden u. a. berücksichtigt:

```text
pillow-heif
heif-convert
magick
ffmpeg
convert
```

Zusätzlich kann `libvips` bevorzugt werden.

Unterstützte Decoder-Erweiterungen enthalten standardmäßig u. a.:

```text
heic
heif
dng
cr2
cr3
nef
nrw
arw
orf
rw2
raf
pef
```

Wenn libvips aktiv ist, kann dessen Formatliste ergänzt werden.

### Konsequenz

Das Preview-Konzept sollte nicht selbst über RAW/HEIC-spezifische Decoder entscheiden. Das ist bereits Backend-Verantwortung.

Der `PreviewDescriptor` braucht höchstens Informationen wie:

```json
{
  "source_kind": "local_file",
  "path": "...",
  "prefer_preview": true
}
```

Die konkrete Decoderwahl bleibt vollständig im Backend.

---

## 6. RAW Embedded Preview

`src/handler/file_handler.py` enthält bereits:

```text
RAW_PREVIEW_EXTENSIONS
extractEmbeddedJpegPreview()
```

Damit existiert bereits ein Mechanismus zur Nutzung eingebetteter JPEG-Vorschauen in RAW-Dateien.

### Konsequenz

Für RAW-Dateien soll der vereinheitlichte Preview-Pfad vorhandene Mechanismen nutzen. Es darf kein separater RAW-Renderer in der UI entstehen.

Langfristiges Ziel:

```text
PreviewResolver
    ↓
/api/file_image?preview=1
    ↓
embedded preview / decoder / fallback
```

---

## 7. Browser-kompatible Formate werden bereits erkannt

In `ui/src/App.vue` existiert:

```js
isBrowserImageCompatiblePath(path)
```

Die aktuelle Liste umfasst mindestens:

```text
jpg
jpeg
png
gif
webp
bmp
svg
avif
```

`faceMatchMixin.js` nutzt diese Prüfung bereits, um zu entscheiden, ob ein Synology-/Thumbnail-Pfad direkt verwendet werden kann oder auf den Backend-Preview zurückgefallen wird.

### Konsequenz

Diese Entscheidung gehört in den geplanten `PreviewResolver`.

Die Views selbst sollen künftig nicht mehr entscheiden:

```text
Browser-kompatibel?
Photos-Thumbnail?
Backend-Fallback?
```

sondern nur noch:

```text
descriptor → resolver → url
```

---

## 8. Bestehende lokale Fallback-Logik im Face Match

`faceMatchMixin.js` besitzt bereits:

```text
getCurrentFaceMatchImageUrl()
getCurrentFaceMatchImageFallbackUrl()
handleFaceMatchImagePreviewError()
```

Die Logik berücksichtigt u. a.:

- direkte Photos-Thumbnails,
- lokalen `image_path`,
- nicht browserkompatible Formate,
- File-Source-Aktionen,
- Backend-Fallback.

Der Error-Handler verwendet `dataset.avFallbackApplied`, damit ein fehlgeschlagenes Bild nicht endlos zwischen Primary- und Fallback-URL wechselt.

### Konsequenz

Diese Logik ist ein sehr guter Ausgangspunkt für den geplanten Resolver.

Sie soll extrahiert statt neu erfunden werden.

Vorgeschlagene Migration:

```text
faceMatchMixin.getCurrentFaceMatchImageUrl()
faceMatchMixin.handleFaceMatchImagePreviewError()
        ↓
previewResolver.js
        ↓
MediaPreview.vue
```

---

## 9. Synology-Photos-Bild-Thumbnails

`faceMatchMixin.js` besitzt bereits:

```text
getFaceMatchThumbnailUrl(image)
```

Diese Funktion delegiert auf die bestehende Photos-Thumbnail-Funktion der Anwendung.

Damit existieren aktuell mindestens zwei Bildquellen:

```text
Synology Photos Thumbnail API
Backend /api/file_image
```

### Konsequenz

Der `PreviewDescriptor.source_kind` sollte diese beiden Quellen explizit unterscheiden:

```text
photos_image
local_file
```

Der Renderer soll davon nichts wissen.

---

## 10. Personen-Thumbnails sind bereits separat vorhanden

`faceMatchMixin.js` besitzt:

```text
getFaceMatchPersonThumbnailUrl(person)
getFaceMatchPersonPreviewUrl(person)
```

Dabei werden u. a. verwendet:

```text
person.additional.thumbnail
person.thumbnail
person.id
Synology Photos Thumbnail API
```

Als Fallback wird bereits ein lokales Unknown-Person-Icon verwendet.

Diese Personenvorschau wird bereits in mehreren Komponenten eingesetzt:

- `FaceMatchView.vue`
- `ChecksFacePane.vue`
- `RecognitionFindingsReview.vue`

### Konsequenz

Personenpreview ist bereits funktional wiederverwendet, aber noch nicht Teil eines allgemeinen Preview-Modells.

Der neue Descriptor sollte daher mindestens unterstützen:

```json
{
  "kind": "person",
  "source_kind": "photos_person",
  "entity_id": 123,
  "thumbnail": { ... },
  "fallback": "person_unknown"
}
```

---

## 11. Bounding-Box-Normalisierung existiert bereits im Backend

`src/services/bbox_normalizer.py` enthält bereits eine zentrale Normalisierung für unterschiedliche Koordinatenquellen.

Vorhandene Funktionen:

```text
from_photos()
from_xywh()
from_xmp()
to_xywh()
to_bbox_dict()
clamp_bbox()
scale_bbox_about_center()
normalize_xmp_face()
denormalize_xmp_face()
to_display_face()
```

Die Daten werden auf ein relatives Koordinatensystem normalisiert.

### Besonders wichtig

`to_display_face()` setzt:

```text
display_normalized = true
```

und erzeugt ein einheitliches:

```json
{
  "bbox": {
    "x1": ...,
    "y1": ...,
    "x2": ...,
    "y2": ...
  }
}
```

Für MWG-/Microsoft-XMP-Regionen wird vorher die Orientierung normalisiert.

### Konsequenz

Das Zielkonzept sollte die UI-Regel verschärfen:

> Neue Preview-Komponenten dürfen keine quellspezifische XMP-/Photos-/EXIF-Bounding-Box-Normalisierung mehr enthalten.

Die UI akzeptiert nur:

```text
display_bbox
```

oder ein bereits als

```text
display_normalized=true
```

markiertes Face-Modell.

---

## 12. `display_bbox` wird bereits im Recognition-Service erzeugt

`src/services/face_recognition_service.py` speichert bzw. liefert bereits Felder wie:

```text
bbox
display_bbox
image_orientation
profile_display_normalized
profile_image_orientation
```

Auch Medoid-/Referenzgesichter übernehmen diese Informationen.

Damit ist der gewünschte Backend-Vertrag für die Vereinheitlichung bereits teilweise Realität.

### Konsequenz

Für Recognition-Previews muss kein neuer Geometrievertrag erfunden werden.

Die Migration sollte zuerst genau dort beginnen, weil dort die saubersten Daten bereits vorliegen.

---

## 13. Tests für Orientierung existieren bereits

In `tests/unit/services/test_face_recognition_service.py` gibt es bereits einen Test für:

```text
orientation = 6
```

und die daraus resultierende `display_bbox`.

### Konsequenz

Dieser Test sollte als Basis für eine vollständige Orientierungs-Matrix erweitert werden:

```text
1
2
3
4
5
6
7
8
```

Die vereinheitlichte Preview-Komponente selbst muss dann nur noch prüfen, dass die gelieferten Display-Koordinaten korrekt in CSS umgesetzt werden.

---

## 14. Aktuelle UI rendert Bounding Boxes noch selbst

Im `faceMatchMixin.js` existieren weiterhin UI-Funktionen wie:

```text
getFaceMatchBBox()
getFaceMatchBoxStyle()
getFaceMatchMaskStyles()
getFaceMatchCropStyle()
```

`FaceMatchView.vue` verwendet diese direkt für:

- Bounding-Box-Rahmen,
- Masken,
- Face-Crop-Darstellung,
- Photo-/Face-Umschaltung.

### Konsequenz

Hier liegt einer der größten tatsächlichen Vereinheitlichungspunkte.

Diese Methoden sollen nicht unmittelbar gelöscht werden, sondern zunächst intern auf gemeinsame Utilities delegieren:

```text
previewGeometry.getBoxStyle()
previewGeometry.getMaskStyles()
previewGeometry.getCropTransform()
```

Danach können `MediaPreview.vue` bzw. `FacePreviewOverlay.vue` dieselbe Logik nutzen.

---

## 15. Preview-Modus `photo` / `face` existiert bereits

`faceMatchMixin.js` besitzt bereits:

```text
faceMatchPreviewMode = 'photo'
isFaceOnlyPreview
```

Damit ist die fachliche Unterscheidung zwischen Gesamtbild und Gesichtsausschnitt bereits etabliert.

### Konsequenz

Die geplanten neuen Modi sollten diese bestehende Semantik übernehmen.

Empfohlene Zuordnung:

| Bestand | Zielmodell |
|---|---|
| `photo` | `full` |
| `face` | `face` |

`context` und `thumbnail` können später ergänzt werden, ohne die bestehende Logik sofort zu verändern.

---

## 16. Bestehende Komponenten mit Preview-Darstellung

Aus dem Quellcode sind aktuell mindestens folgende Komponenten direkt betroffen:

| Komponente | Preview-Typ |
|---|---|
| `FaceMatchView.vue` | Bild, Face Crop, Bounding Box, Person |
| `ChecksFacePane.vue` | Bildvergleich, Gesicht, Personenvorschläge |
| `RecognitionFindingsReview.vue` | Recognition Finding, Personenvorschläge |
| `FaceFrameFindingsTable.vue` | Bild, Face Frame / Bounding Box |

Zusätzlich greifen Mixins direkt auf Preview-Helfer zu:

```text
faceMatchMixin.js
checksMixin.js
cleanupMixin.js
```

### Konsequenz

Diese Liste sollte die verbindliche Migrationsliste für Phase 1 und 2 bilden.

---

## 17. CSS ist ebenfalls zentralisierungsrelevant

`ui/src/styles/face-match.css` enthält heute u. a.:

```text
.face-match-preview
.face-match-thumbnail
.face-match-crop-frame
.face-match-crop-image
.face-match-mask
.face-match-person-preview
.face-match-person-preview-image
.face-match-suggest-thumb
```

### Konsequenz

Nicht nur Vue-Templates, sondern auch CSS-Klassen müssen in die Migration aufgenommen werden.

Empfohlene neue Schicht:

```text
preview.css
```

mit neutralen Klassen:

```text
.media-preview
.media-preview__image
.media-preview__overlay
.media-preview__bbox
.media-preview__mask
.media-preview__crop
.media-preview__fallback
```

Bestehende `face-match-*` Klassen können während der Migration als Aliase erhalten bleiben.

---

## 18. Backend-Fallback liefert bereits ein gültiges Bild

Der `/api/file_image`-Endpunkt liefert im Fehlerfall bereits ein SVG mit dem Text:

```text
Preview unavailable
```

Tests prüfen explizit:

```text
status_code == 200
media_type == image/svg+xml
```

### Konsequenz

Der UI-Renderer muss nicht jeden Decoderfehler zwingend als kaputtes `<img>` behandeln.

Es gibt zwei Fehlerklassen:

```text
1. Resolver-/Transportfehler → UI-Fallbackzustand
2. Backend kann Datei nicht dekodieren → gültiges Fallback-Bild vom Backend
```

Diese Unterscheidung sollte im zentralen Preview-Vertrag berücksichtigt werden.

---

## 19. Bereits vorhandene Preview-Tests

Es existieren bereits Tests für mehrere relevante Verhaltensweisen.

### Backend

`tests/unit/api/test_imgdata_api_orchestration.py`

prüft u. a.:

- Preview-Decodierung,
- JPEG-Ausgabe,
- Fallback auf SVG,
- Logging von `file_image_served`.

### UI statisch

`tests/unit/static/test_face_match_ui_stored_findings.py`

prüft u. a.:

- zentrale URL-Erzeugung,
- dass Mixins nicht eigene `/api/file_image`-Strings duplizieren,
- Browser-Kompatibilitätsprüfung,
- Error-Fallback.

### UI Runtime

`tests/unit/ui/test_face_match_mixin_runtime.py`

prüft u. a.:

- Resolver-artige URL-Auswahl,
- Fallback nach Image Error,
- Schutz gegen mehrfaches Fallback.

### Recognition

`tests/unit/services/test_face_recognition_service.py`

prüft bereits orientierungsabhängige Display-Bounding-Boxes.

### Konsequenz

Die Preview-Vereinheitlichung kann auf vorhandenen Regressionstests aufbauen. Neue Tests sollen bestehende Tests zuerst erweitern und erst später ersetzen.

---

# 20. Ist-Matrix

| Bereich | Bereits vorhanden | Vereinheitlichung nötig | Neu erforderlich |
|---|---:|---:|---:|
| lokale Preview-URL | ja | ja, in Resolver integrieren | nein |
| `/api/file_image` | ja | evtl. später | nein |
| Preview-JPEG-Decoding | ja | nein | nein |
| EXIF-Orientierung | ja | Backend als Standard festschreiben | nein |
| RAW/HEIC-Decoding | ja | nein | nein |
| eingebettetes RAW-JPEG | ja | anbinden/prüfen | nein |
| Browserformat-Erkennung | ja | in Resolver verschieben | nein |
| Photos-Bildthumbnail | ja | in Resolver verschieben | nein |
| Photos-Personthumbnail | ja | in Resolver verschieben | nein |
| Person-Fallback | ja | zentralisieren | nein |
| Image-error-Fallback | ja | zentralisieren | nein |
| Bounding-Box-Normalisierung | ja | konsequent Backend nutzen | nein |
| `display_bbox` | teilweise | Vertrag ausweiten | teilweise |
| Overlay CSS | mehrfach | ja | gemeinsame Klassen |
| Crop CSS/Logik | mehrfach | ja | gemeinsame Geometry Utility |
| Preview-Descriptor | nein | – | ja |
| PreviewResolver | teilweise implizit | ja | als eigenes Modul |
| MediaPreview-Komponente | nein | – | ja |
| Preview-Adapter | nein | – | ja |
| Renderer-Contract-Tests | teilweise | ja | ergänzen |

---

# 21. Empfohlener minimaler Zielvertrag auf Basis des Bestands

Der erste `PreviewDescriptor` muss nicht alle denkbaren Felder enthalten.

Für Phase 1 reicht ein bewusst kleiner Vertrag:

```ts
interface PreviewDescriptor {
    id?: string;

    kind:
        | 'image'
        | 'face'
        | 'person';

    sourceKind:
        | 'local_file'
        | 'photos_image'
        | 'photos_person'
        | 'direct_url';

    path?: string;
    url?: string;
    entityId?: number | string;
    thumbnail?: object;

    bbox?: {
        x1: number;
        y1: number;
        x2: number;
        y2: number;
    };

    displayNormalized?: boolean;

    mode?:
        | 'full'
        | 'face'
        | 'thumbnail';

    fallback?:
        | 'image_unavailable'
        | 'person_unknown';
}
```

Noch nicht erforderlich in Phase 1:

```text
cache revision
complex capability flags
server-side generated descriptor API
preview persistence
worker transport
```

Diese können später ergänzt werden.

---

# 22. Konkreter Resolver aus vorhandener Logik

Der erste Resolver kann fast vollständig aus bestehenden Methoden zusammengesetzt werden.

Pseudoablauf:

```text
resolvePreview(descriptor)

if sourceKind == photos_person
    → vorhandene Person Thumbnail URL
    → fallback person_unknown

if sourceKind == photos_image
    → vorhandene Photos Thumbnail URL
    → bei nicht browserkompatibler Quelle Backend Preview

if sourceKind == local_file
    → getBackendImagePreviewUrl(path)
    → vorzugsweise preview=1

if sourceKind == direct_url
    → URL direkt
```

Damit lässt sich Phase 1 ohne Änderung an der Backend-Datenstruktur umsetzen.

---

# 23. Noch zu prüfender Punkt: `preview=1` konsequent verwenden

Im Bestand existieren beide Formen:

```text
/api/file_image?path=...
/api/file_image?path=...&preview=1
```

Da `preview=1` explizit den Preview-Decoder mit:

- Auto-Orientation,
- Resize,
- JPEG-Normalisierung

aktiviert, sollte im Rahmen der Vereinheitlichung geprüft werden, ob UI-Previews grundsätzlich `preview=1` verwenden sollen.

Empfehlung:

```text
UI Preview → preview=1
Originaldatei-Auslieferung → ohne preview
```

Das sollte vor Migration von Bounding Boxes gegen alle relevanten Dateiformate getestet werden.

---

# 24. Noch zu prüfender Punkt: Bounding Box gegen orientiertes Backend-JPEG

Da `preview_to_jpeg()` EXIF-Transpose durchführt und `display_bbox` ebenfalls orientierungsnormalisiert erzeugt wird, ist das grundsätzlich das gewünschte Paar:

```text
orientiertes Preview-JPEG
+
orientierte display_bbox
```

Für die endgültige Freigabe sollte eine Testmatrix angelegt werden:

| EXIF | Bildausrichtung | erwartete Face-Position |
|---:|---|---|
| 1 | normal | unverändert |
| 2 | gespiegelt | horizontal gespiegelt |
| 3 | 180° | rotiert |
| 4 | vertikal gespiegelt | gespiegelt |
| 5 | transpose | Achsenwechsel |
| 6 | 90° CW | Achsenwechsel |
| 7 | transverse | Achsenwechsel |
| 8 | 90° CCW | Achsenwechsel |

Dieser Test ist wichtiger als weitere UI-Sonderbehandlung.

---

# 25. Empfohlene technische Abarbeitung nach der Bestandsaufnahme

## Schritt 1

Bestehende Helfer nicht ändern, sondern zentralen Resolver einführen:

```text
ui/src/services/previewResolver.js
```

Der Resolver ruft zunächst vorhandene Funktionen auf.

## Schritt 2

Geometry Utility extrahieren:

```text
ui/src/services/previewGeometry.js
```

Dort hinein:

```text
bbox → CSS box
bbox → mask styles
bbox → crop transform
```

## Schritt 3

`MediaPreview.vue` erstellen und nur in `RecognitionFindingsReview.vue` einsetzen.

Warum zuerst dort:

- Backend liefert bereits `display_bbox`,
- Recognition hat bereits normalisierte Orientierung,
- Risiko geringer als in `FaceMatchView.vue`.

## Schritt 4

`FaceFrameFindingsTable.vue` migrieren.

## Schritt 5

`ChecksFacePane.vue` migrieren.

## Schritt 6

`FaceMatchView.vue` zuletzt migrieren und alte Preview-Helfer intern auf Resolver/Geometry umbiegen.

## Schritt 7

Erst danach veraltete Methoden und `face-match-*` Preview-CSS entfernen.

---

# 26. Zusätzliche Tests für die Umsetzung

Neben den bereits vorhandenen Tests sollten folgende neue Tests entstehen.

## Resolver

```text
local_file → backend preview URL
photos_image → Photos URL
photos_image nicht browserfähig → backend fallback
photos_person → Photos Person Thumbnail
photos_person ohne Thumbnail → unknown-person fallback
empty descriptor → empty state
```

## Geometry

```text
bbox normal
bbox am Rand
bbox außerhalb 0..1 → clamp
sehr kleine bbox
face crop
mask styles
```

## Renderer

```text
loading
success
backend SVG fallback
broken primary URL
broken fallback URL
bbox overlay
face mode
full mode
person mode
```

## Integration

```text
Recognition Finding
Face Frame Finding
Checks Pair
Face Match
```

Jeder Integrationstest soll prüfen, dass dieselbe Descriptor-/Resolver-/Renderer-Schicht verwendet wird.

---

# 27. Fazit

Die Quellcodeanalyse reduziert den Umfang des notwendigen Neubaus deutlich.

Bereits vorhanden und wiederverwendbar sind:

```text
Backend Preview Endpoint
Image Decoder
EXIF Auto-Orientation
RAW/HEIC Decoder
Photos Thumbnail Zugriff
Person Thumbnail Zugriff
Browser-Kompatibilitätsprüfung
Fallback-Mechanismen
BBox-Normalisierung
Display-BBox
mehrere Regressionstests
```

Tatsächlich neu gebaut werden müssen primär:

```text
PreviewDescriptor
PreviewResolver als explizites Modul
PreviewGeometry als explizites Modul
MediaPreview.vue
Adapter aus bestehenden Finding-Strukturen
vereinheitlichte Preview-CSS-Klassen
```

Damit sollte die Umsetzung deutlich kleiner ausfallen als ein vollständiger Preview-Neuentwurf.