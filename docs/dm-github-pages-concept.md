# Konzept: GitHub Pages

## 1. Ziel und Entscheidung

ImgData erhält eine zweisprachige öffentliche Tool- und Dokumentationsseite auf GitHub Pages. Die Website ist derzeit die einzige aktiv erzeugte Dokumentationsausgabe. Eine DSM-Hilfe wird vorerst nicht gebaut oder mit dem SPK ausgeliefert.

Die fachlichen Inhalte stammen direkt aus `docs/core/de` und `docs/core/en`.

### Repository-Entscheidung

Für ImgData wird **vorerst kein eigenes Website-Repository angelegt**.

Die GitHub Page gehört fachlich ausschließlich zu ImgData und soll sich automatisch mit Quellcode, Paketmetadaten, Releases und Dokumentation dieses Repositories aktualisieren. Deshalb bleibt die Website im Repository `AndreasVilippus/av_imgdata` verankert.

Vorteile:

- Dokumentation und Code besitzen denselben Änderungsverlauf.
- Releaseinformationen können direkt aus demselben Repository gelesen werden.
- Änderungen an `INFO.sh`, Konfiguration, Worker-Metadaten und Dokumentation können denselben Pages-Build auslösen.
- Pull Requests können Website-Änderungen zusammen mit der zugehörigen Codeänderung prüfen.
- Es entsteht kein Synchronisationsproblem zwischen Produkt- und Website-Repository.

Ein separates Repository ist erst sinnvoll, wenn später eine **übergreifende Website für mehrere Tools/Projekte** entstehen soll. Dann wäre beispielsweise ein Repository `AndreasVilippus.github.io` als zentrale Projekt- bzw. Tool-Übersicht sinnvoll. ImgData könnte dort verlinkt werden, während seine ausführliche Dokumentation weiterhin im Projekt-Repository bleibt.

---

## 2. Öffentliche URL

Als GitHub Project Page ergibt sich ohne eigene Domain grundsätzlich eine URL nach diesem Schema:

```text
https://andreasvilippus.github.io/av_imgdata/
```

Die Dokumentation wird darunter sprachlich getrennt:

```text
https://andreasvilippus.github.io/av_imgdata/de/
https://andreasvilippus.github.io/av_imgdata/en/
```

Eine eigene Domain kann später ergänzt werden, ist aber keine Voraussetzung für den Aufbau.

---

## 3. Grundarchitektur

```text
Repository: AndreasVilippus/av_imgdata
   │
   ├── docs/core/de + docs/core/en       fachliche Texte
   ├── docs/site/                        Website-Konfiguration/Assets
   ├── INFO.sh                           Paketdaten
   ├── var/config.json                   Konfigurationsdefaults
   ├── Feature-/Worker-Metadaten
   ├── Screenshots / Icons
   └── GitHub Releases
          │
          ▼
   GitHub Actions: pages.yml
          │
          ├── Quellen validieren
          ├── technische Daten sammeln
          ├── Website erzeugen
          └── statische Ausgabe in Runner-Verzeichnis
                 │
                 ▼
        GitHub Pages Artifact
                 │
                 ▼
          GitHub Pages Deployment
                 │
          ┌──────┴──────┐
          ▼             ▼
         /de/           /en/
```

Die Website wird **nicht von einer DSM-Hilfe abgeleitet** und hängt nicht von `helptoc.conf`, DSM-Locales oder einem DSM-Help-Renderer ab.

---

## 4. Ablage der Website-Quellen

Es wird zwischen fachlicher Dokumentation und Website-spezifischen Dateien getrennt.

Empfohlene Struktur:

```text
docs/
├── core/
│   ├── de/
│   │   └── ... Markdown-Inhalte
│   └── en/
│       └── ... Markdown-Inhalte
│
├── site/
│   ├── assets/
│   │   ├── icons/
│   │   ├── screenshots/
│   │   └── css/
│   ├── templates/
│   └── configuration/
│
├── dm-github-pages-concept.md
├── dm-documentation-core-concept.md
└── dm-documentation-dsm-help-concept.md

tools/docs/
├── collect_web_data.py
├── validate_web_docs.py
└── render_web.py
```

`docs/core` bleibt die fachliche Single Source of Truth.

`docs/site` enthält ausschließlich Darstellung und Web-spezifische Ergänzungen, beispielsweise:

- Theme-/Layout-Konfiguration,
- zusätzliche Startseiten-Bausteine,
- Screenshots,
- Icons,
- Web-CSS,
- optionale Templates.

Technische Werte wie Version oder Download-URL werden dort nicht dupliziert.

---

## 5. Wo der erzeugte Inhalt abgelegt wird

Der fertige statische Website-Inhalt wird **nicht dauerhaft im `main`-Branch abgelegt**.

Während eines GitHub-Actions-Laufs wird die Seite beispielsweise nach

```text
build/pages/
```

oder in ein vergleichbares temporäres Runner-Verzeichnis gerendert:

```text
build/pages/
├── index.html
├── de/
│   ├── index.html
│   └── ...
├── en/
│   ├── index.html
│   └── ...
└── assets/
```

Dieses Verzeichnis ist ein reines Build-Artefakt und wird nicht committed.

Danach wird die komplette statische Ausgabe als **GitHub Pages Artifact** hochgeladen und mit der GitHub-Pages-Deployment-Action veröffentlicht.

Damit gilt:

```text
Repository-Quellen
        ↓
GitHub Actions Runner
        ↓
build/pages/                 nur während des Builds
        ↓
Pages Artifact
        ↓
GitHub Pages Hosting
```

Es wird kein eigener `gh-pages`-Branch benötigt, solange GitHub Pages direkt über GitHub Actions deployed wird.

### Warum kein generierter Inhalt in `main`

Das vermeidet:

- große Commits mit rein generiertem HTML,
- unnötige Änderungen bei jedem Release,
- Merge-Konflikte zwischen Quellen und Build-Ausgabe,
- versehentliche manuelle Änderungen an generierten Seiten,
- doppelte Wahrheit zwischen Markdown und HTML.

---

## 6. Pages-Deployment über GitHub Actions

GitHub Pages wird im Repository auf **Source: GitHub Actions** gestellt.

Die geplante Workflow-Datei lautet:

```text
.github/workflows/pages.yml
```

Der Workflow besitzt drei logische Schritte:

```text
validate
   ↓
build
   ↓
deploy
```

### Validate

Prüft unter anderem:

- deutsche und englische Dokumente besitzen passende IDs,
- interne Dokumentlinks sind gültig,
- notwendige Metadaten sind vorhanden,
- keine DSM-spezifischen Buildartefakte werden benötigt,
- technische Daten können aus ihren führenden Quellen gelesen werden.

### Build

Erzeugt:

- statische deutsche Seiten,
- statische englische Seiten,
- Sprachumschaltung,
- Startseite,
- technische Paketübersicht,
- Release-/Downloadinformationen,
- Konfigurationsreferenz,
- Assets.

Die Ausgabe landet ausschließlich im Runner, z. B. unter `build/pages`.

### Deploy

Der Build-Ordner wird als Pages-Artifact hochgeladen und anschließend deployed.

Das Deployment benötigt dadurch weder einen Commit noch einen Push des generierten HTML.

---

## 7. Wann die Website aktualisiert wird

Die Website soll automatisch neu gebaut werden, sobald eine ihrer Quellen geändert wird.

### 7.1 Push auf `main`

Ein Pages-Build wird ausgelöst, wenn sich unter anderem ändern:

```text
docs/core/**
docs/site/**
tools/docs/**
INFO.sh
var/config.json
relevante Feature-/Worker-Metadaten
.github/workflows/pages.yml
```

Damit werden fachliche und technische Änderungen unmittelbar auf der Website sichtbar, sobald sie auf `main` liegen.

### 7.2 Veröffentlichung eines GitHub Releases

Ein `release: published`-Event löst ebenfalls den Pages-Build aus.

Dadurch können automatisch aktualisiert werden:

- aktuelle Version,
- Veröffentlichungsdatum,
- Release Notes,
- Release Assets,
- Download-Link auf das aktuelle SPK,
- Prerelease-/Stable-Status.

Die Website muss dafür keine Release-Daten im Repository speichern. Der Pages-Build liest die aktuellen Informationen während des Workflows über GitHub.

### 7.3 Manuelle Aktualisierung

Zusätzlich wird `workflow_dispatch` vorgesehen.

Damit kann die Seite bei Bedarf manuell neu gebaut werden, ohne eine Quelldatei verändern zu müssen.

### 7.4 Pull Requests

Bei Pull Requests wird die Website **gebaut und validiert, aber nicht veröffentlicht**.

Damit können fehlerhafte Dokumentlinks, unvollständige Sprachpaare oder fehlerhafte Generatoren bereits vor dem Merge erkannt werden.

---

## 8. Empfohlene Workflow-Trigger

Konzeptionell:

```yaml
on:
  push:
    branches:
      - main
    paths:
      - 'docs/core/**'
      - 'docs/site/**'
      - 'tools/docs/**'
      - 'INFO.sh'
      - 'var/config.json'
      - '.github/workflows/pages.yml'

  pull_request:
    paths:
      - 'docs/core/**'
      - 'docs/site/**'
      - 'tools/docs/**'
      - 'INFO.sh'
      - 'var/config.json'

  release:
    types:
      - published

  workflow_dispatch:
```

Die endgültige Liste wird erweitert, sobald feststeht, welche Dateien tatsächlich Feature- und Worker-Metadaten für die Website liefern.

---

## 9. Single Source of Truth

| Information | Führende Quelle | GitHub Pages |
|---|---|---|
| Fachliche Dokumentation | `docs/core/de`, `docs/core/en` | direkt |
| Paketname / Version | `INFO.sh` | automatisch |
| DSM-Mindestversion | `INFO.sh` | automatisch |
| Konfigurationsdefaults | `var/config.json` | automatisch |
| Feature-/Worker-Daten | Projektmetadaten | automatisch |
| Release / Download | GitHub Releases | automatisch |
| Release Notes | GitHub Release / Changelog | automatisch |
| Screenshots / Icons | `docs/site/assets` bzw. Repository | eingebunden |
| Issues / Roadmap | GitHub | optional |

Technische Werte werden nicht in beiden Sprachfassungen separat gepflegt.

---

## 10. Dokumentmodell

Dokumente im Core verwenden stabile IDs und aktuell ausschließlich das Web-Target:

```yaml
---
id: external-worker
section: features
title_key: docs.external_worker.title
targets:
  - web
order: 50
---
```

DSM-spezifische Metadaten gehören nicht in den aktiven Website-Build. Falls die DSM-Hilfe später wieder aktiviert wird, kann der Core erneut um ein DSM-Target bzw. eine separate Mapping-Schicht ergänzt werden.

---

## 11. Zweisprachigkeit

Die Website stellt mindestens bereit:

```text
/de/
/en/
```

Zu jeder fachlichen Dokument-ID muss eine deutsche und englische Variante vorhanden sein. Ein Sprachumschalter soll möglichst auf die korrespondierende Seite wechseln.

Sprachneutral bleiben insbesondere Versionen, Zahlenwerte, Defaults, Paketdateinamen, Release-Daten und technische IDs.

Die Root-Seite

```text
/
```

kann entweder eine kurze sprachneutrale Landingpage mit Sprachwahl darstellen oder auf eine definierte Standardsprache weiterleiten. Für ImgData wird eine kleine Landingpage mit direktem Einstieg in Deutsch und Englisch bevorzugt.

---

## 12. Startseite als Toolseite

Da GitHub Pages ausschließlich für ImgData verwendet wird, ist die Seite nicht als allgemeines Entwicklerportal zu konzipieren, sondern als Produkt-/Toolseite.

Die Root- bzw. Sprachstartseite soll insbesondere enthalten:

```text
ImgData
│
├── Kurzbeschreibung
├── aktuelles Release
├── Download DSM-Paket
├── DSM-Kompatibilität
├── wichtigste Funktionen
├── Screenshots
├── External Worker
├── Dokumentation
├── Konfiguration / Referenz
├── Release Notes
└── Links zu GitHub / Issues
```

Damit dient GitHub Pages gleichzeitig als:

- Produktübersicht,
- Download-Einstieg,
- Benutzerdokumentation,
- technische Referenz,
- Troubleshooting-Einstieg.

---

## 13. Automatisch ergänzte Inhalte

GitHub Pages kann aus Projektquellen zusätzlich erzeugen:

- aktuelle Paketversion,
- Release-Datum,
- passende SPK-Downloads,
- DSM-Kompatibilität,
- Konfigurationsreferenz,
- unterstützte Worker-Plattformen,
- Feature-Status,
- Buildstatus,
- bekannte Probleme und Roadmap-Verweise.

Längere Erklärungen bleiben als Markdown im Documentation Core.

### Release-Download

Der Download-Link wird nicht hart codiert. Der Build sucht im neuesten geeigneten GitHub Release nach dem passenden SPK-Asset.

Damit bleibt die Website nach einem Release automatisch aktuell.

---

## 14. Generierte Zwischendaten

Für den Website-Build kann zunächst ein neutrales Datenmodell erzeugt werden, beispielsweise:

```text
build/docs-data/
├── package.json
├── configuration.json
├── release.json
└── workers.json
```

Auch diese Dateien sind Build-Artefakte und werden nicht committed.

Der Renderer verarbeitet damit zwei Quelltypen:

```text
Markdown DE/EN
       +
generierte technische Daten
       ↓
statische Website
```

Dadurch bleiben Datensammlung und HTML-/Markdown-Rendering voneinander getrennt und einzeln testbar.

---

## 15. Abgrenzung zur DSM-Hilfe

Die gemeinsame fachliche Quelle bleibt bewusst so gestaltet, dass eine spätere DSM-Ausgabe möglich ist. Aktuell gibt es aber keine technische Kopplung.

Insbesondere erzeugt der GitHub-Pages-Build nicht:

- `ui/help/*`,
- `ui/helptoc.conf`,
- DSM-`strings` für die Hilfenavigation,
- `indexdb/helpindexdb`.

Der Grund für das Aussetzen der DSM-Hilfe und die vorgesehene korrekte Integration sind in `docs/dm-documentation-dsm-help-concept.md` dokumentiert.

---

## 16. Was bewusst nicht vorgesehen ist

Vorerst nicht vorgesehen sind:

- separates Repository nur für die ImgData-Website,
- Committen generierter HTML-Seiten nach `main`,
- eigener `gh-pages`-Branch als notwendiger Bestandteil des Buildprozesses,
- manuell gepflegte Release-/Versionsnummern in Website-Dateien,
- Kopieren von GitHub-Release-Assets in das Pages-Repository,
- Abhängigkeit vom DSM-Paketbuild.

Der Website-Build soll unabhängig vom zeitaufwendigen SPK-/Worker-Build bleiben.

---

## 17. Wann ein separates Repository sinnvoll würde

Ein separates Website-Repository sollte erst angelegt werden, wenn mindestens einer dieser Fälle eintritt:

1. Es entsteht eine gemeinsame Website für mehrere eigenständige Tools.
2. Die Website erhält einen eigenen Entwicklungszyklus unabhängig von ImgData.
3. Mehrere Repositories sollen Inhalte in eine gemeinsame Dokumentationsplattform einspeisen.
4. Eine umfangreiche Webanwendung ersetzt die einfache statische Projektseite.
5. Eine zentrale Domain soll mehrere Projekte unter einer gemeinsamen Navigation bündeln.

Dann wäre eine Struktur wie

```text
AndreasVilippus.github.io
├── /imgdata/
├── /tool-b/
└── /tool-c/
```

sinnvoll.

Für den aktuellen ImgData-Fall würde ein zweites Repository dagegen zusätzliche Synchronisation verursachen, ohne einen funktionalen Vorteil zu liefern.

---

## 18. Build- und CI-Regeln

Der Web-Build soll prüfen:

1. deutsche und englische Dokumente besitzen passende IDs,
2. interne Links sind auflösbar,
3. technische Werte werden aus ihren führenden Quellen gelesen,
4. generierte Konfigurations- und Release-Daten sind konsistent,
5. die Website kann unabhängig vom DSM-Paketbuild erzeugt werden,
6. es werden keine generierten Website-Dateien im Quellbaum benötigt,
7. Pull Requests können die Seite vollständig bauen, ohne sie zu deployen.

Eine fehlende oder deaktivierte DSM-Hilfe darf den GitHub-Pages-Build nicht beeinflussen.

---

## 19. Umsetzungsschritte

Empfohlene Reihenfolge:

1. `docs/site` als Website-spezifische Quellstruktur anlegen.
2. Renderer/Generator unter `tools/docs` festlegen.
3. lokale Ausgabe nach `build/pages` implementieren.
4. Validierung der DE-/EN-Dokumentpaare implementieren.
5. Paketdaten aus `INFO.sh` übernehmen.
6. GitHub-Release-Daten im Actions-Build ergänzen.
7. `.github/workflows/pages.yml` hinzufügen.
8. GitHub Pages auf Deployment über GitHub Actions stellen.
9. Pull-Request-Build ohne Deployment ergänzen.
10. erst danach zusätzliche Bereiche wie Konfigurationsreferenz, Screenshots und Roadmap schrittweise erweitern.
