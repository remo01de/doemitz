# Sprint 14 · Stadtgebiet bis Hafen und Schleuse

Stand: Plan (23.11.2026), noch nicht umgesetzt.

## Ziel

Das spielbare Gebiet wächst von der Altstadt nach Südosten bis zum Hafen Dömitz und zur Schleuse Dömitz der Müritz-Elde-Wasserstraße. Spieler, Einwohner und Fahrzeuge erreichen den Hafen über echte Straßen. Hafenbecken, Stege, Speicher und Schleuse sind als erkennbare Bauwerke modelliert. Die gewachsene Welt wird in Zellen zerlegt und über World Partition gestreamt (Roadmap-Punkt aus Sprint 11 und 12). Das Ziel von mindestens 15 FPS auf dem Test-PC gilt weiter.

## Entscheidungen des PO

- **Der Festungsgraben bleibt Wasser.** Der Wasserstand hängt stark von der Witterung ab; der trockene Graben auf manchen Fotos ist ein Momentzustand. Der Punkt „Graben als Wiese“ aus Sprint 13.1 entfällt.
- Die Erweiterung geht in Richtung Hafen und Schleuse. Andere Richtungen sind nicht Teil dieses Sprints.

## Ausgangslage

- Ausschnitt bisher: `bounds_lonlat [11.2428, 53.1398, 11.2546, 53.1455]`, lokal etwa x −411…+411 m, y −338…+338 m, 0,50 km². Ursprung `origin_lonlat [11.2487, 53.14265]`, Bezugshöhe 13,001 m NHN.
- Hafen und Schleuse liegen südöstlich knapp außerhalb (Erkundung mit OSM-API am 23.11.2026):

| Objekt | OSM | Lage (lokal, m) | Hinweise |
| --- | --- | --- | --- |
| Schleuse Dömitz | `osm:way:161040933` (`lock=yes`, `lock_name=Schleuse Dömitz`), Kammer `osm:way:1315856502` (`water=lock`), Tore `osm:way:1315856503` und `osm:way:1315856504` (`waterway=lock_gate`) | etwa (763, −280) | Wehr `osm:way:42707704`, Fischtreppe `osm:way:96024317`, Straßenbrücke `osm:way:42325141` (`bridge=yes`, `layer=1`), Gebäude an der Kammer `osm:way:42883859` |
| Hafen Dömitz | Hafenfläche `osm:way:1355845079` (`landuse=harbour`), Marina `osm:node:431057011`, Motoryachtclub `osm:node:2117939128` und Steg `osm:way:117654901`, insgesamt 29 Stege (`man_made=pier`), Liegeplätze (`seamark:type=mooring`), Fähranleger `osm:way:1355845322` | etwa (670, −520) | Straßen „Am Hafen“ (`osm:way:25151524`, `osm:way:42707474`), „Hafenplatz/Alte Lüneburger Bahn“ (`osm:way:306167214`), Platz `osm:way:1355844659` |
| Speicher | `osm:way:42883863` | etwa (710, −566) | OSM `height=60` ist falsch. LoD2 `DEMVAL76000hCycv`: Satteldach, Traufe 20,23 m, First 32,37 m. Zweithöchstes Bauwerk nach der Kirche (39,22 m). |
| Weitere Orte | Hotel Dömitzer Hafen `osm:node:387219809`, Dömitzer Hafen Restaurant `osm:node:1125977013`, Wasserwanderzentrum `osm:node:674133513`, Cafés, Bar, Imbiss, Pensionen, Feuerwehr, ehemaliger Grenzturm | Hafen und Werder | Öffnungszeiten teils in OSM |

- Im Erweiterungsstreifen liegen 147 OSM-Gebäude (207 LoD2-Gebäude), 29 Stege, 9 Mauern und eine Stützmauer, 5 Buhnen, Kanal, Schleusenkammer, Wehr, Fischtreppe sowie etwa 70 Wege aller Klassen.
- **Amtliche Daten liegen schon vor:** Hafen und Schleuse liegen in der vorhandenen DGM1- und LoD2-Kachel `33_248_5894` (UTM E 248–250 km, N 5894–5896 km). Ein neuer Download ist nur nötig, wenn der gewählte Zuschnitt samt 50-m-Rand diese Kachel verlässt.

## Gebietszuschnitt

Vorgabe: `bounds_lonlat [11.2428, 53.1372, 11.2607, 53.1455]`.

- Das sind lokal etwa x −426…+819 m und y −648…+338 m, 1,11 km² (2,2-fach).
- Projiziert ergibt das UTM E 248703–249948 und N 5894067–5895052. Mit 50 m Rand reicht das bis E 249998 und N 5894017, also noch in Kachel `33_248_5894`. Das muss die Kachelsuche (`discover`) bestätigen. Verlangt sie Nachbarkacheln, werden diese mit den vorhandenen Befehlen geladen und Lizenz und Quellen ergänzt.
- **Ursprung, Bezugshöhe und Achsenabbildung bleiben unverändert.** Damit gelten alle lokalen Koordinaten, Spielstände (v7) und Manifest-Positionen weiter.
- Der Campingplatz südlich des Hafens (`osm:way:310930661`) bleibt außerhalb.

## Meilensteine

| Nr. | Meilenstein | Inhalt | Abnahme |
| --- | --- | --- | --- |
| 0 | Daten und Zuschnitt | Neuer OSM-Ausschnitt mit allen benötigten Multipolygon-Bestandteilen (Hafen- und Elbwasserflächen). Der Ausschnitt wird für die ganze Fläche neu geladen. Deshalb kommt ein Diff-Bericht der Altstadt zwischen altem und neuem OSM-Stand dazu. `bounds_lonlat` in `data/manifests/doemitz-altstadt.json`, Kartenmetadaten und Importbericht anpassen. Stadtkarte mit höchstens 0,5 m/px. | Jede in den Manifesten referenzierte OSM-ID existiert weiter (Landmarken, Mauern, Tore, Innenräume, Straßen, Plätze) oder ist begründet ersetzt. Der Offline-Build ist bytegleich wiederholbar. |
| 1 | Wasser | Hafenbecken, Kanal, Schleusenkammer und Elbe als Wasserflächen. Der Wasserstand kommt je Gewässer aus DGM1 (Stand der Befliegung) und ist als `dgm1_capture_level` gekennzeichnet. Ober- und Unterwasser der Schleuse sind getrennte Flächen mit eigener Höhe, geteilt an den Toren. Eine versionierte Übersteuerung je Gewässer in der Konfiguration bereitet spätere Witterungsstände vor. Der Festungsgraben bleibt unverändert Wasser. | Kein Gelände ragt durch Wasserflächen, keine Lücke zwischen Wasser und Ufer. Ober- und Unterwasser haben einen sichtbaren Höhenunterschied, im Bericht dokumentiert. |
| 2 | Schleuse Dömitz | Kammerwände aus Beton oder Mauerwerk entlang `water=lock` bis über Oberwasser. Zwei Stemmtorpaare an den `lock_gate`-Wegen, statisch geschlossen, mit begehbarem Steg und Geländer. Poller und Leitern an der Kammer, das Gebäude an der Kammer aus LoD2, Wehr und Fischtreppe als einfache Bauwerke, die Straßenbrücke `osm:way:42325141` über die bestehende Brückenpipeline. Maße als `assumed_sprint14_lock` gekennzeichnet, Referenzfotos mit Lizenz im Referenzmanifest. | Kammer, Tore und Brücke sind begehbar und kollidieren. Neue PIE-Prüfung: Die Spielfigur geht über die Schleusenbrücke oder den Torsteg, ohne in die Kammer zu fallen. |
| 3 | Hafen | Kaimauern entlang Hafenbecken und Hafenfläche. Stege aus `man_made=pier`: Linien als Holzstege (Breite aus `width`, sonst 2 m, als Annahme gekennzeichnet), Flächen als Plattformen. Liegeplätze als Pfähle. Boote als stilisierte HISM-Requisiten an Stegen und Liegeplätzen, deterministisch gesetzt, mit Kollision wie in Sprint 13.1. Speicher als Landmarke nach LoD2 (Backstein, Ladeluken). Hafenplatz mit Pflaster, Bänken und Laternen. Buhnen an der Elbe als Steinschüttung, wenn sie im Ausschnitt liegen. | Stege tragen die Spielfigur. Kein Boot schneidet Stege oder Kaimauern. Der Speicher steht mit 32,4 m First nach LoD2, nicht mit 60 m. |
| 4 | Straßen, Orte und Simulation | Neue Straßen, Gehwege, Kreuzungen und Parkplätze im Straßengraph, Fahrzeugrouten bis zum Hafen. Neue Orte aus den POIs (Hotel, Restaurant, Cafés, Bar, Imbiss, Pensionen, Wasserwanderzentrum) mit Eingängen und Öffnungszeiten aus OSM, sonst gekennzeichneten Annahmen. Einige Einwohner bekommen Arbeits- oder Freizeitziele am Hafen, Einwohnerzahl bleibt 30. Mindestens eine Aufgabe führt zum Hafen. | `VerifyCitizens`, `VerifyTrafficNetwork`, `VerifyParking`, `VerifyTasks` bestehen mit dem größeren Netz. Ein Fahrzeug erreicht den Hafenparkplatz, ein Einwohner einen Hafenort. |
| 5 | Zellen und Streaming | Die generierten Stadt-Meshes (Wände, Dächer, Giebel, Straßen, Gehwege und andere, bisher je Material ein Mesh für die ganze Stadt) werden in Zellen von 256 m zerlegt. Stabile Asset-Namen: `SM_<Name>_<Zelle>`. HISM-Requisiten ebenfalls je Zelle. Diese Actors werden räumlich geladen (World Partition, Laderadius zunächst 450 m, im Bericht begründet). Immer geladen bleiben Landmarken für die Silhouette (Kirche, Speicher, Festung), Wasser, Simulation, Tag-Nacht-Steuerung und Innenräume in Reichweite. Die Simulation bleibt global; Einwohner und Fahrzeuge brauchen keine geladene Kollision (wie bisher). Spielstand laden und Teleports in PIE warten, bis die Zielzelle gestreamt ist. | Kein sichtbares Loch und kein Durchfallen beim Sprint vom Rathaus zur Schleuse. Spielstand am Hafen laden: Figur steht auf dem Boden. Alle PIE-Prüfungen laufen mit Streaming. |
| 6 | Budgets, Prüfungen und Doku | Geländebudget neu festlegen: maximal 5 cm Fehler in der Altstadt, Dreieckszahl im Bericht. Benchmarkstrecke um „Festungszugang → Hafen → Schleuse“ erweitern oder zweite Strecke anlegen. Screenshots: Schleuse vom Torsteg, Hafen vom Hafenplatz, Speicher, Stege mit Booten, Übergang Altstadt–Hafen. Tests mit festen Zählwerten (Gebäude, Mauern, Brücken, Orte) begründet anpassen, neue Tests für Schleuse, Hafen, Speicherhöhe und Zellen. `docs/GEO_DATA.md` und `docs/ARCHITECTURE.md` (Streaming statt „alles geladen“) aktualisieren. | `python -m unittest discover -s tests` grün, `scripts/Verify-All.ps1` grün (bisherige 20 Prüfungen plus neue), Win64-Build startet, mindestens 15 FPS im Mittel bei 1080p (`DoemitzLow`) auf beiden Strecken. A/B gegen Sprint 13.1 am selben Tag, weil die absoluten Werte des Test-PCs schwanken (siehe Sprint 13.1). |

## Reihenfolge

1. Meilenstein 0 zuerst, mit Diff-Bericht. Wenn der neue OSM-Stand die Altstadt stark verändert, vor dem Weiterbauen mit dem PO klären, ob der alte Stand für die Altstadt eingefroren wird.
2. Danach 1 bis 4 auf Basis des bisherigen Modells (alles geladen), mit FPS-Messung nach jedem Meilenstein.
3. Meilenstein 5 zum Schluss, damit Zerlegung und Streaming an der fertigen Welt gemessen werden.

## Risiken

- **Neuer OSM-Stand in der Altstadt:** geänderte Wege oder Gebäude können Landmarken-Konfiguration, Torvorhof oder Innenräume verschieben. Gegenmittel: ID-Prüfung und Diff-Bericht in Meilenstein 0.
- **Streaming und Prüfskripte:** Teleports in PIE treffen ungeladene Zellen. Gegenmittel: in den Skripten auf den Streaming-Abschluss warten.
- **Leistung:** Die zerlegten Meshes erhöhen die Zahl der Draw Calls, ermöglichen aber Culling. Das muss gemessen und nicht angenommen werden.
- **Wasserstände:** DGM1 zeigt einen Momentzustand. Die Übersteuerung in der Konfiguration hält die Tür für Witterungsstände offen, ohne sie jetzt umzusetzen.

## Nicht im Umfang

- Schleusenbetrieb (Tore bewegen, Kammer füllen), Schiffs- und Fährverkehr.
- Innenräume am Hafen (Speicher, Hotel).
- Witterungsabhängige Wasserstände zur Laufzeit.
- Erweiterung in andere Richtungen.
- Die offenen Punkte der Festung aus Sprint 13.1 (Brustwehr der Bastionsflanken, Zierformen am Sandsteintor, Poternen, Kasematten) bleiben offen.
