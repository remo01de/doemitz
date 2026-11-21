# Altstadt im Unreal Editor

Öffne [DoemitzLivingCity.uproject](DoemitzLivingCity/DoemitzLivingCity.uproject) in Unreal Engine 5.8.4. Die Startkarte ist `/Game/Maps/DoemitzAltstadt`. **Play** startet die Figur an der Goethestraße. **WASD** bewegt die Figur, die Maus steuert die Kamera und die **Leertaste** löst den Sprung aus. Halte die **linke Umschalttaste** zum Sprinten.

Der Figuren-Blueprint aus der Third-Person-Vorlage erbt von `ADoemitzCharacter`. Die C++-Klasse setzt die Sprintgeschwindigkeit und stellt das zuvor eingestellte Gehtempo beim Loslassen wieder her. Der Blueprint konfiguriert die Aktion `IA_Sprint`, und `IMC_Default` ordnet ihr die linke Umschalttaste zu. Kamera, Mannequin und Animationen stammen aus der Vorlage. [Epic – Third-Person-Vorlage](https://dev.epicgames.com/documentation/en-us/unreal-engine/third-person-template-in-unreal-engine)

## Windows-Testbuild erstellen

Auf dem Testrechner verwendet Unreal Build Tool Visual Studio Build Tools 2026 mit MSVC 14.50.35740, Windows SDK 10.0.26100.0 und .NET Framework SDK 4.8. [Epic – Windows-C++-Toolchain](https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine)

Aus dem Repository-Stammordner ausführen.

```powershell
.\scripts\Build-Windows.ps1
```

Für eine andere Engine-Installation `-EngineRoot` angeben. Das Skript erstellt ein Win64-Development-Paket der Altstadt. Die startbare `DoemitzLivingCity.exe` liegt standardmäßig unter `unreal/DoemitzLivingCity/Saved/Builds/Win64Development/`. `-ArchiveDirectory` legt ein separates Ausgabeziel fest.

## Karte aus den Geodaten neu erzeugen

Im Repository die [Geodaten erzeugen](../README.md#geodaten-unter-windows-erzeugen). Anschließend aus dem Projektordner ausführen:

```powershell
.\scripts\Import-Altstadt.ps1
```

Für eine andere Engine-Installation `-EngineRoot` angeben. `-PythonExe` wählt bei Bedarf eine Python-Installation mit den Abhängigkeiten aus `requirements.txt` aus. Das Skript verarbeitet den lokalen Szenenexport und speichert die Meshes, Materialien und World-Partition-Actors im Unreal-Projekt. Nach einem Import die Karte im laufenden Editor neu öffnen, damit die gespeicherten Actors geladen werden. Der Importbericht im Editor-Log enthält die Referenzmessung und die Kollisionsprüfung.

Die binären Unreal-Assets einschließlich der externen Level-Actors liegen in Git LFS. Python und Geometry Script laufen bei der Kartenerzeugung im Editor. [Epic – World Partition](https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition-in-unreal-engine)
