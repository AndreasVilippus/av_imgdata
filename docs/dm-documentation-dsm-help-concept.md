# Konzept: Gemeinsame Dokumentationsbasis für GitHub Pages und DSM-Hilfe

## 1. Ziel

Für das DSM-Paket sollen zwei Dokumentationsausgaben aus möglichst denselben Quellen erzeugt und automatisch gepflegt werden:

1. eine zweisprachige öffentliche GitHub-Page (Deutsch / Englisch)
2. eine in DSM integrierte Anwendungshilfe nach dem Synology-Prinzip für `helptoc.conf`, `help/<sprache>/` und `texts/<sprache>/strings`

Das Grundprinzip lautet:

> Inhalte werden möglichst nur einmal gepflegt. Technische Fakten, Metadaten und strukturierte Beschreibungen besitzen eine zentrale Quelle. Daraus werden GitHub Pages, DSM-Hilfe, Konfigurationsreferenz und Prüfungen generiert.

Damit soll vermieden werden, dass dieselben Informationen separat in README, Website, DSM-Hilfe, Paket-Metadaten, UI und Konfigurationsdokumentation gepflegt werden müssen.

---

## 2. Verbindliche DSM-Grundlage

Die Synology Developer-Dokumentation beschreibt für die Integration einer Anwendungshilfe in DSM folgende Struktur:

- `helptoc.conf` liegt unter dem in `INFO` über `dsmuidir` definierten UI-Verzeichnis.
- Die Hilfeseiten liegen unter `help/<DSM-Sprache>/`.
- Sprachtexte für Baumtitel und andere i18n-Werte liegen unter `texts/<DSM-Sprache>/strings`.
- `helptoc.conf` referenziert Titel über `section:key`.
- Die einzelnen Hilfeseiten werden als HTML erzeugt und verwenden die von DSM vorgegebenen Help-CSS-/Scrollbar-Ressourcen.

Für dieses Paket ist die Integration bereits grundsätzlich passend vorbereitet:

```sh
dsmappname="SYNO.SDS.App.AV_ImgData.Instance"
dsmuidir="ui"
```

Damit ist der vorgesehene Zielort:

```text
ui/
├── helptoc.conf
├── help/
│   ├── enu/
│   └── ger/
└── texts/
    ├── enu/
    │   └── strings
    └── ger/
        └── strings
```

Deutsch wird im DSM-Sprachschema als `ger`, Englisch als `enu` geführt.

### Quellen

Primäre Referenzen:

- Synology Developer Guide: Application Help  
  https://help.synology.com/developer-guide/integrate_dsm/dsm_help.html
- Synology Developer Guide: Application Internationalization  
  https://help.synology.com/developer-guide/integrate_dsm/i18n.html

Diese Synology-Dokumentation ist für die DSM-Zielstruktur maßgeblich.

---

## 3. Gemeinsame Zielarchitektur

```text
                         Repository
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
 Paket-/Builddaten      strukturierte Docs    redaktionelle Docs
 INFO.sh                config schema          Markdown DE/EN
 var/config.json        feature metadata       Tutorials
 Git Tags/Releases      help/navigation        Troubleshooting
 Worker metadata        UI-i18n keys           Konzepte
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ▼
                    Documentation Builder
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
 GitHub Pages DE/EN     DSM Help ger/enu     Validierung/Tests
        │                    │                    │
        ▼                    ▼                    ▼
 öffentliche Doku       Paket ui/help       CI / Paketbuild
```

Es gibt damit **nicht zwei Dokumentationen**, sondern zwei Renderer für dieselbe Dokumentationsbasis.

---

## 4. Welche Inhalte gemeinsam nutzbar sind

Die Schnittmenge zwischen Website und DSM-Hilfe ist groß.

Gemeinsam nutzbar sind insbesondere:

- Produktbeschreibung
- Funktionsübersicht
- Installation
- Bedienung
- Gesichtserkennung
- Profile
- Profilreferenzbilder
- Bildanalyse
- Datenbanklisten
- External Worker
- Konfiguration
- Grenzwerte und Defaults
- Fehlerbehebung
- Architekturüberblick, soweit benutzerrelevant
- Screenshots
- Hinweise und Warnungen
- Versions-/Kompatibilitätsinformationen

Nur für GitHub Pages relevante Inhalte:

- Release-Download
- Release-Historie
- GitHub Issues
- Roadmap
- Buildstatus
- Entwicklerlinks
- Contributor-/Repository-Informationen

Nur für DSM-Hilfe relevante Inhalte:

- DSM-Hilfebaum
- `helptoc.conf`
- DSM-i18n-`strings`
- DSM-spezifische HTML-Hülle
- ggf. kontextbezogene interne Links zwischen Hilfeseiten

---

## 5. Empfohlene Quellstruktur

Die Quellen sollten nicht direkt in `ui/help` gepflegt werden. `ui/help` und `ui/texts` sind Build-Ausgaben.

Empfehlung:

```text
docs-src/
├── content/
│   ├── de/
│   │   ├── index.md
│   │   ├── installation.md
│   │   ├── configuration.md
│   │   ├── troubleshooting.md
│   │   └── features/
│   │       ├── recognition.md
│   │       ├── profiles.md
│   │       ├── profile-references.md
│   │       ├── database.md
│   │       └── external-worker.md
│   │
│   └── en/
│       └── ... gleiche logische Struktur ...
│
├── metadata/
│   ├── navigation.yml
│   ├── features.yml
│   ├── package.yml            # nur falls nicht vollständig ableitbar
│   ├── screenshots.yml
│   └── help.yml
│
├── i18n/
│   ├── de.yml
│   └── en.yml
│
├── generated/
│   ├── package.json
│   ├── configuration.json
│   ├── releases.json
│   └── worker.json
│
└── assets/
    ├── screenshots/
    └── icons/
```

Generierte Zielartefakte:

```text
site/                     # GitHub Pages Build-Ausgabe
ui/helptoc.conf           # DSM Help
ui/help/ger/*.html
ui/help/enu/*.html
ui/texts/ger/strings
ui/texts/enu/strings
```

---

## 6. Zentrale Navigationsquelle

Die Navigation sollte nicht einmal für GitHub Pages und ein zweites Mal als `helptoc.conf` gepflegt werden.

Empfehlung: `docs-src/metadata/navigation.yml`

Beispiel:

```yaml
root:
  id: index
  title_key: help.index
  source: index.md
  children:
    - id: installation
      title_key: help.installation
      source: installation.md

    - id: features
      title_key: help.features
      children:
        - id: recognition
          title_key: help.recognition
          source: features/recognition.md
        - id: profiles
          title_key: help.profiles
          source: features/profiles.md
        - id: external-worker
          title_key: help.external_worker
          source: features/external-worker.md

    - id: configuration
      title_key: help.configuration
      source: configuration.md

    - id: troubleshooting
      title_key: help.troubleshooting
      source: troubleshooting.md
```

Daraus entstehen automatisch:

- MkDocs-/Website-Navigation
- DSM `helptoc.conf`
- Sprachschlüssel für die Hilfenavigation
- Vollständigkeitsprüfung
- Linkprüfung

---

## 7. Generierung von `helptoc.conf`

Aus `navigation.yml` wird beispielsweise erzeugt:

```json
{
  "app": "SYNO.SDS.App.AV_ImgData.Instance",
  "title": "help_tree:index",
  "content": "index.html",
  "toc": [
    {
      "title": "help_tree:installation",
      "content": "installation.html"
    },
    {
      "title": "help_tree:features",
      "content": "features.html",
      "nodes": [
        {
          "title": "help_tree:recognition",
          "content": "features_recognition.html"
        },
        {
          "title": "help_tree:profiles",
          "content": "features_profiles.html"
        },
        {
          "title": "help_tree:external_worker",
          "content": "features_external_worker.html"
        }
      ]
    }
  ]
}
```

Die App-ID darf nicht nochmals manuell gepflegt werden. Der Generator soll sie aus `INFO.sh` (`dsmappname`) übernehmen.

---

## 8. Gemeinsame Sprachquelle und DSM `strings`

Für kurze Titel, Labels und Generator-Texte wird eine zentrale i18n-Quelle verwendet.

Beispiel `docs-src/i18n/de.yml`:

```yaml
help:
  index: ImgData Hilfe
  installation: Installation
  features: Funktionen
  recognition: Gesichtserkennung
  profiles: Personenprofile
  external_worker: External Worker
  configuration: Konfiguration
  troubleshooting: Fehlerbehebung
```

Englisch:

```yaml
help:
  index: ImgData Help
  installation: Installation
  features: Features
  recognition: Face Recognition
  profiles: Person Profiles
  external_worker: External Worker
  configuration: Configuration
  troubleshooting: Troubleshooting
```

Daraus erzeugt der DSM-Renderer:

```text
ui/texts/ger/strings
```

mit z. B.:

```ini
[help_tree]
index="ImgData Hilfe"
installation="Installation"
features="Funktionen"
recognition="Gesichtserkennung"
profiles="Personenprofile"
external_worker="External Worker"
configuration="Konfiguration"
troubleshooting="Fehlerbehebung"
```

und analog `ui/texts/enu/strings`.

Die gleiche i18n-Quelle kann Website-Navigation, Buttons und automatisch erzeugte Tabellen beschriften.

---

## 9. Markdown als gemeinsame Inhaltsquelle

Längere Hilfetexte sollten in Markdown gepflegt werden.

Beispiel:

```text
docs-src/content/de/features/recognition.md
docs-src/content/en/features/recognition.md
```

Der Build erzeugt daraus:

```text
GitHub Pages:
/de/features/recognition/
/en/features/recognition/

DSM:
ui/help/ger/features_recognition.html
ui/help/enu/features_recognition.html
```

Damit bleibt die redaktionelle Pflege auf eine Quelldatei je Sprache beschränkt.

---

## 10. DSM-HTML-Renderer

Für DSM wird Markdown nicht unverändert ausgeliefert, sondern in eine Synology-konforme HTML-Hülle eingebettet.

Template:

```html
<!DOCTYPE html>
<html class="img-no-display">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
  <link href="../../../../help/help.css" rel="stylesheet" type="text/css">
  <link href="../../../../help/scrollbar/flexcroll.css" rel="stylesheet" type="text/css">
  <script type="text/javascript" src="../../../../help/scrollbar/flexcroll.js"></script>
  <script type="text/javascript" src="../../../../help/scrollbar/initFlexcroll.js"></script>
</head>
<body>
  <!-- generierter Inhalt -->
</body>
</html>
```

Die relativen Ressourcenpfade sollten vom Renderer zentral vorgegeben und per Test geprüft werden.

Wichtig: Die DSM-Hilfe sollte bewusst konservatives HTML verwenden. Die GitHub-Page kann deutlich umfangreicheres CSS/JS verwenden.

---

## 11. Quellenmatrix

| Information | Führende Quelle | GitHub Pages | DSM-Hilfe | Testbarkeit |
|---|---|---:|---:|---:|
| Paketname | `INFO.sh` | automatisch | automatisch | hoch |
| App-ID | `INFO.sh:dsmappname` | optional | `helptoc.conf` | hoch |
| UI-Verzeichnis | `INFO.sh:dsmuidir` | nein | Buildziel | hoch |
| Version | `INFO.sh` / Release-Regel | automatisch | optional anzeigen | hoch |
| DSM Mindestversion | `INFO.sh:os_min_ver` | automatisch | automatisch | hoch |
| Paketbeschreibung DE/EN | `INFO.sh` oder zentrale Metadaten | automatisch | Intro möglich | hoch |
| Release | GitHub Releases | automatisch | normalerweise nein | hoch |
| Download | GitHub Release Asset | automatisch | Link optional | hoch |
| Navigation | `navigation.yml` | automatisch | automatisch | sehr hoch |
| Hilfebaum-Titel | i18n DE/EN | automatisch | `strings` | sehr hoch |
| Feature-Liste | `features.yml` | automatisch | automatisch | sehr hoch |
| Feature-Texte | Markdown DE/EN | ja | ja | sehr hoch |
| Installation | Markdown DE/EN | ja | ja | sehr hoch |
| Troubleshooting | Markdown DE/EN | ja | ja | sehr hoch |
| Config Defaults | `var/config.json` | automatisch | automatisch | sehr hoch |
| Config-Typen/Grenzen | Config-Schema | automatisch | automatisch | sehr hoch |
| Config-Beschreibung | i18n / Schema-Key | automatisch | automatisch | sehr hoch |
| UI-Konfigurationslabels | bestehende UI-i18n bzw. gemeinsame Keys | optional | automatisch nutzbar | mittel/hoch |
| Worker-Fähigkeiten | Worker-/Feature-Metadaten | automatisch | automatisch | hoch |
| Screenshots | zentrale Assets | ja | optional | hoch |
| Known Issues | GitHub Issues | automatisch | eher Link/selektiv | mittel |
| Roadmap | GitHub Issues/Milestones | automatisch | nein | mittel |
| Buildstatus | GitHub Actions | automatisch | nein | hoch |

---

## 12. Konfiguration als besonders wichtige gemeinsame Quelle

Die Konfigurationshilfe sollte weder für Website noch DSM manuell als Tabelle nachgebaut werden.

Aktuelle reale Quelle im Projekt ist unter anderem:

```text
var/config.json
```

Dort existieren bereits Defaults wie z. B.:

```text
analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON
analysis.CHECKS.RECOGNITION_MAX_PROFILE_REFERENCE_FACES_PER_PERSON
```

Empfohlen wird ein ergänzendes Schema, das keine Defaults dupliziert, sondern nur Dokumentations- und Validierungsmetadaten enthält.

Beispiel:

```yaml
analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON:
  type: integer
  min: 2
  max: 1000
  category: recognition
  description_key: config.recognition_min_faces
  advanced: true
```

Der Default wird beim Build aus `var/config.json` gelesen.

Aus beiden Quellen entsteht ein neutrales Modell:

```json
{
  "path": "analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON",
  "type": "integer",
  "default": 3,
  "min": 2,
  "max": 1000,
  "category": "recognition",
  "description_key": "config.recognition_min_faces"
}
```

Dieses Modell kann gleichzeitig verwendet werden für:

- GitHub Pages Konfigurationsreferenz
- DSM-Hilfe Konfigurationsreferenz
- UI-Hilfetexte
- Strukturchecks
- Regressionstests

---

## 13. Möglichkeit zur Wiederverwendung bestehender UI-Texte

Wo die Web-UI bereits deutsch/englische Bezeichnungen oder Hilfetexte besitzt, sollte geprüft werden, ob diese als Quelle oder zumindest als Validierungsgegenstück genutzt werden können.

Drei Stufen sind möglich:

### Stufe A – nur vergleichen

UI-i18n bleibt unverändert. Dokumentations-i18n wird separat geführt, ein Test erkennt abweichende oder fehlende Schlüssel.

### Stufe B – gemeinsame Keys

UI und Dokumentation greifen auf dieselben semantischen Schlüssel zurück.

### Stufe C – zentrale Textquelle

Ein neutrales i18n-Format wird Buildquelle für:

- Vue/UI
- GitHub Pages
- DSM `strings`

Stufe C ist langfristig am saubersten, sollte aber nur umgesetzt werden, wenn sie die bestehende UI-Architektur nicht unnötig kompliziert.

---

## 14. Inhalte nach Zielgruppe markieren

Nicht jeder Abschnitt gehört in beide Ausgaben. Deshalb sollte Markdown optional Metadaten besitzen.

Beispiel Frontmatter:

```yaml
---
id: external-worker
outputs:
  - web
  - dsm
since: 0.10
status: beta
---
```

Nur Website:

```yaml
outputs:
  - web
```

Nur DSM:

```yaml
outputs:
  - dsm
```

So bleibt trotzdem eine zentrale Dokumentationsstruktur möglich.

---

## 15. Automatisch erzeugte Hinweise

Aus strukturierten Metadaten können Hinweise automatisch in beide Ausgaben eingebaut werden.

Beispiele:

```text
Verfügbar ab Version 0.10
Requires DSM 7.3 or later
Beta
Advanced setting
External Worker required
Restart required
```

Diese Informationen sollten nicht in Fließtext kopiert werden, sondern aus Metadaten stammen.

---

## 16. Release- und Buildablauf

Empfohlener Ablauf:

```text
Code / Docs ändern
        │
        ▼
Documentation validation
        │
        ├── Quellen prüfen
        ├── DE/EN prüfen
        ├── Links prüfen
        ├── Config-Abdeckung prüfen
        └── Navigation prüfen
        │
        ▼
Generate neutral documentation model
        │
        ├───────────────┐
        ▼               ▼
Generate Website    Generate DSM Help
        │               │
        ▼               ▼
MkDocs build        ui/helptoc.conf
                    ui/help/ger
                    ui/help/enu
                    ui/texts/ger
                    ui/texts/enu
        │               │
        └───────┬───────┘
                ▼
             Tests
                │
       ┌────────┴────────┐
       ▼                 ▼
 GitHub Pages        DSM Paketbuild
```

Bei einem Release wird die Website zusätzlich mit GitHub-Release-Daten angereichert.

---

# 17. Testkonzept

Die Dokumentation soll wie Code getestet werden.

## 17.1 Quellen- und Strukturtests

### `INFO.sh`

Prüfen:

- `dsmuidir` existiert
- `dsmappname` existiert
- `os_min_ver` existiert
- `version` existiert
- `description_enu` und `description_ger` existieren

### Navigation

Prüfen:

- jede `source` existiert für DE und EN
- jede ID ist eindeutig
- keine zyklischen Navigationsstrukturen
- jede referenzierte i18n-ID existiert
- jede DSM-Zieldatei hat einen eindeutigen Dateinamen

---

## 17.2 DSM-`helptoc.conf`-Tests

Prüfen:

- valides JSON
- `app` entspricht `INFO.sh:dsmappname`
- Root enthält `title`, `content`, `toc`
- `toc` ist Array
- jeder Node mit `content` verweist auf eine erzeugte HTML-Datei
- jeder `title` im Format `section:key` besitzt Übersetzungen in `ger` und `enu`
- keine verwaisten Hilfeseiten
- keine doppelten `content`-Ziele

Beispiel Fehler:

```text
FAIL: ui/helptoc.conf references missing help page:
features_external_worker.html
```

---

## 17.3 DSM-`strings`-Tests

Prüfen:

- `ui/texts/ger/strings` vorhanden
- `ui/texts/enu/strings` vorhanden
- benötigte Sections vorhanden
- alle aus `helptoc.conf` verwendeten Keys vorhanden
- keine leeren Werte für verpflichtende Navigationstitel
- UTF-8 lesbar

Beispiel:

```text
FAIL: Missing DSM help translation:
enu [help_tree] external_worker
```

---

## 17.4 DSM-HTML-Tests

Für jede generierte Hilfeseite:

- `<!DOCTYPE html>` vorhanden
- `<html class="img-no-display">` vorhanden
- UTF-8 Meta vorhanden
- DSM `help.css` eingebunden
- DSM Flexcroll CSS/JS eingebunden
- `<body>` nicht leer
- interne Links zeigen auf vorhandene Ziele
- keine Website-spezifischen Scripts/CSS-Leichen

Optional HTML-Parser statt Stringtests verwenden.

---

## 17.5 Sprachtests

Prüfen:

```text
DE-Datei vorhanden ↔ EN-Datei vorhanden
```

Ausnahmen müssen explizit als sprachneutral oder zielgruppenspezifisch markiert sein.

Prüfen:

- gleiche Dokument-IDs
- gleiche Navigationsstruktur
- gleiche automatisch erzeugte technische Werte
- vollständige i18n-Schlüssel

Technische Werte dürfen sich zwischen Sprachen nicht unterscheiden.

Beispiel:

```text
FAIL: Generated config default differs between de/en:
analysis.CHECKS.RECOGNITION_BATCH_SIZE
```

---

## 17.6 Konfigurationsabdeckung

Für dokumentationspflichtige Config-Keys soll gelten:

```text
Key in var/config.json
        ↓
Schema/Metadata vorhanden?
        ↓
Description Key vorhanden?
        ↓
DE Text vorhanden?
        ↓
EN Text vorhanden?
        ↓
Website + DSM Ausgabe erzeugbar?
```

Beispiel:

```text
FAIL: Config key has no documentation metadata:
analysis.CHECKS.NEW_OPTION
```

oder:

```text
FAIL: Missing German description:
config.new_option.description
```

Damit kann ein neuer Konfigurationsparameter nicht unbemerkt ohne Hilfe eingeführt werden.

---

## 17.7 Cross-Output-Tests

Diese Tests sind besonders wichtig, da zwei Renderer verwendet werden.

Für jede gemeinsame Seite prüfen:

- identische Dokument-ID
- identische Überschriftsemantik
- gleiche automatisch erzeugte technische Fakten
- dieselbe Mindestversion
- dieselben Defaultwerte
- dieselben Feature-Statusangaben

Ein Snapshot-Test kann das neutrale Zwischenmodell absichern, statt HTML gegen HTML zu vergleichen.

---

## 17.8 Linktests

Website:

- interne Links
- Release-Links
- GitHub-Links
- Bildreferenzen

DSM:

- interne HTML-Dateien
- Bilder
- keine absoluten GitHub-Pages-Pfade innerhalb der DSM-Hilfe

Externe Links dürfen separat als Warnung behandelt werden, damit ein temporär nicht erreichbarer externer Server keinen Paketbuild blockiert.

---

## 17.9 Paketstrukturtest

Nach dem DSM-Build prüfen, ob die generierten Dateien tatsächlich im Paket landen:

```text
ui/helptoc.conf
ui/help/ger/*.html
ui/help/enu/*.html
ui/texts/ger/strings
ui/texts/enu/strings
```

Damit wird verhindert, dass die Generierung funktioniert, die Package-Buildregeln die Dateien aber versehentlich nicht übernehmen.

---

## 17.10 Optionaler DSM-Integrationstest

Auf einem Test-NAS kann nach Installation geprüft werden:

- Paket wird installiert
- DSM lädt die Anwendung
- Hilfeeintrag erscheint
- Root-Hilfeseite öffnet
- DE bei deutscher DSM-Sprache
- EN bei englischer DSM-Sprache
- Navigation funktioniert
- Styles werden korrekt geladen

Dieser Test ist als Integrations-/Release-Test sinnvoll und muss nicht bei jedem kleinen Commit auf einem NAS laufen.

---

## 18. Testmatrix

| Test | Unit/CI | Package Build | NAS Integration |
|---|---:|---:|---:|
| Navigation YAML valide | X | | |
| DE/EN vollständig | X | | |
| `helptoc.conf` JSON valide | X | X | |
| App-ID korrekt | X | X | |
| DSM strings vollständig | X | X | |
| DSM HTML Template korrekt | X | X | |
| interne Links | X | X | |
| Config-Abdeckung | X | X | |
| technische Daten DE=EN | X | | |
| Dateien im SPK vorhanden | | X | |
| Hilfe in DSM sichtbar | | | X |
| Sprachumschaltung DSM | | | X |
| Styles/Scrollbars DSM | | | X |
| GitHub Pages Build | X | | |
| Release-Daten korrekt | X | Release | |

---

## 19. Gute Quellen im bestehenden Repository

Für die automatische Dokumentation sollten zuerst bereits vorhandene Quellen verwendet werden.

### `INFO.sh`

Bereits vorhanden:

- `package`
- `version`
- `displayname`
- `description`
- `description_enu`
- `description_ger`
- `arch`
- `os_min_ver`
- `dsmappname`
- `dsmuidir`

Diese Datei ist damit eine sehr gute primäre Quelle für Paket- und DSM-Integrationsdaten.

### `var/config.json`

Bereits vorhanden:

- zentrale Konfigurationsdefaults
- Analyse-/Recognition-Parameter
- weitere Laufzeitparameter

Diese Datei sollte Quelle für Defaults bleiben.

### Service-/Validierungscode

Vorhandene Config-Services enthalten bereits teilweise Typ-, Clamp- und Defaultlogik. Diese Informationen können bei der Erstellung eines Config-Schemas helfen, sollten langfristig aber nicht nur durch Sourcecode-Parsing dokumentiert werden.

### UI

Vorhandene Konfigurationsansichten enthalten bereits Labels und semantische Zuordnungen. Sie sind eine gute Quelle zur Initialbefüllung von Dokumentation und Übersetzungen, sollten aber langfristig nicht die einzige maschinenlesbare Dokumentationsquelle sein.

### bestehende `docs/*.md`

Vorhandene Design-/Konzeptdokumente liefern technischen Hintergrund für Architektur-, Worker- und Recognition-Dokumentation. Benutzerhilfe sollte daraus redaktionell verdichtet werden, nicht direkt ungefiltert veröffentlicht werden.

---

## 20. Priorität der Quellen

Empfohlene Rangfolge:

1. **laufzeitrelevante Primärquelle** – z. B. `INFO.sh`, `var/config.json`
2. **strukturierte Dokumentationsmetadaten** – Schema, Features, Navigation
3. **sprachliche Quellen** – DE/EN i18n und Markdown
4. **GitHub-Daten** – Releases, Issues, CI
5. **Quellcodeanalyse** – nur zur Validierung oder Migration, nicht als dauerhafte Hauptquelle für Benutzertexte

Damit wird verhindert, dass Dokumentationsgeneratoren zu stark von zufälligen Implementierungsdetails abhängig werden.

---

## 21. Empfohlener Generatoraufbau

```text
scripts/docs/
├── collect_package_metadata.py
├── collect_config_metadata.py
├── validate_docs.py
├── build_model.py
├── render_web.py
├── render_dsm_help.py
└── check_package_help.py
```

Alternativ ein gemeinsames CLI:

```text
python -m tools.docs validate
python -m tools.docs build-model
python -m tools.docs build-web
python -m tools.docs build-dsm
python -m tools.docs test
```

Das neutrale Modell ist der wichtigste Teil:

```text
sources
   ↓
normalized documentation model
   ├── web renderer
   └── DSM renderer
```

Die Renderer sollen möglichst keine eigene Geschäftslogik enthalten.

---

## 22. Beispiel des neutralen Dokumentationsmodells

```json
{
  "package": {
    "name": "AV_ImgData",
    "displayName": "ImgData",
    "version": "0.10.1",
    "dsmAppName": "SYNO.SDS.App.AV_ImgData.Instance",
    "dsmUiDir": "ui",
    "minimumDsm": "7.3-00000"
  },
  "languages": {
    "de": "ger",
    "en": "enu"
  },
  "navigation": [],
  "features": [],
  "configuration": []
}
```

Dieses Modell kann als JSON-Buildartefakt ausgegeben und in Tests gespeichert werden.

---

## 23. Umgang mit Versionsinformationen

Die aktuelle Paketversion liegt derzeit in `INFO.sh`.

Für Releases sollten folgende Werte konsistent sein:

```text
INFO.sh version
Git Tag
GitHub Release
SPK-Dateiname
GitHub Page
DSM-Hilfe Versionsanzeige, falls vorhanden
```

Ein CI-Test sollte Abweichungen erkennen.

Die DSM-Hilfe muss die Version nicht auf jeder Seite anzeigen. Wenn sie angezeigt wird, darf sie nur aus dem generierten Paketmodell stammen.

---

## 24. GitHub Pages und DSM-Hilfe bewusst unterschiedlich rendern

Die Inhalte sind gemeinsam, die Darstellung nicht.

### GitHub Pages

Geeignet für:

- responsive Layout
- Suche
- Sprachumschalter
- große Screenshots
- Release-Boxen
- Tabellen
- externe Links
- umfangreiche Navigation

### DSM-Hilfe

Geeignet für:

- kurze, direkte Bedienhilfe
- DSM-konformes HTML
- kompakte Screenshots
- klare Hierarchie
- keine unnötigen JavaScript-Abhängigkeiten
- möglichst wenig externe Ressourcen

Das Quell-Markdown kann deshalb optionale Renderer-Hinweise unterstützen, aber die Grundtexte bleiben gemeinsam.

---

## 25. Automatische Aktualisierung

### Bei Config-Änderung

```text
var/config.json geändert
        ↓
Config-Modell neu erzeugen
        ↓
Website Config Reference neu erzeugen
        ↓
DSM Config Help neu erzeugen
        ↓
Tests
```

### Bei Dokumentationsänderung

```text
Markdown/i18n/navigation geändert
        ↓
Website + DSM-Hilfe neu bauen
        ↓
Tests
```

### Bei Release

```text
Tag / Release
        ↓
Paketdaten prüfen
        ↓
DSM-Hilfe bauen
        ↓
SPK bauen
        ↓
Release veröffentlichen
        ↓
GitHub Pages mit Release-Daten neu bauen
```

---

## 26. Konkrete erste Ausbaustufe

### Phase 1 – DSM-Hilfe technisch integrieren

- `navigation.yml` definieren
- DE/EN Basisseiten definieren
- i18n DE/EN definieren
- Generator für `helptoc.conf`
- Generator für `strings`
- Markdown → DSM HTML
- Strukturtests

### Phase 2 – gemeinsame GitHub-Pages-Basis

- dieselben Markdown-Quellen in Website einbinden
- Navigation aus derselben YAML erzeugen
- Sprachumschalter
- gemeinsame Assets

### Phase 3 – Config automatisieren

- Defaults aus `var/config.json`
- Schema/Metadaten ergänzen
- DE/EN Beschreibungen
- Config-Referenz für beide Ausgaben
- Coverage-Test

### Phase 4 – Paket-/Release-Daten

- `INFO.sh` Parser
- GitHub Releases
- Downloadinformationen
- Worker-Metadaten

### Phase 5 – Integrationschecks

- SPK-Inhalt prüfen
- optional Testinstallation auf NAS
- DSM-Hilfe in ger/enu testen

---

## 27. Entscheidender Architekturgrundsatz

Die Zielstruktur soll nicht sein:

```text
Website-Dokumentation
DSM-Hilfe
UI-Hilfe
Config-Dokumentation
README
```

mit fünf unabhängig gepflegten Informationsbeständen.

Stattdessen:

```text
               zentrale Quellen
                    │
      ┌─────────────┼─────────────┐
      │             │             │
 technische     Sprache/Docs   GitHub-Daten
 Daten                           Releases
      │             │             │
      └─────────────┼─────────────┘
                    ▼
          neutrales Docs-Modell
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
 GitHub Pages    DSM Help      Tests/UI
```

Damit können GitHub Pages und DSM-Hilfe dauerhaft gemeinsam wachsen, ohne dass jede neue Funktion mehrfach dokumentiert werden muss.

---

## 28. Empfehlung

Für das Projekt ist eine **gemeinsame Markdown-/Metadatenbasis mit zwei Renderern** die sinnvollste Lösung.

Technische Primärdaten sollen aus bestehenden Paketquellen gelesen werden. Navigation, Feature-Metadaten und Dokumentationsbeschreibungen werden strukturiert ergänzt. Deutsch und Englisch werden parallel gepflegt. Der Build erzeugt daraus sowohl die öffentliche GitHub-Page als auch die DSM-native Hilfe.

Besonders wichtig ist, die automatische Pflege nicht nur über Generatoren, sondern durch CI-Tests abzusichern. Neue Config-Keys, neue Feature-Seiten oder Navigationsänderungen sollen dadurch nicht veröffentlicht werden können, wenn Website und DSM-Hilfe auseinanderlaufen.
