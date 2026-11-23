# Dömitz – Living City

Eine stilisierte 3D-Stadtsimulation für Windows im Maßstab 1:1. Der erste Ausschnitt umfasst die Dömitzer Altstadt einschließlich Festung und Elbufer.

## Geodaten unter Windows erzeugen

PowerShell im Projektordner öffnen. Benötigt werden Python 3.12 und für den ersten Datenabruf eine Internetverbindung.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.geo_import fetch
.\.venv\Scripts\python.exe -m tools.geo_import fetch-dgm
.\.venv\Scripts\python.exe -m tools.geo_import fetch-lod2
.\.venv\Scripts\python.exe -m tools.geo_import build
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

`fetch` und `fetch-dgm` legen die Rohdaten unter `data/raw/doemitz-altstadt/` an (OSM-Snapshot und DGM1-Kacheln). Falls diese bereits vorliegen, direkt mit `build` fortfahren (optional `--terrain flat` für den flachen Testmodus). Der Build arbeitet offline und schreibt nach `data/processed/doemitz-altstadt/`.

| Datei | Inhalt |
| --- | --- |
| `roads.geojson` | Straßen- und Wegeachsen in WGS84 |
| `buildings.geojson` | Gebäudegrundrisse in WGS84 |
| `water.geojson` | Wasserflächen in WGS84 |
| `pois.geojson` | Points of Interest (`shop`, `amenity`, `office`, `tourism`) in WGS84 |
| `terrain-grid.bin` | Zugeschnittenes 1-m-Höhenraster aus dem amtlichen DGM1 in lokalen Metern (`NHN − 13,001 m`) |
| `scene.json` | Kartengeometrie in lokalen Metern und DGM1-Geländemetadaten (`terrain.kind = "dgm1"`) |
| `import-report.json` | Quellprüfsummen (OSM + DGM1), Featurezahlen, Geometriehinweise und Maßstabsprüfung |

Kartendaten © OpenStreetMap contributors, ODbL 1.0 ([OpenStreetMap – Urheberrecht und Lizenz](https://www.openstreetmap.org/copyright)) · Höhen- & 3D-Gebäudedaten © GeoBasis-DE/M-V 2025/2026, CC BY 4.0 ([LAiV M-V](https://www.laiv-mv.de/Geoinformation/Geobasisdaten/Gelaendemodelle/)).

## Projektstand

Das Unreal-Projekt öffnet die Altstadt-Karte als Startlevel. Im Editor startet **Play** die Third-Person-Figur an der Goethestraße auf realem DGM1-Gelände mit 64-m-Geländekacheln, drapierten Straßen und Gehwegen, Hang-Gebäudesockeln, 30 Einwohnern, vernetztem Straßenverkehr, Stadtkarte mit Schummerung und SaveGame v6. [Unreal-Projekt](unreal/DoemitzLivingCity/DoemitzLivingCity.uproject) · [Unreal-Einrichtung und Kartenimport](unreal/README.md)

- [Produktanforderungen](docs/PRD.md)
- [Technische Architektur](docs/ARCHITECTURE.md)
- [Datenquellen und Exportvertrag](docs/GEO_DATA.md)
- [Sprint 1 und Abnahme](docs/SPRINT_01.md)
- [Sprint 2 – Straßen, Gehwege und erstes Fahrzeug](docs/SPRINT_02.md)
- [Sprint 3 – Erste Einwohner und einfache Tagesabläufe](docs/SPRINT_03.md)
- [Sprint 4 – Tag-/Nachtwechsel und UMG-Uhrzeit-/Status-HUD](docs/SPRINT_04.md)
- [Sprint 5 – SaveGame-System und Zeitsteuerung](docs/SPRINT_05.md)
- [Sprint 6 – Stilisierte Altstadt-Architektur, Straßenlaternen und Vegetation](docs/SPRINT_06.md)
- [Sprint 7 – Performance-Basis und vernetzter Straßenverkehr](docs/SPRINT_07.md)
- [Sprint 8 – Wochenkalender, mehr Einwohner und Fußgängerüberwege](docs/SPRINT_08.md)
- [Sprint 9 – Wirtschaft und Interaktion an Gebäudeeingängen](docs/SPRINT_09.md)
- [Sprint 10 – Stadtkarte, erste Aufgaben, Vorfahrt und Parken](docs/SPRINT_10.md)
- [Sprint 11 – Reales Gelände aus DGM1](docs/SPRINT_11.md)
- [Sprint 11.1 – Brücken auf eigener Höhe](docs/SPRINT_11_1.md)
- [Sprint 12 – Reale Gebäudehöhen und markante Bauwerke](docs/SPRINT_12.md)
- [Sprint 13 – Festungstor, Sichtfehler und erste Innenräume](docs/SPRINT_13.md)
- [Sprint 13.1 – Kollision der Stadtmöbel und Festungstor nach Fotos](docs/SPRINT_13_1.md)
- [Sprint 14 – Stadtgebiet bis Hafen und Schleuse (Plan)](docs/SPRINT_14.md)
