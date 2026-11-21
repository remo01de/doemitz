# Dömitz – Living City

Eine stilisierte 3D-Stadtsimulation für Windows im Maßstab 1:1. Der erste Ausschnitt umfasst die Dömitzer Altstadt einschließlich Festung und Elbufer.

## Geodaten unter Windows erzeugen

PowerShell im Projektordner öffnen. Benötigt werden Python 3.12 und für den ersten Datenabruf eine Internetverbindung.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.geo_import fetch
.\.venv\Scripts\python.exe -m tools.geo_import build
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

`fetch` legt einen Snapshot unter `data/raw/doemitz-altstadt/` an. Falls dieser bereits vorliegt, direkt mit `build` fortfahren. Der Build arbeitet offline und schreibt nach `data/processed/doemitz-altstadt/`.

| Datei | Inhalt |
| --- | --- |
| `roads.geojson` | Straßen- und Wegeachsen in WGS84 |
| `buildings.geojson` | Gebäudegrundrisse in WGS84 |
| `water.geojson` | Wasserflächen in WGS84 |
| `scene.json` | Kartengeometrie in lokalen Metern und Umriss der flachen Testlandschaft |
| `import-report.json` | Quellprüfsummen, Featurezahlen, Geometriehinweise und Maßstabsprüfung |

Kartendaten © OpenStreetMap contributors, ODbL 1.0. [OpenStreetMap – Urheberrecht und Lizenz](https://www.openstreetmap.org/copyright)

## Projektstand

Das Unreal-Projekt öffnet die Altstadt-Karte als Startlevel. Im Editor startet **Play** die Third-Person-Figur an der Goethestraße. Dort lassen sich in Sprint 2 die ersten erhöhten Gehwege begehen. Die Demo verwendet einfache Gebäudekörper und eine flache Testgrundfläche. [Unreal-Projekt](unreal/DoemitzLivingCity/DoemitzLivingCity.uproject) · [Unreal-Einrichtung und Kartenimport](unreal/README.md)

- [Produktanforderungen](docs/PRD.md)
- [Technische Architektur](docs/ARCHITECTURE.md)
- [Datenquellen und Exportvertrag](docs/GEO_DATA.md)
- [Sprint 1 und Abnahme](docs/SPRINT_01.md)
- [Sprint 2 – Straßen, Gehwege und erstes Fahrzeug](docs/SPRINT_02.md)
