# Strukturausrichtung für zukünftige Funktionen

## 1. Zweck

Dieses Dokument richtet die bestehenden Konzepte für noch nicht oder erst teilweise implementierte Funktionen an `docs/structure-cleanup-concept.md` aus.

Es ersetzt keine fachlichen Konzepte. Es konkretisiert ausschließlich deren **strukturelle Umsetzung** im Repository.

Damit gilt künftig:

> Fachliche Konzepte definieren Verhalten und Verantwortlichkeiten. Die konkrete Ablage neuer Dateien und Module richtet sich zusätzlich nach der geprüften Projektstruktur und darf keine neue Parallelarchitektur erzeugen.

Bei Widersprüchen zwischen einem älteren Konzept und diesem Dokument gilt für **Pfad-, Ordner- und Modulfragen** diese Reihenfolge:

1. `docs/architecture-and-development-guidelines.md`
2. `docs/structure-cleanup-concept.md`
3. dieses Dokument
4. fachliches Einzelkonzept

Fachliche Regeln aus den Einzelkonzepten bleiben davon unberührt.

---

## 2. Verbindliche Grundregeln für neue Funktionen

### 2.1 Kein neues Python-Root-Package ohne Architekturentscheidung

`src/` bleibt aktuell der Python-Import-Root.

Neue Backend-Funktionen werden daher zunächst in den bestehenden Kategorien abgelegt:

```text
src/api/       Request-/Route-Schicht
src/handler/   Zugriff auf externe/remote Systeme
src/services/  Fachlogik, Orchestrierung, technische Services
src/models/    Datencontainer / Domänenmodelle
src/parser/    Format-/Metadatenparser
src/av_imgdata/db/  persistente Repository-/DB-Schicht
```

Nicht ohne gesondertes Packaging-/Import-Konzept neu anlegen:

```text
src/music/
src/preview/
src/recognition/
src/checks/
src/workflows/
```

Ein fachlicher Bereich darf mehrere Dateien besitzen, soll aber zunächst innerhalb der vorhandenen Layer strukturiert werden.

Beispiel:

```text
src/services/music_ratings_service.py
src/handler/audio_station_handler.py
src/models/music_rating.py
src/parser/music_rating_parser.py
```

statt:

```text
src/music/...
```

### 2.2 `imgdata.py` nicht weiter vergrößern

Neue fachliche Logik soll grundsätzlich nicht direkt in `src/imgdata.py` aufgebaut werden.

Wenn eine bestehende öffentliche Methode von `ImgDataService` benötigt wird, gilt:

```text
bestehende API
    ↓
ImgDataService-Methode bleibt kompatibel
    ↓ delegiert
neuer fokussierter Service
```

Dadurch kann `imgdata.py` schrittweise zur Facade werden, ohne bestehende Aufrufer zu brechen.

### 2.3 Keine neuen allgemeinen Root-Ordner

Neue Funktionen dürfen nicht für ihren eigenen Bereich neue Root-Verzeichnisse einführen.

Insbesondere bleiben bestehen:

```text
processors/
processor_contract/
worker/
tools/
docs/
tests/
ui/
src/
```

Neue Root-Ordner benötigen eine eigene Architekturentscheidung.

### 2.4 `scripts/` bleibt DSM Lifecycle

Neue Build-, Generator-, Analyse- oder Entwicklungswerkzeuge gehören nach:

```text
tools/
```

und bei wachsendem Umfang beispielsweise nach:

```text
tools/docs/
tools/build/
tools/release/
tools/dev/
```

Nicht nach:

```text
scripts/
```

`scripts/` bleibt für DSM Lifecycle und paketnahe Runtime Wrapper reserviert.

### 2.5 Tests folgen der bereits vorhandenen Struktur

Neue Tests sollen sofort eingeordnet werden:

```text
tests/unit/api/
tests/unit/db/
tests/unit/handlers/
tests/unit/parser/
tests/unit/services/
tests/unit/static/
tests/unit/ui/
tests/integration/
tests/contract/
tests/regression/
tests/fixtures/
```

Keine neuen flachen `tests/test_*.py`, sofern kein konkreter Grund besteht.

### 2.6 Bestehende Build-/Runtimepfade nicht beiläufig ändern

Eine neue Funktion darf nicht nebenbei folgende Grundverträge ändern:

- `src` als Python-Import-Root
- `app/main.py` als Backend-Einstieg
- `processor_contract/` als sprachneutraler Prozessorvertrag
- `processors/native/` als lokale/native Implementierungen
- `worker/` als externe Runtime
- `ui/` als DSM-UI-Verzeichnis
- `var/config.json` als ausgelieferte Default-Konfiguration

Wenn eine Funktion eine solche Änderung benötigt, muss zuerst das Struktur-/Architekturkonzept angepasst werden.

---

# 3. Documentation Core / GitHub Pages / DSM-Hilfe

Betroffene Konzepte:

- `dm-github-pages-concept.md`
- `dm-documentation-dsm-help-concept.md`
- `dm-documentation-core-concept.md`

## 3.1 Korrektur der Werkzeugpfade

Die dort teilweise vorgeschlagenen Generatoren unter:

```text
scripts/docs_collect.py
scripts/docs_validate.py
scripts/docs_render_dsm.py
scripts/docs_render_web.py
scripts/docs_build.py
```

werden strukturell ersetzt durch:

```text
tools/docs/
├── collect.py
├── validate.py
├── render_dsm.py
├── render_web.py
└── build.py
```

oder äquivalente klar benannte Dateien unter `tools/docs/`.

Aufrufe sollen entsprechend erfolgen, z. B.:

```bash
python3 tools/docs/build.py
python3 tools/docs/build.py --target dsm
python3 tools/docs/build.py --target web
```

## 3.2 Quellstruktur

Das neuere Documentation-Core-Konzept mit:

```text
docs/core/
docs/metadata/
docs/i18n/
docs/assets/
docs/templates/
docs/generated/
```

ist gegenüber älteren Vorschlägen wie:

```text
docs-site/
docs-src/
```

zu bevorzugen.

Damit wird kein zusätzlicher Dokumentations-Root eingeführt.

## 3.3 Generierte DSM-Ausgaben

Weiterhin korrekt sind:

```text
ui/helptoc.conf
ui/help/ger/
ui/help/enu/
ui/texts/ger/strings
ui/texts/enu/strings
```

Diese Dateien sind Build-Ausgaben und nicht die redaktionelle Quelle.

## 3.4 Konzeptdokumente

Langfristig sollen interne Design-/Konzeptdokumente nach `docs/concepts/` gegliedert werden. Dieser Umzug erfolgt jedoch erst nach Prüfung aller internen Links und Documentation-Core-Generatoren.

Bis dahin bleiben bestehende Dateien an ihrem aktuellen Ort.

---

# 4. Vereinheitlichte Previews

Betroffene Konzepte:

- `preview-unification-technical-concept.md`
- `preview-unification-source-inventory.md`
- `preview-unification-reference-baseline.md`

## 4.1 Backend

Der vorgeschlagene Backend-Service bleibt strukturell passend:

```text
src/services/preview_service.py
```

Er wird jedoch erst eingeführt, wenn reale Backend-Verantwortung aus `/api/file_image`, `ImageDecodeService` oder bestehender Preview-Aufbereitung extrahiert werden muss.

Es wird **kein** neues `src/preview/` angelegt.

Der bestehende `/api/file_image`-Pfad bleibt zunächst maßgeblich. Ein neuer `/api/preview`-Endpunkt darf erst entstehen, wenn er einen konkreten zusätzlichen Vertrag benötigt und nicht lediglich dieselbe Funktion parallel abbildet.

## 4.2 Frontend

Neue gemeinsame Komponenten gehören unter einen klaren gemeinsamen Komponentenbereich:

```text
ui/src/components/preview/
├── MediaPreview.vue
├── PreviewOverlay.vue        # nur falls benötigt
└── ...
```

Technische Logik gehört nach:

```text
ui/src/services/preview-resolver.js
ui/src/services/preview-geometry.js
```

oder vergleichbar konsistent benannte Service-Dateien.

Adapter dürfen eingeführt werden, wenn mehrere Prozesse tatsächlich unterschiedliche Datenformen besitzen:

```text
ui/src/adapters/preview/
```

Ein neuer Top-Level-Bereich `ui/src/features/` wird für die Preview-Migration **nicht vorausgesetzt**.

## 4.3 Referenzverhalten

Die Strukturänderung darf die Reifegradregel nicht verändern:

- klassische Face-Match-Previews bleiben Referenz
- neue gemeinsame Komponenten werden gegen diese Regressionstests gebaut
- neuere Recognition-/Findings-Previews werden zuerst angeglichen
- die Legacy-Funktion wird erst anschließend intern umgestellt

Damit dient die Preview-Vereinheitlichung zugleich als Pilot für eine bessere UI-Struktur ohne großen UI-Ordnerumbau.

---

# 5. Review-UI-Vereinheitlichung

Betroffen:

- `review-ui-unification-concept.md`

## 5.1 Komponentenablage

Die gemeinsamen Bausteine sollen strukturell unter:

```text
ui/src/components/review/
├── ReviewShell.vue
├── ReviewSplitPane.vue
├── ReviewTargetSelector.vue
└── ReviewActionBar.vue
```

liegen.

Preview-Darstellung wird dabei **nicht** erneut in `review/` implementiert, sondern nutzt die gemeinsame Preview-Schicht unter `components/preview/`.

## 5.2 Adapter

Prozessadapter können unter:

```text
ui/src/adapters/review/
```

liegen, wenn mehrere Adapter entstehen.

Bei nur einer oder zwei kleinen Abbildungen ist ein eigener neuer Ordner nicht zwingend; dann kann die Abbildung zunächst nahe beim vorhandenen Mixin/Service bleiben.

## 5.3 Bestehende Mixins

Die Vereinheitlichung ist ausdrücklich eine **inkrementelle Extraktion**.

Nicht vorgesehen ist ein paralleler Komplettumbau aller Mixins in einen neuen State-Framework- oder `features/`-Baum.

Regel:

```text
bestehender Mixin
    ↓ delegiert schrittweise
shared component / service / adapter
```

Erst wenn mehrere Mixins deutlich kleiner geworden sind, wird eine weitere strukturelle Konsolidierung geprüft.

## 5.4 Statusvertrag

Das ältere Review-Beispiel verwendet teilweise eigenständige Operationsbezeichnungen. Für die Umsetzung gilt stattdessen strikt `status-concept-integrated.md`:

```text
file_analysis
checks
face_match
cleanup
```

Neue Review-Funktionen erzeugen keine neue globale Operation, nur weil sie neue Komponenten besitzen.

---

# 6. Recognition-Profilpflege

Betroffen:

- `dm-recognition-profile-maintenance.md`

## 6.1 Backend-Ablage

Neue Profilpflege-Logik soll in fokussierten Services entstehen, z. B.:

```text
src/services/recognition_profile_maintenance_service.py
```

bei Bedarf ergänzt durch bestehende Bereiche:

```text
src/models/
src/av_imgdata/db/repositories/
```

Es wird kein neues:

```text
src/recognition/
```

angelegt.

## 6.2 Persistenz

Dirty-State, Revisionen, Kandidatenstatus und andere dauerhafte Zustände sollen über die bestehende SQLite-/Repository-Schicht geführt werden.

Keine neue parallele JSON-Persistenz für Profilpflege, sofern kein nachgewiesener Grund besteht.

## 6.3 Worker

Die im Konzept vorgesehene Worker-Nutzung bleibt vollständig kompatibel mit der Struktur:

```text
DSM workflow/service
    ↓
bestehender detector/embedder/processor seam
    ↓
shared worker services
    ↓
processor_contract
```

Keine Recognition-spezifische Worker-Unterstruktur oder eigene Queue.

## 6.4 Prozessstatus

`profile_maintenance` wird nicht automatisch zu einer neuen globalen Operation.

Vor einer langlaufenden Umsetzung muss entschieden werden, ob der Ablauf:

- als Aktion einer bestehenden Operation modelliert wird oder
- tatsächlich eine neue globale Operation benötigt.

Im zweiten Fall müssen zuerst `status-concept-integrated.md` und die Architecture Guidelines angepasst werden.

---

# 7. Photo Capture Datetime Consistency

Betroffen:

- `PHOTO_DATETIME_CONSISTENCY_CONCEPT.md`

Dieses Konzept ist bereits weitgehend mit der geltenden Architektur abgestimmt. Die Architecture Guidelines legen ausdrücklich fest, dass die Funktion unter `checks` modelliert wird.

## 7.1 Backend

Empfohlene Ablage:

```text
src/services/photo_datetime_analysis_service.py
src/services/photo_datetime_comparison_service.py   # nur wenn Trennung nötig
src/parser/photo_datetime_*.py                      # formatspezifische Parser
src/models/photo_datetime.py                        # bei echtem gemeinsamem Modellbedarf
```

Synology-Photos-Zugriff bleibt im vorhandenen Handler-/Session-Modell und wird nicht in einen neuen Datetime-Root verschoben.

## 7.2 API und Status

Die Funktion bleibt:

```text
operation = checks
```

mit geeigneter `action`, `scan` und `findings` Semantik.

Kein neues:

```text
operation = photo_datetime
```

ohne vorherige Änderung des Statuskonzepts.

## 7.3 Persistenz

Findings sollen die vorhandene Checks-/SQLite-Infrastruktur wiederverwenden.

Keine eigene Findings-Datenbank oder parallele Statusdatei.

## 7.4 UI

Neue UI-Teile sollen bestehende Check-View-Strukturen und die geplanten Review-Komponenten wiederverwenden. Ein eigener neuer globaler UI-Architekturbereich ist nicht erforderlich.

---

# 8. Musik-Erweiterung

Betroffen:

- `MUSIC_EXTENSION_CONCEPT.md`

Hier besteht der deutlichste strukturelle Anpassungsbedarf.

## 8.1 Der vorgeschlagene `src/music/`-Baum gilt nicht mehr als Ziel

Der ältere Vorschlag:

```text
src/music/
├── audio_station_capabilities.py
├── audio_station_client.py
├── audio_station_db.py
├── ratings_import.py
├── ratings_sources.py
├── ratings_mapping.py
├── music_file_index.py
└── models.py
```

wird für die erste Umsetzung strukturell ersetzt.

Empfohlene Einordnung:

```text
src/handler/audio_station_handler.py
src/services/music_capabilities_service.py
src/services/music_ratings_service.py
src/services/music_rating_mapping_service.py     # nur bei ausreichendem Umfang
src/parser/music_rating_parser.py                 # Datei-/Importformatparser
src/models/music_rating.py                        # wenn gemeinsames Datenmodell nötig
```

API-Routen bleiben in `src/api/`.

Damit nutzt Musik dieselben Layer wie der Rest des Projekts.

## 8.2 Audio Station als Remote-System

Audio-Station-WebAPI-Zugriff gehört fachlich nach `handler/`, da die Architecture Guidelines Remote-Systemzugriff dort verorten.

Ein eventueller direkter Datenbankzugriff ist keine normale Alternative, sondern benötigt vor Implementierung eine gesonderte Risiko-/Schemaanalyse.

## 8.3 Kein neuer globaler Langläufer ohne Statusentscheidung

Das Musik-Konzept schlägt eigene Start-/Status-/Result-Endpunkte vor. Daraus darf nicht automatisch eine neue globale Operation `music` oder `music_ratings` entstehen.

Vor Implementierung eines langlaufenden Musikimports gibt es zwei zulässige Wege:

1. bounded/synchrone Analyse ohne globalen Long-Running-Status, sofern realistisch;
2. bewusste Erweiterung des integrierten Statuskonzepts um eine neue globale Operation.

Ein verstecktes paralleles Progress-Modell nur für Musik ist nicht zulässig.

## 8.4 UI

`MusicRatingsView.vue` kann als View unter:

```text
ui/src/views/
```

entstehen.

Wiederverwendbare Musik-Komponenten können zunächst unter:

```text
ui/src/components/music/
```

liegen, falls mehr als eine kleine View entsteht.

Die Funktion rechtfertigt noch keinen allgemeinen Umbau auf `ui/src/features/`.

## 8.5 Tests

Neue Tests:

```text
tests/unit/handlers/       Audio-Station-Zugriff
tests/unit/services/       Rating-Mapping/Analyse
tests/unit/parser/         CSV/JSON/Tag-Parsing
tests/unit/api/            Routen/Validierung
tests/unit/ui/             View-/State-Verhalten
tests/integration/         nur für echte Audio-Station-Integration
```

---

# 9. DSM Tray Status

Betroffen:

- `TRAY_STATUS_CONCEPT.md`

## 9.1 Besonderheit

Der Tray ist keine normale Vue-Funktion, sondern eine DSM-Desktop-/Tray-Integration. Daher ist ein kleiner eigener UI-Unterbereich sinnvoll.

Der vorgeschlagene Pfad:

```text
ui/src/tray/
```

ist zulässig, **wenn** der UI-Build einen getrennten Entry Point benötigt.

Vor dem Anlegen muss geprüft werden:

- wie `webpack.config.js` zusätzliche Entry Points erzeugt;
- wie Synology `Makefile.js.inc` die erzeugten Bundles installiert;
- ob `app.config` ein separates `jsID`/Bundle benötigt;
- ob der bestehende Hauptbundle-Entry technisch wiederverwendet werden kann.

Damit ist `ui/src/tray/` eine begründete technische Ausnahme, kein allgemeines Feature-Ordnungsmuster.

## 9.2 Backend

Der Tray darf kein eigenes Statussystem besitzen.

Ein `/api/tray_status`-Endpunkt darf lediglich eine kompakte Projektion der bestehenden zentralen Statusdaten liefern.

Die Priorisierung aktiver Operationen gehört backendseitig in den vorhandenen Status-/Servicebereich.

## 9.3 Tests

Neben Unit-/Static-Tests ist hier ein realer DSM-Integrationstest zwingend, weil `autoLaunchType: tray` für Drittanbieterpakete nicht als stabiler öffentlicher Vertrag belegt ist.

---

# 10. External Worker, Processor Contract und Qt Worker GUI

Betroffene Konzepte:

- `optional-worker-concept.md`
- `external-worker-pre-pipeline-concept.md`
- `external-worker-gui-coverage.md`
- `external-worker-platform-contract.md`
- `qt6-worker-gui-lgpl-concept.md`
- `face-model-governance.md`

## 10.1 Kein struktureller Umbau erforderlich

Diese Konzepte entsprechen bereits der geprüften Zieltrennung:

```text
processor_contract/   neutraler Contract
processors/native/    native Compute-Implementierungen
worker/               externe Runtime
src/services/         DSM-seitige Adapter/Dispatch/Provisioning
tools/                Build-/Sync-/Packaging-Werkzeuge
```

Diese Struktur bleibt bestehen.

## 10.2 Zukünftiger Pipeline-Service

Der geplante zentrale Pipeline-Service soll DSM-seitig als fokussierter Service entstehen, z. B.:

```text
src/services/processor_pipeline_service.py
```

und nicht als neuer Root:

```text
pipeline/
src/pipeline/
```

Persistente Pipeline-Daten gehören in die bestehende DB-/Repository-Schicht.

## 10.3 Worker GUI

Die Qt-GUI gehört weiterhin vollständig zum `worker/`-Bereich bzw. dessen Build-/Packaging-Struktur. Sie darf keine zweite Worker-Protokoll- oder Queue-Implementierung neben der vorhandenen Runtime aufbauen.

---

# 11. Neue Konzepte ab jetzt

Neue Konzepte für zukünftige Funktionen sollen einen kurzen Abschnitt **„Strukturelle Einordnung“** enthalten.

Minimal zu beantworten:

1. Welche bestehenden Backend-Layer werden genutzt?
2. Welche neuen Dateien sind voraussichtlich nötig?
3. Wird ein neuer Ordner benötigt? Wenn ja, warum reicht kein bestehender?
4. Welche vorhandenen Services/Komponenten werden wiederverwendet?
5. Welche globale Statusoperation wird genutzt?
6. Welche Persistenz wird genutzt?
7. Ist External Worker relevant und über welchen bestehenden Contract-Seam?
8. Wo liegen Unit-, Contract- und Integrationstests?
9. Entstehen generierte Dateien und wo liegt ihre Quelle?
10. Welche bestehenden Build-/Runtimepfade dürfen nicht verändert werden?

Beispiel:

```text
## Strukturelle Einordnung

Backend:
- src/services/example_service.py
- src/handler/example_remote_handler.py

UI:
- ui/src/views/ExampleView.vue
- ui/src/components/example/

Status:
- operation=checks, action=example_check

Persistenz:
- existing PersistedFindingsRepository

Tests:
- tests/unit/services/
- tests/unit/ui/
- tests/integration/
```

Dadurch wird bereits beim Konzept verhindert, dass ein neues Feature unbeabsichtigt eine neue Parallelarchitektur definiert.

---

# 12. Struktur-Review als Implementierungs-Gate

Vor Beginn einer größeren neuen Funktion soll eine kurze Prüfung erfolgen:

```text
Konzept
   ↓
Strukturelle Einordnung prüfen
   ↓
Pfad-/Import-/Status-/Persistenzvertrag prüfen
   ↓
Tests festlegen
   ↓
Implementierung
```

Ein Review sollte insbesondere blockieren, wenn das Konzept ohne vorherige Architekturänderung eines der folgenden Dinge vorsieht:

```text
neues src-Root-Package
neue globale Statusoperation
neue Persistenz neben SQLite/RuntimeState
neue Worker-Queue
neue Processor-Contract-Struktur
neuer allgemeiner Root-Ordner
Build-Tools unter scripts/
kompletter UI-Parallelbaum
```

---

# 13. Zusammenfassende Ausrichtungsmatrix

| Konzept | bisherige strukturelle Annahme | gültige Ausrichtung |
|---|---|---|
| Documentation Core | Generatoren teilweise unter `scripts/` | `tools/docs/` |
| GitHub Pages | eigener `docs-site/`-Baum | gemeinsame `docs/core`-Architektur |
| DSM Help | eigener `docs-src/`-Baum möglich | gemeinsame `docs/core`-Architektur |
| Preview | neue gemeinsame Schicht | `components/preview`, `services`, optional `adapters/preview` |
| Review | generische Komponenten | `components/review`, Preview nicht duplizieren |
| Recognition Profile Maintenance | fachlicher Maintenance-Prozess | `src/services`, DB-Repositories, bestehende Worker-Seams |
| Photo Datetime | eigener Check | bestehende `checks`-Operation und bestehende Layer |
| Musik | `src/music/` | bestehende `handler/services/parser/models/api`-Layer |
| Tray | eigener kleiner DSM-JS-Entry | `ui/src/tray` nur nach Buildprüfung; zentraler Status bleibt Quelle |
| External Worker | getrennte Worker-/Processor-Struktur | unverändert beibehalten |
| Central Pipeline | späterer zentraler Orchestrator | `src/services` + bestehende DB, kein neuer Root |

---

# 14. Entscheidung

Die Strukturbereinigung führt **nicht** dazu, dass zukünftige Funktionen in einen komplett neuen Repository-Baum gezwungen werden.

Stattdessen gilt:

```text
bestehende stabile Struktur
        +
kleine klar benannte neue Services/Komponenten
        +
keine neuen Parallelarchitekturen
        +
Migration bestehender Altstrukturen nur opportunistisch
```

Die neuen Preview-/Review-Komponenten und der Documentation Core dienen als erste Referenzprojekte dafür, wie neue Funktionalität sauber ergänzt werden kann, ohne gleichzeitig den gesamten Paket-, Import- oder UI-Aufbau umzuschreiben.
