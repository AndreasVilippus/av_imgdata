# DSM-Hilfe: Abgrenzung von Grundlagen und Status

## Zweck

Dieses Dokument präzisiert das bestehende Hilfepunkte-Inventar `docs/dsm-help-topic-inventory.md` und ist bei widersprüchlicher Benennung maßgeblich.

Die Präzisierung betrifft zwei Punkte:

1. Der bisherige Sammelbegriff **Einführung** wird nicht als eigener fachlicher Hilfebereich verwendet.
2. **Status** bezeichnet ausschließlich die tatsächlich vorhandene Status-Ansicht von ImgData und ist kein Sammelbereich für Laufzustände anderer Funktionen.

---

## 1. Grundlagen statt Einführung

Die bisher unter „Einführung“ vorgesehenen Inhalte bleiben sinnvoll:

- Voraussetzungen
- Installation und Aktualisierung
- erster Start
- Navigation und Arbeitsbereiche
- Datensicherheit und Arbeitsweise

Die Bezeichnung „Einführung“ ist jedoch missverständlich, weil die Indexseite selbst bereits die kurze Einführung in ImgData übernimmt.

Daher gilt künftig:

```text
index
= Startseite
= kurze Einführung
= Übersicht der Hilfebereiche
```

und für die weiterführenden allgemeinen Themen:

```text
Grundlagen / Erste Schritte
├── Voraussetzungen
├── Installation und Aktualisierung
├── Erster Start
├── Navigation und Arbeitsbereiche
└── Datensicherheit und Arbeitsweise
```

Die endgültige sichtbare Bezeichnung soll bevorzugt **Grundlagen** lauten. „Erste Schritte“ kann als Untertitel oder Website-Bezeichnung verwendet werden, wenn dies redaktionell besser passt.

Eine zusätzliche Seite `overview` ist nicht erforderlich, solange die Indexseite diese Aufgabe erfüllt.

### Dokument-IDs

Beibehalten bzw. vorgesehen:

- `index`
- `requirements`
- `installation`
- `first-start`
- `navigation`
- `data-safety`

Der bisher vorgesehene Punkt `overview` entfällt als eigenständige Hilfeseite.

---

## 2. Status ist die Status-Ansicht

Der Hilfebereich **Status** bildet die in der Anwendung vorhandene Ansicht **Status** ab.

Er beschreibt nur Informationen, die dort tatsächlich dargestellt werden, beispielsweise:

- Paket-/Anwendungszustand
- Datenbankzustand und zugehörige Basisinformationen
- allgemeine Komponenteninformationen, sofern sie Bestandteil dieser Ansicht sind
- weitere statische oder zusammenfassende Angaben der Status-Ansicht

Entscheidend ist:

> Der Hilfebereich Status wird aus der sichtbaren Status-Ansicht abgeleitet und nicht aus allen im Backend vorhandenen Statusinformationen.

---

## 3. Was ausdrücklich nicht unter Status gehört

Nicht unter dem allgemeinen Hilfebereich Status dokumentiert werden:

- Scan-Fortschritt
- laufende Checks
- Face-Matching-Fortschritt
- Cleanup-Fortschritt
- Recognition-Läufe
- Findings-Review-Zustände
- Resume-Zustände einzelner Operationen
- Worker-Jobstatus
- Worker-Registrierungsstatus
- Worker-Fähigkeiten und Worker-Bereitschaft
- Download-/Bundle-Status externer Worker
- Status einzelner externer Bibliotheken oder Prozessoren, soweit diese in deren eigener Ansicht behandelt werden

Diese Informationen bleiben bei dem Bereich, zu dem sie fachlich gehören.

Beispiele:

```text
Face Matching
└── laufender Suchvorgang, Fortschritt, Fortsetzen

Checks
└── Scanstatus, Findings-Verarbeitung, Fortsetzen

Cleanup
└── Bereinigungs-/Recognition-Lauf und Fortschritt

External Worker
└── Registrierung, Worker-Status, Fähigkeiten, Erreichbarkeit

Externe Bibliotheken
└── Installations-/Verfügbarkeitsstatus von ExifTool, InsightFace, libvips usw.
```

---

## 4. Korrigierter Status-Hilfebaum

Der bisher vorgesehene Baum

```text
Status
├── Statusübersicht
├── Laufende Vorgänge und Fortschritt
├── Fortsetzen unterbrochener Vorgänge
└── Komponentenbereitschaft
```

wird nicht weiterverwendet.

Vorläufig gilt stattdessen:

```text
Status
└── Status-Ansicht
```

Ob später weitere Unterseiten sinnvoll sind, wird erst anhand des tatsächlichen Inhalts von `StatusView.vue` entschieden. Eine Untergliederung darf nicht allein aus Backend-Statusfeldern entstehen.

Die Dokument-ID `status` bleibt stabil.

Die bisher vorgesehenen IDs

- `status-running-operations`
- `status-resume`
- `status-component-readiness`

werden nicht für den allgemeinen Statusbereich verwendet. Falls die zugrunde liegenden Themen eigene Hilfeseiten benötigen, erhalten sie funktionsbezogene IDs in Face Matching, Checks, Cleanup, External Worker oder dem jeweils zuständigen Bereich.

---

## 5. Konsequenz für die Indexseite

Die Kurzbeschreibung von **Status** muss ausdrücklich die Ansicht benennen und darf nicht den Eindruck vermitteln, dort würden sämtliche laufenden Prozesse des Pakets erklärt.

Zieltext:

> Beschreibt die Status-Ansicht von ImgData mit den dort dargestellten Paket-, Datenbank- und Komponenteninformationen. Laufzustände einzelner Funktionen werden in den jeweiligen Hilfebereichen behandelt.

Die englische Fassung folgt derselben Abgrenzung.

---

## 6. Regel für weitere Hilfepunkte

Für die weitere Ausarbeitung gilt grundsätzlich:

> Ein Status gehört in die Hilfe der Funktion, deren Zustand er beschreibt.

Nur Informationen, die tatsächlich in der globalen Status-Ansicht zusammengefasst werden, gehören unter `status`.

Damit bleibt die Hilfe entlang der Benutzeroberfläche und der fachlichen Funktionen strukturiert und bildet nicht die interne Statusarchitektur des Backends nach.
