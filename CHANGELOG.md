# Changelog

Die Release-Pipeline verwendet die Integrationsversion aus manifest.json und die
zugehörigen Änderungen. Releases entstehen nach erfolgreichen Prüfungen auf main.

## 0.2.0

### Features

- Installation als HACS-Custom-Integration mit geführter Einrichtung in Home Assistant.
- Native Sensoren, Schalter, Ziel-SoCs, Regelparameter und Abfahrtsplanung.
- Eigenes Seitenleisten-Panel mit vorhandener Stromflussgrafik und Detailseiten.
- Inbetriebnahme-Optionen nach EOS-Verbindung, Sensoren, Hardware, Grenzen und Verlauf gegliedert.
- Native HA-Sprachdateien und Diagnosen ohne Zugangsdaten oder Haushaltsverlauf.
- Tests gegen Home Assistant 2026.11 für Lebenszyklus, Dienste, Einstellungen und authentifizierte Oberfläche.

### Bugfixes

- Gerätebefehle und Zustandsbestätigungen verwenden direkt die lokale HA-Dienst- und Zustandsverwaltung.
- Entfallene Altregler-Prüfung: vorhandene frühere Helper oder Automationen blockieren die neue Regelung nicht.
- Polling, Einstellungsänderungen und Stoppen werden serialisiert; blockierende Arbeit läuft im Executor.
- Unbestätigte Gerätefreigaben bleiben sichtbar und erneut versuchbar.

### Breaking Changes

- Eigenständiges Add-on, Supervisor-Zugriff, Ingress-Webserver und Docker-Auslieferung entfallen.
- Home Assistant ab 2026.11.0 ist erforderlich; die Entwicklung benötigt Python ab 3.14.2.
- EOS selbst bleibt als separater Dienst bestehen.
- Add-on-Optionen im Integrationsdialog erneut eintragen; native Entitäten besitzen eigene Registry-IDs.
- Lokale Verlaufs- und Alltagsdateien liegen nun unter .storage/eos_energiezentrale/<config-entry-id>.

### Security

- Panelzugriff und Paneländerungen über authentifizierte HA-WebSockets, ausschließlich für Administratoren.
- Kein eigener HTTP-Port und keine Supervisor-/HA-Zugriffstokens im Browser oder in der Integration.
- Herkunfts- und Fensterprüfung für die Panel-Kommunikation; keine beliebigen Serviceaufrufe.
- Bandit, pip-audit, Trivy-Geheimnisscan, hassfest und HACS-Validierung in der Pipeline.

## 0.1.3

### Features

- Automatische GitHub-Releases nach erfolgreichem Container-Publish auf main.
- Versionsgebundene Release-Notizen mit Features, Bugfixes, Breaking Changes und Security.
- CI-Prüfungen für Feature- und Bugfix-Branches, Pull Requests nach main und main.
- Containerbau für amd64 und arm64 sowie versionierte Image-Tags.
- Importierbarer main-Regelsatz und Skript für die Aktivierung des Branchschutzes.
- Tägliche Dependabot-Prüfungen für Docker, GitHub Actions und Entwicklungsabhängigkeiten.
- Zusätzliche fachliche Fehler- und Schnittstellentests für HTTP-Antworten, Gerätebestätigungen, Geräterückgabe und Releases.
- Beitragsleitfaden und Apache License 2.0 einschließlich Urheberhinweisen. Private und kommerzielle Nutzung sind unter den Lizenzbedingungen erlaubt.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Bandit, pip-audit und Trivy prüfen Quellcode, Abhängigkeiten, Geheimnisse und Container in der CI.
- Nicht benötigtes pip einschließlich seiner gebündelten Abhängigkeiten aus dem Laufzeit-Image entfernt; die CI prüft weiterhin den vollständigen Container und dessen Laufzeitimporte.

## 0.1.2

### Features

- Fachliche Regressionstests für Ladeziele, Messwertalter, Phasenwechsel, Speicherfreigabe, Persistenz und Ingress-Grenzen.

### Bugfixes

- Die Regelung bleibt nach einer fehlgeschlagenen Geräterückgabe deaktiviert. Eine ausstehende Rückgabe kann erneut versucht werden.
- Vor dem NRGkick-Phasenwechsel werden zwei frische Nullleistungsmessungen nach dem Abschaltbefehl verlangt.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.1.1

### Features

- Sprachpakete für Deutsch und Englisch.
- Automatische Übernahme der Home-Assistant-Sprache mit Englisch als Rückfall.
- Sprachauswahl in der Add-on-Konfiguration.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.1.0

### Features

- Erste Energiezentrale mit animiertem Stromfluss und Detailseiten für PV, Netz, Haus, Speicher, Fahrzeug und Wärmepumpe.
- EOS-Planabruf, Leistungs- und SoC-Prognosen sowie Moduszeitleisten.
- Generische Speicher- und Wallbox-Schnittstellen mit Fronius- und NRGkick-Treibern.
- PV-Überschussregelung, Ladeziele, Phasenwahl und SoC-Schätzung.
- InfluxDB-Verlauf und lokaler Verlauf ab App-Start.
- Lesemodus, explizite Steuerungsübernahme und über Ingress erreichbare Oberfläche.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.
