# Sprint 4 · Tag-/Nachtwechsel und UMG-Uhrzeit-/Status-HUD

Sprint 4 macht die Simulationszeit aus `UDoemitzSimulationSubsystem` in der Spielwelt und auf dem Bildschirm sichtbar. Lichtstimmung und Benutzeroberfläche bleiben reine Darstellungsschichten über dem zentralen Simulationszustand.

| Meilenstein | Abnahme |
| --- | --- |
| Dynamischer Tag-/Nachtwechsel | `ADoemitzDayNightController` steuert `Altstadt Sun` und `Altstadt Skylight` anhand von `UDoemitzSimulationSubsystem::GetTimeOfDayMinutes()` (Sonnenbogen, warme Horizontfarbe, sanftes Mondlicht in der Nacht). |
| UMG-Uhrzeit- und Status-HUD | `UDoemitzClockWidget` (`UUserWidget`, per Blueprint überschreibbar) zeigt Spieltag, Uhrzeit und Einwohnerstatus (`Tag X \| HH:MM` und aktive/unterwegs befindliche Einwohner). |
| Windows-Demo | Ein Win64-Testbuild startet in der Altstadt und initialisiert Simulation, Fahrzeug, Tag-/Nachtwechsel und Uhrzeit-HUD. |

## Umsetzung

- **Tag-/Nacht-Controller:** [DoemitzDayNightController.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/World/DoemitzDayNightController.h) und [DoemitzDayNightController.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/World/DoemitzDayNightController.cpp) berechnen Sonnenhöhe (bis 60° mittags) und Azimut aus der Spielzeit, passen Lichtfarbe und Intensität der Sonne sowie des `SkyLight` an und schalten nachts auf kühles Mondlicht um.
- **UMG-HUD:** [DoemitzClockWidget.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/UI/DoemitzClockWidget.h) und [DoemitzClockWidget.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/UI/DoemitzClockWidget.cpp) erzeugen ein leichtgewichtiges UMG-Overlay oben links. [DoemitzSimulationConfig.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Simulation/DoemitzSimulationConfig.cpp) hängt das Widget beim Spielstart an den lokalen Viewport.
- **Editor-Import:** [import_altstadt.py](../unreal/DoemitzLivingCity/Content/Python/import_altstadt.py) platziert `Altstadt Day Night Controller` und verknüpft ihn automatisch mit `Altstadt Sun` und `Altstadt Skylight`.

## Prüfungen

- **Editor-Build und Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) fehlerfrei kompiliert; `Import-Altstadt.ps1` bestand alle Prüfungen (`DOEMITZ_IMPORT_OK`, 11 Meshes, 35,4291 m Referenz, 0,0372 % Abweichung, Boden-/Dach-/Wand-/Gehweg-Kollision).
- **Play-Modus (PIE):** `VerifyDayNightHud.py` bestand mit `DOEMITZ_DAYNIGHT_HUD_PIE_OK`:
  - `12:00`: Sonnenhöhe `60,0°`, Intensität `3,80`, HUD `Tag 1  |  12:00`, Status `Doemitz Altstadt  |  4 Einwohner (0 unterwegs)`.
  - `00:00`: Sonnenhöhe `-60,0°`, Mondlicht-Intensität `0,25`, HUD `Tag 1  |  00:00`.
- **Windows-Testbuild:** Das archivierte Win64-Development-Paket wurde erfolgreich erstellt und im Starttest mit `-nullrhi` verifiziert: `/Game/Maps/DoemitzAltstadt` geladen, World Partition initialisiert, `Doemitz simulation started at 470.0 min (scale 60.0x): 5 places, 11 routes, 4 citizens`, `Doemitz clock HUD attached (Tag 1  |  07:50)` und `Traffic vehicle altstadt_compact_01 started on altstadt_goethestrasse_loop (421.4 m)`. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint04/DoemitzLivingCity.exe)
