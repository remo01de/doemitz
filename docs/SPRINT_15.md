# Sprint 15 · Fundament, Architektur & Durchgängige Stadt

Stand: Geplant und in Umsetzung (abgestimmt am 23.11.2026 nach Revision von Sprint 14).

## Ausgangslage nach Sprint 14

Sprint 14 (`8b57ae4`) erweiterte Dömitz auf 1,11 km² bis zum Hafen und zur Schleuse Dömitz (44,3–48,1 FPS auf `DoemitzLow`). Die Revision nach Sprint 14 deckte jedoch sechs vorrangige Mängel auf, die vor weiterem Welt- und Inhaltswachstum behoben werden müssen:

1. **Abgeschnittene Hafen-Halbinsel & isolierte Festung:** Der Ostrand `11,2607° E` schnitt die einzige reale Straßenverbindung (`Werderstraße` ↔ `Am Hafen`) ca. 90 m vor der Kreuzung ab. Dadurch lagen Hotel Dömitzer Hafen, Speicher, Hafenrestaurant, Panorama Café, Strandbar und 3 Hafenparkplätze auf einer isolierten Insel (50/245 Einwohnerrouten mit bis zu 258 m Luftlinie über Wasser; 3 Parkplätze 105–170 m quer übers Wasser gebunden). Zudem blieben die in Sprint 12/13 gebauten Festungstunnel (`Festungstor`, `NW-Steg`) in `citizens.py` aus dem Fußgängergraphen ausgeschlossen.
2. **Einwohner-Zeitskala vs. Uhr (`TimeScale = 60`):** Echtzeit-Fußwege (`1,35 m/s`) gegen `1 s = 1 Spielminute` machten auf der gewachsenen Karte 59,7 % aller Werktags-Etappen und 89,3 % aller Werktags-Einkaufswege bei `1x` unerreichbar (28/30 Einwohner betroffen); `StartTrip` setzte nicht angekommene Einwohner an den Startort zurück.
3. **Innenraum-Beleuchtung in `DoemitzLow`:** `DoemitzGraphicsSettings::ApplyProfile` blendete 2/3 aller `APointLight`-Actors pauschal aus – einschließlich der 20 Innenraum-Deckenlampen.
4. **Sicht- und Geometriefehler im Hafen:** Am Speicher am Hafen (`osm:way:42883863`) saßen 4 Kranbalken/Ladeluken schwebend auf den getreppten Seitenkanten statt an den Giebelseiten; Kaimauern hatten offene Stirnflächen und keinen begehbaren Zugang zu den Schwimmstegen; Boote zeigten Smooth-Shading-Artefakte an scharfen Rumpfkanten; am Schleusen-Unterhaupt ragte eine kleine Geländeecke ins Becken.
5. **Lizenz- & Workspace-Hygiene:** Im öffentlichen GitHub-Repo (`remo01de/doemitz`) waren seit Sprint 1/2 zehn unlizenzierte JPGs in `Images/` getrackt; `data/processed/` im Hauptverzeichnis stand noch auf Sprint 12, während der Sprint-14-Stand im Worktree `.claude/worktrees/next-implementation-steps-82d0a6` lag; ungenutzte Epic-Template-Animationen (`Death/`, `Pistol/`, `Rifle/`) und 16 alte lokale Builds belegten Speicher/LFS.
6. **C++-Monolith:** `DoemitzSimulationSubsystem.cpp` war auf 3.708 Zeilen angewachsen.

## Abgestimmte Designentscheidungen (PO-Freigabe 23.11.2026)

- **Ausschnitt:** Ostrand um ~180 m bis ca. `11,2630° E` erweitern (`min_lat = 53,1372°` unverändert), sodass genau 2 amtliche LAiV-Kacheln (`33_248_5894` + `33_250_5894`) genügen und die reale Kreuzung `Werderstraße / Am Hafen` vollständig im Gebiet liegt.
- **Hybrid-Zeitskala:** Basis-Uhr `BaseTimeScale = 20.0` (1 Spieltag = 72 Echtminuten; Stufen `1x / 2x / 5x / 15x` relativ dazu). Off-Screen-Einwohner (`> 150 m`) reisen in Spielzeit; sichtbare Einwohner und Fahrzeuge skalieren beim Zeitraffer mit; `StartTrip` startet ab aktueller Position ohne Rück-Teleport; entfernungsgewichtete Zielwahl.
- **C++-Architektur (6 `UWorldSubsystem`-Klassen):** Volle Aufteilung mit zentraler, deterministischer Tick-Reihenfolge (`Simulation → Tasks/Economy → Citizens → Traffic`):
  - `UDoemitzSimulationSubsystem` (Kern: Uhr, Kalender, `BaseTimeScale`, Orte, Öffnungszeiten, Innenräume, Stadtkarte, Benachrichtigungen, Tick-Steuerung)
  - `UDoemitzCitizenSubsystem` (Einwohner, Routen, Hybrid-Zeitskala, LOD-Pool, Gesprächspause, Innenraum-Stehplätze)
  - `UDoemitzTrafficSubsystem` (Straßengraph, Fahrzeuge, Vorfahrt/Stoppschilder, Überwege, Parkplätze)
  - `UDoemitzEconomySubsystem` (Konto in Cent, Journal, Inventar, Sortimente, Jobs/Schichten, Ortsumsätze)
  - `UDoemitzTaskSubsystem` (Tagesaufgaben, Fristen, Botengänge/Besorgungen, Aushang)
  - `UDoemitzSaveSubsystem` (SaveGame v1–v7 Speichern/Laden/Migration, Bodentrace)
- **Lizenz- & LFS-Strategie:** `Images/` vollständig aus HEAD und Git-Historie entfernen und per `.gitignore` ausschließen; generierte Stadt-Assets bleiben in Git LFS (direkt spielbar nach `git clone`), aber ungenutzte Template-Assets und alte lokale `Saved/Builds/`-Archive werden bereinigt.
- **Sprint-Schnitt:** Sprint 15 löst Fundament, Konnektivität, 6-Subsystem-Umbau, Hybrid-Zeitskala und Sicht-/Lichtfehler; **Sprint 16** liefert darauf aufbauend echtes Unreal-HLOD (450-m-Laderadius), Gelände-Schürze/Höhennebel, asynchrones SaveGame-Streaming sowie 2 begehbare Hafen-Innenräume (`Hotel Dömitzer Hafen`, `Dömitzer Hafen Restaurant`) und Skalierung auf 45 Einwohner / 12 Fahrzeuge.

## Meilensteine

| Nr. | Meilenstein | Abnahmekriterien |
| --- | --- | --- |
| 0 | Hygiene, History-Rewrite & Workspace | Worktree aufgelöst; `Images/` aus HEAD + Git-Historie entfernt und in `.gitignore`; ungenutzte Template-Assets (`Death/`, `Pistol/`, `Rifle/`) und alte lokale Builds bereinigt; Haupt-Workspace synchron. |
| 1 | Durchgängiges Netz (2. Kachel + Tunnel) | `bounds_lonlat = [11.2428, 53.1372, 11.2630, 53.1455]`, DGM1/LoD2-Kachel `33_250_5894` bezogen und im Report dokumentiert; `Festungstor` & `NW-Steg` im Fußgängergraphen. `0` Wasser-Sprünge in Einwohnerrouten; alle Parkplätze `< 40 m` an Hauptkomponente; durchgängige Straße Kaufhaus → Hotel Dömitzer Hafen. |
| 2 | 6-`UWorldSubsystem`-Split | 6 zyklenfreie `UWorldSubsystem`-Klassen mit deterministischem Tick; alle 19 C++-Dateien und alle PIE-Verify-Skripte umgestellt; SaveGame v1–v7-Migration vollständig funktionsfähig. |
| 3 | Hybrid-Zeitskala (`20x`) | Konfigurierbare `BaseTimeScale = 20.0`, Off-Screen-Spielzeit (`> 150 m`), Zeitraffer-Kopplung für sichtbare Einwohner & Fahrzeuge, `StartTrip` ohne Rück-Teleport, entfernungsgewichtete Zielwahl; `VerifyEconomy.py`-Workaround (`30.0`) entfernt. ≥ 95 % aller Werktags-Etappen bei `1x` pünktlich erreichbar. |
| 4 | Sicht-, Licht- & Qualitätsfixes | `DoemitzLow` drosselt nur Straßenlaternen (alle 20 Innenraumlampen bleiben aktiv); Speicher-Giebel nach Firstrichtung ohne schwebende Kranbalken; Kaimauer-Endkappen & Stegzugangsrampen; `width`-Einheiten-Parser; Split-Normals für Boot-Rümpfe; Schleusen-Unterhaupt-Ecke bereinigt; SaveGame-Trace filtert `SM_LockRailing`/`SM_PierPile`; Doku & Karten-Attribution (`2025/2026`) aktuell. |
| 5 | Prüfungen, Sichtprüfung & Build | Vollständige Python-Testsuite (inkl. `tests/test_sprint15.py`), C++-Editor-Build, `Import-Altstadt.ps1`, `Verify-All.ps1`, Screenshot-Sichtprüfung (Speicher, Hafenstege, Schleuse, Innenräume unter `DoemitzLow`), Win64-Build und `DoemitzLow`-Benchmarks (Altstadt + Hafen ≥ 15 FPS). |

## Ausblick · Sprint 16 (bereits abgestimmt)

- **HLOD & 450-m-Streaming:** Echtes Unreal World-Partition-HLOD mit automatischem Zelltausch bei ~450 m Laderadius + `VerifyStreaming.py`-Prüfung auf echtes Zell-Ent-/Nachladen.
- **Horizont & SaveGame-Streaming:** Prozedurale Gelände-Schürze + `ExponentialHeightFog` gegen den schwarzen Horizont; `UDoemitzSaveSubsystem::LoadCityState` wartet beim Zellwechsel auf `IsStreamingCompleted` vor dem Bodentrace.
- **Lebendiger Hafen:** 2 begehbare Hafen-Innenräume (**Hotel Dömitzer Hafen**, **Dömitzer Hafen Restaurant**), neue Hafen-Jobs & Hafen-Aufgaben, Skalierung auf **45 Einwohner** und **12 Fahrzeuge** (inkl. Startpunkte im Hafen).
