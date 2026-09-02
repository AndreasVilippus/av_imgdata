# DSM-Hilfe: Inventar der Hilfepunkte

## Zweck

Dieses Dokument definiert zunächst ausschließlich die **Struktur und die Hilfepunkte** der zukünftigen DSM-Hilfe und des gemeinsamen Documentation Core. Die eigentlichen Hilfetexte werden in einem nachfolgenden Schritt erstellt.

Die Liste basiert auf:

- der aktuell implementierten DSM-/Vue-Navigation,
- den tatsächlich vorhandenen Aktionen in Face Matching, Checks, Cleanup, Configuration, External Worker, External Libraries und Database Lists,
- den bestehenden Status-, Preview-, Review-, Worker- und Recognition-Konzepten,
- den bereits geplanten zukünftigen Funktionen,
- dem Documentation-Core-Prinzip einer gemeinsamen Quelle für DSM-Hilfe und GitHub Pages.

Grundregel:

> Ein Hilfepunkt beschreibt eine für den Benutzer eigenständig verständliche Funktion, Einstellung, Arbeitsweise oder Fehlerklasse. Interne Architekturdetails werden nur dann Teil der Benutzerhilfe, wenn sie für Installation, Bedienung oder Fehlersuche relevant sind.

Jeder Punkt erhält bereits eine stabile Dokument-ID. Diese IDs sollen später die Grundlage für `docs/metadata/navigation.yml`, interne `[[doc:...]]`-Links und die Generierung von `helptoc.conf` bilden.

---

# 1. Statusklassen

Für das Inventar werden drei Zustände verwendet:

| Status | Bedeutung |
|---|---|
| `current` | Funktion ist aktuell im Paket bzw. in der UI vorhanden |
| `planned` | Funktion ist konzeptioniert, aber noch nicht vollständig produktiv umgesetzt |
| `conditional` | Hilfe ist nur relevant, wenn optionale Komponente/Funktion vorhanden oder aktiviert ist |

Geplante Punkte werden bereits reserviert, sollen aber erst in die ausgelieferte DSM-Hilfe aufgenommen werden, wenn das zugehörige Feature tatsächlich verfügbar ist.

---

# 2. Vorgeschlagener vollständiger Hilfebaum

```text
ImgData Hilfe
│
├── 1. Einführung
│   ├── Überblick
│   ├── Voraussetzungen
│   ├── Installation und Aktualisierung
│   ├── Erster Start
│   ├── Navigation und Arbeitsbereiche
│   └── Datensicherheit und Arbeitsweise
│
├── 2. Status
│   ├── Statusübersicht
│   ├── Laufende Vorgänge und Fortschritt
│   ├── Fortsetzen unterbrochener Vorgänge
│   └── Komponentenbereitschaft
│
├── 3. Face Matching
│   ├── Überblick Face Matching
│   ├── Unbekanntes Photos-Gesicht in Datei suchen
│   ├── Gesicht aus Datei suchen
│   ├── Fehlende Gesichter in Photos markieren
│   ├── Fehlende Gesichter mit InsightFace suchen
│   ├── Unbekannte Gesichter mit InsightFace erkennen
│   ├── Trefferlisten und gespeicherte Findings
│   ├── Personen auswählen, anlegen und zuweisen
│   ├── Automatische und sichere Zuordnungen
│   └── Vorschau, Gesichtsausschnitt und Bounding Box
│
├── 4. Checks
│   ├── Überblick Checks
│   ├── Check ausführen oder gespeicherte Findings bearbeiten
│   ├── Dimensionsprobleme
│   ├── Doppelte Gesichtsmarkierungen
│   ├── Abweichende Gesichtspositionen
│   ├── Namenskonflikte
│   ├── Personenzuordnungen mit InsightFace prüfen
│   ├── Automatische Empfehlungen anwenden
│   ├── Findings ignorieren und Ignore-Listen
│   └── Prüfumfang über Änderungszeitraum begrenzen
│
├── 5. Cleanup
│   ├── Überblick Cleanup
│   ├── Namen anhand der Referenzliste vereinheitlichen
│   ├── Gesichtsrahmen standardisieren
│   ├── Personenprofile für Recognition erstellen
│   ├── Recognition-Referenzgesichter prüfen
│   ├── Recognition-Betriebsarten
│   ├── Recognition-Schwellenwerte und Auswahloptionen
│   └── Ausgewählte Änderungen anwenden
│
├── 6. Recognition-Profile
│   ├── Funktionsweise der Personenprofile
│   ├── Referenzgesichter
│   ├── Profilqualität und Mindestanzahl von Referenzen
│   ├── Outlier und ungeeignete Referenzen
│   └── Profile gezielt aktualisieren                     [planned]
│
├── 7. Konfiguration
│   ├── Überblick Konfiguration
│   ├── Konfiguration laden, speichern und zurücksetzen
│   ├── Metadaten-Schemata
│   │   ├── ACDSee
│   │   ├── Microsoft Face Metadata
│   │   └── MWG Regions
│   ├── Dateien und Bildformate
│   ├── XMP-Sidecars
│   ├── Synology Photos
│   ├── Analyse und Checks
│   ├── Name-Conflict-Erkennung
│   ├── Face Matching
│   ├── Recognition und InsightFace
│   ├── Bilddecoder und Größenbegrenzungen
│   ├── Native Prozessoren
│   └── Worker API
│
├── 8. External Worker
│   ├── Überblick External Worker
│   ├── Wann ein External Worker sinnvoll ist
│   ├── Worker API aktivieren
│   ├── Worker herunterladen
│   ├── Worker installieren
│   │   ├── Windows
│   │   ├── Linux                              [conditional/planned validation]
│   │   └── Docker                             [conditional/planned validation]
│   ├── Worker registrieren
│   ├── Registrierte Worker verwalten
│   ├── Worker-Status und Fähigkeiten
│   ├── Gemeinsame Bildpfade / Shared Path
│   ├── Face-Modelle auf dem Worker
│   ├── Lokale Verarbeitung und Worker-Fallback
│   ├── Sicherheit
│   └── Fehlerbehebung External Worker
│
├── 9. Externe Bibliotheken und Prozessoren
│   ├── Überblick
│   ├── ExifTool
│   │   ├── Status und Installation
│   │   ├── Metadaten lesen
│   │   ├── Sidecar-Verarbeitung
│   │   └── Fehlerbehebung
│   ├── InsightFace-kompatible Modelle
│   │   ├── Modellbereitstellung
│   │   ├── Lizenz-/Nutzungshinweis
│   │   ├── Modellstatus
│   │   └── Native Face Processor
│   ├── libvips
│   │   ├── Status
│   │   ├── unterstützte Bildformate
│   │   └── Fallback auf Standarddecoder
│   └── Abhängigkeiten und optionale Komponenten
│
├── 10. Datenbanklisten
│   ├── Überblick Datenbanklisten
│   ├── Namenszuordnungen
│   │   ├── Namenszuordnung anlegen
│   │   ├── Namenszuordnung bearbeiten
│   │   ├── Namenszuordnung löschen
│   │   └── Namenszuordnungen suchen
│   ├── Ignore-Liste für doppelte Gesichtsmarkierungen
│   ├── Ignore-Liste für abweichende Gesichtspositionen
│   ├── Ignore-Liste für Namenskonflikte
│   └── Listen leeren
│
├── 11. Vorschau und Review
│   ├── Bedienung der Review-Ansichten
│   ├── Vollbild- und Gesichtsvorschau
│   ├── Bounding Boxes und Gesichtsrahmen
│   ├── Zielperson auswählen
│   ├── Speichern, Speichern als und Überspringen
│   ├── Weitersuchen und Fortsetzen
│   └── Fehlerhafte oder nicht verfügbare Vorschauen
│
├── 12. Fehlerbehebung
│   ├── Paket startet nicht
│   ├── Benutzeroberfläche lädt nicht
│   ├── Synology Photos ist nicht erreichbar
│   ├── Keine oder falsche Metadaten gefunden
│   ├── XMP-Sidecars werden nicht gefunden
│   ├── Bild kann nicht dekodiert werden
│   ├── HEIC / HEIF / RAW-Probleme
│   ├── Face Processor nicht verfügbar
│   ├── InsightFace-Modell nicht verfügbar
│   ├── Recognition liefert keine Profile oder Treffer
│   ├── Vorgang bleibt stehen oder wurde unterbrochen
│   ├── Gespeicherte Findings können nicht fortgesetzt werden
│   ├── External Worker nicht erreichbar
│   ├── Worker-Version oder Fähigkeiten passen nicht
│   ├── Konfiguration zurücksetzen
│   └── Diagnoseinformationen sammeln
│
└── 13. Zukünftige Funktionen
    ├── Aufnahmezeitpunkt prüfen und bereinigen           [planned]
    ├── Recognition-Profile inkrementell pflegen         [planned]
    ├── Musikbewertungen / Audio Station                 [planned]
    └── DSM-Tray-Status                                  [planned]
```

---

# 3. Dokument-IDs und Zielstatus

## 3.1 Einführung

| ID | Titel | Status | DSM | Web |
|---|---|---|---:|---:|
| `index` | ImgData Hilfe | current | ja | ja |
| `overview` | Überblick | current | ja | ja |
| `requirements` | Voraussetzungen | current | ja | ja |
| `installation` | Installation und Aktualisierung | current | ja | ja |
| `first-start` | Erster Start | current | ja | ja |
| `navigation` | Navigation und Arbeitsbereiche | current | ja | ja |
| `data-safety` | Datensicherheit und Arbeitsweise | current | ja | ja |

### Inhaltliche Abgrenzung

`data-safety` soll später insbesondere erklären:

- welche Funktionen nur lesen,
- welche Funktionen Daten in Photos, Metadaten oder Paketdatenbank verändern,
- Bedeutung von Preview/Findings vor Änderungen,
- warum bestimmte Funktionen nicht automatisch angewendet werden.

---

## 3.2 Status

| ID | Titel | Status |
|---|---|---|
| `status` | Statusübersicht | current |
| `status-running-operations` | Laufende Vorgänge und Fortschritt | current |
| `status-resume` | Fortsetzen unterbrochener Vorgänge | current |
| `status-component-readiness` | Komponentenbereitschaft | current |

Komponentenbereitschaft umfasst insbesondere:

- Native Face Processor,
- InsightFace-kompatible Modelle,
- optionalen libvips-Backendstatus,
- später weitere optionale Processor-Komponenten.

---

## 3.3 Face Matching

Aktuell implementierte Aktionen bilden jeweils einen eigenen Hilfepunkt.

| ID | Titel | Status |
|---|---|---|
| `face-matching` | Überblick Face Matching | current |
| `face-match-search-photo-face-in-file` | Unbekanntes Photos-Gesicht in Datei suchen | current |
| `face-match-search-file-face` | Gesicht aus Datei suchen | current |
| `face-match-mark-missing-photos-faces` | Fehlende Gesichter in Photos markieren | current |
| `face-match-search-missing-insightface` | Fehlende Gesichter mit InsightFace suchen | current |
| `face-match-recognize-unknown` | Unbekannte Gesichter mit InsightFace erkennen | current |
| `face-match-findings` | Trefferlisten und gespeicherte Findings | current |
| `face-match-target-person` | Personen auswählen, anlegen und zuweisen | current |
| `face-match-safe-assignment` | Automatische und sichere Zuordnungen | current |
| `face-match-preview` | Vorschau, Gesichtsausschnitt und Bounding Box | current |

Die etablierten älteren Face-Match-Funktionen gelten gemäß Preview-Konzept als Referenzverhalten. Die Hilfe sollte deren Bedienlogik daher präzise dokumentieren und später als Referenz für vereinheitlichte Preview-/Review-Hilfe verwenden.

---

## 3.4 Checks

Die aktuell implementierten Check-Typen erhalten jeweils eigene Seiten.

| ID | Titel | Status |
|---|---|---|
| `checks` | Überblick Checks | current |
| `checks-scan-findings` | Check ausführen oder gespeicherte Findings bearbeiten | current |
| `checks-dimension-issues` | Dimensionsprobleme | current |
| `checks-duplicate-faces` | Doppelte Gesichtsmarkierungen | current |
| `checks-position-deviations` | Abweichende Gesichtspositionen | current |
| `checks-name-conflicts` | Namenskonflikte | current |
| `checks-recognition-assignments` | Personenzuordnungen mit InsightFace prüfen | current |
| `checks-auto-apply` | Automatische Empfehlungen anwenden | current |
| `checks-ignore` | Findings ignorieren und Ignore-Listen | current |
| `checks-changed-since` | Prüfumfang über Änderungszeitraum begrenzen | current |
| `checks-capture-datetime` | Aufnahmezeitpunkt prüfen | planned |

`checks-capture-datetime` wird erst aktiviert, wenn das Konzept `PHOTO_DATETIME_CONSISTENCY_CONCEPT.md` umgesetzt wurde. Es bleibt unter `checks` und wird nicht als neue globale Operation dokumentiert.

---

## 3.5 Cleanup

| ID | Titel | Status |
|---|---|---|
| `cleanup` | Überblick Cleanup | current |
| `cleanup-normalize-names` | Namen anhand der Referenzliste vereinheitlichen | current |
| `cleanup-face-frames` | Gesichtsrahmen standardisieren | current |
| `cleanup-build-profiles` | Personenprofile für Recognition erstellen | current |
| `cleanup-reference-outliers` | Recognition-Referenzgesichter prüfen | current |
| `cleanup-recognition-modes` | Recognition-Betriebsarten | current |
| `cleanup-recognition-options` | Recognition-Schwellenwerte und Auswahloptionen | current |
| `cleanup-apply-selected` | Ausgewählte Änderungen anwenden | current |

---

## 3.6 Recognition-Profile

Dieser Bereich ist bewusst zusätzlich zu Cleanup vorgesehen. Cleanup erklärt die Bedienung der Aktionen; Recognition-Profile erklärt das zugrunde liegende Benutzerkonzept.

| ID | Titel | Status |
|---|---|---|
| `recognition-profiles` | Funktionsweise der Personenprofile | current |
| `recognition-reference-faces` | Referenzgesichter | current |
| `recognition-profile-quality` | Profilqualität und Mindestanzahl von Referenzen | current |
| `recognition-outliers` | Outlier und ungeeignete Referenzen | current |
| `recognition-profile-maintenance` | Profile gezielt aktualisieren | planned |

Die geplante inkrementelle Profilpflege wird später in diesen Bereich integriert und nicht als eigenständiger neuer Hauptbereich neben Recognition angelegt.

---

## 3.7 Konfiguration

Die Konfigurationshilfe wird zweistufig aufgebaut:

1. redaktionelle Seiten für die Bedeutung zusammengehöriger Einstellungen,
2. automatisch generierte Einzelreferenz der tatsächlichen Config-Keys und Defaults.

### Redaktionelle Seiten

| ID | Titel | Status |
|---|---|---|
| `configuration` | Überblick Konfiguration | current |
| `configuration-load-save-defaults` | Laden, Speichern und Standardwerte | current |
| `configuration-metadata-schemas` | Metadaten-Schemata | current |
| `configuration-files` | Dateien und Bildformate | current |
| `configuration-sidecars` | XMP-Sidecars | current |
| `configuration-photos` | Synology Photos | current |
| `configuration-analysis` | Analyse und Checks | current |
| `configuration-name-conflicts` | Name-Conflict-Erkennung | current |
| `configuration-face-match` | Face Matching | current |
| `configuration-recognition` | Recognition und InsightFace | current |
| `configuration-image-decoding` | Bilddecoder und Größenbegrenzungen | current |
| `configuration-native-processors` | Native Prozessoren | current |
| `configuration-worker-api` | Worker API | current |

### Automatisch erzeugte Referenz

| ID | Titel | Status |
|---|---|---|
| `configuration-reference` | Vollständige Konfigurationsreferenz | planned generator/current data |

Die Konfigurationsreferenz soll später aus `var/config.json` plus Config-Metadaten/Schema erzeugt werden und nicht manuell gepflegt werden.

---

## 3.8 External Worker

| ID | Titel | Status |
|---|---|---|
| `external-worker` | Überblick External Worker | current |
| `external-worker-use-cases` | Wann ein External Worker sinnvoll ist | current |
| `external-worker-api` | Worker API aktivieren | current |
| `external-worker-download` | Worker herunterladen | current |
| `external-worker-install` | Worker installieren | current/conditional |
| `external-worker-install-windows` | Windows | current |
| `external-worker-install-linux` | Linux | planned validation |
| `external-worker-install-docker` | Docker | planned validation |
| `external-worker-registration` | Worker registrieren | current |
| `external-worker-management` | Registrierte Worker verwalten | current |
| `external-worker-status` | Worker-Status und Fähigkeiten | current |
| `external-worker-shared-path` | Gemeinsame Bildpfade / Shared Path | current |
| `external-worker-models` | Face-Modelle auf dem Worker | current |
| `external-worker-fallback` | Lokale Verarbeitung und Worker-Fallback | current |
| `external-worker-security` | Sicherheit | current |
| `external-worker-troubleshooting` | Fehlerbehebung External Worker | current |

### Wichtige Abgrenzung

Die Benutzerhilfe beschreibt nicht die interne Worker-Queue oder Processor-Verträge im Detail. Erklärt werden nur die für Betrieb und Diagnose relevanten Fakten:

- DSM bleibt führend,
- Worker beschleunigt rechenintensive Verarbeitung,
- welche Funktionen Worker-Unterstützung besitzen,
- wann lokal verarbeitet wird,
- Version/Fähigkeiten müssen passen,
- Shared-Path-Konfiguration,
- Registrierung und Token-Sicherheit.

---

## 3.9 Externe Bibliotheken und Prozessoren

| ID | Titel | Status |
|---|---|---|
| `external-libraries` | Überblick externe Bibliotheken und Prozessoren | current |
| `exiftool` | ExifTool | current |
| `exiftool-status-installation` | Status und Installation | current |
| `exiftool-metadata-read` | Metadaten lesen | current |
| `exiftool-sidecars` | Sidecar-Verarbeitung | current |
| `exiftool-troubleshooting` | Fehlerbehebung ExifTool | current |
| `insightface-models` | InsightFace-kompatible Modelle | current |
| `insightface-model-installation` | Modellbereitstellung | current |
| `insightface-license` | Lizenz-/Nutzungshinweis | current |
| `insightface-model-status` | Modellstatus | current |
| `native-face-processor` | Native Face Processor | current |
| `libvips` | libvips | current/conditional |
| `libvips-status` | Status | current/conditional |
| `libvips-formats` | Unterstützte Bildformate | current/conditional |
| `libvips-fallback` | Fallback auf Standarddecoder | current/conditional |
| `external-dependencies` | Abhängigkeiten und optionale Komponenten | current |

---

## 3.10 Datenbanklisten

Die aktuell sichtbaren persistenten Listen werden einzeln dokumentiert.

| ID | Titel | Status |
|---|---|---|
| `database-lists` | Überblick Datenbanklisten | current |
| `database-name-mappings` | Namenszuordnungen | current |
| `database-name-mapping-add` | Namenszuordnung anlegen | current |
| `database-name-mapping-edit` | Namenszuordnung bearbeiten | current |
| `database-name-mapping-delete` | Namenszuordnung löschen | current |
| `database-name-mapping-search` | Namenszuordnungen suchen | current |
| `database-ignore-duplicate-faces` | Ignore-Liste für doppelte Gesichtsmarkierungen | current |
| `database-ignore-position-deviations` | Ignore-Liste für abweichende Gesichtspositionen | current |
| `database-ignore-name-conflicts` | Ignore-Liste für Namenskonflikte | current |
| `database-clear-list` | Listen leeren | current |

---

## 3.11 Vorschau und Review

Diese Punkte sind bewusst fachbereichsübergreifend. Die einzelnen Face-Match-/Checks-/Cleanup-Seiten verlinken auf sie, statt dieselbe Bedienlogik mehrfach vollständig zu erklären.

| ID | Titel | Status |
|---|---|---|
| `review` | Bedienung der Review-Ansichten | current |
| `review-preview-modes` | Vollbild- und Gesichtsvorschau | current |
| `review-bounding-boxes` | Bounding Boxes und Gesichtsrahmen | current |
| `review-target-selection` | Zielperson auswählen | current |
| `review-actions` | Speichern, Speichern als und Überspringen | current |
| `review-continue-resume` | Weitersuchen und Fortsetzen | current |
| `review-preview-errors` | Fehlerhafte oder nicht verfügbare Vorschauen | current |

Die Texte werden später am etablierten Face-Match-Verhalten ausgerichtet. Neue Preview-/Review-Komponenten verändern diese Bediensemantik nicht automatisch.

---

## 3.12 Fehlerbehebung

| ID | Titel | Status |
|---|---|---|
| `troubleshooting` | Fehlerbehebung | current |
| `troubleshooting-package-start` | Paket startet nicht | current |
| `troubleshooting-ui` | Benutzeroberfläche lädt nicht | current |
| `troubleshooting-photos` | Synology Photos ist nicht erreichbar | current |
| `troubleshooting-metadata` | Keine oder falsche Metadaten gefunden | current |
| `troubleshooting-sidecars` | XMP-Sidecars werden nicht gefunden | current |
| `troubleshooting-image-decode` | Bild kann nicht dekodiert werden | current |
| `troubleshooting-heic-raw` | HEIC / HEIF / RAW-Probleme | current |
| `troubleshooting-face-processor` | Face Processor nicht verfügbar | current |
| `troubleshooting-face-model` | InsightFace-Modell nicht verfügbar | current |
| `troubleshooting-recognition` | Recognition liefert keine Profile oder Treffer | current |
| `troubleshooting-operation-stalled` | Vorgang bleibt stehen oder wurde unterbrochen | current |
| `troubleshooting-findings-resume` | Findings können nicht fortgesetzt werden | current |
| `troubleshooting-worker-connection` | External Worker nicht erreichbar | current |
| `troubleshooting-worker-contract` | Worker-Version oder Fähigkeiten passen nicht | current |
| `troubleshooting-reset-config` | Konfiguration zurücksetzen | current |
| `troubleshooting-diagnostics` | Diagnoseinformationen sammeln | current |

---

# 4. Reservierte Hilfepunkte für geplante Funktionen

Diese IDs werden jetzt festgelegt, aber zunächst nicht in `helptoc.conf` ausgegeben.

## 4.1 Aufnahmezeitpunkt von Fotos

Basierend auf `PHOTO_DATETIME_CONSISTENCY_CONCEPT.md`:

| ID | Titel |
|---|---|
| `checks-capture-datetime` | Aufnahmezeitpunkt prüfen |
| `capture-datetime-sources` | Quellen des Aufnahmezeitpunkts |
| `capture-datetime-timezones` | Zeitzonen und Zeitgenauigkeit |
| `capture-datetime-findings` | Inkonsistenzen und Findings |
| `capture-datetime-correction` | Aufnahmezeitpunkt bereinigen |

Diese Seiten werden unter **Checks** eingeordnet.

## 4.2 Inkrementelle Recognition-Profilpflege

Basierend auf `dm-recognition-profile-maintenance.md`:

| ID | Titel |
|---|---|
| `recognition-profile-maintenance` | Recognition-Profile gezielt aktualisieren |
| `recognition-profile-dirty-state` | Aktualisierungsbedarf von Profilen |
| `recognition-profile-candidates` | Kandidaten und Referenzgesichter |
| `recognition-profile-quality` | Profilqualität und Diversität |

Sie werden unter **Recognition-Profile** eingeordnet.

## 4.3 Musikbereich

Basierend auf `MUSIC_EXTENSION_CONCEPT.md`:

| ID | Titel |
|---|---|
| `music` | Musik |
| `music-ratings` | Musikbewertungen |
| `music-audio-station` | Audio Station / DS Audio |
| `music-rating-sources` | Quellen für Bewertungen |
| `music-rating-preview` | Vorschau geplanter Änderungen |
| `music-rating-apply` | Bewertungen übernehmen |
| `music-troubleshooting` | Fehlerbehebung Musikbewertungen |

Der komplette Hauptbereich bleibt verborgen, bis eine produktiv nutzbare Musikfunktion vorhanden ist.

## 4.4 DSM-Tray

Basierend auf `TRAY_STATUS_CONCEPT.md`:

| ID | Titel |
|---|---|
| `tray-status` | DSM-Tray-Status |
| `tray-running-operation` | Laufende Vorgänge im DSM-Tray |
| `tray-troubleshooting` | Tray wird nicht angezeigt |

Der Hilfepunkt wird erst ausgeliefert, wenn die Drittanbieter-Tray-Integration praktisch validiert und aktiviert wurde.

---

# 5. Punkte, die bewusst keine eigene Benutzerhilfe erhalten

Folgende Konzepte sind technische Architektur und werden nicht als DSM-Hilfepunkt angelegt:

- Repository-Strukturbereinigung,
- Python-Package-Migration,
- Processor-Contract-Interna,
- interne Worker-Queue-/Pipeline-Implementierung,
- Build-Skripte,
- GitHub-Actions-Details,
- PreviewResolver-/MediaPreview-Implementierungsdetails,
- Review-Adapter-Implementierung,
- DB-Repository-Implementierung,
- Documentation-Core-Renderer.

Diese Informationen gehören in Entwickler-/Architekturdokumentation der Website, nicht in die Anwendungshilfe.

---

# 6. Vorgesehene DSM-Navigationstiefe

Die DSM-Hilfe sollte nicht jeden Detailpunkt auf oberster Ebene zeigen.

Empfohlene sichtbare Tiefe:

```text
Hauptbereich
    ├── Überblick
    ├── häufig verwendete Hauptfunktionen
    └── Untergruppe
         └── Detailseite
```

Insbesondere Konfigurations-Einzelkeys werden **nicht** alle im `helptoc.conf` als eigener Baumknoten aufgeführt. Sie erscheinen auf der generierten Konfigurationsreferenz und sind über Suche bzw. Anker erreichbar.

Dasselbe gilt für kleine Unteraktionen wie „Namenszuordnung löschen“: Sie erhalten eine stabile Dokument-ID bzw. einen Abschnitt, müssen aber nicht zwingend als sichtbarer eigener DSM-Baumknoten erscheinen.

---

# 7. Empfohlene erste `helptoc.conf`-Ebene

Für die erste produktive Hilfe sollte der sichtbare Hauptbaum zunächst kompakt bleiben:

```text
ImgData Hilfe
├── Einführung
├── Status
├── Face Matching
├── Checks
├── Cleanup
├── Recognition-Profile
├── Konfiguration
├── External Worker
├── Externe Bibliotheken
├── Datenbanklisten
├── Vorschau und Review
└── Fehlerbehebung
```

Geplante Funktionen werden nur bei tatsächlicher Verfügbarkeit ergänzt.

---

# 8. Beziehung zu GitHub Pages

Alle oben definierten Dokument-IDs sind gemeinsame Documentation-Core-IDs.

Standard:

```yaml
targets:
  - dsm
  - web
```

Nur wenige Seiten sollten davon abweichen.

Die Website kann dieselben Hilfepunkte zusätzlich mit folgenden web-only Bereichen ergänzen:

- Download,
- Releases,
- Changelog,
- Roadmap,
- Entwicklungsdokumentation,
- Buildinformationen,
- Contributor-/GitHub-Informationen.

Die DSM-Hilfe bleibt dagegen strikt an Bedienung, Konfiguration, Betrieb und Fehlerbehebung orientiert.

---

# 9. Nächster Arbeitsschritt

Nach Freigabe dieses Inventars sollten die Hilfetexte nicht beliebig der Reihe nach geschrieben werden, sondern in folgender Reihenfolge:

```text
1. Überblick / Einführung
2. Navigation
3. Face Matching
4. Checks
5. Cleanup
6. gemeinsame Review-/Preview-Bedienung
7. Recognition-Profile
8. Configuration
9. External Worker
10. External Libraries
11. Database Lists
12. Troubleshooting
```

Dabei sollte für jede Seite zuerst aus dem aktuellen Quellcode ermittelt werden:

- was der Benutzer tatsächlich sieht,
- welche Optionen vorhanden sind,
- welche Voraussetzungen gelten,
- welche Daten verändert werden,
- welche Ergebnisse entstehen,
- welche Fehler-/Resume-Zustände existieren,
- auf welche anderen Hilfepunkte verwiesen werden soll.

Erst danach wird der eigentliche DE-Hilfetext erstellt und anschließend die EN-Fassung abgeleitet.