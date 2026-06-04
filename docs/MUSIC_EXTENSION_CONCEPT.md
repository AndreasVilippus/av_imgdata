# Konzept: Erweiterung um einen Musikbereich

## Ziel

`AV_ImgData` soll perspektivisch nicht nur Fotometadaten unterstützen, sondern als DSM-Werkzeug für Medien-Metadaten erweitert werden. Der vorhandene Fotobereich bleibt der Kern des Pakets. Zusätzlich wird ein separater Musikbereich eingeführt.

Die erste Musikfunktion ist eine optionale Bewertungsübernahme nach DS Audio beziehungsweise in die von Synology Audio Station genutzte Musikdatenhaltung.

Wichtig: DS Audio / Audio Station darf keine harte Abhängigkeit des Gesamtpakets werden. Ist Audio Station nicht installiert oder nicht nutzbar, bleibt das Paket vollständig installierbar und alle Fotofunktionen bleiben aktiv. Nur die Musik-Bewertungsübernahme wird dann deaktiviert beziehungsweise als nicht verfügbar angezeigt.

## Ausgangslage aus dem bestehenden Projekt

Aus den geprüften Projektdateien ergeben sich folgende verwertbare Grundlagen:

- Das Paket ist ein DSM-7.3-Paket `AV_ImgData` mit `arch="noarch"`, `support_cgi="yes"`, eigener DSM-App und UI-Verzeichnis `ui`.
- Die bestehende Anwendung nutzt eine Vue-2-Oberfläche mit Synology-DSM-Komponenten.
- Die linke Navigation wird zentral in `ui/src/components/AppSidebarNav.vue` aufgebaut.
- Die Hauptansichten werden zentral in `ui/src/App.vue` anhand von `selectedOption` geschaltet.
- Backend-Aufrufe laufen aus der UI über einen gemeinsamen DSM-API-Client `ui/src/services/dsm-api-client.js`.
- Die Laufzeitkonfiguration liegt initial in `var/config.json` und wird zur Laufzeit in das Paket-Var-Verzeichnis übernommen.
- Das bestehende Paket trennt bereits fachliche Bereiche wie Status, Face Matching, Checks, Cleanup, Configuration und External Libraries.
- Externe Komponenten sind bereits als optionales Konzept vorhanden, etwa ExifTool und optionale pip-Pakete.

Damit sollte der Musikbereich nicht als separater DSM-Desktop-App-Einstieg, sondern als zusätzlicher Fachbereich innerhalb derselben App umgesetzt werden.

## Navigationskonzept

Die linke Navigation sollte künftig sichtbar in Bereiche gegliedert werden:

```text
Fotos
  Status
  Face Matching
  Checks
  Cleanup

Musik
  Bewertungen

Einstellungen / Erweiterungen
  Configuration
  External libraries
  ExifTool
  pip packages
```

Der Begriff `Fotos` fasst die vorhandenen Funktionen zusammen. Der neue Bereich `Musik` enthält zunächst nur eine Funktion: `Bewertungen`. Weitere Musikfunktionen, etwa Tag-Abgleich, Cover-Prüfung oder Dublettenanalyse, können später darunter ergänzt werden.

Technische UI-Änderungen:

- `AppSidebarNav.vue`
  - Abschnittsüberschriften ergänzen, zum Beispiel `nav:section_photos`, `nav:section_music`, `nav:section_settings_extensions`.
  - Neue Option `music_ratings` hinzufügen.
  - Musikoption deaktiviert darstellen, wenn das Backend meldet, dass Audio Station nicht verfügbar ist.
- `App.vue`
  - `MusicRatingsView.vue` importieren.
  - View mit `v-if="selectedOption === 'music_ratings'"` einhängen.
  - Bei Auswahl von `music_ratings` Status/Capabilities laden.
- Lokalisierung
  - Strings für `enu` und `ger` ergänzen.

## Funktionsumfang Phase 1: Bewertungsübernahme nach DS Audio

### Fachliches Ziel

Musikbewertungen aus einer Quelle sollen in die DS-Audio-/Audio-Station-Datenhaltung übernommen werden.

DS Audio ist dabei nicht die eigentliche technische Datenquelle, sondern der Client. Technisch relevant ist die serverseitige Audio-Station-Installation beziehungsweise die von ihr genutzte Musikdatenbank und/oder API.

### Unterstützte Bewertungsquellen

Für Phase 1 sollten drei Quellen vorgesehen werden, aber nicht zwingend alle sofort implementiert werden:

1. **Dateimetadaten**
   - Bewertungen aus Audio-Dateien lesen.
   - Typische Felder je nach Format:
     - MP3/ID3: Popularimeter / `POPM`, ggf. proprietäre Rating-Frames.
     - FLAC/Ogg/Vorbis: `RATING`, `FMPS_RATING`, `POPULARITY`.
     - MP4/M4A: iTunes-/Music-kompatible Rating-Felder, sofern zuverlässig lesbar.
   - Vorteil: direkte Wiederverwendung des bestehenden Metadaten-Gedankens.
   - Nachteil: Rating-Schemata sind uneinheitlich.

2. **Sidecar-/Exportdatei**
   - JSON oder CSV als explizite Importquelle.
   - Empfohlenes Minimum:
     - Pfad oder eindeutiger Musikdatei-Schlüssel
     - Bewertung normalisiert 0 bis 5 Sterne oder 0 bis 100 Prozent
     - optional Zeitstempel und Quelle
   - Vorteil: gut testbar und unabhängig von Tag-Besonderheiten.

3. **Externe Musikbibliothek**
   - Später möglich, zum Beispiel Import aus MusicBee, iTunes/Music XML, foobar2000-Export oder Plex/Jellyfin-Export.
   - Für Phase 1 nur als Erweiterungspunkt dokumentieren.

Empfehlung: Phase 1 sollte mit CSV/JSON und optionalem Datei-Metadatenlesen starten. Damit kann die Übernahmelogik unabhängig von Tag-Spezialfällen und Audio Station validiert werden.

## Zielsystem: Audio Station / DS Audio

### Verfügbarkeitserkennung

Das Paket darf Audio Station nicht voraussetzen. Beim Öffnen des Musikbereichs und optional beim Statusladen sollte ein Capability-Check laufen.

Mögliche Prüfschritte:

1. Paketinstallation prüfen
   - Paketname vermutlich `AudioStation` beziehungsweise Synology-interner Paketname der Audio Station.
   - Prüfung über DSM-Paketstatus, falls aus dem Paketkontext erlaubt.
   - Alternativ Prüfung bekannter Pfade unter `/var/packages/AudioStation/`.
2. Dienststatus prüfen
   - Paket installiert und gestartet?
3. API-Verfügbarkeit prüfen
   - Existiert ein Audio-Station-API-Endpunkt über `/webapi/query.cgi`?
   - Liefert `SYNO.API.Info` Einträge für Audio Station?
4. Datenbankzugriff prüfen
   - Nur falls API nicht ausreichend ist und direkter DB-Zugriff vorgesehen wird.
   - Direkter DB-Zugriff sollte als riskanter Fallback behandelt werden.

Capability-Ergebnis:

```json
{
  "music": {
    "enabled": true,
    "audio_station": {
      "installed": true,
      "running": true,
      "api_available": true,
      "rating_write_supported": false,
      "reason": "rating write endpoint not implemented yet"
    }
  }
}
```

Ist Audio Station nicht vorhanden, sollte die UI anzeigen:

> Audio Station / DS Audio ist nicht installiert oder nicht verfügbar. Die Bewertungsübernahme ist deshalb deaktiviert. Fotofunktionen sind nicht betroffen.

### Schreibstrategie

Für die Bewertungsübernahme gibt es zwei technische Optionen:

#### Option A: Offizielle/inoffizielle Audio-Station-WebAPI

Bevorzugt, wenn ein stabiler Endpunkt für Ratings existiert.

Vorteile:

- Weniger Eingriff in interne Datenbanken.
- Bessere Kompatibilität mit DSM-Rechten und Sessions.
- UI nutzt bereits DSM-Session, Cookies und SynoToken.

Nachteile:

- Rating-Schreibfunktion muss konkret verifiziert werden.
- Synology-WebAPIs sind teilweise nicht vollständig dokumentiert.

#### Option B: Direkter Zugriff auf Audio-Station-Datenbank

Nur als Fallback und nur nach gesonderter Analyse.

Vorteile:

- Unabhängig von fehlenden API-Endpunkten.

Nachteile:

- Höheres Risiko bei Synology-Updates.
- Datenbankschema kann sich ändern.
- Berechtigungen und Sperren müssen sauber behandelt werden.
- Erfordert Backup-/Rollback-Konzept.

Empfehlung: Phase 1 sollte zuerst eine reine Analyse-/Dry-Run-Funktion enthalten. Schreiben wird erst aktiviert, wenn Ziel-API oder Datenbankschema verifiziert sind.

## Datenmodell

### Normalisierte Bewertung

Intern sollte eine normalisierte Bewertung verwendet werden:

```text
rating_percent: 0..100 oder null
rating_stars: 0..5 in 0.5-Schritten oder null
source_rating_raw: Originalwert
source_rating_schema: popm | vorbis | mp4 | csv | json | unknown
```

Für DS Audio muss die Bewertung in das erwartete Zielmodell gemappt werden. Dieses Mapping darf nicht geraten werden. Es muss durch Analyse einer Testinstallation verifiziert werden.

### Musikdatei-Identifikation

Die Zuordnung darf nicht allein über Dateinamen erfolgen. Empfohlene Reihenfolge:

1. Vollständiger DSM-Pfad.
2. Pfad relativ zu konfigurierten Musikordnern.
3. Audio-Station-Medien-ID, falls aus API/DB bekannt.
4. Fallback über technische Metadaten:
   - Dateigröße
   - Dauer
   - Artist
   - Album
   - Title
   - Tracknummer

Für Phase 1 sollte der sichere Pfad-Match bevorzugt werden. Unsichere Matches werden nur im Dry-Run angezeigt und nicht automatisch geschrieben.

### Import-Status

Für jeden Kandidaten sollte ein Ergebnisobjekt erzeugt werden:

```json
{
  "source_path": "/volume1/music/Artist/Album/Track.flac",
  "target_id": 12345,
  "target_path": "/volume1/music/Artist/Album/Track.flac",
  "source_rating_percent": 80,
  "target_rating_percent": 60,
  "action": "update",
  "confidence": "exact_path",
  "status": "pending"
}
```

## Backend-Architektur

Der Musikbereich sollte als neues Backend-Modul neben den bestehenden Foto-/Analysemodulen entstehen.

Vorgeschlagene neue Dateien/Module:

```text
src/
  music/
    __init__.py
    audio_station_capabilities.py
    audio_station_client.py
    audio_station_db.py              # nur falls DB-Fallback nötig
    ratings_import.py
    ratings_sources.py
    ratings_mapping.py
    music_file_index.py
    models.py
```

Falls die aktuelle Backend-Struktur keine Paketunterordner verwendet, sollten die Namen an die bestehende Struktur angepasst werden. Wichtig ist die fachliche Trennung: Musiklogik darf nicht in bestehende Foto-/Face-Matching-Module eingemischt werden.

### Wiederverwendbare Basis

| Bestehende Basis | Wiederverwendung für Musik | Bewertung |
|---|---|---|
| DSM-Paketstruktur | vollständig | hoch |
| DSM-App-Shell und UI-Build | vollständig | hoch |
| Vue-2-Komponentenmuster | vollständig | hoch |
| Sidebar-/View-Schaltung | vollständig | hoch |
| DSM-API-Client der UI | weitgehend | hoch |
| Runtime-Konfigurationsmodell | vollständig | hoch |
| Optionales External-Libraries-Konzept | teilweise | hoch |
| ExifTool-Konzept | teilweise für Audio-Metadaten | mittel |
| File-Scan-Grundlagen | teilweise, sofern generisch genug | mittel |
| Foto-/Face-Matching-Logik | nicht fachlich wiederverwenden | niedrig |
| Name-Mapping | nicht direkt | niedrig |
| Checks-/Cleanup-Sessionmodell | als Ablaufmuster wiederverwendbar | mittel |

## API-Konzept

Neue Backend-Endpunkte sollten analog zu den bestehenden langen Aufgaben eigene Timeouts erhalten.

Vorgeschlagene Endpunkte:

```text
music_capabilities
music_ratings_preview_start
music_ratings_preview_status
music_ratings_preview_result
music_ratings_apply_start
music_ratings_apply_status
music_ratings_apply_result
music_ratings_cancel
```

Ablauf:

1. UI ruft `music_capabilities`.
2. Wenn Audio Station verfügbar ist, kann ein Preview gestartet werden.
3. Preview liest Quelle, ermittelt Zieltreffer und zeigt geplante Änderungen.
4. Nutzer bestätigt explizit.
5. Apply schreibt Bewertungen.
6. Ergebnisprotokoll wird gespeichert.

`dsm-api-client.js` sollte für diese Endpunkte Timeoutwerte erhalten, zum Beispiel 120 Sekunden für Start-/Apply-Endpunkte.

## Konfiguration

`var/config.json` sollte um einen `music`-Block erweitert werden:

```json
{
  "music": {
    "ENABLED": true,
    "AUDIO_STATION": {
      "REQUIRED": false,
      "AUTO_DETECT": true,
      "PACKAGE_NAME": "AudioStation",
      "ALLOW_DATABASE_FALLBACK": false,
      "DRY_RUN_DEFAULT": true
    },
    "RATINGS": {
      "SOURCE_TYPES": ["json", "csv", "audio_metadata"],
      "DEFAULT_SOURCE_TYPE": "json",
      "MIN_MATCH_CONFIDENCE_FOR_APPLY": "exact_path",
      "OVERWRITE_EXISTING": false,
      "WRITE_ONLY_IF_DIFFERENT": true,
      "BACKUP_BEFORE_WRITE": true
    },
    "FILES": {
      "AUDIO_EXTENSIONS": ["mp3", "flac", "m4a", "aac", "ogg", "opus", "wav", "aiff"]
    }
  }
}
```

Diese Konfiguration stellt sicher:

- Musik kann paketweit deaktiviert werden.
- Audio Station ist optional.
- Datenbank-Fallback ist standardmäßig aus.
- Schreibaktionen sind standardmäßig defensiv.
- Dry-Run ist Standard.

## UI-Konzept für `MusicRatingsView.vue`

Die View sollte aus vier Blöcken bestehen:

1. **Status / Voraussetzungen**
   - Audio Station installiert: ja/nein
   - Dienst läuft: ja/nein
   - API verfügbar: ja/nein
   - Schreiben möglich: ja/nein

2. **Quelle auswählen**
   - JSON/CSV-Datei aus Paket-Var oder Upload/Dateipfad.
   - Optional: Audio-Metadaten aus Musikordner scannen.
   - Quellformat erklären.

3. **Vorschau**
   - Anzahl gelesener Bewertungen.
   - Anzahl exakter Treffer.
   - Anzahl unsicherer Treffer.
   - Anzahl geplanter Updates.
   - Konflikte und nicht gefundene Dateien.

4. **Übernehmen**
   - Nur aktiv, wenn Audio Station verfügbar und Schreibstrategie verifiziert ist.
   - Checkbox: `Ich habe ein Backup und möchte die Bewertungen übernehmen`.
   - Ergebnisprotokoll mit Exportoption.

## Paketstruktur und Abhängigkeiten

### Keine harte DSM-Abhängigkeit auf Audio Station

`INFO.sh` sollte keine harte Abhängigkeit auf Audio Station erhalten. Sonst wäre das Paket nicht mehr sauber für reine Fotonutzer installierbar.

Stattdessen:

- Audio Station per Runtime-Capability erkennen.
- UI-Funktion deaktivieren, wenn nicht vorhanden.
- Keine Installation abbrechen, wenn Audio Station fehlt.

### Zusätzliche Python-Abhängigkeiten

Sinnvolle optionale Bibliotheken:

- `mutagen`
  - Lesen und ggf. Schreiben von Audio-Tags.
  - Unterstützt ID3, FLAC/Vorbis, MP4 und weitere Formate.
  - Sollte als optionale pip-Komponente modelliert werden.
- `sqlite3`
  - In Python-Standardbibliothek vorhanden.
  - Nur relevant bei verifiziertem DB-Fallback.
- ExifTool
  - Kann Audio-Metadaten lesen, ist aber für Audio-Ratings nicht zwingend die beste primäre Wahl.
  - Vorteil: vorhandenes optionales Konzept kann genutzt werden.

Empfehlung:

- `mutagen` als neue optionale Komponente `pip_packages.MUTAGEN` einführen.
- ExifTool nur als sekundäre Quelle für Metadatenanalyse verwenden.
- Keine neue harte Systemabhängigkeit einführen.

Beispielkonfiguration:

```json
{
  "pip_packages": {
    "MUTAGEN": {
      "ENABLED": false,
      "INSTALL_ON_START": false,
      "REQUIREMENTS_FILE": "requirements-optional-mutagen.txt",
      "WHEELHOUSE_ENABLED": true,
      "WHEELHOUSE_TARGET": "dsm7-x86_64-python38"
    }
  }
}
```

## Zusätzliche Sourcen, die notwendig oder sinnvoll sind

### Notwendig vor Implementierung des Schreibens

1. **Audio-Station-Paketstatus auf DSM 7.3**
   - Exakter Paketname.
   - Pfade unter `/var/packages/AudioStation/`.
   - Dienststatus-Mechanismus.

2. **Audio-Station-WebAPI**
   - Verfügbare APIs über `SYNO.API.Info`.
   - Gibt es einen stabilen Endpunkt zum Setzen von Ratings?
   - Benötigte Parameter, Rechte und Token.

3. **Audio-Station-Datenmodell**
   - Nur falls API nicht genügt.
   - Tabellen für Songs und Bewertungen.
   - Wertebereich der Bewertung.
   - Verhalten nach Medienindex-Neuscan.

4. **DS-Audio-Anzeigeverhalten**
   - Wird die geschriebene Bewertung sofort angezeigt?
   - Ist ein Reindex oder Cache-Refresh nötig?
   - Sind Benutzerbewertungen global oder benutzerbezogen?

### Sinnvoll für robuste Imports

1. **Rating-Schemata pro Audioformat**
   - ID3 POPM-Wertebereich und E-Mail-Identifier.
   - Vorbis/FLAC-Konventionen `RATING` und `FMPS_RATING`.
   - MP4/M4A-Rating-Konventionen.

2. **Testdaten**
   - Kleine Musikbibliothek mit MP3, FLAC, M4A.
   - Je Datei bekannte Ratings in unterschiedlichen Schemata.
   - DS-Audio-Testbibliothek mit bekannten Zielbewertungen.

3. **Exportformate externer Bibliotheken**
   - CSV/JSON als internes Zielformat priorisieren.
   - Später Adapter für MusicBee, iTunes/Music XML, foobar2000.

## Sicherheits- und Backup-Konzept

Bewertungen sind Nutzerdaten. Schreiboperationen müssen reversibel oder zumindest protokolliert sein.

Mindestanforderungen:

- Standardmäßig Dry-Run.
- Schreibfunktion nur nach expliziter Bestätigung.
- Vor jedem Update alten Zielwert protokollieren.
- Ergebnisdatei im Paket-Var-Verzeichnis speichern.
- Optional Rollback-Datei erzeugen.
- Keine Änderung bei unsicherem Match.
- Keine Änderung, wenn Zielwert bereits identisch ist.

Vorgeschlagene Ergebnisdateien:

```text
/var/packages/AV_ImgData/var/music_rating_imports/
  2026-06-04T120000_preview.json
  2026-06-04T120500_apply.json
  2026-06-04T120500_rollback.json
```

## Testkonzept

### Unit-Tests

- Rating-Normalisierung:
  - 0..5 Sterne nach 0..100 Prozent.
  - POPM 0..255 nach Zielskala.
  - Vorbis `RATING` Varianten.
- CSV-/JSON-Parser.
- Match-Logik für Pfade.
- Konfliktlogik.
- Capability-Parser für Audio Station.

### Integrationstests mit Mocks

- Audio Station fehlt.
- Audio Station installiert, aber gestoppt.
- API verfügbar, aber Schreiben nicht unterstützt.
- Preview mit exakten Matches.
- Preview mit unsicheren Matches.
- Apply mit Rollback-Protokoll.

### Manuelle DSM-Tests

- Installation ohne Audio Station.
- Installation mit Audio Station.
- Reine Fotofunktion nach Musik-Erweiterung unverändert nutzbar.
- Bewertungsübernahme in Testbibliothek.
- Anzeige der Bewertung in DS Audio.

## Migrationsstrategie

Die Erweiterung sollte ohne Breaking Change eingeführt werden.

1. `var/config.json` um `music` erweitern.
2. Backend muss fehlende `music`-Config mit Defaults auffüllen.
3. UI zeigt Musikbereich nur als deaktivierte Funktion, wenn Backend keine Capability liefert.
4. Bestehende Fotofunktionen dürfen keine Kenntnis von Musikmodulen benötigen.
5. Build- und Testpipeline bleibt unverändert, erhält aber zusätzliche Tests.

## Umsetzungsvorschlag in Etappen

### Etappe 1: UI- und Capability-Grundlage

- Sidebar in Bereiche gliedern.
- `MusicRatingsView.vue` als Status-/Platzhalterview.
- Backend-Endpunkt `music_capabilities`.
- Audio-Station-Erkennung ohne Schreibzugriff.
- Tests für fehlende Audio Station.

### Etappe 2: Import-Preview ohne Schreiben

- JSON-/CSV-Quelle definieren.
- Parser und Normalisierung.
- Zielbibliothek über Audio-Station-API oder Mock ermitteln.
- Preview-Ergebnis speichern und anzeigen.

### Etappe 3: Verifizierte Schreibstrategie

- Audio-Station-Rating-Schreibweg verifizieren.
- Apply-Endpunkt implementieren.
- Backup-/Rollback-Protokoll.
- UI-Bestätigung einbauen.

### Etappe 4: Audio-Metadaten als Quelle

- Optional `mutagen` einführen.
- Audio-Dateien lesen.
- Rating-Schemata abbilden.
- ExifTool-Fallback prüfen.

## Bewertung der Wiederverwendung

Die Paketbasis kann zu einem großen Teil weiterverwendet werden. Besonders geeignet sind DSM-Paketstruktur, UI-Shell, Navigationsmechanik, DSM-API-Client, Konfiguration, optionales Erweiterungsmodell und Test-/Build-Ansatz.

Neu gebaut werden müssen die fachliche Musiklogik, Audio-Station-Capabilities, Rating-Normalisierung, Importquellen, Ziel-Matching und Schreib-/Rollback-Mechanik.

Die Paketstruktur sollte nicht in ein neues Paket aufgeteilt werden. Stattdessen sollte `AV_ImgData` intern modularisiert werden: Foto- und Musikfunktionen teilen Infrastruktur, bleiben fachlich aber getrennt. Eine spätere Umbenennung des Anzeigenamens kann geprüft werden, ist für die erste Erweiterung aber nicht notwendig.

## Offene Prüfentscheidungen

Vor der Implementierung dürfen folgende Punkte nicht angenommen werden:

- Exakter Audio-Station-Paketname auf DSM 7.3.
- Verfügbarkeit eines Rating-Schreibendpunkts in der Audio-Station-WebAPI.
- Datenbanktabellen und Wertebereich für Ratings.
- Ob Bewertungen global oder benutzerbezogen gespeichert werden.
- Ob DS Audio geänderte Ratings sofort sieht oder ein Cache-/Index-Refresh nötig ist.

Diese Punkte müssen auf einer DSM-Testinstallation geprüft und anschließend im Konzept oder in einer Implementierungsnotiz ergänzt werden.
