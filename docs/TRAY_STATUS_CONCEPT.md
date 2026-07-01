# Konzept: DSM-Tray-Status fuer laufende AV_ImgData-Prozesse

## Ziel

`AV_ImgData` soll laufende Paketprozesse optional im DSM-System-Tray anzeigen koennen. Beispiele sind Dateianalyse, Checks, Face Matching, Cleanup und laengere Metadaten-Operationen.

Der Tray soll kein zweiter vollstaendiger UI-Einstieg werden. Er dient als kompakte Laufzeit-Anzeige:

- ob ein relevanter Prozess laeuft
- welcher Prozess laeuft
- grober Fortschritt
- wichtigste Zaehler, etwa verarbeitet, Treffer, Fehler
- schneller Sprung in die normale `AV_ImgData`-App

Der aktuelle Erkenntnisstand zeigt einen realistischen technischen Ansatz ueber eine eigene versteckte DSM-Tray-App-Klasse. Die Nutzung der DSM-internen `SYNO.Core.BackgroundTask`-Registrierung ist dagegen fuer Drittanbieterpakete noch nicht ausreichend belegt.

## Gepruefte Grundlage

Die Analyse basiert auf lokal abgelegten DSM-/Paketquellen und einer HAR-Aufzeichnung mit Indexer-, Drive-Synchronisation- und Photo-Analyse-Informationen.

Wichtige Belege aus Synology Drive:

- `sources/SynologyDrive/INFO`
  - `dsmappname` enthaelt neben normalen App-Klassen auch Tray-Klassen:
    - `SYNO.SDS.SynologyDriveShareSync.TrayApp`
    - `SYNO.SDS.CSTN.Tray.DesktopIndex.Instance`
- `sources/SynologyDrive/target/ui/config`
  - `desktop_index_tray.js` ist als versteckte Auto-Launch-App definiert:
    - `type: "app"`
    - `hidden: true`
    - `autoLaunch: true`
    - `autoLaunchType: "tray"`
    - `depend: ["SYNO.SDS.CSTN.Tray.DesktopIndex.Tray"]`
- `sources/SynologyDrive/target/ui/desktop_index_tray.js`
  - erzeugt eine `SYNO.SDS.Tray.ArrowTray`
  - rendert ein `SYNO.SDS.Tray.Panel`
  - pollt `SYNO.SynologyDrive.Index.get_native_client_status`
  - steuert Sichtbarkeit ueber `setTaskButtonVisible(true/false)`
- `sources/SynologyDrive/target/sharesync/ui/config`
  - `app_tray.js` ist als versteckte Auto-Launch-App definiert:
    - `type: "app"`
    - `hidden: true`
    - `autoLaunch: true`
- `sources/SynologyDrive/target/sharesync/ui/app_tray.js`
  - erzeugt ebenfalls eine `SYNO.SDS.Tray.ArrowTray`
  - pollt `SYNO.SynologyDriveShareSync.Connection.list`
  - nutzt `additional:["tray_status","newest_change"]`
  - blendet den Tray nur bei relevanten Daten ein

Ergaenzend ist in `syno_api_doc` dokumentiert:

- `SYNO.Core.Desktop.Initdata.get_ui_config` liefert `JSConfig` mit `autoLaunch`, `autoLaunchType`, `hidden`, `type`, `depend`, `jsBaseURL`, `jsID` und weiteren App-Konfigurationsfeldern.
- `SYNO.Core.Package.list` mit `additional=["dsm_apps"]` liefert DSM-App-Klassen aus Paketmetadaten.
- `SYNO.SynologyDrive.Index.get_native_client_status` und `SYNO.SynologyDriveShareSync.Connection.list` sind die beobachteten Drive-Tray-Polling-APIs.

## Schlussfolgerung

Der naheliegende Ansatz fuer `AV_ImgData` ist eine zusaetzliche versteckte DSM-App-Klasse, die beim DSM-Login automatisch gestartet wird und eine Tray-Komponente erzeugt.

Nicht der Hintergrundprozess selbst registriert sich im Tray. Stattdessen:

1. DSM laedt die versteckte Tray-App ueber Paket-UI-Konfiguration.
2. Die Tray-App erzeugt ein `SYNO.SDS.Tray.ArrowTray`.
3. Die Tray-App pollt eine `AV_ImgData`-Status-API.
4. Die Tray-App zeigt oder versteckt den Tray-Button anhand des Backend-Status.

Dieses Muster entspricht der geprueften Synology-Drive-Implementierung.

## Nicht-Ziele der ersten Umsetzung

Die erste Umsetzung soll bewusst klein bleiben:

- keine direkte Nutzung von `SYNO.Core.BackgroundTask` zum Registrieren eigener DSM-BackgroundTasks
- keine Eingriffe in Synology-interne BackgroundTask-Datenstrukturen
- kein eigenes globales Benachrichtigungssystem
- keine vollstaendige Prozesssteuerung aus dem Tray
- keine Schreiboperationen aus dem Tray ausser optionalem Stop/Pause in einer spaeteren Phase
- kein Ersatz fuer die normale Statusansicht

## Offene Risiken

Der wichtigste offene Punkt ist die Drittanbieterfaehigkeit:

- Synology Drive ist ein Synology-Paket und nutzt versteckte Tray-App-Klassen.
- Es ist noch nicht bewiesen, dass DSM Drittanbieterpakete mit `autoLaunchType: "tray"` exakt gleich behandelt.
- Der Nachweis muss durch ein installiertes `AV_ImgData`-Testpaket mit HAR/DSM-Login erfolgen.

Weitere Risiken:

- DSM kann Auto-Launch-Klassen je nach Privileg, `dsmappname`, `conf/privilege` oder Benutzergruppe filtern.
- `SYNO.SDS.Tray.*` ist ein internes DSM-JS-API und nicht als stabile Drittanbieter-API dokumentiert.
- Ein kaputter Tray-JS-Code kann beim DSM-Login UI-Fehler verursachen.
- Polling darf keine Backend-Last erzeugen und muss bei Fehlern defensiv abschalten.

## Paketregistrierung

### `INFO.sh`

Die bestehende DSM-App-Klasse bleibt unveraendert. Zusaetzlich wird eine Tray-App-Klasse registriert.

Vorschlag:

```bash
dsmappname="SYNO.SDS.App.AV_ImgData.Instance SYNO.SDS.App.AV_ImgData.Tray.Instance"
```

### `conf/privilege`

Die Tray-App muss mindestens dieselben App-Rechte wie die normale App erhalten, sonst kann DSM sie beim Initdata-Aufbau herausfiltern.

Vorschlag:

```json
{
  "app": {
    "SYNO.SDS.App.AV_ImgData.Instance": {
      "permission": [
        {
          "group": "users",
          "permission": "allow"
        }
      ]
    },
    "SYNO.SDS.App.AV_ImgData.Tray.Instance": {
      "permission": [
        {
          "group": "users",
          "permission": "allow"
        }
      ]
    }
  }
}
```

### `ui/app.config`

Die normale App bleibt sichtbar. Die Tray-App wird als versteckte Auto-Launch-App definiert.

Vorschlag:

```json
{
  "SYNO.SDS.App.AV_ImgData.Instance": {
    "type": "app",
    "title": "ImgData",
    "appWindow": "SYNO.SDS.App.AV_ImgData.Instance",
    "allUsers": true,
    "allowMultiInstance": false,
    "hidden": false,
    "icon": "images/icon.png"
  },
  "SYNO.SDS.App.AV_ImgData.Tray.Instance": {
    "type": "app",
    "title": "ImgData",
    "hidden": true,
    "autoLaunch": true,
    "autoLaunchType": "tray",
    "allUsers": true,
    "allowMultiInstance": false,
    "depend": [
      "SYNO.SDS.App.AV_ImgData.Tray"
    ]
  },
  "SYNO.SDS.App.AV_ImgData.Tray": {
    "type": "lib",
    "title": "ImgData",
    "depend": [
      "SYNO.SDS.Tray.ArrowTray"
    ]
  }
}
```

Ob `autoLaunchType: "tray"` zwingend noetig ist, muss im Test geklaert werden. Synology Drive nutzt es fuer den Index-Tray. ShareSync nutzt `autoLaunch: true` ohne sichtbares `autoLaunchType`.

## Frontend-Architektur

Empfohlene neue Datei:

```text
ui/src/tray/av-imgdata-tray.js
```

oder, falls die bestehende Build-Struktur nur einen Bundle-Einstieg vorsieht:

```text
ui/src/tray.js
```

Die Tray-Klassen sollten nicht die komplette Vue-App starten. Sie sollen klein und robust sein.

Minimalstruktur:

```javascript
SYNO.namespace('SYNO.SDS.App.AV_ImgData.Tray');

SYNO.SDS.App.AV_ImgData.Tray.Instance = Ext.extend(SYNO.SDS.AppInstance, {
  initInstance: function () {
    var tray = new SYNO.SDS.App.AV_ImgData.Tray.Item({ appInstance: this });
    this.addInstance(tray);
    tray.open();
  }
});

Ext.define('SYNO.SDS.App.AV_ImgData.Tray.Item', {
  extend: 'SYNO.SDS.Tray.ArrowTray',
  initPanel: function () {
    return new SYNO.SDS.App.AV_ImgData.Tray.Panel({ module: this });
  }
});
```

Das Panel pollt nur eine kleine Backend-Status-API und setzt die Tray-Sichtbarkeit:

```javascript
this.module.setTaskButtonVisible(true);
this.module.setTaskButtonVisible(false);
```

## Backend-Status-API

Der Tray soll nicht mehrere bestehende Detailendpunkte pollten. Stattdessen wird ein kleiner zusammengefasster Endpunkt empfohlen.

Vorschlag:

```text
POST /webman/3rdparty/AV_ImgData/index.cgi/api/tray_status
```

Antwortschema:

```json
{
  "success": true,
  "data": {
    "visible": true,
    "phase": "running",
    "operation": "file_analysis",
    "operation_label": "Dateianalyse",
    "message": "Analysiere Bilddateien",
    "current": 120,
    "total": 41070,
    "percent": 0.29,
    "counters": {
      "findings": 7,
      "errors": 0
    },
    "attention": false,
    "updated_at": "2026-06-29T20:00:00+02:00"
  }
}
```

Regeln:

- `visible=false`: Tray-Button ausblenden.
- `phase=running|preparing|stopping`: Tray anzeigen.
- `phase=failed`: Tray anzeigen, bis Nutzer die normale App oeffnet oder Fehler quittiert.
- `phase=finished`: Tray nur kurz oder gar nicht anzeigen, je nach spaeterer UX-Entscheidung.
- `percent` ist optional. Wenn `total` unbekannt ist, kann die UI nur Text anzeigen.

## Mapping auf bestehende Operationen

Der Tray sollte das integrierte Statuskonzept wiederverwenden und keine eigene Semantik erfinden.

| Operation | Tray-Anzeige |
|---|---|
| `file_analysis` | Dateianalyse laeuft, Fortschritt Dateien/Bilder |
| `checks` | Check laeuft, Fortschritt Dateien oder Eintraege |
| `face_match` | Face Matching laeuft, Treffer/uebertragen |
| `cleanup` | Cleanup laeuft, bereinigt/uebersprungen/Fehler |

Prioritaet bei mehreren Zustaenden:

1. `failed`
2. `stopping`
3. aktive `running`/`preparing` Operation
4. kuerzlich beendete Operation mit relevanten Fehlern
5. nichts anzeigen

Wenn mehrere Operationen parallel sichtbar waeren, soll das Backend eine klare Hauptoperation auswaehlen. Das UI soll nicht selbst aus mehreren Rohzustaenden priorisieren.

## Polling

Startwerte:

- Intervall bei verstecktem Panel: 10 bis 15 Sekunden
- Intervall bei geoeffnetem Panel: 3 bis 5 Sekunden
- Bei wiederholten Fehlern: Backoff auf 30 bis 60 Sekunden

Der Tray darf keine langen Detailabfragen starten. Der Backend-Endpunkt muss schnell antworten und aus bereits vorhandenen Runtime-/Progress-Dateien oder Speicherzustaenden lesen.

## UI-Verhalten

### Tray-Button

Der Button ist nur sichtbar, wenn `visible=true`.

Moegliche Icons:

- normal: Paketicon oder eigenes Tray-Icon
- laufend: animierte oder aktive Klasse, falls DSM-kompatibel
- Fehler/Aufmerksamkeit: gesonderte Icon-Klasse

### Panel

Panel-Inhalt Phase 1:

- Titel `ImgData`
- Operation
- Statusmeldung
- optional Fortschrittsbalken
- zwei bis vier relevante Zaehler
- Button `Oeffnen`

Keine komplexen Tabellen im Tray.

### App oeffnen

Der Button `Oeffnen` soll die normale DSM-App starten oder fokussieren. Falls das nicht stabil ueber DSM-AppMgr erreichbar ist, kann Phase 1 ersatzweise nur ein Link/Launch-Versuch enthalten und der Tray bleibt rein informativ.

## Test- und Nachweisplan

Phase 1 soll nur beweisen, dass DSM die Drittanbieter-Tray-App laedt.

Pruefschritte:

1. Paket mit erweiterter `dsmappname` installieren.
2. Nach DSM-Login HAR aufzeichnen.
3. In `SYNO.Core.Desktop.Initdata.get_ui_config` pruefen:
   - `SYNO.SDS.App.AV_ImgData.Tray.Instance` vorhanden
   - `autoLaunch=true`
   - `hidden=true`
   - falls gesetzt: `autoLaunchType=tray`
4. Browser-Konsole pruefen:
   - keine JS-Fehler beim Laden der Tray-Klasse
5. Backend-Endpunkt manuell testen:
   - `visible=false`: kein Tray-Button
   - `visible=true`: Tray-Button sichtbar
6. Laufende Dateianalyse starten:
   - Tray zeigt Operation und Fortschritt
7. Operation beenden:
   - Tray verschwindet oder zeigt definierten Abschlusszustand

Erst wenn diese Punkte belegt sind, sollte der Tray als Feature aktiviert werden.

## Implementierungsphasen

### Phase 0: Dokumentation und Belege

- Dieses Konzept ablegen.
- Synology-Drive-Belege in `syno_api_doc` dokumentieren.
- Keine Paketlogik aendern.

### Phase 1: Minimaler Prototyp

- `INFO.sh` um Tray-Klasse erweitern.
- `conf/privilege` um Tray-Klasse erweitern.
- `ui/app.config` um Tray-App und Tray-Lib erweitern.
- Kleine Tray-JS-Datei erzeugen.
- Backend-Endpunkt `/api/tray_status` mit statischem oder einfachem Runtime-Status bereitstellen.

Ziel: DSM laedt die Tray-App und kann Button anzeigen/verstecken.

### Phase 2: Integration mit Runtime-Status

- `tray_status` aus bestehendem Status-/Progress-Konzept ableiten.
- Dateianalyse, Checks, Face Matching und Cleanup anbinden.
- Fehlerzustand und Stop-/Finished-Verhalten festlegen.

### Phase 3: Bedienung aus dem Tray

- normale App fokussieren/oeffnen
- optional Stop/Pause nur fuer dafuer geeignete Operationen
- lokalisierte Texte und Icon-Feinschliff

## Entscheidungsempfehlung

Der Tray-Ansatz ist ausreichend belegt, um einen kontrollierten Prototypen zu bauen.

Empfohlen wird:

1. nicht mit `SYNO.Core.BackgroundTask` starten
2. zuerst versteckte DSM-Tray-App nach Drive-Muster testen
3. den Backend-Status stark zusammenfassen
4. das Feature erst nach HAR-Nachweis fuer Drittanbieter-Loading produktiv aktivieren

