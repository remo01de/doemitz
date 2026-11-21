# Sprint 6 · Stilisierte Altstadt-Architektur, Straßenlaternen und Vegetation

Sprint 6 überträgt die visuelle Zielrichtung der Referenzbilder in `Images/` in den prozeduralen Offline-Generator und den Unreal-Import — vollständig deterministisch, ohne Fremdassets und unter Beibehaltung des exakten 1:1-OSM-Maßstabs.

| Meilenstein | Abnahme |
| --- | --- |
| Stilisierte Gebäude-Architektur | Alle 645 Altstadt-Gebäude erhalten deterministisch (über ihre OSM-ID) warme Fassadenfarben, geneigte Sattel-/Walmdächer (Terrakotta, Ziegelbraun, Schiefer), Natursteinsockel, Stockwerk-Gesimse, Fachwerk-Akzente, Fenster mit Rahmen und farbigen Fensterläden, Blumenkästen und Holztüren. |
| Straßenraum & Vegetation | Altstadt-Straßenlaternen mit warm leuchtendem Emissive-Glas säumen die Goethestraße; stilisierte Laubbäume und Büsche beleben die freien Grünflächen ohne Kollision mit Straßen, Gehwegen, Gebäuden oder Wasser. |
| Performance-Budget & Build | Flache Fassadenelemente werden als schlanke Quads erzeugt (29 Meshes, 220.566 Dreiecke). Der Import und der Win64-Testbuild bestehen alle Prüfungen. |

## Umsetzung

- **Architektur-Generator:** [architecture.py](../tools/mesh_generator/architecture.py) erzeugt aus den OSM-Grundrissen Sattel-/Walmdächer mit Dachüberstand und Giebeldreiecken, Natursteinsockel (`StoneTrim`), Fachwerk/Rahmen (`TimberTrim`), spiegelnde Fenster (`WindowGlass`), farbige Fensterläden (`ShuttersGreen`, `ShuttersRed`, `ShuttersBlue`), 3D-Blumenkästen (`FlowerBoxes`) und Türen (`Doors`).
- **Straßenlaternen, Straßenmöbel & Bäume (gesamte Altstadt):** Alle 38 Haupt- und Wohnstraßen erhalten erhöhte Gehwege mit 12 cm Bordstein (8.225,8 m² Gesamtfläche, konfiguriert über `default_sidewalk_widths_m` in [doemitz-altstadt-streets.json](../data/manifests/doemitz-altstadt-streets.json)). [props.py](../tools/mesh_generator/props.py) platziert mit globalem Mindestabstand 134 Altstadt-Laternen (`LampMetal`, `LanternGlow`), 55 Holzbänke mit Terrakotta-Pflanzkübeln, 61 Poller sowie 423 stilisierte Laubbäume und Büsche (`TreeTrunks`, `FoliageLight`, `FoliageMid`, `FoliageDark`).
- **Prozedurale Materialien & Nachtbeleuchtung:** [import_altstadt.py](../unreal/DoemitzLivingCity/Content/Python/import_altstadt.py) erzeugt leichtgewichtige prozedurale Materialmuster (Kopfsteinpflaster, Gehwegplatten, Dachziegelreihen, Natursteinquader, Ziegelmauerwerk, Putz- und Wiesenvariation), glänzendes Wasser (`Roughness 0,12`), spiegelndes Fensterglas (`Roughness 0,14`, `Metallic 0,25`), Gusseisen-Laternen (`Metallic 0,75`), warmes Emissive-Leuchten (`M_LanternGlow`) sowie 68 echte `APointLight`-Laternen (ohne Schattenwurf), die [DoemitzDayNightController.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/World/DoemitzDayNightController.cpp) in der Dämmerung sanft ein- und morgens wieder ausschaltet.

## Prüfungen

- **Offline-Build und Python-Tests:** 29 Meshes, 247.742 Dreiecke, alle 6 Python-Tests bestanden.
- **Editor-Build & Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) kompiliert. `Import-Altstadt.ps1` bestand mit `DOEMITZ_IMPORT_OK: 29 meshes, 35.4291 m reference, 0.0372% error, terrain, roof and wall collision passed, sidewalk collision passed`.
- **Play-Modus (PIE):** `VerifyDayNightHud.py` bestand mit `DOEMITZ_DAYNIGHT_HUD_PIE_OK`: mittags (`12:00`) Sonne `60,0° / 3,80`, Laternen `0`; mitternachts (`00:00`) Sonne `-60,0° / 0,25`, Laternen `3800`.
- **Windows-Testbuild:** Das archivierte Win64-Development-Paket wurde neu erstellt und im Starttest mit `-nullrhi` verifiziert: `/Game/Maps/DoemitzAltstadt` geladen, World Partition initialisiert, `Doemitz simulation started at 470.0 min (scale 60.0x): 5 places, 11 routes, 4 citizens`, `Doemitz clock HUD attached (Tag 1  |  07:50  (1x))` und `Traffic vehicle altstadt_compact_01 started on altstadt_goethestrasse_loop (421.4 m)`. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint06/DoemitzLivingCity.exe)
