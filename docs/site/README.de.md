# ImgData

`AV_ImgData` ist ein Synology-DSM-Paket für Bildmetadaten, Personenmetadaten und Face-Matching-Workflows rund um Synology Photos. Das Paket kombiniert Python- und Shell-Orchestrierung mit nativen C++-Prozessoren für rechenintensive Bild- und Gesichtsoperationen. Zusätzlich können externe Worker-Pakete erstellt werden, um ausgewählte Grafik- und Bildverarbeitungsaufgaben vom NAS auf leistungsfähigere Windows- oder Linux-Systeme auszulagern.

## Funktionen

- Personenstatistiken aus Synology Photos anzeigen.
- Unbekannte Gesichter aus Synology Photos mit in Bildmetadaten gespeicherten Gesichtsnamen abgleichen.
- Ein erkanntes Gesicht einer bestehenden Photos-Person zuweisen.
- Aus einem erkannten Dateigesicht eine neue Photos-Person anlegen.
- Ein Metadaten-Gesicht über ExifTool direkt aus der Prüfansicht aus den XMP-Daten eines Bildes löschen.
- Dauerhafte Namenszuordnungen für wiederkehrende Varianten von Metadatennamen pflegen.
- Laufzeitkonfiguration direkt über die Paketoberfläche bearbeiten.
- Einen mit dem Paket ausgelieferten nativen C++-Gesichtsprozessor für InsightFace-kompatible ONNX-Erkennung und Embeddings verwenden.
- Optional den mitgelieferten nativen libvips-Bildprozessor für Bildinformationen, Thumbnail-/Normalisierungsarbeiten sowie HEIC-/HEIF-Dekodierung über den enthaltenen libheif/libde265-Stack verwenden.
- Als Entwicklungsschwerpunkt der Version 0.11.0 optionale externe Worker-Pakete für Windows- und Linux-Systeme bauen, um ausgewählte Prozessoraufgaben auszulagern.

## Unterstützte Umgebung

- DSM `7.4` oder neuer
- Paketarchitektur: zielplattformabhängig, entsprechend der vom Synology Toolkit gewählten Plattform
- Synology Toolkit / `pkgscripts-ng`
- Vorbereitetes Build-Environment für die Zielplattform, beispielsweise `geminilake`
- Aktuell verfügbare Synology-Photos-Version auf dem Zielsystem

Die aktuellen Paketmetadaten sind in [`INFO.sh`](https://github.com/AndreasVilippus/av_imgdata/blob/main/INFO.sh) definiert.

## Download

Vorgebaute Pakete stehen unter [GitHub Releases](https://github.com/AndreasVilippus/av_imgdata/releases) bereit.

## Installation

1. Die gewünschte `.spk`-Datei von der GitHub-Releases-Seite herunterladen.
2. In DSM das `Paket-Zentrum` öffnen.
3. Manuelle Installation auswählen.
4. Die heruntergeladene Paketdatei auswählen.
5. Den DSM-Installationsdialog abschließen.

Nach der Installation stellt DSM die unter [`ui/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/ui) definierte Desktop-Oberfläche bereit.

ExifTool kann zusätzlich direkt aus der Paketoberfläche installiert werden, ist aber optional. Wenn ExifTool bereits auf dem System vorhanden ist oder für den jeweiligen Workflow nicht benötigt wird, ist keine zusätzliche ExifTool-Installation erforderlich.

## Aus dem Quellcode bauen

Das Paket wird mit dem Synology Toolkit und `pkgscripts-ng` gebaut.

Die erwartete Verzeichnisstruktur des Toolkit-Workspaces ist:

```text
toolkit/
├── pkgscripts-ng/
└── source/
    └── av_imgdata/
```

Der Paket-Build-Wrapper wird aus dem Toolkit-Hauptverzeichnis aufgerufen. Er aktiviert standardmäßig die Paket-Sammlung, sodass erzeugte SPKs nach `result_spk/` kopiert werden.

```bash
source/av_imgdata/tools/build-package.sh -v 7.4 -p geminilake
```

Der Wrapper führt vor dem eigentlichen Synology-Paketbuild die erforderlichen Vorprüfungen aus:

1. Strukturprüfungen ausführen
2. Python-Test-Suite ausführen
3. `pkgscripts-ng/PkgCreate.py` für das Paket `av_imgdata` mit den übergebenen Optionen starten

Während des Toolkit-Builds werden außerdem die nativen C++-Komponenten gebaut und geprüft:

1. `av-imgdata-face-processor`
2. Smoke-Checks des nativen Gesichtsprozessors
3. Funktionstests des nativen Gesichtsprozessors, sofern Modelldateien vorhanden sind
4. `av-imgdata-image-processor` mit libvips, sofern `AV_IMGDATA_WITH_VIPS` nicht auf `0` gesetzt ist

Der native Gesichtsprozessor ist für das aktuelle Paket erforderlich. Er benötigt eine ONNXRuntime-C-API-Distribution für das aktive Toolkit-Ziel. Der Build-Helper sucht sie in den konfigurierten beziehungsweise standardmäßigen nativen Abhängigkeitsverzeichnissen oder unter `ONNXRUNTIME_ROOT`:

```text
include/onnxruntime_c_api.h
lib/libonnxruntime.so
```

Der native libvips-Bildprozessor wird standardmäßig gebaut und kann für einen Paketbuild deaktiviert werden:

```bash
AV_IMGDATA_WITH_VIPS=0 source/av_imgdata/tools/build-package.sh -v 7.4 -p geminilake
```

Wenn libvips aktiviert ist, enthält der Build die benötigten Shared Libraries und Lizenzmaterialien für libvips, libheif und libde265. Der Paket-Installationsschritt schlägt absichtlich fehl, wenn erforderliche native Binärdateien oder Laufzeitbibliotheken fehlen.

Der UI-Build wird bewusst über die normale Synology-Toolkit-Buildkette und die Paket-Makefiles ausgeführt. Dadurch bleibt der getestete Paket-Buildpfad identisch mit dem tatsächlichen DSM-Paketbuild.

Wenn eine Strukturprüfung, ein Python-Test, der UI-Build oder der Toolkit-Paketbuild fehlschlägt, schlägt der gesamte Paketbuild fehl.

Argumente für `build-package.sh` werden als Optionen an `PkgCreate.py` weitergereicht. Der Paketname `av_imgdata` wird vom Wrapper immer selbst ergänzt und sollte daher nicht zusätzlich mit `-c av_imgdata` übergeben werden. Wenn keine Optionen angegeben werden, ergänzt der Wrapper außerdem standardmäßig `-c`, um erzeugte SPKs nach `result_spk/` zu übernehmen.

Beispiel:

```bash
source/av_imgdata/tools/build-package.sh -v 7.4 -p apollolake
```

Vor dem ersten Build muss das Synology-Toolkit-Environment vorbereitet werden, zum Beispiel:

```bash
cd pkgscripts-ng
./EnvDeploy -v 7.4 -p geminilake
cd ..
source/av_imgdata/tools/build-package.sh -v 7.4 -p geminilake
```

Erzeugte Pakete werden vom Toolkit gesammelt unter:

```text
result_spk/
```

Abhängig von der Toolkit-Konfiguration können sowohl ein reguläres Paket als auch eine `_debug.spk` erzeugt werden. Die reguläre SPK ist das Installationsartefakt für den normalen Betrieb. Eine `_debug.spk` ist nur dann sinnvoll, wenn das Toolkit mit `NOSTRIP` läuft; in diesem Fall bleiben native Symbole für Crash- oder Laufzeitdiagnosen erhalten. Für normale Python-/UI-Fehlersuche ist stattdessen das begrenzte `backend-debug.log` vorgesehen. Externe Worker-Archive werden weiterhin als normale Release-Pakete gebaut, sofern sie nicht separat mit expliziten Debug-Einstellungen erzeugt werden.

Native Build-Artefakte entstehen unter:

```text
build/native/<platform>/
```

Der Paket-Wrapper verschiebt lokale Entwicklungsartefakte wie `.test-venv`, `ui/node_modules`, Python-Caches und native Build-Verzeichnisse vorübergehend aus dem Weg, bevor der Quellbaum in das Synology-Toolkit-Build-Environment eingebunden wird. Nach dem Build werden diese Verzeichnisse wiederhergestellt.

## Laufzeitdatenbank

Der gesamte veränderliche Paketstatus wird in der paketlokalen SQLite-Datenbank gespeichert. Dazu gehören Namenszuordnungen, Unterdrückungen, Prüffunde, Face-Match-Funde, interne Kandidaten-Snapshots, Laufzeitfortschritt und das jeweils letzte Analyseergebnis:

```text
${SYNOPKG_PKGVAR}/imgdata.sqlite3
```

Vorhandene `name_mappings.json`, Findings-JSON-Dateien, Runtime-State-JSON-Dateien, `file_analysis.json` und Check-Ignore-Textdateien werden während des SQLite-Upgrades genau einmal importiert. Danach erfolgen operative Lese- und Schreibzugriffe ausschließlich über SQLite.

Die alten Quelldateien bleiben erhalten; spätere Änderungen werden jedoch nur noch in SQLite gespeichert. Backups sollten `imgdata.sqlite3` sowie – sofern vorhanden – `imgdata.sqlite3-wal` und `imgdata.sqlite3-shm` enthalten.

Aktive Face-Match-Funde können über DSM-SSH abgefragt werden:

```bash
sudo sqlite3 -header -column /var/packages/AV_ImgData/var/imgdata.sqlite3 \
  "SELECT position, action, image_path, source_name FROM face_match_finding_entries ORDER BY position;"
```

Prüffunde und gespeicherter Laufzeitstatus lassen sich ebenfalls abfragen:

```bash
sudo sqlite3 -header -column /var/packages/AV_ImgData/var/imgdata.sqlite3 \
  "SELECT finding_type, entry_count, status FROM persisted_findings ORDER BY finding_type;"

sudo sqlite3 -header -column /var/packages/AV_ImgData/var/imgdata.sqlite3 \
  "SELECT key, updated_at FROM app_state ORDER BY key;"
```

Das Paket führt kein dauerhaft wachsendes `server.log`. Uvicorn-Access-Logging und reguläres Shell-Logging sind deaktiviert. Vorhandene ältere `server.log`-Dateien werden beim Paketstart entfernt. Optionale Backend-Diagnosen bleiben über das separat begrenzte `backend-debug.log` verfügbar.

## UI-Entwicklung

Die Paketoberfläche befindet sich unter [`ui/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/ui) und basiert auf Vue 2 mit Synology-DSM-UI-Komponenten.

Nützliche Befehle für reine UI-Entwicklung:

```bash
cd ui
pnpm install
pnpm run build
```

Für Paketbuilds sollte stattdessen der Paket-Build-Wrapper verwendet werden:

```bash
cd ../..
source/av_imgdata/tools/build-package.sh -v 7.4 -p geminilake
```

Der Wrapper führt Strukturprüfungen und Python-Tests aus, bevor das Synology Toolkit gestartet wird. Die UI wird anschließend über denselben Makefile-Pfad gebaut, der auch für das finale Paket verwendet wird.

Hinweise:

- Der eigentliche Paketbuild wird vom Synology Toolkit gesteuert.
- Die DSM-Desktop-App-Konfiguration ist in [`ui/app.config`](https://github.com/AndreasVilippus/av_imgdata/blob/main/ui/app.config) definiert.
- UI-Texte folgen Synologys `texts/<locale>/strings`-Struktur.

## Laufzeitkonfiguration

Die Standardkonfiguration des Pakets wird in [`var/config.json`](https://github.com/AndreasVilippus/av_imgdata/blob/main/var/config.json) ausgeliefert.

Zur Laufzeit verwendet DSM ein beschreibbares Paket-Var-Verzeichnis. Die aktive Konfiguration liegt typischerweise unter:

```text
/var/packages/AV_ImgData/var/config.json
```

Abhängig von der DSM-Umgebung kann `SYNOPKG_PKGVAR` auf einen anderen Paket-Var-Pfad zeigen, beispielsweise `/volume1/@appdata/AV_ImgData/`.

Aktuell unterstützte Konfigurationsbereiche umfassen unter anderem:

- `files.USE_EXIFTOOL`
- `files.IMAGE_DECODER_ENABLED`
- `files.IMAGE_DECODER_EXTENSIONS`
- `files.IMAGE_DECODER_ORDER`
- `files.IMAGE_DECODER_MAX_EDGE`
- `files.RECOGNITION_IMAGE_MAX_EDGE`
- `files.IMAGE_DECODER_TIMEOUT_SECONDS`
- `files.PATHEXIFTOOL`
- `metadata.SCHEMAS.ACD`
- `metadata.SCHEMAS.MICROSOFT`
- `metadata.SCHEMAS.MWG_REGIONS`
- `photos.MAX_PHOTOS_PERSONS`
- `native_processors.FACE_PROCESSOR`
- `native_processors.IMAGE_PROCESSOR_VIPS`

`native_processors.FACE_PROCESSOR` steuert den mit dem Paket ausgelieferten C++-Gesichtsprozessor einschließlich InsightFace-kompatiblem ONNX-Modellpfad/-namen sowie Status-Cache- und Timeout-Einstellungen.

`native_processors.IMAGE_PROCESSOR_VIPS` steuert das optionale libvips-Backend. Es wird standardmäßig mit dem Paket ausgeliefert, ist zur Laufzeit aber standardmäßig mit `ENABLED: false` deaktiviert. Wenn es aktiviert und verfügbar ist, kann es gegenüber dem Standard-Bildbackend bevorzugt werden und bei entsprechender Konfiguration auf das Standard-Backend zurückfallen.

Namenszuordnungen werden in der paketlokalen SQLite-Datenbank gespeichert:

```text
/var/packages/AV_ImgData/var/imgdata.sqlite3
```

Eine vorhandene `name_mappings.json` bleibt als Migrationsquelle erhalten und wird genau einmal importiert.

## Paketstruktur

- [`src/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/src): Backend-Code
- [`ui/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/ui): DSM-Desktop-Oberfläche
- [`processors/native/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/processors/native): mit dem Paket ausgelieferte C++-Prozessoren
- [`processor_contract/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/processor_contract): JSON-Verträge für native Jobs und Ergebnisse
- [`scripts/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/scripts): Synology-Paket-Lifecycle-Skripte
- [`SynoBuildConf/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/SynoBuildConf): Synology-Buildanweisungen
- [`tools/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/tools): Build-, Smoke-Test- und Paket-Hilfsskripte
- [`conf/`](https://github.com/AndreasVilippus/av_imgdata/tree/main/conf): Paket-Privilege- und Resource-Konfiguration

## Lokalisierung

Die primäre Projektsprache für Dokumentation und Standardwerte ist Englisch.

Aktuelle UI-Sprachen:

- `enu`
- `ger`

## Unterstützung

Wenn dir dieses Projekt gefällt oder es dich beziehungsweise deine KI zu neuen Ideen inspiriert, kannst du die Weiterentwicklung unterstützen.

- Buy me a coffee: <https://ko-fi.com/andreasvilippus>
- PayPal-Spende: <https://www.paypal.com/donate/?hosted_button_id=QNGJ8D92V99GN>
- Entwicklung unterstützen

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [`LICENSE`](https://github.com/AndreasVilippus/av_imgdata/blob/main/LICENSE).
