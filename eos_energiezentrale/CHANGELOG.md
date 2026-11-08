# Changelog

Die Release-Pipeline verwendet die Add-on-Version und den zugehörigen Eintrag in diesem Changelog. Version und Änderungen werden gemeinsam per Pull Request nach main übernommen. Ein GitHub-Release entsteht nach erfolgreichen Prüfungen und Container-Publish.

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
