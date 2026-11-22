# Sprint 12 · Reale Gebäudehöhen und markante Bauwerke

Stand: Umgesetzt und geprüft.

## Ausgangslage nach Sprint 11.1

Sprint 11.1 war als `a2b4361` auf `main` committet. Aus der Nachprüfung bestanden zwei Aufgaben für Sprint 12:

1. **Nordwest-Holzsteg (`bridge:osm:way:120432334`):** Das Ostende trifft auf den Tunnelweg `osm:way:416256369` (`tunnel=yes`, `layer=-1`), der auf ~16,4–16,7 m NHN durch den Festungswall führt. Weil Tunnelwege nicht als Widerlageranschluss zählten, griff die Ausweichregel „höchster DGM-Wert im 3-m-Umkreis“ und fand die Wallkrone (21,17 m NHN), wodurch der Steg mit 12,41 % anstieg.
2. **Fehlende Gebäudehöhen in OSM:** Von 645 OSM-Gebäuden besaßen 0 eine `height`, 7 `building:levels` und 0 `roof:shape`. Fast alle Gebäude – einschließlich Johanneskirche, Rathaus und Festungsbauten – standen daher mit der Annahme 6,5 m und generierter Dachform.

## Umgesetzte Meilensteine

| Meilenstein | Umsetzung & Nachweis |
| --- | --- |
| 0 · Nachbesserung Steg und Sicherung | Tunnelwege (`tunnel=yes`) zählen in `tools/mesh_generator/road_elevation.py` als gültige Brückenanschlüsse (`tunnel_portal_dgm` direkt am Portalknoten). Die Ausweichregel `assumed_max_dgm_3m_radius` greift nur noch bei völlig unverbundenen Enden und schreibt bei > 1 m Differenz zum Gegenwiderlager eine Warnung in den Report (`warnings`). Ergebnis für den NW-Steg (`bridge:osm:way:120432334`): Neigung von **12,41 % auf 0,27 %** gesenkt (`16,3385 m → 16,4452 m NHN`), Lichtraum **4,091 m**, `warnings = []`. Alle Fußgängerbrücken ohne OSM-`incline` liegen ≤ 1,35 % (Abnahme ≤ 6 %). Remote-Sicherung bleibt nach PO-Entscheidung offen (kein Remote konfiguriert). |
| 1 · LoD2-Gebäudemodelle beschaffen | Lizenz vor Download aus den amtlichen ISO-Metadaten des LAiV M-V (`CSW-ID 11d74a7f-d3ad-4900-b8e3-fa821cfad3b5`) geprüft: **CC BY 4.0** (`cc-by/4.0`), Quellenvermerk **`© GeoBasis-DE/M-V 2026`** (Lieferstand 2026-03-30). Versioniertes Lizenzmanifest [`data/manifests/doemitz-altstadt-lod2-license.json`](../data/manifests/doemitz-altstadt-lod2-license.json) und `lod2`-Konfiguration in [`data/manifests/doemitz-altstadt.json`](../data/manifests/doemitz-altstadt.json). Neuer Befehl `python -m tools.geo_import fetch-lod2` (`tools/geo_import/lod2.py`) lädt Kachel `lod2_33_248_5894_2_gml.zip` (1.347.457 B, 965 CityGML-Gebäude, SHA-256 `159d3c45b206b8b6ea6e0541951d2dceeb9745217bca024773ccabc3ff4fa072`) nach `data/raw/doemitz-altstadt/lod2/`; URL, Lieferjahr und SHA-256 stehen in `import-report.json`. |
| 2 · Höhen und Dächer aus LoD2 | OSM-Grundrisse und stabile OSM-IDs bleiben unverändert. Strikte 1:1-Flächenzuordnung in `tools/geo_import/lod2.py` (konfigurierbare Schwelle 60 %, kein LoD2-Gebäude doppelt vergeben): **617 von 645 OSM-Gebäuden (95,7 %)** aus LoD2 zugeordnet (Traufhöhe, Firsthöhe, AdV-Dachform → `flat`, `gabled`, `hipped`, `half-hipped`, `mansard`, `skillion`, `pyramidal`, sowie Firstrichtung/Pultneigung). Höhenquellen im Report: `lod2: 617`, `assumed_default: 24`, `reference_photo_estimate: 3` (geteilte Festungs-Teilpolygone in OSM), `osm_levels: 1`. Obere Dach-/Giebel-/Gauben-/Fial-Flächen werden sauber in `Gable*`-Meshes (identisches `Walls*`-Material, Kollision aktiv) getrennt, damit alle `Walls*`-Sockel streng bodenverankert bleiben. |
| 3 · Johanneskirche | Varianten-Generator in `tools/mesh_generator/landmarks.py` über [`data/manifests/doemitz-altstadt-landmarks.json`](../data/manifests/doemitz-altstadt-landmarks.json) (`osm:way:42551672`, `DEMVAL7600bmrAfo`, Überdeckung 98,55 %): neugotischer Backstein-Westturm mit exakter LoD2-Gesamthöhe **39,22 m** über Sockel (**57,38 m NHN**, höchstes Bauwerk im Ausschnitt), 4 Ecktürmchen (Fialen), Schiefer-Oktogonhelm, Turmuhr, Schallluken, NW-Eingangsportal, Kirchenschiff (`eave 11,25 m`), Querhausdach, polygonaler Chor, Strebepfeiler und Spitzbogen-Fensterachsen. Rein in Python generiert, keine Fremdassets. |
| 4 · Rathaus | Barockes Fachwerk-Rathaus (`osm:way:41020272`, `DEMVAL76000gbwej`, Überdeckung 97,62 %, `eave 9,63 m`, `ridge 14,80 m`) mit Fachwerk-Gliederung, Kreuzstockfenstern, rotem Mansardwalmdach, 3 Frontgauben, SW-Rathausturm und repräsentativem Eingangsportal zum Rathausplatz. Der Eingang `entrance:poi:osm:way:41020272` (`source: landmark_reference_door`) liegt direkt an der realen Vordertür (`[-66.7911, -215.9005, 4.9018] m`). |
| 5 · Festungsbauten und Brückendetails | Zeughaus (`osm:way:96029976`, `1360590722`, `eave 8,92 m`, `ridge 11,92 m`), Hauptwache (`osm:way:1360590724`, `96029971`, `1360590723`, `eave 9,06 m`, `ridge 11,83 m`), Kommandantenremise (`osm:way:96029975`, `eave 3,81 m`, `ridge 6,73 m`) und Arrestantenhaus (`osm:way:96029967`, `eave 8,30 m`, `ridge 15,38 m`) mit LoD2-Höhen und Backstein-/Putzfassaden nach Fotos. **Torbrücke** (`bridge:osm:way:29732766`) mit 3 Ziegelbögen und 2 Flusspfeilern (Lichtraum 5,736 m), **Steinbrücke** (`bridge:osm:way:94526517`) mit steinernem Gewölbebogen und Widerlagerpfeilern (Lichtraum 5,138 m). Am NW-Steg (`osm:way:416256369`): sichtbares Backstein-Bogenportal mit Fundamentanschluss, begehbares Tonnengewölbe (13,48 m Länge, 2,6 m × 3,1 m lichte Weite, als `assumed_sprint12_tunnel_portal` gekennzeichnet) und entsprechender Geländeausschnitt im Wall (`tunnel_corridors`). |
| 6 · Quellen, Sichtprüfung und Build | [`data/manifests/doemitz-altstadt-references.json`](../data/manifests/doemitz-altstadt-references.json) verzeichnet alle **11 Wikimedia-Commons-Referenzfotos** mit URL, Urheber, Lizenz, Lizenz-URL, Bauwerk und OSM-IDs (keine Bildkopien im Repo). Quellenvermerk im Spiel, in `docs/GEO_DATA.md` und `README.md` um `© GeoBasis-DE/M-V 2026` ergänzt. Win64-Standalone-Build (`Win64Sprint12`), Starttest und 2×90 s Benchmarks `DoemitzLow` durchgeführt. |

### Nebenerkenntnis & C++-Absicherung

Während der 17/17-PIE-Regression deckte `VerifySaveGame.py` auf, dass `TraceStaticGroundZ` in `DoemitzSimulationSubsystem.cpp` beim Laden eines SaveGames durch die neuen, realen Dachüberhänge auf Gehwegen eine Dachfläche statt den darunterliegenden Gehweg treffen konnte. `TraceStaticGroundZ` überspringt nun explizit Gebäudestrukturen (`SM_Roofs*`, `SM_Walls*`, `SM_Gable*`, `SM_StoneTrim*`, `SM_TimberTrim*`, `SM_Doors*`, `SM_Window*`, `SM_Shutters*`, `SM_Flower*`) sowie nicht begehbare Flächen (`ImpactNormal.Z < 0.5`), sodass sowohl schmale Altstadtgehwege als auch die Brücken-SaveGame-Sicherung (Sprint 11.1) zuverlässig funktionieren.

## Dreieckszahlen der Gebäude (Performance-Budget)

| Ausbaustufe | Gebäudedreiecke | Veränderung ggü. Sprint 11.1 | Gesamt-Meshes / -Dreiecke |
| --- | ---: | ---: | ---: |
| Vor Meilenstein 2 (Sprint 11.1 Baseline) | **175.725** | – | 166 / 348.920 |
| Nach Meilenstein 2 (LoD2-Höhen & -Dächer) | **139.722** | −20,5 % | 166 / 313.385 |
| Nach Meilenstein 3–5 (Wahrzeichen, Gable-Split) | **139.520** | −20,6 % | 172 / 313.601 |

Die Reduktion entsteht dadurch, dass reale LoD2-Traufhöhen (viele Nebengebäude/Garagen/eingeschossige Bauten mit realen 2,5–5 m statt der pauschalen 6,5 m) sowie reale Flach-, Pult- und Walmdächer weniger unnötige Obergeschoss-Fenster- und Fachwerkgeometrie erzeugen.

## Sichtprüfung (Screenshots)

Alle 6 festen Kameraperspektiven wurden mit `CaptureSprint12Screenshots.py` (1280×720, Editor Game-View) erzeugt und visuell geprüft:

| Bauwerk | Screenshot |
| --- | --- |
| Johanneskirche (39,22 m Turm, Fialen, Kirchenschiff) | [01_johanneskirche.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint12/01_johanneskirche.png) |
| Rathaus (Fachwerk, Kreuzstockfenster, Mansarddach, Portal) | [02_rathaus.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint12/02_rathaus.png) |
| Festung Dömitz (Zeughaus, Hauptwache, Kommandantenremise, Arrestantenhaus) | [03_festung.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint12/03_festung.png) |
| Torbrücke (3 Ziegelbögen, 2 Flusspfeiler) | [04_torbruecke.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint12/04_torbruecke.png) |
| Steinbrücke (Gewölbebogen, Widerlagerpfeiler) | [05_steinbruecke.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint12/05_steinbruecke.png) |
| Nordwest-Steg & Festungswall-Tunnelportal (0,27 % Neigung) | [06_nw_steg_tunnelportal.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint12/06_nw_steg_tunnelportal.png) |

## Prüfungen & Ergebnisse

1. **Python-Testsuite (`python -m unittest discover -s tests`):** **44/44 OK** (inkl. 8 neuer Sprint-12-Tests in `tests/test_sprint12.py`: Steg-Neigung ≤ 6 %, Tunnelanschluss als Widerlager, 3-m-Fallback-Warnung > 1 m, LoD2-Lizenz/Report, LoD2-1:1-Zuordnung über Schwelle ohne Doppelvergabe, Kirchturm höchstes Gebäude, Referenz-Manifest mit URL/Urheber/Lizenz, bytegleicher Offline-Build in `dgm1` und `flat`).
2. **C++-Editor-Build (`DoemitzLivingCityEditor Win64 Development`):** `Result: Succeeded` (41,3 s).
3. **Unreal-Import (`scripts/Import-Altstadt.ps1`):** `DOEMITZ_IMPORT_OK: 172 meshes, 35.4291 m reference, 0.0374% error, ref0:hit=4.865m(dgm=4.806m,diff=2.1cm), ref1:hit=4.699m(dgm=4.608m,diff=1.1cm), terrain, roof and wall collision passed, sidewalk collision passed, 5 bridges collision passed` (Terrain: 143 Kacheln, 149.799 Dreiecke ≤ 150.000, `max_err = 4,95 cm`).
4. **PIE-Prüfungen (`scripts/Verify-All.ps1`):** **`DOEMITZ_VERIFY_ALL_OK: 17/17 PIE checks passed.`**
   - `VerifyBridges.py`: Torbrücke `max_dev=2,40 cm`, **NW-Steg → Tunnel `max_dev=2,15 cm` (≤ 5 cm)**, Steinbrücke Fahrzeug `max_dip=0,00 cm`, Fläutendörper Steg Einwohner `max_dev=0,41 cm`, Brücken-SaveGame-Reload `dev=4,00 cm`.
   - `VerifySaveGame.py`: `DOEMITZ_SAVEGAME_PIE_OK` inkl. v4/v5→v6 Höhenmigration.
5. **Win64-Standalone-Build & Benchmarks (`Win64Sprint12`):**
   - `scripts/Build-Windows.ps1 -ArchiveDirectory unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint12`: **`BUILD SUCCESSFUL`** (3 min 54 s).
   - Start ohne Parameter (`DoemitzLivingCity.exe`): stabil aktiv nach 12 s (1024,8 MB Working Set), sauber beendet.
   - Zwei 90-Sekunden-Benchmarks `DoemitzLow` (1920×1080, Intel Core i5-1135G7 / Intel Iris Xe):
     - **Lauf 1 (`sprint12_low_run1.json`):** **57,89 FPS** Mean (`17,28 ms`), p95 `22,11 ms` (45,23 FPS), p99 `26,05 ms` (38,38 FPS), 5.210 Frames.
     - **Lauf 2 (`sprint12_low_run2.json`):** **58,51 FPS** Mean (`17,09 ms`), p95 `21,93 ms` (45,60 FPS), p99 `25,24 ms` (39,62 FPS), 5.267 Frames.
     - **Mittelwert:** **58,20 FPS** (Ziel ≥ 15 FPS, **+2,0 %** gegenüber Sprint 11.1 mit 57,06 FPS; keine Regression).

## Ausblick

| Sprint | Schwerpunkt |
| --- | --- |
| 13 | Erste Innenräume (Kaufhaus, Apotheke, Rathaus-Bürgerbüro) mit Übergang vom Eingang |
| 14 | Erweiterung des Ausschnitts über die Altstadt hinaus mit World-Partition-Streaming |
