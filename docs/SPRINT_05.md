# Sprint 5 · SaveGame-System und Zeitsteuerung

Sprint 5 ergänzt das lokale Spielstandssystem über Unreal `USaveGame` sowie eine direkte Zeitsteuerung im Spiel. Gespeichert werden der zentrale Simulationszustand und die zugehörigen stabilen IDs, unabhängig davon, welche 3D-Actors gerade geladen sind.

| Meilenstein | Abnahme |
| --- | --- |
| SaveGame-Persistenz | `UDoemitzSimulationSubsystem::SaveCityState` und `LoadCityState` speichern und laden Spieltag, Uhrzeit, Zeitfaktor, Spielerposition/-rotation, alle Einwohnerzustände (inkl. aktiver Route und Fortschritt) sowie Fahrzeugpositionen per stabiler ID. |
| Zeit- und Spielstand-Steuerung | `F5` speichert, `F9` lädt den Quicksave-Slot, `1` / `2` / `3` wählen 1x / 5x / 15x Spielzeit, `P` pausiert oder setzt die Simulation fort. Das UMG-HUD zeigt die aktive Zeitstufe und kurze Statusmeldungen an. |
| Windows-Demo | Ein Win64-Testbuild startet in der Altstadt mit Simulation, Fahrzeug, Tag-/Nachtwechsel, HUD und SaveGame-System. |

## Umsetzung

- **SaveGame-Klasse:** [DoemitzSaveGame.h](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Public/Simulation/DoemitzSaveGame.h) definiert `UDoemitzSaveGame` (`SaveSchemaVersion = 1`) mit `FDoemitzSavedCitizen` und `FDoemitzSavedVehicle`.
- **Simulations-Persistenz:** [DoemitzSimulationSubsystem.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Simulation/DoemitzSimulationSubsystem.cpp) speichert und lädt alle Zustände über `UGameplayStatics::SaveGameToSlot` / `LoadGameFromSlot`, baut laufende Einwohner-Routen beim Laden wieder auf und synchronisiert `ADoemitzTrafficVehicle` (`RestoreMotionState`) sowie `ADoemitzDayNightController` sofort nach dem Laden.
- **Steuerung & HUD:** [DoemitzSimulationConfig.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/Simulation/DoemitzSimulationConfig.cpp) verarbeitet die Tastenkürzel `F5`, `F9`, `1`, `2`, `3` und `P`; [DoemitzClockWidget.cpp](../unreal/DoemitzLivingCity/Source/DoemitzLivingCity/Private/UI/DoemitzClockWidget.cpp) zeigt Zeitstufe (`Pause`, `1x`, `5x`, `15x`) und Meldungen bzw. Steuerungshinweis an.

## Prüfungen

- **Editor-Build:** `DoemitzLivingCityEditor` (Win64 Development) fehlerfrei kompiliert.
- **Play-Modus (PIE):** `VerifySaveGame.py` bestand mit `DOEMITZ_SAVEGAME_PIE_OK`:
  - Spielstand bei `483,0 min` (Tag 1, 4 Einwohner, 1 Fahrzeug, Anna auf dem Arbeitsweg) in Test-Slot gespeichert.
  - Uhrzeit auf Nacht (`00:15`), Spielerposition (+8 m) und Fahrzeugdistanz (+50 m) gezielt verändert.
  - Nach `LoadCityState` wurden Uhrzeit, Taglicht, Spielerposition, Fahrzeugdistanz sowie Einwohner-Bewegungszustand und -Position exakt wiederhergestellt; Test-Slot anschließend gelöscht.
- **Windows-Testbuild:** Das archivierte Win64-Development-Paket wurde erfolgreich erstellt und im Starttest mit `-nullrhi` verifiziert: `/Game/Maps/DoemitzAltstadt` geladen, World Partition initialisiert, `Doemitz simulation started at 470.0 min (scale 60.0x): 5 places, 11 routes, 4 citizens`, `Doemitz clock HUD attached (Tag 1  |  07:50  (1x))` und `Traffic vehicle altstadt_compact_01 started on altstadt_goethestrasse_loop (421.4 m)`. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint05/DoemitzLivingCity.exe)
