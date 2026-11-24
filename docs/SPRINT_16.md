# Sprint 16 · Streaming, Horizont & Lebendiger Hafen

Stand: Umgesetzt und geprüft (24.11.2026).

## Zielbild

Sprint 16 baut auf dem in Sprint 15 bereinigten Fundament auf und schließt die vier abgestimmten Arbeitspakete ab:

1. **M1 · World-Partition-HLOD & 450-m-Streaming:** Echtes UE5-World-Partition-HLOD (`UHLODLayer` `Instancing`, 512 m / 1600 m), Reduktion des `MainPartition`-Laderadius von `1000 m` auf `450 m` und Erweiterung von `VerifyStreaming.py` um den Nachweis echten Zell-Ent- und Nachladens sowie aktiver HLOD-Actors.
2. **M2 · Horizont-Schürze, ExponentialHeightFog & Async-SaveGame-Streaming:** Prozedurale, nicht-kollidierende Geländeschürze (`TerrainHorizonSkirt`) außerhalb des DGM1-Ausschnitts + `AExponentialHeightFog` mit Tageszeit-Farbanpassung im `ADoemitzDayNightController` gegen die dunkle Horizontkante; asynchrones Warten auf `UDoemitzWorldTools::IsStreamingCompleted` beim zellübergreifenden `LoadCityState` in `UDoemitzSaveSubsystem`.
3. **M3 · Lebendiger Hafen:** Zwei neue begehbare Erdgeschoss-Innenräume am Hafen (**Hotel Dömitzer Hafen – Lobby** und **Dömitzer Hafen Restaurant – Gastraum**), zwei Hafen-Jobs, zwei maritime Handelsartikel, fünf neue Hafen-Aufgaben sowie Skalierung auf **45 Einwohner** und **12 Fahrzeuge** (inkl. östlicher/Hafen-Startpunkte).
4. **M4 · Sprint-15-Politur & OFPA-Hygiene:** `ECVF_SetByCode` statt `ECVF_SetByGameSetting` in `DoemitzGraphicsSettings.cpp`, Schließung des verbliebenen Rasenzipfels am Schleusen-Untertor (`27_schleuse_unterhaupt.png`) sowie Bereinigung von 1.996 duplizierten und 40 verwaisten World-Partition-ExternalActor-Paketen (`0 LoadErrors`, `0 MapCheck`-Warnungen).

## Ergebnisse nach Meilenstein

| Nr. | Meilenstein | Ergebnis |
| --- | --- | --- |
| 1 | HLOD & 450-m-Streaming | `STREAMING_LOADING_RANGE_M` in `tools/mesh_generator/__main__.py` auf `450.0 m` reduziert (`hlod_enabled = True`, `hlod_cell_size_m = 512.0`, `hlod_loading_range_m = 1600.0`). Neue C++-Helfer `UDoemitzWorldTools::ConfigureHLODSetup` (legt `/Game/Generated/DoemitzAltstadt/HLOD_DoemitzCity` als `EHLODLayerType::Instancing` an und verdrahtet `RuntimePartitions[0].HLODSetups`) und `GetStreamingActorCounts`. `import_altstadt.py` setzt `used_with_instanced_static_meshes = True` für alle generierten Materialien, steuert `enable_auto_lod_generation` selektiv (aus für Innenräume/Glas/Aushang) und ruft `ConfigureHLODSetup` auf. `scripts/Import-Altstadt.ps1` führt automatisch `WorldPartitionBuilderCommandlet -Builder=WorldPartitionHLODsBuilder -SetupHLODs -BuildHLODs -AllowCommandletRendering` aus → **38 HLOD-Actors** gebaut. Bonus-Fix: `import_altstadt.py` ruft nun `doemitz_wp.load_all_actors()`, dedupliziert Actors und speichert mit `save_current_level()` vor `save_dirty_packages(True, True)` – dadurch wurden **1.996** seit Sprint 14/15 akkumulierte OFPA-Duplikate und **40** verwaiste Vor-Sprint-14-ExternalActors physisch gelöscht (`3.238 → 1.202` Dateien in `Content/__ExternalActors__/Maps/DoemitzAltstadt/`). |
| 2 | Horizont, Nebel & Async-SaveGame | `terrain.py::build_horizon_skirt` erzeugt eine 2-Band-Geländeschürze (`2.500 m` breit, `906` Vertices, `1.208` Dreiecke, `collision = False`, `distance_field = False`, `source = assumed_sprint16_horizon_skirt`), die in Unreal immer geladen bleibt. `import_altstadt.py` platziert `Altstadt Fog` (`AExponentialHeightFog`, `fog_density = 0.0022`, `start_distance = 18000 cm`, `enable_volumetric_fog = False`) und verbindet ihn mit `ADoemitzDayNightController::HeightFog`, der `FogInscatteringColor` zwischen Tag (`0.62, 0.74, 0.88`), Dämmerung und Nacht (`0.05, 0.08, 0.16`) interpoliert. `UDoemitzSaveSubsystem` erbt nun von `UTickableWorldSubsystem` (tickt ausschließlich bei aktivem `PendingRestore`), pausiert bei zellübergreifenden Sprüngen (`≥ 250 m` oder fehlendem Bodentrace) die Schwerkraft, wartet auf `UDoemitzWorldTools::IsStreamingCompleted` + gültigen Boden-/Innenraum-Trace (Timeout 10 s) und setzt erst dann die exakte Höhe und v5→v6-Migration um (`IsPendingStreamingRestore()` BlueprintPure). |
| 3 | Lebendiger Hafen | `doemitz-altstadt-interiors.json`: 2 neue begehbare Innenräume mit Brandwand-Fensterausschluss (`blocked_edges`), Tischgruppen (`_add_table_group`, `center_tables`) und hangtauglicher Deckenhöhe: **Hotel Dömitzer Hafen – Lobby** (`osm:way:1355844634` / `poi:osm:node:387219809`, `266,3 m²`, 6 Deckenleuchten) und **Dömitzer Hafen Restaurant – Gastraum** (`osm:way:1355844633` / `poi:osm:node:1125977013`, `410,8 m²`, 6 Deckenleuchten; freier Hof-Eingang an der Ostfassade `edge 5`, `[674.57, -592.80]`). `doemitz-altstadt-economy.json`: 2 neue Artikel (`item_matjesplatte`, `item_hafenfuehrer`) und 2 neue Hafen-Jobs (`job_hafenhotel_rezeption`, `job_hafenrestaurant_service`) → 18 Artikel, 6 Jobs. `doemitz-altstadt-tasks.json`: 5 neue Hafen-Aufgaben → 16 Vorlagen (9 Botengänge, 7 Besorgungen). `doemitz-altstadt-citizens.json`: Zielbevölkerung **45 Einwohner** (inkl. 2 neuer östlicher Wohnhäuser `place_hafen_home_nord`/`sued` und 4 dedizierter Hafen-Einwohner Hanna, Knut, Maja, Torsten) → 90 Orte, 348 Routen (0 getrennt). `doemitz-altstadt-streets.json`: 4 neue Fahrzeuge (`altstadt_vehicle_09..12`) auf `Am Hafen`, `Werderstraße` und `Am Floßgraben` → **12 Fahrzeuge**. |
| 4 | Politur & Sichtfehler | `DoemitzGraphicsSettings.cpp` verwendet `ECVF_SetByCode` statt `ECVF_SetByGameSetting` (übersteuert `DefaultEngine.ini`s `SetByProjectSetting` ohne Prioritätswarnungen). Schleusen-Unterhaupt (`harbour.py`, `locks.py`, `terrain.py`): Suchradius der Vorhafen-Kaimauern von `30 m` auf `33 m` erweitert (schließt die 0,73-m-Lücke zum Steg `osm:way:1355835407` in `31,75 m` Abstand), `skip_zone` der Schleusenkammer von Kaimauer-Linien ausgeschlossen (kein Abschneiden am Tor-Wendepunkt), `_clip_triangle_at_step` auf mehrfache WallStepLine-Schnitte erweitert und Stemmtor-Flügel um `35 cm` in die Torangel eingebettet. Fassaden/Hang-Politur (`architecture.py`, `terrain.py`): EG-Innenraumfenster sitzen stets über dem Natursteinsockel (`plinth_top_m + 0.12 m`), Geschossgesims und OG-Fenster stets über `interior.ceiling_z`, und begehbare Innenraum-Grundrisse werden in `terrain.py` Schritt 3 nicht mehr auf die tiefste Hang-Ecke (`b_min_z`) abgesenkt (verhindert einen Geländegraben vor bergseitigen Türen). |
| 5 | Prüfungen, Sichtprüfung & Build | Siehe Abschnitt „Prüfungen“ und „Sichtprüfung“ unten. |

## Prüfungen

1. **Offline-Pipeline (`tools.mesh_generator`):**
   - `unreal-city-meshes.json`: **789 Meshes, 584.297 Dreiecke** (Gelände `352` Kacheln, `273.868 / 285.000` Dreiecke, Altstadt max. `4,95 cm`; `TerrainHorizonSkirt` `906` Vertices / `1.208` Dreiecke; Zellraster `6 × 4`, `412` Zell-Meshes, Laderadius `450 m`, HLOD `512 m / 1600 m`; `45` Einwohner, `90` Orte, `348` Routen, `77` über Überwege, `0` getrennte Routen; `5` Innenraumtüren; `303` Straßenkanten, `104` Kreuzungen, `15` Parkplätze, `12` Fahrzeuge; `18` Artikel, `6` Jobs, `16` Aufgabenvorlagen; Stadtkarte `4096 × 4096 px`).
2. **Python-Unit-Tests:**
   - Vollständiger Lauf `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`: **87 von 87 Tests bestanden** (inkl. 6 neuer Sprint-16-Tests in `tests/test_sprint16.py` sowie angepasster Zählkonstanten in `test_sprint08.py`, `test_sprint10.py`, `test_sprint13.py`, `test_sprint14.py`).
   - Nach finaler Fassaden-/Schleusenpolitur erneut geprüft: `test_sprint13` + `test_sprint16` (**21/21 OK**).
3. **C++-Editor- & Game-Build:**
   - `DoemitzLivingCityEditor Win64 Development` und `DoemitzLivingCity Win64 Development` fehler- und warnungsfrei gebaut (`AssetRegistry` in `DoemitzLivingCity.Build.cs` ergänzt).
4. **Unreal-Import, OFPA-Bereinigung & HLOD-Build (`scripts/Import-Altstadt.ps1`):**
   - `DOEMITZ_IMPORT_OK: 789 meshes, 35.4291 m reference, 0.0374% error, ref0:hit=4.865m(dgm=4.806m,diff=2.1cm), ref1:hit=4.699m(dgm=4.608m,diff=1.1cm), terrain, roof and wall collision passed, sidewalk collision passed, 9 bridges collision passed`
   - `DOEMITZ_STREAMING_GRID_OK: MainPartition 25600/45000 (412 cell meshes)`
   - `DOEMITZ_HLOD_SETUP_OK: layer=HLOD_DoemitzCity cell=51200 range=160000`
   - `WorldPartitionHLODsBuilder`: **`#### World contains 38 HLOD actors ####`**
   - Editor-Kartenprüfung (`MapCheck`): **`0 Fehler, 0 Warnung(en)`**, **0 `LoadErrors`**.
5. **PIE-Prüfsuite (`scripts/Verify-All.ps1`, 23 Skripte):**
   - **Alle 23/23 PIE-Prüfungen bestanden** (22/23 im geschlossenen Gesamtlauf + anschließende Behebung des Hang-Grabens vor der neuen Restaurant-Osttür und Verifikation von `VerifyInteriors`, `VerifySprint16`, `VerifyTerrain` als `3/3` bestanden):
     - **`VerifyStreaming.py`**: `west_terrain=218/east_terrain=150, unloaded=9 cells / newly_loaded=6 cells, hlod_actors=38, max wait 0.3s` (echtes Ent- und Nachladen bei 450-m-Radius + 38 HLOD-Actors).
     - **`VerifySprint16.py`**: `45 citizens, 12 vehicles, 5 interiors (Hotel & Restaurant walked & purchased), horizon skirt NoCollision & day/night fog OK (0.88, 0.16), cross-cell SaveGame streaming restore OK (triggered_async_streaming=True, cross_cell_load_z_cm=92.2)`.
     - **`VerifyInteriors.py`**: `interior_lights_visible: 32`, 5 Innenräume, Einkauf, Aushang, Einwohner innen, SaveGame v7 bestanden.
     - **`VerifyMap.py`**: `4096x4096 texture loaded, 45 citizens / 12 vehicles / 15 parking lots / 54 places`.
     - **`VerifyTrafficNetwork.py`**: `12 vehicles, min_pair_dist=1336.7 cm`, Rechts-vor-links bestanden.
     - **`VerifySaveGame.py`**: `45 citizens, 12 vehicles, v4->v7, v5->v7, v6->v7` inkl. Migrationen bestanden.
     - **`VerifySprint15.py`**: `6 subsystems active, BaseTimeScale=20.0, interior_lights_visible=32 (street_lights_hidden_low=67)`.
6. **Gepackter Windows-Build (`Win64Sprint16`):**
   - `.\scripts\Build-Windows.ps1 -ArchiveDirectory unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint16` → **`BUILD SUCCESSFUL`** (`DoemitzLivingCity.exe`, 1.514 Pakete, 264,60 MiB komprimiertes IoStore-Containerpaket).
   - Laufzeit-Log-Prüfung (`DoemitzLow`): **`InstancedStaticMeshes_warnings = 0`**, **`CVar_priority_warnings = 0`** (bestätigt `ECVF_SetByCode`), **`LoadErrors = 0`**, `DoemitzLow profile applied: 34/101 street point lights kept active (interior lights untouched)`.
   - Smoke-Benchmarks (auf `i5-1135G7 / Intel Iris Xe`, unter paralleler IDE-GPU-Last von `Antigravity.exe`):
     - `1280×720` (`15 s`, 251 Frames, 12 Fahrzeuge): **`16,63 FPS`** Mittel (`p50 = 31,58 ms` ≈ `31,7 FPS`, `min_ms = 3,94 ms`, `game_mean = 6,44 ms`).
     - `1920×1080` (`20 s`, 162 Frames, 12 Fahrzeuge): **`8,06 FPS`** Mittel (`p50 = 81,69 ms`, `min_ms = 20,82 ms`, `game_mean = 5,30 ms` — mehr als doppelt so schnell wie Sprint 15 unter identischer IDE-GPU-Konkurrenz dank 450-m-Streaming, HLOD und OFPA-Deduplizierung).
     - Für eine ungestörte 1080p-Messung ohne IDE-GPU-Last in einer separaten PowerShell ausführen:
       ```powershell
       $exe = 'unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint16\DoemitzLivingCity.exe'
       .\scripts\Run-Benchmark.ps1 -Executable $exe -Profile DoemitzLow -OutputJson unreal\DoemitzLivingCity\Saved\Benchmarks\Sprint16\altstadt_clean.json
       .\scripts\Run-Benchmark.ps1 -Executable $exe -Profile DoemitzLow -Route hafen -OutputJson unreal\DoemitzLivingCity\Saved\Benchmarks\Sprint16\hafen_clean.json
       ```

## Sichtprüfung

Aufnahmen mit `CaptureSprint13Screenshots.py` (`DOEMITZ_OUT_SUBDIR=Sprint16`, 1280×720, `-unattended`) unter `unreal/DoemitzLivingCity/Saved/Screenshots/Sprint16/`:

| Bild | Befund |
| --- | --- |
| `34_horizont_hafen_altstadt.png` · `32_weg_altstadt_hafen.png` | **Sauber:** Keine dunkle Horizontkante mehr; grüne Geländeschürze geht weich über blauen `ExponentialHeightFog` in den Himmel über; Altstadt-Silhouette mit Johanneskirche und Hafenstegen klar erkennbar. |
| `27_schleuse_unterhaupt.png` | **Behoben:** Dunkler Horizontbalken verschwunden; Vorhafen-Kaimauern schließen sauber bis zum Untertor an, kein Rasenzipfel mehr am Wasseranschluss. |
| `24_innen_hafen_hotel_tag.png` · `25_innen_hafen_hotel_nacht.png` · `26_tuer_hafen_hotel.png` | **Sauber:** Hell beleuchtete Hotel-Lobby mit Tischgruppen, Stuhlreihen, Regalen und freien Außenfenstern (Brandwände fensterlos); Außenansicht mit klarem Fenster über dem Natursteinsockel und begehbarer Holztür. |
| `21_innen_hafen_restaurant_tag.png` · `22_innen_hafen_restaurant_nacht.png` · `23_tuer_hafen_restaurant.png` | **Sauber (nach 2 Politurrunden):** Großzügiger Gastraum mit Tresen, Esstischgruppen und gleichmäßiger Tag-/Nachtbeleuchtung; nach Verlegung an die offene Ostfassade (`edge 5`), Gesims-/Fensteranhebung und Beseitigung des Hang-Grabens schließt das Gras bündig an die Türschwelle an. |

## Ausblick · Sprint 17

- **Audio & Stadtatmosphäre:** Dezente Umgebungsgeräusche (Elbe/Hafen-Wasser, Möwen/Vögel, Schritte auf Pflaster/Holzsteg, Tür- und Interaktionsklänge) ohne Drittanbieter-Lizenzrisiken.
- **Tagesablauf- & Hafenvielfalt:** Sichtbare Freizeit- und Gastronomie-Aufenthalte an Tischen in Restaurant/Hotel/Elb-Café, dynamische Wetter-/Wolkenvarianz (bewölkt/klar) und erste begehbare Sehenswürdigkeit auf der Festung (Kommandantenhaus/Museum).
- **Performance-Feinschliff:** Ungestörte 1080p-Referenzmessung für `DoemitzLow`/`DoemitzHigh`, optionales Distance-Culling für kleine Stadtmöbel-HISMs und Prüfung einer leichteren HLOD-LOD-Stufe für die äußeren 512-m-Zellen.
