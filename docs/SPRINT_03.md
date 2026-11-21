# Sprint 3 · Erste Einwohner und einfache Tagesabläufe

Sprint 3 führt die erste Einwohner-Simulation im Altstadtausschnitt ein. Gemäß der zentralen Architekturregel bleiben Simulationszustand und 3D-Darstellung strikt getrennt: Jede Person besitzt eine stabile ID, eine Wohnung, einen Arbeitsplatz und einen Tagesablauf, der auch dann weiterläuft, wenn ihr 3D-Actor nicht geladen ist.

| Meilenstein | Abnahme |
| --- | --- |
| Stabile Orte & Einwohner-Konfiguration | Orte verweisen im Manifest auf echte OpenStreetMap-Gebäude-IDs entlang der Goethestraße. Der Offline-Generator berechnet Zugangspunkte und hindernisfreie Gehweg-Routen deterministisch ohne hartcodierte Koordinaten. |
| Getrennte Simulation & 3D-Darstellung | `UDoemitzSimulationSubsystem` führt Spielzeit und alle Einwohner-Zustände per stabiler ID. `ADoemitzCitizenActor` synchronisiert ausschließlich die 3D-Darstellung. Der Zustand läuft auch ohne geladenen 3D-Actor weiter. |
| Windows-Demo | Ein Win64-Testbuild startet in der Altstadt und initialisiert sowohl das Fahrzeug als auch die Einwohner-Simulation. |

## Konfiguration und Umsetzung

- **Manifest:** [doemitz-altstadt-citizens.json](../data/manifests/doemitz-altstadt-citizens.json) definiert fünf reale Orte entlang der Goethestraße (`place_goethe_pension` / Radlerpension Dömitz, `place_amtsverwaltung` / Amtsverwaltung und Bürgerbüro, `place_kaufhaus` / Kaufhaus sowie zwei Wohnhäuser) über ihre OSM-Gebäude-IDs und vier Einwohner (`citizen_anna_01` bis `citizen_dieter_04`) mit Tagesabläufen (`Home`, `Working`, `Shopping`, `Strolling`).
- **Offline-Routencompiler:** [citizens.py](../tools/mesh_generator/citizens.py) berechnet für jeden Ort den nächstgelegenen begehbaren Gehweg-Zugangspunkt und erzeugt die benötigten Fußgängerrouten zwischen den Tagesablauf-Orten.
- **Unreal C++:**
  - `UDoemitzSimulationSubsystem` (`UTickableWorldSubsystem`) verwaltet Spielzeit (`StartMinute`, `TimeScale`, `DayNumber`) und alle `FDoemitzCitizenState`-Einträge nach stabiler `CitizenId`.
  - `ADoemitzSimulationConfig` übergibt die importierten Orte, Routen und Einwohner beim Levelstart an das Subsystem.
  - `ADoemitzCitizenActor` stellt einen Einwohner über ein eigenes stilisiertes Low-Poly-Mesh (`doemitz_citizen_mesh.py`, ohne Fremdassets) dar und synchronisiert seine Position in `TG_PostUpdateWork`. Die Kollisionskapsel nutzt `ECC_Pawn`, sodass auch `ADoemitzTrafficVehicle` vor querenden Einwohnern anhält.

## Prüfungen

- **Offline-Build und Python-Tests:** 146 Straßen- und Wegeabschnitte, 645 Gebäude, 3 Wasserflächen, 0 Geometriefehler. Der Mesh- und Simulationsexport (`unreal-city-meshes.json`) war bei Wiederholung bytegleich. Alle 6 Python-Tests liefen erfolgreich.
- **Editor-Build und Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) kompiliert. `Import-Altstadt.ps1` importierte 11 Stadt-Meshes, das Testfahrzeug (`altstadt_compact_01`) sowie `4 citizens, 5 places, 11 routes` (`DOEMITZ_CITIZENS_IMPORT_OK`). Kontrollstrecke 35,4291 m (0,0372 % Abweichung), Kollisionstests für Boden, Dach, Wand und Gehweg bestanden.
- **Play-Modus (PIE):** `VerifyCitizens.py` verifizierte `DOEMITZ_CITIZENS_PIE_OK`: Alle 4 Einwohner waren aktiv, `citizen_anna_01` lief mit synchronisiertem 3D-Actor zur `place_amtsverwaltung`, und `citizen_bernd_02` vollendete seinen Arbeitsweg zur `place_kaufhaus` im `UDoemitzSimulationSubsystem`, nachdem sein 3D-Actor zuvor zerstört wurde.
- **Windows-Testbuild:** Das archivierte Win64-Development-Paket wurde erfolgreich erstellt und im Starttest mit `-nullrhi` verifiziert: `/Game/Maps/DoemitzAltstadt` geladen, World Partition initialisiert, `Doemitz simulation started at 470.0 min (scale 60.0x): 5 places, 11 routes, 4 citizens` und `Traffic vehicle altstadt_compact_01 started on altstadt_goethestrasse_loop (421.4 m)`. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint03/DoemitzLivingCity.exe)
