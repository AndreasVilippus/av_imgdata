# Konzept: Prüfung und Bereinigung des Aufnahmezeitpunkts von Fotos

## 1. Ziel

`AV_ImgData` soll den tatsächlichen **Aufnahmezeitpunkt eines Fotos** aus mehreren voneinander unabhängigen Quellen ermitteln, vergleichen und Inkonsistenzen sichtbar machen.

Im ersten Umsetzungsschritt arbeitet die Funktion **rein lesend**:

- Zeitinformationen aus Datei-Metadaten werden gelesen.
- Der in Synology Photos gespeicherte Aufnahmezeitpunkt wird gelesen.
- Datum und Uhrzeit aus Dateiname und Verzeichnispfad werden, soweit eindeutig erkennbar, als zusätzliche Indizien ausgewertet.
- Die verwendeten Quellen sind auswählbar.
- Standardmäßig werden nur Fotos mit relevanten Inkonsistenzen angezeigt.
- Es werden noch keine Metadaten und keine Einträge in Synology Photos verändert.

In einer späteren Ausbaustufe sollen erkannte Abweichungen anhand von Regeln oder einer manuellen Auswahl bereinigt werden können. Zielsystem kann dabei **Synology Photos**, die **Bilddatei** oder beides sein.

Dieses Konzept behandelt ausschließlich Datum und Uhrzeit der Aufnahme. Dateisystemzeiten wie Änderungs- oder Erstellungszeit sind keine primären Aufnahmedaten, können aber als technische Hilfsquellen dienen.

---

## 2. Leitprinzipien

1. **Lesen vor Schreiben**  
   Die erste Implementierungsstufe darf weder Dateien noch Synology Photos verändern.

2. **Quellen bleiben getrennt sichtbar**  
   Ein errechneter oder bevorzugter Wert darf die Rohwerte nicht verdecken.

3. **Nicht raten**  
   Unklare Datumsangaben, fehlende Zeitzonen oder mehrdeutige Dateinamen werden als unsicher markiert.

4. **Auswählbare Quellen**  
   Der Benutzer entscheidet, welche Quellen beim Vergleich berücksichtigt werden.

5. **Inkonsistenzen statt Datenflut**  
   Die Standardansicht zeigt nur Dateien, für die sich aus den gewählten Quellen ein relevanter Widerspruch ergibt.

6. **Nachvollziehbarkeit**  
   Für jeden Befund muss erkennbar sein, welcher Zeitwert aus welcher Quelle stammt und warum ein Widerspruch gemeldet wird.

7. **Keine stille Normalisierung**  
   Zeitzonen, Sommerzeit und Sekundenabweichungen dürfen nicht unbemerkt korrigiert werden.

8. **Vorschau vor Bereinigung**  
   Spätere Schreiboperationen benötigen immer eine Vorschau der geplanten Änderungen.

9. **Idempotenz**  
   Wiederholte Prüfung derselben unveränderten Datei muss zum gleichen Ergebnis führen.

10. **Auditierbarkeit**  
    Spätere Änderungen müssen mit altem Wert, neuem Wert, Ziel, Regel und Zeitpunkt protokolliert werden.

---

## 3. Begriffe

### 3.1 Aufnahmezeitpunkt

Der fachlich gewünschte Zeitpunkt, zu dem das Foto aufgenommen wurde.

Intern sollte er möglichst als Kombination aus folgenden Bestandteilen behandelt werden:

```text
CaptureDateTime
- local_datetime
- timezone_offset
- timezone_known
- utc_datetime
- precision
- source
- source_field
- raw_value
- confidence
- warnings
```

Ein Datum ohne bekannte Zeitzone ist nicht automatisch ein UTC-Zeitpunkt.

### 3.2 Quelle

Eine unabhängig lesbare Herkunft eines möglichen Aufnahmezeitpunkts, z. B. EXIF, XMP, Synology Photos, Dateiname oder Verzeichnispfad.

### 3.3 Kandidat

Ein aus einer Quelle abgeleiteter möglicher Aufnahmezeitpunkt.

### 3.4 Referenzwert

Der für einen Vergleich oder eine spätere Bereinigung bevorzugte Kandidat. In der ersten Ausbaustufe wird ein Referenzwert höchstens vorgeschlagen, aber nicht geschrieben.

### 3.5 Inkonsistenz

Ein relevanter Unterschied zwischen zwei oder mehr aktivierten Quellen, der nicht durch eine konfigurierte Toleranz oder eine bekannte Normalisierung erklärt werden kann.

---

## 4. Zu berücksichtigende Quellen

Die Quellen werden getrennt eingelesen und können in der Oberfläche einzeln aktiviert oder deaktiviert werden.

### 4.1 EXIF

Primäre Felder:

| Feld | Bedeutung | Priorität |
| --- | --- | --- |
| `EXIF:DateTimeOriginal` | Zeitpunkt der Aufnahme | sehr hoch |
| `EXIF:OffsetTimeOriginal` | Zeitzonenoffset zu `DateTimeOriginal` | sehr hoch |
| `EXIF:SubSecTimeOriginal` | Subsekunden zur Aufnahme | ergänzend |
| `EXIF:CreateDate` | Erzeugungszeit des digitalen Bildes | hoch |
| `EXIF:OffsetTimeDigitized` | Offset zu `CreateDate` | ergänzend |
| `EXIF:ModifyDate` | letzte Metadaten-/Dateiänderung innerhalb EXIF | niedrig |

`ModifyDate` darf nicht gleichwertig mit `DateTimeOriginal` behandelt werden.

### 4.2 XMP

Relevante Felder können unter anderem sein:

- `XMP:DateTimeOriginal`
- `XMP:CreateDate`
- `XMP:ModifyDate`
- hersteller- oder softwarebezogene Datumsfelder

XMP kann einen EXIF-Wert spiegeln, kann aber auch durch spätere Bearbeitung verändert worden sein. Deshalb bleiben EXIF und XMP technisch getrennte Quellen.

### 4.3 IPTC

Je nach Datei und Herkunft können klassische IPTC- oder IPTC-in-XMP-Felder Datumsinformationen enthalten. Sie werden als ergänzende Quelle behandelt, nicht automatisch als führende Quelle.

### 4.4 QuickTime / Video-Container

Für Videos und Live-Photo-Komponenten können insbesondere QuickTime-/MP4-Felder relevant sein, z. B.:

- `QuickTime:CreateDate`
- `QuickTime:MediaCreateDate`
- `QuickTime:TrackCreateDate`

Die Zeitsemantik solcher Felder ist formatspezifisch. Manche Werte sind UTC, andere werden von Software als lokale Zeit interpretiert. Die Parser müssen diese Unterschiede explizit berücksichtigen.

### 4.5 Synology Photos

Der von Synology Photos verwendete bzw. angezeigte Aufnahmezeitpunkt wird als eigenständige Quelle geführt:

```text
photos.capture_datetime
```

Soweit technisch verfügbar, sollen zusätzlich gespeichert werden:

- Rohwert aus der Photos-Datenbank bzw. API
- Zeitzoneninformation oder bekannte Zeitzoneninterpretation
- zugehörige Asset-/Datei-ID
- Herkunft des Werts innerhalb von Photos

Der Photos-Wert darf nicht stillschweigend als Wahrheit angenommen werden. Er ist eine gleichberechtigte, aber wichtige Vergleichsquelle.

### 4.6 Dateiname

Datum und Uhrzeit können aus dem Dateinamen abgeleitet werden, beispielsweise aus Mustern wie:

```text
IMG_20240518_143522.jpg
2024-05-18 14.35.22.jpg
20240518_143522.jpg
2024-05-18_14-35-22.jpg
PXL_20240518_123522123.jpg
Screenshot_2024-05-18-14-35-22.png
```

Die Extraktion erfolgt nur über bekannte, explizit definierte Muster.

Für jeden Treffer werden gespeichert:

```text
FilenameDateCandidate
- parser_id
- matched_pattern
- raw_match
- parsed_datetime
- precision
- timezone_known
- confidence
```

Ein aus dem Dateinamen gelesenes Datum hat normalerweise keine bekannte Zeitzone.

### 4.7 Verzeichnispfad

Auch Teile des Pfads können Datumsinformationen enthalten, z. B.:

```text
/photos/2024/05/18/IMG_1234.jpg
/photos/2024-05-18 Urlaub/IMG_1234.jpg
/photos/2024/05_Mai/IMG_1234.jpg
```

Der Pfad kann unterschiedlich genaue Informationen liefern:

- nur Jahr
- Jahr und Monat
- vollständiges Datum
- in seltenen Fällen Datum und Uhrzeit

Teilinformationen dürfen nicht zu einer künstlich exakten Uhrzeit erweitert werden.

Beispiel:

```text
/photos/2024/05/...
```

liefert lediglich einen Plausibilitätsbereich vom 1. bis 31. Mai 2024 und keinen konkreten Aufnahmezeitpunkt.

### 4.8 Dateisystemzeiten

Optional können folgende Werte als Hilfsquellen aktiviert werden:

- `mtime`
- `ctime`
- soweit verfügbar `birthtime` / Erstellungszeit

Diese Werte sind standardmäßig **nicht führend**, da Kopier-, Import-, Synchronisations- oder Bearbeitungsvorgänge sie verändern können.

Sie dienen primär zur Plausibilisierung und Diagnose.

---

## 5. Empfohlener ExifTool-Lesemodus

Für Bild- und Videometadaten sollte der vorhandene bzw. zentrale ExifTool-Zugriff verwendet werden.

Empfohlener Basismodus:

```bash
exiftool -json -G1 -a -struct -n <file>
```

Zusätzlich müssen Datumsfelder in ihrer Rohform erhalten bleiben. Parser dürfen die Originaldarstellung nicht verwerfen.

Wichtig ist insbesondere die Trennung von:

```text
2024:05:18 14:35:22
2024:05:18 14:35:22+02:00
2024:05:18 14:35:22Z
```

Diese Werte sind nicht semantisch identisch.

---

## 6. Normalisiertes internes Datenmodell

Für jede Datei wird eine Sammlung von Zeitkandidaten erzeugt.

```text
PhotoDateAnalysis
- file_id
- file_path
- photos_asset_id
- analyzed_at
- analyzer_version
- enabled_sources
- candidates[]
- comparison_result
- suggested_reference
- inconsistency_codes[]
- warnings[]
```

Ein Kandidat:

```text
PhotoDateCandidate
- source_type
- source_field
- source_detail
- raw_value
- parsed_local_datetime
- timezone_offset
- timezone_known
- normalized_utc_datetime
- precision
- confidence
- parser_id
- parse_warnings[]
```

### 6.1 `source_type`

Vorgeschlagene Werte:

```text
exif
xmp
iptc
quicktime
photos
filename
path
filesystem
```

### 6.2 Genauigkeit (`precision`)

```text
year
month
day
minute
second
subsecond
```

Quellen unterschiedlicher Genauigkeit dürfen nicht pauschal als widersprüchlich gelten.

Beispiel:

- Pfad: `2024/05`
- EXIF: `2024-05-18 14:35:22`

Das ist konsistent, obwohl die Werte nicht gleich genau sind.

---

## 7. Behandlung von Zeitzonen

Zeitzonen sind einer der wichtigsten Fehlerfälle beim Datumsvergleich.

### 7.1 Grundregel

Ein Zeitpunkt ohne Offset bleibt zunächst eine **lokale Zeit unbekannter Zeitzone**.

Es darf nicht automatisch die aktuelle NAS-Zeitzone verwendet werden.

### 7.2 Vergleich zweier Werte mit bekanntem Offset

Beide Werte werden zusätzlich nach UTC normalisiert und können exakt verglichen werden.

Beispiel:

```text
EXIF:   2024-05-18 14:35:22 +02:00
Photos: 2024-05-18 12:35:22 UTC
```

Diese Werte sind zeitlich identisch und dürfen nicht als Inkonsistenz erscheinen.

### 7.3 Vergleich mit unbekannter Zeitzone

Beispiel:

```text
EXIF:     2024-05-18 14:35:22, Offset unbekannt
Filename: 2024-05-18 14:35:22, Offset unbekannt
```

Die lokalen Werte stimmen überein. Der Befund kann als lokal konsistent gelten, aber die UTC-Zeit bleibt unbekannt.

### 7.4 Typische Zeitzonenabweichungen erkennen

Differenzen von exakt ganzen Stunden sollten gesondert klassifiziert werden, insbesondere:

```text
±1 h
±2 h
±3 h
...
```

Das ist kein automatischer Beweis für einen Zeitzonenfehler, aber ein wichtiger Hinweis.

Ebenso sind Sommer-/Winterzeit-Verschiebungen von einer Stunde als eigener Diagnosefall sinnvoll.

---

## 8. Vergleichslogik

### 8.1 Vorauswahl

Nur aktivierte Quellen nehmen am eigentlichen Konsistenzvergleich teil.

Nicht aktivierte Quellen dürfen optional weiterhin als Detailinformation angezeigt werden, beeinflussen den Status jedoch nicht.

### 8.2 Vergleich auf gemeinsamer Genauigkeit

Zwei Werte werden nur bis zur niedrigeren gemeinsamen Genauigkeit verglichen.

Beispiel:

```text
Pfad:  2024-05-18
EXIF:  2024-05-18 14:35:22
```

Ergebnis: konsistent auf Tagesebene.

### 8.3 Toleranzen

Für präzise Zeitwerte sollte eine kleine konfigurierbare Toleranz möglich sein.

Vorgeschlagene Standardwerte:

| Fall | Toleranz |
| --- | ---: |
| Sekundengenaue Metadaten | 2 Sekunden |
| Quellen ohne Sekunden | bis zum Ende der jeweiligen Minute |
| Datum ohne Uhrzeit | Vergleich nur auf Tagesebene |

Eine größere Zeitabweichung darf nicht pauschal toleriert werden.

### 8.4 Mehrheitsentscheidung

Wenn mindestens drei unabhängige Quellen vorliegen, kann eine Mehrheitsgruppe gebildet werden.

Beispiel:

```text
EXIF DateTimeOriginal   2024-05-18 14:35:22
XMP DateTimeOriginal    2024-05-18 14:35:22
Filename                2024-05-18 14:35:22
Photos                  2024-05-19 14:35:22
```

Die drei übereinstimmenden Quellen bilden einen starken Kandidaten gegen den Photos-Wert.

Eine Mehrheit ist jedoch nur ein **Vorschlag**, keine automatische Wahrheit.

### 8.5 Abhängige Quellen

Nicht jede Übereinstimmung zählt als unabhängige Bestätigung.

Beispielsweise können XMP- und EXIF-Daten durch denselben Exportvorgang synchron geschrieben worden sein. Für spätere Confidence-Berechnung sollte daher zwischen technischer Übereinstimmung und echter Quellenunabhängigkeit unterschieden werden.

---

## 9. Inkonsistenzklassen

Vorgeschlagene interne Codes:

| Code | Bedeutung |
| --- | --- |
| `date_mismatch` | Quellen unterscheiden sich im Kalenderdatum |
| `time_mismatch` | Datum gleich, Uhrzeit relevant verschieden |
| `timezone_mismatch` | Werte werden erst nach Offset-Berücksichtigung konsistent oder zeigen typisches Offset-Muster |
| `photos_mismatch` | Photos weicht von mindestens einer aktivierten Referenzquelle ab |
| `metadata_mismatch` | Metadatenfelder widersprechen einander |
| `filename_mismatch` | Dateiname widerspricht präziseren Quellen |
| `path_mismatch` | Aufnahmezeit liegt außerhalb des aus dem Pfad ableitbaren Bereichs |
| `filesystem_mismatch` | optionale Dateisystemzeit weicht auffällig ab |
| `missing_primary_date` | kein belastbares primäres Aufnahmedatum vorhanden |
| `ambiguous_date` | mehrere plausible Zeitgruppen ohne klaren Favoriten |
| `precision_only_difference` | Unterschied entsteht nur durch verschiedene Genauigkeit; kein echter Fehler |
| `parse_warning` | Datumsquelle erkannt, aber nicht sicher interpretierbar |

`precision_only_difference` sollte standardmäßig nicht in der Inkonsistenzliste erscheinen.

---

## 10. Bewertung der Quellen

Die Anwendung sollte keine unveränderliche globale Wahrheitshierarchie fest einprogrammieren. Für sinnvolle Vorschläge ist dennoch eine Standardgewichtung hilfreich.

Empfohlene initiale Reihenfolge:

1. `EXIF:DateTimeOriginal` mit `OffsetTimeOriginal`
2. `EXIF:DateTimeOriginal` ohne Offset
3. XMP `DateTimeOriginal`
4. Photos-Aufnahmedatum
5. geeignete QuickTime-Aufnahmedaten
6. EXIF/XMP `CreateDate`
7. präzise Dateinamensmuster
8. vollständiges Datum aus dem Pfad
9. ungenaue Pfadangaben
10. Dateisystemzeiten
11. `ModifyDate`

Diese Reihenfolge ist lediglich ein Default für Vorschläge und muss konfigurierbar bzw. durch Regeln übersteuerbar sein.

---

## 11. Auswahl der Quellen

In der Konfiguration bzw. Oberfläche sollte mindestens folgende Auswahl möglich sein:

```text
[x] EXIF DateTimeOriginal
[x] EXIF CreateDate
[x] XMP
[ ] IPTC
[x] Synology Photos
[x] Dateiname
[x] Verzeichnispfad
[ ] Dateisystemzeiten
```

Optional kann zwischen zwei Eigenschaften unterschieden werden:

- **Quelle lesen und anzeigen**
- **Quelle für Konsistenzprüfung verwenden**

Damit kann z. B. `mtime` sichtbar bleiben, ohne einen Widerspruch auszulösen.

---

## 12. Erster Umsetzungsschritt: reine Analyse

### 12.1 Pipeline

```text
Datei / Photos-Asset
  -> Dateikontext ermitteln
  -> aktivierte Metadaten lesen
  -> Photos-Aufnahmezeit lesen
  -> Dateinamen analysieren
  -> Pfad analysieren
  -> optionale Dateisystemzeiten lesen
  -> alle Kandidaten normalisieren
  -> Genauigkeit und Zeitzone bestimmen
  -> Kandidaten vergleichen
  -> Inkonsistenzen klassifizieren
  -> Referenzkandidat nur vorschlagen
  -> Ergebnis speichern / anzeigen
```

### 12.2 Keine Schreiboperation

In dieser Phase sind ausdrücklich nicht erlaubt:

- Änderung von EXIF/XMP/IPTC-Daten
- Umbenennen der Datei
- Verschieben der Datei
- Änderung des Photos-Aufnahmedatums
- Änderung von Dateisystemzeiten

---

## 13. Oberfläche

### 13.1 Standardansicht

Die Standardansicht zeigt nur Dateien mit Inkonsistenzen.

Empfohlene Spalten:

| Spalte | Inhalt |
| --- | --- |
| Datei | Dateiname |
| Pfad | Verzeichnis |
| Photos | Aufnahmezeit in Synology Photos |
| EXIF | bevorzugter EXIF-Aufnahmezeitpunkt |
| XMP | bevorzugter XMP-Zeitpunkt |
| Dateiname | daraus erkannter Kandidat |
| Pfad | daraus erkannter Datumsbereich/Kandidat |
| Differenz | wichtigste Abweichung |
| Befund | Inkonsistenzklasse |
| Vorschlag | aktuell plausibelster Referenzwert |
| Sicherheit | Confidence des Vorschlags |

### 13.2 Filter

Mindestens:

- nur Inkonsistenzen / alle Dateien
- Inkonsistenzklasse
- betroffene Quelle
- Differenzgröße
- Jahr / Zeitraum
- Pfad
- mit / ohne eindeutigen Vorschlag
- mit / ohne bekannte Zeitzone

### 13.3 Detailansicht

Für eine Datei:

```text
Synology Photos
  2024-05-19 14:35:22

EXIF:DateTimeOriginal
  2024-05-18 14:35:22

EXIF:OffsetTimeOriginal
  +02:00

XMP:DateTimeOriginal
  2024-05-18 14:35:22+02:00

Dateiname
  IMG_20240518_143522.jpg
  -> 2024-05-18 14:35:22

Pfad
  /photos/2024/05/18/
  -> 2024-05-18

Bewertung
  Photos weicht um +1 Tag ab.
  EXIF, XMP, Dateiname und Pfad sind konsistent.

Vorschlag
  2024-05-18 14:35:22 +02:00
```

Die Rohwerte müssen für Diagnosezwecke einsehbar bleiben.

---

## 14. Konfigurierbare Dateinamen- und Pfadregeln

Die Parser dürfen nicht nur aus fest verdrahteten Heuristiken bestehen.

Vorgeschlagenes Regelmodell:

```text
DatePatternRule
- id
- enabled
- source: filename | path_segment | full_path
- regex
- datetime_format
- precision
- timezone_mode
- priority
- examples[]
```

Beispiel:

```text
regex:
  ^IMG_(?<date>\d{8})_(?<time>\d{6})

format:
  yyyyMMdd HHmmss
```

Pfadregeln können Segmentgrenzen berücksichtigen, damit beliebige Zahlenfolgen in anderen Verzeichnisnamen nicht versehentlich als Datum interpretiert werden.

---

## 15. Confidence-Modell

Für den vorgeschlagenen Referenzwert sollte eine nachvollziehbare Confidence berechnet werden.

Mögliche Faktoren:

### Positive Faktoren

- `DateTimeOriginal` vorhanden
- passender Zeitzonenoffset vorhanden
- mehrere Quellen stimmen sekundengenau überein
- Dateiname bestätigt denselben Zeitpunkt
- Pfad bestätigt zumindest dasselbe Datum
- Photos stimmt überein

### Negative Faktoren

- mehrere Metadatenfelder widersprechen sich
- keine Zeitzone bekannt
- nur Dateisystemzeiten vorhanden
- Dateiname durch generisches Muster erkannt
- mehrere gleich plausible Kandidaten
- Zeit liegt außerhalb des durch Pfad vorgegebenen Bereichs

Vorgeschlagene Klassen:

```text
high
medium
low
ambiguous
```

Die konkrete Punktelogik sollte erst nach Tests mit realen Beständen festgelegt werden.

---

## 16. Spätere Ausbaustufe: Bereinigung

Nach Stabilisierung der lesenden Analyse kann ein zweiter Modus eingeführt werden.

### 16.1 Mögliche Ziele

Pro Vorgang muss festgelegt werden, welche Ziele verändert werden dürfen:

```text
[ ] Synology Photos
[ ] EXIF/XMP in der Datei
[ ] Dateisystemzeit
[ ] Dateiname
[ ] Verzeichnispfad
```

Für die erste schreibende Ausbaustufe wird empfohlen, nur folgende Ziele zuzulassen:

1. Synology Photos
2. standardisierte Aufnahmefelder in der Bilddatei

Umbenennen, Verschieben und Dateisystemzeiten sollten getrennte spätere Funktionen bleiben.

### 16.2 Manuelle Bereinigung

Der Benutzer markiert eine oder mehrere Dateien und wählt explizit:

- welchen Quellwert er als korrekt ansieht
- welche Zielsysteme geändert werden sollen

Beispiel:

```text
Referenz: EXIF DateTimeOriginal
Ziele:
  [x] Synology Photos
  [ ] Bilddatei
```

### 16.3 Regelbasierte Bereinigung

Später können Regeln definiert werden.

Beispiele:

```text
WENN
  EXIF DateTimeOriginal vorhanden
  UND Photos um genau 24 Stunden abweicht
  UND Dateiname und EXIF übereinstimmen
DANN
  Photos auf EXIF setzen
```

```text
WENN
  Photos, Dateiname und Pfad übereinstimmen
  UND EXIF DateTimeOriginal fehlt
DANN
  DateTimeOriginal in Datei setzen
```

```text
WENN
  EXIF und Photos exakt 2 Stunden auseinanderliegen
  UND EXIF keinen Offset besitzt
DANN
  nur als Zeitzonenverdacht anzeigen
  NICHT automatisch schreiben
```

### 16.4 Regelmodell

```text
PhotoDateCorrectionRule
- id
- name
- enabled
- priority
- conditions[]
- reference_source
- target_sources[]
- required_confidence
- dry_run_required
- allow_batch
```

---

## 17. Vorschau und Sicherheitsmodell für Schreiboperationen

Vor jeder Änderung muss ein Dry-Run erzeugt werden.

Beispiel:

| Datei | Ziel | Alt | Neu | Referenz | Regel |
| --- | --- | --- | --- | --- | --- |
| IMG_1234.jpg | Photos | 2024-05-19 14:35:22 | 2024-05-18 14:35:22 | EXIF | photos_from_exif |
| IMG_5678.jpg | Datei/EXIF | leer | 2023-08-02 09:14:10 | Photos | exif_from_photos |

Schreiboperationen dürfen erst nach expliziter Bestätigung ausgeführt werden.

Für Batch-Aktionen sollten zusätzliche Grenzwerte vorgesehen werden, z. B.:

- maximale Anzahl Dateien pro Lauf
- nur `high` Confidence
- keine `ambiguous`-Fälle
- keine Datei mit Parserwarnung

---

## 18. Audit und Wiederherstellung

Jede spätere Änderung benötigt einen Audit-Eintrag:

```text
PhotoDateChangeAudit
- file_id
- file_path
- photos_asset_id
- changed_at
- actor
- rule_id
- reference_source
- reference_value
- target
- old_value
- new_value
- write_result
- backup_reference
```

Für Dateimetadaten sollte vor Änderungen mindestens eine der folgenden Strategien verwendet werden:

- ExifTool-Backupdatei kontrolliert erhalten
- Metadaten-Snapshot in der AV_ImgData-Datenbank speichern
- vollständige Originaldatei über vorhandene Backupstrategie absichern

Für Photos-Änderungen muss der vorherige Photos-Wert im Audit stehen, damit ein Rücksetzen möglich bleibt, soweit die eingesetzte Photos-Schnittstelle dies erlaubt.

---

## 19. Umgang mit Sonderfällen

### 19.1 Scans

Gescannten Fotos fehlt häufig ein technisch echtes `DateTimeOriginal`. Ein bewusst gepflegtes Datum aus Photos, Dateiname oder Pfad kann fachlich korrekter sein als das Scanner-Erstellungsdatum.

Solche Dateien sollten später über Regeln oder Dateigruppen als Scan-Bestand klassifizierbar sein.

### 19.2 Screenshots

Screenshots besitzen meist ein technisches Erstellungsdatum, aber keinen klassischen Kamera-Aufnahmezeitpunkt. Dateiname und Metadaten können hier eine andere Gewichtung erhalten.

### 19.3 Bearbeitete oder exportierte Dateien

Bildbearbeitungsprogramme können `CreateDate`, `ModifyDate`, XMP-Felder und Dateisystemzeiten verändern. `DateTimeOriginal` sollte daher getrennt von Export-/Änderungszeiten bewertet werden.

### 19.4 RAW + Sidecar

Bei RAW-Dateien kann eine `.xmp`-Sidecar-Datei zusätzliche oder überschreibende Datumsinformationen enthalten. Sidecars sollten als eigene Quelle modelliert werden, damit RAW und Sidecar nicht undurchsichtig vermischt werden.

### 19.5 Live Photos

Foto und zugehöriges Video können getrennte Containerzeiten besitzen. Sie sollten als zusammengehörige Assets erkannt und auf grobe zeitliche Konsistenz geprüft werden.

### 19.6 Historische Fotos ohne Uhrzeit

Ein manuell gepflegtes Datum wie `1978-06-01` darf nicht künstlich auf `00:00:00` präzisiert werden. Intern muss die Genauigkeit `day` erhalten bleiben.

---

## 20. Persistenz der Analyseergebnisse

Die Ergebnisse sollten persistiert werden, damit große Bestände nicht bei jeder UI-Abfrage vollständig neu analysiert werden müssen.

Vorgeschlagene Schlüssel für Invalidierung:

```text
- file path
- file size
- mtime
- optional content hash
- Photos asset version / last modified, soweit verfügbar
- analyzer version
- pattern configuration version
```

Eine erneute Analyse ist erforderlich, wenn sich eine relevante Quelle oder Parserkonfiguration geändert hat.

---

## 21. Statusintegration

Dieses Konzept soll keinen parallelen globalen Statusmechanismus erzeugen.

Empfohlen ist ein eigener Analysebefund innerhalb des bestehenden Check-/Statusmodells:

```text
consistent
inconsistent
ambiguous
insufficient_data
parse_error
```

Ob daraus sichtbare Statuswerte werden oder bestehende Status wiederverwendet werden, muss mit dem vorhandenen Status-Konzept abgestimmt werden.

Die Standardliste der Funktion filtert auf:

```text
inconsistent
ambiguous
parse_error
```

`consistent` wird nur bei expliziter Auswahl „alle anzeigen“ eingeblendet.

---

## 22. Konfiguration

Vorgeschlagener grober Konfigurationsbereich:

```json
{
  "photo_datetime_check": {
    "enabled": true,
    "show_only_inconsistencies": true,
    "sources": {
      "exif_datetime_original": true,
      "exif_create_date": true,
      "xmp": true,
      "iptc": false,
      "photos": true,
      "filename": true,
      "path": true,
      "filesystem": false
    },
    "comparison": {
      "second_tolerance": 2,
      "detect_hour_offset_patterns": true
    }
  }
}
```

Die konkrete Einordnung in die bestehende Konfigurationsstruktur muss bei der Implementierung anhand der vorhandenen Config-Konventionen erfolgen.

---

## 23. Teststrategie

### 23.1 Parser-Tests

Testfälle mindestens für:

- EXIF mit und ohne Offset
- XMP mit ISO-8601-Offset
- Subsekunden
- fehlende Sekunden
- ungültige Metadaten
- mehrere gleichnamige Felder aus verschiedenen Gruppen
- QuickTime UTC-Zeiten
- verschiedene Dateinamenmuster
- Pfade mit Jahr, Monat und Datum
- Zahlen im Pfad, die kein Datum sind

### 23.2 Vergleichstests

Mindestens:

- exakt identische Werte
- Werte mit gleicher UTC-Zeit und verschiedenen Offsets
- gleiche lokale Zeit ohne Zeitzone
- Abweichung um 1 Sekunde innerhalb Toleranz
- Abweichung um 1 Stunde
- Abweichung um 1 Tag
- nur unterschiedliche Genauigkeit
- drei Quellen gegen eine Quelle
- zwei gleich starke widersprüchliche Gruppen

### 23.3 Integrationstests mit Photos

Mindestens:

- Photos stimmt mit EXIF überein
- Photos weicht von EXIF ab
- Photos enthält Wert, Datei enthält keinen Aufnahmezeitpunkt
- Datei enthält Wert, Photos nicht oder nicht lesbar
- spätere Dry-Run-Vorschau ohne tatsächliche Änderung

---

## 24. Empfohlene Umsetzungsschritte

### Phase 1 – Datenaufnahme

- neutrales Kandidatenmodell definieren
- EXIF/XMP/QuickTime-Datumsfelder zentral lesen
- Photos-Aufnahmezeit lesend anbinden
- Dateinamenparser implementieren
- Pfadparser implementieren
- Quellenkonfiguration ergänzen

### Phase 2 – Konsistenzanalyse

- Präzisionsmodell implementieren
- Zeitzonenlogik implementieren
- Toleranzen implementieren
- Inkonsistenzklassen ableiten
- Confidence und Referenzvorschlag erzeugen
- Analyseergebnisse persistieren

### Phase 3 – UI

- standardmäßig nur Inkonsistenzen anzeigen
- Quellenfilter
- Detailansicht aller Rohwerte
- Differenz und Diagnose verständlich darstellen
- vorgeschlagenen Referenzwert anzeigen

### Phase 4 – Dry-Run für Bereinigung

- manuelle Referenzauswahl
- Zielauswahl Photos / Datei
- Änderungsplan erzeugen
- noch keine oder nur explizit bestätigte Einzeländerungen

### Phase 5 – Regelbasierte Bereinigung

- Regelmodell
- Batch-Dry-Run
- Confidence-Grenzen
- Schreibadapter für Photos
- Schreibadapter für EXIF/XMP
- Audit und Rücksetzlogik

---

## 25. Offene technische Punkte vor der Implementierung

Vor der konkreten Umsetzung müssen im bestehenden Code insbesondere folgende Punkte verifiziert werden:

1. Über welchen vorhandenen Adapter bzw. Datenbankzugriff der aktuelle Aufnahmezeitpunkt aus Synology Photos zuverlässig gelesen werden kann.
2. In welcher Einheit und Zeitzoneninterpretation Photos diesen Wert intern speichert.
3. Ob Photos beim Ändern des Aufnahmezeitpunkts ausschließlich seine Datenbank aktualisiert oder unter bestimmten Bedingungen Metadaten der Datei beeinflusst.
4. Welche vorhandene zentrale ExifTool-Schicht für den neuen Check wiederverwendet werden kann.
5. Wo Analysebefunde im vorhandenen Status-/Checkmodell am besten persistiert werden.
6. Wie RAW/Sidecar- und Live-Photo-Zuordnungen im vorhandenen Datenmodell bereits repräsentiert sind.

---

## 26. Kurzfassung des Zielverhaltens

Die Funktion soll zunächst folgende Frage beantworten:

> **„Welche Fotos besitzen bezüglich ihres Aufnahmezeitpunkts widersprüchliche Angaben, und welche Quelle spricht mit welcher Sicherheit für welchen Zeitpunkt?“**

Erst wenn diese Analyse zuverlässig ist, folgt die zweite Frage:

> **„Welche dieser Abweichungen dürfen nach welchen Regeln in Synology Photos und/oder in den Dateien korrigiert werden?“**

Damit bleiben Erkennung, Entscheidung und Änderung technisch und fachlich sauber voneinander getrennt.
