# Beiträge zur EOS Energiezentrale

Beiträge zu Hardwaretreibern, Bedienung, Übersetzungen und Fehlerkorrekturen sind willkommen. Bitte beschreibe bei größeren Änderungen zuerst das Problem und den geplanten Lösungsweg in einem Issue.

## Entwicklung einrichten

Verwende Python 3.13 oder 3.14. Installiere die Entwicklungswerkzeuge aus dem Repository-Hauptverzeichnis.

```sh
python -m venv .venv
python -m pip install -r requirements-dev.txt
```

Aktiviere vor der Installation die virtuelle Umgebung oder verwende deren Python-Interpreter. Die vorhandene VS-Code-Konfiguration verwendet pytest und die Umgebung unter `.venv`.

## Änderungen einreichen

1. Erstelle einen Branch unter `feature/` oder `bug/`.
2. Beschreibe das gewünschte Verhalten und die Auswirkungen auf vorhandene Geräte und Einstellungen.
3. Ergänze fachlich sinnvolle Tests für neue Anforderungen oder Fehlerkorrekturen.
4. Führe die Prüfungen aus und öffne einen Pull Request nach `main`.
5. Erhöhe vor einem Merge nach main die Add-on-Version in eos_energiezentrale/config.yaml und ergänze den passenden Versionseintrag im Changelog. Halte Haupt- und Add-on-Changelog identisch.

Der konfigurierte GitHub-Regelsatz für `main` verlangt Pull Requests und erfolgreiche Prüfungen. Er wird erst durch Aktivierung in den Repository-Einstellungen wirksam. Der Workflow ist in [CI.md](CI.md) beschrieben.

## Tests und Fehlerbehandlung

Führe die Prüfungen im Repository-Hauptverzeichnis aus.

```sh
python -m pytest -q
python -m pytest --cov=energy --cov-branch --cov-report=term-missing
python -m bandit -r eos_energiezentrale/energy tools -ll
python -m pip_audit -r requirements-dev.txt --strict
node --check eos_energiezentrale/energy/web/app.js
```

Teste Anforderungen über beobachtbares Verhalten. Beispiele sind ein Ladestopp am Ziel-SoC, das Warten auf frische Messwerte, eine bestätigte Ladepause vor dem Phasenwechsel oder die ausbleibende Freigabe bei einem API-Fehler. Prüfe auch Wiederholungen, Kommunikationsabbrüche und die Rückkehr in einen kontrollierten Zustand.

Nutze für externe Geräte und Dienste simulierte Antworten an deren Schnittstellen. Tests dürfen keine echten Wallbox-, Speicher- oder EOS-Konfigurationen verändern. Assertions sollen fachliche Ergebnisse und notwendige Gerätebefehle prüfen. Interne Variablennamen, eine bestimmte Zahl von Hilfsfunktionsaufrufen oder die aktuelle Quellcodeform sind keine eigenständigen Anforderungen.

## Hardwaretreiber und Übersetzungen

Weitere Geräte implementieren die Schnittstelle `BatteryDriver` oder `WallboxDriver` und werden in der passenden Treiberregistrierung eingetragen. Dokumentiere die Parameter, Einheiten, Vorzeichen und Bestätigungen des Geräts. Ergänze insbesondere Tests für fehlende Bestätigungen und sichere Phasenwechsel.

Sprachpakete liegen unter `eos_energiezentrale/energy/i18n/`. Verwende `en.json` als Vorlage, erhalte die Nachrichtenschlüssel und Platzhalter und ergänze den Sprachcode in der Sprachauswahl von `config.yaml`. Die Einrichtung ist in der [README](README.md#sprache-der-oberfläche) beschrieben.

## Fehler und Sicherheitsmeldungen

Gib bei Fehlerberichten App-Version, Hardwaretyp, erwartetes und beobachtetes Verhalten sowie relevante, bereinigte Meldungen an. Entferne Zugangsdaten und persönliche Informationen aus Logs und Konfigurationen. Sicherheitslücken können über „Report a vulnerability“ auf GitHub vertraulich gemeldet werden, sofern diese Funktion im Repository aktiviert ist.

## Rechte an Beiträgen

Sofern nicht ausdrücklich anders vereinbart, stellst du einen zur Aufnahme eingereichten Beitrag gemäß Abschnitt 5 der [Apache License 2.0](LICENSE) unter diese Lizenz. Du behältst deine Urheberrechte. Reiche nur Inhalte ein, die du unter diesen Bedingungen bereitstellen darfst. Erhalte vorhandene Lizenz- und Urheberhinweise und dokumentiere gegebenenfalls die Herkunft übernommener Drittinhalte.

## Changelog und Releases

Neue Versionseinträge enthalten die Abschnitte **Features**, **Bugfixes**, **Breaking Changes** und **Security**. Ein leerer Bereich erhält „- Keine.“. Für Breaking Changes dokumentierst du die Auswirkung und die erforderlichen Migrationsschritte.

Die Pipeline prüft Version, Changelog und vorhandene Tags bereits vor dem Merge. Auf main erzeugt sie nach erfolgreichem Container-Publish das zugehörige GitHub-Release. Details stehen in [CI.md](CI.md).
