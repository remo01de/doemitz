# Unreal-Projekt starten

Vorgesehener Projektpfad ist `unreal/DoemitzLivingCity/DoemitzLivingCity.uproject`. Der Editor ist auf dem Entwicklungsrechner bisher nicht nachgewiesen. Das C++-Projekt und die Map entstehen im installierten UE5-Editor.

1. Unreal Engine 5 mit der zur gewählten Engine-Version passenden Visual-Studio-C++-Toolchain bereitstellen. Die verwendete Engine-Version beim Anlegen des Projekts festhalten. [Epic – Visual Studio einrichten](https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine)
2. Im Projektbrowser **Games → Third Person** wählen und ein C++-Projekt namens `DoemitzLivingCity` mit dem Ordner `unreal/` als Speicherort erstellen. Im Vorlagenlevel Bewegung und Kamera mit **Play** prüfen. [Epic – Third-Person-Vorlage](https://dev.epicgames.com/documentation/en-us/unreal-engine/third-person-template-in-unreal-engine)
3. Das Stadtlevel als `/Game/Maps/DoemitzAltstadt` anlegen. World Partition und Streaming in den World Settings prüfen. Das Level nach der Integration als Editor Startup Map und Game Default Map einstellen. [Epic – World Partition](https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition-in-unreal-engine)
4. Die Mesh-Generierung an `data/processed/doemitz-altstadt/scene.json` anbinden. Lokale Meter beim Import einmalig in UE-Zentimeter konvertieren, die Achsen gemäß Architektur abbilden und die Kontrollstrecke im Level messen.

Die LFS-Regeln für `.uasset`, `.umap`, `.ubulk` und `.uexp` gelten bereits im Git-Repository.
