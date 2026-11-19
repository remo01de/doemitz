# Sprint 1 · Die erste begehbare Stadt

Planungsrahmen laut Auftrag sind zwei Wochen mit rund 30–50 Arbeitsstunden. Ziel ist eine zu Fuß erkundbare Windows-Demo eines real angelegten Altstadtausschnitts. Einwohner, Fahrzeuge und Missionen sind für spätere Sprints vorgesehen.

| Schritt | Stand | Abnahme |
| --- | --- | --- |
| 1. Projekt und Engine | Git, Git LFS, Arbeitsregeln und Dokumentation eingerichtet. Unreal-Editorstart offen. | C++-Projekt aus der Vorlage Third Person im Editor öffnen und World Partition prüfen. |
| 2. Geodaten | Erster OSM-Snapshot lokal geladen und Offline-Neuaufbau geprüft. | Alle fünf Exportdateien waren beim zweiten Build bytegleich. |
| 3. Koordinaten und Terrain | Lokale Meterkoordinaten und als Platzhalter gekennzeichnete Testgrundfläche exportiert. | Im Engine-Import Achsen, 100 UE-Einheiten pro Meter und Kontrollstrecke prüfen. |
| 4. Straßen und Gebäude | Offen. | Meshes mit Kollisionen erzeugen, Straßenkreuzungen prüfen und Platzhaltermaterialien zuweisen. |
| 5. Spieler und Kamera | Offen. | Gehen, Sprinten, Kamera und Kollisionen in der Altstadt testen. |
| 6. Windows-Demo | Offen. | Einen Windows-Testbuild starten und bei 1080p die Bildrate mit Hardware und Einstellungen erfassen. Ziel sind möglichst stabile 60 FPS. |

## Erster Datenstand

Der [Importbericht](../data/manifests/doemitz-altstadt-initial-import.json) erfasst 146 Straßen- und Wegeabschnitte, 645 Gebäudegrundrisse und 3 Wasserflächen. Die Maßstabsprüfung an der Goethestraße ergibt 35,4291 m in der Projektion und 35,4159 m geodätisch. Die Abweichung dieser Geodatenmessung beträgt 0,0373 %.
