# Technische Architektur

## Geodaten und Weltaufbau

1. Python lädt einen begrenzten OSM-Ausschnitt einschließlich benötigter Multipolygon-Bestandteile. Der Offline-Build filtert die Sprint-Layer, beschneidet sie auf den Ausschnitt und prüft die Geometrie.
2. Die Pipeline projiziert die Geometrie nach ETRS89 / UTM 33N und verschiebt sie zu einem versionierten lokalen Ursprung. `scene.json` ist die Übergabe an die Weltgenerierung. [Koordinaten und Datenvertrag](GEO_DATA.md)
3. Die Mesh-Stufe erzeugt aus Flächen und Straßenachsen eine flache Testgrundfläche, Wasser, Gebäudekörper und Straßen. Sie trennt Straßenmaterialien über überschneidungsfreie Flächen und ergänzt im konfigurierten Pilotabschnitt erhöhte Gehwege. Sie trianguliert Flächen mit ihren Polygonlöchern und vermerkt die Herkunft der Höhen und Breiten im Mesh-Export.
4. Der Editor-Import aktualisiert die generierten Assets und Actors. Der 1:1-Übergang verwendet `X = Nord`, `Y = Ost` und `Z = Höhe` mit 100 Unreal Units pro Meter. Der Koordinatentausch berücksichtigt die Dreiecksreihenfolge beim Übergang in das linkshändige Unreal-System. Die Altstadt-Karte verwendet World Partition. Seit Sprint 14 zerlegt die Mesh-Stufe die Stadt-Meshes in Zellen von 256 m (`<Mesh>__cX_Y`); diese Zellen, die Geländekacheln und die Requisiten je Zelle werden räumlich geladen. Immer geladen bleiben Landmarken (`<Mesh>__lm`: Kirche, Rathaus, Festungsbauten, Speicher), Festungsmauern, Schleuse, Brücken und Wasser. Der Import setzt das Laufzeitraster (Zellgröße 256 m, Laderadius 1000 m) über `UDoemitzWorldTools::ConfigureStreamingGrid`. Ohne HLOD bleibt der Radius so groß, dass von jedem Punkt der heutigen Fläche keine Lücke am Horizont entsteht. Boden, Gebäudewände und Dächer kollidieren in Unreal.

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
