# Konzept: GitHub Pages

## Ziel

ImgData erhält eine einfache, optisch saubere und mit wenig Pflegeaufwand betreibbare zweisprachige Dokumentationsseite auf GitHub Pages.

Die Website ist die einzige aktuell aktive Dokumentationsausgabe. Eine DSM-Hilfe wird vorerst nicht gebaut oder mit dem SPK ausgeliefert.

Die fachlichen Inhalte stammen aus:

```text
docs/core/de/
docs/core/en/
```

Als Renderer wird **MkDocs Material** verwendet. Es liefert ohne eigenes Theme bereits Navigation, Suche, responsive Darstellung, Hell-/Dunkelmodus und eine brauchbare Standardoptik.

---

## Repository-Entscheidung

Für die ImgData-Seite wird **kein separates Repository** angelegt. Die Dokumentation gehört ausschließlich zu ImgData; ein zweites Repository würde unnötige Synchronisation für Dokumentation, Releases, Paketversionen und Buildlogik erzeugen.

Die Seite wird als Project Page direkt aus `AndreasVilippus/av_imgdata` veröffentlicht:

```text
https://andreasvilippus.github.io/av_imgdata/
```

Ein separates `AndreasVilippus.github.io`-Repository ist erst sinnvoll, wenn später eine übergreifende Einstiegsseite für mehrere unabhängige Tools entstehen soll.

---

## Strikte Trennung vom DSM-Paketbuild

Der GitHub-Pages-Build ist **kein Bestandteil des Paketbuilds** und darf keine Voraussetzung für das Erzeugen eines SPK sein.

Verbindliche Regeln:

- `tools/build-package.sh` ruft weder MkDocs noch `tools/docs/build_github_pages.py` auf.
- `Makefile`, `SynoBuildConf/build`, `SynoBuildConf/install` und `ui/Makefile` enthalten keine GitHub-Pages-Buildschritte.
- `requirements-docs.txt` ist ausschließlich für Dokumentationsentwicklung und GitHub Actions bestimmt.
- Für einen normalen Paketbuild müssen weder MkDocs noch `mkdocs-material` installiert sein.
- `build/docs-site/` und `build/pages/` sind reine Website-Artefakte und niemals Paketinhalt.
- Ein Benutzer, der nur das DSM-Paket bauen möchte, muss keinen Schritt der Pages-Pipeline ausführen.

Die Trennung wird durch `tests/unit/static/test_github_pages_build_isolation.py` abgesichert. Der Test verhindert, dass die Pages-spezifischen Entry-Points versehentlich in die Paketbuild-Dateien aufgenommen werden.

Damit existieren zwei unabhängige Buildpfade:

```text
DSM-Paket:
tools/build-package.sh
        ↓
Synology Toolkit
        ↓
SPK

GitHub Pages:
.github/workflows/pages.yml
        ↓
requirements-docs.txt
        ↓
tools/docs/build_github_pages.py
        ↓
MkDocs Material
        ↓
GitHub Pages
```

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

`build/docs-site/` und `build/pages/` werden nicht committed.

---

## Staging der Dokumentation

Die Markdown-Dateien unter `docs/core` besitzen interne Front-Matter-Metadaten, beispielsweise:

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

`tools/docs/build_github_pages.py` übernimmt deshalb vor dem MkDocs-Build:

1. Prüfung, dass deutsche und englische Dokumente paarig vorhanden sind,
2. Prüfung identischer Dokument-IDs,
3. Kopieren der Quellen nach `build/docs-site/`,
4. Entfernen des internen Front Matters aus der Website-Kopie,
5. Kopieren der Website-Startseite und des CSS,
6. Übernahme des vorhandenen Paket-Icons.

Die Quellen unter `docs/core` werden nicht verändert.

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

Die Root-Seite bietet die Sprachwahl. Weitere Dokumente werden nur unter `docs/core/de` und `docs/core/en` ergänzt und automatisch übernommen.

---

## Gestaltung

Es wird bewusst kein eigenes Theme entwickelt. Verwendet werden:

- MkDocs Material Standardtheme,
- automatische Hell-/Dunkel-Darstellung,
- responsive Navigation,
- integrierte Suche,
- Suchvorschläge und Hervorhebung,
- Copy-Button für Codeblöcke,
- vorhandenes ImgData-Paketicon als Logo/Favicon,
- wenige CSS-Regeln für Breite und Abstände.

Eigenes JavaScript ist zunächst nicht vorgesehen.

---

## Build-Abhängigkeiten

`requirements-docs.txt` enthält nur die optionale Dokumentations-Toolchain:

```text
mkdocs-material>=9,<10
```

Sie wird ausschließlich vom Pages-Workflow oder bei einem ausdrücklich gewünschten lokalen Website-Build installiert.

Optionaler lokaler Website-Build:

```bash
python3 -m venv .docs-venv
. .docs-venv/bin/activate
python3 -m pip install -r requirements-docs.txt
python3 tools/docs/build_github_pages.py
mkdocs build --strict --config-file docs/site/mkdocs.yml
```

Das Ergebnis liegt unter:

```text
build/pages/
```

Lokale Vorschau:

```bash
mkdocs serve --config-file docs/site/mkdocs.yml
```

Diese Befehle sind für Paketbauer nicht erforderlich.

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
- `.github/workflows/pages.yml`

Zusätzlich kann der Workflow manuell gestartet werden und läuft bei veröffentlichten GitHub Releases erneut.

Ablauf:

```text
Push auf main / Release / manueller Start
      │
      ▼
GitHub Actions
      │
      ├── Python einrichten
      ├── Dokumentations-Abhängigkeiten installieren
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

Pull Requests bauen und validieren die Website, werden aber nicht deployed.

---

## GitHub-Pages-Konfiguration

Das Repository muss einmalig unter:

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

Technische Werte werden nicht separat in deutscher und englischer Dokumentation gepflegt.

---

## Nächste Ausbaustufen

Die erste Version bleibt absichtlich klein. Später können schrittweise ergänzt werden:

1. aktuelle Paketversion aus `INFO.sh`,
2. aktueller SPK-Download aus GitHub Releases,
3. DSM-Mindestversion,
4. automatisch erzeugte Konfigurationsreferenz,
5. Worker-Plattformen und Worker-Downloads,
6. Screenshots,
7. sprachgleicher Seitenwechsel.

Diese Erweiterungen gehören in die Dokumentationspipeline und dürfen keine neue Abhängigkeit des DSM-Paketbuilds erzeugen.

---

## Abgrenzung zur DSM-Hilfe

Der GitHub-Pages-Build erzeugt keinerlei DSM-Hilfe-Artefakte:

- kein `ui/help/*`,
- kein `ui/helptoc.conf`,
- keine DSM-Help-Strings,
- kein `indexdb/helpindexdb`.

Der Grund für das Aussetzen der DSM-Hilfe und die vorgesehene technische Integration bleiben in `docs/dm-documentation-dsm-help-concept.md` dokumentiert.
