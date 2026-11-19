# Technische Architektur

## Geodaten und Weltaufbau

1. Python lädt einen begrenzten OSM-Ausschnitt einschließlich benötigter Multipolygon-Bestandteile. Der Offline-Build filtert die Sprint-Layer, beschneidet sie auf den Ausschnitt und prüft die Geometrie.
2. Die Pipeline projiziert die Geometrie nach ETRS89 / UTM 33N und verschiebt sie zu einem versionierten lokalen Ursprung. `scene.json` ist die Übergabe an die Weltgenerierung. [Koordinaten und Datenvertrag](GEO_DATA.md)
3. Die geplante Mesh-Stufe erzeugt aus Flächen und Straßenachsen Gelände, Gebäudekörper und Straßen. Sie berücksichtigt Polygonlöcher, erzeugt Kollisionen und dokumentiert abgeleitete Gebäudehöhen und Fahrbahnbreiten.
4. Ein Editor-Import soll die erzeugten Assets anhand ihrer IDs aktualisieren. World Partition verwaltet die räumliche Zuordnung der Actors. Projektweit bleibt `X = Nord`, `Y = Ost` und `Z = Höhe` beim Übergang in das linkshändige Unreal-System. Jeder Meter wird zu 100 Unreal Units. Die Achsenabbildung vertauscht die beiden horizontalen Achsen gegenüber `[Ost, Nord]` und muss bei Flächennormalen und Dreiecksreihenfolge berücksichtigt werden.

## Unreal-Laufzeit

| Verantwortungsbereich | Technik und Aufgabe |
| --- | --- |
| Welt und Streaming | C++ für gemeinsame Systeme, World Partition für sichtbare Stadtbereiche |
| Charakter | Third-Person-Steuerung, Kamera und Sprint, Konfiguration per Blueprint |
| Stadtgenerierung | Python und Blender oder Unreal PCG im Editor |
| Zeit, Verkehr, Einwohner | Laufzeitzustand in C++, Navigation und StateTree für die Darstellung und das Verhalten |
| Wirtschaft und Spielstand | C++, Data Assets, Unreal SaveGame |
| Bedienoberfläche | UMG für Karte, Uhrzeit und spätere Interaktionen |

Einwohner, Fahrzeuge und Orte erhalten stabile IDs. Ihr Zustand kann weitergeführt werden, wenn die zugehörigen Actors durch Streaming entladen sind. Die Singleplayer-Simulation läuft lokal.
