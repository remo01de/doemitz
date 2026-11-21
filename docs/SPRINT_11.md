# Sprint 11 · Reales Gelände aus DGM1

Stand: Umgesetzt und geprüft.

## Zusammenfassung

Sprint 11 ersetzt die flache Platzhalter-Grundfläche (`flat_placeholder`, 0 m) aus Sprint 1 durch das amtliche Digitale Geländemodell 1 m (**DGM1 Mecklenburg-Vorpommern**, `EPSG:25833`, `DHHN2016 / NHN`) des LAiV M-V. Die gesamte Dömitzer Altstadt (822 m × 675 m, Relief von `11,70 m NHN` am Elbufer bis `23,23 m NHN` auf dem Festungswall, 11,53 m Höhenunterschied) ruht nun auf vereinfachten, rissfreien 64-m-Geländekacheln. Straßen, Gehwege (überall 12 cm Bordstein), Gebäude (Natursteinsockel ab tiefster Grundrisshöhe bis über die höchste Hangstelle), Wasserflächen (fester Wasserspiegel unter Uferhöhe), Ausstattung, Einwohner, Verkehr (mit Fahrbahnneigung), Stadtkarte (Schummerung + Quellenvermerk) und SaveGame v6 (Höhenmigration für v1–v5) sind vollständig an das reale Gelände angebunden.

## Meilensteine und Abnahme

| Meilenstein | Status | Ergebnis / Nachweis |
| --- | --- | --- |
| 0 · Daten und Lizenz festlegen | Erledigt | `tools/geo_import/dgm.py` + `geo_import fetch-dgm` laden die den Ausschnitt + 50 m Rand abdeckende Kachel `dgm1_33_248_5894_2_xyz.zip` (2×2 km, Lieferjahr `2025`, SHA-256 `15f0b11a12e9b59e6faed70b0e5dcde5356c7411e0a3e67bfdca8482b6cd3706`) aus dem LAiV-Atom-Dienst nach `data/raw/doemitz-altstadt/dgm1/`. `data/manifests/doemitz-altstadt-dgm-license.json` nennt eindeutig eine Lizenz (`Creative Commons Namensnennung – 4.0 International (CC BY 4.0)`, `cc-by/4.0`), den konkreten Quellenvermerk `© GeoBasis-DE/M-V 2025` und `status: "imported"`. |
| 1 · Höhenraster im Offline-Build | Erledigt | `geo_import build` liest das DGM1-XYZ-Archiv (exakte `.5`-m-Zellmitten-Ausrichtung, 0 fehlende Zellen), schneidet das 709×856-Raster auf den Ausschnitt + 16 m Rand zu und speichert lokale Höhen `z_lokal = NHN − 13,001 m` deterministisch in `terrain-grid.bin` (`scene.json`: `terrain.kind = "dgm1"`). Die Referenzhöhe `13,001 m NHN` (DGM1 am lokalen Ursprung) sowie Glättungs-, Kachel- und Wasserspiegelannahmen sind in `data/manifests/doemitz-altstadt.json` versioniert. Zentrale Abbildung in `tools/geo_transform/local.py` & `tools/geo_transform/terrain.py`. `--terrain flat` erhält den alten flachen Modus. |
| 2 · Geländemesh | Erledigt | `tools/mesh_generator/terrain.py` erzeugt **143 Geländekacheln** (64 m × 64 m) als rissfreie Greedy-TIN-Dreiecksnetze mit **149.755 Dreiecken** (Budget ≤ 150.000) und **4,95 cm maximaler vertikaler Abweichung** auf offenem Gelände (Budget ≤ 5,0 cm). Unter Straßen, Gehwegen, Gebäuden und Wasserflächen ist das Gelände abgesenkt bzw. im Gebäudekern ausgeschnitten (kein Z-Fighting). Bytegleich in beiden Modi (`dgm1` und `flat`). |
| 3 · Straßen und Gehwege drapieren | Erledigt | `tools/mesh_generator/road_elevation.py` berechnet je Straße ein geglättetes Längsprofil (gleitender Mittelwert über **12,0 m** ≥ 10 m, knotenkonsistent an allen Kreuzungen) mit ebenem Querquerschnitt und weist `max_slope_percent` je Straße im Report aus. Gehwege behalten überall **12 cm ± 1 cm** Bordstein über der Fahrbahn mit nach unten geschlossenen Bordsteinkanten. Straßengraph (167 Kanten, 61 Kreuzungen, 6 Vorfahrtsschilder, 4 Überwege, 9 Parkplätze inkl. Stellplätze) und Fahrzeugrouten tragen 3D-Höhen. |
| 4 · Gebäude, Wasser und Ausstattung | Erledigt | Alle 645 Gebäude (davon 643 auf geneigtem Grund) gründen auf der tiefsten Geländehöhe unter ihrem Grundriss; Traufhöhe zählt ab dort; der Natursteinsockel (`StoneTrim`) reicht auf Hanglagen sichtbar über die höchste Geländestelle. Alle 3 Wasserflächen liegen auf festen Wasserspiegeln je Gewässer (`bank_min − 0,05 m`, dokumentierte Annahme `assumed_bank_min_minus_5cm`, strikt unter Uferhöhen: `11,649 / 11,850 / 11,700 m NHN`). Laternen, Bänke, Pflanzkübel, Poller, Bäume, Büsche, Eingänge, Einwohnerrouten und Aufgabenziele stehen auf dem realen Gelände bzw. Gehweg. |
| 5 · Unreal-Import und Laufzeit | Erledigt | `import_altstadt.py` importiert alle 165 Meshes (inkl. 143 `Terrain_XX_YY`-Kacheln mit gemeinsamem `M_Terrain`, `BlockAll`-Kollision und `distance_field_resolution_scale = 0.0` sowie aktivierter Fahrbahn-Kollision auf `SM_Paving`/`SM_Roads`/`SM_Paths`). Spieler, Einwohner (inkl. Off-Pool-LOD) und Fahrzeuge folgen der Höhe; `SampleEdgePose` neigt Fahrzeuge mit der Fahrbahn (`Pitch`, `Roll = 0`). Die Offline-Stadtkarte (`city-map.png`) erhält eine dezente NW-Schummerung aus dem DGM1. `© GeoBasis-DE/M-V 2025` steht im Spiel (`TextRenderActor`) und auf der Stadtkarte neben der OSM-Attribution. |
| 6 · SaveGame v6 und Demo | Erledigt | `UDoemitzSaveGame::CurrentSchemaVersion = 6`. Beim Laden älterer Spielstände (v1–v5 mit flachen Höhen) werden Spieler- und Einwohnerpositionen per Abwärts-Line-Trace (`ECC_Visibility`) auf das DGM1-Gelände gesetzt und Fahrzeuge über ihre 3D-Kante / Parkbucht wiederhergestellt. Benchmark-Strecke `Goethestraße → Rathausplatz → Festungszugang` folgt dem realen Gelände (+180 cm Augenhöhe). Win64-Build `Win64Sprint11` erstellt und geprüft. |

## Durchgeführte Prüfungen

### 1. Offline-Geodaten & Python-Tests
- `.\.venv\Scripts\python.exe -m tools.geo_import fetch-dgm`: 1 Kachel (`dgm1_33_248_5894_2_xyz.zip`, `© GeoBasis-DE/M-V 2025`) erfolgreich geladen.
- `.\.venv\Scripts\python.exe -m tools.geo_import build` & `tools.mesh_generator`:
  - `143` Geländekacheln, `149.755` Geländedreiecke (`347.823` Dreiecke gesamt über `165` Meshes), `max_err = 4,95 cm`.
  - Referenzpunkte vs. DGM1: Rathausplatz (`-75, -223`: `4,734 m` vs. `4,755 m`, Δ `2,05 cm`), Festungswall (`-244, 40`: `10,137 m` vs. `10,169 m`, Δ `3,14 cm`), Elbufer (`-380, -320`: innerhalb ±5 cm).
  - Kontrollstrecke Goethestraße: `35,4291 m` projiziert vs. `35,4159 m` geodätisch (`0,0373 %` Abweichung).
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`: **30 von 30 Tests bestanden** (23 bestehende + 7 neue in `tests/test_sprint11.py`: Lizenz/Report, Bytegleichheit in `dgm1` und `flat`, 3 bekannte Punkte ±5 cm, 12 cm ±1 cm Bordstein überall, keine schwebenden Gebäudesockel, Fahrbahnsteigungen, Wasserspiegel unter Uferhöhen, Schummerung & GeoBasis-Vermerk).

### 2. Editor-Build & Level-Import
- C++-Editor-Build (`DoemitzLivingCityEditor Win64 Development` via UnrealBuildTool): erfolgreich ohne Fehler.
- `scripts/Import-Altstadt.ps1` / `import_altstadt.py`:
  - `DOEMITZ_IMPORT_OK: 165 meshes, 35.4291 m reference, 0.0374% error, ref0:hit=4.865m(dgm=4.806m,diff=2.1cm), ref1:hit=4.699m(dgm=4.608m,diff=1.1cm), terrain, roof and wall collision passed, sidewalk collision passed`

### 3. Automatisierte PIE-Prüfungen (`scripts/Verify-All.ps1`)
Alle **16 von 16** PIE-Skripten bestanden (`DOEMITZ_VERIFY_ALL_OK: 16/16 PIE checks passed`), u. a.:
- `VerifyTerrain.py` (neu): Spieler läuft Goethestraße und steigt die reale Festungswall-Rampe (`osm:way:416326354`) ohne Durchfallen (`walk_z=[470.5, 774.6] cm`, Steigung `+304,1 cm`), Fahrzeug fährt geneigte Kante mit `pitch=6,66°` und Bodenabstand `0,6 cm`, Off-Pool-Einwohner (`altstadt_citizen_10`) erscheint auf Geländehöhe (`dz=0,2 cm`), In-Game-Quellenvermerk `© GeoBasis-DE/M-V` vorhanden.
- `VerifySidewalk.py`: `crossed 339.9 cm onto sidewalk and returned` (12 cm Bordstein auf DGM1).
- `VerifyMap.py`: `2048x2048 texture loaded, 30 citizens / 8 vehicles / 9 parking lots / 35 places`, OSM- und GeoBasis-Attribution geprüft.
- `VerifySaveGame.py`: v6-Speichern/Laden sowie v4→v6- und **v5→v6-Höhenmigration** (flache `96 cm` / `20 cm` per Abwärts-Trace auf `575,1 cm` / `472,8 cm` gesetzt) bestanden.

### 4. Win64-Build & Benchmarks (`DoemitzLow`, 1920×1080, 90 s, 8 Fahrzeuge)
- Paketierung: `scripts/Build-Windows.ps1 -ArchiveDirectory unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint11` (`ExitCode=0`, IoStore `259,68 MiB`).
- Parameterloser Start von `DoemitzLivingCity.exe`: erfolgreich (`alive_after_12s=True`).
- Messstrecke `Goethestraße → Rathausplatz → Festungszugang` (`326,4 m`, jetzt über reales DGM1-Gelände) auf Intel Core i5-1135G7 / Intel Iris Xe Graphics:

| Lauf | Profil | Mean FPS | Mean ms | P50 ms | P95 ms | P99 ms | Game / Draw / GPU ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lauf 1 | `DoemitzLow` | **59,67** | 16,76 | 16,51 | 19,98 | 22,62 | 3,68 / 13,49 / 16,76 |
| Lauf 2 | `DoemitzLow` | **60,94** | 16,41 | 16,21 | 19,29 | 21,17 | 3,64 / 13,38 / 16,41 |

Kein Performanceverlust gegenüber Sprint 10 (58,4 FPS) — im Gegenteil leicht schneller (+2–4 %) durch 64-m-Kachel-Culling und deaktivierte Distance-Field-Generierung auf den Geländekacheln. Budget (≥ 15 FPS) deutlich übertroffen.

## Bekannte Grenzen (bewusst außerhalb Sprint 11)

- Brücken (`Torbrücke`, `Steinbrücke`, Festungsbrücke) liegen weiterhin ohne eigene Brückenhöhe auf dem DGM1-Gelände (wie in `GEO_DATA.md` beschrieben), weshalb dort lokal steilere Längsneigungen im Report auftreten.
- Markante Bauwerke/Innenräume folgen in Sprint 12, die Erweiterung über die Altstadt hinaus in Sprint 13.
- Remote-Sicherung bleibt als offene Entscheidung beim Product Owner.

## Ausblick

| Sprint | Schwerpunkt |
| --- | --- |
| 12 | Markante Bauwerke nach Referenzmaterial (Festung, Kirche, Rathaus), erste Innenräume |
| 13 | Erweiterung des Ausschnitts über die Altstadt hinaus mit World-Partition-Streaming |
