# DSM-Hilfe: Referenz aus File Station unter DSM 7.4

## Zweck

Dieses Dokument hält die auf einer realen DSM-7.4-Installation geprüfte File-Station-Hilfestruktur als technische Referenz für die ImgData-Hilfe fest.

Die Referenz ergänzt den Synology Developer Guide um das tatsächlich ausgelieferte Verhalten unter DSM 7.4. Die fachlichen Hilfetexte von File Station werden nicht übernommen; verwendet werden ausschließlich Struktur, Dateiverträge und Darstellungsprinzipien.

---

## 1. Zielplattform

ImgData verwendet inzwischen DSM 7.4 als Mindestziel. Dies ist bereits in `INFO.sh` festgelegt:

```sh
os_min_ver="7.4-00000"
```

Die nachfolgenden File-Station-Beispiele gelten daher als aktuelle Referenz für die Zielplattform des Pakets.

---

## 2. Geprüfter File-Station-Aufbau

Die File-Station-Hilfe befindet sich unter:

```text
/var/packages/FileStation/target/ui/file_browser/
```

Die dortige `helptoc.conf` verwendet unter anderem:

```json
{
  "app": "SYNO.SDS.App.FileStation3.Instance",
  "title": "tree:leaf_filebrowser",
  "content": "FileBrowser_desc.html",
  "helpset": "help",
  "stringset": "texts",
  "toc": []
}
```

Damit sind unter DSM 7.4 folgende Felder praktisch bestätigt:

- `app`
- `title`
- `content`
- `helpset`
- `stringset`
- `toc`
- `nodes`
- optional `disable`

---

## 3. Konsequenz für ImgData `helptoc.conf`

Für ImgData soll der DSM-Renderer folgende Grundstruktur erzeugen:

```json
{
  "app": "SYNO.SDS.App.AV_ImgData.Instance",
  "title": "helptoc:imgdata",
  "content": "index.html",
  "helpset": "help",
  "stringset": "texts",
  "toc": []
}
```

### Quellen

| Feld | Quelle |
|---|---|
| `app` | `INFO.sh:dsmappname` |
| `title` | Documentation-i18n / Navigation |
| `content` | Dokument-ID `index` |
| `helpset` | DSM-Renderer-Konstante `help` |
| `stringset` | DSM-Renderer-Konstante `texts` |
| `toc` | gemeinsame Navigation |

`helpset` und `stringset` sollen im Renderer fest definiert und per Test abgesichert werden.

---

## 4. Gruppenknoten und Unterseiten

File Station bestätigt, dass ein Hauptpunkt gleichzeitig eine eigene Übersichtsseite über `content` und weitere Unterseiten über `nodes` besitzen kann.

Beispielprinzip:

```json
{
  "title": "helptoc:group",
  "content": "group.html",
  "nodes": [
    {
      "title": "helptoc:child_a",
      "content": "child_a.html"
    },
    {
      "title": "helptoc:child_b",
      "content": "child_b.html"
    }
  ]
}
```

Das ist für ImgData insbesondere sinnvoll bei:

- Face Matching
- Checks
- Cleanup
- Gesichtserkennung und Personenprofile
- External Worker
- Externe Bibliotheken
- Datenbanklisten
- Fehlerbehebung

---

## 5. Indexseite als DSM-Startseite

Die File-Station-Startseite verwendet semantisch:

```html
<body>
  <h1>File Station</h1>
  <p>Kurze Beschreibung der Anwendung ...</p>

  <h4><a href="...">Hilfebereich A</a></h4>
  <p>Kurze Beschreibung von Bereich A</p>

  <h4><a href="...">Hilfebereich B</a></h4>
  <p>Kurze Beschreibung von Bereich B</p>
</body>
```

Für ImgData wird dasselbe Muster verwendet.

In der ersten Ausbaustufe bleiben die Einträge bewusst unverlinkt, solange die jeweiligen Unterseiten noch nicht erstellt und freigegeben sind:

```html
<h4>Status</h4>
<p>Überblick über Paketstatus, laufende Vorgänge und wichtige Komponenten.</p>
```

Nach Aktivierung einer Zielseite kann der DSM-Renderer daraus automatisch erzeugen:

```html
<h4><a href="status.html">Status</a></h4>
<p>Überblick über Paketstatus, laufende Vorgänge und wichtige Komponenten.</p>
```

Die redaktionelle Quelle soll dafür keinen festen HTML-Link enthalten müssen.

---

## 6. Keine separate Einführungsseite

Die File-Station-Referenz bestätigt, dass die Root-`content`-Seite selbst Einführung und Übersicht übernehmen kann.

Für ImgData gilt deshalb:

```text
index
= Startseite
= kurze Einführung
= Übersicht der Hilfebereiche
```

Eine separate Seite `introduction` wird vorerst nicht angelegt.

---

## 7. Erste Ebene der ImgData-Hilfe

Aktueller Zielstand:

```text
ImgData
├── Status
├── Face Matching
├── Checks
├── Cleanup
├── Gesichtserkennung und Personenprofile
├── Konfiguration
├── External Worker
├── Externe Bibliotheken
├── Datenbanklisten
├── Vorschau und Review
└── Fehlerbehebung
```

Die Indexseite listet dieselben Bereiche in derselben Reihenfolge.

Zielregel:

```text
Documentation Core Navigation
        =
DSM-Hilfebaum
        =
Indexseiten-Übersicht
```

Der Generator soll diese Konsistenz prüfen.

---

## 8. HTML-Hülle unter DSM 7.4

Die reale File-Station-Seite verwendet:

```html
<!DOCTYPE html>
<html class="img-no-display">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" >
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<link href="../../../../help/help.css" type="text/css" rel="stylesheet" />
<link href="../../../../help/scrollbar/flexcroll.css" type="text/css" rel="stylesheet" />
<script type="text/javascript" src="../../../../help/scrollbar/flexcroll.js"></script>
<script type="text/javascript" src="../../../../help/scrollbar/initFlexcroll.js"></script>
</head>
<body>
  <!-- erzeugter Inhalt -->
</body>
</html>
```

Der ImgData-DSM-Renderer soll sich an diesem tatsächlich ausgelieferten DSM-7.4-Aufbau orientieren.

Eigene Website-CSS- oder JavaScript-Komponenten werden nicht in die DSM-Hilfe übernommen.

---

## 9. Hinweisboxen

File Station verwendet für Hinweise beispielsweise:

```html
<div class="section">
  <h4>Anmerkung:</h4>
  <ul>
    <li>...</li>
  </ul>
</div>
```

Dieses Muster kann später als DSM-Ausgabe für strukturierte Hinweise im Documentation Core verwendet werden.

---

## 10. Aktivierung noch nicht vorhandener Seiten

Während die Hilfetexte schrittweise entstehen, sollen weder Indexseite noch `helptoc.conf` auf nicht vorhandene Dateien verweisen.

Empfohlenes Navigationsmetadatum:

```yaml
- id: status
  title_key: helptoc.status
  dsm:
    enabled: false
```

Solange `enabled: false` gilt:

- wird der Punkt auf der Indexseite nur als Überschrift und Kurzbeschreibung ausgegeben,
- wird noch kein aktiver `toc`-Eintrag erzeugt,
- entsteht kein toter DSM-Hilfe-Link.

Nach Fertigstellung:

```yaml
dsm:
  enabled: true
```

Dann werden Index-Link und `toc`-Eintrag gemeinsam aktiviert.
