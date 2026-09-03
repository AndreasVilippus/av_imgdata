# Konzept: Documentation Core

## Ziel

`docs/core` ist die gemeinsame fachliche Dokumentationsbasis von ImgData. Aktuell wird daraus ausschließlich die öffentliche GitHub-Pages-Dokumentation abgeleitet. Eine DSM-Hilfe bleibt als mögliche spätere zweite Ausgabe vorgesehen, ist aber nicht Bestandteil des Paketbuilds.

Grundprinzip:

> Fachliche Inhalte werden einmal in Deutsch und Englisch gepflegt. Renderer und Zielplattformen dürfen daraus unterschiedliche Ausgaben erzeugen, ohne technische Fakten zu duplizieren.

## Aktiver Zustand

```text
Repository
   │
   ├── docs/core/de
   ├── docs/core/en
   ├── INFO.sh
   ├── var/config.json
   ├── Feature-/Worker-Metadaten
   └── GitHub Releases
          │
          ▼
   Documentation Core
          │
          ▼
   GitHub-Pages-Renderer
          │
          ▼
      Website DE/EN
```

Die DSM-Ausgabe ist derzeit deaktiviert. Es werden im Paketbuild keine `ui/help`, keine `helptoc.conf` und keine Help-Index-Datenbank erzeugt.

## Quellen und Single Source of Truth

Technische Werte bleiben in ihren fachlichen Quellen:

- Paketname, Version, DSM-Mindestversion und App-ID: `INFO.sh`
- Konfigurationsdefaults: `var/config.json`
- Releases und Download-Assets: GitHub Releases
- Worker-Fähigkeiten: Worker-/Feature-Metadaten
- längere Benutzertexte: `docs/core/de` und `docs/core/en`

Die Dokumentation darf technische Werte nur referenzieren bzw. beim Build einlesen, nicht separat duplizieren.

## Sprachmodell

Die aktiven Dokumentationssprachen sind:

```text
Documentation Core: de / en
GitHub Pages:       de / en
```

DSM-Locale-Mappings wie `ger` und `enu` gehören nur in eine zukünftige DSM-Renderer-Schicht und nicht mehr in den aktiven Core-Build.

Jede fachliche Seite besitzt dieselbe Dokument-ID in beiden Sprachen. Beispiel:

```yaml
---
id: status
section: status
title_key: docs.status.title
targets:
  - web
order: 10
---
```

`dsm_title_key` und das aktive Target `dsm` werden solange nicht verwendet, wie keine DSM-Hilfe ausgeliefert wird.

## GitHub Pages als aktuelle Ableitung

GitHub Pages liest direkt aus dem Documentation Core und ergänzt ihn um Web-spezifische Daten:

```text
docs/core/*
    +
INFO / Config / Feature-Daten
    +
GitHub Releases / Issues
    ↓
Web-Dokumentationsmodell
    ↓
GitHub Pages DE/EN
```

Website-spezifische Inhalte wie Downloads, Releases, Roadmap, Buildstatus und Repository-Links können zusätzlich eingeblendet werden, ohne in den fachlichen Kerntexten dupliziert zu werden.

## Zukünftige DSM-Ableitung

Soll die DSM-Hilfe später wieder aktiviert werden, bleibt `docs/core` die fachliche Quelle. Dann wird eine separate DSM-Pipeline ergänzt:

```text
Documentation Core
      ↓
DSM-Renderer
      ↓
ui/helptoc.conf
ui/help/{ger,enu}
ui/texts/{ger,enu}
      ↓
DSM-kompatibler offizieller Help-Indexer
      ↓
indexdb/helpindexdb
```

Diese Pipeline darf erst aktiviert werden, wenn ein mit dem aktuellen Synology-Toolkit kompatibler und belastbarer Help-Index-Buildweg verfügbar ist. Details stehen in `docs/dm-documentation-dsm-help-concept.md`.

## Build- und Testprinzip

Aktuell prüfen Tests nur aktive Ausgaben. Deshalb gibt es keine DSM-Help-Buildverträge mehr.

Für GitHub Pages gilt weiterhin:

1. technische Daten aus führenden Quellen sammeln,
2. Sprachpaarigkeit und Dokument-IDs validieren,
3. Website aus `docs/core` erzeugen,
4. Links und generierte technische Referenzen prüfen.

Falls DSM-Hilfe später zurückkehrt, müssen die tatsächlich ins SPK gelangenden Help-Artefakte vor dem Paketieren erzeugt und genau diese Artefakte getestet werden.
