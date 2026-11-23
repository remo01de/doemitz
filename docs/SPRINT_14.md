# Sprint 14 · Stadtgebiet bis Hafen und Schleuse

Stand: Umgesetzt und geprüft (Plan vom 23.11.2026, Umsetzung am selben Tag).

## Ziel

Das spielbare Gebiet wächst von der Altstadt nach Südosten bis zum Hafen Dömitz und zur Schleuse Dömitz der Müritz-Elde-Wasserstraße. Hafenbecken, Stege, Speicher und Schleuse sind als erkennbare Bauwerke modelliert. Die gewachsene Welt ist in Zellen zerlegt und wird über World Partition gestreamt. Das Ziel von mindestens 15 FPS auf dem Test-PC gilt weiter.

## Entscheidungen des PO

- **Der Festungsgraben bleibt Wasser.** Der Wasserstand hängt stark von der Witterung ab; der trockene Graben auf manchen Fotos ist ein Momentzustand.
- Die Erweiterung geht in Richtung Hafen und Schleuse.

## Ergebnisse

| Nr. | Meilenstein | Ergebnis |
| --- | --- | --- |
| 0 | Daten und Zuschnitt | `bounds_lonlat [11.2428, 53.1372, 11.2607, 53.1455]`, lokal x −426…+819 m, y −648…+338 m, 1,11 km² statt 0,50 km². Ursprung, Bezugshöhe und Achsen bleiben gleich; Koordinaten und Spielstände gelten weiter. Ausschnitt plus 50 m Rand liegt in der vorhandenen DGM1/LoD2-Kachel `33_248_5894`, also ohne neuen amtlichen Download. Der OSM-Stand wurde neu geladen (`map.osm` plus Relationen 285875 und 1809795). **Diff Altstadt:** Kein OSM-Objekt des alten Ausschnitts hat sich geändert; nur zwei Radrouten-Relationen haben neue Versionen. Die Unterschiede im Szenen-Export kommen allein vom neuen Zuschnitt am alten Rand. Alle 72 OSM-IDs aus den Manifesten existieren weiter. Ergebnis: 782 Gebäude (vorher 645), 213 Wege, 9 Wasserflächen, 177 POIs, 20 Mauern. Stadtkarte 4096 px, 0,31 m/px. |
| 1 | Wasser | Neue Szenenebenen `waterworks`, `piers` und `moorings`. Schleusentore, Wehre und Dämme teilen Wasserflächen in Abschnitte, jeder mit eigenem Stand aus dem eigenen Ufer (DGM1-Stand, die Schnittlinie zählt nicht mit). Die Elde-Fläche `osm:relation:285875` zerfällt in Unterwasser 11,75 m NHN, oberen Vorhafen 14,70 m NHN und altes Elde-Bett oberhalb des Wehrs 14,70 m NHN. Die Kammer steht auf Unterwasser (11,80 m NHN). Der Festungsgraben bleibt unverändert. |
| 2 | Schleuse Dömitz | Neues Modul `tools/mesh_generator/locks.py`. Die Kammer (`osm:way:1315856502`, 61,1 m lang, etwa 5,5 m breit) hat Betonwände bis 17,3 m NHN mit Abdeckung, Leiternischen, Pollern und Geländer; das Gelände dahinter wird wie bei Stützmauern bis zur Abdeckung aufgefüllt und an der Wand geteilt. Zwei Stemmtorpaare an `osm:way:1315856503` und `osm:way:1315856504` reichen bis auf Uferhöhe, mit begehbarem Steg, Geländer und Waagebalken; sie schließen die Fallhöhe von 2,95 m. Das Wehr `osm:way:42707704` ist ein Betonkörper mit Pfeilern, Krone auf Oberwasser. Die Straßenbrücke `osm:way:42325141` kommt aus der Brückenpipeline. Maße als `assumed_sprint14_lock` gekennzeichnet. |
| 3 | Hafen | Neues Modul `tools/mesh_generator/harbour.py`: 26 Schwimmstege (Deck 0,35 m über dem Wasser, 2,0 m breit bei Hauptstegen, 1,2 m bei Fingerstegen, über Land 0,12 m über Gelände mit Rampe), 2 Plattformen, Führungspfähle, 5 Dalben, 5 Buhnen als Steinschüttung, Kaimauern an hohen Ufern in Stegnähe und 16 Boote als HISM-Requisiten mit Kollision (Motorkreuzer und Segelboot, deterministisch, nur ganz im Wasser und ohne Berührung von Stegen oder anderen Booten). Der **Speicher** (`osm:way:42883863`) ist eine eigene Landmarke: Backstein, 6 Geschosse mit kleinen Fenstern, Ladeluken in den Giebelseiten, Kranbalken und Satteldach nach LoD2 (Traufe 20,23 m, First 32,37 m; OSM `height=60` ist falsch). |
| 4 | Straßen, Orte, Simulation | 246 Straßenkanten, 86 Knoten, 14 Parkplätze, 75 Orte (18 im Erweiterungsgebiet: Hafenrestaurant, Hotel Dömitzer Hafen, Panorama Café, Strandbar, Cafés, Läden, Pensionen, Feuerwehr). 15 der 30 Einwohner nutzen Orte im neuen Gebiet. Neue Aufgabe `task_tpl_errand_kaufhaus_hafenhotel`: eine Kiste vom Kaufhaus zum Hotel am Hafen. |
| 5 | Zellen und Streaming | Die Mesh-Stufe zerlegt die Stadt-Meshes in Zellen von 256 m (`<Mesh>__cX_Y`, Raster 5 × 4). Dreiecke der Landmarken (Kirche, Rathaus, Festungsbauten, Speicher) kommen nach `<Mesh>__lm` und bleiben immer geladen, ebenso Festungsmauern, Schleuse, Brücken und Wasser. 352 Zell-Meshes, 320 Geländekacheln und 168 Requisiten-Actors (je Zelle) werden räumlich geladen. Das Laufzeitraster (WorldPartitionRuntimeHashSet) stellt `UDoemitzWorldTools::ConfigureStreamingGrid` beim Import ein: Zelle 256 m, Laderadius 1000 m (vorher 128 m / 256 m). Neue PIE-Prüfung `VerifyStreaming.py`. |
| 6 | Budgets, Prüfungen, Doku | Gelände: höchstens 5 cm Fehler in der Altstadt, höchstens 10 cm im Erweiterungsgebiet, 244.273 von 250.000 Dreiecken. Doku in `docs/GEO_DATA.md` und `docs/ARCHITECTURE.md` aktualisiert. |

## Abweichung vom Plan

- **Schleusenhäupter ergänzt:** An jedem Torende steht ein begehbarer Betonblock auf Steghöhe (3 × 3 m). Ohne ihn endete der Torsteg am westlichen Oberhaupt an einer steilen Böschung, und die Figur rutschte ins Oberwasser.
- **Editor-Ansicht:** Der Editor lädt räumlich geladene Zellen nicht von selbst. Skripte, die die Karte rendern, laden vorher alle Zellen (`doemitz_wp.load_all_actors()`, in `CaptureSprint13Screenshots.py` eingebaut). Wer die Karte im Editor öffnet, lädt die Zellen über das World-Partition-Fenster. Im Spiel und in PIE lädt das Laufzeit-Streaming automatisch.

- **Laderadius 1000 m statt 450 m:** Ohne HLOD fehlen entladene Zellen am Horizont ganz, also auch Gelände und Häuser. Mit 1000 m bleibt von jedem Punkt der heutigen Fläche alles Sichtbare geladen; Streaming und Zellen sind aktiv und geprüft, entladen aber bei der heutigen Größe kaum etwas. HLOD-Aufbau und ein kleinerer Radius gehören in die nächste Erweiterung.
- **Kaimauern:** Sie entstehen automatisch an hohen Ufern in Stegnähe (16 Abschnitte); einige liegen am Kanal, wo das Ufer in Wirklichkeit eine Böschung sein kann.

## Prüfungen

- Python: `python -m unittest discover -s tests`, 72 Tests in 651 s, alle bestanden. Neu ist `tests/test_sprint14.py` (7 Tests: Ausschnitt und Ursprung, Ober- und Unterwasser, Schleuse, Hafen und Boote, Speicherhöhe, Geländebudget je Bereich, Zellen, Karte und Hafen-Aufgabe). Angepasst wurden fest eingetragene Zählwerte älterer Tests (782 Gebäude, 9 Brücken, 11 Landmarken, 9 OSM-Eingänge, Karte 4096 px, Geländebudget 250.000) und die Mesh-Namen nach der Zellteilung.
- Offline-Pipeline: `python -m tools.geo_import build` und `python -m tools.mesh_generator`, 696 Meshes, 524.804 Dreiecke, Gelände 244.273 Dreiecke (Altstadt max. 4,95 cm, Erweiterung max. 9,95 cm).
- C++-Editor-Build (`DoemitzLivingCityEditor Win64 Development`): erfolgreich. Neu: `UDoemitzWorldTools` (Streaming-Raster setzen und auslesen, Streaming-Abschluss), zweite Benchmark-Strecke `-DoemitzBenchmarkRoute=hafen`.
- Import (`scripts/Import-Altstadt.ps1`): `DOEMITZ_IMPORT_OK: 696 meshes`, Kollision von Gelände, Dächern, Wänden, Gehwegen und 9 Brücken bestanden; `DOEMITZ_HISM_IMPORT_OK: 168 HISM actors, 1543 instances, 1123 blocking`; `DOEMITZ_STREAMING_GRID_OK: WorldPartitionRuntimeHashSet: MainPartition 12800/25600 -> 25600/100000`.
- PIE (`scripts/Verify-All.ps1`): `DOEMITZ_VERIFY_ALL_OK: 21/21 PIE checks passed`. Neu `VerifyStreaming.py`: 21 Positionen vom Rathaus über die Schleuse zum Hafen, an jeder ist nach dem Streaming (höchstens 0,1 s) Boden unter der Figur; danach geht die Figur über den oberen Torsteg von Haupt zu Haupt (tiefster Fuß 4,35 m, Steg 4,33 m). Angepasst: `VerifyCrossing.py` liest die Kante des Zebrastreifens aus dem Paket (die Kantennummer hat sich durch den größeren Ausschnitt verschoben), `VerifyMap.py` die Kartengröße, `VerifyEconomy.py` lässt die Uhr in der Einkaufsphase halb so schnell laufen (siehe Offen), `VerifyPropCollision.py` erkennt die Requisiten je Zelle.
- Windows-Build (`scripts/Build-Windows.ps1 -ArchiveDirectory …\unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint14` im Hauptprojekt): `BUILD SUCCESSFUL`.
- Benchmark (`scripts/Run-Benchmark.ps1 -Profile DoemitzLow`, 1920×1080, 90 s, gepackter Build, Ergebnisse unter `Saved/Benchmarks/Sprint14/`):

  | Strecke | Lauf | FPS (Mittel) | Frametime p50 / p95 / p99 | GPU / Draw / Game |
  | --- | --- | --- | --- | --- |
  | Goethestraße → Rathausplatz → Festungszugang (328 m) | 1 | 44,34 | 22,13 / 27,82 / 35,45 ms | 22,6 / 17,9 / 3,5 ms |
  | Goethestraße → Rathausplatz → Festungszugang (328 m) | 2 | 44,33 | 21,97 / 27,70 / 36,43 ms | 22,6 / 17,7 / 3,5 ms |
  | Rathausplatz → Hafen → Schleuse (1092 m, `-Route hafen`) | 1 | 48,08 | 19,92 / 27,76 / 38,89 ms | 20,8 / 16,3 / 3,4 ms |
  | Rathausplatz → Hafen → Schleuse (1092 m, `-Route hafen`) | 2 | 47,41 | 20,17 / 26,64 / 38,42 ms | 21,1 / 16,3 / 3,4 ms |

  Das Ziel von mindestens 15 FPS ist auf beiden Strecken deutlich erfüllt. Auf der Altstadt-Strecke liegen die Werte etwa 10 % unter dem Stand von Sprint 13.1 am selben Tag (47–50 FPS), weil mit 1000 m Laderadius die ganze größere Stadt geladen bleibt.

## Sichtprüfung

Aufnahmen mit `CaptureSprint13Screenshots.py` unter `unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/`:

| Bild | Was zu sehen ist |
| --- | --- |
| [27_schleuse_unterhaupt.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/27_schleuse_unterhaupt.png) | Vom Unterwasser: Kammerwände mit Leitern und Pollern, unteres Tor mit Steg und Geländer, Betonhäupter beiderseits des Tors, Waagebalken über dem Ufer, Schleusengebäude. |
| [28_schleuse_kammer.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/28_schleuse_kammer.png) | Vom oberen Torsteg in die Kammer, Geländer entlang der Kammerkanten. |
| [29_hafen_steganlage.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/29_hafen_steganlage.png) | Auf dem Hauptsteg am Südkai: Boot, Fingerstege, Kaimauer mit Leiter, dahinter der Speicher. |
| [30_speicher.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/30_speicher.png) | Speicher mit Satteldach über Kaimauer und Steganlage. |
| [31_hafen_steg.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/31_hafen_steg.png) | Nordsteg mit Fingerstegen, Pfählen und Segelboot, Kaimauer am Kanal. |
| [32_weg_altstadt_hafen.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/32_weg_altstadt_hafen.png) | Übergang von der Altstadt zum Hafen. |

## Offen

- HLOD für entfernte Zellen und ein kleinerer Laderadius (nötig bei weiterem Wachstum).
- Am neuen Ostrand (bei der Schleuse) endet die Welt sichtbar; ein Abschluss (Gelände-Schürze oder Horizontkulisse) fehlt.
- Annas Einkaufsfenster (60 Spielminuten) ist kürzer als ihr Weg vom Amt zum Kaufhaus bei 1x (94 Spielminuten); das war schon vor Sprint 14 so und fiel nur nicht auf, weil zwei andere Einwohner im Kaufhaus einkauften.
- Schleusenbetrieb, Schiffs- und Fährverkehr, Innenräume am Hafen.
- Die offenen Punkte der Festung aus Sprint 13.1 bleiben offen.
