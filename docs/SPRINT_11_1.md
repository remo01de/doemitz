# Sprint 11.1 · Brücken auf eigener Höhe (Nachbesserung)

Stand: Umgesetzt und geprüft (vor Sprint 12).

## Befund

Nach Sprint 11 (`0c950f4` auf `main`) lagen die Brücken im Spiel auf Höhe des Wassers bzw. Grabenbodens. Ursache: DGM1 ist ein Geländemodell ohne Bauwerke und liefert unter Brücken den Graben- oder Flussboden. `road_elevation.py` hatte `bridge`-Wege wie normale Straßen auf das Gelände drapiert; die 12-m-Glättung hatte den Einbruch lediglich verwischt.

Gemessener Vorher-Befund am Offline-Export (DGM1 entlang der OSM-Achse, NHN):

| OSM-Weg | Name | Typ | Länge | Höhe an den Enden | Tiefster Punkt | Durchhang vorher |
| --- | --- | --- | --- | --- | --- | --- |
| `osm:way:94526517` | Steinbrücke | primary | 16,4 m | 17,36 / 17,32 m | 11,78 m | 5,54 m |
| `osm:way:29732751` | Fläutendörper Steg | path | 36,8 m | 17,54 / 17,23 m | 12,00 m | 5,23 m |
| `osm:way:120432334` | – | path | 38,9 m | 16,35 / 16,45 m | 11,90 m | 4,46 m |
| `osm:way:29732766` | Torbrücke | primary | 28,4 m | 15,18 / 16,74 m | 12,44 m | 2,74 m |
| `osm:way:120431986` | – | service | 29,1 m | 16,54 / 13,20 m | 11,90 m | 1,30 m |
| `osm:way:120431984` | – | service | 3,3 m | 13,20 / 16,05 m | 13,20 m | – |

Klärung der beiden `service`-Wege: `osm:way:120431984` (`bridge=movable`, Zugbrücke, 3,3 m) und `osm:way:120431986` (`bridge=yes`, `material=wood`, 29,1 m) teilen denselben inneren Knoten über dem Festungsgraben (`13,20 m NHN`) und bilden zusammen die 32,37 m lange Festungsbrücke (`bridge:osm:way:120431984`) zwischen den beiden Ufer-Widerlagern (`16,16 m` / `16,59 m NHN`). Beim nordwestlichen Holzsteg (`osm:way:120432334`, `bridge:structure=beam`) schließt am Festungswall ein Tunnelweg (`osm:way:416256369`, `tunnel=yes`) an; dieses Widerlager nutzt daher die definierte Ausweichregel (`assumed_max_dgm_3m_radius`, `21,17 m NHN`).

## Meilensteine und Abnahme

| Meilenstein | Status | Ergebnis / Nachweis |
| --- | --- | --- |
| 1 · Brücken erkennen | Erledigt | `tools/geo_import/export.py` übernimmt zusätzlich `bridge:structure`, `bridge:name` und `material`. `tools/mesh_generator/road_elevation.py` fasst die 6 OSM-Brückenwege zu **5 Brückenzügen** mit stabilen IDs (`bridge:<erste Way-ID>`) und jeweils zwei Widerlagern zusammen; der Report listet jeden Brückenzug samt Widerlagern, Materialquelle und lichter Höhe. |
| 2 · Fahrbahnprofil | Erledigt | Widerlagerhöhen werden aus dem Höhenprofil der anschließenden Nicht-Brückenstraße bestimmt (unter Ausschluss unmittelbarer DGM-Böschungskanten ≤ 1,5 m am Grabenrand, z. B. Torbrücke `18,09 → 17,83 m NHN`) bzw. bei fehlendem Anschluss über das 3-m-DGM-Maximum (`assumed_max_dgm_3m_radius`). Brückenfahrbahnen verlaufen strikt linear zwischen den Widerlagern und werden vor der 12-m-Glättung der Nachbarstraßen fixiert; das DGM unter Brücken wird für die Fahrbahn nicht gelesen. |
| 3 · Bauwerk | Erledigt | `tools/mesh_generator/bridges.py` erzeugt das eigene, kollisionsfähige Mesh `SM_Bridges` mit Vertex-Farben (`M_Bridges`): **0,5 m** Fahrbahnplatte, **1,0 m** Brüstung/Geländer, sichtbare Seitenflächen und Widerlagerschürzen (alle Maße als `assumed_sprint11_1_bridge_defaults` gekennzeichnet). Material nach OSM-Tags (`material`/`surface`/`bridge:structure`), sonst Naturstein für Straßenbrücken und Holz für Fußwege. Gehwege auf Straßenbrücken (`Torbrücke`, `Steinbrücke`) laufen durchgehend mit 12 cm Bordstein über die Brückendecke; normale Fahrbahnflächen (`Roads`/`Paving`/`Paths`) sparen Brückenflächen aus (kein Z-Fighting). |
| 4 · Unter der Brücke | Erledigt | Kanal-/Grabenboden (`SM_Terrain_*`) und Wasserflächen (`SM_Water`) unter Brücken werden nicht abgesenkt oder ausgeschnitten; lediglich Böschungskuppen, die an Uferanschlüssen oberhalb der linearen Brückendecke lagen (`Steinbrücke` +10 cm, `Fläutendörper Steg` +31 cm), werden selektiv unter die Brückendecke gedeckelt (`terrain.py`). Bäume, Büsche und Stadtmöbel (`props.py`) werden unter Brückenflächen ausgeschlossen. |
| 5 · Laufzeit und Spielstand | Erledigt | Straßengraph (mit `is_bridge`-Flag je Kante), Fahrzeugrouten, Überwege, Einwohnerrouten und Aufgabenziele übernehmen automatisch die linearen Brückenhöhen. `UDoemitzSimulationSubsystem::TraceStaticGroundZ` beginnt oberhalb der Fahrbahn (`max(5000, ReferenceZ + 2000) cm`) und hebt beim Laden auch ältere/abgesunkene Positionen (> 25 cm unterhalb des Abwärts-Traces) auf die Brückendecke – ohne neues SaveGame-Schema (v6 bleibt unverändert). |
| 6 · Doku und Demo | Erledigt | `docs/GEO_DATA.md` dokumentiert die Brückenregel, `docs/SPRINT_11.md` und `README.md` verweisen auf Sprint 11.1. Win64-Build `Win64Sprint11_1` erstellt und mit zwei 90-s-Benchmarks geprüft. |

## Ergebnisse je Brückenzug (DGM1-Export)

| Brücken-ID | Name | Typ | Material (Quelle) | Länge | Widerlager (NHN) | Längsneigung | Lichte Höhe über Wasser | Lichte Höhe über Graben |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `bridge:osm:way:29732766` | Torbrücke | primary | Stein (`assumed_natural_stone_for_road_bridge`) | 28,35 m | `18,09 → 17,83 m` | 0,92 % | **5,736 m** | 5,148 m |
| `bridge:osm:way:94526517` | Steinbrücke | primary | Stein (`assumed_natural_stone_for_road_bridge`) | 16,39 m | `17,26 → 17,27 m` | 0,05 % | **5,138 m** *(Referenz nächstes Gewässer)* | 5,060 m |
| `bridge:osm:way:29732751` | Fläutendörper Steg | path | Holz (`osm_surface:wood`) | 36,85 m | `17,45 → 17,16 m` | 0,79 % | **5,136 m** | 4,921 m |
| `bridge:osm:way:120431984` | Festungsbrücke (`120431984` + `120431986`) | service | Holz (`osm_material:wood`) | 32,37 m | `16,16 → 16,59 m` | 1,35 % | **3,900 m** | 4,070 m |
| `bridge:osm:way:120432334` | NW-Holzsteg (`beam`) | path | Holz (`osm_surface:wood`) | 38,92 m | `16,34 → 21,17 m` *(3-m-DGM-Annahme am Wall)* | 12,41 % | **5,059 m** | 7,362 m |

## Durchgeführte Prüfungen

### 1. Offline-Geodaten & Python-Tests
- `.\.venv\Scripts\python.exe -m tools.geo_import build` & `tools.mesh_generator`:
  - `166` Meshes (inkl. `SM_Bridges`), `349.256` Dreiecke gesamt; `143` Geländekacheln mit `149.869` Dreiecken (Budget ≤ 150.000), `max_err = 4,95 cm` (Budget ≤ 5,0 cm), `bridges = 5`.
  - Bytegleichheit in `dgm1` und `flat` bestätigt.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: **36 von 36 Tests bestanden** (30 bestehende + 6 neue in `tests/test_sprint11_1.py`: 5 Brückenzüge & OSM-Tags, lineare Fahrbahn ±2 cm zwischen Widerlagern, Unterkante ≥ 0,5 m über Wasserspiegel, kein Ausstattungsobjekt unter Brückenflächen, Übergang Straße → Brücke ≤ 2 cm, Bytegleichheit in `dgm1` und `flat`).

### 2. Editor-Build & Level-Import
- C++-Editor-Build (`DoemitzLivingCityEditor Win64 Development` via UnrealBuildTool): erfolgreich ohne Fehler.
- `scripts/Import-Altstadt.ps1` (`import_altstadt.py`, inkl. CDO-Fallback für `StaticMeshEditorSubsystem` im Commandlet und Kollisionsprüfung aller 5 Brücken):
  - `DOEMITZ_IMPORT_OK: 166 meshes, 35.4291 m reference, 0.0374% error, ref0:hit=4.865m(dgm=4.806m,diff=2.1cm), ref1:hit=4.699m(dgm=4.608m,diff=1.1cm), terrain, roof and wall collision passed, sidewalk collision passed, 5 bridges collision passed`

### 3. Automatisierte PIE-Prüfungen (`scripts/Verify-All.ps1`)
Alle **17 von 17** PIE-Skripten bestanden (`DOEMITZ_VERIFY_ALL_OK: 17/17 PIE checks passed`), darunter:
- `VerifyBridges.py` (neu):
  - Spieler überquert die Torbrücke (`max_dev = 2,40 cm` ≤ 5 cm vom linearen Profil).
  - Fahrzeug überquert die Steinbrücke ohne Senke (`max_dip = 0,00 cm`).
  - Einwohner überquert den Fläutendörper Steg (`max_dev = 0,41 cm`).
  - Spielstand mit abgesunkener Position (`Z = 120 cm`) auf der Torbrücke lädt oben auf der Brückendecke (`dev = 4,00 cm`).
- `VerifyTerrain.py` geprüft: Die Fahrzeugneigung von `6,66°` liegt auf der echten Geländekante `edge:osm:way:37793195:0:0:fwd` (`highway=service`, `surface=grass_paver`), nicht auf einer Brücke; Brückenkanten sind dort zusätzlich explizit über `edge.get("is_bridge")` ausgeschlossen (`walk_z=[470.5, 774.6] cm`, `climb=304.1 cm`, `vehicle_pitch=6.66 deg`, `gap=0.6 cm`).
- `VerifySaveGame.py`: v6-Speichern/Laden sowie v4→v6- und v5→v6-Höhenmigration weiterhin bestanden.

### 4. Win64-Build & Benchmarks (`DoemitzLow`, 1920×1080, 90 s, 8 Fahrzeuge)
- Paketierung: `scripts/Build-Windows.ps1 -ArchiveDirectory unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint11_1` (`ExitCode=0`, IoStore `259,61 MiB`).
- Parameterloser Start von `DoemitzLivingCity.exe`: erfolgreich (`alive_after_12s=True`).
- Messstrecke `Goethestraße → Rathausplatz → Festungszugang` (`326,4 m`) auf Intel Core i5-1135G7 / Intel Iris Xe Graphics:

| Lauf | Profil | Mean FPS | Mean ms | P50 ms | P95 ms | P99 ms | Game / Draw / GPU ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lauf 1 | `DoemitzLow` | **56,39** | 17,73 | 16,63 | 24,43 | 33,26 | 3,77 / 14,53 / 17,73 |
| Lauf 2 | `DoemitzLow` | **57,72** | 17,32 | 16,72 | 22,59 | 25,28 | 3,72 / 13,93 / 17,32 |

Mittelwert **57,06 FPS** (−5,4 % gegenüber Sprint 11 mit 60,31 FPS; deutlich innerhalb des Abnahmekriteriums von höchstens −20 % ≥ 48,2 FPS und weit über dem 15-FPS-Zielbudget).

## Bewusst außerhalb dieser Nachbesserung

- Bögen, Pfeiler und historische Details der Steinbrücke und der Torbrücke (folgen mit den markanten Bauwerken in Sprint 12).
- Begehbarer Graben unter den Brücken.
