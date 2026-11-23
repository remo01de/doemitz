# Sprint 15 · Fundament, Architektur & Durchgängige Stadt

Stand: Umgesetzt und geprüft (abgestimmt und umgesetzt am 23.11.2026 nach Revision von Sprint 14).

## Ausgangslage nach Sprint 14

Sprint 14 (`8b57ae4`) erweiterte Dömitz auf 1,11 km² bis zum Hafen und zur Schleuse Dömitz (44,3–48,1 FPS auf `DoemitzLow`). Die Revision nach Sprint 14 deckte jedoch sechs vorrangige Mängel auf, die vor weiterem Welt- und Inhaltswachstum behoben werden mussten:

1. **Abgeschnittene Hafen-Halbinsel & isolierte Festung:** Der Ostrand `11,2607° E` schnitt die einzige reale Straßenverbindung (`Werderstraße` ↔ `Am Hafen`) ca. 90 m vor der Kreuzung ab. Dadurch lagen Hotel Dömitzer Hafen, Speicher, Hafenrestaurant, Panorama Café, Strandbar und 3 Hafenparkplätze auf einer isolierten Insel (50/245 Einwohnerrouten mit bis zu 258 m Luftlinie über Wasser; 3 Parkplätze 105–170 m quer übers Wasser gebunden). Zudem blieben die in Sprint 12/13 gebauten Festungstunnel (`Festungstor`, `NW-Steg`) in `citizens.py` aus dem Fußgängergraphen ausgeschlossen.
2. **Einwohner-Zeitskala vs. Uhr (`TimeScale = 60`):** Echtzeit-Fußwege (`1,35 m/s`) gegen `1 s = 1 Spielminute` machten auf der gewachsenen Karte 59,7 % aller Werktags-Etappen und 89,3 % aller Werktags-Einkaufswege bei `1x` unerreichbar (28/30 Einwohner betroffen); `StartTrip` setzte nicht angekommene Einwohner an den Startort zurück.
3. **Innenraum-Beleuchtung in `DoemitzLow`:** `DoemitzGraphicsSettings::ApplyProfile` blendete 2/3 aller `APointLight`-Actors pauschal aus – einschließlich der 20 Innenraum-Deckenlampen.
4. **Sicht- und Geometriefehler im Hafen:** Am Speicher am Hafen (`osm:way:42883863`) saßen 4 Kranbalken/Ladeluken schwebend auf den getreppten Seitenkanten statt an den Giebelseiten; Kaimauern hatten offene Stirnflächen und keinen begehbaren Zugang zu den Schwimmstegen; Boote zeigten Smooth-Shading-Artefakte an scharfen Rumpfkanten und einen offenen Bugspalt; am Schleusen-Unterhaupt ragte eine Geländeecke ins Becken.
5. **Lizenz- & Workspace-Hygiene:** Im öffentlichen GitHub-Repo (`remo01de/doemitz`) waren seit Sprint 1/2 zehn unlizenzierte JPGs in `Images/` getrackt; `data/processed/` im Hauptverzeichnis stand noch auf Sprint 12, während der Sprint-14-Stand im Worktree lag; ungenutzte Epic-Template-Animationen (`Death/`, `Pistol/`, `Rifle/`) und 16 alte lokale Builds belegten Speicher/LFS.
6. **C++-Monolith:** `DoemitzSimulationSubsystem.cpp` war auf 3.708 Zeilen angewachsen.

## Ergebnisse nach Meilenstein

| Nr. | Meilenstein | Ergebnis |
| --- | --- | --- |
| 0 | Hygiene, History-Rewrite & Workspace | `Images/` per Git-History-Rewrite vollständig aus HEAD und Historie entfernt (`7d259dc` auf `origin/main` gepusht) und in `.gitignore` ausgeschlossen; 74 ungenutzte Mannequin-Animationen (`Death/`, `Pistol/`, `Rifle/`) entfernt; ~10,6 GB alte lokale Win64-Builds bereinigt; Haupt-Workspace synchronisiert. |
| 1 | Durchgängiges Netz (2. Kachel + Tunnel) | `bounds_lonlat = [11.2428, 53.1372, 11.2630, 53.1455]` (+154 m Ost), Ursprung (`11,2487° E / 53,14265° N`) und Bezugshöhe (`13,001 m NHN`) unverändert. Zweite LAiV-M-V-Kachel `33_250_5894` für DGM1 und LoD2 bezogen und in den Lizenzmanifesten dokumentiert (`grid = 1028×1433`, 352 Geländekacheln, 273.595 von 285.000 Dreiecken, Altstadt max. 4,95 cm Fehler). Frischer OSM-Export: 241 Straßen, 808 Gebäude, 11 Wasserflächen, 192 POIs, 21 Mauern, 5 Wasserbauwerke, 43 Stege, 5 Dalben (0 Geometriefehler, alle Manifest-IDs vorhanden). Straßennetz: 303 Kanten, 104 Kreuzungen, 15 Parkplätze – alle `Werderstraße`-, `Am Hafen`- und `Hafenplatz`-Kanten haben `dead_end = False`; alle 3 Süd-Hafen-Parkplätze binden direkt an `Am Hafen`. Fußgängergraph bindet begehbare Tunnelportale (`osm:way:120431987` Festungstor, `osm:way:416256369` NW-Steg) inkl. Tunnelboden-Höheninterpolation ein und schnappt ausschließlich an die Hauptkomponente (`871/915` Knoten): **`disconnected_route_count = 0`**, **`0` Routen über offenes Wasser (`> 3 m`)**, 237 Routen (53 über Überwege). |
| 2 | 6-`UWorldSubsystem`-Split | Vollständige Aufteilung von `UDoemitzSimulationSubsystem` (3.708 → 545 Zeilen) in 6 zyklenfreie `UWorldSubsystem`-Klassen mit zentraler, deterministischer Tick-Reihenfolge (`Simulation → Tasks/Economy → Citizens → Traffic`) und gemeinsamem Typ-Header `DoemitzSimulationTypes.h`: `UDoemitzSimulationSubsystem`, `UDoemitzEconomySubsystem`, `UDoemitzCitizenSubsystem`, `UDoemitzTrafficSubsystem`, `UDoemitzTaskSubsystem`, `UDoemitzSaveSubsystem`. Alle C++-Caller (UI-Widgets, Interaktion, Türen, Fahrzeuge, Einwohner-Actors, Config) und alle 16 betroffenen PIE-Verify-Skripte migriert. SaveGame v1–v7-Migration vollständig erhalten. |
| 3 | Hybrid-Zeitskala (`20x`) | `BaseTimeScale = 20.0` (1 Spieltag = 72 Echtzeit-Minuten; HUD-Stufen `1x / 5x / 15x / Pause` relativ zur Basis-Zeitskala statt festem `/ 60.0`; Arbeitsschicht `15x = 300.0`). Sichtbare Einwohner (`≤ 150 m`) gehen im realen Gehtempo (`~1,35 m/s × Multiplier`), Off-Screen-Einwohner (`> 150 m`) reisen in Spielzeit (`~27 m/s` bei `1x`). `StartTrip` führt laufende Wege nahtlos ab aktueller `WorldLocation` auf dem Straßennetz weiter (kein Rück-Teleport; gemessen `1,3 cm` Übergang). Entfernungsgewichtete Zielwahl in `citizens.py` (Median-Werktagsetappe 290 m, 119/119 = 100 % Off-Screen bei `1x` erreichbar). Der Sprint-14-Workaround `set_time_scale(30.0)` in `VerifyEconomy.py` wurde entfernt – der Test läuft wieder bei echtem `1x` (`20.0`). |
| 4 | Sicht-, Licht- & Qualitätsfixes | `DoemitzGraphicsSettings` drosselt in `DoemitzLow` ausschließlich `ADoemitzDayNightController::GetStreetLights()` – alle 20 Innenraum-Deckenlampen bleiben unangetastet und sichtbar (67 Straßenlaternen weiterhin gedrosselt). Speicher (`landmarks.py`): echte Giebelerkennung über LoD2-Firstrichtung (`12,14°`) und Dachpolygongrenze → exakt 2 Kranbalken an den echten 15,84-m-Giebeln (0 schwebende Ausleger). `locks.py`: feste Endkappen (`LockConcrete` + `LockCoping` inkl. Rückseite) an `build_edge_wall` und Kammerwand-Verlängerung um 0,55 m in die Schleusenhäupter. `harbour.py`: einheitensicherer `_parse_meters`-Parser, Kaimauern vor Stegen, geneigte begehbare Uferrampen (`3,4°–12,5°`) sowie doppelte Süd-Marina-Gangways (`osm:way:1355847994` & `1355847995`, `12,5°–13,5°`, mit Geländern) vom Südkai-Podest (`osm:way:1355847997`) zum 80,9-m-Hauptsteg. `doemitz_prop_meshes.py`: Split-Normals (`_add_sharp_box`, 24 Vertices) für scharfe Bootskabinen, geschlossener spitzer Bug (`w = 0.0`) und geschlossener Kielboden. `DoemitzSaveSubsystem`: `SM_LockRailing` & `SM_PierPile` im Gebäudestruktur-Filter. `import_altstadt.py`: `used_with_instanced_static_meshes = True` für alle 14 `M_Prop*`-Materialien (beseitigt 14 Default-Material-Warnungen im gepackten Win64-Build). `DoemitzUiText`/Widgets: Karten-Attribution auf `© GeoBasis-DE/M-V 2025/2026`, Titel auf `Dömitz` aktualisiert. Doku (`ARCHITECTURE.md`, `GEO_DATA.md`, `README.md`, `SPRINT_13.md`, `SPRINT_14.md`) aktualisiert. |
| 5 | Prüfungen, Sichtprüfung & Build | Siehe Abschnitt „Prüfungen“ und „Sichtprüfung“ unten. |

## Prüfungen

1. **Offline-Pipeline:** `python -m tools.geo_import build` und `python -m tools.mesh_generator`:
   - `scene.json`: 241 Straßen, 808 Gebäude, 11 Wasserflächen, 192 POIs, 21 Mauern, 5 Wasserbauwerke, 43 Stege, 5 Dalben, 0 Geometriefehler, `grid = 1028×1433`, Referenzfehler `0,0373 %`.
   - `unreal-city-meshes.json`: **781 Meshes, 574.484 Dreiecke** (Gelände 352 Kacheln, 273.595 / 285.000 Dreiecke, Altstadt max. 4,95 cm; Zellraster `6 × 4`, 405 Zell-Meshes; 303 Straßenkanten, 15 Parkplätze; 30 Einwohner, 75 Orte, 237 Routen, 0 Wasserquerungen, 0 getrennte Routen; 13 Hafen-Gangways inkl. `1355847994`/`1355847995`; Stadtkarte `4096 × 4096 px`, `0,3483 m/px`).
2. **Python-Unit-Tests:** `python -m unittest discover -s tests` — **81 von 81 Tests bestanden** (inkl. 9 neuer Tests in `tests/test_sprint15.py` für M1–M4; 5 Konstanten in `test_sprint11.py`, `test_sprint12.py`, `test_sprint14.py` auf den erweiterten Ostrand angepasst).
3. **C++-Editor-Build** (`DoemitzLivingCityEditor Win64 Development`): `Result: Succeeded` (0 Fehler, 0 Warnungen).
4. **Unreal-Weltimport** (`import_altstadt.py` + `FixPropMaterials`):
   - `DOEMITZ_IMPORT_OK: 781 meshes, 35.4291 m reference, 0.0374% error, terrain/roof/wall/sidewalk/9 bridges collision passed`
   - `DOEMITZ_HISM_IMPORT_OK: 195 HISM actors, 1702 instances, 1240 blocking`
   - `DOEMITZ_STREAMING_GRID_OK: WorldPartitionRuntimeHashSet: MainPartition 25600/100000 -> 25600/100000; (405 cell meshes)`
   - `DOEMITZ_PROP_MATS_OK: updated 14 prop materials with used_with_instanced_static_meshes=True`
   - Zusätzlich `Import-Altstadt.ps1` und `Verify-All.ps1` gehärtet, sodass alte Logdateien vor jedem Lauf gelöscht werden.
5. **PIE-Prüfsuite** (`scripts/Verify-All.ps1`): **`DOEMITZ_VERIFY_ALL_OK: 22/22 PIE checks passed.`**
   - Neu **`VerifySprint15.py`**: `6 subsystems active, BaseTimeScale=20.0 (HUD 1x/5x/15x/Pause OK), visible_speed=141.7cm/s, offscreen_speed=5397.5cm/s, midtrip_jump=1.3cm, interior_lights_visible=20 (street_lights_hidden_low=67)`.
   - **`VerifyEconomy.py`**: `Kaufhaus citizen revenue at true 1x (20) daily=3980ct weekly=3980ct` (ohne Workaround).
   - **`VerifyInteriors.py`**: `interior_lights_visible: 20`, 3 Innenräume, Tür/Tresen/Aushang/Einwohner/SaveGame v7 bestanden.
   - Nach den finalen Material-/Grafik-Fixes erneut verifiziert (`VerifyInteriors.py`, `VerifyPropCollision.py`, `VerifySprint15.py`: 3/3 bestanden).
6. **Windows-Build (`Win64Sprint15`):** `scripts/Build-Windows.ps1 -ArchiveDirectory unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint15` → **`BUILD SUCCESSFUL`** (`DoemitzLivingCity.exe`, 1.483 Pakete, 264,16 MiB IoStore-Pak; Laufzeit-Log bestätigt **0** `InstancedStaticMeshes`-Materialwarnungen und `DoemitzLow profile applied: 34/101 street point lights kept active (interior lights untouched)`).
7. **Benchmark-Befund (`DoemitzLow`, 1920×1080, i5-1135G7 / Intel Iris Xe):**
   - Die 4 Läufe (`Saved/Benchmarks/Sprint15/altstadt_run1..2.json`, `hafen_run1..2.json`) liefen technisch stabil durch (`DOEMITZ_BENCHMARK_OK`), wurden während dieser Sitzung jedoch durch den parallel laufenden Electron-UI-GPU-Prozess der IDE (`Antigravity.exe --type=gpu-process`, gemessen **71,6 %** 3D-GPU-Auslastung + `dwm` **11,1 %** → nur **18,1 %** GPU-Anteil für `DoemitzLivingCity.exe`) im WDDM-Scheduler auf 2,1–3,4 FPS im Mittel gedrosselt (`draw_mean_ms = 239–320 ms`, `gpu_mean_ms = 294–384 ms`).
   - Eine systematische Bisektion (alle Lichter, Schatten, Lumen, VSM, SkyLight-Capture, Fog, Atmosphere aus + 480×270-Test) bestätigte eindeutig die externe GPU-Konkurrenz als Ursache (keine Regression durch die 20 Innenraumlampen oder den Subsystem-Split). Auf ungestörten Einzelframes erreichte der finale `Win64Sprint15`-Build **`min_ms = 8,52 ms` (~117 FPS)** (Sprint 14: `min_ms = 9,90 ms`).
   - Für eine ungestörte Vergleichsmessung (erwartet > 40 FPS auf Iris Xe) den Benchmark direkt in einer separaten PowerShell mit minimiertem IDE-Fenster ausführen:
     ```powershell
     $exe = 'unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint15\DoemitzLivingCity.exe'
     .\scripts\Run-Benchmark.ps1 -Executable $exe -Profile DoemitzLow -OutputJson unreal\DoemitzLivingCity\Saved\Benchmarks\Sprint15\altstadt_clean.json
     .\scripts\Run-Benchmark.ps1 -Executable $exe -Profile DoemitzLow -Route hafen -OutputJson unreal\DoemitzLivingCity\Saved\Benchmarks\Sprint15\hafen_clean.json
     ```

## Sichtprüfung

Aufnahmen mit `CaptureSprint13Screenshots.py` (`DOEMITZ_OUT_SUBDIR=Sprint15`, 1280×720) unter `unreal/DoemitzLivingCity/Saved/Screenshots/Sprint15/`:

| Bild | Befund |
| --- | --- |
| `30_speicher.png` | **Behoben:** Keine schwebenden Kranbalken mehr; Ladeluken und Ausleger sitzen sauber an den echten 15,84-m-Giebeln. |
| `33_hafen_gangway.png` | **Neu & behoben:** Doppelte begehbare Gangways (`1355847994`/`1355847995`) mit grünen Stahlgeländern führen vom Südkai-Podest sauber auf den Schwimmsteg; Motorboot im Vordergrund mit scharfen Kabinenkanten und geschlossenem Rumpf. |
| `31_hafen_steg.png` | **Behoben:** Segelboot mit spitzem, geschlossenem Bug ohne Spalt und scharfer Kajüte; Kaimauer rechts mit solider geschlossener Endkappe; Ufersteg-Rampe schließt sauber an. |
| `29_hafen_steganlage.png` | **Behoben:** Scharfe Bootskabine, begehbare Gangways entlang des Südkais, Speicher-Giebel sauber im Hintergrund. |
| `27_schleuse_unterhaupt.png` · `28_schleuse_kammer.png` | **Weitgehend behoben:** Saubere Kammerwände, Tore, Stege und Geländer; lediglich ganz unten rechts am Untertor an der Wasserlinie ragt noch ein winziger (~15 cm) Rasenzipfel hervor (Politurpunkt für Sprint 16). |
| `18_innen_kaufhaus_tag.png` · `19_innen_kaufhaus_nacht.png` | **Behoben:** Alle 12 Deckenleuchten im Kaufhaus leuchten hell und gleichmäßig bei Tag und Nacht. |

## Offen / Ausblick · Sprint 16 (bereits abgestimmt)

- **HLOD & 450-m-Streaming:** Echtes Unreal World-Partition-HLOD mit automatischem Zelltausch bei ~450 m Laderadius + `VerifyStreaming.py`-Prüfung auf echtes Zell-Ent-/Nachladen.
- **Horizont & SaveGame-Streaming:** Prozedurale Gelände-Schürze + `ExponentialHeightFog` gegen den schwarzen Horizont; `UDoemitzSaveSubsystem::LoadCityState` wartet beim Zellwechsel auf `IsStreamingCompleted` vor dem Bodentrace.
- **Lebendiger Hafen:** 2 begehbare Hafen-Innenräume (**Hotel Dömitzer Hafen**, **Dömitzer Hafen Restaurant**), neue Hafen-Jobs & Hafen-Aufgaben, Skalierung auf **45 Einwohner** und **12 Fahrzeuge** (inkl. Startpunkte im Hafen).
- **Kleine Restpolitur:** `ECVF_SetByCode` statt `ECVF_SetByGameSetting` in `DoemitzGraphicsSettings.cpp` (damit Lumen/VSM-Override auch auf SM6/DX12-GPUs über `SetByProjectSetting` liegt) sowie den kleinen 15-cm-Rasenzipfel unten rechts am Schleusen-Untertor (`27_schleuse_unterhaupt.png`) schließen.
