# Projekt DÖMITZ – Living City

Technische Architektur · Entwicklungsplan · Sprint 1

Wir entwickeln eine maßstabsgetreue 3D-Stadtsimulation von Dömitz, mit stilisierter Grafik, lebendigen Einwohnern, Fahrzeugverkehr, Gebäuden und einem simulierten Stadtalltag.

Anders als bei GTA steht nicht die Kriminalität im Vordergrund, sondern das Leben in einer möglichst realistischen deutschen Kleinstadt.

Projektentscheidungen

Festgelegt

| Eigenschaft | Entscheidung                           |
| ----------- | -------------------------------------- |
| Projektname | Dömitz – Living City                   |
| Grafik      | Stilisiert, hochwertiger 3D-Look       |
| Maßstab     | 1:1, ein Spielmeter = ein realer Meter |
| Schauplatz  | Dömitz 19303, Mecklenburg-Vorpommern   |
| Spieltyp    | Open-World-Stadtsimulation             |
| Perspektive | Third Person                           |
| Spielmodus  | Singleplayer, später erweiterbar       |
| Plattform   | Windows                                |
| Entwicklung | KI-unterstützt, modular                |

## 1. Visuelle Zielrichtung

[A Colorful Stylized Town Set Up in Unreal Engine 5](https://images.openai.com/static-rsc-4/rtuLfJG4RiQzTBfhWzh1W4ekoupUYkOcbSdM0DbljvoH4wjDJ5bQENfsduPJLkXGrZ5dycuty6XZQR1QP19pUkaJIhPxXjZMllHpLBb_9neEEpz4ZSpJlT9s89wqYK8EKWFv_FHzRNgtgk4lMc1oa8haPbgaiu0-8IuxxOSbRv4?purpose=inline)

[Buy cheap Medieval Supermarket Shop Simulator PS5 key - lowest price | GG.deals](https://images.openai.com/static-rsc-4/cXSy5NUiA6HMKnkHbCrvQ8GXpSCUFcfqWU6LpOutWAVjyy1RmDfep0byBazu_JsNb2Fkt8lenaakzQpsOpFKelzNTjn1OsOES3g1tM07SeSyg6o_qUnT3F2_cnbe0VUjc9J2VcW-l-0b1CYaMbb5MwrPZbJSMqCRWDnx6yO1yIU?purpose=inline)

[Transport Fever 2: Console Edition - Deluxe Upgrade | Deku Deals](https://images.openai.com/static-rsc-4/jEas7GjUZfBJzvSxlRg82lfk29bVIa_vrlr9isNrvyNjvchNVFBMCAYZPBdd9pSWyj8B7iSsVRZdSooM6Q7OBiQW1U5ZDIFXOIu44bIPXaLImtjY_JzzKAWzcCe450FIZopk_M54StdSrjNZ_JJ0LW61zh5pjckJTmn0V6vK3As?purpose=inline)

[Europe Street | Fab](https://images.openai.com/static-rsc-4/xNeWbqX7pG1Mb97JdIwPnBV29As9Y5rCiNYRD4s64jMJj2mbNDb3_2YA-AO7Mdaql4tTm6T5c-MZeVsgS7jbkGE6dkI4-h8sSLhDczXGsVrWBlI50mq9HlIxvGUnoDNbR8C_jPnBeQ248amG-s6_diFW5An1fnbHDSI9IALM6NA?purpose=inline)

[A Colorful Stylized Town Set Up in Unreal Engine 5](https://images.openai.com/static-rsc-4/W35ibPtnUCW85lUSEhuKyusl1hoXY_oBAOB_aq6zv7uDF-89iLCJ5tN8wCW32zykz57WT3cCvFZZKaNPm2l6LIq6TZM59i0xxBVzBrTJTwWstzvPPR_wNQ4BYEEiYfL5KwUaFRgUYqQcmVQovmXt7G4KCntT74OgQLKfxZgCaTw?purpose=inline)

[Le seul village d'Auvergne avec 20 maisons à pans de bois des XVe-XVIe siècles](https://images.openai.com/static-rsc-4/epiEWX9RiHA-LOvqUxUb6Nh8Y1WgaVL8-kcEm-xj_AHn1OZ3niTE0SZHQEnK_qkqnX3GX-dOa5a-Q07BMnbhFNpW3YCbZvWQc2H3Pjo2Qkxcl9Vs2uLaml7D-EwNJbL8Xjl9e8vZIuABWRXvMiLXMBxBz7_bcqmY740HXtpw6vU?purpose=inline)

[It's Transport Tycoon For The 21st Century - Kotaku](https://images.openai.com/static-rsc-4/P-qEWEsCrC3yfHjBfIztFA52CHqotO-X_uVfVRfCSnbmfihH_Lae1a4Mvz-mPsUS-w463sw2MqHpcgsqvNCFohU3P9BXJfRz8_AsQ-5M7OadW1-nqmLJt8YiGLsTl9r2DwNKNsTXhMSn-hWM9nY-rU1JuYEhqD62RHJRH-VDcZU?purpose=inline)

[Stylized Environment Production in Unity](https://images.openai.com/static-rsc-4/HqeYZ7FNm1QIhf0FWwHJzA6V6SV0a6E2opEoRXmhs00EnN-7HcAXEuRABwodyIASKcIZmIqwZONiA4hAOBjvkC_NPNuVktP_BIkTe8dDnBIx9VNhcpa994QW67XhLOD3c8wLiuEPXGuGERIhno4Ew-mK2OHSR7lQRd2QfLJb-w0?purpose=inline)

[City Tales - Medieval Era on Steam](https://images.openai.com/static-rsc-4/rNofE7sUOWkpeAPRaQvKwntKlntSRIM4MUzuUrvgtNKGqauAdgFYqOfb6PpZ4E9ERFXPEGYHm9qzuGyZyl_20NGi_snHlagyy2NRsrPsxIRiXvtulMKXaAfVb9W9TtA6ZoIS2axE44u6k66T4mdZRuZ5QTrg3pAKoj7bTS_1LHM?purpose=inline)

[Counter-Strike's Italy Map Reimagined in Unreal Engine 5](https://images.openai.com/static-rsc-4/3ne9nDkTBweBsbRU7aCxOloRwCo2xnCwukSpOq_IzY8B9OvksHxwcGw7tySy7sNh6TorAFcy4zT77-ta6v5dzao0A5_NUKIbU5uXGYyXPwnsCJRB84hxoI-l-FW9ND5IicnovAF73OzTvD-_xx1sZmCkHBGLgkqSIHnF-q9G3wY?purpose=inline)

Die Grafik soll zwischen realistischer Architektur und einem stilisierten 3D-Spiel liegen. Die Proportionen der Stadt bleiben korrekt, während Oberflächen, Figuren und Farben etwas vereinfacht werden.

## 2. Architektur des Projekts

Engine: Unreal Engine 5

Ich würde Unreal Engine mit C++, Blueprints und einer Python-Pipeline für geografische Daten einsetzen.

Datenquellen

OpenStreetMap · GeoPortal MV · eigene Referenzfotos

Geodaten-Pipeline – Python

Bereinigung · Koordinaten · Straßen · Gebäude · Höhen

3D-Generierung – Blender / Unreal PCG

Gebäudemodelle · Straßen-Meshes · Vegetation

Unreal Engine – Laufzeit

Welt & Streaming

Charaktersteuerung

Verkehr & Fahrzeuge

NPCs & Tagesabläufe

Wirtschaft & Missionen

UI & Speichersystem

### Technische Module

| Modul           | Technologie                | Funktion                            |
| --------------- | -------------------------- | ----------------------------------- |
| World Core      | Unreal C++                 | Spielzeit, Zustand, globale Systeme |
| World Streaming | World Partition            | Stadtbereiche dynamisch laden       |
| City Generator  | Python + PCG               | Stadt aus Geodaten erzeugen         |
| Building System | Blender + PCG              | Gebäude automatisch platzieren      |
| Character       | C++ + Blueprints           | Spielerbewegung, Kamera             |
| Traffic         | C++ + Nav-Daten            | Verkehr und Verkehrsregeln          |
| Citizen AI      | State Machines / StateTree | Einwohner mit Tagesabläufen         |
| Economy         | C++ + Data Assets          | Arbeit, Geld, Einkauf               |
| Save System     | Unreal SaveGame            | Spielstände und Veränderungen       |
| UI              | Unreal UMG                 | Karte, Uhrzeit, Inventar            |

World Partition ist genau für die dynamische Verwaltung größerer Spielwelten vorgesehen. PCG unterstützt die prozedurale Erzeugung und Platzierung von Weltinhalten.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://dev.epicgames.com\&sz=32)

Epic Developer Community+1



Für die erste Version benötigen wir keinen eigenen Webserver und keine externe Datenbank. Die Simulation läuft lokal. SQLite oder eine API können wir später ergänzen, falls ein Stadt-Editor oder externe Verwaltungsfunktionen entstehen.

## 3. Maßstabsgetreuer Nachbau von Dömitz

Die Geodaten werden in ein lokales metrisches Koordinatensystem transformiert. Dadurch bleiben Straßenabstände, Gebäudegrundrisse und relative Positionen korrekt.

Geografische Grundlage

OpenStreetMap für Straßen und Gebäudegrundrisse, geeignete Höhen- und Katasterdaten aus dem [GeoPortal Mecklenburg-Vorpommern](https://www.geoportal-mv.de/portal/Geodatenviewer/Datenuebersicht?utm_source=chatgpt.com). Dort sind unter anderem Geländemodelle, Orthofotos und Gebäudekoordinaten aufgeführt. Die konkreten Nutzungsbedingungen prüfen wir pro Datensatz.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.geoportal-mv.de\&sz=32)

GeoPortal Mecklenburg-Vorpommern



Gebäude

Tatsächliche Grundrisse übernehmen. Fehlende Gebäudehöhen zunächst anhand gekennzeichneter Annahmen erzeugen. Markante Gebäude später manuell anhand von Referenzmaterial nachbauen.

Straßennetz

Originalverläufe übernehmen. Fahrbahnbreiten und Gehwege, wo keine belastbaren Daten existieren, zunächst parametrisch modellieren. Straßenkreuzungen müssen für die Fahrzeugsimulation verbunden sein.

Wichtig: Maßstab 1:1 bedeutet nicht automatisch eine millimetergenaue Kopie. Die Qualitätsstufen der Geodaten dokumentieren wir getrennt, damit angenommene Gebäudedetails nicht als vermessen gelten.

## 4. Zielarchitektur der Stadtsimulation

Jedes simulierte Objekt bekommt eine stabile ID, unabhängig davon, ob es gerade sichtbar ist.

Beispielsweise besitzt ein Einwohner eine Wohnung, einen Arbeitsplatz und einen Tagesablauf. Das System berechnet seinen Zustand auch dann vereinfacht weiter, wenn sein Stadtteil gerade nicht geladen ist.

| System     | Erstes Ausbaustadium          | Später                             |
| ---------- | ----------------------------- | ---------------------------------- |
| Einwohner  | Wenige NPCs auf festen Routen | Berufe, Beziehungen, Tagesabläufe  |
| Verkehr    | Einzelne Fahrzeuge            | Vorfahrt, Ampeln, Parken           |
| Gebäude    | Außenmodelle                  | Geschäfte, Wohnungen, Innenräume   |
| Zeit       | Tag-/Nachtwechsel             | Wochenkalender, Öffnungszeiten     |
| Wirtschaft | Einfacher Geldbestand         | Einkaufen, Arbeiten, Betriebe      |
| Stadtleben | Spaziergänger                 | Ereignisse und dynamische Aufgaben |

Die zentrale Architekturregel lautet: Simulationsdaten und 3D-Darstellung bleiben getrennt. So können später Hunderte Einwohner existieren, ohne dass jeder ständig als vollständiger 3D-Charakter berechnet werden muss.

## 5. Projektstruktur

Das Repository wird so aufgebaut, dass Codex einzelne Komponenten bearbeiten kann, ohne die gesamte Spielwelt verändern zu müssen.

```
doemitz-living-city/
├── AGENTS.md
├── README.md
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── GEO_DATA.md
│   └── SPRINT_01.md
├── data/
│   ├── raw/              # Original-Geodaten
│   ├── processed/        # Bereinigte Geodaten
│   └── manifests/        # Quellen und Lizenzen
├── tools/
│   ├── geo_import/       # OSM-Import
│   ├── geo_transform/    # Koordinaten
│   ├── mesh_generator/   # Straßen/Gebäude
│   └── validation/       # Geometrie-Tests
├── unreal/
│   └── DoemitzLivingCity/
│       ├── Source/
│       │   ├── World/
│       │   ├── Character/
│       │   ├── Simulation/
│       │   ├── Traffic/
│       │   └── Interaction/
│       ├── Content/
│       │   ├── Maps/
│       │   ├── Buildings/
│       │   ├── Roads/
│       │   ├── Characters/
│       │   └── UI/
│       └── Config/
├── tests/
└── scripts/
```

Große Rohdaten und generierte Assets werden nicht unkontrolliert in Git gespeichert. Für binäre Unreal-Assets verwenden wir Git LFS, für reproduzierbare Kartengenerierung einen dokumentierten Datenimport.

## 6. Sprint 1 – Die erste begehbare Stadt

Sprint 01

Planungsrahmen: 2 Wochen · ca. 30–50 Arbeitsstunden

Sprint-Ziel: Wir starten das Spiel und können durch einen ersten geografisch korrekt angelegten Ausschnitt von Dömitz laufen. Straßen und einfache Gebäude sind bereits vorhanden.

Noch keine NPCs, Fahrzeuge oder Missionen.

Sprint-Checkliste

0 / 6 abgeschlossen

Tag 1–2

Projekt und Engine einrichten

Unreal-C++-Projekt, Third-Person-Template, World Partition, Git LFS, Verzeichnisstruktur und AGENTS.md

Ergebnis: Projekt startet im Editor

Tag 3–4

Geodaten importieren

Kleinen Kernbereich von Dömitz aus OSM extrahieren; Straßen, Gebäude und Wasserflächen in GeoJSON speichern; Datenquellen dokumentieren

Ergebnis: Validierter, wiederholbarer Datenexport

Tag 5–6

Koordinaten und Terrain

Projiziertes metrisches Koordinatensystem, lokaler Ursprung, Höhenmodell falls verfügbar; andernfalls markierte flache Testlandschaft

Ergebnis: Maßstabsgetreue 3D-Grundfläche

Tag 7–8

Straßen und Gebäude generieren

Straßen und Gebäudeflächen als Meshes erzeugen, Kreuzungen bereinigen, Platzhalterhöhen und stilisierte Materialien zuweisen

Ergebnis: Erkennbare Stadtszene

Tag 9

Spieler und Kamera

Third-Person-Charakter, Bewegung, Sprinten, Kollisionen und Kamerasteuerung testen

Ergebnis: Stadt zu Fuß erkundbar

Tag 10

Tests und Demo-Build

Maßstab kontrollieren, Import wiederholen, Performance messen, Windows-Build und technische Dokumentation

Ergebnis: Erster reproduzierbarer Prototyp

&#x20;Checkliste kopieren

## 7. Technische Abnahmekriterien

Sprint 1 ist erst abgeschlossen, wenn:

- Die ausgewählten Straßenverläufe und Gebäudegrundrisse in korrekter relativer Lage importiert werden.
- Ein bekannter Referenzabstand im Spiel höchstens 2 % von der Geodatenmessung abweicht.
- Ein Spieler durch die erzeugte Stadt laufen kann, ohne durch Gebäude oder den Boden zu fallen.
- Der Import mit denselben Quelldaten reproduzierbar ist, ohne manuelle Platzierung aller Gebäude.
- Auf dem festgelegten Test-PC möglichst stabile 60 FPS bei 1080p erreicht werden; die Hardware wird im Sprint dokumentiert.
- Ein Windows-Testbuild gestartet werden kann.

Dabei bleiben geometrische Genauigkeit, Grafikqualität und Simulationsfunktionen bewusst getrennte Ziele.

## 8. KI-Unterstützung und Entwicklungsregeln

Codex erhält klare Aufgaben über `AGENTS.md`:

- C++ und Blueprints: Spiellogik, nur C++ für komplexe oder wiederverwendbare Kernsysteme.

- Python: Geodaten, Validierung, Asset-Erzeugung und Editor-Automatisierung. Python wird nicht als Gameplay-Laufzeit verwendet.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://dev.epicgames.com\&sz=32)

  Epic Developer Community

- Keine hartcodierten Gebäudekoordinaten: Orte stammen aus Daten oder versionierten Konfigurationen.

- Keine ungeprüften Assets: Quellen und Lizenzstatus müssen dokumentiert sein, insbesondere für OpenStreetMap-Derivate.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://www.openstreetmap.org\&sz=32)

  OpenStreetMap

- Jeder Sprint liefert ein startbares Ergebnis.

### Was wir nach Sprint 1 machen

Sprint 2 beschäftigt sich mit der Straßenqualität, begehbaren Gehwegen und einem ersten Fahrzeug. Sprint 3 führt Einwohner mit einfachen Tagesabläufen ein. Ab dann wird aus dem 3D-Nachbau schrittweise eine lebendige Stadtsimulation.

Meine Empfehlung: Nicht zuerst die gesamte Stadt generieren, sondern mit einem kleineren Kernbereich um die Altstadt beginnen. Die Geodaten-Pipeline wird trotzdem von Anfang an so ausgelegt, dass sie später ganz Dömitz abbilden kann.

Als nächster konkreter Entwicklungsschritt steht ein vollständiges, versioniertes Projektpaket mit `PRD.md`, `ARCHITECTURE.md`, `AGENTS.md` und den ersten Python-Importscripten an.