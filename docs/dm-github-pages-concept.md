# Konzept: Automatisch gepflegte, zweisprachige GitHub Page

## 1. Ziel

Für das DSM-Paket soll eine öffentliche GitHub-Page entstehen, die möglichst viele Informationen direkt aus bereits vorhandenen Projektquellen übernimmt und sich bei Änderungen bzw. Releases automatisch aktualisiert.

Die Seite soll vollständig auf **Deutsch und Englisch** verfügbar sein.

Grundprinzip:

> Informationen werden dort gepflegt, wo sie ohnehin entstehen. Die GitHub Page stellt diese Informationen nur dar und soll möglichst wenig eigene, doppelt gepflegte Daten besitzen.

Ziele:

- möglichst geringer zusätzlicher Pflegeaufwand
- automatische Aktualisierung bei Releases
- automatische Übernahme technischer Paketinformationen
- zentrale, nachvollziehbare Quellen für Versions- und Konfigurationsdaten
- deutsch- und englischsprachige Dokumentation
- gemeinsame Nutzung derselben technischen Daten in beiden Sprachen
- klare Trennung zwischen manuell gepflegten und automatisch generierten Inhalten

---

## 2. Grundarchitektur

```text
Repository / GitHub
        │
        ├── Paket-Metadaten
        ├── Konfiguration / Defaults
        ├── README / Markdown
        ├── Screenshots / Icons
        ├── CHANGELOG
        ├── GitHub Releases
        ├── Git Tags
        ├── GitHub Issues / Milestones
        └── GitHub Actions
                │
                ▼
        Dokumentations-Generator
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
      Deutsch          English
        │                │
        └───────┬────────┘
                ▼
          GitHub Pages
```

Die technische Datenbasis wird einmal erzeugt und anschließend für beide Sprachversionen verwendet.

---

## 3. Single Source of Truth

Für jede Information muss festgelegt werden, wo sie führend gepflegt wird.

| Information | Primäre Quelle | Website |
|---|---|---|
| Versionsnummer | Paket-Metadaten / Git Tag | automatisch |
| neuestes Release | GitHub Releases | automatisch |
| Release-Datum | GitHub Releases | automatisch |
| Download | Release Asset | automatisch |
| Changelog | CHANGELOG / Release Notes | automatisch |
| Paketname | Paket-Metadaten | automatisch |
| DSM-Anforderungen | Paket-Metadaten | automatisch |
| Architekturen | Build-/Paket-Konfiguration | automatisch |
| Konfigurationswerte | `var/config.json` / Schema | automatisch |
| Feature-Metadaten | zentrale Feature-Datei | automatisch |
| Screenshots | Repository | automatisch eingebunden |
| Installationsanleitung | Markdown DE/EN | manuell |
| Feature-Beschreibungen | Markdown DE/EN | manuell |
| External Worker | Markdown + generierte Daten | gemischt |
| bekannte Probleme | GitHub Issues | optional automatisch |

Nicht gewünscht ist eine Situation, in der z. B. dieselbe Versionsnummer in Paket, README, Website und Download-Link separat gepflegt werden muss.

---

## 4. Zweisprachigkeit Deutsch / Englisch

Die Seite soll mindestens folgende Sprachvarianten besitzen:

```text
/de/
/en/
```

Beispiel:

```text
https://<user>.github.io/<repo>/de/
https://<user>.github.io/<repo>/en/
```

Alternativ kann Englisch die Root-Sprache sein und Deutsch unter `/de/` liegen. Für ein deutsch geprägtes Projekt ist auch Deutsch als Root möglich. Technisch sollte die Sprachstruktur jedoch eindeutig und dauerhaft sein.

### 4.1 Sprachumschalter

Auf jeder Seite soll ein sichtbarer Sprachumschalter vorhanden sein:

```text
Deutsch | English
```

Beim Umschalten sollte möglichst die entsprechende Seite in der anderen Sprache geöffnet werden, nicht nur die jeweilige Startseite.

Beispiel:

```text
/de/features/external-worker/
        ⇅
/en/features/external-worker/
```

### 4.2 Keine doppelte Pflege technischer Daten

Folgende Werte dürfen nicht übersetzt oder separat gepflegt werden:

- Version
- Releasedatum
- Dateigröße
- Download-URL
- Paketdateiname
- DSM-Version
- Architektur
- Buildstatus
- Konfigurations-Defaults
- technische Grenzwerte

Diese Informationen werden einmal generiert und in beide Sprachversionen eingebunden.

Nur beschreibende Texte werden übersetzt.

---

## 5. Empfohlene Dateistruktur für Sprachen

```text
docs-site/
├── de/
│   ├── index.md
│   ├── installation.md
│   ├── troubleshooting.md
│   ├── features/
│   │   ├── recognition.md
│   │   ├── profiles.md
│   │   ├── database.md
│   │   └── external-worker.md
│   └── architecture/
│       └── overview.md
│
├── en/
│   ├── index.md
│   ├── installation.md
│   ├── troubleshooting.md
│   ├── features/
│   │   ├── recognition.md
│   │   ├── profiles.md
│   │   ├── database.md
│   │   └── external-worker.md
│   └── architecture/
│       └── overview.md
│
├── generated/
│   ├── package.json
│   ├── releases.json
│   ├── configuration.json
│   └── build.json
│
└── assets/
    ├── screenshots/
    └── icons/
```

`generated/` enthält sprachneutrale Daten.

Die Seitengenerierung verwendet diese Daten für Deutsch und Englisch gleichermaßen.

---

## 6. Manuell gepflegte und generierte Inhalte trennen

### Manuell gepflegt

Redaktionelle Inhalte, z. B.:

- Einführung
- Installation
- Funktionsbeschreibung
- External-Worker-Erklärung
- Tutorials
- Troubleshooting
- Architekturtexte

Jeweils separat in Deutsch und Englisch.

### Automatisch generiert

- Paketversion
- aktuelles Release
- Release-Datum
- Download-Links
- Release Assets
- Dateigrößen
- Release-Historie
- Paket-Metadaten
- DSM-Kompatibilität
- Architekturen
- Config Defaults
- Build-Informationen
- GitHub-Links
- optional Issue-/Roadmap-Informationen

---

## 7. Aktuelles Release

GitHub Releases soll die primäre Quelle für Downloadinformationen darstellen.

Automatisch übernommen werden können:

- Tag
- Release Name
- Versionsnummer
- Veröffentlichungsdatum
- Release Notes
- Assets
- Dateigröße
- Download-URL
- Prerelease-Status

Beispiel:

```text
Current Release / Aktuelle Version

Version 1.4.2
Released / Veröffentlicht: 29 August 2026

[Download DSM Package]
```

Der Download-Link darf nicht hart codiert werden, sondern wird aus dem neuesten passenden Release Asset erzeugt.

---

## 8. Stable / Beta / Debug

Die Website kann Releases automatisch nach Typ unterscheiden.

Beispiel:

```text
Stable
*.spk

Debug
*_debug.spk
```

GitHub-Prereleases können zusätzlich als Beta oder Development Release dargestellt werden.

Mögliche Bereiche:

- Latest Stable
- Latest Beta
- Debug Package

Diese Bezeichnungen werden im Frontend übersetzt, die zugrunde liegenden Release-Daten bleiben identisch.

---

## 9. Paketinformationen direkt aus dem DSM-Paket

Vorhandene Paketinformationen sollen während des Website-Builds ausgelesen werden, z. B.:

- Paketname
- Version
- Architektur
- minimale DSM-Version
- Maintainer
- Beschreibung, sofern geeignet

Die Website erzeugt daraus automatisch eine technische Übersicht.

---

## 10. Automatische Konfigurationsdokumentation

Ein besonders hohes Automatisierungspotenzial besteht bei der Konfiguration.

Bereits vorhandene Werte aus z. B.:

```text
var/config.json
```

können automatisch in eine Referenz überführt werden.

Beispiel:

```text
analysis.CHECKS.RECOGNITION_MIN_FACES_PER_PERSON
Default: 3
Type: integer
```

Für eine vollständige Dokumentation sollte langfristig ein Schema bzw. eine Metadatenquelle ergänzt werden.

Beispiel:

```json
{
  "RECOGNITION_MIN_FACES_PER_PERSON": {
    "type": "integer",
    "description_de": "Minimale Anzahl benötigter Gesichter ...",
    "description_en": "Minimum number of faces required ...",
    "category": "Recognition",
    "advanced": true
  }
}
```

Besser als eingebettete Übersetzungen wäre langfristig eine Trennung von technischen Metadaten und Übersetzungen.

---

## 11. Config-Schema als zentrale Quelle

Langfristig sollte ein Schema enthalten:

- Datentyp
- Beschreibungsschlüssel
- Minimum
- Maximum
- Default
- Kategorie
- Deprecated-Status
- ggf. Sichtbarkeit / Advanced

Aus derselben Quelle können entstehen:

1. Validierung
2. Website-Dokumentation
3. UI-Hilfetexte
4. Default-Config-Prüfungen
5. eventuell Konfigurationsdialoge

Die sprachlichen Texte werden über Übersetzungsdateien aufgelöst.

Beispiel:

```text
config.schema.json
locales/de.json
locales/en.json
```

---

## 12. Übersetzungsstrategie

Für kurze UI-Bezeichnungen und automatisch generierte Seiten sollten Übersetzungsschlüssel verwendet werden.

Beispiel:

```json
{
  "release.latest": "Aktuelle Version",
  "release.download": "Herunterladen",
  "config.default": "Standardwert"
}
```

Englisch:

```json
{
  "release.latest": "Latest Release",
  "release.download": "Download",
  "config.default": "Default"
}
```

Längere Dokumentation bleibt in eigenständigen Markdown-Dateien pro Sprache.

Damit werden zwei unterschiedliche Anforderungen sauber getrennt:

- UI-/Generator-Texte → Übersetzungsdateien
- längere redaktionelle Dokumentation → eigene Markdown-Dateien

---

## 13. Übersetzungsvollständigkeit prüfen

Der Build sollte kontrollieren, ob beide Sprachversionen vollständig vorhanden sind.

Beispiele:

```text
FAIL: Missing English page:
features/external-worker.md
```

oder:

```text
FAIL: Missing translation key in en.json:
config.recognition_min_faces.description
```

Optional kann zunächst nur eine Warnung erzeugt werden.

Langfristig sollte ein Release jedoch nicht mit unvollständiger Hauptdokumentation veröffentlicht werden.

---

## 14. Features

Benutzerfunktionen sollten bewusst beschrieben werden, z. B.:

- Gesichtserkennung
- Personenprofile
- Profilreferenzbilder
- Bildanalyse
- Datenbanklisten
- External Worker

Mögliche zentrale Metadaten:

```yaml
features:
  recognition:
    title_key: feature.recognition.title
    icon: recognition.png
    documentation: recognition
    status: stable

  external_worker:
    title_key: feature.external_worker.title
    icon: worker.png
    documentation: external-worker
    status: beta
```

Daraus können automatisch Navigation, Feature-Kacheln und Statusanzeigen erzeugt werden.

Die ausführliche Beschreibung liegt in:

```text
de/features/recognition.md
en/features/recognition.md
```

---

## 15. Screenshots und Icons

Screenshots und Icons sollen nur einmal im Repository liegen.

```text
docs-site/assets/screenshots/
docs-site/assets/icons/
```

Sprachabhängige Bildbeschreibungen können über Metadaten oder Übersetzungsschlüssel erfolgen.

Beispiel:

```json
{
  "profiles.jpg": {
    "title_key": "screenshots.profiles.title",
    "description_key": "screenshots.profiles.description"
  }
}
```

Falls Screenshots UI-Texte enthalten, kann es später sinnvoll sein, getrennte DE-/EN-Screenshots vorzusehen. Das sollte aber nur erfolgen, wenn der Informationsgewinn den Pflegeaufwand rechtfertigt.

---

## 16. CHANGELOG und Release Notes

Es sollte genau eine führende Changelog-Quelle geben.

Empfehlung:

```text
CHANGELOG.md
        ↓
GitHub Release
        ↓
GitHub Page
```

Für Zweisprachigkeit gibt es zwei sinnvolle Möglichkeiten:

### Variante A – Changelog primär Englisch

Technische Release Notes werden nur auf Englisch gepflegt. Die deutsche Website zeigt dieselben Release Notes an.

Vorteil: minimaler Pflegeaufwand.

### Variante B – zweisprachige Release Notes

```text
CHANGELOG.de.md
CHANGELOG.en.md
```

oder strukturierte Release-Metadaten mit DE-/EN-Texten.

Für dieses Projekt ist zunächst Variante A wahrscheinlich ausreichend. Die eigentliche Produktdokumentation bleibt vollständig zweisprachig.

---

## 17. GitHub Issues und Roadmap

Optional können automatisch dargestellt werden:

- offene Issues
- bekannte Probleme
- geplante Features
- Milestones
- Entwicklungsstatus

Beispiel anhand von Labels:

```text
known-issue
bug
feature
enhancement
status:planned
status:development
```

Die Website kann daraus Bereiche wie "Known Issues" / "Bekannte Probleme" oder "Roadmap" erzeugen.

Issue-Titel selbst werden dabei nicht automatisch übersetzt.

---

## 18. External Worker

Der External Worker sollte eine eigene Hauptseite erhalten.

Manuell gepflegte Inhalte:

- Funktionsweise
- Installation
- Netzwerkmodell
- Sicherheitsaspekte
- Einsatzszenarien

Automatisch ergänzbare Daten:

- Worker-Version
- kompatible Paketversion
- unterstützte Plattformen
- unterstützte Aufgaben
- erforderliche Runtime-Versionen
- Status des Workers

Auch hier werden dieselben technischen Daten in beiden Sprachversionen verwendet.

---

## 19. Startseite

Beispielstruktur:

```text
------------------------------------------------

      [Package Icon]

      Paketname

      Kurzbeschreibung

      [Aktuelle Version herunterladen]
      [Dokumentation]

------------------------------------------------

Aktuelle Version

v1.5.0
29. August 2026
DSM 7.x

------------------------------------------------

Funktionen

[Icon] Gesichtserkennung
[Icon] Profile
[Icon] Datenbank
[Icon] External Worker

------------------------------------------------

Screenshots

------------------------------------------------

External Worker

------------------------------------------------

Dokumentation

Installation
Konfiguration
Fehlerbehebung

------------------------------------------------

Entwicklung

GitHub
Issues
Release Notes

------------------------------------------------
```

Die englische Seite besitzt dieselbe Struktur mit übersetzten Texten.

---

## 20. Empfohlene technische Lösung

Empfohlen wird:

```text
GitHub Repository
+
Markdown
+
MkDocs
+
Mehrsprachigkeits-Unterstützung
+
kleine Python-Generatoren
+
GitHub API
+
GitHub Actions
+
GitHub Pages
```

MkDocs übernimmt insbesondere:

- Markdown-Rendering
- Navigation
- Suche
- responsive Darstellung
- Codeblöcke
- Tabellen
- Inhaltsverzeichnisse
- Theme / Dark Mode

Die eigenen Python-Generatoren erzeugen lediglich die projektspezifischen Daten.

---

## 21. Generierungsprozess

Beispiel:

```text
extract_package_metadata.py
extract_config.py
extract_releases.py
        │
        ▼
site-data/*.json
        │
        ├───────────────┐
        ▼               ▼
   Build Deutsch     Build English
        │               │
        └───────┬───────┘
                ▼
          GitHub Pages
```

Die Generatoren selbst sollen möglichst keine sprachabhängigen Inhalte erzeugen, sondern neutrale Daten bereitstellen.

---

## 22. GitHub Actions

### Bei Dokumentationsänderungen

```text
Push auf main
        ↓
Daten generieren
        ↓
DE-Dokumentation bauen
        ↓
EN-Dokumentation bauen
        ↓
Vollständigkeit prüfen
        ↓
GitHub Pages Deploy
```

### Bei Release

```text
Git Tag
        ↓
Package Build
        ↓
Tests
        ↓
SPK erzeugen
        ↓
GitHub Release
        ↓
Release Assets
        ↓
Website-Daten aktualisieren
        ↓
DE + EN bauen
        ↓
GitHub Pages Deploy
```

Nach einem normalen Release sollte damit keine zusätzliche manuelle Pflege der Website erforderlich sein.

---

## 23. Plausibilitätsprüfungen

Der Website-/Release-Build sollte u. a. prüfen:

- Paketversion entspricht Git Tag
- Release besitzt erwartetes `.spk`
- Stable Release verwendet nicht versehentlich nur `_debug.spk`
- Config-Dokumentation enthält alle relevanten Werte
- alle Feature-Seiten existieren
- alle referenzierten Screenshots und Icons existieren
- deutsche Hauptseiten besitzen englische Gegenstücke
- englische Hauptseiten besitzen deutsche Gegenstücke
- alle benötigten Übersetzungsschlüssel existieren
- keine hart codierten Versionsnummern in generierten Bereichen

---

## 24. Dokumentationsabdeckung als Check

Die vorhandenen Strukturchecks können um Dokumentationschecks ergänzt werden.

Beispiel:

```text
FAIL: Configuration key has no documentation metadata:
analysis.CHECKS.NEW_PARAMETER
```

oder:

```text
FAIL: Missing German translation:
config.NEW_PARAMETER.description
```

oder:

```text
WARN: Feature metadata contains no English documentation page.
```

Damit wird verhindert, dass neue Funktionen und Konfigurationswerte dauerhaft undokumentiert bleiben.

---

## 25. Automatisierungsgrad

### Vollautomatisch

- Version
- Release
- Download
- Datum
- Dateigröße
- Release-Historie
- Git Tag
- Paket-Metadaten
- Config Defaults
- Buildstatus
- GitHub Links

### Halbautomatisch

- Konfigurationsbeschreibungen
- Feature-Metadaten
- Screenshots
- Architektur
- Worker-Metadaten

### Manuell zweisprachig

- Einführung
- Installation
- Tutorials
- Troubleshooting
- ausführliche Feature-Beschreibungen
- konzeptionelle Architekturtexte

---

## 26. Zielbild für den Entwicklungsprozess

```text
Code ändern
        ↓
Version erhöhen
        ↓
CHANGELOG ergänzen
        ↓
Dokumentation bei Bedarf DE/EN ergänzen
        ↓
Push / Tag
        ↓
────────────────────────────
ab hier automatisch
────────────────────────────
        ↓
Tests
        ↓
SPK Build
        ↓
GitHub Release
        ↓
Release Assets
        ↓
Paketdaten extrahieren
        ↓
Config-Dokumentation generieren
        ↓
Release-Seiten generieren
        ↓
Deutsch bauen
        ↓
Englisch bauen
        ↓
Sprachvollständigkeit prüfen
        ↓
GitHub Pages Deployment
```

---

## 27. Empfohlene Ausbaustufen

### Phase 1 – Grundseite zweisprachig

- MkDocs-Grundstruktur
- Deutsch / Englisch
- Sprachumschalter
- Startseite
- Features
- Installation
- Screenshots
- aktuelles Release
- automatischer Download

### Phase 2 – automatische Paketdaten

- Version
- DSM-Kompatibilität
- Architektur
- Release-Historie
- Paket-Metadaten

### Phase 3 – Konfigurationsreferenz

- Config automatisch analysieren
- Defaults darstellen
- Schema / Metadaten ergänzen
- Beschreibungen DE/EN
- suchbare Konfigurationsreferenz

### Phase 4 – Entwicklungsintegration

- Known Issues
- Roadmap
- Buildstatus
- Worker-Kompatibilität
- automatisierte Dokumentationschecks
- Übersetzungsvollständigkeit

---

## 28. Architekturgrundsatz

```text
                 GitHub Repository
                        │
          ┌─────────────┼─────────────┐
          │             │             │
       Package       Releases       Docs
          │             │             │
          └─────────────┼─────────────┘
                        │
                        ▼
                neutrale Site-Daten
                        │
                 ┌──────┴──────┐
                 │             │
                 ▼             ▼
              Deutsch       English
                 │             │
                 └──────┬──────┘
                        ▼
                   GitHub Page
```

Die GitHub Page ist damit keine zweite Datenquelle, sondern eine Präsentationsschicht über den vorhandenen Projektinformationen.

Technische Daten werden nur einmal erzeugt. Sprachabhängig gepflegt werden nur Inhalte, die tatsächlich sprachlich formuliert werden müssen.

---

## 29. Nächster sinnvoller Schritt

Vor der konkreten Implementierung sollte eine Bestandsaufnahme des bestehenden Repositories erfolgen.

Dabei wird für jede verwertbare Quelle dokumentiert:

```text
Quelle
→ enthaltene Information
→ Aktualisierungszeitpunkt
→ Generator
→ Ausgabeformat
→ DE/EN-Abhängigkeit
→ Zielseite
```

Beispiel:

| Quelle | Daten | Generator | Sprache | Ziel |
|---|---|---|---|---|
| `var/config.json` | Defaults | `extract_config.py` | neutral | Konfigurationsreferenz DE/EN |
| GitHub Release | Version, Assets | `extract_releases.py` | neutral | Download DE/EN |
| Feature-Markdown | Beschreibung | MkDocs | DE + EN | Feature-Seiten |
| Paket-Metadaten | DSM, Arch, Version | `extract_package.py` | neutral | Startseite / Download |

Diese Bestandsaufnahme bildet anschließend die konkrete technische Spezifikation für die GitHub-Page.