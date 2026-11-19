# Dömitz – Living City

Eine stilisierte 3D-Stadtsimulation für Windows im Maßstab 1:1. Sprint 1 beginnt mit einem Ausschnitt der Dömitzer Altstadt einschließlich Festung und Elbufer.

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

Das Git-Repository und der Geodatenimport sind eingerichtet. Für das UE5-Projekt ist der Start mit der C++-Vorlage Third Person vorgesehen. [Unreal-Einrichtung](unreal/README.md)

- [Produktanforderungen](docs/PRD.md)
- [Technische Architektur](docs/ARCHITECTURE.md)
- [Datenquellen und Exportvertrag](docs/GEO_DATA.md)
- [Sprint 1 und Abnahme](docs/SPRINT_01.md)
