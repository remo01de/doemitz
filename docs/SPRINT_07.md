# Sprint 7 · Performance-Basis und vernetzter Straßenverkehr

Stand: Abgeschlossen (21.11.2026).

## Warum jetzt

Sprint 1 hatte ein Abnahmekriterium offen gelassen: Der Test-PC (Intel Core i5-1135G7, Iris Xe, 16 GB RAM) erreichte bei `1920 × 1080` im Mittel ca. 9,6 FPS. Das Ziel für diesen Test-PC wurde am 21.11.2026 auf mindestens **15 FPS im Mittel bei 1080p** angepasst ([PRD](PRD.md)). Seit Sprint 2 war die Szene auf 247.742 Dreiecke und 68 dynamische Punktlichter gewachsen; `DefaultEngine.ini` aktivierte Lumen-GI, Lumen-Reflexionen und Virtual Shadow Maps.

Gleichzeitig bildet der vernetzte Straßenverkehr den nächsten Simulationsbaustein nach PRD: Statt eines einzelnen Fahrzeugs auf einer festen Schleife fahren nun 5 Fahrzeuge deterministisch mit Grundregeln (Abstandhalten, Rechts vor links, Fußgänger-Halt) im realen Altstadt-Straßengraphen.

## Meilensteine und Abnahme

| Meilenstein | Status | Ergebnis |
| --- | --- | --- |
| A · Reproduzierbare Performance-Messung | Erfüllt | Feste 326,4-m-Laufstrecke (`Goethestraße → Rathausplatz → Festungszugang`, 90 s + 3 s Warmup) per `-DoemitzBenchmark` im Win64-Build ([DoemitzBenchmarkSubsystem.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Benchmark/DoemitzBenchmarkSubsystem.cpp), [Run-Benchmark.ps1](../scripts/Run-Benchmark.ps1)). Schreibt Mittelwert, P50/P95/P99 sowie `stat unit` (Game, Draw, GPU) als JSON nach `Saved/Benchmarks/`. Abweichung zwischen je zwei Läufen: 1,5 % – 3,7 % (≤ 5 %). |
| B · Performance-Budget | Erfüllt | `DoemitzLow` (Lumen aus, klassische CSM-Schatten, FXAA, reduzierte Lichtradien, 23 schattenlose Laternenlichter) plus HISM-Instanzierung für 861 Props (Laternen, Bänke, Pflanzkübel, Poller, Bäume, Büsche via [DoemitzInstancedPropActor.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/World/DoemitzInstancedPropActor.cpp)) erreichen **54,3 FPS im Mittel bei 1080p** mit 5 Fahrzeugen (Ziel: ≥ 15 FPS). Ein 64-m-Mesh-Raster war damit nicht mehr nötig. `DoemitzHigh` mit Lumen bleibt erhalten. |
| C · Straßengraph | Erfüllt | [road_graph.py](../tools/mesh_generator/road_graph.py) erzeugt `road-graph` im Mesh-Export: **90 Knoten** (Kreuzungen mit OSM-Node-IDs), **167 gerichtete Kanten** (`109` stark zusammenhängend im Hauptnetz, `58` als Sackgasse markiert), `oneway`, Fahrbahnbreite und Tempo (`98` aus OSM `maxspeed`, `32` Annahme 20 km/h Kopfsteinpflaster, `37` Annahme 30 km/h Altstadt). Geprüft durch [test_road_graph.py](../tests/test_road_graph.py). |
| D · Mehrere Fahrzeuge im Netz | Erfüllt | 5 Fahrzeuge (`altstadt_vehicle_01` … `05`) aus [doemitz-altstadt-streets.json](../data/manifests/doemitz-altstadt-streets.json) mit deterministischer Kantenwahl (`Seed 202607 + VehicleId + DecisionIndex`). Zustand (Kante, Distanz, Geschwindigkeit, Entscheidungen) liegt in `UDoemitzSimulationSubsystem`; `ADoemitzTrafficVehicle` stellt ihn nur noch dar. |
| E · Grundregeln | Erfüllt | Abstandhalten auf derselben und der nächsten Kante plus 2D-Überlappungsschutz, Rechtsfahrgebot auf Zweirichtungsstraßen, Rechts-vor-links an Kreuzungen über `JunctionReservations` im Subsystem sowie Halten vor Spieler und Einwohnern. |
| F · SaveGame v2 und Demo | Erfüllt | `SaveSchemaVersion = 2` speichert die Fahrzeugzustände je Kante ([DoemitzSaveGame.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Simulation/DoemitzSaveGame.h)). Spielstände der Version 1 werden beim Laden automatisch auf die nächste befahrbare Kante migriert. Win64-Testbuild startet mit 5 Fahrzeugen und führt den Benchmark reproduzierbar aus. |

## Benchmark-Ergebnisse (1920 × 1080, Test-PC)

Test-PC: `Intel Core i5-1135G7 @ 2.40 GHz`, `Intel Iris Xe Graphics`, `16 GB RAM`, Windows 11.
Messstrecke: `Goethestraße → Rathausplatz → Festungszugang` (326,4 m, 90 s Messzeit nach 3 s Warmup).

| Messung | Lauf 1 (Ø FPS / Ø ms / P95 / P99) | Lauf 2 (Ø FPS / Ø ms / P95 / P99) | Abweichung | `stat unit` Ø (Game / Draw / GPU) |
| --- | --- | --- | --- | --- |
| Sprint 6 Baseline (1 Fzg., Lumen + VSM, 68 Lichter) | **9,95 FPS** / 100,48 ms / 155,91 ms / 252,91 ms | **9,59 FPS** / 104,31 ms / 152,38 ms / 206,38 ms | 3,7 % | 4,03 / 98,35 / 102,41 ms |
| Sprint 7 Schritt B1 (`DoemitzLow`, 1 Fzg., vor HISM) | **47,20 FPS** / 21,19 ms / 25,69 ms / 38,67 ms | **46,49 FPS** / 21,51 ms / 27,72 ms / 38,19 ms | 1,5 % | 3,22 / 17,23 / 21,35 ms |
| Sprint 7 Final (`DoemitzLow`, 5 Fzg., 861 HISM-Instanzen) | **54,74 FPS** / 18,27 ms / 22,56 ms / 25,80 ms | **53,89 FPS** / 18,56 ms / 22,74 ms / 25,67 ms | 1,6 % | 3,28 / 14,28 / 18,41 ms |
| Sprint 7 Final (`DoemitzHigh`, 5 Fzg., 861 HISM, Lumen + VSM) | **7,75 FPS** / 129,04 ms / 165,04 ms / 221,21 ms | **7,52 FPS** / 133,04 ms / 177,68 ms / 231,95 ms | 3,0 % | 4,25 / 126,93 / 131,05 ms |

## Prüfungen

- **Offline-Build und Python-Tests:** `geo_import build` + `mesh_generator` bytegleich bei Wiederholung (`23` Meshes, `182.642` Dreiecke, SHA-256 identisch), alle `9` Python-Tests (`test_geo_import.py`, `test_mesh_generator.py`, `test_road_graph.py`) bestanden.
- **DGM-Lizenzprüfung:** Lizenz des DGM1 Mecklenburg-Vorpommern (LAiV M-V / GeoPortal.MV: CC BY 4.0 / Datenlizenz Deutschland – Namensnennung, Quellenvermerk `© GeoBasis-DE/M-V <Jahr>`) in [doemitz-altstadt-dgm-license.json](../data/manifests/doemitz-altstadt-dgm-license.json) dokumentiert.
- **Editor-Build & Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) kompiliert. `Import-Altstadt.ps1` bestand mit `DOEMITZ_HISM_IMPORT_OK: 11 HISM actors, 861 instances`, `DOEMITZ_TRAFFIC_NETWORK_IMPORT_OK: 5 vehicles, 167 road edges (seed=202607)` und `DOEMITZ_IMPORT_OK: 23 meshes, 35.4291 m reference, 0.0372% error, terrain, roof and wall collision passed, sidewalk collision passed`.
- **Play-Modus (PIE):**
  - `VerifyTrafficNetwork.py`: `DOEMITZ_TRAFFIC_NETWORK_PIE_OK: 5 vehicles, decisions={'altstadt_vehicle_01': 4, 'altstadt_vehicle_02': 3, 'altstadt_vehicle_03': 3, 'altstadt_vehicle_04': 4, 'altstadt_vehicle_05': 3}, min_pair_dist=2733.9 cm, rvl_node=osm:node:277309010 holder=altstadt_vehicle_02 left_yielded=True`
  - `VerifySaveGame.py`: `DOEMITZ_SAVEGAME_PIE_OK: v2 saved & restored time=482.5m, player/vehicle/citizen states, daytime lighting, and v1->v2 migration verified`
  - `VerifyDayNightHud.py`: `DOEMITZ_DAYNIGHT_HUD_PIE_OK`
- **Windows-Testbuild:** `Win64Sprint07` neu erstellt und mit allen vier 90-s-Benchmarks (`DoemitzLow` & `DoemitzHigh`) verifiziert. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint07/DoemitzLivingCity.exe)

## Ausblick

| Sprint | Schwerpunkt |
| --- | --- |
| 8 | Wochenkalender und Öffnungszeiten, 20–40 Einwohner aus Wohngebäuden im OSM-Bestand, vereinfachte Simulation für nicht sichtbare Einwohner, Fußgängerüberwege |
| 9 | Wirtschaft und Interaktion: Geldbestand, Arbeiten und Einkaufen im Kaufhaus, Interaktionstaste an Gebäudeeingängen |
| 10 | UMG-Stadtkarte mit Einwohnern und Fahrzeugen, erste Aufgaben, Ampeln und Parken |
