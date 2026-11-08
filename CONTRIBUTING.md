# Contributing

Beiträge werden unter der [Apache License 2.0](LICENSE) angenommen.
Mit einem Beitrag bestätigst du, dass du die erforderlichen Rechte besitzt.

## Arbeitsweise

1. Branch unter `feature/` oder `bug/` anlegen.
2. Änderungen klein und fachlich nachvollziehbar halten.
3. Verhalten und relevante Fehlerfälle testen. Keine Tests schreiben, die nur die
   aktuelle Implementierungsstruktur spiegeln.
4. Manifest-Version erhöhen und Changelog um Features, Bugfixes, Breaking Changes
   und Security ergänzen. Leere Kategorien mit `- Keine.` kennzeichnen.
5. Pull Request nach `main`; alle Pflichtprüfungen müssen erfolgreich sein.

## Lokale Tests

Python 3.14.2 oder neuer und Node.js 24 verwenden:

```sh
python -m venv .venv
python -m pip install -r requirements-dev.txt -r requirements-test.txt
python -m pytest -q --cov=custom_components.eos_energiezentrale --cov-branch
node --test tests/panel.test.cjs
python -m bandit -r custom_components tools -ll
python -m pip_audit -r requirements-dev.txt -r requirements-test.txt --strict
python tools/release.py validate
```

VS Code nutzt weiterhin die Projekt-`.venv` und die zentrale `pytest.ini`.
Nach dem Architekturwechsel die vorhandene Umgebung mit Python 3.14 neu anlegen
oder die beiden Requirements-Dateien in eine kompatible Umgebung installieren.

## Architektur

`custom_components/eos_energiezentrale/energy` enthält die unabhängig von HA
modellierte Regelungslogik, Treiberverträge, EOS-/Influx-Clients und den Verlauf.
`adapter.py` verbindet synchrone Treiber aus einem Executor mit dem HA-Eventloop.
Der Coordinator serialisiert Polling, Steuerbefehle, Einstellungen und Stoppen.
Blockierende HTTP-, Datei- und SQLite-Zugriffe dürfen nicht in den Eventloop.

Gerätebefehle benötigen passende Domänen und Bestätigungen. Ausschalten und Fehler
müssen neue Regelbefehle verhindern; eine unbestätigte Rückgabe darf nicht als Erfolg
erscheinen. Neue Hardware erweitert die Registries und erhält fachliche Tests.

Die Oberfläche nutzt HA-WebSockets statt eigener Authentifizierung. Keine Tokens,
Passwörter oder Rohfehler mit privaten Daten in Frontend-Antworten, Logs oder Tests
mit echten Zugangsdaten aufnehmen. Sicherheitsprobleme nicht mit privaten
Messwerten in öffentlichen Issues veröffentlichen.

Übersetzungen: native HA-Texte in `translations`, Panel-Texte in `energy/i18n`.
Englisch bleibt der Rückfall. UI und Einstellungen müssen auf kleinen Bildschirmen
benutzbar bleiben.
