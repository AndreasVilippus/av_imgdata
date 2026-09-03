# Konzept: DSM-Hilfe für ImgData

## Statusentscheidung

Die Integration von ImgData in das DSM-Hilfe-Center wird vorerst **nicht ausgeliefert**. Die fachliche Dokumentation bleibt erhalten, wird aktuell aber nur für die öffentliche Dokumentation genutzt.

Grund ist nicht die DSM-Laufzeitunterstützung selbst, sondern der öffentlich verfügbare Buildpfad für den Help-Suchindex: Synology dokumentiert weiterhin `helptoc.conf`, `help/<locale>/` und `texts/<locale>/strings` sowie die Resource `indexdb.help-index`. Für eine vollständige Einbindung in die zentrale DSM-Hilfe-Suche wird jedoch ein vorgebautes `helpindexdb` benötigt.

## Vorgesehene DSM-Integration

Bei einer späteren Aktivierung soll die Paketstruktur so aussehen:

```text
target/
├── ui/
│   ├── helptoc.conf
│   ├── help/
│   │   ├── ger/
│   │   └── enu/
│   └── texts/
│       ├── ger/strings
│       └── enu/strings
└── indexdb/
    └── helpindexdb/
```

`INFO.sh` enthält dafür bereits die passende App-Identität und das UI-Verzeichnis:

```sh
dsmappname="SYNO.SDS.App.AV_ImgData.Instance"
dsmuidir="ui"
```

Die Resource-Registrierung wäre bei vollständigem Build:

```json
"indexdb": {
  "help-index": {
    "conf-relpath": "ui/helptoc.conf",
    "db-relpath": "indexdb/helpindexdb"
  }
}
```

Der Ablauf wäre damit:

```text
docs/core/de + docs/core/en
        ↓
DSM-Renderer
        ↓
ui/helptoc.conf + ui/help/* + ui/texts/*
        ↓
Synology Help-Indexer
        ↓
indexdb/helpindexdb
        ↓
SPK
        ↓
indexdb.help-index registriert den Index beim Paketstart
```

## Problem mit dem DSM-7.4-Toolkit

Das DSM-7.4-Build-Environment enthält weiterhin `/usr/syno/bin/indexer.php` und die zugehörigen Module. Gleichzeitig verwendet das von `EnvDeploy` erzeugte Build-Environment PHP 8.4.

Der mitgelieferte Indexer enthält jedoch noch Konstruktoren im alten PHP-Stil, beispielsweise:

```php
class AppHelpToc {
    public function AppHelpToc($tocpath) {
        ...
    }
}
```

Auch `IndexFinder`, `HelpIndexer` und `AppIndexer` verwenden dieses Muster. Unter PHP 8 werden diese Methoden nicht mehr als Konstruktoren ausgeführt. Ein Testlauf im DSM-7.4-Chroot führte deshalb zu nicht initialisierten Pfaden, fehlenden Locales und einem unbrauchbaren Help-Index.

Der öffentliche Synology Package Developer Guide ist zudem weiterhin auf DSM 7.2.2 ausgerichtet. Im DSM7.4-Branch von `pkgscripts-ng` wurde kein neuer Help-Indexer, kein PHP-7-Wrapper und kein automatischer Help-Index-Buildhook gefunden. Ebenso gibt es dort keinen dokumentierten Ersatz für `indexer.php`.

Damit ist für DSM 7.4 derzeit kein ausreichend belastbarer, öffentlich dokumentierter Third-Party-Buildweg für `helpindexdb` vorhanden.

## Entscheidung

ImgData patcht das Synology-Toolkit **nicht** und installiert auch keine alte PHP-Version in das DSM-7.4-Build-Environment.

Bis Synology einen belastbaren aktuellen Buildweg dokumentiert oder ein kompatibles Tool bereitstellt, gilt:

- kein `ui/helptoc.conf` im SPK,
- keine generierten `ui/help/*`-Dateien im SPK,
- kein `indexdb/helpindexdb`,
- kein `indexdb.help-index` in `conf/resource`,
- kein Aufruf von `indexer.php` im Paketbuild,
- keine DSM-Help-spezifischen Buildtests.

Die Recherche und die geplante Zielstruktur bleiben in diesem Konzept dokumentiert, damit die Integration später ohne erneute Grundsatzanalyse wieder aufgenommen werden kann.

## Bedingungen für eine spätere Reaktivierung

Die DSM-Hilfe darf erst wieder aktiviert werden, wenn mindestens eine der folgenden Bedingungen erfüllt ist:

1. Synology dokumentiert einen DSM-7.4+-kompatiblen Third-Party-Workflow zur Erzeugung von `helpindexdb`.
2. Das offizielle Toolkit liefert einen mit seiner PHP-Version kompatiblen Indexer.
3. Ein alternativer offizieller Mechanismus ersetzt `indexer.php`.

Vor einer Reaktivierung muss ein vollständiger Pakettest nachweisen, dass das SPK startet und dass `SYNO.Core.UISearch` die ImgData-Hilfe tatsächlich findet.
