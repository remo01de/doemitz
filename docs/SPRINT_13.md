# Sprint 13 · Festungstor, Sichtfehler und erste Innenräume

Stand: Umgesetzt und geprüft, noch nicht committet.

## Ausgangslage nach Sprint 12

Sprint 12 war als `37423b9` auf `main` committet. Die Sichtprüfung der Sprint-12-Screenshots zeigte Fehler, die keine Prüfung erfasst hatte: schwarze Flecken auf Fassaden und Dächern, ein Rathausturm ohne Schaft, ein Tunnelportal auf „Beinen" im Graben, eine Steinbrücke, deren Bogen im Bild nicht zu sehen war. Der Product Owner meldete außerdem zwei Fehler im Spiel:

1. **Wallstraße 6 stimmt nicht.** Das Haus hatte eine Traufhöhe von 2,0 m unter einem 12,9 m hohen Satteldach.
2. **Man kann nicht in die Festung gehen, der Tunnel fehlt.** Die einzige Zufahrt führt über die Grabenbrücken und durch den Torweg im Wall. Dieser Torweg war nicht gebaut.

## Ergebnisse

| Meilenstein | Ergebnis |
| --- | --- |
| Festungstor | Ursache: Die Zufahrt in die Festung ist in OSM der Tunnelweg `osm:way:120431987` (`tunnel=yes`, `layer=-1`, 26,5 m, mit Knick). Der Generator ließ Tunnel aus und baute nur den in Sprint 12 konfigurierten NW-Steg-Gang. Zudem lag DGM1 über dem Torweg auf der Wallkrone (20,1 bis 22,3 m NHN), die 8 m lange Zufahrt `osm:way:416256368` stieg daher von 16,1 auf 22,3 m an. Jetzt gilt allgemein: Für jeden in `tunnel_portals` konfigurierten Tunnel liegt der Boden an jedem Ende auf der niedrigsten DGM-Höhe der direkt anschließenden Straße innerhalb von 15 m (`tunnel_approach_min_dgm`). Die Zufahrt wird linear darauf abgesenkt, und die Brückenwiderlager übernehmen diese Höhe (`tunnel_floor`). Das Gewölbe folgt der OSM-Linie samt Knick, eine Rasenkappe schließt die Wallkrone auf DGM-Höhe, und die Portalwand reicht bis an die Wallkrone. Ergebnis: Torweg 16,32 → 16,00 m NHN (1,21 %), Zufahrt 0,55 %, Grabenbrücken 1,78 %. Lichte Weite 3,6 × 3,9 m, als `assumed_sprint13_gate_passage` gekennzeichnet. Die fünf Kasemattengänge (`osm:way:1312288189` bis `…194`) stehen mit Grund unter `tunnels_not_built` im Report. |
| Festungsmauer (Nachtrag) | Rückmeldung des Product Owners: Die Festung stand ohne Festungsmauer da. DGM1 bildet die Backstein-Futtermauer am Graben als grünen Steilhang ab. Neues Modul `tools/mesh_generator/fortress.py`, konfiguriert unter `fortress_walls` in [`doemitz-altstadt-landmarks.json`](../data/manifests/doemitz-altstadt-landmarks.json). Die Mauerlinie ist der OSM-Umriss `osm:way:42318561` (`historic=castle`), der genau auf dem Innenrand des Festungsgrabens liegt. Die Mauer beginnt 0,6 m unter dem Grabenwasserspiegel und reicht bis zur DGM-Höhe 1–3 m hinter der Linie (über 10 m geglättet, mindestens 2,5 m hoch), also 2,5–11,9 m Höhe auf 785,7 m Länge. Dazu kommen Backsteinabdeckung, ein Gesims 0,9 m unter der Krone und Scharten in den kurzen Flanken nach den Fotos `ref_festung_mauer` und `ref_festung_bastion_held`. Öffnungen gibt es nur dort, wo Wege die Linie kreuzen: am Tor (4,5 m, mit Backsteinwangen bis zum Torportal) und am NW-Steg (5,4 m, Tunnelportal). Das Gelände wird hinter der Mauer bis zur Krone aufgefüllt (4-m-Band) und davor auf Grabenhöhe gesenkt. Die Geländedreiecke werden exakt an der Mauerlinie geteilt, sonst ragten schräge Rasenkeile vor die Mauer. Das Geländebudget steigt dafür versioniert von 150.000 auf 155.000 Dreiecke (`terrain_max_triangles`, Ergebnis 152.073). Die Fotos unter `Images/Festung/` haben teils unbekannte Lizenzen; sie dienten nur als Vorlage und sind nicht im Repository. Im Referenzmanifest stehen die beiden Commons-Fotos mit Urheber und Lizenz. |
| Mauern, Torbau und Sandsteintor (Nachtrag 2) | Der OSM-Export liefert jetzt eine Ebene `walls` (`barrier=wall`/`city_wall`/`retaining_wall` mit Höhe und den `barrier=gate`-Knoten auf der Mauer), gebaut von `tools/mesh_generator/walls.py`. Mauern mit mindestens 1,5 m Geländesprung gelten als Stützmauern: nur die tiefe Seite zeigt Backstein, das Gelände wird oben bis zur Krone aufgefüllt, unten bis zum Fuß gesenkt und an der Mauerlinie geteilt. Öffnungen entstehen an kreuzenden Wegen; ein Tor-Knoten in einer frei stehenden Mauer wird zum Torbogen. Gebaut sind 10 Mauern. Die **Kehlmauer der Bastion Drache** (`osm:way:416256358`, 5 m laut OSM) hat Zinnen, Scharten, zwei Rundtürme mit Kegeldach und einen Torbogen am Knoten `osm:node:4173552055`, nach dem Foto `ref_festung_drache_kehlmauer`. Die **innere Tormauer** (`osm:way:416256360`, 6 m) trägt den Knoten `osm:node:4170573071` „Sandsteintor" (1565); das Torwegportal dort ist jetzt aus Sandstein mit Pilastern, Gebälk und Stufengiebel (`end_styles: sandstone_aedicula`). Der kleine **Torvorhof** zwischen Escarpe und Tormauer bleibt eben auf Torhöhe, die Hilfs-Torwangen entfallen. An der Zugbrücke steht ein **Torbau** mit Durchgang (3,8 m), Pfeilern, Steinband und Satteldach nach dem Foto `ref_festung_zugbruecke`; die Escarpe hat einen grauen Steinsockel bis 1,8 m über dem Grabenwasser. |
| Wallstraße 6 | Ursache: Der LoD2-Import nahm bei Sattel-, Walm- und Flachdächern die tiefste Kante aller Dachflächen als Traufe. Wallstraße 6 (`osm:way:198050053`, `DEMVAL76000gbxna`) hat neben dem 162 m² großen Hauptdach ein 7,7 m² großes Flachdach 0,1 m über dem Boden. Die Traufe ist jetzt für alle Dachformen der flächengewichtete Median der Dachflächen-Unterkanten, wie es bisher nur für die Formen 5000 und 9999 galt. Wallstraße 6: 2,0 m → 8,56 m Traufe bei 12,86 m First. Insgesamt hatten 54 Gebäude eine um mehr als 0,5 m zu niedrige Traufe. |
| 0 · Sichtfehler | **Schwarze Flecken:** Der Vergleich von vier Renderer-Varianten zeigte, dass die Ursache Distance Field AO ist, nicht die virtuellen Schattenkarten. Die generierten Wände, Dächer und Giebel sind offene, einseitige Hüllen über viele Gebäude, ihre Mesh Distance Fields haben kein gültiges Inneres. Alle generierten Stadt- und Geländemeshes erzeugen deshalb keine Distance Fields mehr (`distance_field_resolution_scale = 0`, `affect_distance_field_lighting = False`). Die Screenshots entstehen jetzt mit eingeschalteter DFAO und sind fleckenfrei. Die schwarze Kirchenschiffdachfläche hatte dieselbe Ursache. **Rathausturm:** Der Turm ist in OSM und LoD2 ein eigenes Gebäude (`osm:way:97118216`, LoD2-Traufe 15,27 m, First 21,25 m). Er war als kleines Giebelhaus gebaut, und die Rathaus-Variante setzte zusätzlich einen Mini-Turm. Neue Variante `rathausturm` nach dem Referenzfoto `ref_rathaus_front`: Backsteinschaft bis zur LoD2-Traufe, vier Wimperge, schlanker Schieferhelm bis zum LoD2-First, Wetterstange. Der Mini-Turm ist entfernt. **Tunnelportal NW-Steg:** Ein Fundament unter der Schwelle ersetzt die beiden „Beine" im Graben. Das schräge Element in der Öffnung war das gerade Gewölbe, das den Knick der OSM-Linie nicht mitging; das Gewölbe folgt jetzt der Linie. **Torbrücke:** Material ist laut Konfiguration und Bild Naturstein; die Angabe „Ziegelbögen" im Sprint-12-Bericht war falsch. **Steinbrücke:** Neue Kamera im Graben östlich der Brücke. |
| 1 · Türöffnungen | Kaufhaus, Fritz-Reuter-Apotheke und Rathaus haben eine echte Türöffnung in Außen- und Innenwand, mit Laibung, Schwelle, Steinrahmen und unterbrochenem Sockel. Türbreite 1,2 m (Rathaus 1,6 m), Höhe 2,3 m (Rathaus 2,6 m), als Annahme gekennzeichnet. Die Rathaustür sitzt an der realen Tür, die anderen am auf die Fassade projizierten Gehweg-Zugang. Der Eingang des Orts liegt 0,6 m vor der Tür (`interior_door`). Wo der Boden höher liegt als der Gehweg, entstehen Stufen (Rathaus 0,28 m). Die Tür ist ein eigener Actor (`ADoemitzInteriorDoor`). Sie schwingt bei Annäherung nach innen auf, wenn der Ort geöffnet ist, und lässt einen Spieler von innen immer hinaus. Geschlossen blockiert sie, offen hat sie keine Kollision. |
| 2 · Innenraum-Generator | Neues Manifest [`doemitz-altstadt-interiors.json`](../data/manifests/doemitz-altstadt-interiors.json) mit Innenräumen und Einrichtungsvorlagen. `tools/mesh_generator/interiors.py` erzeugt das Erdgeschoss aus dem OSM-Grundriss: 0,4 m Wandstärke, Boden, Decke auf Geschosshöhe, Innenwände mit denselben Öffnungen wie außen, Tresen, Wandregale, Mittelregale (Kaufhaus), Stuhlreihen und Aushang (Bürgerbüro), Deckenlampen. Jedes Möbelstück wird nur gesetzt, wenn Tresen, Aushang und alle Stehplätze auf einem 0,2-m-Raster mit 0,36 m Kapselradius von der Tür aus erreichbar bleiben. Kaufhaus 660 m² (Tresen, 7 Wandregale, 2 Mittelregale, 12 Lampen), Apotheke 176 m² (Tresen, 8 Regale, 4 Lampen), Bürgerbüro 224 m² (Schalter, 2 Stuhlreihen, Aushang, 4 Lampen). Zusammen 4.274 Dreiecke. Bytegleich bei Wiederholung. |
| 3 · Betreten und Beleuchtung | Die Räume liegen am realen Ort in der durchgehenden Welt, ohne Ladebildschirm. Die Erdgeschossfenster der drei Gebäude sind offen und haben eine durchsichtige, beidseitige Scheibe mit Kollision (`WindowGlassClear`, 68 Fenster). Unter den Räumen schneidet der Geländegenerator das Gelände exakt an der Außenwand ab, sonst ragten vereinfachte Hangdreiecke im Kaufhaus bis zu 0,9 m durch den Boden. Deckenlampen als bewegliche Punktlichter ohne Schatten (45 cd). Die Kamera kollidiert mit Innenwänden und Decke. |
| 4 · Handlungen im Raum | Bei Orten mit Innenraum öffnet sich das Ortsmenü am Tresen statt an der Straßentür. An der Tür erscheint nur bei geschlossenem Ort die Öffnungszeit. Kaufen und Schichtbeginn laufen über das Menü am Tresen, die Figur steht also sichtbar im Raum. Neu ist der Aushang im Bürgerbüro (`UDoemitzTaskBoardWidget`): Er zeigt die Aufgaben des Tages, „Annehmen" trägt sie ins Aufgabenbuch ein. Einwohnergespräche bieten weiter Aufgaben an. |
| 5 · Einwohner im Raum | `GetCitizenPresentationTransform` stellt Einwohner, die an einem Ort mit Innenraum einkaufen oder arbeiten, auf die Stehplätze aus dem Manifest. Arbeitende zuerst hinter den Tresen, Kunden danach in der Reihenfolge ihrer IDs, höchstens 6 je Raum, nur solange der Ort geöffnet ist. Die Simulation bleibt unverändert, nur Actor-Position und Gesprächssuche nutzen die Präsentation. |
| 6 · SaveGame v7 | `SaveSchemaVersion = 7` speichert den Innenraum des Spielers (`PlayerInteriorId`, `PlayerInteriorPlaceId`). Beim Laden sucht ein Trace von knapp unter der Decke den Boden. Existiert der Innenraum nicht mehr, steht der Spieler am Eingang des Orts. Spielstände v6 laden ohne Innenraum. Der Boden-Trace für Spielstände filtert zusätzlich Decke, Möbel, Lampen, Türen und Aushang. |

## Weitere Änderungen

- `Run-Benchmark.ps1 -InteriorPlaceId <Ort>` misst einen Gang durch einen Innenraum um 22:00 Uhr.
- `CaptureSprint13Screenshots.py` erzeugt 20 Ansichten aus festen Kameras, die Innenansichten berechnet es aus dem Paket.
- `.venv` im Hauptverzeichnis lädt fest den Code aus `C:\Users\Remo\Projects\Doemitz` (eingebettetes Python mit `..\..` im `._pth`). Aus einem Worktree heraus braucht man eine eigene `.venv`.

## Prüfungen

Alle Prüfungen liefen im Worktree auf dem Endstand, mit einer eigenen `.venv`.

1. **Offline-Build und Python-Tests:** `python -m unittest discover -s tests` besteht mit **59 von 59** Tests. Neu sind 15 Tests in `tests/test_sprint13.py`:
   - Festungstor gebaut, Boden auf Zufahrtshöhe, Neigung ≤ 6 %.
   - Festungsmauer entlang des Umrisses, Öffnungen nur an Tor und NW-Steg, Fuß unter Wasser, Kollision, Referenzen vorhanden.
   - OSM-Mauern: Kehlmauer Drache frei stehend mit Türmen, Zinnen und Torbogen, innere Tormauer als Stützmauer mit Öffnung am Torweg, Sandsteintor-Stil.
   - Zufahrt und Grabenbrücken eben.
   - Traufe von Wallstraße 6 kommt aus dem Hauptdach.
   - Kein LoD2-Gebäude hat eine 2-m-Traufe unter hohem Dach.
   - Rathausturm überragt das Rathaus.
   - Interior-Manifest verweist auf existierende Gebäude und Orte.
   - Tür sitzt am Eingang (±10 cm).
   - Raum liegt im OSM-Grundriss.
   - Alle Stehplätze, Tresen und Aushang sind von der Tür aus erreichbar.
   - Möblierung je Raumtyp stimmt.
   - Innenraum-Meshes haben Kollision, Scheiben sind beidseitig.
   - Fenster sind innen und außen gleich geöffnet.
   - Bytegleicher Build in `flat` und `dgm1`.

   Angepasst wurden:
   - `test_sprint12`: Rathausturm als 10. Wahrzeichen, Widerlagerquelle `tunnel_floor`, Rathaus-Eingang an der Tür.
   - `test_sprint11`: Maßgeblich ist die tiefste Wandkante je Punkt, weil Wandstreifen über Öffnungen höher beginnen. Das Geländebudget kommt aus dem Manifest (155.000).
   - `test_sprint11_1`: Das Straßennetz wird mit denselben Tunneln nachgebaut wie im Paket.

   Kennzahlen des Pakets:
   - 184 Meshes mit 344.468 Dreiecken.
   - Gelände 152.674 Dreiecke (Budget 155.000). maximale Abweichung 4.95 cm.
   - Gebäude 152.624 Dreiecke, vorher 139.520. Der Zuwachs kommt von höheren Wänden bei den 54 korrigierten Trauf-Gebäuden, dem Rathausturm und den Öffnungen.
   - Innenräume 4.274 Dreiecke.
2. **Editor-Build** (`DoemitzLivingCityEditor Win64 Development`): `Result: Succeeded`.
3. **Unreal-Import** (`scripts/Import-Altstadt.ps1`): `DOEMITZ_IMPORT_OK: 184 meshes, 35.4291 m reference, 0.0374% error`. Kollision von Gelände, Dach, Wand, Gehweg und den 5 Brücken bestanden.
4. **PIE** (`scripts/Verify-All.ps1`): **`DOEMITZ_VERIFY_ALL_OK: 19/19 PIE checks passed.`** Neu:
   - `VerifyInteriors.py`: Der Spieler läuft am Montag um 10:00 durch die sich öffnende Apothekentür zum Tresen, das Menü öffnet sich, ein Kauf bucht 395 ct ab. Am Sonntag bleibt die Tür zu, der Spieler kommt nicht hindurch, und das HUD zeigt „geschlossen, öffnet Mo 08:00". Am Aushang im Bürgerbüro werden 3 Angebote angezeigt, das erste ist danach aktiv. 6 Einwohner stehen im Kaufhaus auf verschiedenen Plätzen, der Verkäufer hinter dem Tresen. Ein Spielstand im Kaufhaus lädt auf den Boden (94 cm Kapselmitte über Boden) mit der richtigen Innenraum-ID.
   - `VerifyFortressGate.py`: Der Spieler läuft in 12,8 s von „An der Festung" über die Grabenbrücken durch den Torweg in den Festungshof, ohne hängen zu bleiben. Höchstens 7,6 cm Abweichung vom Durchgangsboden bei 587 Messungen im Torweg.
   - `VerifyInteraction.py`: Das Menü öffnet sich jetzt am Tresen. An der Straßentür wird ein geschlossener Ort weiter abgewiesen.
   - `VerifySaveGame.py`: v7 speichern und laden, Migration v4/v5/v6 → v7, ein entfernter Innenraum führt zum Eingang.
   - `VerifyBridges.py`: NW-Steg → Tunnel `max_dev = 2,27 cm` (≤ 5 cm).
5. **Win64-Build** (`scripts/Build-Windows.ps1`, Archiv `unreal/DoemitzLivingCity/Saved/Builds/Win64Sprint13` im Hauptverzeichnis, Stand mit Festungsmauer): `BUILD SUCCESSFUL`. Ohne Parameter gestartet: läuft nach 15 s stabil, 935 MB Arbeitsspeicher, dann beendet.
6. **Benchmark `DoemitzLow`** (i5-1135G7 / Iris Xe, 1920×1080, 8 Fahrzeuge):

| Lauf | FPS (Mittel) | Frametime Mittel / p95 / p99 | Frames |
| --- | ---: | --- | ---: |
| Strecke, Lauf 1 (90 s) | 69,05 | 14,48 / 16,14 / 17,04 ms | 6.215 |
| Strecke, Lauf 2 (90 s) | 66,26 | 15,09 / 17,42 / 19,01 ms | 5.964 |
| Kaufhaus innen, 22:00, 12 Lampen (60 s) | 64,58 | 15,48 / 17,29 / 18,47 ms | 3.875 |
| Strecke mit Festungsmauer, Lauf 1 (90 s) | 66,86 | 14,96 / 17,20 / 18,23 ms | 6.018 |
| Strecke mit Festungsmauer, Lauf 2 (90 s) | 64,02 | 15,62 / 20,24 / 30,37 ms | 5.762 |
| Strecke mit Mauern, Torbau und Sandsteintor, Lauf 1 (90 s) | 72,57 | 13,78 / 15,38 / 16,15 ms | 6.531 |
| Strecke mit Mauern, Torbau und Sandsteintor, Lauf 2 (90 s) | 72,50 | 13,79 / 15,67 / 16,64 ms | 6.526 |

Ziel ≥ 15 FPS erfüllt. Die ersten drei Läufe entstanden vor der Festungsmauer, die folgenden mit ihr. Die Strecke liegt 10–25 % über Sprint 12 (58,2 FPS); die Streuung zwischen den Sitzungen ist größer als der Einfluss der Mauern. Die Ursache habe ich nicht isoliert. Naheliegend ist, dass die Stadtmeshes keine Distance Fields mehr erzeugen; belegt ist das nicht.

## Sichtprüfung

Alle Bilder entstehen mit `CaptureSprint13Screenshots.py` (1280×720, Editor-Spielansicht, Distance Field AO und virtuelle Schattenkarten eingeschaltet, Lumen aus) unter `unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/`.

| Bild | Was zu sehen ist |
| --- | --- |
| [01_johanneskirche.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/01_johanneskirche.png) | Westturm mit Fialen und Helm, Kirchenschiff. Keine schwarzen Flecken mehr; die linke Schieferdachfläche liegt im Schatten und ist dunkelgrau, nicht schwarz. |
| [02_rathaus.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/02_rathaus.png) | Fachwerkfassade ohne dunklen Schleier, Mansarddach mit drei Gauben, Turmhelm hinter dem Dach. |
| [03_festung.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/03_festung.png) | Festungsbauten von oben, Fassaden und Dächer fleckenfrei. |
| [04_torbruecke.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/04_torbruecke.png) | Torbrücke aus hellem Naturstein mit drei Bögen und zwei Flusspfeilern. |
| [05_steinbruecke.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/05_steinbruecke.png) | Blick aus dem Graben: Gewölbebogen der Steinbrücke mit Durchblick. |
| [06_nw_steg_tunnelportal.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/06_nw_steg_tunnelportal.png) | NW-Steg führt durch eine Öffnung der Festungsmauer in das Backsteinportal, das auf einem durchgehenden Fundament steht; links und rechts Mauer mit Gesims und Scharten. |
| [07_festungstor_aussen.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/07_festungstor_aussen.png) | Von der Zugbrücke: Torbau mit Giebel in der Festungsmauer, dahinter der Torvorhof und das Sandsteintor mit dem Torweg. |
| [08_festungstor_durchfahrt.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/08_festungstor_durchfahrt.png) | Im Torweg: Tonnengewölbe, Boden, am Ende der Festungshof mit Gebäude. An den Portalecken zum Hof ragen kleine Geländekeile ins Bild. |
| [09_festungstor_hof.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/09_festungstor_hof.png) | Vom Hof: Portal mit Durchblick nach draußen, Straße „Auf der Festung" führt hinein. |
| [10_wallstrasse_6.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/10_wallstrasse_6.png) | Wallstraße 6 dreigeschossig mit Satteldach in normalen Proportionen. |
| [11_rathausturm.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/11_rathausturm.png) | Rathausturm neben dem Rathaus: Backsteinschaft, Wimperge, schlanker Schieferhelm, wie auf dem Referenzfoto. |
| [12](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/12_innen_buergerbuero_tag.png) · [13](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/13_innen_buergerbuero_nacht.png) | Bürgerbüro tags und nachts: Schalter, Fenster mit Blick nach draußen (nachts dunkel), Aushang am rechten Rand, Raumhöhe 4,7 m. |
| [14_tuer_buergerbuero.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/14_tuer_buergerbuero.png) | Rathaustür mit Steinrahmen, Verdachung und zwei Stufen; durch die Kreuzstockfenster ist der beleuchtete Raum zu sehen. |
| [15](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/15_innen_apotheke_tag.png) · [16](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/16_innen_apotheke_nacht.png) | Apotheke: Tresen, Regale zwischen den Fenstern, Durchblick nach draußen. Nachts ist die hintere rechte Ecke dunkler (4 Lampen auf 176 m²). |
| [17_tuer_apotheke.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/17_tuer_apotheke.png) | Geschlossene Tür im Steinrahmen, um 0,2 m zurückgesetzt, linke Hälfte im Schlagschatten der Laibung; durch die Fenster sind Regale zu sehen. |
| [18](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/18_innen_kaufhaus_tag.png) · [19](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/19_innen_kaufhaus_nacht.png) | Kaufhaus-Halle: Tresen, Mittelregale, Wandregal, Fensterreihe; nachts gleichmäßig von 12 Lampen beleuchtet. |
| [20_tuer_kaufhaus.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/20_tuer_kaufhaus.png) | Kaufhaustür mit Rahmen, unterbrochener Sockel, offenes Fenster mit Blick in die Halle. |
| [21_festungsmauer_bastion_held.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/21_festungsmauer_bastion_held.png) | Bastion Held von jenseits des Grabens: Backsteinmauer steigt senkrecht aus dem Wasser, Gesims und Abdeckung, begrünter Wall dahinter. |
| [22_festungsmauer_graben.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/22_festungsmauer_graben.png) | Mauerecke einer Bastion im Graben, Scharte in der Flanke, Mauer folgt der Wallhöhe. |
| [23_kehlmauer_drache.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/23_kehlmauer_drache.png) | Kehlmauer der Bastion Drache vom Hof: Zinnen, Scharten, Torbogen, zwei Rundtürme mit Kegeldach. |
| [24_sandsteintor.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/24_sandsteintor.png) | Sandsteintor aus dem Torvorhof: Sandsteinrahmen, Pilaster, Gebälk und Stufengiebel, dahinter das Tonnengewölbe; links und rechts noch kleine Rasenhügel am Hofrand. |

## Offen

- Remote-Sicherung erledigt: Das Repository liegt seit Sprint 13 auf GitHub (`remo01de/doemitz`, öffentlich).
- An der Festungsmauer fehlen noch Poternen und Zierformen des Sandsteintors; die Escarpenkrone folgt dem DGM und ist an Stellen mit niedrigem Wall nur 2,5 m hoch. Am Rand des Torvorhofs stehen kleine Rasenhügel.
- Kasemattengänge in den Bastionen sind nicht begehbar (Report `tunnels_not_built`).
- Bei den übrigen Gebäuden können vereinfachte Geländedreiecke am Hang weiterhin innerhalb des Grundrisses ansteigen. Das ist unsichtbar, solange die Gebäude geschlossen sind.
