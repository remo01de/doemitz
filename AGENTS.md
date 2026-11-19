# Dömitz – Living City

- Lies für Änderungen die relevanten Abschnitte in `docs/PRD.md`, `docs/ARCHITECTURE.md` und `docs/SPRINT_01.md`. `Auftrag.md` enthält den ursprünglichen Projektauftrag.
- Verwende Unreal Engine 5 für die Windows-Spielversion. Verwende C++ für wiederverwendbare Spielsysteme und Blueprints für Konfiguration und Präsentation. Python bleibt ein Entwicklungs- und Editorwerkzeug.
- Halte Simulationszustand und 3D-Darstellung getrennt. Verwende stabile IDs. Gebäudekoordinaten stammen aus Geodaten oder versionierter Konfiguration.
- Verwende im Austauschformat lokale Meter und in Unreal Zentimeter. Halte die Achsenabbildung in der Importstrecke zentral. Kennzeichne angenommene Höhen, Breiten und die flache Testlandschaft an der Quelle.
- Dokumentiere Quelle und Lizenz von Geodaten und Assets. Bewahre Rohdaten und reproduzierbare Exporte lokal in `data/raw/` und `data/processed/` auf. Versioniere Konfiguration und kleine Manifeste in `data/manifests/`. Nutze Git LFS für binäre Unreal-Assets.
- Prüfe Geodatenänderungen mit dem Offline-Build und `python -m unittest discover -s tests`. Vermerke bei Änderungen am Spiel, welche Editor-, Spiel- und Build-Prüfungen du durchgeführt hast.
