# Arbeitsanweisungen für Agents

Diese Regeln gelten für das gesamte Repository und ergänzen `CONTRIBUTING.md`.
Ziel sind kleine, vollständige und überprüfbare Pull Requests nach `main`, auch
bei der Nachbearbeitung von Dependabot-Updates.

## Vor Beginn

- `CONTRIBUTING.md`, die betroffenen Dateien und `.github/workflows/ci.yml` lesen.
  Die CI ist die maßgebliche Quelle für Laufzeiten und Pflichtprüfungen.
- Aktuellen Branch, Arbeitsverzeichnis und Diff zur Zielbranch prüfen. Vorhandene
  Änderungen erhalten; keine fremden Änderungen zurücksetzen oder überschreiben.
- Bei einem vorhandenen Fix oder Dependabot-PR auf dessen Branch weiterarbeiten.
  Neue Arbeitsbranches unter `feature/`, `bug/` oder `bugfix/` anlegen.
- Den tatsächlichen Änderungsumfang ermitteln und die notwendige Arbeit bis zu
  einem prüfbaren Ergebnis ausführen. Nicht bei einer Empfehlung stehen bleiben.

## Vollständigkeit und Releases

Jeder zur Veröffentlichung bestimmte PR, einschließlich CI- und
Abhängigkeitsupdates, ergänzt `CHANGELOG.md`:

1. Nur den obersten Abschnitt `## New Version` pflegen, mit allen vier Kategorien
   `Features`, `Bugfixes`, `Breaking Changes` und `Security`; ohne Änderung
   `- Keine.` verwenden. Bestehende veröffentlichte Einträge erhalten.
2. Die Manifest-Version im Quellbranch bleibt `0.0.0`. Version und Datum werden
   ausschließlich von der CI im veröffentlichten Tag gesetzt. Keine manuellen
   Versionsbumps oder datierten Abschnitte für neue Änderungen anlegen.
3. Die CI berücksichtigt nur neue/geänderte Stichpunkte gegenüber dem letzten
   stabil veröffentlichten Quellstand: Breaking Changes erhöht Major, Features
   Minor, sonst Bugfixes/Security Patch. Die stabile Release-Historie verhindert
   Wiederholungen auch nach der Bereinigung des Entwurfs. Bereits veröffentlichte
   Stichpunkte entfernt die CI bei erfolgreichen Push-Läufen auf Arbeitsbranches
   durch einen Bot-Commit; diesen vor weiteren Änderungen mit `git pull --ff-only`
   übernehmen. Ein neuer Release braucht neue Einträge. Details stehen in `CI.md`.
4. Das tatsächliche Verhalten beschreiben. Bei Dependency-Updates Abhängigkeit,
   bisherige und neue Version bzw. Commit sowie den betroffenen Einsatz nennen.
   Ein normales Versionsupdate nicht ohne Beleg als behobene Sicherheitslücke
   darstellen. Dokumentation gehört ebenfalls zum Änderungsumfang.

Ein Push auf `feature/`, `bug/` oder `bugfix/` veröffentlicht nach erfolgreichen
Pflichtprüfungen eine Beta; ein Merge nach `main` ein stabiles HACS-Release.
Die Pipeline erzeugt einen Metadatencommit mit dem geprüften Quellcommit als
direktem Elterncommit. Zusätzlich bereinigt sie `New Version` auf Arbeitsbranches
nach erfolgreichen Tests, Sicherheits- und Integrationsprüfungen durch einen
Fast-Forward-Bot-Commit und startet für dessen HEAD die vollständigen Prüfungen
ohne weitere Veröffentlichung. `main` bleibt von Bot-Commits ausgenommen.
Die nummerierte Historie steht vollständig im Changelog des Release-Tags. Agents dürfen Tags und Releases
nicht als Ersatz für die Pipeline manuell erzeugen oder veröffentlichte Tags
verschieben.

## Dependabot-PRs nachbearbeiten

Dependabot aktualisiert die unterstützten Abhängigkeitsdateien anhand von
`.github/dependabot.yml`. Diese `AGENTS.md` ist eine Arbeitsanweisung für
Coding-Agents; sie bewirkt für sich allein keine zusätzlichen Dependabot-Schritte.
Die folgenden Aufgaben übernimmt der Agent, der einen Dependabot-PR fertigstellt.

- Den vollständigen Diff und die offiziellen Release Notes bzw. den Vergleich
  der alten und neuen Version lesen. Kompatibilität, geänderte APIs, Laufzeiten,
  Action-Eingaben, Ausgaben und erforderliche Berechtigungen prüfen.
- GitHub Actions weiterhin mit vollständigen Commit-SHAs pinnen. Versionskommentare
  müssen zur referenzierten Version passen; keine beweglichen Tags als Ersatz
  einführen. Weitere Verwendungen derselben Abhängigkeit im Repo prüfen und
  notwendige zusammenhängende Anpassungen einschließen.
- Bei Python-Updates beide Requirements-Dateien, die Home-Assistant-Testversion
  und die verwendete Python-Version berücksichtigen. Keine zusätzlichen
  Laufzeitabhängigkeiten oder Lockdatei-Formate ohne konkreten Bedarf einführen.
- Erforderliche Code-, Konfigurations-, Dokumentations- und Testanpassungen sowie
  den Abschnitt `New Version` im selben PR ergänzen. Unterschiedliche Updates nicht
  beiläufig bündeln.
- Ein Major-Update gezielt auf Migrationen prüfen. Bei Inkompatibilität Ursache
  und erforderliche Anpassungen dokumentieren; einen fehlschlagenden PR nicht
  als mergebereit bezeichnen.
- Nach eigenen Commits kann Dependabot automatische Rebases einstellen.
  `@dependabot recreate` kann eigene Änderungen überschreiben. Keine Skip-Marker
  verwenden, die das Überschreiben eigener Ergänzungen erlauben. Nach einem
  Rebase oder einer Neuerstellung Vollständigkeit und Prüfungen erneut bewerten.

Referenzen: [Dependabot-Konfiguration](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference),
[Umgang mit zusätzlichen Commits](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/manage-dependabot-prs).

## Architektur und Sicherheitsgrenzen

- Die Regelungslogik liegt in `custom_components/eos_energiezentrale/energy`.
  Der HA-Adapter führt synchrone Arbeit im Executor aus; Polling,
  Steuerbefehle, Einstellungen und Stoppen bleiben serialisiert. Kein
  blockierender HTTP-, Datei- oder SQLite-Zugriff im HA-Eventloop.
- Gerätebefehle brauchen Bestätigungen. Ausschalten und Fehler verhindern neue
  Regelbefehle; fehlende oder veraltete Messwerte dürfen nicht als gültige
  Regelgrundlage dienen. Eine unbestätigte Geräterückgabe bleibt sichtbar.
- Authentifizierung und Administratorprüfung über Home Assistant erhalten.
  Keine Zugangsdaten oder privaten Messwerte in Logs, Tests, PRs oder Reports.
  Die Schwärzung sensibler Inhalte in SARIF-Berichten erhalten.
- Pflichtprüfungen, Scanner und deren Fehlerauswertung nicht abschwächen, um
  einen grünen Status zu erreichen. Begrenzte Workflow-Berechtigungen und
  `persist-credentials: false` erhalten. Fremden PR-Code nicht mit privilegierten
  Tokens über `pull_request_target` ausführen.
- Native HA-Übersetzungen liegen in `translations`, Panel-Texte in `energy/i18n`.
  Deutsch und Englisch pflegen; Englisch bleibt der Rückfall.
- Fachliche Berechnungen, Statusbewertungen und Warnungen im Backend halten.
  Das Frontend übermittelt Eingaben und übernimmt Darstellung und Formatierung.
  Backend-Warnungen und -Fehler müssen unabhängig von Browserabrufen protokolliert
  werden; gemeinsame Kennungen für Anzeige, Log und Diagnosedaten verwenden.
  Unveränderte Probleme deduplizieren, Ursachenwechsel und Behebungen erfassen.
  Browserfehler bleiben im Browser und werden weder an das Backend gemeldet noch
  nach Verbindungsaufbau nachgeliefert. Plugin-Lesefehler, unvollständige Rückgaben
  und Konfigurationsfehler im Backend protokollieren. Siehe `LOGGING.md`.

## Prüfung vor Abschluss

Für die folgenden Befehle den Interpreter der Projektumgebung verwenden:
unter PowerShell z. B. `.\.venv\Scripts\python.exe` anstelle von `python`;
unter Linux/macOS `.venv/bin/python`. Derzeit sind Python ab 3.14.2 und Node.js 24
vorgesehen. Keine maschinenabhängigen absoluten Pfade ins Repository schreiben.

Release- und Metadatenprüfungen bei jedem PR ausführen:

```sh
python tools/validate_hacs_metadata.py
python tools/release.py validate --check-local-tag --commit "$(git rev-parse HEAD)"
git diff --check
```

Die vollständige HEAD-SHA mit `git rev-parse HEAD` ermitteln. Der lokale
Tag-Check kennt nur vorhandene lokale Tags; er ersetzt nicht die CI-Prüfung.

Bei Code-, Dependency- und Workflow-Änderungen die relevanten Prüfungen aus
`.github/workflows/ci.yml` ausführen, insbesondere:

```sh
python -m pip install -r requirements-dev.txt -r requirements-test.txt
python -m pytest -q --cov=custom_components.eos_energiezentrale --cov-branch --cov-report=term-missing
node --check custom_components/eos_energiezentrale/energy/web/accounting.js
node --check custom_components/eos_energiezentrale/energy/web/app.js
node --check custom_components/eos_energiezentrale/energy/web/panel.js
node --check custom_components/eos_energiezentrale/energy/web/status.js
node --test tests/*.test.cjs
python -m bandit -r custom_components tools -ll
python -m pip_audit -r requirements-dev.txt -r requirements-test.txt --strict
```

Neue Verhaltenstests bei fachlichen Änderungen und Regressionen ergänzen.
Für reine Dokumentations- oder Versionsänderungen keine künstlichen Tests bauen.
Die CI prüft zusätzlich Trivy, SARIF-Verarbeitung/-Upload, hassfest und HACS.
Nicht lokal ausführbare Prüfungen und fehlenden Netzwerkzugriff konkret benennen;
nie einen nicht ausgeführten Check als erfolgreich ausgeben.

## Übergabe und PR-Beschreibung

- Problem und resultierendes Verhalten, bei Updates alte/neue Abhängigkeit und
  Kompatibilitätsbewertung nennen. Changelog und berechneter Release-Typ müssen
  zum endgültigen Diff passen; die Versionsnummer vergibt die CI.
- Ausgeführte Prüfungen mit Ergebnis und verbleibende Einschränkungen angeben.
  Ein unbekannter oder fehlgeschlagener Check ist kein Erfolg.
- Vor dem Merge müssen `tests`, `security`, `integration`, `release_metadata`
  und die Sammelprüfung `required` für den aktuellen PR-Stand erfolgreich sein.
  Externe CI-Ergebnisse überprüfen, sofern Zugriff besteht.
- Keine sachfremden Änderungen, Secrets oder generierten Testberichte mitliefern.
  Mergen und Veröffentlichen nur im ausdrücklich beauftragten Rahmen.
