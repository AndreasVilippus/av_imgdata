# Konzept: GitHub Pages

## Ziel

ImgData erhält eine zweisprachige öffentliche Dokumentation auf GitHub Pages. Die Website ist derzeit die einzige aktiv erzeugte Dokumentationsausgabe. Eine DSM-Hilfe wird vorerst nicht gebaut oder mit dem SPK ausgeliefert.

Die fachlichen Inhalte stammen direkt aus `docs/core/de` und `docs/core/en`.

## Architektur

```text
Repository
   │
   ├── docs/core/de + docs/core/en
   ├── INFO.sh
   ├── var/config.json
   ├── Feature-/Worker-Metadaten
   ├── Screenshots / Icons
   └── GitHub Releases / Issues / Actions
          │
          ▼
   Web-Dokumentationsbuild
          │
      ┌───┴───┐
      ▼       ▼
     /de/    /en/
          │
          ▼
      GitHub Pages
```

Die Website wird **nicht mehr von einer DSM-Hilfe abgeleitet** und hängt nicht von `helptoc.conf`, DSM-Locales oder einem DSM-Help-Renderer ab.

## Single Source of Truth

| Information | Führende Quelle | GitHub Pages |
|---|---|---|
| Fachliche Dokumentation | `docs/core/de`, `docs/core/en` | direkt |
| Paketname / Version | `INFO.sh` | automatisch |
| DSM-Mindestversion | `INFO.sh` | automatisch |
| Konfigurationsdefaults | `var/config.json` | automatisch |
| Feature-/Worker-Daten | Projektmetadaten | automatisch |
| Release / Download | GitHub Releases | automatisch |
| Release Notes | Release/Changelog | automatisch |
| Screenshots / Icons | Repository | eingebunden |
| Issues / Roadmap | GitHub | optional |

Technische Werte werden nicht in beiden Sprachfassungen separat gepflegt.

## Dokumentmodell

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

## Zweisprachigkeit

Die Website stellt mindestens bereit:

```text
/de/
/en/
```

Zu jeder fachlichen Dokument-ID muss eine deutsche und englische Variante vorhanden sein. Ein Sprachumschalter soll möglichst auf die korrespondierende Seite wechseln.

Sprachneutral bleiben insbesondere Versionen, Zahlenwerte, Defaults, Paketdateinamen, Release-Daten und technische IDs.

## Automatisch ergänzte Inhalte

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

## Abgrenzung zur DSM-Hilfe

Die gemeinsame fachliche Quelle bleibt bewusst so gestaltet, dass eine spätere DSM-Ausgabe möglich ist. Aktuell gibt es aber keine technische Kopplung.

Insbesondere erzeugt der GitHub-Pages-Build nicht:

- `ui/help/*`,
- `ui/helptoc.conf`,
- DSM-`strings` für die Hilfenavigation,
- `indexdb/helpindexdb`.

Der Grund für das Aussetzen der DSM-Hilfe und die vorgesehene korrekte Integration sind in `docs/dm-documentation-dsm-help-concept.md` dokumentiert.

## Build- und CI-Regeln

Der Web-Build soll prüfen:

1. deutsche und englische Dokumente besitzen passende IDs,
2. interne Links sind auflösbar,
3. technische Werte werden aus ihren führenden Quellen gelesen,
4. generierte Konfigurations- und Release-Daten sind aktuell,
5. die Website kann unabhängig vom DSM-Paketbuild erzeugt werden.

Eine fehlende oder deaktivierte DSM-Hilfe darf den GitHub-Pages-Build nicht beeinflussen.
