# Konzept: GitHub Pages

## Ziel

ImgData erhält eine einfache, optisch saubere und mit wenig Pflegeaufwand betreibbare zweisprachige GitHub-Page.

Die Website ist bewusst **keine eigene Dokumentationsplattform mit Themen-Unterseiten**, sondern eine kompakte Toolseite mit je **einer zusammenhängenden Seite pro Sprache**. Inhaltlich ist die bestehende `README.md` der Ausgangspunkt. Sie wird für die Website nicht verkürzt oder auf eine reine Marketing-Zusammenfassung reduziert.

Eine DSM-Hilfe wird vorerst nicht gebaut oder mit dem SPK ausgeliefert.

## Inhaltsmodell

Die englische Website-Fassung wird direkt aus der bestehenden Repository-README erzeugt:

```text
README.md
```

Die deutsche Fassung liegt als vollständige Übersetzung unter:

```text
docs/site/README.de.md
```

Damit besteht die Website inhaltlich aus:

```text
/           → vollständige deutsche Toolseite
/en/        → vollständige englische Toolseite aus README.md
```

Es gibt keine zusätzlichen Themen-Unterseiten wie `/status/`, `/features/` oder `/configuration/`.

Die `README.md` selbst bleibt die ausführliche englische Projektbeschreibung im Repository. Sie wird durch die Pages-Integration nicht vereinfacht.

## Sprache

Die bisherige große Sprachwahl auf einer vorgeschalteten Startseite entfällt.

Die deutsche Fassung ist die Standardseite. Der Sprachwechsel erfolgt über die von MkDocs Material bereitgestellte kleine Sprachwahl im Seitenkopf:

```text
Deutsch  ↔  English
```

Dafür werden die `extra.alternate`-Links von Material verwendet. Es ist keine eigene Sprachwahl-Seite und kein eigenes JavaScript erforderlich.

## Repository-Entscheidung

Für die ImgData-Seite wird kein separates Repository angelegt. Die Toolseite gehört ausschließlich zu ImgData und wird als Project Page aus `AndreasVilippus/av_imgdata` veröffentlicht:

```text
https://andreasvilippus.github.io/av_imgdata/
```

Ein separates `AndreasVilippus.github.io`-Repository wäre erst sinnvoll, wenn später eine übergreifende Einstiegsseite für mehrere unabhängige Tools entsteht.

## Strikte Trennung vom DSM-Paketbuild

Der GitHub-Pages-Build ist kein Bestandteil des Paketbuilds und darf keine Voraussetzung für das Erzeugen eines SPK sein.

Verbindliche Regeln:

- `tools/build-package.sh` ruft weder MkDocs noch `tools/docs/build_github_pages.py` auf.
- `Makefile`, `SynoBuildConf/build`, `SynoBuildConf/install` und `ui/Makefile` enthalten keine GitHub-Pages-Buildschritte.
- `requirements-docs.txt` ist ausschließlich für Dokumentationsentwicklung und GitHub Actions bestimmt.
- Für einen normalen Paketbuild müssen weder MkDocs noch `mkdocs-material` installiert sein.
- `build/docs-site/` und `build/pages/` sind reine Website-Artefakte und niemals Paketinhalt.
- Ein Benutzer, der nur das DSM-Paket bauen möchte, muss keinen Schritt der Pages-Pipeline ausführen.

Die Trennung wird durch `tests/unit/static/test_github_pages_build_isolation.py` abgesichert.

## Architektur

```text
README.md --------------------------┐
                                   ├── tools/docs/build_github_pages.py
README.de.md -----------------------┘
                                              │
                                              ▼
                                      build/docs-site/
                                      ├── index.md
                                      └── en/index.md
                                              │
                                              ▼
                                        MkDocs Material
                                              │
                                              ▼
                                         build/pages/
                                              │
                                              ▼
                                        GitHub Pages
```

`tools/docs/build_github_pages.py` kopiert ausschließlich die beiden Sprachfassungen und die Website-Assets in das temporäre Staging-Verzeichnis. Die Quellen werden dabei nicht verändert.

## Gestaltung

Es wird bewusst kein eigenes Theme entwickelt. Verwendet werden:

- MkDocs Material,
- automatische Hell-/Dunkel-Darstellung,
- responsive Darstellung,
- integrierte Suche,
- Copy-Button für Codeblöcke,
- vorhandenes ImgData-Paketicon als Logo/Favicon,
- Inhaltsverzeichnis für die Abschnitte der langen Einzelseite,
- kleine Sprachwahl im Header,
- keine große Sprachwahl im Seiteninhalt,
- keine primäre Seitennavigation für Themen-Unterseiten,
- wenige CSS-Regeln für Breite und Abstände.

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

## Automatische Aktualisierung

Der Workflow liegt unter:

```text
.github/workflows/pages.yml
```

Die Website wird automatisch neu gebaut, wenn sich auf `main` einer dieser Bereiche ändert:

- `README.md`
- `docs/site/**`
- `tools/docs/build_github_pages.py`
- `requirements-docs.txt`
- `.github/workflows/pages.yml`

Damit aktualisiert eine Änderung der englischen README automatisch auch die englische GitHub-Page. Änderungen der deutschen Übersetzung aktualisieren die deutsche Fassung.

Zusätzlich kann der Workflow manuell gestartet werden und läuft bei veröffentlichten GitHub Releases erneut.

Pull Requests bauen und validieren die Website, werden aber nicht deployed.

## GitHub-Pages-Konfiguration

Das Repository wird einmalig unter:

```text
Settings → Pages → Build and deployment
```

auf:

```text
Source: GitHub Actions
```

gestellt.

Danach erfolgt die Veröffentlichung ausschließlich über `.github/workflows/pages.yml`. Ein `gh-pages`-Branch wird nicht benötigt.

## Abgrenzung zur DSM-Hilfe

Der GitHub-Pages-Build erzeugt keinerlei DSM-Hilfe-Artefakte:

- kein `ui/help/*`,
- kein `ui/helptoc.conf`,
- keine DSM-Help-Strings,
- kein `indexdb/helpindexdb`.

Der Grund für das Aussetzen der DSM-Hilfe und die vorgesehene technische Integration bleiben in `docs/dm-documentation-dsm-help-concept.md` dokumentiert.
