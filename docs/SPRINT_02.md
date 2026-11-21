# Sprint 2 · Straßen, Gehwege und erstes Fahrzeug

Der erste Abschnitt liegt an der Goethestraße, wo die Spielfigur in der Altstadt startet. Die Bilder in `Images/` dienen als Referenz für warme Farbtöne und eine gut lesbare Gliederung des Straßenraums. Die Straßenachsen und Gebäudegrundrisse stammen aus dem vorhandenen OpenStreetMap-Snapshot.

| Meilenstein | Abnahme |
| --- | --- |
| Straßenoberflächen und Gehwege an der Goethestraße | Der Offline-Import erzeugt die Karte aus dem vorhandenen Snapshot. Die Fahrbahn und die erhöhten Gehwege sind sichtbar. Die Spielfigur kann den Bordstein in beide Richtungen überqueren. |
| Erstes Fahrzeug | Ein erstes Fahrzeug bewegt sich im Altstadtausschnitt auf einer festgelegten Teststrecke. Route und Fahrzeug erhalten stabile IDs. Routenfortschritt und Darstellung bleiben getrennt. |
| Windows-Demo | Ein Win64-Testbuild startet in der Altstadt. Eine definierte Strecke dient zur Prüfung von Bewegung und Bildrate. |

## Goethestraße

Der Mesh-Generator unterscheidet anhand der OSM-Tags Steinbeläge, sonstige Fahrbahnen und schmale Wege. Die Goethestraße trägt in OSM den Wert `unhewn_cobblestone` und erhält eine warme Steinfarbe. Der Generator setzt auf beiden Seiten einen 1,6 m breiten Gehweg mit einem 12 cm hohen Bordstein über der sichtbaren Fahrbahn an. Breite und Höhe sind Annahmen für den Pilotabschnitt auf der flachen Testlandschaft. Der Gehweg wird an Straßenflächen, Fußwegen, Gebäudegrundrissen und Wasserflächen ausgeschnitten. [Konfiguration des Pilotabschnitts](../data/manifests/doemitz-altstadt-streets.json)

Die Farbmaterialien und Geometrie entstehen im Projektimport. Kartendaten © OpenStreetMap contributors, ODbL 1.0. [Geodaten und Quellen](GEO_DATA.md)

## Erstes Fahrzeug

Das Pilotmanifest definiert ein erstes Fahrzeug (`altstadt_compact_01`) auf dem geschlossenen 421,4 m langen Altstadtkurs `altstadt_goethestrasse_loop` aus sechs verbundenen OpenStreetMap-Straßenabschnitten um die Goethestraße. Der Offline-Generator rundet Kurven und prüft die Fahrzeugkontur gegen Fahrbahnkorridor, Gebäude und Wasserflächen. In Unreal trennt `FDoemitzVehicleMotion` den Routenfortschritt (Strecke und Runden) von der Darstellung in `ADoemitzTrafficVehicle`. Ein eigener Low-Poly-Kompaktwagen (`SM_CompactCar`) entsteht im Editor-Import aus `doemitz_vehicle_mesh.py` ohne Fremdassets. Vor der Spielfigur bremst das Fahrzeug über eine Box-Sweep-Prüfung ab und setzt die Fahrt fort, sobald die Fahrbahn frei ist. [Konfiguration des Pilotabschnitts](../data/manifests/doemitz-altstadt-streets.json)

## Prüfungen

- **Offline-Build und Python-Tests:** 146 Straßen- und Wegeabschnitte, 645 Gebäude und 3 Wasserflächen mit 0 Geometriefehlern verarbeitet. Der Mesh-Export (11 Meshes, 12.793 Dreiecke) war bei Wiederholung bytegleich (`SHA-256` identisch). Alle 5 Python-Tests liefen erfolgreich.
- **Editor-Build und Altstadt-Import:** `DoemitzLivingCityEditor` (Win64 Development) kompiliert. `Import-Altstadt.ps1` importierte 11 Meshes und `altstadt_compact_01` auf `altstadt_goethestrasse_loop` (421,4 m). Die Kontrollstrecke maß 35,4291 m bei 0,0372 % Abweichung gegenüber der Geodäte; Kollisionstests mit Boden, Wänden, Dächern und Gehweg bestanden.
- **Play-Modus (PIE):**
  - Gehweg: Die Spielfigur lief von der Fahrbahn etwa 3,40 m auf den Gehweg und zurück; die Höhe an beiden Endpunkten passte.
  - Fahrzeug (`VerifyTraffic.py`): `altstadt_compact_01` hielt nach 1,89 m vor dem Spieler auf der Fahrbahn an, fuhr nach dem Wechsel des Spielers auf den Gehweg weiter und vollendete eine komplette 421,4 m-Runde.
- **Windows-Testbuild:** Das archivierte Win64-Development-Paket wurde neu erstellt und lud die Altstadt im Starttest mit `-nullrhi` einschließlich World Partition und Start von `altstadt_compact_01` auf `altstadt_goethestrasse_loop`. Die 1080p-Streckenmessung (Bewegung und Bildrate) steht noch aus. [Windows-Testbuild](../unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint02/DoemitzLivingCity.exe)
