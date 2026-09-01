# Preview-Vereinheitlichung: Referenzbasis der etablierten Funktionen

## Zweck

Dieses Dokument ergänzt `preview-unification-technical-concept.md` und `preview-unification-source-inventory.md` um einen verbindlichen Migrationsgrundsatz:

> Die älteren, über längere Zeit praktisch erprobten Preview-Flows gelten als technische Referenzimplementierung. Die Vereinheitlichung soll deren bewährtes Verhalten erhalten und abstrahieren, nicht durch eine theoretisch neu entworfene Preview-Logik ersetzen.

Insbesondere Funktionen wie **„unbekanntes Gesicht in Datei suchen“** sowie die verwandten klassischen Face-Match-Flows sind als höher gereift einzustufen als neuere Recognition-/Findings-Previews.

---

## 1. Konsequenz für die Zielarchitektur

Die Zielarchitektur bleibt grundsätzlich bestehen:

```text
fachlicher Prozess
    -> Preview Adapter
    -> PreviewDescriptor
    -> PreviewResolver
    -> MediaPreview
```

Die Semantik dieser Schichten wird jedoch nicht frei neu definiert. Sie wird zunächst aus dem Verhalten der etablierten Face-Match-Previews extrahiert.

Damit gilt:

```text
etablierter Preview-Flow
        |
        v
Verhalten inventarisieren
        |
        v
Contract-/Regressionstests
        |
        v
allgemeinen Preview-Vertrag ableiten
        |
        v
neue Preview-Komponenten implementieren
        |
        v
neuere Funktionen angleichen
```

Nicht:

```text
neuen generischen Preview-Vertrag entwerfen
        |
        v
ältere erprobte Funktionen darauf umbauen
```

---

## 2. Referenzkandidaten

Als primäre Referenz gelten insbesondere die Preview-Pfade rund um:

- „unbekanntes Gesicht in Datei suchen“
- `search_photo_face_in_file`
- `search_file_face_in_sources`
- verwandte klassische Face-Match-Aktionen
- bestehende Vollbild-/Face-only-Umschaltung
- bestehende lokale Datei- und Photos-Thumbnail-Fallbacks
- bestehende Personen-Thumbnail-Auflösung

Die konkrete Priorität wird anhand von Codealter, vorhandenen Tests und praktischer Nutzung festgelegt.

---

## 3. Was aus der Referenz übernommen werden soll

### 3.1 Quellenpriorität

Die etablierte Entscheidungskette für Bildquellen wird dokumentiert und zentralisiert, z. B.:

1. geeignete Synology-Photos-Thumbnail-Quelle, sofern vorhanden
2. direkte browserfähige Bildquelle, sofern zuverlässig
3. Backend-Preview über `/api/file_image`
4. Backend-Decoding/Normalisierung bei nicht browserfähigen Formaten
5. definierter Fallback

Die genaue Reihenfolge wird aus den bestehenden Methoden und Regressionstests übernommen und nicht ohne konkreten Grund verändert.

### 3.2 Browser-Kompatibilität

Die bestehende Erkennung browserfähiger Bildformate bleibt zunächst Referenz. Die zentrale Implementierung darf später erweitert werden, soll aber keine bisher funktionierenden Formate verlieren.

### 3.3 Fehler-Fallback

Das bestehende Verhalten von `handleFaceMatchImagePreviewError(...)` gilt als Referenz:

- primäre Quelle darf fehlschlagen
- genau ein kontrollierter Fallback wird angewendet
- Fallback-Schleifen werden verhindert
- ein bereits angewendeter Fallback wird markiert

Dieses Verhalten soll in `MediaPreview` übernommen und anschließend aus den alten Views entfernt werden.

### 3.4 Preview-Modi

Die vorhandene Umschaltung zwischen vollständigem Foto und Face-only-Darstellung gilt als Referenz für die Semantik der späteren standardisierten Modi.

Die neuen Begriffe `full`, `face`, `context` und `thumbnail` dürfen das bestehende Verhalten präzisieren, aber nicht unbeabsichtigt verändern.

### 3.5 Bounding Box und Crop

Die bestehenden Face-Match-Funktionen für:

- `getFaceMatchBBox(...)`
- Box-Styles
- Masken
- Crop-Styles

werden vor einer Ablösung vollständig als Verhalten erfasst.

Der zentrale Renderer muss danach mindestens dieselben Fälle korrekt darstellen können.

### 3.6 Personen-Previews

Die bestehende `getFaceMatchPersonThumbnailUrl(...)`-/`getFaceMatchPersonPreviewUrl(...)`-Logik wird als Referenz für `synology-person` verwendet.

Insbesondere werden übernommen:

- vorhandene Thumbnail-Metadaten
- Synology-Thumbnail-Endpunkt
- Token-/Request-Kontext
- unbekannte Person als definierter Fallback

---

## 4. Reifegradmodell

Für die Migration wird jeder Preview-Flow einem Reifegrad zugeordnet.

| Reifegrad | Bedeutung | Behandlung |
|---|---|---|
| A – etabliert | lange praktisch genutzt, bekannte Sonderfälle, Tests vorhanden | Referenz; Verhalten einfrieren |
| B – stabil | regelmäßig genutzt, aber weniger Historie | gegen A vergleichen |
| C – neu | neue Recognition-/Findings-Funktion | an A/B angleichen |
| D – experimentell | neue oder optionale Preview-Art | erst nach Kernmigration vereinheitlichen |

Für die erste Bestandsaufnahme gelten klassische Face-Match-Previews grundsätzlich als **A**, sofern keine konkrete Gegenindikation vorliegt.

Neuere Recognition-/Findings-Previews werden zunächst als **C** betrachtet.

---

## 5. Referenzmatrix

Vor Implementierung von `MediaPreview` soll eine Matrix aufgebaut werden:

| Verhalten | etablierter Face Match | Checks | Recognition | Face Frame | Ziel |
|---|---:|---:|---:|---:|---|
| lokale JPEG-Vorschau | Referenz | prüfen | prüfen | prüfen | Referenz übernehmen |
| HEIC/RAW | Referenz/Backend-Fallback | prüfen | prüfen | prüfen | identisch |
| Photos Thumbnail | Referenz | prüfen | ggf. | ggf. | Resolver |
| Person Thumbnail | Referenz | vorhanden | vorhanden | n/a | Resolver |
| Face-only | Referenz | teilweise | teilweise | teilweise | MediaPreview |
| Vollbild | Referenz | vorhanden | vorhanden | vorhanden | MediaPreview |
| Bounding Box | Referenz | vorhanden | vorhanden | vorhanden | gemeinsame Geometry |
| Orientierung | Referenz + Backend-Normalisierung | prüfen | vorhanden | prüfen | Backend/display_bbox |
| Fehler-Fallback | Referenz | uneinheitlich | uneinheitlich | uneinheitlich | MediaPreview |
| Placeholder | vorhanden | prüfen | prüfen | prüfen | zentral |

Die Matrix wird durch Codeanalyse und Tests konkretisiert.

---

## 6. Golden-Master-/Contract-Tests

Die etablierten Funktionen sollen vor der Migration zusätzliche Regressionstests erhalten.

### Pflichtfälle

1. browserfähiges JPEG
2. Dateiname mit Leerzeichen und Sonderzeichen
3. nicht browserfähiges HEIC/RAW
4. Backend-Preview mit `preview=1`
5. primäre Thumbnail-Quelle erfolgreich
6. primäre Thumbnail-Quelle fehlerhaft -> Backend-Fallback
7. Fallback ebenfalls fehlerhaft -> stabiler Fehlerzustand
8. Person mit Thumbnail
9. Person ohne Thumbnail
10. Full-photo-Modus
11. Face-only-Modus
12. Bounding Box am Bildrand
13. sehr kleine Bounding Box
14. EXIF Orientation 1–8
15. gespeicherter Finding-Eintrag mit nur `image_path`
16. Photos-Quelle mit Thumbnail-Metadaten

### Ziel

Vor der ersten visuellen Migration gilt:

```text
Legacy Preview -> Testvektor -> erwartete Quelle/Geometrie/Fallback
```

Nach der Migration:

```text
MediaPreview -> derselbe Testvektor -> dasselbe erwartete Verhalten
```

Nur bewusst beschlossene Änderungen dürfen vom Golden Master abweichen.

---

## 7. Migration in umgekehrter Reihenfolge

Die bisher vorgesehene Reihenfolge wird angepasst.

### Phase 0 – Referenz sichern

- klassische Face-Match-Preview-Flows inventarisieren
- Verhalten dokumentieren
- fehlende Regressionstests ergänzen
- Sonderfälle und Fallback-Reihenfolge festhalten

### Phase 1 – technische Primitive extrahieren

Aus der Referenz werden zunächst ohne Verhaltensänderung extrahiert:

- URL-Auflösung
- Browser-Kompatibilitätsprüfung
- Person-Thumbnail-Auflösung
- Fallback-Zustandsautomat
- Geometry-Helfer

### Phase 2 – `MediaPreview` gegen Legacy-Verhalten bauen

`MediaPreview` wird nicht zuerst in einer neuen Funktion getestet, sondern muss die Golden-Master-Fälle der etablierten Preview reproduzieren.

### Phase 3 – neue Funktionen auf zentrale Preview umstellen

Zuerst werden neuere und weniger erprobte Flows migriert:

1. Recognition Findings
2. Face Frame Findings
3. Checks

Dabei werden sie an das etablierte Preview-Verhalten angeglichen.

### Phase 4 – Legacy-Funktion selbst umstellen

Erst wenn die zentrale Preview-Schicht alle Referenztests besteht, wird die alte Face-Match-Darstellung intern auf `MediaPreview` umgestellt.

Für den Benutzer darf sich dabei möglichst nichts ändern.

---

## 8. Entscheidung zu `/api/file_image?preview=1`

Die technische Bestandsaufnahme zeigt, dass `preview=1` zusätzliche Normalisierung und Decoding aktiviert.

Trotzdem wird nicht pauschal beschlossen, alle alten Preview-Quellen sofort darauf umzustellen.

Stattdessen gilt:

1. bestehendes Legacy-Verhalten erfassen
2. direkte und `preview=1`-Ausgabe für die Referenzfälle vergleichen
3. Orientation, Qualität, Dateiformat, Performance und Cache-Verhalten testen
4. erst danach eine zentrale Standardregel festlegen

Damit wird verhindert, dass eine vermeintliche Vereinfachung einen lange erprobten Pfad verschlechtert.

---

## 9. Performance als Teil des Referenzvertrags

Die etablierten Funktionen gelten nicht nur visuell, sondern auch hinsichtlich gefühlter Reaktionszeit als Referenz.

Zu messen sind mindestens:

- Zeit bis Bildquelle feststeht
- Zeit bis Preview sichtbar ist
- Anzahl HTTP-Requests pro Preview
- unnötige Decoder-Aufrufe
- wiederholte Requests beim Wechsel zwischen Findings
- Verhalten bei bereits gecachten Photos-Thumbnails

Die zentrale Lösung darf zwar technisch sauberer sein, soll aber keinen messbaren Performance-Rückschritt erzeugen.

---

## 10. Akzeptanzregel

Eine Preview-Vereinheitlichung ist erst abgeschlossen, wenn:

- die etablierten Legacy-Fälle als Tests beschrieben sind,
- `MediaPreview` diese Fälle reproduziert,
- neuere Preview-Flows dasselbe zentrale Verhalten verwenden,
- die Legacy-Funktion selbst anschließend ohne sichtbare Regression auf dieselbe Komponente umgestellt werden kann,
- Fallback, Orientation, Crop, Bounding Box und Personen-Thumbnail mindestens auf dem bisherigen Reifegrad bleiben.

Der Grundsatz lautet damit:

> **Nicht das Neueste definiert den Standard, sondern das am längsten erprobte korrekte Verhalten.**
