# Sprint 9 · Wirtschaft und Interaktion an Gebäudeeingängen

Stand: Abgeschlossen (21.11.2026).

## Ausgangslage nach Sprint 8

Nach Sprint 8 (`5e40033`) liefen Kalender, Öffnungszeiten, 30 Einwohner und Straßenverkehr stabil. In Sprint 9 wurden die offenen Aufräumpunkte geschlossen und die ersten Spielerhandlungen umgesetzt: Gebäudeeingänge, Interaktionstaste `E`, Geldbestand in Cent, Einkaufen mit Inventar, Schichtarbeit mit anteiliger Lohnabrechnung, Einwohner als Kunden sowie SaveGame v4.

## Meilensteine und Abnahme

| Meilenstein | Status | Ergebnis |
| --- | --- | --- |
| 0 · Aufräumen | Erfüllt | Überholtes `VerifyTraffic.py` entfernt, `VerifyCitizens.py` auf 30 Einwohner + Pool umgestellt, alle **11 gültigen PIE-Skripte** in [Verify-All.ps1](../scripts/Verify-All.ps1) gebündelt. [README.md](../README.md) verlinkt Sprint 8 und 9 sowie `pois.geojson`. Remote-Sicherung bleibt eine offene Product-Owner-Entscheidung (kein Remote konfiguriert). |
| 1 · Gebäudeeingänge | Erfüllt | [export.py](../tools/geo_import/export.py) extrahiert OSM-`entrance=*`-Knoten; [citizens.py](../tools/mesh_generator/citizens.py) erzeugt je Ort genau einen Eingang mit stabiler ID (`entrance:<place_id>`). Herkunft je Eingang dokumentiert: `1` aus OSM (`entrance=*`), `56` als `assumed_sidewalk_access` gekennzeichnet. |
| 2 · Interaktion | Erfüllt | [DoemitzInteractionComponent.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Interaction/DoemitzInteractionComponent.h) / [DoemitzInteractionComponent.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Interaction/DoemitzInteractionComponent.cpp) an `ADoemitzCharacter` findet den nächsten Eingang im Umkreis von `2 m` (`200 cm`). Das HUD ([DoemitzClockWidget.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/UI/DoemitzClockWidget.cpp)) zeigt z. B. `E - Fritz-Reuter-Apotheke (geoeffnet bis 12:30)` bzw. `Fritz-Reuter-Apotheke (geschlossen, oeffnet Mo 08:00)`. `E` öffnet [DoemitzPlaceMenuWidget.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/UI/DoemitzPlaceMenuWidget.cpp); geschlossene Orte werden mit Meldung abgewiesen. |
| 3 · Geldbestand | Erfüllt | `UDoemitzSimulationSubsystem` führt `PlayerMoneyCents` als `int64` (keine Gleitkommazahlen) mit Startguthaben `125,00 EUR` (`12500` Cent, `assumed_starting_balance`) aus dem Data Asset. Jede Buchung landet mit laufender ID, Zeitpunkt, Ort und Betrag in `LedgerEntries` (letzte 200). Das HUD zeigt `Konto: 125,00 EUR`. |
| 4 · Einkaufen | Erfüllt | Versioniertes Manifest [doemitz-altstadt-economy.json](../data/manifests/doemitz-altstadt-economy.json) mit 4 Sortimentskategorien (`pharmacy`, `shop`, `gastronomy`, `tourism`, **16 Artikel**, alle Preise als `assumed_fictional_price`), validiert durch [economy.py](../tools/mesh_generator/economy.py) und beim Import als Data Asset `/Game/Generated/DoemitzAltstadt/DA_DoemitzEconomy` ([DoemitzEconomyDataAsset.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Economy/DoemitzEconomyDataAsset.h)) gespeichert – nichts in C++ hartcodiert. Kauf bucht ab, legt Artikel ins Inventar (`ItemId × Anzahl`) und lehnt Käufe ohne Deckung mit Meldung ab. |
| 5 · Arbeiten | Erfüllt | 4 Stellen im Manifest (`place_kaufhaus`, `Touristeninformation`, `Elb-Cafe`, `Fritz-Reuter-Apotheke`, alle Löhne als `assumed_fictional_wage`). Annahme am Eingang (`AcceptJob`), Schichtbeginn blendet die Figur aus und setzt die Zeit auf `15x` (`900.0`) bis Schichtende, anschließend Lohnbuchung. Unpünktlichkeit kürzt den Lohn anteilig nach tatsächlich gearbeiteten Minuten. |
| 6 · Einwohner als Kunden | Erfüllt | `Shopping`-Aufenthalte der Einwohner erzeugen deterministischen Umsatz (`EconomySeed 202609 + CitizenId + DayNumber + PlaceId`) am jeweiligen Ort. Jeder Ort führt Tages- und Wochenumsatz (Rücksetzung um Mitternacht bzw. Montag), sichtbar im Ortsmenü. |
| 7 · SaveGame v4 und Demo | Erfüllt | `SaveSchemaVersion = 4` ([DoemitzSaveGame.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Simulation/DoemitzSaveGame.h)) speichert Kontostand, Buchungen (letzte 200), Inventar, Arbeitsstelle und Ortsumsätze. Spielstände v1–v3 werden automatisch migriert (Startguthaben, leeres Inventar). Win64-Testbuild erstellt und verifiziert. |

## Benchmark-Ergebnisse (1920 × 1080, Test-PC)

Test-PC: `Intel Core i5-1135G7 @ 2.40 GHz`, `Intel Iris Xe Graphics`, `16 GB RAM`, Windows 11.
Messstrecke: `Goethestraße → Rathausplatz → Festungszugang` (326,4 m, 90 s Messzeit nach 3 s Warmup), **30 Einwohner (150-m-Pool)**, **5 Fahrzeuge**, **4 Überwege**, **57 Gebäudeeingänge**, **Wirtschaftssystem aktiv**.

| Messung | Lauf 1 (Ø FPS / Ø ms / P95 / P99) | Lauf 2 (Ø FPS / Ø ms / P95 / P99) | Abweichung | `stat unit` Ø (Game / Draw / GPU) |
| --- | --- | --- | --- | --- |
| Sprint 8 Vergleich (`DoemitzLow`) | **58,14 FPS** / 17,20 ms / 20,57 ms / 24,15 ms | **58,39 FPS** / 17,13 ms / 20,22 ms / 21,94 ms | 0,4 % | 3,58 / 13,73 / 17,16 ms |
| Sprint 9 Final (`DoemitzLow`) | **61,65 FPS** / 16,22 ms / 18,40 ms / 20,02 ms | **60,62 FPS** / 16,50 ms / 19,15 ms / 20,39 ms | 1,7 % | 3,49 / 13,18 / 16,36 ms |

Das Performance-Budget (≥ 15 FPS, maximal 20 % Verlust gegenüber Sprint 8) wird mit **61,13 FPS** im Mittel übertroffen.

## Prüfungen

- **Offline-Build und Python-Tests:** `geo_import build` (`146` Straßen, `645` Gebäude, `3` Wasserflächen, `121` POIs, `0` Geometriefehler) + `mesh_generator` (`57` Eingänge: `1` OSM / `56` Annahme, `16` Artikel, `4` Stellen) bytegleich bei Wiederholung (`SHA-256: CE34818ECD7780D8BE6AC8EE51FE5294B98D0A71954917EBD97BABA725332DC2`). Alle **17 Python-Tests** (`test_geo_import.py`, `test_mesh_generator.py`, `test_road_graph.py`, `test_sprint08.py`, [test_sprint09.py](../tests/test_sprint09.py)) bestanden.
- **Editor-Build & Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) kompiliert. `Import-Altstadt.ps1` bestand mit `DOEMITZ_ECONOMY_IMPORT_OK: start=12500 ct, 4 categories, 4 jobs -> /Game/Generated/DoemitzAltstadt/DA_DoemitzEconomy`, `DOEMITZ_CITIZENS_IMPORT_OK: 30 citizens, 57 places, 238 routes, 6 mesh variants` und `DOEMITZ_IMPORT_OK: 23 meshes, 35.4291 m reference, 0.0372% error, terrain, roof and wall collision passed, sidewalk collision passed`.
- **Play-Modus (PIE via `scripts/Verify-All.ps1`) – 11 / 11 bestanden:**
  - `VerifySprint.py`: `DOEMITZ_SPRINT_PIE_OK` (`600.0 -> 750.0 -> 600.0 cm/s`)
  - `VerifySidewalk.py`: `DOEMITZ_SIDEWALK_PIE_OK` (`crossed 339.9 cm onto sidewalk and returned`)
  - `VerifyCitizens.py`: `DOEMITZ_CITIZENS_PIE_OK` (`30 citizens simulated`, Anna → Amtsverwaltung, Bernd → Kaufhaus)
  - `VerifyDayNightHud.py`: `DOEMITZ_DAYNIGHT_HUD_PIE_OK`
  - `VerifyTrafficNetwork.py`: `DOEMITZ_TRAFFIC_NETWORK_PIE_OK` (`5 vehicles`, `min_pair_dist=2733.8 cm`, Rechts vor links)
  - `VerifyCalendar.py`: `DOEMITZ_CALENDAR_PIE_OK`
  - `VerifyCitizenLod.py`: `DOEMITZ_CITIZEN_LOD_PIE_OK` (`delta=0.00 cm`)
  - `VerifyCrossing.py`: `DOEMITZ_CROSSING_PIE_OK` (`osm:node:1125976999`)
  - `VerifyInteraction.py`: `DOEMITZ_INTERACTION_PIE_OK` (Eingang `entrance:poi:osm:node:1794647095`, Prompt geöffnet/geschlossen, Menü geöffnet/geschlossen, geschlossener Ort abgewiesen)
  - `VerifyEconomy.py`: `DOEMITZ_ECONOMY_PIE_OK` (Kauf `-395 ct`, Deckungsprüfung, 1 h verspätete Schicht `+4350 ct`, Einwohner-Kundenumsatz Kaufhaus `680 ct`)
  - `VerifySaveGame.py`: `DOEMITZ_SAVEGAME_PIE_OK` (SaveGame v4 inkl. Kontostand/Inventar/Stelle/Umsatz + `v3 -> v4`-Migration)
- **Windows-Testbuild:** `Win64Sprint09` neu erstellt. Parameterloser Start loggt `DoemitzLow profile applied: 23/68 street point lights kept active` und `Doemitz economy configured: start=125,00 EUR, 4 categories, 4 jobs (seed=202609)`. Zwei `DoemitzLow`-Benchmarks verifiziert. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint09/DoemitzLivingCity.exe)

## Ausblick

| Sprint | Schwerpunkt |
| --- | --- |
| 10 | UMG-Stadtkarte mit Einwohnern, Fahrzeugen und Orten, erste Aufgaben (z. B. Botengang mit Lohn), Ampeln und Parken |
| 11 | DGM1-Terrain: Höhen für Boden, Straßen, Gehwege und Gebäudesockel, Elbufer und Festungswall |
