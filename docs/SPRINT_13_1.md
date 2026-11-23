# Sprint 13.1 · Kollision der Stadtmöbel und Festungstor nach Fotos

Stand: Umgesetzt und geprüft (Nachbesserung zu Sprint 13).

## Befund

Rückmeldung des PO nach Sprint 13:

- Die Spielfigur läuft durch Laternen, Bänke und Bäume.
- Dazu kamen Fotos von Festungsmauer, Bastion und Festungseingang. Die Fotos stammen von Michael Schletze und Albert Speelman sowie aus weiteren Quellen. Sie dienen nur als Sichtvorlage und liegen nicht im Repository.

Ursache der fehlenden Kollision: Die Stadtmöbel und Bäume sind HISM-Instanzen (`ADoemitzInstancedPropActor`). Die Komponente stand auf `NoCollision`, und die Prototyp-Meshes hatten keine Kollisionskörper.

Vergleich der Torpartie mit den Fotos:

| Bauteil | Sprint 13 | Foto |
| --- | --- | --- |
| Torbau an der Zugbrücke | Rechteckige Öffnung, Satteldach mit Giebel | Rundbogen zwischen zwei Pfeilern, Ochsenaugen, helle Steinfelder, geschweiftes Attikagesims ohne Dach, Zugbrückenbalken mit Ketten |
| Mauer beiderseits des Torbaus | Escarpe mit Krone nach DGM, schräg ansteigend | Niedrige, waagerechte Mauer mit kleinen Schießscharten auf einem Sandsteinsockel |
| Brücke über den Graben | Durchgehende Brüstungswände | Holzbohlen, offenes Holzgeländer, Holzböcke im Graben |
| Sandsteintor | Rechteckiger Rahmen mit Stufengiebel, 23° schräg zur Tormauer | Rundbogen mit Bossenquadern und Schlussstein, Pilaster mit Diamantquadern, Gebälk mit Inschrifttafel, Attika mit zwei Wappen, Dreiecksgiebel mit Büste, Nebenpforte mit eigenem Giebel; bündig in der Tormauer |
| Torvorhof | Rasen, am Nordschenkel der Tormauer ein Hang bis 2,5 m über Hofniveau, schwarzes Loch unter dem Mauerfuß | Ebener, gepflasterter Hof |

## Ergebnisse

| Bereich | Ergebnis |
| --- | --- |
| Kollision | Laternen, Bänke, Poller, Pflanzkübel und Baumstämme blockieren die Spielfigur. Insgesamt sind es 618 Instanzen. `doemitz_prop_meshes.py` legt zu jedem Prototyp einfache Kollisionskörper an (Kapseln für Mast, Poller, Kübel und Stamm, eine Box für die Bank). `ADoemitzInstancedPropActor::SetMeshCollisionShapes` schreibt sie in die BodySetup des Meshes (`CTF_UseSimpleAsComplex`). `SetBlocksMovement` schaltet die HISM-Komponente auf QueryOnly und blockiert Pawns. Visibility- und Camera-Kanal werden ignoriert, damit Bodentraces, Interaktion und Kamera-Boom unverändert bleiben. Baumkronen, Büsche und die Laternengläser bleiben durchlässig. |
| Torbau | Neu in `fortress.py` als `_add_gatehouse`: Rundbogen 3,3 × 4,1 m, Pfeiler 1,45 m mit Ochsenaugen und hellen Steinfeldern, gemauerter Bogenring, Schlussstein und Kämpfer. Darüber ein geschweiftes Attikagesims 5,0–5,7 m über der Brücke mit Steinband und Abdeckplatte, ohne Dach. Dazu ein Sandsteinsockel bis zum Grabenboden und zwei Zugbrückenbalken mit Ketten. Die Maße sind als `assumed_sprint13_1_gatehouse` gekennzeichnet. |
| Schartenmauer am Torvorhof | Der Escarpenabschnitt vor dem Torvorhof ist 20,6 m lang (Bereich des Rings, den die OSM-Tormauer `osm:way:416256360` abschneidet). Er ist jetzt eine waagerechte Mauer 2,3 m über Brückenhöhe mit Innenseite, flacher Steinabdeckung und 8 Schießscharten. Der Sandsteinsockel reicht 1,3 m über das Grabenwasser und steht nur hier (`stone_plinth_scope: forecourt`). Die übrige Escarpe ist wie auf den Fotos Backstein bis zum Grabenboden. An beiden Enden schließt die hohe Escarpe mit einer Stirnfläche an. |
| Holzbrücken | Alle drei Holzbrücken (Zugbrücke mit Grabensteg, NW-Steg, Fläutendörper Steg) haben Querbohlen und ein offenes Geländer mit Pfosten alle 1,25 m, Handlauf und Mittelholm. Alle 5 m steht ein Holzbock mit Pfosten, Holm und Strebe bis zum Graben- oder Flussboden. Report-Feld `railing: timber_posts_rails`. Die Steinbrücken behalten ihre Brüstungen. |
| Sandsteintor | Neu als `_add_sandstone_gate` in `bridges.py` mit allen Bauteilen aus der Vergleichstabelle. Die Fassade liegt jetzt in der Flucht der Tormauer: Das letzte Profil des Torwegs ist um 22,9° in die Mauerlinie gedreht (Report `facades.exit`). Die Tormauer endet 0,3 m im Portalblock, statt einen Rasenstreifen neben dem Portal frei zu lassen. |
| Torwegportale | Beide Enden des Torwegs und das NW-Steg-Portal haben jetzt eine Rundbogenöffnung passend zum Tonnengewölbe (10 statt 6 Segmente) statt eines rechteckigen Sturzes. Vor und unter jedem Portalblock wird das Gelände auf Bodenhöhe abgesenkt. Damit verschwinden die Geländekeile an den Ecken des Hofportals. |
| Torvorhof | Die ebene Hoffläche kommt jetzt aus `build_fortress_wall` und liegt 10 cm unter der Brückenfahrbahn. Die Stützmauer reicht auf der Hofseite bis zum Hofboden und ist dort bis zu 8,8 m hoch. Der Hof ist gepflastert (`Paving`). Die Rasenhügel und das Loch unter dem Mauerfuß sind weg. |

Neue Meshes: `FortressSandstone` mit Kollision und `FortressSteel` (Zugbrückenbalken, ohne Kollision). Farben sind lineare Werte; Sandstein ist ein warmes Grau-Ocker, Tür und Holz sind dunkler als zuvor.

## Prüfungen

- Python: `python -m unittest discover -s tests`, 65 Tests in 580 s, alle bestanden. Neu ist `tests/test_sprint13_1.py` mit 6 Tests: Kollisionskörper der Stadtmöbel, durchlässige Büsche, Torbau ohne Dach, Schartenmauer, Holzgeländer, Sandsteintor in der Mauerflucht.
- Offline-Pipeline: `python -m tools.mesh_generator`, 186 Meshes, 350.349 Dreiecke. Gelände 152.691 von 155.000 Dreiecken, maximaler Fehler 4,95 cm.
- C++-Editor-Build (`DoemitzLivingCityEditor Win64 Development`): erfolgreich.
- Import (`scripts/Import-Altstadt.ps1`): `DOEMITZ_IMPORT_OK`, Brücken-, Gelände-, Dach- und Wandkollision bestanden. `DOEMITZ_HISM_IMPORT_OK: 11 HISM actors, 855 instances, 618 blocking`.
- PIE (`scripts/Verify-All.ps1`): `DOEMITZ_VERIFY_ALL_OK: 20/20 PIE checks passed`. Neu ist `VerifyPropCollision.py`: Die Spielfigur läuft gerade auf eine freistehende Laterne, Bank und einen Baum zu und bleibt jeweils am Kollisionsradius stehen (51 / 63 / 63 cm, erwartet 51 / 62 / 63 cm). Eine Visibility-Spur durch einen Baumstamm trifft den Stamm nicht. `VerifyFortressGate.py` läuft weiter über die Holzbrücke durch Torbau, Torvorhof und Torweg in den Hof.
- Windows-Build (`scripts/Build-Windows.ps1 -ArchiveDirectory …\unreal\DoemitzLivingCity\Saved\Builds\Win64Sprint13` im Hauptprojekt): `BUILD SUCCESSFUL`, das Paket dort ist aktualisiert.
- Benchmark (`scripts/Run-Benchmark.ps1 -Profile DoemitzLow`, 1920×1080, 90 s, gepackter Build, Ergebnisse unter `Saved/Benchmarks/Sprint13_1/`):

  | Lauf | FPS (Mittel) | Frametime p50 / p95 / p99 | GPU / Draw |
  | --- | --- | --- | --- |
  | 1 | 49,67 | 19,50 / 24,68 / 33,35 ms | 20,1 / 15,8 ms |
  | 2 | 48,05 | 19,99 / 25,84 / 45,03 ms | 20,8 / 16,4 ms |
  | 3 | 47,04 | – | 21,3 / 16,7 ms |

  Die Werte liegen unter den 72,5 FPS vom Vortag. Ein A/B-Vergleich am selben Tag mit dem ungekochten Spiel (`UnrealEditor -game`, 45 s, gleiche Strecke) zeigt, dass das nicht an den Änderungen liegt: Der Stand `42beeab` vor Sprint 13.1 erreicht 49,5 / 49,9 FPS, der neue Stand 49,7 / 46,0 FPS. Die Kollision der Requisiten allein kostet in diesem Vergleich 2 bis 4 FPS (42,5 / 42,8 FPS mit, 45,1 / 46,9 FPS ohne). Das Ziel von mindestens 15 FPS ist deutlich erfüllt.

## Sichtprüfung

Aufnahmen mit `CaptureSprint13Screenshots.py` unter `unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/`:

| Bild | Was zu sehen ist |
| --- | --- |
| [25_torbau_bruecke.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/25_torbau_bruecke.png) | Von der Holzbrücke: Torbau mit Rundbogen, Ochsenaugen, Steinfeldern und geschweiftem Gesims, links und rechts die Schartenmauern, durch den Bogen das Sandsteintor. |
| [07_festungstor_aussen.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/07_festungstor_aussen.png) | Nah am Torbau: Zugbrückenbalken mit Ketten, Holzgeländer, gepflasterter Torvorhof. |
| [26_torvorhof_graben.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/26_torvorhof_graben.png) | Vom Graben aus: Torbau und Schartenmauern auf dem niedrigen Sandsteinsockel, dahinter die hohen Escarpen von Kurtine und Bastion. |
| [24_sandsteintor.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/24_sandsteintor.png) | Aus dem Torvorhof: Sandsteintor mit Bossenbogen, Pilastern, Gebälk, Wappenattika, Voluten, Giebel und Büste, rechts die Nebenpforte. Bündig in der Backstein-Tormauer, ohne Rasenkeil. |
| [09_festungstor_hof.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/09_festungstor_hof.png) | Hofportal mit Rundbogen, ohne Geländekeile vor der Portalwand. |
| [06_nw_steg_tunnelportal.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/06_nw_steg_tunnelportal.png) | NW-Steg mit Holzgeländer und Holzböcken, Portal mit Rundbogen. |
| [22_festungsmauer_graben.png](../unreal/DoemitzLivingCity/Saved/Screenshots/Sprint13/22_festungsmauer_graben.png) | Bastion Held: Backstein bis zum Wasser ohne grauen Sockel, links der Grabensteg auf Holzböcken. |

## Offen

- Der Festungsgraben bleibt nach Entscheidung des PO eine Wasserfläche: Der Wasserstand hängt stark von der Witterung ab, der trockene Graben auf den Fotos ist ein Momentzustand.
- Die Bastionsflanken haben auf den Fotos eine gemauerte Brustwehr mit Pfeiler am Übergang zur Kurtine; das fehlt noch.
- Zierformen am Sandsteintor (Kannelur, Löwenköpfe, Wappenrelief) sind nur als Blöcke angedeutet.
- Büsche bleiben absichtlich durchlässig.
