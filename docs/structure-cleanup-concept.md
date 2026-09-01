# Konzept: Strukturbereinigung des Projekts

## 1. Ziel

Dieses Dokument beschreibt eine schrittweise Bereinigung und Vereinheitlichung der Repository-Struktur von `av_imgdata`.

Der Schwerpunkt liegt ausdrücklich **nicht** auf einem kosmetischen Verschieben von Dateien. Jede Strukturänderung muss vorab gegen die tatsächlichen Build-, Runtime-, Import-, Paket-, Test- und Dokumentationsverträge geprüft werden.

Das Konzept folgt deshalb dem Ablauf:

```text
Ist-Struktur
    ↓
Abhängigkeiten und Verträge prüfen
    ↓
Befund je Strukturpunkt
    ↓
Zielstruktur festlegen
    ↓
Migration nur bei fachlichem/technischem Nutzen
    ↓
Contract-/Build-/Regressionstests
```

Grundregel:

> Eine bestehende Struktur wird nur geändert, wenn der Zielzustand die Wartbarkeit, Zuständigkeit oder technische Absicherung messbar verbessert und die betroffenen Verträge vorher identifiziert wurden.

Dieses Konzept berücksichtigt insbesondere:

- `docs/architecture-and-development-guidelines.md`
- `docs/dm-documentation-core-concept.md`
- `docs/review-ui-unification-concept.md`
- `docs/preview-unification-technical-concept.md`
- `docs/preview-unification-source-inventory.md`
- `docs/preview-unification-reference-baseline.md`
- `docs/external-worker-pre-pipeline-concept.md`
- `docs/external-worker-gui-coverage.md`
- `docs/optional-worker-concept.md`
- `docs/status-concept-integrated.md`
- `processor_contract/README.md`

Die Architektur-Guidelines bleiben die übergeordnete Vorgabe. Dieses Dokument konkretisiert nur, wie die bestehende Verzeichnisstruktur kontrolliert dorthin entwickelt werden kann.

---

# 2. Wichtigste geprüfte Randbedingungen

Vor der Einzelbewertung wurden die zentralen Strukturverträge geprüft.

## 2.1 DSM-Paketbuild kopiert `src/` und `app/` als komplette Verzeichnisse

`SynoBuildConf/install` baut das Paket derzeit unter anderem mit:

```text
cp ... src <package>
cp ... app <package>
```

Damit sind `src/` und `app/` nicht nur Entwicklungsordner, sondern Bestandteil des installierten Runtime-Layouts.

Folge:

- Verschiebungen innerhalb von `src/` verändern Python-Importpfade im installierten Paket.
- Verschiebungen von `app/` oder `src/` verändern Startskripte und Pakettests.
- eine Bereinigung des Python-Packagings muss als eigene Migration behandelt werden und darf nicht beiläufig erfolgen.

## 2.2 `app/main.py` setzt `src/` explizit auf `sys.path`

Der Runtime-Einstiegspunkt macht aktuell bewusst:

```python
SRC_DIR = .../src
sys.path.insert(0, SRC_DIR)
```

und importiert anschließend unter anderem:

```python
from api.imgdata_api import ...
from services.external_worker_gui_integration import ...
```

Das aktuelle Python-Modell ist damit technisch eindeutig:

```text
src/
    = Python import root
```

und **nicht**:

```text
src/av_imgdata/
    = alleiniger Python import root
```

`src/av_imgdata/` ist derzeit nur ein echtes Package innerhalb dieses Import-Roots und enthält im Wesentlichen die DB-Schicht.

## 2.3 DSM-Startskript nutzt ebenfalls `PYTHONPATH=<package>/src`

`scripts/start-stop-status` startet beispielsweise die DB-Initialisierung mit:

```text
PYTHONPATH="${SYNOPKG_PKGDEST}/src"
python -m av_imgdata.db.bootstrap
```

Damit ist die Mischform aus Top-Level-Modulen und `av_imgdata.db` nicht nur historisch, sondern aktuell Bestandteil des Runtime-Vertrags.

## 2.4 Architektur-Guidelines definieren die derzeitigen Backend-Verzeichnisse ausdrücklich

Die geltenden Guidelines definieren:

```text
src/api/       API request parsing
src/handler/   Remote-system access
src/services/  focused utility/domain logic
src/models/    data containers
```

Eine Umstellung auf eine komplett neue Package-/Layer-Struktur darf daher nicht allein aus ästhetischen Gründen erfolgen. Zuerst müssten die Architecture Guidelines bewusst geändert werden.

## 2.5 `tools/` existiert bereits und ist der vorgesehene Entwicklungs-/Build-Werkzeugordner

Die erste Strukturprüfung hatte `tools/` als mögliche Ergänzung genannt. Die Prüfung zeigt: `tools/` existiert bereits umfangreich und enthält unter anderem:

- Paketbuild
- Worker-Build
- Native-Processor-Builds
- Smoke-/Functional-Checks
- Strukturchecks
- Worker Enrollment/Store Tools

Die Architecture Guidelines nennen `tools/` ausdrücklich für native Build-/Package-Integration.

Folge:

> `tools/` muss nicht neu eingeführt, sondern nur intern sinnvoll gegliedert werden, wenn die Menge weiter wächst.

## 2.6 `scripts/` ist ein DSM-Lifecycle-Verzeichnis

Der bestehende Ordner enthält die Synology-Paketskripte:

```text
preinst
postinst
preuninst
postuninst
preupgrade
postupgrade
start-stop-status
```

sowie einen paketnahen `exiftool-wrapper`.

Damit sollte `scripts/` semantisch für **DSM Package Lifecycle / Runtime Wrapper** reserviert bleiben.

Das Documentation-Core-Konzept schlägt derzeit noch Dokumentationsgeneratoren unter `scripts/` vor. Für die tatsächliche Umsetzung ist das zu korrigieren:

```text
nicht:
    scripts/docs_build.py

sondern:
    tools/docs/...
```

Damit bleibt die DSM-Paketstruktur eindeutig.

## 2.7 `ui/dist/` ist tatsächlich ein Build-Artefakt, aber derzeit versioniert

`ui/Makefile` definiert:

```text
JS_DIR=dist
BUNDLE_JS=dist/av-img-data.bundle.js
```

und erzeugt `dist` über den UI-Build. `clean` löscht `dist` vollständig.

Gleichzeitig ist `ui/dist/av-img-data.bundle.js` im Repository versioniert.

Damit ist bestätigt:

> `ui/dist` ist technisch erzeugbar und kein primärer Source-of-Truth-Ordner.

Vor dem Entfernen aus Git muss allerdings geprüft werden, ob alle relevanten Entwicklungs-, CI- und DSM-Buildumgebungen den UI-Build reproduzierbar ausführen können.

## 2.8 Tests sind bereits teilweise konsolidiert

`tests/unit/` enthält bereits:

```text
api/
db/
handlers/
parser/
scripts/
services/
static/
ui/
```

Daneben existieren weiterhin ältere `tests/test_*.py` direkt unter `tests/`.

Die Zielstruktur ist damit nicht neu zu erfinden. Es handelt sich um eine **laufende, noch nicht abgeschlossene Konsolidierung**.

## 2.9 `face_detection_models/` enthält tatsächlich Assets

`src/face_detection_models/` enthält:

```text
README.md
haarcascade_frontalface_default.xml
```

also kein Python-Package, sondern ein Runtime-Modell-/Assetverzeichnis.

`src/services/face_detector.py` löst die Datei aktuell relativ zu `src/services` über:

```text
../face_detection_models/haarcascade_frontalface_default.xml
```

Ein Verschieben ist möglich, aber nur zusammen mit:

- Pfadauflösung
- Paketbuild
- Lizenz-/Attributionsprüfung
- Tests
- ggf. Dokumentation der Model Assets

## 2.10 Processor/Worker-Trennung ist konzeptionell bereits definiert

`processor_contract/README.md` definiert `processor_contract/` ausdrücklich als sprachneutralen Vertrag zwischen DSM-Backend und austauschbaren Prozessorimplementierungen.

`processors/native/` enthält konkrete lokale/native Implementierungen:

```text
face_processor/
image_processor/
image_backend_vips/
```

`worker/` ist dagegen die externe Runtime mit eigener Struktur aus `src`, `protocol`, `jobs`, `packaging`, `tests` usw.

Diese Dreiteilung ist fachlich sinnvoll und entspricht den Worker-Konzepten:

```text
processor_contract/
    neutraler Vertrag

processors/native/
    lokale Compute-Implementierungen

worker/
    externe Ausführungsruntime
```

Eine Zusammenlegung würde die bestehende Verantwortungsgrenze eher verschlechtern.

---

# 3. Bewertungsmodell für Strukturänderungen

Jeder Umbaupunkt wird nach fünf Kriterien bewertet.

| Kriterium | Bedeutung |
|---|---|
| Nutzen | verbessert die Struktur tatsächlich Wartbarkeit/Verständlichkeit? |
| Build-Risiko | betrifft DSM-, UI-, Native- oder Worker-Build? |
| Runtime-Risiko | ändern sich Imports, Pfade oder gestartete Komponenten? |
| Contract-Risiko | sind Tests, Scripts, Schemas oder dokumentierte Verträge pfadabhängig? |
| Empfehlung | jetzt, opportunistisch, später oder nicht ändern |

Klassifizierung:

```text
A = sofort/geringes Risiko
B = gezielte Migration sinnvoll
C = nur bei ohnehin notwendigem Refactoring
D = aktuell nicht ändern
```

---

# 4. Punkt 1 – Root-Struktur

## Ursprüngliche Annahme

Der Root mischt DSM-Paketlayout und Monorepo-/Softwareprojektlayout.

## Prüfung

Bestätigt wurden insbesondere:

```text
INFO.sh
SynoBuildConf/
conf/
scripts/
var/
```

als paketnahe DSM-Struktur sowie:

```text
app/
src/
ui/
processors/
processor_contract/
worker/
tests/
tools/
docs/
```

als Entwicklungs-/Komponentenstruktur.

`SynoBuildConf/install` und die Root-/UI-Makefiles greifen direkt auf mehrere dieser Pfade zu.

## Befund

Die Root-Struktur ist **nicht inkonsistent genug, um eine Root-Reorganisation zu rechtfertigen**.

Insbesondere sollten die DSM-relevanten Pfade nicht in einen künstlichen Unterordner `package/` verschoben werden, solange dies keinen konkreten Buildvorteil bringt.

## Ergebnis

**Klasse D – Root grundsätzlich beibehalten.**

Zulässig sind nur klar abgegrenzte Ergänzungen/Untergliederungen innerhalb bestehender Bereiche.

---

# 5. Punkt 2 – Backend `src/`

## Ursprüngliche Annahme

`src/` wirkt inkonsistent, weil `src/av_imgdata/` neben `src/api`, `src/services`, `src/models`, `src/parser`, `src/handler` liegt.

## Prüfung

Bestätigt:

- `src` ist expliziter Runtime-Import-Root.
- `app/main.py` importiert `api.*` und `services.*` als Top-Level-Pakete.
- `scripts/start-stop-status` nutzt `PYTHONPATH=<package>/src`.
- `src/av_imgdata` enthält derzeit vor allem `db/`.
- Services importieren gleichzeitig `av_imgdata.db.*` und andere Module als `services.*`.
- Tests spiegeln diese Importstruktur.
- `tools/check_syntax_and_structure.py` enthält feste Pfade wie `src/services/config_service.py`.
- die Architecture Guidelines definieren die bestehenden Verzeichnisrollen explizit.

## Befund

Die Struktur ist uneinheitlich, aber aktuell **ein etablierter technischer Vertrag**.

Ein Ziel wie:

```text
src/av_imgdata/api
src/av_imgdata/services
...
```

wäre ein vollständiges Python-Packaging-Refactoring und hätte Auswirkungen auf:

- alle Imports
- `app/main.py`
- DSM-Startskripte
- Strukturchecks
- Unit-/Integrationstests
- statische Pfadtests
- Build-/Packaging-Logik
- möglicherweise externe Debug-/Entwicklungsaufrufe

## Ergebnis

**Klasse C – derzeit nicht als reine Strukturmaßnahme durchführen.**

Stattdessen gilt:

1. keine weiteren neuen Top-Level-Kategorien unter `src/` ohne Architekturentscheidung;
2. bestehende Kategorien `api`, `handler`, `services`, `models`, `parser`, `av_imgdata/db` zunächst beibehalten;
3. eine spätere echte Python-Package-Migration nur als eigenes Projekt mit Import-Compatibility-Plan.

---

# 6. Punkt 3 – `src/imgdata.py`

## Ursprüngliche Annahme

`src/imgdata.py` ist mit rund 498 KB ein struktureller Monolith.

## Prüfung

Bestätigt:

- Datei ist außergewöhnlich groß.
- parallel existieren bereits spezialisierte Services.
- Architecture Guidelines verlangen, gemeinsame Multi-Step-Workflows nicht zwischen API, Cleanup, Checks und Face Match zu duplizieren.
- Preview-, Recognition-, Worker-, Persistence- und Config-Konzepte setzen zunehmend auf dedizierte Services.

Nicht empfohlen ist jedoch ein rein dateigrößengetriebenes Zerschneiden.

## Vor jeder Extraktion prüfen

Für jeden zu extrahierenden Block:

1. Welche öffentlichen Methoden von `ImgDataService` verwenden API/UI/Tests?
2. Welcher Zustand liegt auf `self` und wird gemeinsam genutzt?
3. Gibt es Lock-/Progress-/Session-/Persistence-Abhängigkeiten?
4. Gibt es bereits einen passenden Service?
5. Ist die Logik Orchestrierung oder echte Fachlogik?
6. Ist sie Teil eines etablierten älteren Face-Match-Flows, der laut Preview-Referenzkonzept als Reifegrad-A-Verhalten geschützt werden muss?

## Befund

`imgdata.py` sollte **nicht verschoben**, sondern schrittweise zu einer Facade/Orchestrierungsschicht reduziert werden.

## Ergebnis

**Klasse B – hohe Priorität, aber funktionsweise extrahieren statt Struktur-Großumbau.**

Empfohlenes Muster:

```text
ImgDataService
    ↓ delegiert
src/services/<focused_service>.py
```

Dabei bleiben bestehende öffentliche Methoden zunächst als kompatible Delegationspunkte erhalten.

---

# 7. Punkt 4 – `handler`, `parser`, `services`

## Ursprüngliche Annahme

Die Begriffe können sich semantisch überschneiden.

## Prüfung gegen Guidelines

Die Architecture Guidelines definieren bereits:

```text
handler = remote-system access
services = focused utility/domain logic
models = data containers
api = request parsing
```

`parser/` ist zusätzlich für Format-/Metadatenparser etabliert und wird durch Tests gespiegelt (`tests/unit/parser`).

## Befund

Die Trennung ist ausreichend klar, wenn sie konsequent angewandt wird.

Das Problem ist weniger der Ordnername als einzelne Dateien, die historisch mehrere Rollen besitzen können.

## Ergebnis

**Klasse D – Ordner nicht umbenennen/zusammenlegen.**

Stattdessen neue Dateien nach diesen Regeln einordnen:

```text
Synology/remote access        -> handler/
Format-/Quellparser           -> parser/
fachliche/technische Logik    -> services/
DTO/Data container            -> models/
HTTP request/response         -> api/
DB persistence                -> av_imgdata/db/
```

Wenn ein `handler` überwiegend Fachlogik enthält, wird die Logik in einen Service extrahiert; der Handler bleibt Adapter.

---

# 8. Punkt 5 – `models/`

## Prüfung

`src/models/` entspricht den Architecture Guidelines. Gemeinsame Datenmodelle wie Bounding Boxes passen dort hinein; Transformationslogik liegt dagegen bereits sinnvoll in Services wie `bbox_normalizer.py`.

## Befund

Die bestehende Trennung ist sinnvoll.

## Ergebnis

**Klasse D – beibehalten.**

Regel ergänzen:

> `models/` enthält Datenrepräsentation und kleine modellinhärente Operationen, aber keine DSM-, API-, Dateisystem- oder Workflow-Orchestrierung.

---

# 9. Punkt 6 – `face_detection_models/`

## Prüfung

Der Ordner enthält tatsächliche Runtime Assets:

```text
haarcascade_frontalface_default.xml
```

und wird von `src/services/face_detector.py` über einen festen relativen Pfad aufgelöst.

Das Paket kopiert `src/` vollständig, wodurch das Asset automatisch mit ausgeliefert wird.

## Möglicher Zielzustand

Semantisch wäre beispielsweise denkbar:

```text
resources/models/face_detection/
```

oder ein klarer Paket-Assetpfad.

## Vor einer Verschiebung zwingend prüfen

- Lizenz und Attribution des Haar-Cascade-Assets
- alle Pfadreferenzen
- Paketinhalt nach Build
- installierte Runtime-Pfadauflösung
- optionale Tests ohne OpenCV
- bestehende Face-Detection-Fixtures

## Befund

Der aktuelle Pfad ist semantisch nicht optimal, aber technisch sehr robust, weil `src` komplett gepackt wird.

Ein Umzug bringt aktuell wenig Nutzen.

## Ergebnis

**Klasse C/D – erst zusammen mit einer echten Resource-/Model-Asset-Governance ändern.**

Die separaten InsightFace-Modelle bleiben gemäß Architecture Guidelines ohnehin user-supplied und dürfen nicht mit diesem einfachen Assetmodell vermischt werden.

---

# 10. Punkt 7 – UI-Grundstruktur

## Prüfung

`ui/src` enthält bereits die konventionellen Bereiche:

```text
components/
i18n/
mixins/
services/
styles/
views/
```

Das ist grundsätzlich konsistent.

Die Architecture Guidelines erlauben derzeit ausdrücklich wiederverwendbare Logik in Mixins **oder** dedizierten Modulen.

Die Review- und Preview-Konzepte schlagen zusätzliche zentrale Bausteine/Services/Adapter vor.

## Befund

Ein sofortiger Umbau auf eine globale `features/`-Struktur wäre unnötig und würde viele Komponenten bewegen, ohne die eigentliche Logikschuld zu beheben.

## Ergebnis

**Klasse C – keine globale UI-Verzeichnisreorganisation.**

Stattdessen bei neuen Querschnittsfunktionen klare Unterbereiche verwenden, z. B.:

```text
ui/src/components/preview/
ui/src/services/preview-*.js
ui/src/adapters/preview/
```

oder analog für Review-Bausteine.

Erst wenn mehrere abgeschlossene Features ein stabiles gemeinsames Muster zeigen, kann eine `features/`-Struktur neu bewertet werden.

---

# 11. Punkt 8 – große UI-Mixins

## Prüfung

Die Preview-/Review-Bestandsaufnahme zeigt, dass Preview-, Status-, Suggestions-, Actions- und View-spezifische Logik teilweise über Mixins verteilt ist.

Gleichzeitig gelten ältere Face-Match-Preview-Flows laut `preview-unification-reference-baseline.md` als technisch ausgereifte Referenz und dürfen durch eine Strukturmigration nicht funktional verändert werden.

## Befund

Mixins sind ein tatsächlicher Refactoring-Kandidat, aber nicht primär ein Ordnerproblem.

## Ergebnis

**Klasse B – opportunistisch bei Preview-/Review-Vereinheitlichung abbauen.**

Reihenfolge:

1. Verhalten durch Golden-Master-/Regressionstests sichern.
2. querschnittliche technische Logik in Services/Adapter/Komponenten extrahieren.
3. fachliche View-Logik im bestehenden Mixin zunächst als Delegation belassen.
4. erst nach stabiler Migration Mixin verkleinern oder auflösen.

Keine gleichzeitige kosmetische Verschiebung aller UI-Dateien.

---

# 12. Punkt 9 – `ui/dist`

## Prüfung

Bestätigt:

- `ui/Makefile` erzeugt `dist`.
- `clean` löscht `dist`.
- `dist/av-img-data.bundle.js` ist trotzdem versioniert.
- Root `.gitignore` ignoriert nur `/dist/`, nicht `/ui/dist/`.

## Vor Entfernung aus Git prüfen

1. DSM pkgscripts Build erzeugt Bundle zuverlässig.
2. Debian-Entwicklungsbuild erzeugt Bundle zuverlässig.
3. CI besitzt Node/Snpm/Pnpm-Abhängigkeiten passend zum jeweiligen Buildweg.
4. Debug-Paketbuild funktioniert ohne vorab eingechecktes Bundle.
5. keine Tests lesen absichtlich `ui/dist` statt `ui/src`.
6. Package-Inhalt bleibt identisch.
7. Reproduzierbarkeit/Versionsbindung über `pnpm-lock.yaml` ist ausreichend.

## Befund

`ui/dist` ist klar ein Build-Artefakt und langfristig ein guter Kandidat für Entfernung aus Git.

Der Synology-UI-Build benutzt allerdings `/usr/local/tool/snpm`, weshalb vor Entfernung die tatsächlichen lokalen/CI Buildpfade verifiziert werden müssen.

## Ergebnis

**Klasse B – gezielt vorbereiten, nicht sofort löschen.**

Akzeptanzkriterium:

```text
clean checkout
    -> package build
    -> funktionierendes UI im SPK
```

ohne irgendeine vorversionierte Datei in `ui/dist`.

---

# 13. Punkt 10 – DSM-UI-Dateien und Vue-Frontend unter `ui/`

## Prüfung

Unter `ui/` liegen bewusst beide Schichten:

```text
DSM:
    app.config
    config.define
    index.cgi
    texts/
    images/

Frontend Build:
    package.json
    webpack.config.js
    src/
    dist/
```

`INFO.sh` definiert `dsmuidir="ui"`. Das Documentation-Core-Konzept plant außerdem DSM-Hilfe unter `ui/help`, `ui/helptoc.conf` und generierte `ui/texts`-Inhalte.

## Befund

Die physische Mischung ist durch den DSM-Zielordner sachlich gerechtfertigt.

Eine Aufteilung in `frontend/` und `dsm-ui/` würde zusätzliche Buildkopierlogik schaffen, ohne klaren Nutzen.

## Ergebnis

**Klasse D – `ui/` beibehalten.**

Aber Source-vs-Generated-Regeln explizit machen:

```text
Source:
    ui/src
    ui/images (soweit handgepflegt)
    DSM config files

Generated:
    ui/dist
    zukünftig ui/help
    zukünftig ui/helptoc.conf
    ggf. generierte Anteile von ui/texts
```

Die Documentation-Core-Implementierung muss verhindern, dass handgepflegte UI-i18n-Texte versehentlich von generierten Help-Strings überschrieben werden. Entweder werden Abschnitte zusammengeführt oder getrennte Source-Dateien vor dem finalen DSM-`strings`-Build kombiniert.

---

# 14. Punkt 11 – `worker/`

## Prüfung

Der Worker besitzt bereits eine eigenständige, klare C++-/Runtime-Struktur:

```text
CMakeLists.txt
cmake/
config/
include/
jobs/
packaging/
protocol/
src/
tests/
```

Die Worker-Konzepte definieren ihn als externe Ausführungsruntime, während DSM Workflow, Status, Findings, Persistence und Writes besitzt.

## Befund

Die Struktur unterstützt genau diese Trennung.

## Ergebnis

**Klasse D – nicht strukturell umbauen.**

Neue Worker-Funktionen müssen innerhalb dieser bestehenden Verantwortung einsortiert werden, nicht durch neue Root-Level-Worker-Nebenprojekte.

---

# 15. Punkt 12 – `processors/` vs. `worker/`

## Prüfung

`processors/native/` enthält lokale Compute-Implementierungen.

`worker/` enthält die externe Runtime.

Die Architecture Guidelines schreiben außerdem vor, dass Runtime-Zugriff auf native Binaries über Backend-Service-Adapter erfolgt und Worker nur Processor Contracts ausführen.

## Befund

Die Trennung ist fachlich richtig und sollte nicht vereinheitlicht werden.

## Ergebnis

**Klasse D – beibehalten und dokumentieren.**

Verbindliche Semantik:

```text
processors/native/  = Compute Engine Implementations
worker/             = Remote Runtime / Transport / Job Host
```

---

# 16. Punkt 13 – `processor_contract/`

## Prüfung

Der README definiert explizit eine sprachneutrale Grenze zwischen DSM und austauschbaren Processor-Implementierungen. Die Worker-Konzepte bauen darauf auf.

Die Schemas sind damit nicht bloß Worker-Dateien und gehören gerade **nicht** unter `worker/`.

## Befund

Der separate Root-Level-Ordner ist gerechtfertigt.

## Ergebnis

**Klasse D – beibehalten.**

Eine spätere Umbenennung wie `contracts/processor/` wäre nur sinnvoll, wenn weitere gleichrangige Contract-Familien entstehen. Aktuell würde sie nur Pfade brechen.

---

# 17. Punkt 14 – Teststruktur

## Prüfung

Die aktuelle Struktur ist weiter entwickelt als zunächst angenommen.

Bereits vorhanden:

```text
tests/unit/api
tests/unit/db
tests/unit/handlers
tests/unit/parser
tests/unit/scripts
tests/unit/services
tests/unit/static
tests/unit/ui

tests/contract
tests/integration
tests/regression
tests/fixtures
```

Parallel liegen ältere `tests/test_*.py` direkt unter `tests/`.

`tools/check_syntax_and_structure.py` durchsucht `tests` rekursiv, sodass reine Verschiebungen grundsätzlich von diesem Syntaxcheck vertragen werden.

Andere statische Tests referenzieren jedoch konkrete Repositorypfade und müssen bei Verschiebungen angepasst werden.

## Befund

Die gewünschte Zielstruktur existiert bereits. Es müssen nur Altbestände einsortiert werden.

## Ergebnis

**Klasse A/B – Konsolidierung sinnvoll und relativ risikoarm.**

Regel für flache Alt-Tests:

```text
reiner Service-/Modultest         -> tests/unit/<bereich>/
Pfad-/Quellcodevertrag            -> tests/unit/static/
mehrere echte Komponenten         -> tests/integration/
Bug-Reproduktion                  -> tests/regression/
Schema/API-Vertrag                -> tests/contract/
```

Nicht blind alle Dateien verschieben: Testart zuerst anhand des Inhalts bestimmen.

---

# 18. Punkt 15 – `tests/images`

## Prüfung

Der Ordner liegt neben `tests/fixtures`.

Die neuen Preview-Konzepte benötigen künftig verstärkt definierte Bild-Fixtures für:

- EXIF Orientation 1–8
- JPEG/PNG/WebP
- HEIC/RAW Preview
- Bounding Boxes
- Crop/Context
- Fallback

## Befund

Eine zentrale Fixture-Struktur wäre sinnvoll.

## Ergebnis

**Klasse B – nach Inventar konsolidieren.**

Empfohlenes Ziel:

```text
tests/fixtures/images/
```

Vor Verschiebung:

- alle `Path("tests/images/...`)`-Referenzen suchen;
- Build-/Testtools auf direkte Pfade prüfen;
- große/binary Fixtures katalogisieren;
- Lizenz/Provenienz der Testbilder dokumentieren.

Für Preview-Golden-Master-Fixtures ggf. weitere Unterteilung:

```text
tests/fixtures/images/orientation/
tests/fixtures/images/formats/
tests/fixtures/images/faces/
```

---

# 19. Punkt 16 – `tests/function_matrix.md`

## Prüfung

Die Datei wird in den Architecture Guidelines ausdrücklich als maßgebliche Übersicht für File-/ExifTool-Verantwortlichkeiten referenziert.

Damit ist sie derzeit **kein beliebiges Testdokument**.

## Befund

Ein Verschieben würde mindestens die Architecture Guidelines und ggf. weitere Referenzen ändern.

Eine automatische JSON/YAML-Quelle wäre langfristig denkbar, ist aber noch nicht etabliert.

## Ergebnis

**Klasse D – vorerst an Ort und Stelle lassen.**

Späterer möglicher Ausbau:

```text
strukturierte Source of Truth
    ↓
Testparameter + generiertes Markdown
```

aber nur als eigenes Vorhaben.

---

# 20. Punkt 17 – `scripts/`

## Prüfung

Bestätigt als DSM Lifecycle-/Runtime-Verzeichnis.

Gleichzeitig empfiehlt das Documentation-Core-Konzept derzeit generische Docs-Generatoren unter `scripts/`.

## Befund

Das wäre eine zukünftige Inkonsistenz.

## Ergebnis

**Klasse A – Konvention sofort festlegen:**

```text
scripts/
    ausschließlich DSM Lifecycle / paketnahe Runtime Wrapper

tools/
    Build, Development, Docs, Release, Validation, Migration
```

Für Documentation Core daher:

```text
tools/docs/collect.py
tools/docs/validate.py
tools/docs/render_dsm.py
tools/docs/render_web.py
tools/docs/build.py
```

anstatt neuer `scripts/docs_*.py`.

Bei Umsetzung des Documentation-Core-Konzepts ist dessen Strukturabschnitt entsprechend zu aktualisieren.

---

# 21. Punkt 18 – `app/`

## Prüfung

`app/main.py` ist der FastAPI Runtime-Einstiegspunkt und macht `src` importierbar.

`SynoBuildConf/install` kopiert `app` und `src` beide in das Paket.

## Befund

Die Trennung ist sinnvoll:

```text
app/ = executable/application bootstrap
src/ = implementation
```

## Ergebnis

**Klasse D – beibehalten.**

`app/` sollte bewusst klein bleiben. Neue Fachlogik gehört nicht dort hinein.

Der aktuelle `main.py` ist bereits überwiegend Bootstrap, Middleware, Router-Mount und Startup-Hook und passt damit zur vorgesehenen Rolle.

---

# 22. Punkt 19 – `docs/`

## Prüfung

`docs/` enthält inzwischen:

- Architecture Guidelines
- Status-/Runtime-Konzepte
- Worker-Konzepte
- UI-/Preview-/Review-Konzepte
- Feature-Konzepte
- Documentation-Core-Konzepte

Das Documentation-Core-Konzept plant zusätzlich:

```text
docs/core/
docs/metadata/
docs/i18n/
docs/assets/
docs/generated/
docs/templates/
```

## Befund

Hier besteht echter Strukturbedarf. Gleichzeitig dürfen bestehende Konzeptpfade nicht sofort verändert werden, weil:

- Architecture Guidelines konkrete Dokumentpfade referenzieren;
- Konzepte sich gegenseitig referenzieren;
- künftige Documentation-Core-Generatoren ihre Quellenstruktur definieren müssen.

## Ergebnis

**Klasse B – Docs strukturiert migrieren, aber erst nach Referenzinventar.**

Empfohlenes Ziel:

```text
docs/
├── core/                  # öffentliche Benutzerhilfe DE/EN
├── metadata/              # Documentation-Core Metadaten
├── i18n/                  # Documentation-Core Generator-i18n
├── assets/
├── templates/
├── generated/             # nicht manuell editieren
│
├── architecture/          # verbindliche Cross-Cutting Architektur
├── concepts/              # Design-/Entwicklungskonzepte
│   ├── documentation/
│   ├── ui/
│   ├── recognition/
│   ├── metadata/
│   └── worker/
└── development/
```

Wichtig:

`docs/core` ist **Benutzerdokumentation** und darf nicht mit internen Designkonzepten vermischt werden.

---

# 23. Punkt 20 – Dateinamenskonventionen in `docs`

## Prüfung

Aktuell parallel vorhanden:

```text
MUSIC_EXTENSION_CONCEPT.md
PHOTO_DATETIME_CONSISTENCY_CONCEPT.md
TRAY_STATUS_CONCEPT.md

preview-unification-technical-concept.md
review-ui-unification-concept.md

dm-documentation-core-concept.md
```

## Befund

Die Benennung ist inkonsistent.

Ein sofortiges Rename aller Dateien würde aber zahlreiche interne Referenzen ändern und erzeugt wenig unmittelbaren fachlichen Nutzen.

## Ergebnis

**Klasse A für neue Dokumente, Klasse C für Altbestand.**

Ab sofort:

```text
kebab-case.md
```

Interne Konzepte werden langfristig über den Ordner `docs/concepts/...` klassifiziert; Präfixe wie `dm-` sind dann nicht mehr nötig.

Altdateien nur während der geplanten Docs-Migration umbenennen und alle Referenzen im selben Commit aktualisieren.

---

# 24. Punkt 21 – vorgeschlagene Zielstruktur neu bewertet

Die erste Analyse schlug sinngemäß eine vollständige Struktur mit `src/av_imgdata/...`, `ui/features/...` und neuem `tools/` vor.

Nach Prüfung ist diese Zielstruktur zu aggressiv.

## 24.1 Was bestätigt wird

Sinnvoll bleiben:

```text
docs klar gliedern
tests konsolidieren
tools intern gliedern
imgdata.py schrittweise verkleinern
UI-Querschnittslogik aus großen Mixins extrahieren
ui/dist als Build-Artefakt behandeln
```

## 24.2 Was korrigiert wird

Nicht als kurzfristiges Ziel festlegen:

```text
src/* komplett nach src/av_imgdata/* verschieben
worker/ unter processors/ verschieben
processor_contract/ verschieben
DSM-Verzeichnisse unter package/ verschieben
UI komplett auf features/ umstellen
```

Diese Änderungen wären entweder vertragsbrechend oder bringen aktuell zu wenig Nutzen.

---

# 25. Aktualisierte Zielstruktur

Die realistische Zielstruktur lässt die etablierten Build-/Runtime-Grenzen bestehen:

```text
av_imgdata/
│
├── INFO.sh
├── Makefile
├── SynoBuildConf/
├── conf/
├── scripts/                    # DSM Lifecycle / runtime wrappers
├── var/                        # shipped defaults
│
├── app/                        # Runtime bootstrap
│   └── main.py
│
├── src/                        # Python import root bleibt zunächst bestehen
│   ├── api/
│   ├── av_imgdata/
│   │   └── db/
│   ├── handler/
│   ├── models/
│   ├── parser/
│   ├── services/
│   ├── face_detection_models/ # bis Resource-Governance geklärt
│   └── imgdata.py              # schrittweise auf Facade reduzieren
│
├── ui/
│   ├── src/
│   │   ├── components/
│   │   ├── i18n/
│   │   ├── mixins/             # schrittweise verkleinern
│   │   ├── services/
│   │   ├── styles/
│   │   ├── views/
│   │   └── adapters/           # bei Preview/Review bei Bedarf ergänzen
│   ├── images/
│   ├── texts/
│   ├── help/                   # generated, Documentation Core
│   ├── helptoc.conf            # generated
│   └── dist/                   # generated, perspektivisch nicht versioniert
│
├── processor_contract/
│   └── schemas/
│
├── processors/
│   └── native/
│
├── worker/
│   ├── src/
│   ├── include/
│   ├── jobs/
│   ├── protocol/
│   ├── config/
│   ├── packaging/
│   └── tests/
│
├── tests/
│   ├── unit/
│   │   ├── api/
│   │   ├── db/
│   │   ├── handlers/
│   │   ├── parser/
│   │   ├── scripts/
│   │   ├── services/
│   │   ├── static/
│   │   └── ui/
│   ├── integration/
│   ├── contract/
│   ├── regression/
│   ├── fixtures/
│   │   └── images/
│   └── function_matrix.md
│
├── docs/
│   ├── core/
│   ├── metadata/
│   ├── i18n/
│   ├── assets/
│   ├── templates/
│   ├── generated/
│   ├── architecture/
│   ├── concepts/
│   │   ├── documentation/
│   │   ├── ui/
│   │   ├── recognition/
│   │   ├── metadata/
│   │   └── worker/
│   └── development/
│
└── tools/
    ├── docs/                    # zukünftig Documentation Core
    ├── build/                   # optional später gruppieren
    ├── release/                 # optional später gruppieren
    ├── validation/              # optional später gruppieren
    └── bestehende Tools zunächst kompatibel lassen
```

Wichtig: Die Untergliederung von `tools/` ist **kein sofortiger Move-Auftrag**. Viele Buildskripte und `SynoBuildConf/install` referenzieren heute konkrete `tools/<name>`-Pfade. Sie sollte erst erfolgen, wenn ein entsprechender Compatibility-/Reference-Check vorliegt.

---

# 26. Konsequenzen aus anderen Konzepten

## 26.1 Documentation Core

Das Documentation-Core-Konzept verlangt neue Quell- und Generated-Bereiche unter `docs/` und generierte DSM-Hilfe unter `ui/`.

Strukturentscheidung:

- wird unterstützt;
- Generatoren gehören nach `tools/docs/`, nicht nach `scripts/`;
- `ui/help` und `ui/helptoc.conf` sind generated;
- bei `ui/texts` ist Source-/Generated-Merging explizit zu definieren.

## 26.2 Preview-Vereinheitlichung

Das Preview-Konzept verlangt gemeinsame Resolver/Adapter/Renderer.

Strukturentscheidung:

- keine neue globale UI-Feature-Hierarchie erforderlich;
- neue Preview-Schicht darf unter bestehenden `components`, `services` und optional neuem `adapters` entstehen;
- etablierte ältere Face-Match-Flows bleiben Referenz und werden erst spät migriert.

Backendseitig:

- ein späterer `preview_service.py` passt in `src/services/`;
- kein neues `src/preview/` Top-Level-Verzeichnis.

## 26.3 Review-UI-Vereinheitlichung

Gemeinsame `ReviewShell`, `ReviewSplitPane`, TargetSelector und ActionBar passen als wiederverwendbare Komponenten unter `ui/src/components/`.

Keine Notwendigkeit, dafür das gesamte UI auf `features/` umzustrukturieren.

## 26.4 External Worker

Die bestehenden Root-Bereiche `processor_contract`, `processors/native` und `worker` spiegeln die beabsichtigte Verantwortung korrekt wider.

Sie dürfen nicht aus optischen Gründen zusammengeführt werden.

## 26.5 Status-Konzept

Status/Progress ist globaler Backend-Vertrag. Eine Strukturmigration von Services oder `imgdata.py` darf keine parallelen Statusbuilder pro Feature erzeugen.

Bei Extraktion aus `imgdata.py` muss geprüft werden, ob der neue Service nur Domain-Counter liefert oder versehentlich Statusschema-Semantik übernimmt.

## 26.6 Architecture Guidelines

Mehrere zunächst denkbare Strukturänderungen widersprechen aktuell expliziten Guidelines.

Daher gilt:

> Erst Guidelines ändern, dann Struktur ändern – nicht umgekehrt.

Dies betrifft insbesondere eine komplette Abschaffung von `src/handler`, `src/services` oder eine Migration sämtlicher Module nach `src/av_imgdata`.

---

# 27. Vor jeder tatsächlichen Verschiebung: Pflichtprüfung

Für jede Datei-/Ordnerbewegung muss ein standardisierter Check erfolgen.

## 27.1 Referenzen

Repositoryweit suchen nach:

- Importpfaden
- `Path(...)`
- Shellpfaden
- Makefilepfaden
- CMakepfaden
- Dokumentationslinks
- statischen Tests
- Buildskripten
- DSM Lifecycle Scripts

## 27.2 Build

Je nach Bereich:

```text
Python      syntax + focused unit tests
UI          pnpm/npm build + lint + static tests
DSM         package build
Native      focused native build/smoke
Worker      relevant target build/tests
Docs        documentation validation/render
```

## 27.3 Runtime

Bei paketnahen Pfaden zusätzlich prüfen:

- installierter Pfad im SPK
- `SYNOPKG_PKGDEST`
- `SYNOPKG_PKGVAR`
- `PYTHONPATH`
- `index.cgi`
- Start/Stop
- DB bootstrap
- API startup

## 27.4 Teststruktur

Bei Testverschiebungen:

- pytest discovery
- relative Fixture-Pfade
- `Path(__file__)`
- statische Repositorypfade
- CI Selektoren

## 27.5 Dokumentation

Bei Docs-Verschiebungen:

- interne Markdownlinks
- Guidelines-Referenzen
- Documentation-Core Navigation
- zukünftige Help-/Web-Renderer

---

# 28. Automatisierter Struktur-Contract

Die Bereinigung sollte nicht allein durch Konvention abgesichert werden.

`tools/check_syntax_and_structure.py` ist bereits der natürliche Ort für einige Repository-Regeln.

Langfristig sinnvoll sind zusätzliche Checks, beispielsweise:

```text
FAIL: generated file tracked as source: ui/help/...
FAIL: new top-level Python package under src/: foo
FAIL: development tool added under DSM scripts/: scripts/docs_build.py
FAIL: flat unit test added to tests/: tests/test_new_service.py
FAIL: internal concept added to docs/core/
```

Diese Regeln sollten erst aktiviert werden, wenn die jeweilige Migration abgeschlossen ist, damit bestehender Altbestand nicht sofort zum Buildfehler wird.

Mögliches Stufenmodell:

```text
Phase 1: Warnung für neue Verstöße
Phase 2: Altbestand migrieren
Phase 3: Fehler bei Verstoß
```

---

# 29. Migrationsmatrix

| Bereich | Befund | Priorität | Risiko | Aktion |
|---|---|---:|---:|---|
| Root | grundsätzlich sinnvoll | niedrig | hoch bei Move | beibehalten |
| `src` Gesamtpackage | inkonsistent, aber Runtime-Vertrag | niedrig | sehr hoch | nicht global migrieren |
| `imgdata.py` | echter Monolith | hoch | mittel/hoch | schrittweise Service-Extraktion |
| `api/handler/services/models/parser` | Guidelines-konform | niedrig | mittel | beibehalten |
| Face model asset | semantisch unsauber, technisch stabil | niedrig | mittel | später mit Asset-Governance |
| UI Grundstruktur | ausreichend | niedrig | mittel | beibehalten |
| UI Mixins | echte Logikschuld | hoch | mittel | mit Preview/Review abbauen |
| `ui/dist` | Build-Artefakt | mittel | mittel | reproduzierbaren Build beweisen, dann untracken |
| `ui` DSM + Vue | sinnvoll gekoppelt | niedrig | hoch | beibehalten |
| Worker | sauber | niedrig | hoch | beibehalten |
| Processor vs Worker | fachlich korrekt | niedrig | hoch | beibehalten |
| Processor Contract | sinnvoll separat | niedrig | hoch | beibehalten |
| Tests | teilweise bereits sauber | mittel | niedrig/mittel | flache Alt-Tests einsortieren |
| Test Images | konsolidierbar | mittel | niedrig/mittel | nach Fixtures nach Referenzcheck |
| Function Matrix | etablierter Architekturvertrag | niedrig | mittel | vorerst belassen |
| `scripts` | DSM-spezifisch | hoch als Konvention | niedrig | keine Devtools dort hinzufügen |
| `app` | sauberer Bootstrap | niedrig | hoch | beibehalten |
| Docs | echter Strukturbedarf | hoch | mittel | kontrollierte Migration |
| Docs-Namen | inkonsistent | mittel | niedrig/mittel | neue kebab-case; Altbestand mit Docs-Migration |
| `tools` | bereits vorhanden | mittel | mittel | nicht neu einführen; später optional gruppieren |

---

# 30. Empfohlene konkrete Reihenfolge

## Phase 1 – Regeln festschreiben, keine riskanten Moves

1. Dieses Strukturkonzept als Referenz verwenden.
2. Neue Dateien nur noch gemäß Zielregeln einordnen.
3. Keine neuen generischen Development-Skripte unter `scripts/`.
4. Neue interne Docs in kebab-case.
5. Keine neue Top-Level-Kategorie unter `src/` ohne Architecture-Entscheidung.

## Phase 2 – Documentation-Struktur

Gemeinsam mit Umsetzung des Documentation Core:

1. `docs/core`, `metadata`, `i18n`, `assets`, `templates` anlegen.
2. Documentation Tools unter `tools/docs` anlegen.
3. interne Konzepte nach `docs/concepts/...` migrieren.
4. alle internen Referenzen automatisiert suchen und aktualisieren.
5. erst danach Alt-Konzeptdateien umbenennen.

## Phase 3 – Tests

1. flache `tests/test_*.py` klassifizieren.
2. jeweils einzeln nach `tests/unit/...`, `integration`, `regression` oder `contract` verschieben.
3. Fixture-Pfade prüfen.
4. `tests/images` nach `tests/fixtures/images` migrieren, wenn alle Referenzen bekannt sind.
5. Strukturcheck gegen neue flache Unit-Tests ergänzen.

## Phase 4 – Preview/Review als UI-Strukturpilot

1. gemeinsame Preview-Komponenten/Services/Adapter einführen.
2. älteres Preview-Verhalten mit Golden-Master-Tests schützen.
3. neuere Flows migrieren.
4. erst danach veraltete Mixin-Teile entfernen.
5. daraus UI-Konvention für weitere Features ableiten.

## Phase 5 – Backend-Monolith

1. `imgdata.py` nach Verantwortlichkeiten inventarisieren.
2. bestehende Services bevorzugen.
3. neue fokussierte Services nur unter `src/services`.
4. öffentliche `ImgDataService`-Methoden zunächst delegieren lassen.
5. API-/Status-/Persistence-Verträge pro Extraktion testen.

## Phase 6 – Generated Artefacts

1. clean-checkout UI-Build automatisieren.
2. DSM-Paket aus clean checkout bauen.
3. Paketinhalt vergleichen.
4. erst dann `ui/dist` aus Git entfernen und `/ui/dist/` ignorieren.
5. gleiche Source-vs-Generated-Regeln für DSM Help etablieren.

## Phase 7 – Python-Package-Struktur neu bewerten

Erst wenn `imgdata.py` deutlich kleiner und Servicegrenzen stabil sind, erneut entscheiden, ob eine Migration nach:

```text
src/av_imgdata/{api,services,...}
```

überhaupt noch einen ausreichenden Nutzen bringt.

Bis dahin ist sie ausdrücklich **kein Ziel der Strukturbereinigung**.

---

# 31. Tests für die Strukturmigration

## 31.1 Statische Strukturtests

- keine neuen Developmenttools unter `scripts/`
- keine neuen flachen Unit-Tests
- keine handgepflegten Dateien in Generated-Help-Verzeichnissen
- keine neuen unbekannten `src`-Top-Level-Packages
- Docs Core enthält keine internen Designkonzepte

## 31.2 Python

Nach Backend-/Testverschiebungen mindestens:

```text
python syntax/structure check
focused pytest
DB bootstrap test
API import/startup test
```

Bei Importpfadänderungen zusätzlich vollständiger Testlauf.

## 31.3 UI

Nach Preview-/UI-Strukturänderung:

- lint
- bundle build
- Preview Golden Masters
- Preview fallback tests
- Review contract tests
- existing older face-match regression tests

## 31.4 DSM Package

Nach paketrelevanten Pfadänderungen:

```text
clean package build
SPK content check
install/upgrade test
start-stop-status
API ping
UI load
```

## 31.5 Worker/Native

Nur wenn dort Pfade geändert werden:

- native build/smoke/functional
- worker target builds
- processor contract tests
- package worker archive validation

---

# 32. Akzeptanzkriterien

Die Strukturbereinigung gilt als erfolgreich, wenn:

1. DSM-konforme Rootpfade stabil bleiben.
2. neue Dateien eindeutig einem Verantwortungsbereich zugeordnet werden können.
3. `scripts/` nicht zum allgemeinen Tool-Sammelordner wird.
4. Documentation Core und interne Konzepte klar getrennt sind.
5. Test-Neuzugänge nicht mehr flach unter `tests/` landen.
6. Preview-/Review-Vereinheitlichung ohne parallele neue UI-Strukturwelt erfolgt.
7. `imgdata.py` schrittweise kleiner wird, ohne API-/Statusverträge zu brechen.
8. Worker, Processor Contract und Native Processors ihre bestehenden Grenzen behalten.
9. Generated Artefacts klar als solche markiert und reproduzierbar sind.
10. jede tatsächliche Pfadverschiebung durch automatisierte Tests abgesichert ist.

---

# 33. Zusammenfassung

Die detaillierte Prüfung verändert die ursprüngliche Empfehlung wesentlich.

Das Projekt braucht **keinen großen Repository-Rewrite**. Mehrere scheinbare Inkonsistenzen sind etablierte DSM-/Runtime-/Architecture-Verträge.

Die tatsächlichen Strukturbaustellen sind:

```text
1. docs ordnen
2. flache Alt-Tests konsolidieren
3. scripts vs tools verbindlich trennen
4. ui/dist als Generated Artifact behandeln
5. UI-Mixins über Preview/Review schrittweise entlasten
6. imgdata.py serviceweise verkleinern
```

Dagegen sollten zunächst stabil bleiben:

```text
DSM Root Layout
src als Python Import Root
api / handler / services / models / parser
app als Bootstrap
worker
processors/native
processor_contract
```

Das Leitprinzip lautet daher:

> **Struktur durch klarere Verantwortlichkeiten bereinigen, nicht durch möglichst viele Datei-Verschiebungen.**

Jede Migration soll klein, testbar, reversibel und kompatibel mit den bestehenden Architektur- und Fachkonzepten erfolgen.
