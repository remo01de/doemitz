# Geodaten

## Quelle und Ausschnitt

Der im Manifest versionierte Sprint-Ausschnitt reicht von 11,2428° bis 11,2546° Ost und 53,1398° bis 53,1455° Nord. Er umfasst die Altstadt, die Festung und einen Teil des Elbufers. Die OSM-API liefert den Kartenausschnitt als XML. Falls Polygonringe über den Ausschnitt hinausreichen, ergänzt der Download die fehlenden Bestandteile über den jeweiligen Relationsendpunkt. Der Importbericht nennt URL und SHA-256 jeder verwendeten Datei. [OSM-Karten-API](https://wiki.openstreetmap.org/wiki/API_v0.6#Retrieving_map_data_by_bounding_box:_GET_/api/0.6/map)

Kartendaten © OpenStreetMap contributors, ODbL 1.0. Die Attribution und Lizenzverweise stehen im Manifest, in der lokalen Szene und im Importbericht. Die OSMF beschreibt die Attribution für Spiele und Simulationen. [OpenStreetMap – Urheberrecht und Lizenz](https://www.openstreetmap.org/copyright) · [OSMF – Computerspiele und Simulationen](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines#Computer_games_and_simulations)

## Datenvertrag

- Die drei GeoJSON-Dateien verwenden WGS84 in der Reihenfolge Längengrad, Breitengrad. Straßen sind Linien, Gebäude und Gewässer Flächen. Multipolygone können Innenringe enthalten. [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946)
- Features tragen stabile IDs wie `osm:way:25642325` und `osm:relation:1809795`. Quell-Tags wie `bridge`, `height` und `building:levels` werden, sofern vorhanden, im Originalformat weitergereicht.
- `scene.json` enthält dieselben Layer mit lokalen Koordinaten `[Ost, Nord]` in Metern. Die Projektion ist ETRS89 / UTM 33N, EPSG:25833. Die Szene nennt Ursprung, Achsen und Einheit. [GeoPortal MV – Geowebdienste und Bezugssysteme](https://www.geoportal-mv.de/portal/Geowebdienste/Hinweise_zu_Geowebdiensten)
- Die Szene markiert die Grundfläche mit `flat_placeholder` und 0 m lokaler Höhe. Das amtliche Höhenmodell steht noch aus. Die Mesh-Stufe verwendet Polygonflächen für Gebäude und Wasser und puffert Straßenachsen anhand ihrer Breiten. Schnittflächen von Straßen werden vereinigt. Brücken werden im Prototyp auf der flachen Grundfläche dargestellt. Tunnel werden aus der sichtbaren Straßenfläche ausgelassen. Wasser ist eine visuelle Fläche über der durchgehenden Grundfläche.
- Die geometrischen Platzhalter verwenden, sofern verfügbar, OSM-Höhen und -Breiten. Die Höhe aus der Anzahl von Stockwerken beträgt 3 m je Stockwerk. Gebäude ohne Höhenangabe sind standardmäßig 6,5 m hoch, Nebengebäude wie Garagen und Schuppen 2,8 m. Straßen ohne Breitenangabe verwenden Werte nach Straßenklasse. Der Mesh-Export nennt für Höhe und Breite jeweils die angewendete Quelle.
- Die Gehwegfläche der Goethestraße leitet sich aus der OSM-Straßenachse und der im Pilotmanifest geschätzten Breite je Seite ab. Der Mesh-Export protokolliert die Breitenquelle und die erzeugte Gehwegfläche. [Pilotmanifest](../data/manifests/doemitz-altstadt-streets.json)
- Die Kontrollstrecke ist der Luftlinienabstand zweier OSM-Knoten auf der Goethestraße zwischen Rathausplatz und Fritz-Reuter-Straße. Der Build prüft, dass die Knoten in der exportierten Straßenachse liegen, und vergleicht die lokale Strecke mit der WGS84-Geodäte. Unreal misst dieselbe Strecke zwischen zwei Actors im Stadtlevel. [OSM – Goethestraße](https://www.openstreetmap.org/way/25642325)

## Reproduzierbarkeit

Ein erneuter `build` verarbeitet den vorhandenen lokalen Snapshot. Für einen identischen Export dieselben XML-Dateien und den gleichen Toolstand verwenden. Einen späteren Abruf mit `fetch --raw-dir <neuer-ordner>` separat ablegen und mit `build --raw-dir <neuer-ordner> --output-dir <export-ordner>` verarbeiten. Die API liefert bei jedem Abruf den verfügbaren Datenstand. Die SHA-256-Werte im [Erstimportbericht](../data/manifests/doemitz-altstadt-initial-import.json) identifizieren den lokal gespeicherten ersten Snapshot.
