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

Verifizierter Stand für `0.8.0`:

- Ein Laufzeittest bestätigt, dass `SYNO.AudioStation.Song.setrating(id, rating)` die Bewertung der aktiven Sitzung schreibt.
- Die Paketquellen von Audio Station `7.2.0-5516` bestätigen die Bindung an `APIRequest::GetLoginUID()` und enthalten keinen Zielbenutzer-Parameter oder alternativen administrativen Rating-Endpunkt.
- Das mitgelieferte Datenbankschema bestätigt `rating_track(userid bigint, track integer, star integer)` mit Primärschlüssel `(userid, track)` und Fremdschlüssel auf `track(id)`.
- Für den erforderlichen Multi-User-Systemdienst ist Option B der vorgesehene Schreibweg.
- Bis zum Nachweis von Authentifizierung, Transaktionsverhalten, Sperren, Backup/Rollback und Aktualisierung des Audio-Station-Zustands bleibt der Schreibweg deaktiviert; die Implementierung arbeitet als Dry-Run.

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

## Verifizierte Grundlage aus `dev/pg.php`

Die vorhandene PHP-Funktion belegt für die dort eingesetzte Audio-Station-Version:

- PostgreSQL-Datenbank: `mediaserver`
- Musiktabelle: `track` mit mindestens `id` und `path`
- Benutzerbezogene Bewertungstabelle: `rating_track`
- Bewertungsfelder: `userid`, `track`, `star`
- Zielskala: ganzzahlige Sterne `1..5`
- Die Zuordnung erfolgt über den exakten Dateipfad aus `track.path`.
- Eine Bewertung wird für jeden ausgewählten Benutzer separat geschrieben.

Die in `pg.php` verwendete Windows-/POPM-Abbildung ist:

| POPM-Wert | Zielsterne |
|---:|---:|
| `1` | 1 |
| `64` | 2 |
| `128` | 3 |
| `196` | 4 |
| `255` | 5 |

Der PHP-Prototyp enthält fest codierte Benutzer-IDs und Zugangsdaten. Beides darf nicht in das Paket übernommen werden. Benutzer müssen zur Laufzeit ausgelesen und in der UI ausgewählt werden. Zugangsdaten für einen möglichen Datenbank-Fallback benötigen ein separates Berechtigungs- und Secret-Konzept.

Für den API-Weg genügt zunächst der DSM-Benutzername zur Auswahl und Protokollierung. Für den DB-Fallback ist zwingend die numerische UID erforderlich. `SYNO.Core.User.list` ist als Benutzerquelle vorgesehen; ob die Runtime-Antwort `uid` oder `id` zuverlässig liefert, muss im Browser geprüft und anschließend in `syno_api_doc` dokumentiert werden. Ohne belegte UID darf kein DB-Schreiben angeboten werden.

## Bewertungsformate und Normalisierung

Intern werden alle Quellen auf `rating_stars` in 0,5-Stern-Schritten und `rating_percent` von 0 bis 100 normalisiert. Für Audio Station wird erst beim Schreiben auf die belegte Zielskala abgebildet.

| Datei-/Tagfamilie | Relevante Felder | Quellskala | Normalisierung |
|---|---|---:|---|
| MP3 / ID3v2 | `POPM` / Popularimeter | `0..255` | Windows-Werte gemäß `pg.php`; andere Werte stufenweise |
| FLAC / Ogg / Opus Vorbis Comments | `RATING`, `POPULARITY` | häufig `0..5` oder `0..100` | Werte über 5 als Prozent, sonst Sterne |
| FLAC / Ogg / Opus FMPS | `FMPS_RATING` | üblicherweise `0..1` | mit 5 multiplizieren |
| MP4 / M4A | proprietäre Rating-/iTunes-Felder | nicht einheitlich | nur nach erkanntem Feldschema; sonst kein Schreibkandidat |
| WAV / AIFF | ID3 oder proprietäre Chunks | nicht einheitlich | nur bei eindeutig erkanntem Schema |
| CSV / JSON | explizites Schema | Sterne oder Prozent | entsprechend deklarierter Quelle |

Mehrere Rating-Felder in derselben Datei erzeugen einen Konflikt, solange keine konfigurierbare Quellenpriorität festgelegt ist. Unbekannte oder widersprüchliche Werte dürfen nicht automatisch geschrieben werden.

## Entscheidung API oder direkter DB-Zugriff

Lokal dokumentiert ist `SYNO.AudioStation.Song.setrating` mit den Parametern `id` und `rating`. Ein Parameter für Zielbenutzer oder Benutzer-ID ist nicht dokumentiert. Damit ist aktuell nur eine Bewertung im Kontext der angemeldeten Sitzung plausibel, nicht das Schreiben für andere Benutzer.

`rating_track(userid, track, star)` aus `pg.php` belegt dagegen explizit benutzerbezogene Speicherung.

Aktuelle Entscheidung:

- Der erforderliche Anwendungsfall ist ein einziger Paketdienst unter einem Systemkonto, der Bewertungen für mehrere ausgewählte DSM-Benutzer schreibt. Ein Betrieb des Dienstes mit eigener Sitzung je Benutzer ist nicht vorgesehen.
- Der API-Weg ist für diesen Anwendungsfall nur geeignet, wenn ein Request unter einer administrativen beziehungsweise System-Sitzung einen expliziten Zielbenutzer akzeptiert.
- Die Paketquellen von Audio Station `7.2.0-5516` bestätigen, dass die offizielle UI bei `setrating` ausschließlich `id` und `rating` sendet. `libaudioui.so` verwendet `APIRequest::GetLoginUID()` und führt Rating-Abfragen und -Schreibvorgänge gegen `rating_track.userid` aus.
- Weder in den API-Deskriptoren noch in der offiziellen UI wurde ein Zielbenutzer-Parameter oder eine alternative administrative Rating-Methode gefunden. Der API-Weg ist damit für den erforderlichen Multi-User-Systemdienst nicht geeignet.
- Der direkte Zugriff auf `rating_track(userid, track, star)` ist der vorgesehene Schreibweg.
- Direkter DB-Zugriff bleibt bis zur technischen Prüfung standardmäßig deaktiviert.
- DB-Schreiben wird erst implementiert, wenn Schema, PostgreSQL-Authentifizierung, Transaktionsverhalten, Sperren, Backup und Verhalten nach Audio-Station-Updates geprüft sind.

### Statischer Nachweis aus den Paketquellen

Die untersuchten Paketdateien liegen unter `syno_api_doc/sources/AudioStation/`. Relevante Befunde:

- `target/webapi/AudioStation.api` führt `setrating` für API-Version 2 und 3 und keine alternative administrative Rating-Methode.
- Die offizielle UI ruft `setrating` nur mit `api`, `method`, `id` und `rating` auf.
- `target/lib/libaudioui.so` importiert `APIRequest::GetLoginUID()` und enthält die Rating-Abfragen und -Schreibanweisungen mit `rating_track.userid`.
- `target/scripts/dbupgrade/mediaserver/mediaserver.pgsql` belegt Tabelle, Primärschlüssel, Indizes und Fremdschlüssel.
- `target/etc/pgbouncer.ini` verbindet die Datenbank `mediaserver` über den PostgreSQL-Systemsocket als DB-Rolle `AudioStation` und stellt einen paketlokalen Socket unter `/run/AudioStation` bereit.
- Der paketlokale PGBouncer verwendet `pool_mode=transaction`, `auth_type=any` und einen Socket mit Modus `0700` für `AudioStation:AudioStation`.
- `pkg-AudioStation-pgbouncer.service` läuft als `root`, erzeugt `/run/AudioStation` und übergibt das Verzeichnis an `AudioStation:AudioStation`.
- Die Paketressourcen lassen für Audio Station einen PostgreSQL-Benutzer anlegen und gewähren ihm die Gruppe `MediaIndex`.
- Die mitgelieferten DB-Upgradeskripte verwenden auf DSM `/usr/bin/psql`; dieser Pfad ist damit der erste konkret zu prüfende Clientpfad.

Damit ist ein passwortloser interner DB-Zugang für Audio Station belegt. Nicht belegt ist, dass das separate Paketkonto von AV ImgData den Socket öffnen oder die DB-Rolle `AudioStation` verwenden darf. Vor einer Implementierung sind deshalb auf dem NAS rein lesend zu prüfen:

1. tatsächlicher `psql`-Pfad und Erreichbarkeit des Sockets,
2. Zugriff als Audio-Station-Paketkonto und als AV-ImgData-Paketkonto,
3. effektive DB-Rolle und Rechte auf `track` und `rating_track`,
4. Zuordnung der DSM-Benutzer zu `rating_track.userid`,
5. Sichtbarkeit einer kontrollierten DB-Änderung in Audio Station sowie notwendige Cache-/Index-Aktualisierung.

Eine dauerhafte Aufnahme des AV-ImgData-Paketkontos in die Gruppe `AudioStation`, die Nutzung der DB-Rolle `AudioStation` oder eine Ausführung als `root` wird nicht vorausgesetzt. Dafür ist zunächst ein minimales Berechtigungsmodell zu entwerfen und zu prüfen.

Ein erster Laufzeittest zeigt, dass der Audio-Station-PGBouncer den PostgreSQL-Startup-Parameter `options` und damit `PGOPTIONS=-c default_transaction_read_only=on` ablehnt. Rein lesende Diagnoseläufe müssen deshalb nach dem Verbindungsaufbau explizit `BEGIN TRANSACTION READ ONLY` ausführen und mit `ROLLBACK` enden. Vor dem Wechsel zum Betriebssystemkonto `AudioStation` ist außerdem in ein für dieses Konto zugängliches Verzeichnis wie `/tmp` zu wechseln.

Ein anschließender rein lesender Laufzeittest über `/run/AudioStation` bestätigt:

- Das Betriebssystemkonto `AudioStation` verbindet sich als DB-Rolle `AudioStation` mit `mediaserver`.
- `BEGIN TRANSACTION READ ONLY` setzt `transaction_read_only` wirksam auf `on`.
- Die Rolle darf `track` und `rating_track` lesen.
- Die Rolle besitzt `INSERT`-, `UPDATE`- und `DELETE`-Rechte auf `rating_track`.
- Vorhandene Bewertungszeilen wurden für die Benutzer-IDs `1027`, `1036` und `1037` gefunden.

Damit ist der interne Audio-Station-DB-Weg technisch bestätigt. Noch nicht bestätigt ist der Zugriff vom separaten AV-ImgData-Paketkonto auf den geschützten PGBouncer-Socket. Außerdem müssen die gefundenen numerischen IDs eindeutig DSM-Benutzern zugeordnet werden.

Der anschließende Paketgrenzen-Test bestätigt:

- Das Konto `AV_ImgData` besitzt eine eigene UID und gehört nur zu `AV_ImgData` und `synopkgs`.
- `/run/AudioStation` hatte zur Laufzeit Modus `0755`; der eigentliche Socket `/run/AudioStation/.s.PGSQL.5432` hatte Modus `0700` und gehörte `AudioStation:AudioStation`.
- Ein Verbindungsversuch als Betriebssystemkonto `AV_ImgData` wurde bereits beim Öffnen des Unix-Sockets mit `Permission denied` abgewiesen.

Der aktuelle AV-ImgData-Dienst kann deshalb nicht direkt auf die Audio-Station-Datenbank zugreifen. Ein DB-Schreibweg benötigt eine ausdrücklich entworfene Berechtigungsbrücke. Das Ändern der Laufzeit-Socketrechte, eine dauerhafte privilegierte Ausführung des gesamten Dienstes oder eingebettete DB-Zugangsdaten sind keine akzeptablen Standardlösungen.

Neue Erkenntnisse werden in `syno_api_doc` als YAML unter `api-spec/` beziehungsweise `runtime.observations.yaml` dokumentiert, anschließend mit `tools/validate_yaml.py` geprüft und die Markdown-Dokumentation generiert.

## Gemeinsame Musikordner und Scan

Der Musikscan arbeitet ausschließlich auf konfigurierten gemeinsamen Musikordnern, initial `music`. Weitere Shared-Folder-Namen können konfiguriert werden. Persönliche Home-Verzeichnisse sind nicht automatisch Teil des Scans.

Der Scan erhält analog zu den Foto-Prüfungen `changed_since_days`:

- `0`: vollständiger Scan
- `> 0`: nur Dateien, deren `mtime` innerhalb des Zeitfensters liegt
- spätere Erweiterung: Metadaten- oder Indexänderungszeit berücksichtigen, wenn diese belastbar verfügbar ist

## Optionaler Live-Dienst

Ein optionaler Hintergrunddienst soll auf Änderungen in den konfigurierten gemeinsamen Musikordnern reagieren. Er ist standardmäßig deaktiviert.

Vorgesehene Eigenschaften:

- DSM-Paketdienst, kein Prozess aus der Webanfrage
- rekursive Beobachtung der gemeinsamen Musikordner
- Debounce und Zusammenfassung schneller Änderungsfolgen
- nur unterstützte Audio-Endungen
- Verarbeitung über dieselbe Scan-/Normalisierungspipeline
- persistente Warteschlange und Fehlerstatus
- Fallback auf periodischen Änderungstage-Scan, falls Dateisystem-Watching nicht verfügbar ist
