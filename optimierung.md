# Optimierungsplan: Lese- und Schreibvorgänge in AV_ImgData reduzieren

## Ziel

Dieses Dokument beschreibt konkrete, sequenziell abarbeitbare Optimierungen für das Repository `AndreasVilippus/av_imgdata`.

Der Fokus liegt auf:

- weniger Datei-Lesezugriffen
- weniger vollständigem Einlesen großer Bilddateien
- weniger wiederholtem JSON-/Config-Parsing
- weniger ExifTool-Prozessstarts
- weniger redundanten Synology-Photos-API-Abfragen
- weniger Schreiblast auf Runtime-/Findings-Dateien
- stabiler Kompatibilität mit dem bestehenden Single-Uvicorn-Worker-Design

Mehrere Uvicorn-Worker sind **nicht** Bestandteil dieses Plans. Die Optimierungen sollen innerhalb des bestehenden Single-Prozess-Designs funktionieren.

---

## Grundregeln für alle Änderungen

Codex soll bei allen Arbeitspaketen folgende Regeln einhalten:

1. Bestehende API-Endpunkte dürfen nicht umbenannt werden.
2. Bestehende Response-Strukturen sollen kompatibel bleiben.
3. Keine Änderung am DSM-Paketstart auf mehrere Uvicorn-Worker.
4. Caches müssen thread-sicher sein, wenn sie von Hintergrund-Threads genutzt werden.
5. Langlauf-Caches sollen bevorzugt pro Scanlauf gelten, nicht dauerhaft über Prozesslaufzeit hinweg, außer explizit anders beschrieben.
6. Änderungen an Schreiboperationen müssen atomar sein, wenn Runtime-/Findings-Dateien betroffen sind.
7. Bei Fehlern muss der bestehende Fallback-Pfad erhalten bleiben.
8. Jede Optimierung muss über Unit-Tests oder mindestens gezielte Integrationstests abgesichert werden.
9. Performance-Verbesserungen müssen messbar sein: Anzahl Reads/Writes, Anzahl ExifTool-Aufrufe, Laufzeit pro N Dateien.
10. Neue Konfigurationsoptionen müssen sinnvolle Defaults haben und ohne bestehende `config.json` funktionieren.

---

## Betroffene Hauptdateien

Die folgenden Dateien sind voraussichtlich primär betroffen:

```text
src/handler/file_handler.py
src/handler/exiftool_handler.py
src/services/config_service.py
src/services/name_mapping_service.py
src/services/file_analysis_service.py
src/handler/photos_handler.py
src/api/session_manager.py
src/imgdata.py
src/api/imgdata_api.py
```

Optional, falls Tests vorhanden oder anzulegen sind:

```text
tests/
```

Falls noch kein Test-Setup existiert, soll Codex minimal-invasive Tests unter `tests/` ergänzen.

---

# Arbeitspaket 1: ConfigService mtime-cache

## Problem

`ConfigService.readMergedConfig()` liest und merged die Konfiguration wiederholt. Viele Handler fragen dieselbe Config mehrfach pro Request oder Scan ab. Dadurch entstehen unnötige kleine Datei-Reads und wiederholtes JSON-Parsing.

## Ziel

`readMergedConfig()` soll die gemergte Konfiguration cachen und nur neu laden, wenn sich die zugrunde liegende `config.json` oder relevante Ignore-List-Dateien geändert haben.

## Betroffene Datei

```text
src/services/config_service.py
```

## Umsetzungsschritte

1. In `ConfigService.__init__` neue Instanzfelder ergänzen:

   ```python
   self._merged_config_cache = None
   self._merged_config_cache_signature = None
   ```

2. Eine private Methode ergänzen:

   ```python
   def _config_signature(self) -> tuple:
       ...
   ```

3. Die Signatur soll mindestens enthalten:

   - Pfad der Config-Datei
   - `st_mtime_ns` der Config-Datei oder `0`, wenn sie nicht existiert
   - `st_size` der Config-Datei oder `0`
   - für jede bekannte Ignore-List:
     - Pfad
     - `st_mtime_ns`
     - `st_size`

4. `readMergedConfig()` so ändern:

   - Signatur berechnen
   - wenn Cache vorhanden und Signatur identisch:
     - gecachte Config zurückgeben
   - sonst:
     - `readConfig()`
     - `migrateLegacyChecksIgnoreLists(config)`
     - `normalizeConfig(config)`
     - `_deep_merge_dict(defaultConfig(), normalized)`
     - Ergebnis cachen
     - Ergebnis zurückgeben

5. Wichtig: Rückgabe gegen versehentliche Mutation schützen.

   Empfohlene Variante:

   ```python
   import copy
   return copy.deepcopy(self._merged_config_cache)
   ```

   Alternativ kann intern konsequent nicht-mutierende Nutzung garantiert werden. Sicherer ist `deepcopy`.

6. Bei `writeConfig()`, `writeChecksIgnoreList()`, `appendChecksIgnoreToken()` und `clearChecksIgnoreList()` den Cache invalidieren:

   ```python
   self._merged_config_cache = None
   self._merged_config_cache_signature = None
   ```

## Akzeptanzkriterien

- Wiederholte `readMergedConfig()`-Aufrufe ohne Dateiänderung lesen `config.json` nicht erneut.
- Änderungen an `config.json` werden beim nächsten Aufruf erkannt.
- Änderungen an Ignore-Listen werden beim nächsten Aufruf erkannt.
- Bestehende Config-Defaults bleiben unverändert.
- Keine API-Response ändert sich.

## Tests

1. Test: `readMergedConfig()` zweimal aufrufen, Datei zwischenzeitlich nicht ändern, Ergebnis identisch.
2. Test: Config-Datei ändern, `readMergedConfig()` erneut aufrufen, neuer Wert sichtbar.
3. Test: Ignore-List ändern, Status/Config reflektiert Änderung.
4. Test: `writeConfig()` invalidiert Cache.

---

# Arbeitspaket 2: NameMappingService mtime-cache und Lookup-Index

## Problem

`NameMappingService.findNameMapping()` liest die Mapping-Datei indirekt bei jeder Suche erneut. Bei vielen Matching-/Review-Operationen erzeugt das unnötige Datei-Reads und JSON-Parsing.

## Ziel

Name-Mappings sollen mtime-basiert gecacht und zusätzlich als normalisierter Lookup-Index gehalten werden.

## Betroffene Datei

```text
src/services/name_mapping_service.py
```

## Umsetzungsschritte

1. In `__init__` ergänzen:

   ```python
   self._cache_signature = None
   self._cache_mappings = None
   self._cache_index = None
   ```

2. Private Methode ergänzen:

   ```python
   def _mapping_signature(self) -> tuple:
       ...
   ```

   Enthalten:

   - Mapping-Dateipfad
   - `st_mtime_ns` oder `0`
   - `st_size` oder `0`

3. Private Methode ergänzen:

   ```python
   def _load_cached(self) -> tuple[list[dict], dict[str, dict]]:
       ...
   ```

4. `readNameMappings()` so ändern:

   - Signatur prüfen
   - wenn unverändert: Kopie des gecachten Mappings zurückgeben
   - wenn geändert: Datei lesen, normalisieren, Cache und Index aktualisieren

5. `findNameMapping()` so ändern:

   - nicht mehr linear `readNameMappings()` iterieren, sondern Index nutzen:

     ```python
     _, index = self._load_cached()
     return index.get(source_key)
     ```

6. `saveNameMapping()` so ändern:

   - aktuellen Cache laden
   - Mapping aktualisieren oder ergänzen
   - atomar schreiben:
     - temporäre Datei im selben Verzeichnis
     - `json.dump`
     - `flush`
     - optional `os.fsync`
     - `Path.replace`
   - Cache nach erfolgreichem Schreiben aktualisieren oder invalidieren

7. Optional neue Methode:

   ```python
   def saveNameMappingsBatch(self, mappings: list[dict]) -> bool:
       ...
   ```

   Diese Methode ist hilfreich, wenn später mehrere Mappings in einem Lauf geschrieben werden.

## Akzeptanzkriterien

- `findNameMapping()` liest die Datei nicht bei jedem Aufruf neu.
- Änderungen an der Mapping-Datei außerhalb des Prozesses werden erkannt.
- `saveNameMapping()` bleibt kompatibel.
- Schreibvorgänge sind atomar.
- Bei defekter JSON-Datei bleibt bestehendes Verhalten erhalten: leere Liste und `_last_read_error`.

## Tests

1. Test: Zwei `findNameMapping()`-Aufrufe ohne Dateiänderung nutzen Cache.
2. Test: Datei ändern, neuer Mapping-Wert wird erkannt.
3. Test: `saveNameMapping()` aktualisiert existierenden Eintrag.
4. Test: `saveNameMapping()` ergänzt neuen Eintrag.
5. Test: defekte JSON-Datei führt nicht zu Exception.

---

# Arbeitspaket 3: Sidecar-Verzeichnis-Cache pro Scanlauf

## Problem

`FileHandler.findXmpForImage()` prüft für jedes Bild mehrere Sidecar-Varianten und nutzt dafür case-insensitive Verzeichnissuchen. Bei vielen Bildern im selben Ordner werden dieselben Verzeichnisse wiederholt gelesen.

## Ziel

Während eines Analyse-/Matching-/Check-Laufs sollen Verzeichnisse und XMP-Sidecars nur einmal indexiert werden.

## Betroffene Dateien

```text
src/handler/file_handler.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Klasse oder Struktur in `file_handler.py` einführen:

   ```python
   class SidecarLookupCache:
       def __init__(self):
           self._dir_cache = {}
           self._xmp_lookup_cache = {}
           self._lock = Lock()
   ```

2. `SidecarLookupCache` soll bereitstellen:

   ```python
   def find_xmp_for_image(self, image_path: str, variants: list[str]) -> Optional[str]:
       ...
   ```

3. Directory-Index-Cache:

   ```python
   self._dir_cache[directory_path] = {
       "filename_lower": Path(...),
       ...
   }
   ```

4. Für `xmp`-Unterordner ebenfalls Directory-Index nutzen.

5. `FileHandler.findXmpForImage()` kompatibel lassen:

   - bestehende Signatur bleibt erhalten
   - intern optional Cache-Parameter erlauben:

     ```python
     def findXmpForImage(self, image_path: str, lookup_cache: Optional[SidecarLookupCache] = None) -> Optional[str]:
         ...
     ```

6. In `ImgDataService` pro Langlauf einen `SidecarLookupCache` erzeugen und an alle Metadatenleseoperationen weiterreichen.

   Dafür `_readImageMetadata()` erweitern:

   ```python
   def _readImageMetadata(self, image_path: str, *, include_unnamed_acd: bool = False, sidecar_cache=None) -> MetadataPayload:
       ...
   ```

7. Alle internen Aufrufer in Scan-/Matching-/Check-Läufen anpassen, damit sie denselben Cache wiederverwenden.

8. Für direkte API-Einzeloperationen darf `sidecar_cache=None` bleiben.

## Akzeptanzkriterien

- Bestehende Sidecar-Varianten funktionieren unverändert:
  - `same_dir_stem`
  - `same_dir_filename`
  - `xmp_dir_stem`
  - `xmp_dir_filename`
- Case-insensitive Lookup bleibt erhalten.
- Pro Scanlauf wird ein Verzeichnis höchstens einmal indexiert.
- Cache wird nicht dauerhaft pro Prozess gehalten, außer explizit gewünscht.
- Änderungen an Sidecars während eines laufenden Scans müssen nicht zwingend sichtbar sein; das ist akzeptabel, solange bestehende Schreiboperationen weiterhin File-Snapshots prüfen.

## Tests

1. Test: Sidecar im gleichen Ordner mit Stem wird gefunden.
2. Test: Sidecar im gleichen Ordner mit vollständigem Dateinamen wird gefunden.
3. Test: Sidecar im `xmp`-Unterordner wird gefunden.
4. Test: Groß-/Kleinschreibung wird ignoriert.
5. Test: Directory-Index wird bei mehreren Bildern im selben Ordner nur einmal aufgebaut.

---

# Arbeitspaket 4: JPEG-Kontext in einem Header-Scan lesen

## Problem

JPEG-Dateien werden derzeit mehrfach und vollständig gelesen:

- eingebettetes XMP
- Dimensionen
- Exif-Orientation

Das erzeugt unnötiges I/O und RAM-Druck.

## Ziel

Für JPEG/JPEG-Dateien soll ein einziger segmentweiser Header-Scan Breite, Höhe, Orientation und XMP liefern.

## Betroffene Dateien

```text
src/handler/file_handler.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Methode in `FileHandler` ergänzen:

   ```python
   @staticmethod
   def readJpegContext(image_path: str, *, include_xmp: bool = True, max_scan_bytes: int = 64 * 1024 * 1024) -> Dict[str, Any]:
       ...
   ```

2. Rückgabeformat:

   ```python
   {
       "width": int | None,
       "height": int | None,
       "unit": "pixel",
       "orientation": int | None,
       "xmp_content": str | None,
       "xmp_source": "embedded_xmp_parsed" | "",
       "scanned_bytes": int,
       "complete": bool,
   }
   ```

3. JPEG-Parser muss Marker segmentweise lesen:

   - Datei beginnt mit `0xFFD8`
   - Marker iterieren
   - Segmentlänge lesen
   - SOF-Marker erkennen:
     - `0xC0`, `0xC1`, `0xC2`, `0xC3`, `0xC5`, `0xC6`, `0xC7`, `0xC9`, `0xCA`, `0xCB`, `0xCD`, `0xCE`, `0xCF`
   - APP1 Exif erkennen:
     - Segment beginnt mit `Exif\x00\x00`
     - Orientation aus TIFF-Struktur lesen
   - APP1 XMP erkennen:
     - typischer Header `http://ns.adobe.com/xap/1.0/\x00`
     - XMP-Inhalt danach dekodieren
   - Scan abbrechen, sobald Dimensionen, Orientation und XMP gefunden wurden
   - `max_scan_bytes` respektieren

4. Bestehende Methoden nicht sofort entfernen:

   - `_readJpegDimensions()`
   - `readJpegExifOrientation()`
   - `loadXmpFromImageParsed()`

   Diese bleiben als Fallback oder für Tests erhalten.

5. `_readImageMetadata()` in `src/imgdata.py` anpassen:

   - Wenn Datei `.jpg`/`.jpeg`
   - und kein Sidecar-XMP vorhanden
   - und ExifTool nicht bevorzugt wird
   - dann `readJpegContext()` einmal aufrufen
   - daraus:
     - `xmp_content`
     - `xmp_source`
     - `image_dimensions`
     - `image_orientation`
     wiederverwenden

6. Wenn `PREFER_EXIFTOOL_FOR_CONTEXT=True`, ExifTool-Pfad respektieren.

7. Wenn der Header-Scan keine Dimensionen oder Orientation liefert, bestehende Fallbacks nutzen.

## Akzeptanzkriterien

- JPG/JPEG-Dateien werden für Dimensionen und Orientation nicht mehr vollständig gelesen, sofern Header-Scan erfolgreich ist.
- XMP aus APP1 wird weiterhin gefunden.
- Dateien ohne XMP funktionieren.
- Dateien ohne Exif-Orientation funktionieren.
- Progressive JPEGs liefern Dimensionen.
- Fallbacks greifen bei beschädigten oder exotischen JPEGs.

## Tests

1. Test-JPEG mit bekannten Dimensionen.
2. Test-JPEG mit Orientation.
3. Test-JPEG mit XMP.
4. Test-JPEG ohne XMP.
5. Test beschädigte JPEG-Datei.
6. Test: Methode liest nicht die komplette Datei, wenn alle Informationen früh gefunden wurden.

---

# Arbeitspaket 5: Full-File-XMP-Scan begrenzen

## Problem

`loadXmpFromImageParsed()` liest vollständige Bilddateien ein. Bei RAW/TIFF/großen JPEGs ist das teuer.

## Ziel

Full-File-XMP-Scan soll begrenzt, konfigurierbar und nur als Fallback genutzt werden.

## Betroffene Dateien

```text
src/handler/file_handler.py
src/services/config_service.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Config-Defaults ergänzen:

   ```python
   "files": {
       ...
       "EMBEDDED_XMP_FULL_SCAN_ENABLED": False,
       "EMBEDDED_XMP_FULL_SCAN_MAX_BYTES": 67108864
   }
   ```

2. `ConfigService.normalizeConfig()` anpassen, damit die Werte normalisiert werden:

   - Boolean für `EMBEDDED_XMP_FULL_SCAN_ENABLED`
   - Integer für `EMBEDDED_XMP_FULL_SCAN_MAX_BYTES`
   - Minimum z. B. `1048576`
   - Maximum z. B. `536870912`

3. `FileHandler.loadXmpFromImageParsed()` erweitern:

   ```python
   def loadXmpFromImageParsed(image_path: str, max_bytes: Optional[int] = None) -> Optional[str]:
       ...
   ```

4. Wenn `max_bytes` gesetzt ist:

   - nur bis `max_bytes` lesen
   - keine vollständige Datei laden
   - bei nicht gefundenem Endtag `None` zurückgeben

5. `_readImageMetadata()` so ändern:

   - JPEG nutzt zuerst `readJpegContext()`
   - Nicht-JPEG nutzt Full-Scan nur, wenn `EMBEDDED_XMP_FULL_SCAN_ENABLED=True`
   - Max-Bytes aus Config nutzen

6. Dokumentation/Kommentar in Code ergänzen:

   - Full-Scan ist teuer
   - sollte nur für Spezialfälle aktiviert werden

## Akzeptanzkriterien

- Standardmäßig kein vollständiger Embedded-XMP-Scan für große Nicht-JPEG-Dateien.
- Option kann alte Verhaltensteilmenge wieder aktivieren.
- Maximalgrenze wird eingehalten.
- Sidecar-XMP bleibt unverändert bevorzugt.

## Tests

1. Test: Standardkonfiguration führt bei Nicht-JPEG nicht zum Full-Scan.
2. Test: Aktivierte Option liest bis Max-Bytes.
3. Test: XMP innerhalb Max-Bytes wird gefunden.
4. Test: XMP nach Max-Bytes wird nicht gefunden.

---

# Arbeitspaket 6: ExifTool-Reads pro Datei bündeln

## Problem

`ExifToolHandler` startet getrennte Prozesse für:

- eingebettetes XMP
- Dimensionen
- Orientation

Prozessstarts sind teuer.

## Ziel

ExifTool soll Metadaten pro Datei mit einem einzigen Aufruf lesen können.

## Betroffene Dateien

```text
src/handler/exiftool_handler.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Methode in `ExifToolHandler` ergänzen:

   ```python
   def readMetadataContext(self, image_path: str, *, include_xmp: bool = True) -> Dict[str, Any]:
       ...
   ```

2. ExifTool-Aufruf:

   ```bash
   exiftool -j -n -ImageWidth -ImageHeight -Orientation -XMP <image_path>
   ```

   Wenn `include_xmp=False`:

   ```bash
   exiftool -j -n -ImageWidth -ImageHeight -Orientation <image_path>
   ```

3. Rückgabeformat:

   ```python
   {
       "success": bool,
       "xmp_content": str | None,
       "image_dimensions": {"width": int | None, "height": int | None, "unit": "pixel"},
       "image_orientation": int | None,
       "error": str,
   }
   ```

4. JSON robust parsen:

   - ExifTool liefert Liste
   - erstes Element verwenden
   - mögliche Keys berücksichtigen:
     - `ImageWidth`
     - `ImageHeight`
     - `Orientation`
     - `XMP`

5. Bestehende Methoden behalten:

   - `loadEmbeddedXmp`
   - `readImageDimensions`
   - `readImageOrientation`

   Diese können intern später auf `readMetadataContext()` delegieren, müssen aber kompatibel bleiben.

6. `_readImageMetadata()` anpassen:

   - Wenn `exiftool_available` und ExifTool für Embedded XMP oder Kontext verwendet werden soll:
     - `readMetadataContext()` einmal aufrufen
     - Werte wiederverwenden
   - Keine drei separaten ExifTool-Aufrufe mehr pro Datei.

## Akzeptanzkriterien

- Bei ExifTool-Kontextlesung maximal ein ExifTool-Prozess pro Datei.
- Dimensionen und Orientation bleiben korrekt.
- XMP bleibt korrekt.
- Fallback auf native Methoden bleibt erhalten.
- Fehler in ExifTool führen nicht zum Abbruch des Scans.

## Tests

1. Mock für `subprocess.run`, prüfen, dass nur ein Aufruf erfolgt.
2. Test JSON-Ausgabe mit Breite/Höhe/Orientation/XMP.
3. Test ExifTool-Fehler.
4. Test fehlende Keys.

---

# Arbeitspaket 7: ExifTool-Batch-Read für Scanläufe vorbereiten

## Problem

Selbst ein ExifTool-Aufruf pro Datei ist bei großen Scans noch teuer.

## Ziel

Für Analyse-Scans soll optional ein Batch-Read vorbereitet werden, der Metadaten für viele Dateien in einem ExifTool-Prozess liest.

## Betroffene Dateien

```text
src/handler/exiftool_handler.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Methode in `ExifToolHandler`:

   ```python
   def readMetadataContextBatch(self, image_paths: list[str], *, include_xmp: bool = True, batch_size: int = 100) -> Dict[str, Dict[str, Any]]:
       ...
   ```

2. Pro Batch ExifTool ausführen:

   ```bash
   exiftool -j -n -ImageWidth -ImageHeight -Orientation -XMP file1 file2 ...
   ```

3. Ergebnis nach `SourceFile` indizieren.

4. Rückgabe:

   ```python
   {
       "/path/to/file1.jpg": {...context...},
       "/path/to/file2.jpg": {...context...}
   }
   ```

5. Neue Config-Defaults:

   ```python
   "files": {
       ...
       "EXIFTOOL_BATCH_READ_ENABLED": False,
       "EXIFTOOL_BATCH_SIZE": 100
   }
   ```

6. In `ImgDataService` zunächst nur vorbereiten:

   - Batch-Kontext optional in Scanlauf erzeugen
   - `_readImageMetadata()` optional `metadata_context_cache` übergeben:

     ```python
     def _readImageMetadata(..., metadata_context_cache: Optional[dict] = None):
         ...
     ```

7. Falls `metadata_context_cache` einen Eintrag für `image_path` hat:

   - keine ExifTool-Einzelreads
   - Kontext direkt verwenden

8. Diese Funktion standardmäßig deaktiviert lassen, bis Tests stabil sind.

## Akzeptanzkriterien

- Batch-Methode funktioniert isoliert.
- Standardverhalten bleibt unverändert, wenn `EXIFTOOL_BATCH_READ_ENABLED=False`.
- Bei aktiviertem Batch sinkt die Anzahl ExifTool-Prozesse deutlich.
- Fehlende Dateien oder ExifTool-Fehler brechen nicht den gesamten Scan ab.

## Tests

1. Mock ExifTool-Batch mit mehreren `SourceFile`-Einträgen.
2. Test `batch_size`.
3. Test fehlende/fehlerhafte Datei.
4. Test Integration mit `_readImageMetadata()` über Cache.

---

# Arbeitspaket 8: Sidecars direkt lesen, ExifTool nur als Fallback

## Problem

Wenn `USE_EXIFTOOL_FOR_SIDECARS=True`, werden `.xmp`-Sidecars über ExifTool gelesen. Für normale XMP-Sidecars ist das unnötig teuer.

## Ziel

Sidecar-Dateien sollen standardmäßig direkt gelesen werden. ExifTool für Sidecars soll nur als Fallback oder expliziter Modus genutzt werden.

## Betroffene Dateien

```text
src/imgdata.py
src/services/config_service.py
```

## Umsetzungsschritte

1. Neue oder geänderte Semantik für Config:

   Bestehende Option:

   ```python
   USE_EXIFTOOL_FOR_SIDECARS
   ```

   beibehalten, aber Nutzung ändern:

   - `False`: direkt lesen
   - `True`: erst direkt lesen, wenn fehlgeschlagen, ExifTool versuchen

2. Neue Option für Fallback-Modus:

   ```python
   SIDECAR_EXIFTOOL_FALLBACK_ENABLED
   ```

   - `False` (Standard): Kein Fallback auf ExifTool für Sidecars
   - `True`: Bei fehlgeschlagenem Direktlesen wird ExifTool als Fallback verwendet, auch wenn `USE_EXIFTOOL_FOR_SIDECARS=False`

3. Optional SIDECAR_READ_MODE:

   ```python
   "SIDECAR_READ_MODE": "direct_first"
   ```

   Erlaubte Werte:

   - `direct_first`
   - `exiftool_first`
   - `direct_only`
   - `exiftool_only`

4. Minimal-invasive Empfehlung:

   Keine neue Option, nur Verhalten verbessern:

   ```python
   xmp_content = self.files.loadXmpFromFile(xmp_path)
   if not xmp_content and use_exiftool_for_sidecars and exiftool_available:
       xmp_content = self.exiftool_handler.loadXmpFile(xmp_path)
   ```

5. Bestehende Tests anpassen oder ergänzen.

## Akzeptanzkriterien

- Sidecar-XMP wird weiterhin gelesen.
- ExifTool-Prozessstart für normale Sidecars entfällt im Erfolgsfall.
- Bei Direktlesefehler kann ExifTool weiterhin helfen, wenn aktiviert.
- Keine Änderung für Embedded-XMP.

## Tests

1. Test Sidecar direkt erfolgreich.
2. Test Sidecar direkt fehlschlägt, ExifTool-Fallback erfolgreich.
3. Test ExifTool nicht verfügbar.
4. Test bestehende Konfigurationsoption bleibt gültig.

---

# Arbeitspaket 9: JSON-Schreibvorgänge atomar und nur bei Änderung

## Problem

`FileAnalysisService` schreibt Analyse- und Findings-Dateien vollständig per `json.dump(..., indent=2, sort_keys=True)`. Auch bei unverändertem Inhalt wird potenziell geschrieben.

## Ziel

Runtime-/Findings-Dateien sollen nur geschrieben werden, wenn sich der Inhalt tatsächlich geändert hat, und dann atomar.

## Betroffene Datei

```text
src/services/file_analysis_service.py
```

## Umsetzungsschritte

1. Hilfsmethode ergänzen:

   ```python
   def _json_bytes(self, payload: Dict[str, Any], *, pretty: bool = True) -> bytes:
       ...
   ```

2. Hilfsmethode ergänzen:

   ```python
   def _write_json_if_changed(self, path: Path, payload: Dict[str, Any], *, pretty: bool = True) -> bool:
       ...
   ```

3. Ablauf:

   - Payload serialisieren
   - Falls Ziel existiert:
     - bestehende Bytes lesen
     - wenn identisch:
       - nicht schreiben
       - `True` zurückgeben
   - sonst:
     - Parent erstellen
     - temporäre Datei im selben Ordner schreiben
     - flush
     - optional `os.fsync`
     - `replace`

4. `writeLatestResult()`, `writeCheckFindings()` und `writeRuntimeState()` auf diese Hilfsmethode umstellen.

5. Optional Config ergänzen:

   ```python
   "runtime": {
       "PRETTY_JSON": True,
       "FSYNC_RUNTIME_WRITES": False
   }
   ```

   Falls keine neue Config gewünscht ist, `pretty=True` beibehalten und `fsync=False`.

## Akzeptanzkriterien

- Unveränderte Inhalte erzeugen keinen Rewrite.
- Schreibvorgänge sind atomar.
- JSON-Format bleibt kompatibel.
- Bei Schreibfehlern wird `False` zurückgegeben wie bisher.

## Tests

1. Test: gleicher Payload schreibt Datei nur einmal.
2. Test: geänderter Payload ersetzt Datei.
3. Test: defekter Parent/Permission-Fehler führt zu `False`.
4. Test: JSON bleibt parsebar.

---

# Arbeitspaket 10: Findings-/Progress-Flush weiter drosseln

## Problem

Große Findings-Dateien können teuer sein, wenn sie während langer Läufe häufig geschrieben werden. Es existieren bereits Flush-Intervalle, diese sollten konsequent angewendet und erweitert werden.

## Ziel

Findings und Progress sollen getrennt behandelt werden:

- Progress: klein, häufiger erlaubt
- Findings: groß, seltener und nur bei Änderung

## Betroffene Dateien

```text
src/imgdata.py
src/services/file_analysis_service.py
```

## Umsetzungsschritte

1. In `ImgDataService` alle Stellen suchen, die `writeCheckFindings()`, `writeLatestResult()` oder `writeRuntimeState()` aufrufen.

2. Für große Findings sicherstellen:

   - Write nur bei:
     - Ende eines Laufs
     - nach `FACE_MATCH_FINDINGS_FLUSH_INTERVAL_SECONDS`
     - nach `FACE_MATCH_FINDINGS_FLUSH_ENTRY_INTERVAL`
     - explizitem Stop/Fehler
   - nicht bei jedem einzelnen Finding

3. Eine generische Debounce-Hilfsklasse einführen:

   ```python
   class WriteDebouncer:
       def __init__(self, min_interval_seconds: int, min_entry_delta: int):
           ...
       def should_flush(self, *, force: bool = False, entry_count: int = 0) -> bool:
           ...
       def mark_flushed(self, entry_count: int) -> None:
           ...
   ```

4. Für Check-Findings ähnliche Intervalle ergänzen:

   ```python
   CHECK_FINDINGS_FLUSH_INTERVAL_SECONDS = 60
   CHECK_FINDINGS_FLUSH_ENTRY_INTERVAL = 25
   ```

5. Progress-Dateien klein halten:

   - Fortschrittsstatus nicht mit kompletter Findings-Liste vermischen
   - Progress ggf. weiterhin häufiger schreiben, aber ebenfalls nur bei Änderung

## Akzeptanzkriterien

- Findings werden während großer Läufe nicht bei jedem Eintrag geschrieben.
- Bei normalem Abschluss ist der finale Stand vollständig geschrieben.
- Bei Stop/Fehler wird ein möglichst aktueller Stand geschrieben.
- UI-Progress bleibt ausreichend aktuell.
- Keine Findings gehen durch Debouncing im normalen Abschluss verloren.

## Tests

1. Test Debouncer nach Zeit.
2. Test Debouncer nach Entry-Delta.
3. Test Force-Flush.
4. Test Abschluss schreibt finalen Stand.

---

# Arbeitspaket 11: Photos-Folder- und Item-Cache pro Scanlauf

## Problem

`PhotosHandler.findFotoTeamItemByPath()` ruft für Ordnerpfade wiederholt `listFotoTeamFolders()` und danach seitenweise `listFotoTeamItems()` auf. Bei vielen Dateien im selben Ordner ist das redundant.

## Ziel

Während eines Scanlaufs sollen Folder-IDs und Items pro Folder gecacht werden.

## Betroffene Dateien

```text
src/handler/photos_handler.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Klasse in `photos_handler.py` oder eigener Datei:

   ```python
   class PhotosLookupCache:
       def __init__(self):
           self.folder_id_by_path = {}
           self.items_by_folder_id = {}
           self.lock = Lock()
   ```

2. `PhotosHandler.findFotoTeamItemByPath()` erweitern:

   ```python
   def findFotoTeamItemByPath(..., lookup_cache: Optional[PhotosLookupCache] = None) -> Optional[Dict[str, Any]]:
       ...
   ```

3. Folder-Cache:

   - Schlüssel: relativer Ordnerpfad, z. B. `/2024/Urlaub`
   - Wert: Folder-ID

4. Items-Cache:

   - Schlüssel: Folder-ID
   - Wert: Dict `filename -> item`
   - Beim ersten Zugriff auf einen Folder alle Items seitenweise laden und indexieren
   - Bei sehr großen Ordnern optional weiterhin paginiert abbrechen, aber Standard: kompletter Folder-Index

5. Cache nur pro Scanlauf erzeugen.

6. Mutierende Operationen, die Photos-Faces ändern, sollen nicht dauerhaft auf alten Cache vertrauen.

   Empfehlung:

   - Item-Cache nur für Pfad-zu-Item-Auflösung nutzen.
   - Nach `addFaceToItem`, `assignFaceToPerson`, `createPersonFromFace` keine Face-Daten aus Cache verwenden.
   - `list_faceFotoTeamItems()` weiterhin frisch lesen, wenn Validierung nötig ist.

## Akzeptanzkriterien

- Wiederholte Lookups im selben Ordner lösen nur einmal Folder-/Item-Listing aus.
- Pfad-zu-Item-Auflösung bleibt korrekt.
- Cache gilt nur während eines Scanlaufs.
- Mutationsvalidierungen bleiben frisch.

## Tests

1. Test: zwei Dateien im selben Ordner erzeugen nur ein Item-Listing.
2. Test: Folder-ID wird gecacht.
3. Test: Datei nicht gefunden.
4. Test: Cache wird nicht global über Scanläufe wiederverwendet.

---

# Arbeitspaket 12: requests.Session pro User wiederverwenden

## Problem

`SessionManager.call_api()` und `call_api_post()` erzeugen pro DSM-API-Aufruf ein neues `requests.Session()`-Objekt. Dadurch werden HTTP Keep-Alive und Connection-Pooling nicht optimal genutzt.

## Ziel

Pro `user_key` soll eine persistente `requests.Session` gehalten und wiederverwendet werden.

## Betroffene Datei

```text
src/api/session_manager.py
```

## Umsetzungsschritte

1. In `SessionManager.__init__` ergänzen:

   ```python
   self._http_sessions: Dict[str, requests.Session] = {}
   ```

2. Private Methode:

   ```python
   def _get_http_session(self, user_key: str, cookies: Dict[str, str]) -> requests.Session:
       ...
   ```

3. Verhalten:

   - Wenn Session für `user_key` fehlt:
     - `requests.Session()` erstellen
     - `verify` setzen
   - Cookies aktualisieren:
     - `session.cookies.update(cookies)`
   - Session zurückgeben

4. In `_resume()`, `call_api()` und `call_api_post()` die persistente Session nutzen.

5. Bei bestimmten Fehlern Session verwerfen:

   - SSL-/Connection-Fehler optional
   - Auth-Resume-Fehler
   - explizite neue Methode:

     ```python
     def _reset_http_session(self, user_key: str) -> None:
         ...
     ```

6. Thread-Sicherheit:

   Aktuell werden `call_api()` und `call_api_post()` pro `user_key` über RLock serialisiert. Dadurch ist die Nutzung einer User-Session akzeptabel.

7. Keine Session pro Prozess global für alle User mischen.

## Akzeptanzkriterien

- Pro User wird Session wiederverwendet.
- Cookies werden aktualisiert.
- Bestehendes Auth-/Resume-Verhalten bleibt kompatibel.
- Keine Cross-User-Cookie-Leaks.
- Fehlerhafte Session kann verworfen werden.

## Tests

1. Mock prüfen: zwei API-Calls für denselben User nutzen dieselbe Session.
2. Zwei User bekommen unterschiedliche Sessions.
3. Cookies werden aktualisiert.
4. Reset entfernt Session.

---

# Arbeitspaket 13: Scan-Kontext-Objekt einführen

## Problem

Mehrere Optimierungen benötigen pro Scanlauf gemeinsame Caches:

- SidecarLookupCache
- PhotosLookupCache
- ExifTool-Batch-Kontext
- Config-Snapshot
- NameMapping-Snapshot

Wenn diese einzeln durchgereicht werden, wird der Code unübersichtlich.

## Ziel

Ein `ScanContext` soll pro Langlauf erzeugt und intern weitergereicht werden.

## Betroffene Dateien

```text
src/imgdata.py
src/handler/file_handler.py
src/handler/photos_handler.py
```

## Umsetzungsschritte

1. Neue Klasse ergänzen, z. B. in `src/imgdata.py` oder `src/services/scan_context.py`:

   ```python
   class ScanContext:
       def __init__(self, config: dict):
           self.config = config
           self.sidecar_cache = SidecarLookupCache()
           self.photos_lookup_cache = PhotosLookupCache()
           self.metadata_context_cache = {}
           self.name_mapping_index = {}
   ```

2. In Startmethoden für Langläufe erzeugen:

   - Face Matching Discovery
   - File Analysis Discovery
   - Checks Discovery
   - Cleanup Discovery, falls relevant

3. `_readImageMetadata()` Signatur erweitern:

   ```python
   def _readImageMetadata(..., scan_context: Optional[ScanContext] = None):
       ...
   ```

4. Innerhalb von `_readImageMetadata()`:

   - Config aus `scan_context.config` nutzen, wenn vorhanden
   - SidecarCache aus `scan_context.sidecar_cache`
   - ExifTool-Kontext aus `scan_context.metadata_context_cache`

5. Bestehende Einzeloperationen lassen `scan_context=None`.

6. Schrittweise migrieren:

   - zuerst Config + Sidecar
   - danach Photos
   - danach ExifTool-Batch

## Akzeptanzkriterien

- Langläufe verwenden gemeinsamen ScanContext.
- Einzel-API-Aufrufe bleiben unverändert.
- Caches werden am Ende des Laufs freigegeben.
- Keine globalen dauerhaften Scan-Caches.

## Tests

1. Test: ScanContext wird erzeugt und weitergereicht.
2. Test: `_readImageMetadata()` funktioniert mit und ohne ScanContext.
3. Test: SidecarCache im ScanContext wird wiederverwendet.

---

# Arbeitspaket 14: Instrumentierung für I/O- und ExifTool-Messung

## Problem

Optimierungen sollten messbar sein. Ohne Zähler ist schwer zu erkennen, ob Reads/Writes/ExifTool-Aufrufe tatsächlich sinken.

## Ziel

Optionales Runtime-Profiling für Scanläufe.

## Betroffene Dateien

```text
src/imgdata.py
src/handler/file_handler.py
src/handler/exiftool_handler.py
src/services/file_analysis_service.py
```

## Umsetzungsschritte

1. Neue Config-Option:

   ```python
   "debug": {
       "IO_METRICS_ENABLED": False
   }
   ```

2. Kleine Metrikklasse:

   ```python
   class IoMetrics:
       file_reads = 0
       file_read_bytes = 0
       file_writes = 0
       file_write_bytes = 0
       exiftool_calls = 0
       photos_api_calls = 0
       cache_hits = {}
       cache_misses = {}
   ```

3. In ScanContext optional `io_metrics` halten.

4. An zentralen Stellen Zähler erhöhen:

   - `FileHandler.loadXmpFromFile`
   - `FileHandler.readJpegContext`
   - `ExifToolHandler.readMetadataContext`
   - `ExifToolHandler.readMetadataContextBatch`
   - `FileAnalysisService._write_json_if_changed`
   - `PhotosHandler` API-Listing-Funktionen, falls ScanContext erreichbar

5. Metriken im Progress oder Ergebnis optional ausgeben:

   ```json
   "io_metrics": {
       "file_reads": 123,
       "file_read_bytes": 456789,
       "file_writes": 4,
       "exiftool_calls": 10,
       "cache_hits": {...}
   }
   ```

6. Standardmäßig deaktiviert.

## Akzeptanzkriterien

- Keine Metriken im Normalbetrieb, wenn deaktiviert.
- Bei Aktivierung erscheinen Metriken im Ergebnis oder Progress.
- Zähler verursachen keine Exceptions.
- Keine sensiblen Cookies/Tokens in Metriken.

## Tests

1. Test Metriken deaktiviert.
2. Test Metriken aktiviert.
3. Test ExifTool-Call-Zähler.
4. Test Write-skipped-Zähler.

---

# Arbeitspaket 15: Optionales Speicherformat für große Findings vorbereiten

## Problem

Große Findings-Dateien als pretty JSON komplett neu zu schreiben ist ineffizient.

## Ziel

Mittelfristig soll ein alternatives Speicherformat vorbereitet werden, ohne sofort die API zu brechen.

## Betroffene Dateien

```text
src/services/file_analysis_service.py
src/imgdata.py
```

## Umsetzungsschritte

1. Neue Config-Option:

   ```python
   "runtime": {
       "FINDINGS_STORAGE_FORMAT": "json"
   }
   ```

2. Erlaubte Werte:

   - `json`
   - später `jsonl`
   - später `sqlite`

3. Vorerst nur `json` implementieren.

4. Interfaces in `FileAnalysisService` intern entkoppeln:

   ```python
   def readCheckFindings(...)
   def writeCheckFindings(...)
   def appendCheckFindingEntries(...)
   ```

5. Neue Methode vorbereiten:

   ```python
   def appendCheckFindingEntries(self, finding_type: str, entries: list[dict]) -> bool:
       ...
   ```

   Für Format `json` darf sie zunächst lesen, ergänzen, schreiben. Später kann sie für `jsonl` append-only werden.

## Akzeptanzkriterien

- Bestehendes JSON-Verhalten bleibt Standard.
- API bleibt kompatibel.
- Code ist vorbereitet, große Findings später append-only zu schreiben.

## Tests

1. Test Standardformat `json`.
2. Test unbekanntes Format fällt auf `json` zurück.
3. Test `appendCheckFindingEntries()` ergänzt Einträge.

---

# Priorisierte Umsetzung

## Phase 1: Risikoarm und direkt wirksam

Diese Phase sollte zuerst umgesetzt werden.

1. Arbeitspaket 1: ConfigService mtime-cache
2. Arbeitspaket 2: NameMappingService mtime-cache und Lookup-Index
3. Arbeitspaket 9: JSON-Schreibvorgänge atomar und nur bei Änderung
4. Arbeitspaket 3: Sidecar-Verzeichnis-Cache pro Scanlauf
5. Arbeitspaket 8: Sidecars direkt lesen, ExifTool nur als Fallback

## Phase 2: Größerer I/O-Gewinn bei Bildmetadaten

6. Arbeitspaket 4: JPEG-Kontext in einem Header-Scan lesen
7. Arbeitspaket 5: Full-File-XMP-Scan begrenzen
8. Arbeitspaket 6: ExifTool-Reads pro Datei bündeln

## Phase 3: Scanlauf-weite Optimierungen

9. Arbeitspaket 13: Scan-Kontext-Objekt einführen
10. Arbeitspaket 11: Photos-Folder- und Item-Cache pro Scanlauf
11. Arbeitspaket 10: Findings-/Progress-Flush weiter drosseln

## Phase 4: Fortgeschrittene Optimierungen

12. Arbeitspaket 12: requests.Session pro User wiederverwenden
13. Arbeitspaket 7: ExifTool-Batch-Read für Scanläufe vorbereiten
14. Arbeitspaket 14: Instrumentierung für I/O- und ExifTool-Messung
15. Arbeitspaket 15: Optionales Speicherformat für große Findings vorbereiten

---

# Empfohlene Branch-/Commit-Struktur

Codex soll die Änderungen in kleinen, reviewbaren Commits umsetzen.

```text
perf/config-cache
perf/name-mapping-cache
perf/atomic-json-writes
perf/sidecar-lookup-cache
perf/jpeg-context-reader
perf/exiftool-context-read
perf/scan-context
perf/photos-lookup-cache
perf/session-reuse
perf/io-metrics
```

Jeder Commit sollte enthalten:

- Codeänderung
- Tests
- kurze Beschreibung der erwarteten Performance-Wirkung

---

# Nicht-Ziele

Diese Punkte sollen in diesem Optimierungsplan ausdrücklich nicht umgesetzt werden:

1. Kein Wechsel auf mehrere Uvicorn-Worker.
2. Kein kompletter Umbau auf externe Queue.
3. Kein Redis, keine externe Datenbank als Pflichtdependency.
4. Kein Entfernen bestehender API-Endpunkte.
5. Kein Entfernen bestehender Config-Werte ohne Migration.
6. Keine Änderung an DSM-Paketstruktur, außer falls Tests oder optionale Config-Defaults ergänzt werden müssen.
7. Keine aggressive Parallelisierung ohne vorherige Messung.

---

# Definition of Done

Der Optimierungsplan gilt als umgesetzt, wenn:

1. Alle Phase-1-Arbeitspakete implementiert und getestet sind.
2. Mindestens Arbeitspaket 4 oder 6 implementiert ist, weil dort der größte Bildmetadaten-I/O-Gewinn liegt.
3. Bestehende API-Endpunkte weiter funktionieren.
4. Ein Scanlauf mit Beispielbildern erfolgreich abgeschlossen wird.
5. Die Anzahl vollständiger Bilddatei-Reads reduziert ist.
6. Die Anzahl ExifTool-Prozessstarts bei aktivem ExifTool reduziert ist.
7. Unveränderte Findings-/Runtime-Dateien nicht mehr neu geschrieben werden.
8. Sidecar-Lookups in Ordnern mit vielen Bildern weniger Directory-Scans erzeugen.
9. Keine neuen Race Conditions bei laufenden Hintergrund-Threads entstehen.
10. Die Änderungen ohne mehrere Uvicorn-Worker stabil laufen.

---

# Manuelle Prüfliste nach Implementierung

Nach der Umsetzung soll manuell geprüft werden:

```text
1. DSM-Paket startet normal.
2. /api/ping liefert success.
3. Status-Seite lädt.
4. File Analysis startet, zeigt Progress und kann gestoppt werden.
5. Checks starten, zeigen Progress und schreiben Findings.
6. Face Matching startet, zeigt Progress und kann gestoppt werden.
7. XMP-Sidecars werden weiterhin erkannt.
8. Embedded XMP in JPEGs wird weiterhin erkannt.
9. Orientierung und Dimensionen werden korrekt angezeigt.
10. Name-Mappings funktionieren weiterhin.
11. ExifTool optional aktiviert funktioniert weiterhin.
12. ExifTool deaktiviert funktioniert weiterhin.
13. Keine Runtime-/Findings-Dateien werden beschädigt.
14. Logs enthalten keine sensiblen Cookies oder Tokens.
15. Performance-Messung zeigt weniger Reads/Writes oder weniger ExifTool-Aufrufe.
```

---

# Hinweise für Codex

Codex soll bei Unsicherheit bevorzugt minimal-invasive Änderungen durchführen.

Empfohlener Arbeitsmodus:

1. Zuerst Tests oder kleine Messpunkte ergänzen.
2. Dann eine Optimierung isoliert implementieren.
3. Tests ausführen.
4. Bestehende Fallbacks beibehalten.
5. Keine großflächigen Refactorings ohne direkten Nutzen.
6. Keine parallelen Worker-Prozesse einführen.
7. Bei jeder Cache-Einführung definieren:
   - Lebensdauer
   - Invalidierung
   - Thread-Sicherheit
   - Fehlerfallback

