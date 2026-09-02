# Konzept: Gemeinsamer Documentation Core für DSM-Hilfe und GitHub Pages

## 1. Ziel

Für ImgData soll eine gemeinsame Dokumentationsarchitektur entstehen, aus der sowohl die in DSM integrierte Anwendungshilfe als auch die öffentliche GitHub-Page erzeugt werden.

Die zentrale Idee lautet:

> **Die fachliche Dokumentation wird nur einmal gepflegt. DSM-Hilfe und GitHub Pages sind zwei unterschiedliche Ausgaben derselben Documentation Core.**

Damit werden insbesondere folgende Ziele verfolgt:

- keine doppelte Pflege identischer Hilfetexte
- vollständige Dokumentation auf Deutsch und Englisch
- automatische Übernahme technischer Daten aus dem Paket
- automatische Übernahme von Konfigurationswerten und Defaults
- automatische Release- und Versionsinformationen auf der Website
- automatisch erzeugte DSM-Hilfe gemäß Synology-Vorgaben
- einheitliche Navigation und konsistente Benennung
- automatische Prüfungen auf Vollständigkeit, fehlende Übersetzungen und veraltete Dokumentation
- möglichst geringe zusätzliche Pflege bei neuen Features, Config-Optionen oder Releases

Die Website soll die Hilfe damit nicht lediglich kopieren. Beide Ausgaben greifen auf dieselbe fachliche Quelle zu und ergänzen sie je nach Zielplattform um plattformspezifische Inhalte.

---

## 2. Offizielle DSM-Hilfe als technische Randbedingung

Synology beschreibt für die Integration einer Anwendungshilfe in DSM im Wesentlichen drei Bausteine:

1. eine `helptoc.conf` unterhalb des in `INFO` angegebenen `dsmuidir`
2. sprachabhängige Hilfe-Dokumente unter `help/<locale>/`
3. sprachabhängige i18n-Texte unter `texts/<locale>/strings`

Für ImgData ist in `INFO.sh` bereits definiert:

```bash
package="AV_ImgData"
version="0.11.0"
displayname="ImgData"
dsmappname="SYNO.SDS.App.AV_ImgData.Instance"
dsmuidir="ui"
```

Daraus ergibt sich als DSM-Zielstruktur:

```text
ui/
├── helptoc.conf
├── help/
│   ├── ger/
│   │   ├── index.html
│   │   └── ...
│   └── enu/
│       ├── index.html
│       └── ...
└── texts/
    ├── ger/
    │   └── strings
    └── enu/
        └── strings
```

Die `helptoc.conf` beschreibt die Baumstruktur der DSM-Hilfe. `title`-Felder können über DSM-i18n-Schlüssel wie `app_tree:index_title` aufgelöst werden. Die eigentlichen Hilfeseiten müssen als HTML vorliegen und das von Synology erwartete Help-CSS bzw. die Help-Skripte einbinden.

Referenz:

- Synology Developer Guide: `https://help.synology.com/developer-guide/integrate_dsm/dsm_help.html`

Diese DSM-Ausgabedateien sollen **nicht manuell gepflegt**, sondern vollständig aus dem Documentation Core generiert werden.

---

## 3. Zielarchitektur

```text
                           Repository
                              │
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
   Fachliche Docs       technische Quellen     GitHub-Daten
   DE / EN Markdown     INFO.sh, config,        Releases, Tags,
                        Feature-Metadaten        Issues, Actions
          │                   │                    │
          └───────────────────┼────────────────────┘
                              ▼
                    Documentation Core Build
                              │
                    normalisiertes Datenmodell
                              │
              ┌───────────────┴────────────────┐
              │                                │
              ▼                                ▼
        DSM Help Renderer                Web Renderer
              │                                │
              ▼                                ▼
      ui/helptoc.conf                    GitHub Pages
      ui/help/ger/*.html                 /de/...
      ui/help/enu/*.html                 /en/...
      ui/texts/*/strings
```

Die Trennung ist wichtig:

- **Quellen** werden gepflegt.
- **Documentation Core** normalisiert und verknüpft die Quellen.
- **Renderer** erzeugen plattformspezifische Ausgaben.
- **Generierte Dateien** werden nicht manuell verändert.

---

## 4. Grundprinzip: Single Source of Truth

Für jede Information wird genau eine führende Quelle definiert.

### 4.1 Technische Daten

Technische Werte werden nicht in Markdown dupliziert.

Beispiele:

- Paketversion → `INFO.sh`
- Paketname → `INFO.sh`
- Mindest-DSM-Version → `INFO.sh`
- Architektur → Build-/Paketinformation
- Config-Default → `var/config.json` bzw. zukünftig Schema
- Release-Version → GitHub Release / Tag
- Download-Asset → GitHub Release Asset

### 4.2 Fachliche Texte

Benutzerorientierte Erklärungen werden im Documentation Core gepflegt:

- Installation
- Bedienung
- Gesichtserkennung
- Personenprofile
- Profilreferenzbilder
- Konfiguration
- Datenbankfunktionen
- External Worker
- Fehlerbehebung
- Hintergrundinformationen

### 4.3 Navigation

Auch die Navigation wird nur einmal definiert und anschließend für beide Ausgaben transformiert.

### 4.4 Übersetzungen

Deutsch und Englisch besitzen dieselbe Dokument-ID und dieselbe semantische Struktur. Nur die sprachlichen Inhalte unterscheiden sich.

---

## 5. Empfohlene Repository-Struktur

```text
docs/
├── core/
│   ├── de/
│   │   ├── index.md
│   │   ├── installation.md
│   │   ├── configuration.md
│   │   ├── troubleshooting.md
│   │   ├── features/
│   │   │   ├── recognition.md
│   │   │   ├── profiles.md
│   │   │   ├── profile-reference-images.md
│   │   │   ├── database.md
│   │   │   └── external-worker.md
│   │   └── concepts/
│   │       └── architecture.md
│   │
│   └── en/
│       └── gleiche logische Struktur
│
├── metadata/
│   ├── navigation.yml
│   ├── features.yml
│   ├── documentation.yml
│   └── config-docs.yml
│
├── i18n/
│   ├── de.yml
│   └── en.yml
│
├── assets/
│   ├── icons/
│   ├── screenshots/
│   └── diagrams/
│
├── generated/
│   ├── package.json
│   ├── configuration.json
│   ├── releases.json
│   ├── features.json
│   └── documentation-model.json
│
├── templates/
│   ├── dsm-help-page.html
│   └── web/
│
├── dm-github-pages-concept.md
├── dm-documentation-dsm-help-concept.md
└── dm-documentation-core-concept.md

scripts/
├── docs_collect.py
├── docs_validate.py
├── docs_render_dsm.py
├── docs_render_web.py
└── docs_build.py
```

`docs/core`, `docs/metadata`, `docs/i18n` und `docs/assets` sind Quellen.

`docs/generated`, `ui/help`, `ui/texts` und die finale Website sind Build-Produkte.

---

## 6. Dokumentidentität statt Dateipfad als fachliche Referenz

Jede Dokumentationsseite erhält eine stabile ID.

Beispiel:

```yaml
---
id: external-worker
section: features
title_key: docs.external_worker.title
targets:
  - dsm
  - web
order: 50
---
```

Die Datei kann dann beispielsweise unter

```text
docs/core/de/features/external-worker.md
```

liegen, ihre fachliche Identität ist aber `external-worker`.

Dadurch können interne Links sprach- und rendererunabhängig formuliert werden.

Beispiel im Quelltext:

```text
[[doc:configuration]]
```

Der DSM-Renderer erzeugt daraus einen DSM-Hilfe-Link, der Web-Renderer einen Web-Link in der passenden Sprache.

Das verhindert, dass Quelltexte feste HTML- oder Website-Pfade enthalten.

---

## 7. Front Matter der Dokumente

Empfohlenes Minimalmodell:

```yaml
---
id: recognition
section: features
title_key: docs.recognition.title
targets:
  - dsm
  - web
order: 10
status: stable
keywords:
  - face recognition
  - gesichtserkennung
---
```

Optional:

```yaml
web:
  featured: true
  show_release_banner: false

dsm:
  toc: true
  filename: recognition.html
```

Normalerweise sollten Dateinamen und Zielpfade jedoch automatisch aus `id` generiert werden.

---

## 8. Target-Modell

Nicht jede Seite muss in beiden Ausgaben erscheinen.

### Gemeinsame Inhalte

```yaml
targets:
  - dsm
  - web
```

Typische Beispiele:

- Bedienung
- Installation
- Konfiguration
- Features
- External Worker
- Troubleshooting

### Nur Website

```yaml
targets:
  - web
```

Typische Beispiele:

- Download
- Release-Historie
- Roadmap
- GitHub Issues
- Buildstatus
- Developer Notes

### Nur DSM

```yaml
targets:
  - dsm
```

Nur verwenden, wenn ein Thema tatsächlich ausschließlich im DSM-Kontext sinnvoll ist, beispielsweise ein sehr spezifischer Hinweis zur Bedienung im DSM-Fenster.

Der Normalfall sollte `dsm + web` sein.

---

## 9. Sprachmodell

### 9.1 Unterstützte Sprachen

Zunächst:

- Deutsch
- Englisch

Interne Locale-Bezeichnungen:

```text
Documentation Core: de / en
DSM:                ger / enu
Website:            de / en
```

Die Abbildung wird zentral definiert:

```yaml
languages:
  de:
    dsm_locale: ger
    web_locale: de
  en:
    dsm_locale: enu
    web_locale: en
```

### 9.2 Seitenpaarigkeit

Zu jeder gemeinsamen Dokument-ID muss eine deutsche und eine englische Variante existieren.

Beispiel:

```text
docs/core/de/features/recognition.md
docs/core/en/features/recognition.md
```

Beide Dateien müssen dieselbe `id` verwenden.

### 9.3 Sprachneutrale Daten

Folgende Werte werden nie separat pro Sprache gepflegt:

- Version
- Defaultwerte
- Zahlenbereiche
- DSM-Version
- Dateigröße
- Architektur
- Release-URLs
- interne IDs
- Statuswerte

Nur ihre Beschriftung ist lokalisiert.

---

## 10. Zentrale i18n-Dateien

Kurze Texte und Generatorbeschriftungen sollten nicht in jedem Markdown-Dokument wiederholt werden.

Beispiel `docs/i18n/de.yml`:

```yaml
docs:
  index:
    title: ImgData Hilfe
  recognition:
    title: Gesichtserkennung
  external_worker:
    title: External Worker

labels:
  default: Standardwert
  minimum: Minimum
  maximum: Maximum
  current_release: Aktuelle Version
```

Englisch entsprechend in `en.yml`.

Aus diesen Dateien kann der DSM-Renderer zusätzlich die benötigten `strings`-Dateien erzeugen.

---

## 11. Generierung der DSM-`strings`

Für DSM wird aus der gemeinsamen i18n-Quelle beispielsweise erzeugt:

```text
ui/texts/ger/strings
ui/texts/enu/strings
```

Beispielinhalt:

```ini
[app_tree]
index_title="ImgData Hilfe"
recognition="Gesichtserkennung"
configuration="Konfiguration"
external_worker="External Worker"
```

Englisch:

```ini
[app_tree]
index_title="ImgData Help"
recognition="Face Recognition"
configuration="Configuration"
external_worker="External Worker"
```

Damit stammen Website-Titel, DSM-Navigation und Hilfetitel aus denselben Übersetzungsschlüsseln.

---

## 12. Navigation als gemeinsame Quelle

Empfohlen wird `docs/metadata/navigation.yml`.

Beispiel:

```yaml
root:
  id: index
  children:
    - id: installation
    - id: recognition
      children:
        - id: profiles
        - id: profile-reference-images
    - id: configuration
    - id: external-worker
    - id: troubleshooting
```

Aus derselben Struktur entstehen:

- DSM `helptoc.conf`
- Website-Hauptnavigation
- vorherige/nächste Seite
- Breadcrumbs
- optionale Inhaltsübersichten

### DSM-Ausgabe

Beispiel:

```json
{
  "app": "SYNO.SDS.App.AV_ImgData.Instance",
  "title": "app_tree:index_title",
  "content": "index.html",
  "toc": [
    {
      "title": "app_tree:installation",
      "content": "installation.html"
    }
  ]
}
```

`app` wird nicht manuell in `navigation.yml` eingetragen, sondern aus `INFO.sh:dsmappname` übernommen.

Damit ist auch diese Information Single Source of Truth.

---

## 13. DSM-Hilfe-Renderer

Der DSM-Renderer übernimmt das normalisierte Dokumentmodell und erzeugt DSM-kompatibles HTML.

### 13.1 Template

Grundtemplate entsprechend Synology:

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
  <!-- gerenderter Dokumentinhalt -->
</body>
</html>
```

### 13.2 Markdown-Untermenge

Für gemeinsame Dokumente sollte eine definierte Markdown-Untermenge verwendet werden, die beide Renderer zuverlässig unterstützen:

- Überschriften
- Absätze
- Listen
- Tabellen
- Codeblöcke
- Bilder
- Hinweise / Notes
- interne Dokumentlinks
- externe Links

Website-spezifische HTML-Fragmente im gemeinsamen Markdown sollten vermieden werden.

### 13.3 DSM-spezifische Anpassungen

Der Renderer übernimmt:

- DSM-HTML-Wrapper
- Auflösung interner Dokumentlinks
- Bildpfade
- DSM-kompatible Tabellen
- Entfernen rein webbezogener Elemente
- korrekte Sprache und Zieldatei

---

## 14. Web-Renderer / GitHub Pages

Die Website verwendet denselben Core-Inhalt, darf ihn aber stärker anreichern.

Empfohlen bleibt:

```text
Markdown
+
MkDocs
+
Material for MkDocs oder vergleichbares Theme
+
Generator-Skripte
+
GitHub Pages
```

Der Web-Renderer erhält zusätzlich Daten wie:

- aktuelles GitHub Release
- SPK-Download
- Release-Historie
- Screenshots
- GitHub Issues / Roadmap
- Buildstatus
- Repository-Link

### Website-Struktur

```text
/de/
/en/
```

Der Sprachumschalter versucht immer, dieselbe Dokument-ID in der anderen Sprache zu öffnen.

---

## 15. Quellenmatrix

| Information | Führende Quelle | Core | DSM Help | Website | Test |
|---|---|---:|---:|---:|---|
| Paket-ID | `INFO.sh package` | ✓ | optional | ✓ | Parser-Test |
| Anzeigename | `INFO.sh displayname` | ✓ | ✓ | ✓ | Parser-Test |
| Version | `INFO.sh version` / Release-Abgleich | ✓ | optional | ✓ | Versionskonsistenz |
| DSM App-ID | `INFO.sh dsmappname` | ✓ | `helptoc.conf` | optional | exakter Match |
| DSM UI Dir | `INFO.sh dsmuidir` | ✓ | Zielpfad | – | Pfadtest |
| Mindest-DSM | `INFO.sh os_min_ver` | ✓ | ✓ | ✓ | Parser-Test |
| Paketbeschreibung | `INFO.sh description_*` | ✓ | optional | ✓ | Locale-Test |
| Hauptdokumentation | `docs/core/<lang>` | ✓ | ✓ | ✓ | Pair-/Render-Test |
| Navigation | `navigation.yml` | ✓ | `helptoc.conf` | Navigation | Graph-Test |
| kurze Übersetzungen | `docs/i18n/*.yml` | ✓ | `strings` | Labels | Key-Parität |
| Config Defaults | `var/config.json` | ✓ | ✓ | ✓ | Coverage-Test |
| Config Typ/Range | Schema / Config-Service | ✓ | ✓ | ✓ | Schema-Test |
| Config Beschreibung | `config-docs.yml` + i18n | ✓ | ✓ | ✓ | Coverage-Test |
| Feature-Liste | `features.yml` | ✓ | ✓ | ✓ | Referenz-Test |
| Feature Beschreibung | Core Markdown | ✓ | ✓ | ✓ | Dokument-ID-Test |
| Screenshots | `docs/assets` | ✓ | optional | ✓ | Asset-Test |
| Release | GitHub Releases | ✓ | optional | ✓ | API-/Fixture-Test |
| Download | Release Asset | ✓ | – | ✓ | Asset-Regel-Test |
| Changelog | definierte Changelog-Quelle | ✓ | optional | ✓ | Versions-Test |
| Known Issues | GitHub Issues/Labels | optional | – | ✓ | optional |
| Buildstatus | GitHub Actions | optional | – | ✓ | optional |

---

## 16. Konfiguration als besonders wichtige gemeinsame Quelle

Die vorhandene Konfiguration ist bereits eine starke Datenquelle. In `var/config.json` existieren beispielsweise Werte wie:

```text
analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON
analysis.CHECKS.RECOGNITION_MAX_PROFILE_REFERENCE_FACES_PER_PERSON
analysis.CHECKS.RECOGNITION_BATCH_SIZE
```

Diese Defaults dürfen nicht separat in DSM-Hilfe und Website eingetragen werden.

### Zielmodell

Langfristig sollte jede dokumentierbare Config-Option folgende Informationen besitzen:

```yaml
path: analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON
type: integer
minimum: 2
maximum: 1000
default_source: var/config.json
category: recognition
title_key: config.recognition_min_faces.title
description_key: config.recognition_min_faces.description
advanced: true
```

Der Default wird **nicht** in dieser Datei wiederholt, sondern beim Build aus der tatsächlichen Konfiguration gelesen.

### Ausgaben

DSM und Website erzeugen daraus beispielsweise:

```text
Minimale Anzahl Gesichter pro Person
Standardwert: 3
Bereich: 2–1000
```

bzw.

```text
Minimum faces per person
Default: 3
Range: 2–1000
```

---

## 17. Config-Schema als langfristiger Zielzustand

Ein strukturiertes Schema wäre perspektivisch die beste technische Quelle.

Beispiel:

```json
{
  "analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON": {
    "type": "integer",
    "minimum": 2,
    "maximum": 1000,
    "defaultFrom": "var/config.json",
    "documentation": "config.recognition_min_faces"
  }
}
```

Dasselbe Schema kann künftig genutzt werden für:

1. Laufzeitvalidierung
2. UI-Validierung
3. Dokumentationsgenerierung
4. Tests
5. Default-Abgleich
6. Migrationsprüfungen

Damit wird Dokumentation Teil des technischen Vertrags und nicht nur Begleittext.

---

## 18. Feature-Metadaten

Eine zentrale `features.yml` sollte die verfügbaren Benutzerfunktionen beschreiben.

Beispiel:

```yaml
features:
  recognition:
    title_key: features.recognition.title
    doc_id: recognition
    icon: recognition.png
    status: stable

  profiles:
    title_key: features.profiles.title
    doc_id: profiles
    icon: profiles.png
    status: stable

  external_worker:
    title_key: features.external_worker.title
    doc_id: external-worker
    icon: external-worker.png
    status: beta
```

Diese Datei kann verwendet werden für:

- Website-Feature-Kacheln
- automatische Feature-Übersichten
- DSM-Hilfe-Übersichten
- Prüfung, ob jedes Feature dokumentiert ist
- Statusanzeigen

---

## 19. Generated Documentation Model

Zwischen Quellen und Renderer sollte ein normalisiertes JSON-Modell erzeugt werden.

Beispiel:

```json
{
  "package": {
    "name": "AV_ImgData",
    "displayName": "ImgData",
    "version": "0.11.0",
    "dsmAppName": "SYNO.SDS.App.AV_ImgData.Instance",
    "minDsm": "7.4-00000"
  },
  "languages": ["de", "en"],
  "documents": [],
  "navigation": {},
  "configuration": [],
  "features": [],
  "release": {}
}
```

Vorteile:

- Renderer sind voneinander unabhängig.
- Collector und Validierung lassen sich separat testen.
- Builds werden reproduzierbar.
- Fehler können vor dem Rendering erkannt werden.
- spätere weitere Targets sind möglich.

---

## 20. Build-Pipeline

Empfohlener Ablauf:

```text
1. collect
   │
   ├── INFO.sh lesen
   ├── var/config.json lesen
   ├── Metadata laden
   ├── i18n laden
   ├── Markdown lesen
   └── optional GitHub-Daten laden
   │
   ▼
2. normalize
   │
   └── documentation-model.json
   │
   ▼
3. validate
   │
   ├── Dokumente
   ├── Sprachen
   ├── Links
   ├── Config-Abdeckung
   ├── Navigation
   └── technische Konsistenz
   │
   ▼
4. render DSM
   │
   ├── ui/helptoc.conf
   ├── ui/help/ger/*.html
   ├── ui/help/enu/*.html
   └── ui/texts/*/strings
   │
   ▼
5. render Web
   │
   └── MkDocs / site
   │
   ▼
6. package / deploy
```

Ein einziger Einstiegspunkt sollte genügen:

```bash
python scripts/docs_build.py
```

Optional:

```bash
python scripts/docs_build.py --target dsm
python scripts/docs_build.py --target web
python scripts/docs_build.py --validate-only
```

---

## 21. Verhalten bei Offline-Builds

Der DSM-Paketbuild darf nicht zwingend vom GitHub-Netzwerkzugriff abhängen.

Daher sind zwei Datenklassen zu unterscheiden.

### Lokale Pflichtquellen

- `INFO.sh`
- Konfiguration
- Markdown
- Navigation
- i18n
- Assets

Diese müssen für DSM vollständig ausreichen.

### Externe optionale Quellen

- GitHub Releases
- Issues
- Actions

Diese werden primär für die Website benötigt.

Der DSM-Renderer darf deshalb niemals fehlschlagen, nur weil GitHub nicht erreichbar ist.

---

## 22. Release-Daten

Für die Website werden GitHub Releases als Quelle verwendet.

Automatisch darstellbar:

- neueste stabile Version
- Veröffentlichungsdatum
- Release Notes
- Stable/Beta
- SPK-Datei
- Debug-SPK
- Dateigröße
- Download-Link

Die Release-Asset-Auswahl sollte über feste Regeln getestet werden.

Beispiel:

```text
Stable Package:
*.spk, aber nicht *_debug.spk

Debug Package:
*_debug.spk
```

---

## 23. DSM-Hilfe und Release-Information

Die DSM-Hilfe sollte nicht bei jeder Version mit umfangreichen Release-Daten angereichert werden.

Sinnvoll sind maximal:

- Paketversion im Hilfe-Startbereich
- Link zur Website / Releases, falls gewünscht

Der eigentliche Release-Bereich bleibt web-spezifisch.

Damit bleibt die integrierte Hilfe kompakt und offline verwendbar.

---

## 24. Bilder und Screenshots

Assets liegen zentral unter:

```text
docs/assets/
```

Metadaten können festlegen, in welchen Targets sie sinnvoll sind.

Beispiel:

```yaml
id: screenshot-profile
file: screenshots/profile.png
targets:
  - web
  - dsm
caption_key: screenshots.profile.caption
```

Der Renderer kopiert oder transformiert Pfade passend zum Ziel.

Screenshots mit sprachabhängiger UI können optional separat geführt werden:

```text
screenshots/de/profile.png
screenshots/en/profile.png
```

Dies sollte nur dort erfolgen, wo die Lokalisierung für das Verständnis relevant ist.

---

## 25. Interne Verweise

Quelltexte sollten keine festen Ausgabe-URLs verwenden.

Nicht empfohlen:

```markdown
[Konfiguration](../configuration.html)
```

Empfohlen:

```text
[[doc:configuration]]
```

oder ein Markdown-Plugin mit semantischem Link-Schema.

Der Renderer kennt:

- Ziel
- Sprache
- tatsächlichen Dateipfad

und erzeugt den korrekten Link.

---

## 26. Externe Links

Externe Links bleiben normale URLs.

Der Validator sollte prüfen:

- syntaktisch gültige URL
- optional periodische Linkprüfung in CI

Eine externe Linkprüfung darf jedoch wegen temporärer Netzwerkfehler nicht zwingend jeden Paketbuild blockieren. Sie eignet sich besser als separater CI-Job.

---

## 27. Web-spezifische Komponenten

Die Website darf zusätzliche Komponenten um den Core-Inhalt herum darstellen:

- Release-Banner
- Download-Button
- Feature-Kacheln
- Screenshots
- GitHub Links
- Roadmap
- Known Issues
- Buildstatus

Diese Informationen werden nicht in den gemeinsamen Hilfetext hineingeschrieben.

Beispiel:

```text
Web Layout
├── Release Banner          ← GitHub Release
├── Core Document           ← docs/core
├── Related Features        ← features.yml
└── GitHub Links            ← Repository metadata
```

---

## 28. DSM-spezifische Komponenten

DSM erhält dagegen:

```text
DSM Help Page
├── DSM Help Wrapper
├── Dokumenttitel
├── Core Document
└── ggf. kompakte Versionsinfo
```

Keine Webnavigation, keine Download-Kacheln und keine GitHub-UI werden in DSM gerendert.

---

## 29. Teststrategie

Die Dokumentationspipeline muss wie produktiver Code behandelt werden.

Es gibt fünf Testebenen:

1. Quellen-/Parser-Tests
2. Modell-/Konsistenztests
3. Renderer-Tests
4. Artefakt-/Strukturtests
5. DSM-Integrationstest auf einem echten NAS

---

## 30. Parser-Tests

### INFO.sh

Prüfen:

- `package` vorhanden
- `version` vorhanden
- `displayname` vorhanden
- `dsmappname` vorhanden
- `dsmuidir` vorhanden
- `os_min_ver` vorhanden
- deutsche und englische Beschreibung vorhanden

Beispiel:

```text
FAIL: INFO.sh missing dsmappname
```

### Config

Prüfen:

- JSON valide
- erwartete Struktur vorhanden
- Defaultwerte lesbar

---

## 31. Dokument-ID-Tests

Prüfen:

- jede ID eindeutig
- jede deutsche Seite hat englische Entsprechung
- beide Sprachvarianten haben dieselbe ID
- keine unbekannte ID in Navigation
- keine unbekannte ID in internen Links

Beispiele:

```text
FAIL: Duplicate document id: recognition
```

```text
FAIL: Missing English document for id: external-worker
```

---

## 32. Übersetzungstests

Prüfen:

- Schlüsselmenge DE = Schlüsselmenge EN
- jeder in Navigation verwendete `title_key` vorhanden
- jeder Config-Beschreibungsschlüssel vorhanden
- jeder Feature-Titel vorhanden

Beispiel:

```text
FAIL: Missing en translation:
config.recognition_min_faces.description
```

---

## 33. Navigationstests

`navigation.yml` wird als Graph behandelt.

Prüfen:

- Root vorhanden
- keine Zyklen
- keine doppelte Position desselben Knotens, sofern nicht explizit erlaubt
- jede ID existiert
- jedes DSM-Dokument mit `dsm`-Target ist erreichbar
- jedes Web-Hauptdokument ist erreichbar

Optional:

```text
WARN: document 'architecture' is not linked from web navigation
```

---

## 34. Config-Dokumentationsabdeckung

Dies ist einer der wichtigsten Tests.

Für definierte dokumentationspflichtige Bereiche wird geprüft:

```text
Config-Key vorhanden
        ↓
Dokumentationsmetadaten vorhanden?
        ↓
DE-Beschreibung vorhanden?
        ↓
EN-Beschreibung vorhanden?
```

Beispiel:

```text
FAIL: undocumented config key:
analysis.CHECKS.RECOGNITION_MAX_PROFILE_REFERENCE_FACES_PER_PERSON
```

Damit kann ein neuer Konfigurationsparameter nicht unbemerkt ohne Hilfe veröffentlicht werden.

Nicht alle internen Parameter müssen dokumentiert werden. Dafür kann ein expliziter Marker verwendet werden:

```yaml
documentation: internal
```

oder

```yaml
documentation: hidden
```

Damit ist das Fehlen bewusst statt zufällig.

---

## 35. Default-Konsistenztests

Ein dokumentierter Default darf nicht manuell vom tatsächlichen Default abweichen.

Deshalb wird der Default ausschließlich aus der Laufzeitquelle geladen.

Zusätzlich kann geprüft werden, ob bestehende Defaults in mehreren Codebereichen übereinstimmen, soweit dies bereits Teil der Paketstruktur ist.

Beispiel:

```text
FAIL: Config default mismatch:
var/config.json = 3
config_service.py = 5
```

Der Docs-Build kann bestehende Strukturtests ergänzen, sollte aber möglichst dieselbe Prüflogik wiederverwenden und keine zweite Wahrheit schaffen.

---

## 36. DSM-Renderer-Tests

Prüfen:

- `ui/helptoc.conf` ist valides JSON
- `app` entspricht exakt `INFO.sh:dsmappname`
- alle `content`-Dateien existieren in `ger` und `enu`
- jeder `title`-i18n-Key existiert in beiden `strings`
- HTML besitzt erwarteten DSM-Wrapper
- Charset ist UTF-8
- Help-CSS wird eingebunden
- Flexcroll-Dateien werden entsprechend Synology-Vorgabe eingebunden
- interne Links zeigen auf vorhandene Hilfe-Seiten

---

## 37. Web-Renderer-Tests

Prüfen:

- `/de/` und `/en/` werden erzeugt
- jede gemeinsame Dokument-ID existiert in beiden Sprachen
- Sprachwechsel zeigt auf äquivalente ID
- interne Links sind gültig
- Assets existieren
- Release-Komponente kann ohne GitHub-Daten kontrolliert degradiert werden
- Release-Daten entsprechen Fixture/API

---

## 38. Snapshot-/Golden-Master-Tests

Für zentrale Generatorausgaben sind kleine Snapshot-Tests sinnvoll.

Beispiele:

- `helptoc.conf`
- ein deutsches DSM-Hilfe-Dokument
- ein englisches DSM-Hilfe-Dokument
- generierte Config-Tabelle
- normalisiertes Dokumentmodell

Damit fallen unbeabsichtigte Formatänderungen früh auf.

Snapshots sollten sich auf stabile, kleine Testfixtures beziehen, nicht auf das komplette echte Repository.

---

## 39. Build-Reproduzierbarkeit

Lokale Pflichtquellen müssen einen reproduzierbaren DSM-Help-Build ergeben.

Test:

```text
Build 1 → Hash A
Build 2 → Hash A
```

Zeitstempel oder zufällige IDs sollten nicht unnötig in generierte Inhalte einfließen.

Für Webdaten aus GitHub werden im Test Fixtures statt Live-Abfragen verwendet.

---

## 40. Paketstruktur-Test

Nach dem DSM-Paketbuild wird geprüft, ob im Paket enthalten sind:

```text
ui/helptoc.conf
ui/help/ger/index.html
ui/help/enu/index.html
ui/texts/ger/strings
ui/texts/enu/strings
```

Zusätzlich:

- alle in `helptoc.conf` referenzierten Dateien
- alle von Hilfe-Seiten benötigten lokalen Assets

---

## 41. Integrationstest auf DSM

Der automatisierte Strukturtest ersetzt keinen echten DSM-Test vollständig.

Mindestens vor Freigaben sollte geprüft werden:

1. SPK auf Test-NAS installieren
2. ImgData starten
3. DSM-Hilfe öffnen
4. Anwendungshilfe von ImgData sichtbar
5. deutsche Sprache auswählen
6. Navigation vollständig
7. Seiten öffnen korrekt
8. englische Sprache auswählen
9. Navigation vollständig
10. interne Links und Bilder testen

Dieser Test kann zunächst manuell dokumentiert werden.

Später kann der bestehende automatisierte Installationsprozess auf dem NAS um eine einfache Dateiprüfung nach Installation ergänzt werden.

---

## 42. CI-Testmatrix

| Test | Pull Request | Main | Release | echter NAS |
|---|---:|---:|---:|---:|
| Markdown parse | ✓ | ✓ | ✓ | – |
| IDs / Pairing | ✓ | ✓ | ✓ | – |
| i18n-Parität | ✓ | ✓ | ✓ | – |
| Navigation | ✓ | ✓ | ✓ | – |
| Config Coverage | ✓ | ✓ | ✓ | – |
| DSM Render | ✓ | ✓ | ✓ | – |
| Web Render | ✓ | ✓ | ✓ | – |
| Linkcheck intern | ✓ | ✓ | ✓ | – |
| externer Linkcheck | optional | ✓ | optional | – |
| Paketstruktur | – | ✓ | ✓ | – |
| DSM-Hilfe sichtbar | – | optional | empfohlen | ✓ |
| Sprachwechsel DSM | – | – | empfohlen | ✓ |

---

## 43. Verhalten bei Fehlern

### Build-blockierend

- fehlende Dokument-ID
- fehlende DE-/EN-Hauptseite
- fehlender Navigationseintrag auf nicht existierende ID
- fehlender DSM-Hilfe-Content
- ungültige `helptoc.conf`
- fehlender i18n-Key
- dokumentationspflichtiger Config-Key ohne Dokumentation
- kaputter interner Link

### Warnung

- nicht verlinktes optionales Dokument
- fehlender Screenshot
- externer Link temporär nicht erreichbar
- Release-API nicht erreichbar beim lokalen Webbuild

---

## 44. GitHub Actions

Empfohlene Jobs:

```text
pull_request
    │
    ├── docs-validate
    ├── docs-render-dsm-test
    └── docs-render-web-test

main
    │
    ├── docs-validate
    ├── package-build
    └── pages-build-deploy

release/tag
    │
    ├── full-tests
    ├── docs-build
    ├── package-build
    ├── GitHub Release
    └── pages-build-deploy
```

Die Website wird dadurch bei normalen Dokumentationsänderungen aktualisiert und nach Releases automatisch mit neuen Release-Daten neu gebaut.

---

## 45. Release-Workflow

Zielzustand:

```text
Code / Docs ändern
        ↓
Config / Feature ggf. ergänzen
        ↓
DE + EN Core-Dokumentation aktualisieren
        ↓
Pull Request
        ↓
Documentation Tests
        ↓
Merge
        ↓
Website automatisch aktualisiert
        ↓
Release Tag
        ↓
DSM-Hilfe automatisch generiert
        ↓
SPK Build
        ↓
Release Asset
        ↓
Website liest neues Release
```

Damit gibt es keinen separaten manuellen Schritt „DSM-Hilfe aktualisieren“ oder „Website aktualisieren“.

---

## 46. Migration der bestehenden `docs`

Die vorhandenen Design-/Konzeptdokumente unter `docs` sollen nicht automatisch Teil der Benutzerhilfe werden.

Es wird zwischen zwei Dokumenttypen unterschieden:

### Entwickler-/Design-Dokumente

Bleiben beispielsweise:

```text
docs/dm-*.md
```

Sie dokumentieren interne Designentscheidungen und Konzepte.

### Benutzer-Dokumentation

Wird schrittweise unter

```text
docs/core/de/
docs/core/en/
```

aufgebaut.

Dadurch bleibt die bestehende `docs`-Historie erhalten, ohne interne Design-Memos ungefiltert auf der öffentlichen Hilfe-Website oder in DSM anzuzeigen.

---

## 47. Migration bestehender UI-Texte

Im UI existieren bereits lokalisierte Bezeichnungen und Fallback-Texte. Diese können als zusätzliche Quelle bzw. Migrationshilfe dienen.

Langfristig sollte jedoch vermieden werden, dass derselbe Hilfetext gleichzeitig in

- Vue-Komponenten
- Documentation i18n
- DSM strings

separat gepflegt wird.

Kurze UI-Feldnamen dürfen aus der bestehenden UI-i18n stammen, wenn die Struktur dafür geeignet ist. Längere Hilfebeschreibungen gehören in die Documentation-Core-i18n bzw. Markdown-Dokumente.

---

## 48. Wiederverwendung vorhandener Config-Informationen

Vorhandene Quellen wie

```text
var/config.json
src/services/config_service.py
ui/src/views/ConfigurationView.vue
```

enthalten bereits Teile der benötigten Information.

Für die endgültige Architektur sollte festgelegt werden:

- Defaultwert: genau eine Quelle
- Datentyp / Range: genau eine Quelle oder Schema
- UI-Label: bestehende i18n oder gemeinsame Metadaten
- Hilfebeschreibung: Documentation Core

Ziel ist nicht, alle vorhandenen Dateien zu parsen und damit dauerhaft mehrere Wahrheiten zu akzeptieren. Parsing mehrerer Quellen eignet sich zunächst zur Migration und als Konsistenztest. Langfristig sollten die Metadaten konsolidiert werden.

---

## 49. Empfohlene Priorität der Quellen

Wenn sich Quellen widersprechen, gilt eine feste Priorität.

### Paketdaten

```text
INFO.sh > Dokumentation
```

### Runtime-Defaults

```text
Runtime-/Default-Config > Dokumentation
```

### Config-Typen und Grenzen

```text
Schema > Implementierung > Dokumentationsmetadaten
```

### Fachliche Erklärung

```text
Documentation Core > generierte Darstellung
```

### Releases

```text
GitHub Release > Website Cache
```

Der Validator soll Widersprüche melden, nicht still eine beliebige Variante auswählen.

---

## 50. Suchfunktion

### Website

MkDocs kann eine Volltextsuche über die komplette Dokumentation bereitstellen.

### DSM

Die Integration erfolgt über den von DSM vorgesehenen Hilfebaum. Eigene Suchlogik sollte zunächst nicht implementiert werden.

Dokumenttitel und klare Seitenstruktur sind deshalb für DSM besonders wichtig.

---

## 51. Dokumentationsumfang der ersten Version

Für die erste produktive Hilfe sollten mindestens vorhanden sein:

### Allgemein

- Was ist ImgData?
- Voraussetzungen
- Installation / Update
- Grundkonzept

### Funktionen

- Metadaten
- Analyse
- Gesichtserkennung
- Personenprofile
- Referenzbilder
- Datenbanklisten
- External Worker

### Konfiguration

- allgemeine Optionen
- Analyseoptionen
- Recognition-Parameter
- External-Worker-Konfiguration

### Betrieb

- Start / Stop
- Logs
- Fehlerbehebung
- Performancehinweise

---

## 52. Web-only-Bereich der ersten Version

Zusätzlich zur Hilfe:

- aktuelles Release
- Download
- Systemanforderungen
- Screenshots
- Release-Historie
- GitHub Repository
- Issues
- gegebenenfalls Roadmap

Damit ist die GitHub Page mehr als nur eine Spiegelung der DSM-Hilfe, ohne die fachliche Dokumentation zu duplizieren.

---

## 53. DSM-Hilfe-Startseite

Die DSM-Hilfe sollte bewusst kompakt sein.

Beispiel:

```text
ImgData

ImgData analysiert Foto-Metadaten und unterstützt Gesichtsabgleich sowie die Auslagerung rechenintensiver Bildprozesse auf externe Worker.

Erste Schritte
- Installation und Voraussetzungen
- Analyse starten
- Gesichtserkennung
- Personenprofile
- External Worker
- Konfiguration
- Fehlerbehebung
```

Die Website kann denselben Inhalt als Dokumentationsstart verwenden, ihn aber mit Release- und Download-Elementen ergänzen.

---

## 54. Dokumentationsqualität als Release-Kriterium

Langfristig sollte ein Release nur möglich sein, wenn:

```text
Code                     ✓
Tests                    ✓
Paketstruktur            ✓
Documentation Core       ✓
Deutsch                  ✓
Englisch                 ✓
DSM Help Render          ✓
Web Render               ✓
Config Documentation     ✓
```

Dokumentation wird damit Teil der Definition of Done.

---

## 55. Erweiterbarkeit

Die Architektur erlaubt später weitere Targets, ohne die fachlichen Texte neu aufzubauen.

Denkbar:

```text
Documentation Core
├── DSM Help
├── GitHub Pages
├── README-Auszüge
├── CLI --help
├── API-Dokumentation
└── Release-Handbuch
```

Neue Renderer sollten jedoch nur eingeführt werden, wenn sie tatsächlich denselben semantischen Inhalt sinnvoll wiederverwenden können.

---

## 56. Umsetzung in Phasen

### Phase 1 – Fundament

- `docs/core/de` und `docs/core/en` anlegen
- Dokument-Front-Matter definieren
- `navigation.yml` definieren
- `docs/i18n` anlegen
- Collector und Validator implementieren

### Phase 2 – DSM Help

- DSM-HTML-Template
- `helptoc.conf` generieren
- `strings` generieren
- DE/EN-Hilfeseiten erzeugen
- Paketstrukturtests
- Test auf DSM

### Phase 3 – Website

- MkDocs konfigurieren
- DE/EN-Struktur
- Web-Renderer
- Sprachumschalter
- GitHub Pages Deployment

### Phase 4 – technische Quellen

- `INFO.sh` automatisch einlesen
- Config-Dokumentation generieren
- Feature-Metadaten
- Release-Daten
- Download-Auswahl

### Phase 5 – strikte Qualitätssicherung

- Config-Coverage blockierend
- Übersetzungsparität blockierend
- Linktests
- Snapshot-Tests
- Release-Gate

---

## 57. Empfohlene erste Implementierungsreihenfolge

Konkret für das bestehende Repository:

1. Dokumentformat und IDs festlegen.
2. `navigation.yml` erstellen.
3. zunächst 5–8 zentrale Hilfeseiten auf Deutsch erstellen.
4. englische Gegenstücke erstellen.
5. `docs_validate.py` implementieren.
6. `INFO.sh` in das Core-Modell übernehmen.
7. DSM-Renderer implementieren.
8. DSM-Hilfe in Debug-SPK integrieren und auf NAS testen.
9. MkDocs-Webrenderer hinzufügen.
10. `var/config.json` als automatische Config-Quelle anbinden.
11. Schema/Config-Metadaten konsolidieren.
12. GitHub Releases anbinden.

Damit wird zuerst der schwierigere technische Vertrag mit DSM stabilisiert, bevor die reichhaltigere Website darauf aufgebaut wird.

---

## 58. Architekturentscheidung

Die empfohlene endgültige Architektur lautet daher:

```text
              SINGLE SOURCES OF TRUTH
        ┌──────────────┬───────────────┐
        │              │               │
   Core Markdown    Paket/Config     GitHub
      DE / EN          Daten           Daten
        │              │               │
        └──────────────┼───────────────┘
                       ▼
              Documentation Core
                       │
           Validierung + Normalisierung
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
     DSM Help Renderer         Web Renderer
          │                         │
          ▼                         ▼
       DSM Paket               GitHub Pages
```

Die **Documentation Core** ist damit die zentrale fachliche Ebene.

Die **DSM-Hilfe ist keine separat gepflegte Dokumentation**.

Die **GitHub Page ist keine separat gepflegte Dokumentation**.

Beide sind unterschiedliche Projektionen desselben dokumentierten Produktzustands.

---

## 59. Wichtigste Regeln

1. Technische Werte nie in Hilfetexten duplizieren, wenn sie aus Code oder Paketmetadaten gelesen werden können.
2. Gemeinsame Benutzerhilfe immer im Documentation Core pflegen.
3. DE und EN verwenden dieselben Dokument-IDs.
4. Navigation nur einmal definieren.
5. `helptoc.conf`, DSM-HTML und DSM-`strings` immer generieren.
6. Website-Hilfe aus denselben Core-Dokumenten erzeugen.
7. Web-only-Inhalte klar vom gemeinsamen Hilfeinhalt trennen.
8. Neue Config-Optionen müssen entweder dokumentiert oder explizit als intern markiert werden.
9. Generierte Dateien dürfen nicht manuell gepflegt werden.
10. Dokumentationsvalidierung ist Bestandteil von CI und Release.

---

## 60. Ergebnis

Mit diesem Modell entsteht eine wartbare Dokumentationsplattform, bei der ein typischer Feature-Change idealerweise nur folgende Pflege benötigt:

```text
Feature implementieren
        │
        ├── technische Metadaten / Config aktualisieren
        ├── deutschen Core-Hilfetext aktualisieren
        └── englischen Core-Hilfetext aktualisieren
                 │
                 ▼
           ab hier automatisch
                 │
        ┌────────┴─────────┐
        ▼                  ▼
    DSM-Hilfe          GitHub Page
```

Damit bleiben Paket, integrierte Hilfe und öffentliche Dokumentation dauerhaft wesentlich enger synchronisiert als bei getrennt gepflegten Dokumentationssystemen.
