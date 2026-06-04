# Konzept: Erweiterung um Gesichtsdaten in IPTC/XMP-Metadaten

## Ziel

`AV_ImgData` soll um die Fähigkeit erweitert werden, Gesichtsdaten aus IPTC-/XMP-Metadaten zu lesen, zu normalisieren, mit bestehenden Gesichtsdaten aus anderen Quellen zu vergleichen und optional in kompatible Metadatenstrukturen zu schreiben.

Der Schwerpunkt liegt nicht auf klassischem IPTC-IIM, sondern auf IPTC Photo Metadata in XMP, insbesondere den IPTC-Extension-Regionen. Klassische IPTC-IIM-Felder können Personennamen transportieren, enthalten aber keine standardisierte Gesichtgeometrie. Für echte Gesichtsdaten mit Namen und Koordinaten ist XMP erforderlich.

Die Erweiterung soll in das bestehende Fotometadaten-Konzept integriert werden und die vorhandenen Schemata wie ACD, Microsoft und MWG-Regions ergänzen. IPTC wird als zusätzliche Metadatenquelle und optionales Ziel behandelt.

## Ausgangslage im aktuellen Paket

Aus der bestehenden Projektstruktur ergeben sich folgende Grundlagen:

- Das Paket fokussiert aktuell auf die Übernahme personbezogener Bildmetadaten in Synology Photos.
- Die Konfiguration enthält bereits einen Bereich `metadata.SCHEMAS` mit `ACD`, `MICROSOFT` und `MWG_REGIONS`.
- Es gibt bereits Checks für doppelte Gesichter, Positionsabweichungen, Dimensionsprobleme und Namenskonflikte.
- ExifTool ist optional eingebunden und kann im Paket als externe Komponente verwendet werden.
- Die UI enthält bereits Fotofunktionen für Status, Face Matching, Checks und Cleanup.
- Das Paket unterscheidet zwischen Metadaten in Dateien und Personen/Faces in Synology Photos.

Die IPTC-Erweiterung sollte deshalb nicht als komplett neuer Hauptbereich entstehen, sondern als Erweiterung des bestehenden Fotobereichs:

- zusätzliche Metadatenquelle `IPTC_EXT_REGIONS`
- neue Checks zur IPTC-Kompatibilität
- neue Schreib-/Exportoption für IPTC-XMP-Regionen
- optional neue UI-Unterfunktion unter Checks oder Configuration

## Fachliche Abgrenzung: IPTC-IIM, IPTC Core, IPTC Extension, XMP

### IPTC-IIM

IPTC-IIM ist das ältere technische Format für IPTC-Metadaten. Es eignet sich für klassische Felder wie Caption, Keywords, Creator, Copyright, City oder Object Name.

Für Gesichtsdaten ist IPTC-IIM nur eingeschränkt geeignet:

- keine standardisierte Region-/Face-Struktur
- keine Koordinaten für Personenflächen
- keine robuste Personenidentität je Gesicht
- potenziell problematische Zeichenkodierung

IPTC-IIM sollte daher nur ergänzend gelesen werden, etwa für globale Personennamen oder Keywords, aber nicht als primärer Face-Region-Standard.

### IPTC Core in XMP

IPTC Core enthält allgemeine Bildmetadaten in XMP. Relevant für Personen ist insbesondere ein Feld für gezeigte Personen, typischerweise `PersonInImage` beziehungsweise `Person shown`.

Dieses Feld ist nützlich für:

- Liste der im Bild gezeigten Personen
- Abgleich gegen erkannte Gesichter
- Plausibilitätsprüfung, ob Metadaten-Gesichter vollständig sind

Es reicht aber nicht für:

- Gesichtkoordinaten
- mehrere Gesichter derselben Person
- Status je Gesicht
- Rollen oder Regionstypen je Region

### IPTC Extension Image Region

Für die Erweiterung ist `IPTC Extension Image Region` der zentrale Ansatz. Dieses Schema beschreibt Bildregionen in XMP und kann für Personen-/Gesichtsregionen verwendet werden.

Relevante Konzepte:

- Region als strukturierter XMP-Eintrag
- Region Boundary mit Geometrie
- Region Name als Name/Beschreibung der Region
- Region Role zur fachlichen Bedeutung der Region
- optional Region Type oder ähnliche Typisierung, je nach konkreter Spezifikation und Tool-Unterstützung

Für das Paket wird IPTC Extension Image Region als neues Region-Schema behandelt, gleichrangig zu MWG Regions, Microsoft People Tags und ACDSee-spezifischen Regionen.

## Zielbild

Nach Umsetzung soll das Paket folgende IPTC-Funktionen unterstützen:

1. IPTC/XMP-Gesichtsregionen aus Bilddateien lesen.
2. IPTC-Personenlisten ohne Koordinaten lesen und mit Regionen vergleichen.
3. IPTC-Regionen in das interne Face-Modell normalisieren.
4. IPTC-Regionen in Checks berücksichtigen.
5. IPTC-Regionen mit Synology-Photos-Gesichtern vergleichen.
6. Aus anderen Face-Schemata IPTC-XMP-Regionen erzeugen.
7. Bestehende IPTC-Metadaten erhalten und nur gezielt Face-/Region-Daten ändern.
8. Dry-Run, Backup und Protokollierung vor Schreibzugriffen nutzen.

## Nicht-Ziele der ersten Umsetzung

Folgende Punkte sollen nicht Teil der ersten Implementierung sein:

- automatische Gesichtserkennung nur zum Erzeugen neuer IPTC-Regionen
- direkte Bearbeitung aller IPTC-Felder
- DAM-/Agenturworkflow für vollständige IPTC-Beschreibung
- Migration kompletter IPTC-IIM-Daten nach XMP
- semantische Rollenbewertung wie wichtig/unwichtig ohne gesondertes Regelwerk
- Cloud-Synchronisierung von IPTC-Metadaten

## Datenmodell

### Internes Face-Modell

Das bestehende interne Modell sollte um eine robuste Quellenkennzeichnung erweitert werden, falls noch nicht vorhanden.

Vorschlag:

```json
{
  "source_schema": "IPTC_EXT_REGIONS",
  "source_location": "embedded_xmp",
  "source_file": "/volume1/photo/example.jpg",
  "name": "Max Mustermann",
  "display_name": "Max Mustermann",
  "region_role": "person",
  "region_type": "face",
  "x": 0.4123,
  "y": 0.2875,
  "w": 0.0833,
  "h": 0.1440,
  "unit": "relative",
  "rotation": 0,
  "confidence": null,
  "source_raw": {}
}
```

### Pflichtfelder für nutzbare Gesichtsdaten

Ein IPTC-Regionseintrag ist für Face Matching nur nutzbar, wenn mindestens vorhanden sind:

- Dateiidentifikation
- Region Boundary oder äquivalente Geometrie
- Name oder eine eindeutig auswertbare Region-Beschriftung
- Bilddimension oder relative Koordinaten

Wenn Koordinaten fehlen, kann der Eintrag nur als `person_in_image`-Hinweis verwendet werden, nicht als Gesicht.

### Koordinatenmodell

Alle Metadatenschemata sollten intern auf ein einheitliches Koordinatenmodell normalisiert werden:

```text
x, y, w, h: relative Werte 0..1
origin: top-left
shape: rectangle
rotation: optional, Grad
```

IPTC-Regionen können je nach konkreter XMP-Struktur Rechtecke oder andere Formen beschreiben. Für Phase 1 sollte nur `rectangle` unterstützt werden. Andere Formen werden erkannt, protokolliert und zunächst nicht automatisch geschrieben.

### PersonInImage ohne Region

IPTC-Personenlisten sollten separat modelliert werden:

```json
{
  "source_schema": "IPTC_CORE",
  "source_field": "PersonInImage",
  "name": "Max Mustermann",
  "has_region": false
}
```

Damit können neue Checks entstehen:

- Person steht in IPTC-Personenliste, aber keine passende Face-Region vorhanden.
- Face-Region enthält Namen, aber Person fehlt in IPTC-Personenliste.
- Synology Photos kennt Person, IPTC-Personenliste fehlt.

## Konfiguration

`var/config.json` sollte erweitert werden:

```json
{
  "metadata": {
    "SCHEMAS": {
      "ACD": true,
      "MICROSOFT": true,
      "MWG_REGIONS": true,
      "IPTC_CORE": true,
      "IPTC_EXT_REGIONS": true
    },
    "IPTC": {
      "READ_PERSON_IN_IMAGE": true,
      "READ_IMAGE_REGIONS": true,
      "WRITE_IMAGE_REGIONS": false,
      "WRITE_PERSON_IN_IMAGE": false,
      "PREFER_XMP_OVER_IIM": true,
      "PRESERVE_EXISTING_REGION_IDS": true,
      "UPDATE_PERSON_IN_IMAGE_FROM_REGIONS": false,
      "REGION_ROLE_FOR_FACES": "person",
      "REGION_TYPE_FOR_FACES": "face",
      "UNSUPPORTED_REGION_SHAPES": "warn"
    }
  }
}
```

Defensive Defaults:

- Lesen ist aktiv.
- Schreiben ist standardmäßig aus.
- XMP wird gegenüber IIM bevorzugt.
- Bestehende Region-IDs werden erhalten.
- PersonInImage wird nicht automatisch verändert, solange der Nutzer dies nicht explizit aktiviert.

## Architekturvorschlag Backend

Neue oder erweiterte Module:

```text
src/
  metadata/
    iptc_core.py
    iptc_regions.py
    iptc_region_serializer.py
    iptc_region_parser.py
    iptc_persons.py
    face_schema_registry.py
    face_schema_normalizer.py
    metadata_write_plan.py
```

Falls die bestehende Backendstruktur anders aufgebaut ist, sollten die Dateinamen entsprechend angepasst werden. Wichtig ist die fachliche Trennung:

- IPTC-Lesen getrennt von IPTC-Schreiben
- Parser getrennt vom normalisierten Face-Modell
- Schreibplan getrennt von tatsächlicher Dateiveränderung
- XMP-Struktur getrennt von UI-/Synology-Photos-Logik

### Schema Registry

Die vorhandenen Schemata sollten nicht über verstreute `if`-Blöcke erweitert werden. Sinnvoll ist eine Registry:

```python
SCHEMA_READERS = {
    "ACD": AcdReader,
    "MICROSOFT": MicrosoftReader,
    "MWG_REGIONS": MwgRegionsReader,
    "IPTC_CORE": IptcCoreReader,
    "IPTC_EXT_REGIONS": IptcExtRegionsReader,
}
```

Dadurch können Checks, Statusanzeigen und Konfiguration einheitlich über alle Metadatenquellen laufen.

## Lesewege

### ExifTool als primärer praktischer Leseweg

ExifTool sollte für IPTC/XMP zunächst der bevorzugte technische Leseweg sein, weil es bereits optional im Paket vorgesehen ist und viele XMP-Strukturen anzeigen kann.

Vorteile:

- unterstützt eingebettete XMP-Daten
- unterstützt Sidecars
- kann IPTC-IIM und XMP gemeinsam auslesen
- vorhandene Paketkonfiguration für ExifTool kann genutzt werden

Nachteile:

- verschachtelte XMP-Regionen können je nach Ausgabeformat komplex sein
- Schreibzugriffe auf strukturierte XMP-Arrays müssen sorgfältig getestet werden
- Performance bei großen Bibliotheken muss gemessen werden

Empfehlung:

- Phase 1: ExifTool JSON-Ausgabe lesen und in internes Modell normalisieren.
- Phase 2: Schreiben nur über gezielte XMP-Serialisierung oder geprüfte ExifTool-Argumente.

### Nativer XMP-Parser als ergänzende Option

Langfristig kann ein nativer XMP-Parser sinnvoll sein:

- `xml.etree.ElementTree` für XMP-Pakete
- eigene Extraktion der XMP-Sektion aus JPEG/TIFF nur falls notwendig
- kein hartes zusätzliches Paket erforderlich

Risiko: Bildformate und XMP-Einbettung sind fehleranfällig. Deshalb sollte native Verarbeitung zunächst nur für Sidecar-XMP oder bereits extrahierte XMP-Blöcke verwendet werden.

## Schreibkonzept

### Grundprinzip

Schreiben in IPTC/XMP muss defensiv erfolgen:

1. Datei analysieren.
2. Bestehende XMP-Struktur sichern.
3. Schreibplan erzeugen.
4. Dry-Run anzeigen.
5. Nur bei expliziter Bestätigung schreiben.
6. Backup oder Rollback-Daten erzeugen.
7. Nach dem Schreiben erneut lesen und validieren.

### Schreibziele

Mögliche Schreiboperationen:

| Operation | Beschreibung | Default |
|---|---|---|
| `write_iptc_regions_from_selected_schema` | IPTC-Regionen aus ACD/MWG/MS/Photos erzeugen | aus |
| `update_iptc_region_names` | Namen vorhandener IPTC-Regionen korrigieren | aus |
| `update_person_in_image_from_regions` | globale Personenliste aus Regionen erzeugen | aus |
| `remove_iptc_regions` | IPTC-Regionen löschen | aus |
| `merge_iptc_regions` | bestehende Regionen mit neuer Quelle abgleichen | aus |

### Schreibstrategie für Regions

Für Phase 1 sollte nur `replace controlled subset` unterstützt werden:

- Bestehende IPTC-Regionen werden gelesen.
- Nur Regionen, die eindeutig vom Tool verwaltet werden oder eindeutig mit einer Quelle gematcht wurden, werden verändert.
- Unbekannte IPTC-Regionen bleiben erhalten.
- Nicht-rechteckige Regionen bleiben erhalten und werden nicht verändert.

Ein kompletter Ersatz aller IPTC-Regionen sollte nur als Expertenoption umgesetzt werden.

## Mapping zwischen vorhandenen Schemata und IPTC

### ACDSee nach IPTC

Mögliche Quelle:

- ACDSee-Gesichtsregionen mit Namen und Koordinaten.

Mapping:

- ACD-Name -> IPTC Region Name
- ACD-Koordinaten -> IPTC Region Boundary
- Quelle -> Tool-Hinweis in internem Protokoll, nicht zwingend in IPTC schreiben

Risiken:

- ACDSee kann eigene Felder und abweichende Koordinatensysteme nutzen.
- Doppelte Gesichter müssen vor dem Schreiben geprüft werden.

### Microsoft People Tags nach IPTC

Mögliche Quelle:

- Microsoft-Personenregionen.

Mapping:

- Person Display Name -> IPTC Region Name
- Rectangle -> IPTC Boundary

Risiken:

- Microsoft-Personentags können teilweise Kontakt-/Identity-Informationen enthalten.
- Privacy-relevante Felder dürfen nicht unkontrolliert übernommen werden.

### MWG Regions nach IPTC

Mögliche Quelle:

- MWG RegionInfo / RegionList.

Mapping:

- MWG Area -> IPTC Boundary
- MWG Name -> IPTC Region Name
- MWG Type `Face` -> IPTC Face/Person-Rolle

MWG dürfte die fachlich naheliegendste Quelle für eine IPTC-Regionserzeugung sein, weil beide Regionenkonzepte strukturiert sind.

### Synology Photos nach IPTC

Mögliche Quelle:

- Synology-Photos-Gesichter und Personenzuordnung.

Mapping:

- Synology Person Name -> IPTC Region Name
- Synology Face Bounding Box -> IPTC Region Boundary

Risiken:

- Synology Photos kann interne Face IDs, Cluster und Rechtekontext besitzen.
- Nur Daten schreiben, die der Nutzer explizit exportieren will.
- Personen, die in Synology Photos versteckt/ignoriert werden sollen, müssen respektiert werden, sobald eine solche Ignore-Logik im Paket existiert.

## Checks und Analysefunktionen

Die IPTC-Erweiterung sollte neue Checks ergänzen:

### IPTC ohne Region

Person steht in IPTC `PersonInImage`, aber es gibt keine passende Region.

Ergebnis:

- Hinweis, kein Fehler.
- Option: Region aus anderem Schema erzeugen, wenn verfügbar.

### Region ohne PersonInImage

Eine IPTC-Region hat einen Namen, aber der Name fehlt in `PersonInImage`.

Ergebnis:

- Vorschlag: `PersonInImage` ergänzen.

### IPTC/MWG/ACD/MS Positionsabweichung

IPTC-Region unterscheidet sich stark von einer vorhandenen Region derselben Person in anderem Schema.

Ergebnis:

- Konflikt anzeigen.
- Keine automatische Korrektur ohne Bestätigung.

### Doppelte IPTC-Regionen

Mehrere IPTC-Regionen mit gleichem Namen und stark überlappender Fläche.

Ergebnis:

- möglicher Duplikat-Hinweis.
- Option: manuell ignorieren oder zusammenführen.

### Ungültige IPTC-Regionen

Regionen mit fehlender Boundary, negativen Werten, Werten außerhalb 0..1 oder nicht unterstützter Form.

Ergebnis:

- Validierungsfehler.
- Schreiben blockieren, bis geklärt.

### Nicht synchronisierte Namen

Gleiche Region/Position, aber abweichende Namen zwischen IPTC und anderem Schema.

Ergebnis:

- Namenskonflikt.
- Nutzung bestehender Name-Mapping-Logik prüfen.

## UI-Konzept

Die Erweiterung sollte in bestehende Fotofunktionen integriert werden.

### Configuration

Neue Einstellungen:

- IPTC Core lesen
- IPTC Extension Regions lesen
- IPTC Regions schreiben erlauben
- PersonInImage schreiben erlauben
- XMP-Sidecars berücksichtigen
- Eingebettetes XMP scannen
- ExifTool für IPTC bevorzugen

### Checks

Neue Filter/Spalten:

- Quelle: `IPTC Core`, `IPTC Extension Regions`
- Region vorhanden: ja/nein
- PersonInImage vorhanden: ja/nein
- Shape: rectangle/unsupported
- Schreibvorschlag: kein/update/create/skip

### Cleanup

Erweiterbare Aktionen:

- IPTC-Region löschen
- IPTC-Regionsname ersetzen
- IPTC-Region aus anderem Schema erzeugen
- PersonInImage-Liste ergänzen

Alle Aktionen müssen Dry-Run und Einzelbestätigung unterstützen.

## API-Konzept

Neue oder erweiterte Endpunkte:

```text
metadata_schema_status
iptc_preview_file
iptc_scan_start
iptc_scan_status
iptc_scan_result
iptc_write_plan_start
iptc_write_plan_status
iptc_write_apply_start
iptc_write_apply_status
iptc_write_result
```

Alternativ können bestehende Checks-Endpunkte erweitert werden, wenn sie bereits generisch genug sind. Wichtig ist, dass IPTC-Schreiboperationen nicht versteckt in allgemeinen Checks laufen.

## Paketstruktur

Keine Änderung an `INFO.sh` erforderlich. IPTC ist keine DSM-Paketabhängigkeit.

Mögliche neue Dateien:

```text
requirements-optional-xmp.txt           # nur falls später zusätzliche XMP-Bibliothek gewählt wird
src/metadata/iptc_core.py
src/metadata/iptc_regions.py
src/metadata/iptc_region_parser.py
src/metadata/iptc_region_writer.py
src/metadata/iptc_checks.py
src/metadata/schema_registry.py
ui/src/views/IptcMetadataView.vue        # optional, falls eigene View gewünscht
ui/src/mixins/iptcMetadataMixin.js       # optional
```

Empfehlung für Phase 1: keine neue pip-Abhängigkeit. ExifTool und Python-Standardbibliothek reichen für Analyse und Sidecar-XMP-Prototypen. Zusätzliche Bibliotheken erst nach belastbarem Nutzen einführen.

## Sidecar-Konzept

Das Paket unterstützt bereits Sidecar-Varianten in der Konfiguration. IPTC-XMP sollte diese Grundlage nutzen:

- eingebettetes XMP in Bilddatei
- `.xmp` Sidecar mit gleichem Stem
- `.xmp` Sidecar im Unterordner
- Schreibziel konfigurierbar: eingebettet oder Sidecar

Empfohlener Default:

- Lesen: eingebettet und Sidecar nach bestehender Sidecar-Logik.
- Schreiben: zunächst Sidecar bevorzugen, falls vorhanden oder explizit aktiviert.
- Direktes Schreiben in Originalbild nur mit Backup.

## Datenschutz und Rechte

Gesichtsdaten sind personenbezogene Daten. IPTC-Schreibfunktionen müssen deshalb bewusst zurückhaltend sein.

Anforderungen:

- Schreibfunktionen standardmäßig deaktiviert.
- Sichtbarer Hinweis, dass Namen und Gesichtspositionen in Dateien geschrieben werden.
- Keine automatische Veröffentlichung/Exportannahme.
- Protokoll, welche Dateien personenbezogene Daten erhalten haben.
- Optionaler Modus, der nur technische Face-Regionen ohne Namen schreibt, falls sinnvoll.
- Möglichkeit, bestimmte Personen vom IPTC-Export auszuschließen.

## Backup- und Rollback-Konzept

Vor jeder Schreiboperation:

- Originaldatei oder Original-XMP sichern.
- Schreibplan speichern.
- Alte IPTC/XMP-Struktur speichern.
- Nach dem Schreiben validieren.

Vorgeschlagener Speicherort:

```text
/var/packages/AV_ImgData/var/iptc_region_writes/
  2026-06-04T130000_plan.json
  2026-06-04T130000_before.json
  2026-06-04T130000_after.json
  2026-06-04T130000_rollback.json
```

Rollback sollte mindestens für Sidecar-Dateien vollständig möglich sein. Für eingebettete Originaldateien ist ein vollständiges Dateibackup vorzuziehen.

## Testkonzept

### Unit-Tests

- IPTC-Region-Parser
- PersonInImage-Parser
- Koordinatennormalisierung
- Rechteckvalidierung
- Mapping MWG -> IPTC
- Mapping Microsoft -> IPTC
- Mapping ACD -> IPTC
- Konflikterkennung
- Schreibplanerzeugung

### Fixture-Dateien

Benötigt werden kleine Testdateien beziehungsweise XMP-Samples:

```text
tests/fixtures/iptc/
  iptc_core_person_in_image.xmp
  iptc_ext_region_single_face.xmp
  iptc_ext_region_multiple_faces.xmp
  iptc_ext_region_unsupported_shape.xmp
  iptc_ext_region_without_name.xmp
  mixed_mwg_iptc_regions.xmp
```

Für eingebettete Metadaten sollten zusätzlich kleine JPEG-Testdateien verwendet werden, sofern Lizenz und Repositorygröße das erlauben. Alternativ werden XMP-Blöcke als Textfixtures getestet.

### Integrationstests

- ExifTool nicht vorhanden: IPTC-Lesen deaktiviert oder nur Sidecar-Parser aktiv.
- ExifTool vorhanden: eingebettetes XMP wird gelesen.
- Datei mit IPTC Core, aber ohne Regions.
- Datei mit IPTC Regions, aber ohne PersonInImage.
- Schreibplan erzeugen, aber nicht ausführen.
- Sidecar schreiben und erneut lesen.
- Backup-/Rollback-Dateien erzeugen.

### Manuelle DSM-Tests

- Synology Photos liest bestehende Dateien weiterhin korrekt.
- Keine Verschlechterung der bestehenden ACD/Microsoft/MWG-Erkennung.
- ExifTool-Pfadkonfiguration funktioniert unverändert.
- Große Bibliothek mit aktivem IPTC-Scan bleibt performant.

## Performance-Konzept

IPTC/XMP-Regionen können teuer zu lesen sein, wenn jede Datei vollständig analysiert wird.

Empfehlungen:

- IPTC-Scan nur für unterstützte Bilddateien.
- Sidecar zuerst lesen, wenn konfiguriert.
- Eingebettetes XMP nur bei Bedarf oder mit Byte-Limit scannen.
- ExifTool persistent nutzen, falls aktiviert.
- Pro Datei Metadaten-Hash oder mtime-basierte Cache-Information speichern.
- IPTC-Checks inkrementell ausführen.

## Migrationsstrategie

1. Konfiguration um IPTC-Schemata erweitern.
2. Parser read-only einführen.
3. Statusanzeige erweitern: Anzahl IPTC-Core-Personen, Anzahl IPTC-Regionen.
4. Checks erweitern, ohne Schreibfunktion.
5. Schreibplan als Dry-Run einführen.
6. Sidecar-Schreiben aktivieren.
7. Eingebettetes Schreiben erst nach zusätzlicher Absicherung aktivieren.

## Risiken

| Risiko | Bewertung | Gegenmaßnahme |
|---|---:|---|
| IPTC-Region-Struktur wird von Tools unterschiedlich geschrieben | hoch | breite Fixtures, ExifTool-JSON-Auswertung, toleranter Parser |
| Schreibzugriff beschädigt XMP | hoch | Dry-Run, Backup, Sidecar bevorzugen |
| Koordinatensysteme unterscheiden sich | mittel | strikte Normalisierung und Validierung |
| PersonInImage und Regions widersprechen sich | mittel | Checks statt Auto-Korrektur |
| Datenschutz durch Export von Namen | hoch | Opt-in, Ausschlusslisten, Protokoll |
| Performance bei großen Bibliotheken | mittel | Cache, persistent ExifTool, inkrementelle Scans |

## Umsetzungsvorschlag in Etappen

### Etappe 1: Read-only IPTC-Erkennung

- Config-Flags ergänzen.
- IPTC Core PersonInImage lesen.
- IPTC Extension Regions lesen.
- Normalisierte Face-Objekte erzeugen.
- Status/Counts anzeigen.
- Unit-Tests mit XMP-Fixtures.

### Etappe 2: Checks-Integration

- IPTC-Regionen in vorhandene Duplicate-/Position-/Name-Checks einbeziehen.
- Neue IPTC-spezifische Checks ergänzen.
- UI-Filter für IPTC-Quellen.

### Etappe 3: Schreibplan ohne Ausführung

- Mapping aus MWG/ACD/MS/Synology nach IPTC.
- Schreibplan anzeigen.
- Konflikte blockieren.
- Ergebnisdateien im Paket-Var-Verzeichnis speichern.

### Etappe 4: Sidecar-Schreiben

- IPTC-XMP in Sidecar schreiben.
- Backup-/Rollback-Dateien erzeugen.
- Nachkontrolle durch erneutes Lesen.

### Etappe 5: Eingebettetes Schreiben

- Nur mit ExifTool und Dateibackup.
- JPEG/TIFF separat testen.
- UI-Warnung und explizite Bestätigung.

## Offene Prüfentscheidungen

Vor der Implementierung dürfen folgende Punkte nicht geraten werden:

- Exakte von ExifTool gelieferte Tag-Namen für IPTC Extension Image Region in JSON-Ausgabe.
- Vollständige XMP-Struktur der IPTC-Regionen für alle relevanten Werkzeuge.
- Ob Synology Photos IPTC Extension Image Regions selbst berücksichtigt oder ignoriert.
- Ob bestehende Tools wie ACDSee, Lightroom, Photo Mechanic oder digiKam IPTC-Regionen kompatibel schreiben oder nur lesen.
- Ob Schreibzugriffe in eingebettetes XMP auf DSM mit vorhandenen Rechten zuverlässig funktionieren.

Diese Punkte müssen mit Testdateien und einer DSM-Testinstallation verifiziert werden.

## Empfehlung

Die Erweiterung sollte als zusätzliche Metadaten-Schema-Unterstützung umgesetzt werden, nicht als eigener Produktbereich. Der erste Schritt ist ein read-only IPTC/XMP-Parser mit Checks. Schreibfunktionen sollten strikt als Opt-in erfolgen und zunächst auf Sidecar-XMP begrenzt werden.

Damit bleibt das Paket stabil, bestehende Fotofunktionen werden nicht gefährdet, und IPTC-Gesichtsdaten können schrittweise in den vorhandenen Workflow aus Lesen, Prüfen, Mapping und Übernehmen integriert werden.
