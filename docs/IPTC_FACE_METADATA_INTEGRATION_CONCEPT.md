# Konzept: Integration von Gesichtsdaten aus und in IPTC/XMP-Metadaten

## 1. Ziel

`AV_ImgData` soll Gesichtsdaten aus Bildmetadaten erkennen, normalisieren und kontrolliert in die bestehenden Analyse-, Status- und Guide-Workflows einbinden. Der erste grosse Umsetzungsschritt ist **rein lesend**: Beim Analyse-Lauf sollen vorhandene Gesichtsdaten in IPTC/XMP-Metadaten erkannt, bewertet und in den vorhandenen Statusfluss ueberfuehrt werden.

Schreibende Funktionen in Bilddateien sind spaetere Ausbaustufen und duerfen erst umgesetzt werden, wenn die lesende Erkennung, Statusabbildung, UI-Darstellung und Tests stabil sind.

## 2. Einordnung in die bestehende Dokumentation

Dieses Konzept ist **kein Ersatz** fuer das vorhandene Status-Konzept und **kein alternativer Benutzer-Guide**. Es erweitert beide Dokumente fachlich um den Metadatenbereich.

Verbindliche Einordnung:

1. Das bestehende Status-Konzept unter `docs` bleibt fuehrend fuer Statusnamen, Statusuebergaenge, Anzeigegruppen und erlaubte Aktionen.
2. Der vorhandene Guide unter `docs` bleibt fuehrend fuer Benutzerfuehrung, Reihenfolge der Arbeitsschritte und Begriffe in der Oberflaeche.
3. Dieses Konzept fuehrt nur dort neue interne Detailzustande ein, wo Gesichtsdaten aus Metadaten technisch genauer klassifiziert werden muessen.
4. Neue Status duerfen nicht parallel zum Status-Konzept entstehen. Wenn ein neuer sichtbarer Zustand benoetigt wird, muss zuerst das Status-Konzept erweitert werden.
5. Der erste Implementierungsschritt darf vorhandene Checks, Statusfilter und Guide-Schritte nicht umgehen.

Daraus folgt: Metadaten-Gesichter werden nicht als eigener Sonderworkflow neben dem aktuellen Check-/Statusmodell behandelt, sondern als zusaetzliche Eingangsquelle fuer vorhandene Analyse- und Entscheidungsprozesse.

## 3. Begriffsklaerung

Im Projektkontext wird haeufig von IPTC-Metadaten gesprochen. Fuer Gesichtsdaten ist technisch vor allem XMP relevant.

- Klassische IPTC/IIM-Felder koennen Personen indirekt als Keywords oder Beschreibungen enthalten, aber keine belastbaren Gesichtsregionen.
- IPTC Core in XMP ist fuer klassische beschreibende Felder relevant.
- IPTC Extension in XMP kann strukturierte Bildregionen und Personeninformationen tragen.
- MWG Regions und herstellerspezifische XMP-Namensraeume koennen ebenfalls Gesichtsrechtecke enthalten.

Das Konzept verwendet deshalb den Begriff **IPTC/XMP**, wenn strukturierte Gesichtsregionen gemeint sind.

## 4. Leitprinzipien

- Nicht raten: Unsichere Metadaten werden als unsicher gekennzeichnet, nicht automatisch als valide uebernommen.
- Lesen vor Schreiben: Der erste Schritt veraendert weder Bilddateien noch Synology Photos.
- Status-Konzept vor Detailmodell: Interne Detailflags duerfen sichtbare Status nicht ersetzen.
- Guide vor Sonderlogik: Benutzeraktionen muessen in die bestehende Anleitung und UI-Logik passen.
- Nachvollziehbarkeit: Jede erkannte Region muss Quelle, Rohdaten, Parser, Warnungen und Normalisierung zeigen koennen.
- Idempotenz: Wiederholte Analyse derselben Datei darf keine doppelten Aufgaben erzeugen.
- Datenschutz: Gesichtsdaten sind personenbezogene Daten; keine stille Rueckschreibung in Dateien.

## 5. Erster grosser Schritt: Erkennung beim Analyse-Lauf

### 5.1 Ziel

Beim Analyse-Lauf soll fuer jede relevante Bilddatei festgestellt werden:

1. Gibt es strukturierte Gesichtsregionen in IPTC/XMP oder verwandten XMP-Schemata?
2. Aus welchem Schema stammen sie?
3. Sind Koordinaten, Bildbezug und Orientierung plausibel?
4. Gibt es Name, Identifier, Rolle oder Beschreibung?
5. Fuehrt der Fund zu einer vorhandenen Check-Aufgabe?
6. Muss ein vorhandener Status gesetzt, bestaetigt oder ausgeschlossen werden?
7. Ist der Fund nur ein Hinweis, aber keine matchbare Gesichtsregion?

Das Ergebnis ist ein Analysebefund, der in den vorhandenen Status- und Checkfluss eingespeist wird.

### 5.2 Analyse-Pipeline

```text
Bilddatei
  -> Dateikontext ermitteln
  -> ExifTool JSON lesen
  -> Metadatenquellen erkennen
  -> Regionskandidaten parsen
  -> Koordinaten normalisieren
  -> Personendaten normalisieren
  -> Plausibilitaet pruefen
  -> Duplikate gruppieren
  -> Status gemaess bestehendem Status-Konzept ableiten
  -> Check-/Guide-kompatible Ausgabe erzeugen
```

### 5.3 ExifTool-Lesemodus

Empfohlener Basismodus:

```bash
exiftool -json -G1 -a -struct -n <file>
```

Begruendung:

- `-json` liefert maschinenlesbare Daten.
- `-G1` erhaelt Gruppeninformationen.
- `-a` verhindert, dass mehrfach vorhandene Felder verschluckt werden.
- `-struct` ist fuer XMP-Strukturen wichtig.
- `-n` vermeidet formatierte oder lokalisierte Zahlenwerte.

Der ExifTool-Zugriff soll zentral gekapselt werden, damit Analyse, Tests und spaetere Schreibpfade dieselbe Sicht auf Metadaten nutzen.

## 6. Zu erkennende Metadatenquellen

Prioritaet fuer den ersten lesenden Schritt:

| Prioritaet | Quelle | Rolle im Konzept |
| --- | --- | --- |
| P1 | IPTC Extension Image Region | Zielnahes Standardschema fuer strukturierte Regionen |
| P1 | MWG Regions / `mwg-rs` | breite Kompatibilitaet mit bestehenden Face-Regionen |
| P2 | ACDSee-spezifische XMP-Felder | Import aus vorhandenen ACDSee-Bestaenden |
| P2 | Microsoft/Windows Photo XMP | Altbestaende aus privaten Archiven |
| P3 | PersonInImage, Keywords, Beschreibung | Personenerwaehnung, aber keine Gesichtsregion |
| P3 | Sidecar-XMP | spaeterer Ausbau, insbesondere fuer RAW-Dateien |

Wichtig: Ein Name ohne Region ist keine erkannte Gesichtsflaeche. Er darf als Hinweis gespeichert werden, aber nicht als Gesicht in den Matching-Status gelangen.

## 7. Internes neutrales Datenmodell

Die Parser sollen unterschiedliche Metadatenformate in ein neutrales Modell ueberfuehren. Dieses Modell ist technisches Zwischenmodell und darf das vorhandene Status-Konzept nicht ersetzen.

```text
MetadataFaceRegion
- file_id / file_path
- source_schema
- source_group
- source_index
- parser_id
- parser_version
- region_shape
- region_unit
- source_x
- source_y
- source_w
- source_h
- normalized_left
- normalized_top
- normalized_width
- normalized_height
- image_width_at_read_time
- image_height_at_read_time
- orientation_at_read_time
- person_name_raw
- person_name_normalized
- person_identifier
- person_role
- person_description
- technical_quality
- status_bridge
- ignore_reason
- parse_warnings
- raw_metadata_json
- fingerprint
```

### 7.1 Technische Qualitaetsklassen

Diese Klassen sind interne Analysequalitaeten, keine zwingend sichtbaren UI-Status:

| Klasse | Bedeutung | Matchbar |
| --- | --- | --- |
| `valid_named_region` | Region und Name plausibel | ja |
| `valid_unnamed_region` | Region plausibel, kein Name | nein, aber sichtbar |
| `named_without_region` | Name vorhanden, keine Region | nein, nur Hinweis |
| `invalid_region` | Region geometrisch unbrauchbar | nein |
| `unsupported_region` | Struktur erkannt, Parser reicht nicht aus | nein |
| `duplicate_region` | Region ist Duplikat einer bevorzugten Quelle | nicht separat |
| `ignored_region` | Region ist bekannt, aber bewusst nicht relevant | nein |

### 7.2 Bruecke zum Status-Konzept

Das Feld `status_bridge` darf keine neuen sichtbaren Status frei definieren. Es muss auf vorhandene Status aus dem Status-Konzept abbilden.

Empfohlenes Abbildungsprinzip:

| Technischer Befund | Statuswirkung |
| --- | --- |
| valide Region mit eindeutigem Namen | vorhandener offener Matching-/Pruefstatus |
| valide Region ohne Namen | vorhandener Informations- oder Pruefstatus, nicht automatisch matchbar |
| Name ohne Region | Hinweisstatus, nicht Gesichtsmatching |
| ungueltige Region | Fehler-/Warnstatus gemaess Status-Konzept |
| ignorierte Region | vorhandener Ignoriert-/Erledigt-/Ausgeschlossen-Status, sofern definiert |
| Duplikat aus mehreren Quellen | keine neue Aufgabe; Verweis auf bevorzugte Region |

Falls das Status-Konzept keinen passenden sichtbaren Status enthaelt, muss das Status-Konzept erweitert werden. Dieses Konzept darf dann nur den Bedarf beschreiben, nicht eigenstaendig einen neuen UI-Status einfuehren.

## 8. Parser-Verhalten

Jede Metadatenquelle wird ueber einen eigenen Parser behandelt.

```text
MetadataRegionParser
- parser_id
- parser_version
- supports(metadata_json) -> bool
- parse(metadata_json, file_context) -> list[MetadataFaceRegionCandidate]
```

Parserregeln:

- Keine stillen Verwerfungen.
- Unvollstaendige Funde werden mit Warnung gespeichert.
- Ungueltige Geometrie wird gespeichert, aber nicht gematcht.
- Unbekannte Einheiten verhindern automatische Zuordnung.
- Rohdaten werden fuer Debugging und Regressionstests gekapselt gespeichert.
- Parser-Versionen muessen Cache-Invalidierung ermoeglichen.

## 9. Koordinaten-Normalisierung

Alle Regionen werden intern auf normalisierte Koordinaten bezogen:

```text
0.0 <= left   <= 1.0
0.0 <= top    <= 1.0
0.0 <  width  <= 1.0
0.0 <  height <= 1.0
```

Zu speichern sind immer:

- Originalkoordinaten,
- erkannte Einheit,
- Bildbreite und Bildhoehe,
- EXIF Orientation,
- Normalisierungsergebnis,
- Warnungen.

Wenn Orientierung oder Einheit nicht sicher interpretierbar sind, darf keine automatische Zuordnung zu Synology Photos erfolgen.

## 10. Deduplizierung und Quellprioritaet

Mehrere Programme schreiben dieselben Gesichter in unterschiedliche XMP-Namensraeume. Die Analyse muss diese Funde gruppieren.

Kriterien:

- gleiche Datei,
- identischer oder normalisiert gleicher Name,
- stark ueberlappende Rechtecke,
- gleicher Identifier,
- bekannte Spiegelung zwischen Schemata.

Prioritaet bei gleicher Region:

1. IPTC Extension mit vollstaendiger Struktur,
2. MWG Region mit vollstaendiger Struktur,
3. herstellerspezifische XMP-Region,
4. sonstige strukturierte Region.

Duplikate erzeugen keine eigenen offenen Aufgaben im Statusfluss. Sie bleiben aber in der Detailansicht nachvollziehbar.

## 11. Ignorieren uninteressanter Gesichter

Das Projekt benoetigt eine Moeglichkeit, Gesichter als bekannt aber uninteressant zu behandeln. Dies muss mit dem vorhandenen Status-Konzept kompatibel sein.

### 11.1 Interne Gruende

`ignore_reason` kann technische oder fachliche Gruende enthalten:

```text
background_person
stranger
poster_or_artwork
duplicate
false_positive
too_small
no_action_needed
user_ignored
```

Diese Gruende sind keine eigenstaendigen UI-Status. Sie ergaenzen den im Status-Konzept vorgesehenen Status fuer ignorierte, ausgeschlossene oder erledigte Funde.

### 11.2 Wirkung auf den Guide

Der Guide soll fuer den Benutzer klar beschreiben:

- wie ein Metadaten-Gesicht ignoriert wird,
- dass ignorierte Gesichter nicht mehr in der Standardliste offener Aufgaben erscheinen,
- dass sie in Detail-/Filteransichten weiterhin sichtbar bleiben,
- wie eine Ignorierung aufgehoben wird,
- dass im ersten Schritt keine Datei-Metadaten geschrieben werden.

### 11.3 Metadatenbasierter Ignorierstatus

Ein standardisierter IPTC-Wert fuer „dieses Gesicht nicht wieder vorschlagen“ darf nicht angenommen werden. Fuer spaetere Schreibpfade kann eine optionale AV_ImgData-XMP-Erweiterung geprueft werden, z. B.:

```text
avimg:RegionIntent = "ignored"
avimg:IgnoreReason = "background_person"
avimg:IgnoreVersion = "1"
```

Diese Erweiterung waere proprietaer, abschaltbar und erst nach gesonderter Entscheidung zulaessig.

## 12. Matching gegen Synology Photos

Die Metadatenanalyse erzeugt Kandidaten, aber keine automatische Photos-Aenderung.

Eingaben:

- normalisierter Name,
- optionaler Identifier,
- normalisierte Metadatenregion,
- vorhandene Synology-Photos-Gesichter zur Datei,
- bekannte Namensmappings,
- bisherige Benutzerentscheidungen,
- aktueller Status gemaess Status-Konzept.

Match-Typen:

```text
name_exact
name_mapping
region_overlap
name_and_region
identifier_match
ambiguous
no_match
```

Automatische Aktionen duerfen nur erfolgen, wenn das Status-Konzept und der Guide dafuer einen ausdruecklichen Pfad vorsehen. Ambigue Treffer bleiben Benutzerentscheidungen.

## 13. UI-/Guide-Integration

Die UI soll Metadaten-Gesichter in vorhandene Check- und Statusansichten integrieren.

Empfohlene Filter, sofern mit dem Status-Konzept vereinbar:

```text
Alle Metadaten-Gesichter
Offen / pruefbar
Matchbar
Ohne Name
Ohne Region
Ungueltig
Ignoriert
Doppelte Quellen
```

Die Detailansicht pro Datei soll zeigen:

- Bildvorschau mit Metadatenrechtecken,
- Synology-Photos-Gesichter, falls vorhanden,
- Ueberlappung zwischen beiden Quellen,
- Quellschema,
- Rohname und normalisierter Name,
- Rolle und Identifier,
- Parserwarnungen,
- aktueller Status gemaess Status-Konzept,
- Aktionen gemaess Guide.

Im ersten Schritt erlaubte Aktionen:

- ignorieren,
- Ignorierung aufheben,
- Namensmapping anlegen,
- Fund als falsch erkannt markieren,
- Rohdaten anzeigen,
- Analyse fuer Datei wiederholen.

Nicht erlaubt im ersten Schritt:

- Bilddatei schreiben,
- XMP-Region loeschen,
- Synology Photos automatisch aendern,
- neue proprietaere XMP-Felder erzeugen.

## 14. Persistenz

Empfohlene Tabellen oder Persistenzobjekte:

```text
metadata_face_region
metadata_face_region_group
metadata_person_mention
metadata_parse_warning
metadata_ignore_rule
metadata_status_projection
metadata_write_journal
```

`metadata_status_projection` dient als Bruecke zum bestehenden Statusmodell. Es speichert nicht beliebige neue Status, sondern die Ableitung aus technischem Befund auf den im Status-Konzept definierten Zustand.

## 15. Schreibende Integration als spaetere Phase

Schreiben in IPTC/XMP ist nicht Teil des ersten grossen Schritts.

Spaetere Ziele:

1. Synology-Photos-Gesichter als XMP-Regionen schreiben.
2. Benutzerkorrekturen als Metadaten persistieren.
3. Ignorierinformationen optional als AV_ImgData-Erweiterung schreiben.
4. veraltete Regionen kontrolliert entfernen.
5. Schreibpreview und Journal bereitstellen.

Regeln:

- kein Schreiben ohne Preview,
- kein Schreiben ohne Backup- oder Journalstrategie,
- keine Aenderung fremder IPTC-Felder ausserhalb des Zielbereichs,
- kein Duplikatschreiben,
- nach jedem Schreibvorgang erneutes Lesen und Validieren.

## 16. Teststrategie

Fixtures:

1. gueltige IPTC-Extension-Region mit Name,
2. gueltige MWG-Region mit Name,
3. Region ohne Name,
4. Name ohne Region,
5. mehrere Gesichter in einer Datei,
6. doppelte Region in zwei Schemata,
7. Region ausserhalb des Bilds,
8. gedrehtes Bild mit EXIF Orientation,
9. ACDSee-spezifischer Bestand,
10. ignorierte Region,
11. unbekanntes strukturiertes XMP,
12. defektes ExifTool-JSON.

Unit-Tests:

- Parser erkennt erwartete Kandidaten.
- Koordinaten werden korrekt normalisiert.
- ungueltige Regionen bleiben sichtbar.
- Deduplizierung gruppiert erwartete Duplikate.
- Fingerprints bleiben stabil.
- Parser-Versionen invalidieren Caches.
- Ignorierregeln greifen nach Reanalyse.
- technische Befunde werden auf vorhandene Status abgebildet.

Integrationstests:

- Analyse erzeugt erwartete Persistenzobjekte.
- UI/API trennt matchbare, ungueltige, ignorierte und hinweisartige Funde.
- bestehende Check- und Status-Workflows bleiben kompatibel.
- Guide-Schritte koennen ohne Sonderpfad durchlaufen werden.

## 17. Rollout

### Phase 1: Lesende Erkennung

- ExifTool-Reader zentralisieren.
- Parser-Interface einfuehren.
- IPTC-Extension- und MWG-Parser implementieren.
- neutrales Regionenmodell persistieren.
- Statusabbildung an bestehendes Status-Konzept anbinden.
- UI-/API-Ausgabe in bestehende Checks integrieren.
- Tests mit JSON-Fixtures einfuehren.

### Phase 2: Matching-Vertiefung

- Region-Overlap gegen Synology Photos berechnen.
- Namensmappings in Bewertung einbeziehen.
- Duplikatgruppen in Checks verwenden.
- Ignorierstatus in Standardlisten beruecksichtigen.

### Phase 3: Guide- und Kompatibilitaetserweiterung

- Guide um Metadaten-Gesichter, Ignorieren und Reanalyse erweitern.
- ACDSee-/Microsoft-Parser ergaenzen.
- reale Archivfaelle als anonymisierte Fixtures aufnehmen.

### Phase 4: Kontrolliertes Schreiben

- Schreibpreview,
- Journal,
- Backupstrategie,
- Re-Read-Validierung,
- optionale XMP-Erweiterungen.

## 18. Akzeptanzkriterien fuer den ersten Schritt

- Strukturierte Gesichtsdaten aus IPTC Extension und MWG werden erkannt.
- Jeder Fund zeigt Quelle, Koordinaten, Name, technische Qualitaet und Warnungen.
- Der sichtbare Zustand wird aus dem bestehenden Status-Konzept abgeleitet.
- Der Guide kann den Workflow ohne separaten Sonderprozess beschreiben.
- Ignorierte Gesichter erscheinen nicht mehr als offene Standardaufgabe.
- Reanalyse erkennt dieselben Gesichter stabil wieder.
- Ungueltige und unvollstaendige Funde bleiben nachvollziehbar.
- Es findet kein schreibender Zugriff auf Bilddateien statt.
- Bestehende Check-, Status- und Matching-Workflows werden nicht verschlechtert.

## 19. Offene Punkte

Diese Punkte muessen anhand der aktuellen `docs`-Dokumente und Testsysteme konkretisiert werden:

1. exakte Statusnamen und erlaubte Statusuebergaenge aus dem Status-Konzept,
2. konkrete Guide-Kapitel, in denen Metadaten-Gesichter ergaenzt werden,
3. genaue Synology-Photos-Datenquelle fuer Face-Boxen,
4. Stabilitaet von Photos-Face-IDs ueber Reindex und Updates,
5. konkrete ACDSee-XMP-Strukturen aus realen Dateien,
6. Sidecar-Strategie fuer RAW-Dateien,
7. erlaubte Schreibformate fuer spaetere Phasen,
8. Umgang mit Widerspruechen zwischen internem Ignorierstatus und Datei-Metadaten.

Diese Punkte werden nicht geraten, sondern muessen durch Lesen der aktuellen Dokumente, reale Metadatenbeispiele und Tests geklaert werden.
