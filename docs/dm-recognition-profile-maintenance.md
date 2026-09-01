# Design Memo: Inkrementelle Pflege und Erweiterung von Recognition-Profilen

## Status

Konzept / Design Memo

## Ziel

Personenprofile der Gesichtserkennung sollen nicht ausschließlich durch einen vollständigen Lauf von `recognition_build_profiles` erzeugt oder erneuert werden. Bestehende Profile sollen gezielt und inkrementell um geeignete Referenzgesichter erweitert bzw. optimiert werden können.

Auslöser können insbesondere sein:

- eine neue manuelle Zuweisung eines Gesichts zu einer Person,
- neue Bilder einer bereits bekannten Person,
- Profile mit zu wenigen oder qualitativ schwachen Referenzen,
- erkannte Outlier oder geringe Diversität,
- Änderungen an Personenzuweisungen,
- Zusammenführungen oder Umstrukturierungen von Personen,
- eine gezielte Benutzeraktion für ausgewählte Profile.

Das Ziel ist ausdrücklich nicht, möglichst viele Gesichter in ein Profil aufzunehmen. Stattdessen soll für jede Person eine begrenzte, qualitativ gute und möglichst diverse Referenzmenge gepflegt werden.

---

## 1. Begriffe und Datenebenen

Für jede Person werden drei Ebenen unterschieden.

### 1.1 Zugewiesene Gesichter

Alle Gesichter, die Synology Photos aktuell einer Person zuordnet.

Diese Menge kann klein oder sehr groß sein und ist nicht identisch mit dem Recognition-Profil.

### 1.2 Profilkandidaten

Gesichter, die grundsätzlich als Referenz geeignet sein könnten.

Typische Ausschlussgründe:

- zu kleines Gesicht,
- schlechte Detection-Qualität,
- unscharfe oder stark verdeckte Aufnahme,
- offensichtlicher Outlier,
- nahezu identische Serienaufnahme,
- technisch ungeeignete Bounding Box.

### 1.3 Aktive Referenzgesichter

Eine begrenzte Auswahl der besten Kandidaten bildet das produktive Recognition-Profil.

Der bereits vorhandene Parameter `max_profile_reference_faces_per_person` soll dafür weiterverwendet werden.

Beispielzustand:

```json
{
  "person_id": 4711,
  "assigned_faces": 238,
  "candidate_faces": 91,
  "reference_faces": 18,
  "profile_quality": 0.87,
  "profile_diversity": 0.79
}
```

Ein neu zugewiesenes Gesicht wird daher nicht automatisch zu einer dauerhaften Profilreferenz. Es wird zunächst Kandidat.

---

## 2. Dirty-State für Personenprofile

Profile benötigen einen persistenten Änderungszustand.

Minimal:

```json
{
  "profile_dirty": true,
  "profile_dirty_reason": "person_assignment_changed",
  "profile_dirty_since": "...",
  "profile_revision": 17
}
```

Mögliche Zustände:

- `clean`
- `dirty`
- `queued`
- `processing`
- `review`
- `error`

Der zentrale Vorteil besteht darin, dass eine Änderung der Personenzuweisung keinen unmittelbaren vollständigen Recognition-Lauf starten muss. Die betroffene Person wird lediglich als aktualisierungsbedürftig markiert.

Mehrere Änderungen derselben Person werden dadurch automatisch zusammengefasst.

---

## 3. Trigger bei neuer Personenzuweisung

Nach erfolgreicher Änderung einer Zuweisung in Synology Photos wird die betroffene Person markiert:

```text
assignment_changed(person_id=1234)
        ↓
mark_person_profile_dirty(
    person_id=1234,
    reason="new_face_assignment"
)
```

Diese Operation muss billig bleiben.

Insbesondere darf der interaktive Zuweisungsvorgang nicht darauf warten, dass InsightFace das Bild erneut analysiert oder das Profil vollständig neu berechnet.

---

## 4. Fast Path bei bereits vorhandenem Embedding

Ist das Embedding des neu zugewiesenen Gesichts bereits vorhanden, kann unmittelbar eine billige Kandidatenbewertung erfolgen.

Beispiel:

```text
neue Zuweisung
    ↓
Embedding bereits im Cache
    ↓
Similarity / Quality / Diversity prüfen
    ↓
Kandidat vormerken
```

Das Profil bleibt dennoch `dirty`, weil die optimale Referenzmenge gegebenenfalls neu bewertet werden muss.

---

## 5. Kein blindes Anhängen neuer Referenzen

Die Logik muss ausdrücklich verhindern, dass jede neue Zuweisung dauerhaft in das Recognition-Profil aufgenommen wird.

Stattdessen:

```text
neues Gesicht
    ↓
Candidate Pool
    ↓
Qualitätsbewertung
    ↓
Ähnlichkeitsprüfung
    ↓
Diversitätsbewertung
    ↓
optimale Referenzmenge
```

Ein neuer Kandidat kann daher auch eine bestehende Referenz ersetzen.

Beispiel:

```text
vorher:
A B C D

neuer Kandidat:
E

nach Ranking:
A B C E
```

---

## 6. Profilqualität

Die GUI sollte nicht nur die Anzahl der Referenzen darstellen, sondern den Zustand des Profils.

Sinnvolle Kennzahlen:

- Anzahl zugewiesener Gesichter,
- Anzahl analysierter Kandidaten,
- Anzahl aktiver Referenzen,
- Qualitätswert,
- Diversitätswert,
- Anzahl möglicher Outlier,
- Anzahl neuer, noch nicht verarbeiteter Gesichter,
- Zeitpunkt der letzten Aktualisierung.

Beispiel:

```text
Anna
238 zugewiesene Gesichter
18 aktive Referenzen
Qualität: sehr gut
Diversität: gut
Profil aktuell
```

oder:

```text
Peter
7 zugewiesene Gesichter
3 aktive Referenzen
Qualität: niedrig
Hinweis: zu wenige Referenzen
```

---

## 7. Neue GUI-Liste für Recognition-Profile

Eine eigene Profilübersicht bietet sich an.

| Person | Gesichter | Referenzen | Qualität | Zustand | Hinweis |
|---|---:|---:|---|---|---|
| Anna | 238 | 18 | sehr gut | aktuell | – |
| Peter | 7 | 3 | niedrig | aktualisieren | wenige Referenzen |
| Maria | 143 | 22 | mittel | prüfen | mögliche Outlier |
| Max | 42 | 11 | gut | aktualisieren | 4 neue Bilder |

Sinnvolle Filter:

- Alle
- Aktualisierung erforderlich
- Schwache Profile
- Zu wenige Referenzen
- Neue Kandidaten
- Outlier
- Fehler

Aktionen:

- Profil aktualisieren
- Ausgewählte Profile aktualisieren
- Weitere Referenzen suchen
- Referenzen anzeigen
- Profil vollständig neu erstellen

---

## 8. Revisionen und Änderungsverfolgung

Ein Profil sollte erkennen können, ob sich seine Quellen geändert haben.

Beispiel:

```json
{
  "last_profile_build": "...",
  "profile_revision": 12,
  "source_revision": 15
}
```

Wenn `source_revision > profile_revision`, ist das Profil veraltet.

Alternativ oder ergänzend können bekannte Face-IDs persistiert werden. Dann müssen nur neue oder entfernte Faces erneut betrachtet werden.

---

## 9. Persistenter Embedding-Cache

Der wichtigste Performancebaustein ist ein dauerhaft nutzbarer Embedding-Cache.

Für jedes analysierte Gesicht sollte mindestens gespeichert werden:

```json
{
  "face_id": "...",
  "image_id": "...",
  "model_key": "...",
  "embedding": "...",
  "quality": 0.91,
  "bbox": {},
  "analyzed_at": "..."
}
```

Der bestehende modellabhängige Schlüssel des Recognition-Service soll weiterverwendet werden.

Damit gilt:

```text
gleiches Face
+ gleicher model_key
→ kein erneutes Embedding notwendig
```

Bei Modell- oder relevanter Parameteränderung wird ein anderer Cache-Namespace verwendet.

Der Cache muss konzeptionell getrennt sein von:

1. Face Embeddings,
2. Person Candidate State,
3. aktivem Recognition-Profil.

Diese Trennung ermöglicht spätere Änderungen an Ranking oder maximaler Referenzzahl ohne erneute Bildanalyse.

---

## 10. Zwei Aktualisierungsarten

### 10.1 Incremental Update

Normalfall.

Nur neue oder geänderte Gesichter werden analysiert.

```text
bestehendes Profil
      +
neue Kandidaten
      ↓
Referenzmenge neu optimieren
```

Typische Auslöser:

- neue manuelle Zuweisung,
- wenige neue Bilder,
- einzelne geänderte Face-Zuordnungen.

### 10.2 Full Rebuild

Nur bei größeren strukturellen Änderungen.

Typische Gründe:

- Modellwechsel,
- relevante Detection-Parameter geändert,
- Profil beschädigt,
- Personen zusammengeführt,
- starke Inkonsistenz,
- explizite Benutzeraktion.

Der vorhandene Parameter `rebuild_all` soll dafür weiterverwendet werden.

---

## 11. Ranking neuer Kandidaten

Die Auswahl neuer Referenzen sollte mehrere Faktoren berücksichtigen.

Konzeptionell:

```text
candidate_score =
    quality
  + profile_similarity
  + diversity_gain
  + assignment_confidence
```

Die genaue mathematische Gewichtung ist später separat festzulegen.

### Quality

Zum Beispiel:

- Größe des Gesichts,
- Detection confidence,
- Beschnitt,
- Pose,
- technische Verwendbarkeit.

### Profile Similarity

Ein Kandidat muss zum bestehenden Profil passen.

Sehr geringe Ähnlichkeit deutet auf einen möglichen Outlier hin.

### Diversity Gain

Nahezu identische Aufnahmen sollen kaum zusätzlichen Wert erzeugen.

Gesichter mit anderer Perspektive, anderem Alter, anderer Beleuchtung oder anderen relevanten Erscheinungsmerkmalen können dagegen einen hohen Informationsgewinn haben.

---

## 12. Semantik manueller Zuweisungen

Eine manuelle Benutzerzuweisung sollte als bestätigte Personenzuordnung gelten:

```text
confirmed_assignment = true
```

Sie bedeutet jedoch nicht automatisch, dass das Gesicht eine gute Recognition-Referenz ist.

Ein korrekt zugeordnetes, aber sehr kleines oder unscharfes Gesicht darf daher bei der Person verbleiben, ohne in deren aktive Referenzmenge aufgenommen zu werden.

---

## 13. Weitere Referenzen gezielt suchen

Für Profile mit wenigen oder schwachen Referenzen sollte es eine Aktion geben:

```text
Weitere geeignete Referenzen suchen
```

Dabei werden noch nicht bewertete Gesichter dieser Person untersucht.

Bei sehr großen Personenbeständen muss die Suche begrenzt bzw. priorisiert werden.

Beispiel:

```text
2700 zugewiesene Gesichter
    ↓
100 günstige Kandidaten vorselektieren
    ↓
InsightFace Analyse
    ↓
32 gute Kandidaten
    ↓
20 aktive Referenzen
```

---

## 14. Günstige Vorauswahl vor InsightFace

Vor rechenintensiver Analyse können bereits einfache Metadaten genutzt werden.

Bevorzugbar sind zum Beispiel:

- größere Face-Bounding-Boxes,
- noch nicht analysierte Gesichter,
- unterschiedliche Aufnahmezeitpunkte,
- unterschiedliche Bilder statt Serien,
- neue Bilder.

Damit muss nicht jede Person mit tausenden Bildern vollständig durch den Embedder laufen.

---

## 15. Serienbilder und Redundanz

Fast identische Gesichter aus Serienbildern sollen nicht mehrfach als aktive Profilreferenz verwendet werden.

Eine sehr hohe Embedding-Ähnlichkeit kann als Redundanzkriterium dienen.

Optional können zusätzlich Aufnahmezeit und Seriennähe berücksichtigt werden.

---

## 16. Automatische Profilpflege

Die eigentliche Profilpflege soll außerhalb der interaktiven Zuweisung erfolgen.

```text
Benutzer weist Face zu
      ↓
profile_dirty = true
      ↓
Maintenance Queue
      ↓
Profil später aktualisieren
```

Die UI kann zwischenzeitlich anzeigen:

```text
Profilaktualisierung ausstehend
1 neues Gesicht
```

---

## 17. Sofort, verzögert und Batch

Drei Verarbeitungspfade sind sinnvoll.

### Sofort

Wenn alle benötigten Embeddings bereits existieren, können billige Profiloperationen unmittelbar durchgeführt werden.

### Kurz verzögert

Wenn neue Embeddings berechnet werden müssen, wird die Person lediglich in die Maintenance Queue eingereiht.

### Batch Maintenance

Bei mehreren dirty Profiles werden fehlende Embeddings gesammelt und möglichst gebündelt verarbeitet.

Dies ist insbesondere für den External Worker relevant.

---

## 18. External Worker

Die vorhandene Worker-Architektur soll unverändert genutzt werden.

Der DSM-Backendprozess bleibt zuständig für:

- Synology Photos API,
- Ermittlung betroffener Personen,
- Dirty-State,
- Queue,
- Profilstatus,
- Findings und Review,
- Persistierung und Mutation.

Der External Worker übernimmt ausschließlich Processor-Aufgaben:

- Face Detection,
- Embedding,
- Embedding Batch,
- Ranking,
- Profilmathematik.

Relevante vorhandene Processor-Contracts:

- `face_native_embed`
- `face_native_embed_batch`
- `face_native_rank_embeddings`
- `face_native_profile_math`

Damit bleibt DSM die Source of Truth und der Worker kennt keine Synology-spezifische Profilsemantik.

---

## 19. Worker-Nutzung bei größerer Last

Gerade die inkrementelle Profilpflege lässt sich gut bündeln.

Beispiel:

```text
30 dirty Profiles
je 5 neue Bilder
= 150 Bilder
```

DSM kann die fehlenden Embeddings in Batches über `face_native_embed_batch` verarbeiten.

Die bereits vorhandenen Optionen `recognition_batch_size` und `external_worker_prefetch_batches` sollen dafür weiterverwendet werden.

Es darf keine zweite Recognition-spezifische Worker-Infrastruktur entstehen.

---

## 20. Abgrenzung zum zukünftigen zentralen Pipeline-Service

Die aktuelle Worker-Architektur besitzt Batch-Verarbeitung, aber noch keinen allgemeinen persistenten Pipeline-Orchestrator für mehrere unabhängige In-Flight-Arbeitseinheiten.

Queue Prefill, persistente Item-Zustände, mehrere unabhängige In-Flight-Jobs, geordnete Ergebnisübernahme und Cancellation gehören weiterhin in den geplanten zentralen Pipeline-Service.

Die Profilpflege soll deshalb zunächst keine konkurrierende eigene Pipeline implementieren.

Sie soll so strukturiert werden, dass sie später als Consumer des zentralen Pipeline-Service betrieben werden kann.

---

## 21. Subprozess vs. Cron

### Subprozess als Trigger: nicht verwenden

Ein eigener Prozess pro Zuweisung würde zu Problemen führen:

- mehrere Prozesse für dieselbe Person,
- keine Deduplizierung,
- schwieriges Recovery,
- unnötiges Modellladen,
- schwer kontrollierbare Parallelität.

Ein Subprozess kann Teil der eigentlichen Processor-Ausführung bleiben, aber nicht Scheduling-Mechanismus der Profilpflege sein.

### Cron als alleiniger Mechanismus: ebenfalls nicht verwenden

Ein reiner Cron-Lauf wäre zwar robust, reagiert aber unnötig träge und müsste wiederholt nach Änderungen suchen, die beim Assignment bereits bekannt sind.

### Empfohlene Architektur

```text
Assignment / Änderung
        ↓
persistenter Dirty-State
        ↓
deduplizierte Maintenance Queue
        ↓
Background Maintenance Runner
        ↓
Local Processor / External Worker

Cron
  ↓
nur Watchdog / Recovery / Safety Net
```

Cron ist damit nicht der eigentliche Prozessor.

---

## 22. Cron als Watchdog

Ein periodischer Maintenance-Job kann beispielsweise alle 15 oder 30 Minuten prüfen:

- dirty, aber nicht queued,
- lange queued,
- lange processing,
- Retry fällig,
- inkonsistente Zustände.

Er analysiert nicht pauschal alle Personen.

Damit übernimmt Cron ausschließlich Recovery und periodischen Maintenance-Anstoß.

---

## 23. Deduplizierung

Mehrere Änderungen derselben Person dürfen nur einen Queue-Eintrag erzeugen.

Nicht:

```text
Anna Job 1
Anna Job 2
Anna Job 3
```

sondern:

```text
Anna
profile_dirty = true
pending_changes = 3
```

Technisch bietet sich ein `UPSERT` pro `person_id` an.

---

## 24. Debounce

Manuelle Serienzuweisungen sollen automatisch gebündelt werden.

Beispiel:

```text
15:01:02 Änderung Anna
15:01:04 Änderung Anna
15:01:08 Änderung Anna
15:01:11 Änderung Anna
```

Der Runner startet erst, wenn beispielsweise für einige Sekunden keine neue Änderung erfolgt ist.

Dadurch wird Anna nur einmal verarbeitet.

---

## 25. Prioritäten

Mögliche Priorisierung:

- 100: explizites „Profil jetzt aktualisieren“
- 80: neue manuelle Personenzuweisung
- 50: automatisch erkannte Profiländerung
- 20: periodische Qualitätsoptimierung

Interaktive Benutzeraktionen werden dadurch bevorzugt abgearbeitet.

---

## 26. Persistenter Profilzustand

Der bestehende Recognition Runtime State sollte um Maintenance-Informationen erweitert werden.

Beispiel:

```json
{
  "person_id": 4711,
  "references": [],
  "profile_revision": 18,
  "quality": {
    "score": 0.87,
    "reference_count": 18,
    "diversity": 0.81,
    "outliers": 0
  },
  "maintenance": {
    "dirty": false,
    "dirty_since": null,
    "last_updated": "...",
    "last_full_rebuild": "...",
    "last_reason": "new_face_assignment"
  }
}
```

---

## 27. Persistente Maintenance Queue

Eine kleine deduplizierte Queue ist sinnvoll.

Beispiel:

```json
{
  "person_id": 4711,
  "reason": "assignment_changed",
  "created_at": "...",
  "updated_at": "...",
  "priority": 80,
  "attempt": 0,
  "state": "pending"
}
```

`person_id` muss logisch eindeutig sein.

Neue Änderungen aktualisieren denselben Eintrag.

---

## 28. Fehlerverhalten

Worker-Ausfälle oder Processor-Fehler dürfen kein bestehendes Profil zerstören.

Bei Fehler:

```text
profile bleibt dirty
state = retry
attempt += 1
last_error = ...
```

Das bisher aktive Profil bleibt weiter verwendbar.

---

## 29. Atomare Profilaktivierung

Profilupdates sollten revisioniert berechnet und erst nach vollständigem Erfolg aktiviert werden.

```text
aktive Revision 17
      ↓
Revision 18 berechnen
      ↓
alles erfolgreich?
  ja → Revision 18 aktivieren
  nein → Revision 17 bleibt aktiv
```

Damit existieren keine halb aktualisierten produktiven Profile.

---

## 30. Entfernen oder Verschieben einer Zuweisung

Wird ein Gesicht von Anna zu Maria verschoben, werden beide Profile dirty:

```text
Anna: reason = face_removed
Maria: reason = face_added
```

Beide Profile werden anschließend inkrementell aktualisiert.

---

## 31. Personenzusammenführung

Bei einer Zusammenführung sollte ein vollständiger Neuaufbau markiert werden:

```text
dirty_mode = full
```

weil sich große Teile des Kandidatenbestands ändern können.

---

## 32. Löschen einer Person

Beim Löschen einer Person werden entfernt:

- aktives Recognition-Profil,
- personenspezifischer Candidate State,
- offener Maintenance-Eintrag.

Globale Face-Embeddings können bestehen bleiben, wenn sie als generischer Cache modelliert sind.

---

## 33. Re-Ranking ohne Re-Embedding

Die Trennung zwischen Embedding-Cache und Profilreferenzen ermöglicht spätere Änderungen der Profilstrategie ohne neue Bildanalyse.

Beispiel:

```text
max references: 20 → 30
```

Dann genügt:

```text
cached embeddings
      ↓
profile math / ranking
      ↓
neue Referenzmenge
```

Hierfür kann der vorhandene Contract `face_native_profile_math` genutzt werden.

---

## 34. Profildetailansicht

Eine Detailansicht kann beispielsweise zeigen:

```text
Anna

Profilqualität: 87 %
18 aktive Referenzen
238 zugewiesene Gesichter
12 weitere analysierte Kandidaten
4 neue, noch nicht analysierte Gesichter

Status: Aktualisierung empfohlen
```

Aktionen:

- Profil aktualisieren
- Weitere Referenzen suchen
- Referenzen anzeigen
- Vollständig neu erstellen

---

## 35. Referenzansicht

Aktive Referenzen und Kandidaten sollten visuell unterscheidbar sein.

Mögliche Kennzeichnung:

- aktive Referenz,
- geeigneter Kandidat,
- möglicher Outlier,
- ungeeignet.

Zusätzliche Werte:

- Quality,
- Similarity,
- Diversity,
- Source.

Damit wird die Profilbildung nachvollziehbar und kontrollierbar.

---

## 36. Konfiguration

Mögliche neue Einstellungen:

```json
{
  "recognition": {
    "PROFILE_AUTO_UPDATE_ON_ASSIGNMENT": true,
    "PROFILE_MAINTENANCE_ENABLED": true,
    "PROFILE_MAINTENANCE_DEBOUNCE_SECONDS": 15,
    "PROFILE_MAINTENANCE_BATCH_PERSONS": 10,
    "PROFILE_MAX_NEW_CANDIDATES_PER_RUN": 50
  }
}
```

Bestehende Parameter wie diese sollen weiterhin genutzt werden:

- `RECOGNITION_MAX_PROFILE_REFERENCE_FACES_PER_PERSON`
- `RECOGNITION_MIN_FACES_PER_PERSON`
- `recognition_batch_size`
- `external_worker_prefetch_batches`

Es sollen keine parallelen Konfigurationskonzepte für dieselbe Semantik entstehen.

---

## 37. Zielablauf bei manueller Zuweisung

```text
1. Benutzer weist Gesicht einer Person zu
                ↓
2. Synology-Zuweisung erfolgreich
                ↓
3. mark_person_profile_dirty(person_id)
                ↓
4. vorhandenes Embedding ggf. sofort bewerten
                ↓
5. Maintenance Queue / Debounce
                ↓
6. Kandidaten bestimmen
                ↓
7. fehlende Embeddings bestimmen
                ↓
8. External Worker bevorzugen
   face_native_embed_batch
                ↓
9. Embeddings speichern
                ↓
10. Quality / Outlier / Diversity bewerten
                ↓
11. optimale Referenzmenge bestimmen
                ↓
12. neue Profilrevision erzeugen
                ↓
13. atomar aktivieren
                ↓
14. dirty = false
```

---

## 38. Zentrale interne API

Konzeptionell sollten wenige klar getrennte Service-Funktionen entstehen:

```python
mark_person_profile_dirty(
    person_id,
    reason,
    force_full_rebuild=False,
)
```

```python
refresh_person_profile(
    person_id,
    mode="incremental",
)
```

```python
refresh_dirty_profiles(
    limit=10,
)
```

Interne Schritte:

```text
collect_profile_candidates
load_cached_embeddings
embed_missing_candidates
rank_profile_candidates
build_profile
commit_profile
```

---

## 39. Wiederverwendung durch `recognition_build_profiles`

Langfristig sollte auch der bestehende vollständige Profilbuild dieselbe zentrale Profilbildungslogik verwenden.

Statt eines separaten vollständigen Codepfads:

```text
recognition_build_profiles
      ↓
Personen auswählen
      ↓
refresh_person_profile(...)
```

Die verschiedenen Workflows unterscheiden sich dann nur noch in der Auswahl der Personen und dem Modus:

- alle Profile,
- dirty Profiles,
- ausgewählte Profile,
- einzelne Person,
- incremental,
- full.

---

## 40. Keine direkte UI-Worker-Kopplung

Die Architektur bleibt:

```text
UI
 ↓
DSM Recognition Service
 ↓
Profile Maintenance
 ↓
Processor Dispatch
 ↓
Local / External Worker
```

Nicht:

```text
UI → External Worker
```

Der Worker erhält ausschließlich technische Processor-Aufträge.

---

## 41. Übergang zum zentralen Pipeline-Service

Die Profilpflege ist ein geeigneter späterer Consumer des geplanten zentralen Pipeline-Service.

Heute:

```text
Profile Queue
    ↓
Maintenance Runner
    ↓
Batch Worker Call
```

Später:

```text
Central Pipeline

Stage 1: Candidate Discovery
Stage 2: Embedding Batches
Stage 3: Profile Math
Stage 4: Commit
```

Die erste Implementierung sollte deshalb keine Recognition-spezifische Pipeline-Infrastruktur schaffen, die später wieder entfernt werden müsste.

---

## 42. Empfohlene Implementierungsphasen

### Phase 1: Profilstatus

Einführen:

- dirty,
- dirty_reason,
- last_updated,
- source revision,
- profile revision,
- Profilübersicht in der GUI.

### Phase 2: gezielte Aktualisierung

Implementieren:

```text
refresh_person_profile(person_id)
```

und GUI-Aktionen für einzelne bzw. ausgewählte Profile.

### Phase 3: Assignment Trigger

Nach erfolgreicher Änderung einer Personenzuweisung:

```text
mark_person_profile_dirty(...)
```

### Phase 4: automatische Maintenance

Einführen:

- Debounce,
- Deduplizierung,
- Prioritäten,
- Retry,
- Batch-Verarbeitung.

### Phase 5: Cron Watchdog

Cron prüft ausschließlich Recovery-Zustände und stößt liegen gebliebene Maintenance erneut an.

### Phase 6: erweiterte Profiloptimierung

Danach folgen:

- Diversitätsanalyse,
- Serienbildreduktion,
- zusätzliche Kandidatensuche,
- Profilgesundheit,
- erweiterte Qualitätsbewertung.

---

## 43. Architekturentscheidung

Für die erste Umsetzung gilt:

```text
Cron:
JA, aber nur als Watchdog und Safety Net.

Subprozess:
JA, soweit bereits Teil der Processor-Ausführung,
aber NICHT als Trigger pro Personenzuweisung.

Primärer Mechanismus:
persistenter Dirty-State + deduplizierte Maintenance Queue.
```

Der Assignment-Pfad bleibt dadurch leicht und schnell:

```text
Personenzuweisung
→ Dirty-State setzen
→ fertig
```

Rechenintensive Arbeit läuft kontrolliert im Hintergrund und kann bei Bedarf auf den External Worker ausgelagert werden.

---

## 44. Empfohlener Minimal-Scope

Für eine erste produktiv nutzbare Version sollten sechs Bausteine umgesetzt werden:

1. `profile_dirty` inklusive Grund und Zeitstempel,
2. `refresh_person_profile(person_id)` als zentrale inkrementelle Funktion,
3. persistenter Face-Embedding-Cache,
4. Profil-Liste mit `aktuell / Aktualisierung erforderlich / schwach`,
5. Dirty-Markierung nach erfolgreicher Änderung einer Personenzuweisung,
6. Maintenance Runner mit External-Worker-Batchnutzung und Cron ausschließlich als Watchdog.

Damit entsteht bereits der wesentliche Nutzen, ohne den geplanten zentralen Pipeline-Service vorwegzunehmen.

---

## 45. Zielbild

```text
              PERSON PROFILE
                    │
          ┌─────────┴─────────┐
          │                   │
      Source Faces       Active References
          │                   │
          ▼                   ▼
     Candidates ◀──── Profile Optimizer
          │                   ▲
          │                   │
          └── Embedding Cache ┘
                    │
                    ▼
             Local / Worker
```

Profile werden damit zu kontinuierlich gepflegten Recognition-Artefakten:

- neue manuelle Zuweisungen können sie automatisch verbessern,
- alte oder schwache Profile lassen sich gezielt optimieren,
- Änderungen werden gesammelt statt mehrfach verarbeitet,
- vorhandene Embeddings werden wiederverwendet,
- rechenintensive Operationen können auf den External Worker verlagert werden,
- Cron bleibt auf Recovery und periodischen Maintenance-Anstoß beschränkt.
