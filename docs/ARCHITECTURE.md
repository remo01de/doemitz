# Technische Architektur

## Geodaten und Weltaufbau

1. Python lädt einen begrenzten OSM-Ausschnitt einschließlich benötigter Multipolygon-Bestandteile. Der Offline-Build filtert die Sprint-Layer, beschneidet sie auf den Ausschnitt und prüft die Geometrie.
2. Die Pipeline projiziert die Geometrie nach ETRS89 / UTM 33N und verschiebt sie zu einem versionierten lokalen Ursprung. `scene.json` ist die Übergabe an die Weltgenerierung. [Koordinaten und Datenvertrag](GEO_DATA.md)
3. Die Mesh-Stufe erzeugt aus dem DGM1-Raster 64-m-Geländekacheln (TIN, höchstens 5 cm Fehler in der Altstadt, 10 cm im Erweiterungsgebiet), Wasserflächen mit eigenem Wasserstand je Abschnitt, drapierte Straßen und Gehwege, eigenständige Brücken und begehbare Tunnelkorridore, LoD2-Gebäudekörper, Wahrzeichen, Festungs- und Stützmauern, drei begehbare Erdgeschoss-Innenräume sowie Schleuse und Hafenanlagen (Stege, Gangways, Kaimauern, Buhnen). Sie vermerkt die Herkunft aller Höhen, Breiten und Annahmen im Mesh-Export.
4. Der Editor-Import aktualisiert die generierten Assets und Actors. Der 1:1-Übergang verwendet `X = Nord`, `Y = Ost` und `Z = Höhe` mit 100 Unreal Units pro Meter. Der Koordinatentausch berücksichtigt die Dreiecksreihenfolge beim Übergang in das linkshändige Unreal-System. Die Stadtkarte verwendet World Partition. Seit Sprint 14 zerlegt die Mesh-Stufe die Stadt-Meshes in Zellen von 256 m (`<Mesh>__cX_Y`, seit Sprint 15 Raster 6 × 4 mit 405 Zell-Meshes); diese Zellen, die 352 Geländekacheln und die Requisiten je Zelle werden räumlich geladen. Immer geladen bleiben Landmarken (`<Mesh>__lm`: Kirche, Rathaus, Festungsbauten, Speicher), Festungsmauern, Schleuse, Brücken und Wasser. Der Import setzt das Laufzeitraster (Zellgröße 256 m, Laderadius 1000 m) über `UDoemitzWorldTools::ConfigureStreamingGrid`. Ohne HLOD bleibt der Radius so groß, dass von jedem Punkt der heutigen Fläche keine Lücke am Horizont entsteht. Boden, Gebäudewände, Dächer, Brücken, Hafenstege und feste Stadtmöbel kollidieren in Unreal.

## Unreal-Laufzeit

Die Spielsimulation ist seit Sprint 15 in sechs zyklenfreie `UWorldSubsystem`-Klassen mit gemeinsamen Datentypen in `DoemitzSimulationTypes.h` aufgeteilt (`UDoemitzSimulationSubsystem` koordiniert den deterministischen Tick in fester Reihenfolge):

| Subsystem / Bereich | Technik und Aufgabe |
| --- | --- |
| `UDoemitzSimulationSubsystem` | Zentrale Uhr (`BaseTimeScale = 20.0`, 1 Tag = 72 Echtzeit-Minuten, `1x/5x/15x/Pause`), Wochenkalender, Orte & Öffnungszeiten, Innenraum-Metadaten, Stadtkarte (4096 px) und Benachrichtigungs-Events |
| `UDoemitzCitizenSubsystem` | 30 Einwohner mit Hybrid-Zeitskala (sichtbar ≤ 150 m in realem Gehtempo, außerhalb 150 m in Spielzeit), kontinuierliches Mid-Trip-Routing ohne Teleport und 150-m-Actor-Pooling |
| `UDoemitzTrafficSubsystem` | 8 Fahrzeuge auf 303 gerichteten Straßenkanten, 104 Kreuzungen (Rechts vor links & Vorfahrtsschilder), 9 Fußgängerüberwege, 15 Parkplätze und Sub-Stepping bei Zeitraffer |
| `UDoemitzEconomySubsystem` | Spielerkonto, Buchungsjournal, Inventar, Ladenkäufe, Stellen & Schichten (15× relativ zur Basis-Zeitskala) sowie Tages-/Wochenumsätze je Ort |
| `UDoemitzTaskSubsystem` | Deterministische Tagesaufgaben (Botengänge & Besorgungen), Fristen und Bürgerbüro-Aushang |
| `UDoemitzSaveSubsystem` | SaveGame v7 (inkl. Abwärtsmigration v1–v7), Terrain-, Brücken- und Innenraum-Wiederherstellung |
| Welt, Beleuchtung & Grafik | World Partition, `ADoemitzDayNightController` (Sonne, Himmel, Straßenlaternen), `UDoemitzGraphicsSettings` (`DoemitzLow`/`DoemitzHigh`; drosselt ausschließlich Straßenlaternen, Innenraumleuchten bleiben stets aktiv) |
| Charakter & Interaktion | Third-Person-Steuerung, Kamera mit Wand-/Deckenkollision, Sprint, `UDoemitzInteractionComponent`, `ADoemitzInteriorDoor` |
| Bedienoberfläche | Programmatisches UMG (Uhr/Status-HUD, Stadtkarte mit Zoom/Pan/Hover, Ortsmenü, Einwohnerdialog, Aushang, Aufgabenbuch), zentralisierte deutsche Texte in `FDoemitzUiText` |

Einwohner, Fahrzeuge und Orte erhalten stabile IDs. Ihr Zustand läuft deterministisch weiter, auch wenn die zugehörigen Actors durch LOD-Pooling oder Streaming entladen sind. Die Singleplayer-Simulation läuft lokal.
