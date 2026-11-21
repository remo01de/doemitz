# Sprint 8 · Wochenkalender, mehr Einwohner und Fußgängerüberwege

Stand: Abgeschlossen (21.11.2026).

## Ausgangslage nach Sprint 7

Sprint 7 hatte die Performance-Basis (`DoemitzLow`, HISM) und den vernetzten Straßenverkehr (5 Fahrzeuge, Rechts vor links, SaveGame v2) geliefert. Zu Beginn von Sprint 8 wurden drei offene Punkte geschlossen:

1. **Aufräumen & Versionierung:** Sprint 7 war auf `main` committet (`6cf48ef`); die ungetrackte 4,5-GB-Kopie `unreal/DoemitzLivingCity 5.8/` wurde entfernt. Alle PIE-Prüfskripte (`Verify*.py`, `ConfigureSprint.py`) wurden aus `Saved/` nach `unreal/DoemitzLivingCity/Content/Python/Verify/` übernommen und über [Verify-All.ps1](../scripts/Verify-All.ps1) gebündelt.
2. **Standard-Grafikprofil `DoemitzLow`:** Die Profillogik zog aus `UDoemitzBenchmarkSubsystem` in `UDoemitzGraphicsSettings` (`GameUserSettings.ini`). Beim normalen Spielstart ohne Kommandozeilenparameter startet das Spiel direkt mit `DoemitzLow`.
3. **Skalierung der Stadtsimulation:** Mit Wochenkalender, OSM-Öffnungszeiten, 30 deterministischen Einwohnern aus dem OSM-POI- und Wohngebäudebestand, einem 150-m-Actor-Pool samt 1-Hz-Grobsimulation sowie `highway=crossing`-Überwegen wächst die Altstadt-Simulation auf reale Alltagsabläufe.

## Meilensteine und Abnahme

| Meilenstein | Status | Ergebnis |
| --- | --- | --- |
| 0 · Aufräumen Sprint 7 | Erfüllt | `unreal/DoemitzLivingCity 5.8/` entfernt. Alle `Verify*.py` und `ConfigureSprint.py` liegen versioniert in `unreal/DoemitzLivingCity/Content/Python/Verify/` und laufen über [Verify-All.ps1](../scripts/Verify-All.ps1). |
| 1 · Grafikprofil als Spieleinstellung | Erfüllt | [DoemitzGraphicsSettings.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Settings/DoemitzGraphicsSettings.h) / [DoemitzGraphicsSettings.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Settings/DoemitzGraphicsSettings.cpp) speichert das Profil in `GameUserSettings.ini` (Standard `DoemitzLow`). `F7` schaltet im Spiel zwischen `DoemitzLow` und `DoemitzHigh` um ([DoemitzSimulationConfig.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Simulation/DoemitzSimulationConfig.cpp)), das HUD zeigt `Grafik: Low` / `Grafik: High`, und `-DoemitzProfile=` überschreibt weiterhin für Benchmarks. |
| 2 · Wochenkalender | Erfüllt | `UDoemitzSimulationSubsystem` führt `DayOfWeek` (`0 = Mo` … `6 = So`) und `CalendarWeek` (Spielstart: Montag, KW 1). Das Manifest ([doemitz-altstadt-citizens.json](../data/manifests/doemitz-altstadt-citizens.json)) und alle generierten Einwohner unterscheiden `Werktag`, `Samstag`, `Sonntag`. Das HUD ([DoemitzClockWidget.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/UI/DoemitzClockWidget.cpp)) zeigt `Mo, Tag 1  |  07:50  (1x)`. |
| 3 · Öffnungszeiten | Erfüllt | [opening_hours.py](../tools/mesh_generator/opening_hours.py) wertet OSM-`opening_hours` aus (`12` reale Altstadt-Orte aus OSM, u. a. `Fritz-Reuter-Apotheke`, `Sparkasse Mecklenburg-Schwerin`, `Elb-Cafe`, `Touristeninformation`, `Nette Ecke`) und kennzeichnet alle übrigen Orte explizit als Annahme (`assumed_*`). Einwohner überspringen geschlossene `Shopping`-Ziele und wählen die nächste offene Aktivität. |
| 4 · 30 Einwohner aus Geodaten | Erfüllt | [export.py](../tools/geo_import/export.py) ergänzt den `pois`-Layer (**121 POIs** mit stabilen IDs `poi:osm:*`). [citizens.py](../tools/mesh_generator/citizens.py) behält die 4 Bestandseinwohner (`citizen_anna_01` … `citizen_dieter_04`) und erzeugt 26 weitere (`altstadt_citizen_05` … `30`, `Seed 202608`) deterministisch auf Wohngebäuden und Arbeits-/Einkaufs-POIs (**57 Orte**, **238 Fußgängerrouten**). |
| 5 · Detailstufen der Simulation | Erfüllt | `UDoemitzSimulationSubsystem` verwaltet einen `ADoemitzCitizenActor`-Pool mit 6 geteilten Mesh-Varianten und `150 m` Radius (`15000 cm`). Außerhalb des Radius laufen Einwohner ohne Actor mit 1-Hz-Grobsimulation; beim Wiedereintritt wird die Restzeit sofort nachgeführt und der Pool-Actor exakt an der Simulationsposition platziert (`delta = 0,00 cm`). |
| 6 · Fußgängerüberwege | Erfüllt | [export.py](../tools/geo_import/export.py) und [road_graph.py](../tools/mesh_generator/road_graph.py) übernehmen **4** `highway=crossing`-Knoten im Altstadt-Ausschnitt (inkl. Zebrastreifen `osm:node:1125976999`) auf die befahrbaren Straßenkanten. **63** Fußgängerrouten queren an Überwegen. Fahrzeuge bremsen und halten vor besetzten Überwegen (`bYieldingForCrossing`). |
| 7 · SaveGame v3 und Demo | Erfüllt | `SaveSchemaVersion = 3` ([DoemitzSaveGame.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Simulation/DoemitzSaveGame.h)) speichert `DayOfWeek`, `CalendarWeek` und alle 30 Einwohner. Spielstände v1/v2 werden beim Laden auf Montag + Startzustand neuer Einwohner migriert. Win64-Build startet ohne Parameter mit `DoemitzLow`. |

## Benchmark-Ergebnisse (1920 × 1080, Test-PC)

Test-PC: `Intel Core i5-1135G7 @ 2.40 GHz`, `Intel Iris Xe Graphics`, `16 GB RAM`, Windows 11.
Messstrecke: `Goethestraße → Rathausplatz → Festungszugang` (326,4 m, 90 s Messzeit nach 3 s Warmup), **30 Einwohner (150-m-Pool)**, **5 Fahrzeuge**, **4 Überwege**.

| Messung | Lauf 1 (Ø FPS / Ø ms / P95 / P99) | Lauf 2 (Ø FPS / Ø ms / P95 / P99) | Abweichung | `stat unit` Ø (Game / Draw / GPU) |
| --- | --- | --- | --- | --- |
| Sprint 7 Vergleich (`DoemitzLow`, 4 Einw., 5 Fzg.) | **54,74 FPS** / 18,27 ms / 22,56 ms / 25,80 ms | **53,89 FPS** / 18,56 ms / 22,74 ms / 25,67 ms | 1,6 % | 3,28 / 14,28 / 18,41 ms |
| Sprint 8 Final (`DoemitzLow`, 30 Einw. + Pool, 5 Fzg.) | **58,14 FPS** / 17,20 ms / 20,57 ms / 24,15 ms | **58,39 FPS** / 17,13 ms / 20,22 ms / 21,94 ms | 0,4 % | 3,58 / 13,73 / 17,16 ms |
| Sprint 8 Final (`DoemitzHigh`, 30 Einw. + Pool, 5 Fzg., Lumen + VSM) | **7,79 FPS** / 128,33 ms / 168,03 ms / 246,00 ms | — | — | 4,60 / 124,66 / 128,34 ms |

Das Performance-Budget (≥ 15 FPS, maximal 20 % Verlust gegenüber Sprint 7) wird deutlich übertroffen (**58,27 FPS** im Mittel bei `DoemitzLow`).

## Prüfungen

- **Offline-Build und Python-Tests:** `geo_import build` (`146` Straßen, `645` Gebäude, `3` Wasserflächen, `121` POIs, `0` Geometriefehler) + `mesh_generator` (`30` Einwohner, `57` Orte, `238` Routen, `63` über Überwege, `12` OSM-Öffnungszeiten) bytegleich bei Wiederholung (`SHA-256: D4B438AFFA1805B11E6A34FABBF4DD1C04F62ECB5FD889217A031555ADA7B01C`). Alle `14` Python-Tests (`test_geo_import.py`, `test_mesh_generator.py`, `test_road_graph.py`, `test_sprint08.py`) bestanden.
- **Editor-Build & Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) kompiliert. `Import-Altstadt.ps1` bestand mit `DOEMITZ_HISM_IMPORT_OK: 11 HISM actors, 861 instances`, `DOEMITZ_TRAFFIC_NETWORK_IMPORT_OK: 5 vehicles, 167 road edges, 4 crossings (seed=202607)`, `DOEMITZ_CITIZENS_IMPORT_OK: 30 citizens, 57 places, 238 routes, 6 mesh variants` und `DOEMITZ_IMPORT_OK: 23 meshes, 35.4291 m reference, 0.0372% error, terrain, roof and wall collision passed, sidewalk collision passed`.
- **Play-Modus (PIE via `scripts/Verify-All.ps1`):**
  - `VerifyDayNightHud.py`: `DOEMITZ_DAYNIGHT_HUD_PIE_OK` (`Mo, Tag 1 | 12:00 (1x)`, `30 Einwohner`, `Grafik: Low`)
  - `VerifyTrafficNetwork.py`: `DOEMITZ_TRAFFIC_NETWORK_PIE_OK` (5 Fahrzeuge, `min_pair_dist=2763.9 cm`, Rechts vor links an `osm:node:277309010`)
  - `VerifyCalendar.py`: `DOEMITZ_CALENDAR_PIE_OK` (Mo→Di-Wechsel, geschlossenes `place_kaufhaus` am Sonntag übersprungen, Standard `DoemitzLow`)
  - `VerifyCitizenLod.py`: `DOEMITZ_CITIZEN_LOD_PIE_OK` (Austritt aus 150-m-Radius, 1-Hz-Grobsimulation `278.8 cm`, Wiedereintritt mit Pool-Actor `delta=0.00 cm`)
  - `VerifyCrossing.py`: `DOEMITZ_CROSSING_PIE_OK` (Halt am Zebrastreifen `osm:node:1125976999` vor `citizen_anna_01` und anschließende Weiterfahrt)
  - `VerifySaveGame.py`: `DOEMITZ_SAVEGAME_PIE_OK` (SaveGame v3 inkl. 30 Einwohner und `v2 -> v3`-Migration verifiziert)
- **Windows-Testbuild:** `Win64Sprint08` neu erstellt. Start ohne `-DoemitzProfile=` loggt `DoemitzLow profile applied: 23/68 street point lights kept active`. Zwei `DoemitzLow`-Benchmarks und ein `DoemitzHigh`-Benchmark verifiziert. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint08/DoemitzLivingCity.exe)

## Ausblick

| Sprint | Schwerpunkt |
| --- | --- |
| 9 | Wirtschaft und Interaktion: Geldbestand, Arbeiten und Einkaufen, Interaktionstaste an Gebäudeeingängen |
| 10 | UMG-Stadtkarte mit Einwohnern und Fahrzeugen, erste Aufgaben, Ampeln und Parken |
| 11 | DGM1-Terrain: Höhen für Boden, Straßen, Gehwege und Gebäudesockel, Elbufer und Festungswall |
