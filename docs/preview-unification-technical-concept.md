# Technisches Konzept: Vereinheitlichte Previews

## 1. Ziel

Die verschiedenen Bild-, Gesichts-, Personen- und Vergleichsvorschauen in ImgData sollen technisch vereinheitlicht werden, damit neue Review- und Analyseansichten nicht erneut eigene Preview-Logik implementieren müssen.

Das Ziel ist **nicht**, alle fachlichen Review-Abläufe in eine einzige Komponente zu pressen. Vereinheitlicht werden ausschließlich die technischen Aufgaben rund um eine Vorschau:

- Quelle eines Vorschaubildes bestimmen
- lokale Datei, Synology-Photos-Thumbnail oder Fallback auflösen
- Bildausschnitt bzw. Gesichtsausschnitt bestimmen
- Orientation berücksichtigen
- Bounding Box normalisieren und darstellen
- Lade-, Fehler- und Leerzustand behandeln
- Cache-/Reload-Verhalten vereinheitlichen
- Preview-Größen und Varianten festlegen
- Alt-Text und Labels bereitstellen
- Full-photo-, Face-only- und Person-Preview gleichartig modellieren

Das vorhandene Review-UI-Konzept bleibt fachlich übergeordnet. Dieses Dokument beschreibt die technische Preview-Schicht darunter.

---

## 2. Ausgangslage

Aktuell existieren mehrere teilweise unterschiedliche Preview-Pfade.

Betroffene Stellen sind insbesondere:

- `ui/src/components/ChecksFacePane.vue`
- `ui/src/components/cleanup/FaceFrameFindingsTable.vue`
- `ui/src/components/cleanup/RecognitionFindingsReview.vue`
- `ui/src/views/FaceMatchView.vue`
- `ui/src/mixins/faceMatchMixin.js`
- `ui/src/mixins/checksMixin.js`
- `ui/src/mixins/cleanupMixin.js`
- `ui/src/styles/face-match.css`
- `src/api/imgdata_api.py`
- `src/services/face_recognition_service.py`
- `src/handler/file_handler.py`

Bereits sichtbar sind unterschiedliche technische Quellen:

1. lokale Dateien über ImgData-API
2. Synology-Photos-Thumbnails über `/synofoto/api/v2/t/Thumbnail/get`
3. Personenbilder aus Photos
4. Gesichtsausschnitte aus lokalen Bildern
5. vollständige Bilder mit Bounding Box
6. RAW-Dateien mit eingebettetem Preview
7. Fallback-Icons bzw. Placeholder

Zusätzlich existieren Roh- und Anzeige-Koordinaten nebeneinander. In `face_recognition_service.py` werden bereits `bbox`, `display_bbox` und `image_orientation` unterschieden. Diese Trennung soll für alle Previews verbindlich werden.

---

## 3. Hauptproblem

Die aktuelle Struktur vermischt vier Verantwortlichkeiten:

```text
fachlicher Review-Zustand
        +
Preview-Daten ableiten
        +
Preview-URL bauen
        +
Bild darstellen
```

Dadurch entstehen in mehreren Views eigene Varianten von:

- `get...PreviewUrl(...)`
- `get...ImageUrl(...)`
- Thumbnail-Auflösung
- unbekannte Person → Fallback-Icon
- Bounding-Box-Umrechnung
- Preview-Modus `photo` / `face`
- CSS für Container und Thumbnail
- Error-Fallback

Das erschwert Änderungen und verursacht Unterschiede zwischen ansonsten fachlich ähnlichen Ansichten.

---

# 4. Zielarchitektur

Die Preview-Schicht wird in vier Ebenen aufgeteilt:

```text
Backend / Prozessstatus
        │
        ▼
Preview Descriptor
        │
        ▼
Preview Resolver
        │
        ▼
Preview Renderer
        │
        ▼
Review-/Check-Komponente
```

Dabei gilt:

- **Backend** liefert fachlich belastbare Quelldaten.
- **Preview Descriptor** beschreibt, was dargestellt werden soll.
- **Preview Resolver** bestimmt, wie daraus eine konkrete Bildquelle wird.
- **Preview Renderer** zeigt diese Quelle einheitlich an.
- **Review-Komponenten** entscheiden nur noch, welche Preview links/rechts/oben/unten angezeigt wird.

---

# 5. Zentrales Preview-Datenmodell

Jede Vorschau wird intern über einen `PreviewDescriptor` beschrieben.

Empfohlene Struktur:

```js
{
  id: 'face:4711',
  kind: 'face',

  source: {
    type: 'local-file',
    path: '/volume1/photo/example.jpg',
    imageId: 123,
    faceId: 4711,
    personId: null
  },

  display: {
    mode: 'photo',
    fit: 'contain',
    size: 'review',
    showBoundingBox: true
  },

  geometry: {
    bbox: {
      left: 0.21,
      top: 0.18,
      width: 0.16,
      height: 0.22,
      unit: 'relative'
    },
    orientation: 6,
    normalized: true
  },

  label: {
    title: 'Unbekanntes Gesicht',
    subtitle: 'Bild 123',
    alt: 'Vorschau des unbekannten Gesichts'
  },

  fallback: {
    kind: 'person-unknown'
  }
}
```

Dieses Objekt ist zunächst ein **UI-internes Modell**. Das Backend muss nicht sofort exakt dieselbe Struktur liefern.

---

# 6. `kind`

Vorgesehene Preview-Arten:

```text
image
face
person
comparison
metadata
placeholder
```

Bedeutung:

### `image`

Komplettes Foto oder Video-Standbild.

### `face`

Gesicht in einem Bild, optional mit Bounding Box oder Crop.

### `person`

Repräsentatives Personenbild, typischerweise Synology Photos Person Thumbnail.

### `comparison`

Kein eigenes Bildformat, sondern semantischer Hinweis für Paaransichten. Technisch bestehen Vergleiche aus zwei einzelnen Preview-Deskriptoren.

### `metadata`

Kein echtes Bild, sondern ein Preview-Slot mit Metadateninhalt. Relevant für Checks, die heute dieselbe linke/rechte Pane-Struktur verwenden.

### `placeholder`

Expliziter leerer oder nicht verfügbarer Zustand.

---

# 7. Quellenmodell

`source.type` wird verbindlich normalisiert.

Vorgesehene Werte:

```text
local-file
local-image-id
synology-thumbnail
synology-person
embedded-preview
remote-worker-asset
static-asset
none
```

## 7.1 `local-file`

```js
{
  type: 'local-file',
  path: '/volume1/photo/test.jpg'
}
```

Wird über den vorhandenen ImgData-Datei-/Preview-Endpunkt aufgelöst.

## 7.2 `local-image-id`

Bevorzugt, wenn eine stabile interne Bild-ID existiert.

```js
{
  type: 'local-image-id',
  imageId: 123
}
```

Vorteil: UI muss Pfade nicht kennen oder URL-encoden.

## 7.3 `synology-thumbnail`

Für Photos-Bilder.

```js
{
  type: 'synology-thumbnail',
  id: 123,
  cacheKey: '...'
}
```

Der Resolver kapselt Synology-spezifische URL-Parameter inklusive `SynoToken`.

## 7.4 `synology-person`

```js
{
  type: 'synology-person',
  personId: 42923,
  thumbnailId: 123
}
```

Dadurch verschwindet `getFaceMatchPersonPreviewUrl(...)` schrittweise aus fachlichen Mixins.

## 7.5 `embedded-preview`

Für RAW-Dateien oder andere Formate mit eingebettetem Preview.

Die Entscheidung, ob eine Originaldatei direkt lesbar ist oder ein eingebettetes Vorschaubild verwendet werden muss, bleibt im Backend bzw. zentralen Preview-Service.

## 7.6 `remote-worker-asset`

Nur für späteren Ausbau.

Externe Worker dürfen kein eigenes UI-URL-Schema erzeugen. Ein Worker-Ergebnis wird zunächst in einen NAS-seitig auflösbaren Preview-Descriptor überführt.

---

# 8. Preview-Modi

Die vorhandene Unterscheidung `photo` / `face` wird formalisiert.

```text
full
face
context
thumbnail
```

## `full`

Vollständiges Bild ohne automatischen Crop.

## `face`

Nur Gesichtsausschnitt.

Der Crop soll vorzugsweise **serverseitig** erfolgen, wenn dadurch RAW-, Orientation- und Formatbehandlung vereinheitlicht werden kann.

## `context`

Bild mit Gesicht und zusätzlichem Rand.

Beispiel:

```text
bbox + 50 % Rand
```

Dieser Modus ist für Review-Zwecke häufig besser als ein enger Face-Crop.

## `thumbnail`

Kleine Variante für Vorschlagslisten und Personenauswahl.

---

# 9. Größenklassen

Keine View soll eigene Pixelgrößen an Backend-Endpunkte übergeben.

Stattdessen werden semantische Größen verwendet:

```text
xs
sm
md
review
large
```

Beispielhafte Zuordnung:

| Größe | Verwendung |
|---|---|
| `xs` | kleine Listenicons |
| `sm` | Personen-Vorschlagsliste |
| `md` | Tabellen / kompakte Findings |
| `review` | linke/rechte Hauptvorschau |
| `large` | vergrößerte Einzelansicht |

Die konkrete Pixeldefinition liegt zentral.

Beispiel:

```js
const PREVIEW_SIZES = {
  xs: 48,
  sm: 80,
  md: 160,
  review: 512,
  large: 1024
};
```

Diese Werte sind Implementierungsdetails und können später geändert werden, ohne alle Views anzufassen.

---

# 10. Bounding-Box-Vertrag

Bounding Boxes werden intern ausschließlich in **display-normalisierten relativen Koordinaten** dargestellt.

Verbindliches Format:

```js
{
  left: 0.21,
  top: 0.18,
  width: 0.16,
  height: 0.22,
  unit: 'relative',
  coordinateSpace: 'display'
}
```

Zulässiger Bereich:

```text
0.0 <= left <= 1.0
0.0 <= top <= 1.0
0.0 <= width <= 1.0
0.0 <= height <= 1.0
```

Es darf im Renderer keine EXIF-Orientation-Umrechnung mehr stattfinden.

Das Backend bzw. ein zentraler Normalizer liefert bereits display-kompatible Koordinaten.

Das vorhandene Muster aus `face_recognition_service.py` mit:

```text
bbox
image_orientation
display_bbox
```

wird zum Standard.

---

# 11. Rohkoordinaten bleiben erhalten

Für fachliche Verarbeitung dürfen Rohkoordinaten weiterhin existieren.

Beispiel:

```json
{
  "bbox": {...},
  "display_bbox": {...},
  "image_orientation": 6
}
```

Regel:

```text
Analyse / Speicherung -> bbox
UI / Preview          -> display_bbox
```

Die UI darf nicht selbst entscheiden, wann `bbox` rotiert oder gespiegelt werden muss.

---

# 12. Backend Preview Service

Langfristig soll die Backend-Erzeugung in einen eigenen Service gekapselt werden.

Vorgeschlagen:

```text
src/services/preview_service.py
```

Aufgaben:

- Bildquelle prüfen
- MIME-Type bestimmen
- RAW-/Embedded-Preview auflösen
- Orientation anwenden
- optional Crop erzeugen
- Skalierung durchführen
- Placeholder erzeugen
- HTTP-Cache-Metadaten bestimmen
- Fehler in definierte Preview-Fehler übersetzen

Nicht Aufgabe:

- Personenmatching
- Review-Entscheidungen
- Analysezustand
- Prozesssteuerung

---

# 13. Zentraler Preview-Endpunkt

Mittelfristiges Ziel:

```text
GET /api/preview
```

Beispielparameter:

```text
source=image
image_id=123
mode=context
size=review
face_id=4711
```

oder:

```text
GET /api/preview/image/123?mode=full&size=review
GET /api/preview/face/4711?mode=context&size=review
```

Die konkrete REST-Form ist zweitrangig. Wichtig ist ein zentraler Vertrag.

---

# 14. Kein universeller Proxy für Synology Photos nötig

Synology-Photos-Thumbnails können zunächst weiterhin direkt vom Browser geladen werden.

Daher unterstützt der Frontend-Resolver zwei Klassen:

```text
backend preview URL
synology native thumbnail URL
```

Eine Proxy-Lösung über ImgData ist nur dann sinnvoll, wenn später erforderlich:

- einheitliches Caching
- Zugriffskontrolle
- Crop
- Formatkonvertierung
- Offline-/Worker-Verarbeitung

Diese Entscheidung muss für die erste Vereinheitlichung nicht getroffen werden.

---

# 15. Frontend Preview Resolver

Neue zentrale Datei:

```text
ui/src/services/previewResolver.js
```

oder bei bestehender Projektstruktur:

```text
ui/src/utils/preview.js
```

Empfohlen wird ein Service, da URL-Auflösung mehr als reine Formatierung ist.

API:

```js
resolvePreview(descriptor, context)
```

Rückgabe:

```js
{
  src: '/api/preview/...',
  fallbackSrc: '/.../person_unknown.png',
  alt: '...',
  kind: 'image',
  mode: 'context',
  bbox: {...},
  cacheKey: '...',
  loading: 'lazy'
}
```

---

# 16. Resolver darf keine Fachlogik enthalten

Nicht erlaubt:

```js
if (action === 'recognition_analyze_unknown_faces') {
   ...
}
```

Erlaubt:

```js
if (descriptor.source.type === 'synology-person') {
   ...
}
```

Damit bleibt der Resolver wiederverwendbar.

---

# 17. Preview Factory / Adapter

Bestehende Backend-Antworten werden zunächst über kleine Factories in Deskriptoren übersetzt.

Beispiel:

```text
ui/src/adapters/preview/
    faceMatchPreviewAdapter.js
    checksPreviewAdapter.js
    recognitionPreviewAdapter.js
    faceFramePreviewAdapter.js
```

Beispiel:

```js
function fromRecognitionFinding(finding) {
  return {
    id: `face:${finding.face_id}`,
    kind: 'face',
    source: {
      type: finding.image_id ? 'local-image-id' : 'local-file',
      imageId: finding.image_id,
      path: finding.image_path,
      faceId: finding.face_id
    },
    display: {
      mode: 'context',
      size: 'review',
      showBoundingBox: true
    },
    geometry: {
      bbox: finding.display_bbox || null,
      orientation: finding.image_orientation || null,
      normalized: !!finding.display_bbox
    }
  };
}
```

Diese Adapter sind temporäre Migrationsbausteine und können verschwinden, sobald Backend-Antworten direkt normalisierte Preview-Felder liefern.

---

# 18. Gemeinsame Vue-Komponenten

## 18.1 `MediaPreview.vue`

Basiskomponente für ein einzelnes Medium.

Verantwortung:

- `<img>` rendern
- Ladezustand
- Fehlerzustand
- Fallback
- Aspect Ratio
- `object-fit`
- Bounding-Box-Overlay
- optional Toolbar-Slot

Props:

```js
preview
interactive
showLabel
showBoundingBox
```

Keine fachlichen Props wie:

```text
person
finding
action
reviewType
```

---

## 18.2 `PreviewPane.vue`

Rahmen um eine Preview.

Enthält:

- Titel
- Untertitel
- Preview
- Metainformationen
- Empty State
- optionale Aktionen als Slot

Damit kann `ChecksFacePane.vue` später auf einen deutlich kleineren fachlichen Wrapper reduziert werden.

---

## 18.3 `PreviewPair.vue`

Zwei Preview-Panes nebeneinander.

Props:

```js
left
right
layout
```

Keinerlei Matching- oder Review-Logik.

Geeignet für:

- Duplicate Face Checks
- Photo ↔ Metadata Face
- Face ↔ Person
- Source ↔ Target

---

## 18.4 `PersonPreview.vue`

Optionaler schlanker Wrapper um `MediaPreview`.

Nur falls Personen-UI wiederkehrende Zusatzinformationen benötigt:

- Name
- Person-ID
- Gruppenzugehörigkeit

Die Bildauflösung bleibt trotzdem im normalen Preview-Resolver.

---

# 19. Einheitlicher UI-Zustand

`MediaPreview.vue` besitzt genau definierte Zustände:

```text
idle
loading
ready
error
empty
```

Darstellung:

### `loading`

Skeleton oder neutraler Ladeplatzhalter.

### `error`

Fallback-Asset plus optional kleiner Fehlerhinweis.

### `empty`

Kein Bild vorhanden, aber kein technischer Fehler.

Beispiel:

```text
Person besitzt kein Vorschaubild
```

Diese Unterscheidung verhindert, dass fehlende Bilder als Netzwerkfehler erscheinen.

---

# 20. Fallback-Modell

Fallbacks werden nicht mehr direkt in Views gewählt.

Zentrale Typen:

```text
person-unknown
image-unavailable
face-unavailable
loading
broken
```

Resolver:

```js
resolveFallback('person-unknown')
```

Dadurch kann das Icon-Design später zentral geändert werden.

---

# 21. Fehlerbehandlung

Der Browser darf bei Bildfehlern nicht in URL-Schleifen geraten.

Regel:

```text
Originalquelle
   ↓ Fehler
Fallbackquelle
   ↓ Fehler
statischer Empty State
```

Maximal ein Fallback-Wechsel.

Ein `@error`-Handler darf nicht dieselbe URL erneut setzen.

---

# 22. Cache-Konzept

Previews sind potenziell teuer, insbesondere:

- RAW-Vorschauen
- Face-Crops
- große Bilder
- Remote-/Worker-Ergebnisse

Deshalb wird Cachefähigkeit Teil des Preview-Vertrags.

Empfohlene Cache-Identität:

```text
source identity
+
source modification marker
+
mode
+
size
+
bbox/crop version
```

Beispiel:

```text
image:123:mtime=1725100000:mode=context:size=review:face=4711
```

Backend kann daraus ETag oder Cache-Key bilden.

---

# 23. Cache Busting nach Mutation

Nach fachlichen Mutationen soll die UI nicht pauschal `?timestamp=...` anhängen.

Besser:

```text
preview_revision
```

oder vorhandener Änderungsmarker.

Beispiel:

```js
{
  imageId: 123,
  revision: 7
}
```

URL:

```text
/api/preview/image/123?...&rev=7
```

Revision wird nur erhöht, wenn sich das Preview-relevante Asset geändert hat.

---

# 24. Performance-Regeln

## Listen

- `loading="lazy"`
- `sm` oder `md`
- kein großes `review`-Bild
- keine Full-Resolution-Datei

## aktiver Review-Fund

- Preview sofort laden
- optional nächsten Fund vorladen

## Vorschlagslisten

- maximal `sm`
- Synology-Thumbnail direkt nutzen

## Fullscreen

- `large` erst bei expliziter Benutzeraktion laden

---

# 25. Prefetch

Optional nach erster Stabilisierung:

```text
aktueller Fund N
      ↓
N+1 Preview im Hintergrund vorladen
```

Nicht mehr als ein oder zwei Einträge im Voraus.

Kein Preload großer Bilder in langen Findings-Listen.

---

# 26. Security

Die Vereinheitlichung darf keine neuen beliebigen Dateizugriffe ermöglichen.

Backend-Endpunkte dürfen nicht akzeptieren:

```text
path=/etc/passwd
```

nur weil das Frontend einen generischen Preview-Service besitzt.

Bevorzugt:

```text
image_id
face_id
asset_id
```

Falls Pfade übergeben werden müssen, gelten weiterhin vorhandene Allowed-Path- und Shared-Path-Regeln.

---

# 27. API-Zielvertrag für Review-Antworten

Langfristig können Review-Antworten direkt Preview-Deskriptoren enthalten.

Beispiel:

```json
{
  "review": {
    "source": {
      "kind": "unknown_face",
      "preview": {
        "kind": "face",
        "source": {
          "type": "local-image-id",
          "image_id": 123,
          "face_id": 4711
        },
        "mode": "context",
        "display_bbox": {
          "left": 0.21,
          "top": 0.18,
          "width": 0.16,
          "height": 0.22
        }
      }
    }
  }
}
```

Damit muss die UI nicht mehr aus zehn Prozessfeldern rekonstruieren, welches Bild gemeint ist.

---

# 28. Übergangsvertrag

Für die erste Umsetzung reicht ein Frontend-Adapter.

```text
bestehende API
     ↓
Preview Adapter
     ↓
PreviewDescriptor
     ↓
MediaPreview
```

Backend-Umbauten sind für die erste UI-Vereinheitlichung nicht zwingend erforderlich.

Das reduziert Risiko und macht die Arbeit schneller.

---

# 29. Konkrete Migrationsmatrix

| Bestand | Ziel |
|---|---|
| `getFaceMatchPersonPreviewUrl()` | `previewResolver.resolvePreview()` |
| direkte `/synofoto/...Thumbnail/get`-Erzeugung | Synology-Resolver |
| `faceMatchPreviewMode` | `descriptor.display.mode` |
| lokale `<img>`-Fehlerbehandlung | `MediaPreview.vue` |
| `face-match-preview` CSS | zentrale Preview-CSS |
| `face-match-thumbnail` | `MediaPreview size=md/review` |
| eigene Bounding-Box-Overlays | `MediaPreview` Overlay |
| `bbox` + UI-Orientation-Logik | `display_bbox` |
| Person-Fallback direkt in Mixin | zentraler Fallback Resolver |
| RAW-Sonderbehandlung in UI | Backend Preview Service |

---

# 30. Reihenfolge der technischen Umsetzung

## Phase 0 – Tests vor Umbau

Zuerst bestehendes Verhalten festschreiben:

- FaceMatch Person Preview
- FaceMatch Photo Preview
- Recognition Finding
- Face Frame Finding
- Checks Duplicate Pair
- unbekannte Person
- nicht vorhandenes Bild
- Orientation 1/3/6/8
- Bounding Box

Noch keine Architekturänderung.

---

## Phase 1 – Datenmodell und Resolver

Neue Dateien:

```text
ui/src/services/previewResolver.js
ui/src/adapters/preview/
ui/src/constants/preview.js
```

Noch keine zentrale Vue-Komponente zwingend erforderlich.

Bestehende Views können zunächst nur ihre `src` über den Resolver beziehen.

Vorteil: sehr kleiner erster Schritt.

---

## Phase 2 – `MediaPreview.vue`

Neue Komponente:

```text
ui/src/components/common/MediaPreview.vue
```

Zunächst implementieren:

- Bild
- loading
- fallback
- error
- Bounding Box
- Größenklassen

Noch keine `PreviewPair`-Abstraktion.

---

## Phase 3 – RecognitionFindingsReview

Erster produktiver Migrationskandidat.

Gründe:

- bereits relativ isoliert
- nutzt Personensuggestions
- benötigt Face Preview
- benötigt Person Preview
- gute Testbarkeit

Ziel:

```text
RecognitionFinding
    ↓ Adapter
PreviewDescriptor
    ↓
MediaPreview
```

---

## Phase 4 – FaceFrameFindingsTable

Danach:

- Thumbnail
- Bounding Box
- aktiver Fund
- ggf. Kontextpreview

Hier lässt sich die Bounding-Box-Vereinheitlichung besonders gut absichern.

---

## Phase 5 – ChecksFacePane

`ChecksFacePane.vue` wird auf Preview-Darstellung reduziert oder intern auf `PreviewPane` / `PreviewPair` umgebaut.

Check-spezifische Labels bleiben außerhalb des Renderers.

---

## Phase 6 – FaceMatchView

Erst zuletzt.

Hier wird entfernt:

- direkte Person-Preview-Auflösung
- lokale Fallbacklogik
- doppelte Preview-CSS
- soweit möglich View-spezifische Bild-URL-Erzeugung

`faceMatchMixin.js` behält fachlichen Zustand, aber keine allgemeine Medienauflösung.

---

## Phase 7 – Backend Preview Service

Erst wenn die Frontend-Abstraktion stabil ist:

- vorhandene File-Image-Endpunkte inventarisieren
- gemeinsamen Preview-Service extrahieren
- RAW-/Orientation-/Crop-Logik zentralisieren
- API-Endpunkte auf Service umstellen

Dadurch werden UI- und Backend-Refactoring entkoppelt.

---

# 31. Nicht gleichzeitig ändern

Zur Risikoreduktion sollen folgende Änderungen **nicht** im selben Schritt erfolgen:

- Preview-Vereinheitlichung + Review-Status-Vertrag komplett umbauen
- Preview-Vereinheitlichung + External-Worker-Protokoll ändern
- Preview-Vereinheitlichung + Datenbankschema ändern
- Preview-Vereinheitlichung + alle Views gleichzeitig migrieren

Jede Preview-Migration soll UI-seitig möglichst verhaltensneutral sein.

---

# 32. Testarchitektur

Die Tests werden in vier Ebenen geteilt.

```text
Descriptor Tests
Resolver Tests
Component Tests
Integration / Contract Tests
```

---

# 33. Descriptor-Tests

Adaptertests prüfen ausschließlich die Normalisierung.

Beispiele:

### Recognition Finding

Input:

```json
{
  "face_id": 4711,
  "image_id": 123,
  "display_bbox": {
    "left": 0.2,
    "top": 0.1,
    "width": 0.3,
    "height": 0.4
  }
}
```

Erwartung:

```text
kind = face
source.type = local-image-id
source.faceId = 4711
display.mode = context
geometry.bbox = display_bbox
```

---

# 34. Resolver-Tests

Pflichtfälle:

- local image ID
- local path
- Synology thumbnail
- Synology person
- missing person image
- static fallback
- invalid descriptor
- unsupported source type
- Cache Revision

Keine Vue-Komponente nötig.

---

# 35. Geometry-Tests

Besonders wichtig.

Matrix:

| Orientation | Raw BBox | Display BBox vorhanden | Erwartung |
|---|---|---|---|
| 1 | ja | ja | Display BBox unverändert |
| 3 | ja | ja | Display BBox unverändert |
| 6 | ja | ja | Display BBox unverändert |
| 8 | ja | ja | Display BBox unverändert |
| 6 | ja | nein | Adapter markiert nicht normalisiert / kein Overlay |

Die UI darf bei fehlendem `display_bbox` nicht stillschweigend eine möglicherweise falsche Box anzeigen.

Optional kann während Migration ein zentraler Legacy-Normalizer existieren. Dieser muss jedoch separat getestet und später entfernt werden.

---

# 36. Component-Tests

`MediaPreview.vue`:

- zeigt Bild
- zeigt Loading State
- wechselt einmal auf Fallback
- zeigt Empty State
- rendert BBox korrekt
- BBox wird an Containergröße angepasst
- `showBoundingBox=false`
- `fit=contain`
- `fit=cover`
- Alt-Text gesetzt

---

# 37. Visuelle Regressionen

Für Preview-Komponenten sind Screenshots sinnvoll.

Mindestens:

```text
full image
face context
face crop
person thumbnail
missing image
loading
bbox landscape
bbox portrait
```

Wenn im Projekt keine Browser-Screenshot-Tests verwendet werden, kann zunächst mit DOM-/Style-Vertragsprüfungen gearbeitet werden.

---

# 38. API-Contract-Tests

Backendtests prüfen:

- Preview-Endpunkt liefert gültigen MIME-Type
- nicht vorhandene Quelle → definierter Status
- ungültiger Pfad → abgewiesen
- RAW-Datei → Preview oder definierter Fallback
- Orientation wird korrekt verarbeitet
- Face Crop bleibt innerhalb des Bildes
- extreme Bounding Box wird geclamped
- Cache Header / ETag konsistent

---

# 39. Status-Matrix-Erweiterung

Die vorhandene Review-Status-Matrix sollte Preview-Eigenschaften explizit prüfen.

Für jeden relevanten Review-Fall mindestens:

```text
preview kind
preview source identity
preview mode
preview display_bbox
preview fallback capability
```

Ziel ist nicht, URLs exakt festzuschreiben, sondern die semantische Preview-Beschreibung.

---

# 40. Testmatrix pro Prozess

| Prozess | Bild | Face Crop | BBox | Person Thumbnail | Fallback |
|---|---:|---:|---:|---:|---:|
| Face Match | ✓ | ✓ | ✓ | ✓ | ✓ |
| Recognition Findings | ✓ | ✓ | ✓ | ✓ | ✓ |
| Checks | ✓ | ✓ | ✓ | ✓ | ✓ |
| Face Frame | ✓ | optional | ✓ | – | ✓ |
| Unknown Faces | ✓ | ✓ | ✓ | ✓ | ✓ |

---

# 41. Akzeptanzkriterien Phase 1–3

Die erste Vereinheitlichung gilt als erfolgreich, wenn:

1. ein zentraler Preview Descriptor existiert.
2. Synology-Personen- und lokale Bildquellen über denselben Resolver laufen.
3. mindestens `RecognitionFindingsReview.vue` vollständig `MediaPreview.vue` verwendet.
4. Fallback und Loading nicht mehr lokal implementiert werden.
5. Bounding Boxes ausschließlich als Display-Koordinaten an den Renderer gelangen.
6. bestehendes Verhalten unverändert bleibt.
7. Resolver und Component Tests existieren.

---

# 42. Akzeptanzkriterien Endzustand

- Kein Review-View baut selbst Synology-Thumbnail-URLs.
- Kein Review-View enthält eigene generische `<img @error>`-Fallbacklogik.
- Keine View berechnet EXIF-Orientation für Bounding Boxes.
- `faceMatchMixin.js`, `checksMixin.js` und `cleanupMixin.js` enthalten keine generische Preview-Infrastruktur mehr.
- Preview-CSS ist zentralisiert.
- Person-, Bild- und Face-Preview verwenden dieselben Basiskomponenten.
- RAW-Sonderfälle werden im Backend behandelt.
- neue Review-Ansichten benötigen für eine Standardpreview nur einen Descriptor.

Beispiel:

```vue
<MediaPreview :preview="sourcePreview" />
```

statt eigener URL-, Fehler-, BBox- und Fallbacklogik.

---

# 43. Empfohlene Zielstruktur

```text
ui/src/
├── components/
│   └── common/
│       ├── MediaPreview.vue
│       ├── PreviewPane.vue
│       └── PreviewPair.vue
│
├── services/
│   └── previewResolver.js
│
├── adapters/
│   └── preview/
│       ├── faceMatchPreviewAdapter.js
│       ├── checksPreviewAdapter.js
│       ├── recognitionPreviewAdapter.js
│       └── faceFramePreviewAdapter.js
│
└── constants/
    └── preview.js

src/
└── services/
    └── preview_service.py
```

Der Backend-Service kann später ergänzt werden; die Frontend-Struktur kann vorher bereits eingeführt werden.

---

# 44. Technische Arbeitsreihenfolge für schnelle Umsetzung

Empfohlene konkrete Reihenfolge:

```text
1. Preview-Inventar-Test schreiben
2. preview.js Konstanten
3. previewResolver.js
4. Recognition Preview Adapter
5. MediaPreview.vue
6. RecognitionFindingsReview migrieren
7. Tests stabilisieren
8. FaceFrame Adapter + Migration
9. Checks Adapter + Migration
10. PreviewPair extrahieren
11. FaceMatchView migrieren
12. alte Preview-Helfer entfernen
13. CSS bereinigen
14. Backend preview_service.py extrahieren
15. API-Contract vereinheitlichen
```

Damit entsteht früh nutzbarer gemeinsamer Code, ohne dass vorab ein großer Backend-Umbau erforderlich ist.

---

# 45. Bewusste Designentscheidung

Die wichtigste Entscheidung lautet:

> **Nicht die URL wird vereinheitlicht, sondern die Bedeutung einer Preview.**

Ein lokales Foto, ein Synology-Personenbild und ein RAW-Embedded-Preview dürfen technisch weiterhin unterschiedliche Quellen besitzen.

Für die restliche Anwendung sehen sie jedoch gleich aus:

```text
PreviewDescriptor
      ↓
PreviewResolver
      ↓
MediaPreview
```

Dadurch bleibt die Architektur flexibel, während der technische Abarbeitungsaufwand für neue und bestehende Ansichten deutlich sinkt.
