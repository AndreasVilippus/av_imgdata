# Konzept: GitHub Pages

## Ziel

ImgData erhält eine einfache, optisch saubere und mit wenig Pflegeaufwand betreibbare zweisprachige Dokumentationsseite auf GitHub Pages.

Die Website ist die einzige aktuell aktive Dokumentationsausgabe. Eine DSM-Hilfe wird vorerst nicht gebaut oder mit dem SPK ausgeliefert.

Die fachlichen Inhalte stammen direkt aus:

```text
docs/core/de/
docs/core/en/
```

Als technischer Renderer wird **MkDocs Material** verwendet. Es liefert ohne eigenes Theme bereits Navigation, Suche, responsive Darstellung, Hell-/Dunkelmodus, Code-Darstellung und eine brauchbare Standardoptik.

---

## Repository-Entscheidung

Für die ImgData-Seite wird **kein separates Repository** angelegt.

Die Dokumentation gehört funktional ausschließlich zu ImgData. Ein zweites Repository würde zusätzliche Synchronisation für Dokumentation, Releases, Paketversionen, Screenshots und Buildlogik erzeugen.

Die GitHub Page wird daher als Project Page direkt aus `AndreasVilippus/av_imgdata` veröffentlicht:

```text
https://andreasvilippus.github.io/av_imgdata/
```

Ein separates `AndreasVilippus.github.io`-Repository wäre erst sinnvoll, wenn später eine übergreifende Einstiegsseite für mehrere unabhängige Tools entstehen soll.

---

## Aktuelle Architektur

```text
Repository
   │
   ├── docs/core/de/
   ├── docs/core/en/
   ├── docs/site/
   │      ├── index.md
   │      ├── extra.css
   │      └── mkdocs.yml
   │
   ├── tools/docs/build_github_pages.py
   ├── requirements-docs.txt
   └── ui/PACKAGE_ICON_256.png
          │
          ▼
   Documentation staging
          │
          ▼
   build/docs-site/
          │
          ▼
      MkDocs Material
          │
          ▼
      build/pages/
          │
          ▼
   GitHub Pages Artifact
          │
          ▼
   GitHub Pages Deployment
```

`build/docs-site/` und `build/pages/` sind ausschließlich temporäre Build-Ausgaben und werden nicht committed.

---

## Warum ein Staging-Verzeichnis verwendet wird

Die Markdown-Dateien unter `docs/core` enthalten eigene Front-Matter-Metadaten wie:

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

Diese Metadaten gehören zum Documentation Core und sollen nicht direkt als Website-Inhalt erscheinen.

`tools/docs/build_github_pages.py` übernimmt daher vor dem MkDocs-Build:

1. Prüfung, dass deutsche und englische Dokumente paarig vorhanden sind,
2. Prüfung, dass beide Sprachfassungen dieselbe Dokument-ID besitzen,
3. Kopieren der Markdown-Dateien nach `build/docs-site/`,
4. Entfernen des internen Front Matters aus der gerenderten Kopie,
5. Kopieren der Website-Startseite,
6. Kopieren des kleinen Zusatz-CSS,
7. Übernahme des vorhandenen Paket-Icons.

Die Quellen unter `docs/core` werden dabei nicht verändert.

---

## Website-Struktur

Die erzeugte Website besitzt zunächst:

```text
/
├── de/
│   ├── index/
│   └── status/
└── en/
    ├── index/
    └── status/
```

Die Root-Seite bietet eine einfache Sprachwahl:

```text
ImgData

[Deutsch] [English]
```

Weitere Dokumente werden ausschließlich unter `docs/core/de` und `docs/core/en` ergänzt. Der Staging-Build übernimmt sie automatisch; ein zusätzlicher manueller Kopierschritt ist nicht erforderlich.

---

## Gestaltung

Es wird bewusst **kein eigenes Theme** entwickelt.

Verwendet werden:

- MkDocs Material Standardtheme,
- automatische Hell-/Dunkel-Darstellung,
- responsive Navigation,
- integrierte Suche,
- Suchvorschläge und Hervorhebung,
- Copy-Button für Codeblöcke,
- vorhandenes ImgData-Paketicon als Logo/Favicon,
- nur wenige CSS-Regeln für maximale Inhaltsbreite und Startseiten-Abstände.

Eigenes JavaScript ist für die erste Version nicht vorgesehen.

---

## Build-Abhängigkeiten

Die Website besitzt eine eigene kleine Dependency-Datei:

```text
requirements-docs.txt
```

Aktuell:

```text
mkdocs-material>=9,<10
```

Damit bleibt der Dokumentationsbuild vom Python-Runtime-Stack des DSM-Pakets getrennt.

Lokaler Testbuild:

```bash
python3 -m pip install -r requirements-docs.txt
python3 tools/docs/build_github_pages.py
mkdocs build --strict --config-file docs/site/mkdocs.yml
```

Das Ergebnis liegt danach ausschließlich unter:

```text
build/pages/
```

Zum lokalen Betrachten kann zusätzlich verwendet werden:

```bash
mkdocs serve --config-file docs/site/mkdocs.yml
```

Vorher muss einmal `build_github_pages.py` ausgeführt worden sein.

---

## Automatische Aktualisierung

Der Workflow liegt unter:

```text
.github/workflows/pages.yml
```

Bei Änderungen auf `main` an folgenden Bereichen wird die Website automatisch neu gebaut:

- `docs/core/**`
- `docs/site/**`
- `tools/docs/build_github_pages.py`
- `requirements-docs.txt`
- dem Pages-Workflow selbst

Zusätzlich kann der Workflow manuell gestartet werden und wird bei veröffentlichten GitHub Releases erneut ausgeführt. Der Release-Trigger ist bereits vorgesehen, auch wenn Release-Daten erst in einem späteren Schritt in die Seiten eingeblendet werden.

Ablauf:

```text
Push auf main
      │
      ▼
GitHub Actions
      │
      ├── Python einrichten
      ├── MkDocs Material installieren
      ├── Documentation Core validieren
      ├── build/docs-site erzeugen
      ├── MkDocs --strict ausführen
      └── build/pages erzeugen
              │
              ▼
      Pages Artifact hochladen
              │
              ▼
      GitHub Pages deployen
```

Pull Requests führen denselben Build und dieselben Prüfungen aus, werden aber **nicht deployed**.

---

## GitHub-Pages-Konfiguration

Das Repository muss einmalig in GitHub unter:

```text
Settings → Pages → Build and deployment
```

auf:

```text
Source: GitHub Actions
```

gestellt werden.

Danach erfolgt die Veröffentlichung ausschließlich über `.github/workflows/pages.yml`. Ein `gh-pages`-Branch wird nicht benötigt.

---

## Single Source of Truth

| Information | Führende Quelle | Website |
|---|---|---|
| Fachliche Dokumentation | `docs/core/de`, `docs/core/en` | automatisch |
| Website-Startseite | `docs/site/index.md` | direkt |
| Website-Konfiguration | `docs/site/mkdocs.yml` | direkt |
| kleines Styling | `docs/site/extra.css` | direkt |
| Paketicon | `ui/PACKAGE_ICON_256.png` | automatisch kopiert |
| Paketname / Version | `INFO.sh` | später automatisch |
| DSM-Mindestversion | `INFO.sh` | später automatisch |
| Konfigurationsdefaults | `var/config.json` | später automatisch |
| Feature-/Worker-Daten | Projektmetadaten | später automatisch |
| Release / Download | GitHub Releases | später automatisch |

Technische Werte sollen nicht in deutschen und englischen Markdown-Dateien separat gepflegt werden.

---

## Nächste Ausbaustufen

Die erste Version bleibt absichtlich klein. Danach können schrittweise ergänzt werden:

1. aktuelle Paketversion aus `INFO.sh`,
2. aktueller SPK-Download aus GitHub Releases,
3. DSM-Mindestversion,
4. automatisch erzeugte Konfigurationsreferenz,
5. Worker-Plattformen und Worker-Downloads,
6. Screenshots,
7. stabiler sprachgleicher Seitenwechsel statt nur Wechsel auf die jeweilige Sprachstartseite.

Diese Erweiterungen werden bevorzugt in `tools/docs/build_github_pages.py` bzw. weiteren kleinen Generatoren umgesetzt. MkDocs selbst bleibt möglichst unverändert.

---

## Abgrenzung zur DSM-Hilfe

Der GitHub-Pages-Build erzeugt keinerlei DSM-Hilfe-Artefakte:

- kein `ui/help/*`,
- kein `ui/helptoc.conf`,
- keine DSM-Help-Strings,
- kein `indexdb/helpindexdb`.

Der Grund für das Aussetzen der DSM-Hilfe und die technisch vorgesehene Integration bleiben in `docs/dm-documentation-dsm-help-concept.md` dokumentiert.
