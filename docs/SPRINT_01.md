# Sprint 1 · Die erste begehbare Stadt

Planungsrahmen laut Auftrag sind zwei Wochen mit rund 30–50 Arbeitsstunden. Ziel ist eine zu Fuß erkundbare Windows-Demo eines real angelegten Altstadtausschnitts. Einwohner, Fahrzeuge und Missionen sind für spätere Sprints vorgesehen.

| Schritt | Stand | Abnahme |
| --- | --- | --- |
| 1. Projekt und Engine | Das Projekt startet in UE 5.8.4 mit einem C++-Spielmodul und der Third-Person-Blueprint-Figur. | Das Win64-Editor-Ziel kompiliert mit MSVC 14.50.35740 und Windows SDK 10.0.26100.0. World Partition initialisiert in der Altstadt-Karte im Editor und im Play-Modus. |
| 2. Geodaten | Erster OSM-Snapshot lokal geladen und Offline-Neuaufbau geprüft. | Alle fünf Exportdateien waren beim zweiten Build bytegleich. |
| 3. Koordinaten und Terrain | Flache Testgrundfläche und lokale Meterkoordinaten importiert. | Unreal misst 35,4291 m zwischen den beiden Referenzpunkten. Das sind rund 0,037 % Abweichung gegenüber der WGS84-Geodäte. |
| 4. Straßen und Gebäude | Straßenflächen, Wasser und Gebäudekörper mit Platzhaltermaterialien gespeichert. Prüfrays treffen Boden, Gebäudewand und Dach. | Kreuzungen und höhenversetzte Straßenverläufe prüfen. |
| 5. Spieler und Kamera | Bewegung und Maussteuerung in der Altstadt im Play-Modus geprüft. Die linke Umschalttaste ist der C++-Sprintmechanik zugeordnet. | Im Play-Modus für `IA_Sprint` 600 → 750 → 600 cm/s verifiziert. Ein längerer Lauf zur Kollisionsprüfung steht aus. |
| 6. Windows-Demo | Win64-Development-Build erstellt und als eigenständiges Spiel in der Altstadt gestartet. | Auf dem Test-PC im Mittel 9,6 FPS bei 1920 × 1080. Das Ziel von möglichst stabilen 60 FPS bleibt offen. |

## Windows-Starttest

Test-PC mit Intel Core i5-1135G7, Intel Iris Xe und 16 GB RAM. Der Build lief im Fenster mit 1920 × 1080 und Unreal-Qualitätsstufe 3. Die Engine wählte für den verfügbaren Grafikadapter DirectX 11 mit Shader Model 5. Die letzten 240 Frames der 360-Frame-Startaufnahme lagen im Mittel bei 104,1 ms pro Frame. Das 95. Perzentil lag bei 162,7 ms. Eine Messung auf einer festgelegten Laufstrecke steht aus.

## Erster Datenstand

Der [Importbericht](../data/manifests/doemitz-altstadt-initial-import.json) erfasst 146 Straßen- und Wegeabschnitte, 645 Gebäudegrundrisse und 3 Wasserflächen. Die Maßstabsprüfung an der Goethestraße ergibt 35,4291 m in der Projektion und 35,4159 m geodätisch. Die Abweichung dieser Geodatenmessung beträgt 0,0373 %.
