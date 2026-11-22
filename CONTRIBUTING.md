# Contributing

Beiträge werden unter der [Apache License 2.0](LICENSE) angenommen.
Mit einem Beitrag bestätigst du, dass du die erforderlichen Rechte besitzt.

## Arbeitsweise

Für Coding-Agents gelten ergänzend die [Arbeitsanweisungen in AGENTS.md](AGENTS.md),
einschließlich der Nachbearbeitung von Dependabot-PRs.

1. Branch unter `feature/` oder `bug/` anlegen.
2. Änderungen klein und fachlich nachvollziehbar halten.
3. Verhalten und relevante Fehlerfälle testen. Keine Tests schreiben, die nur die
   aktuelle Implementierungsstruktur spiegeln.
4. Im Changelog nur `## New Version` um Features, Bugfixes, Breaking Changes
   und Security ergänzen. Leere Kategorien mit `- Keine.` kennzeichnen.
   Die Manifest-Version bleibt im Quellbranch `0.0.0`; die CI vergibt Version
   und Datum. Nach allen Pflichtprüfungen wartet der Push-/Merge-Lauf auf eine
   Antwort im automatisch angelegten Issue: `szech77` antwortet exakt `ja` zum
   Veröffentlichen oder `nein` zum erfolgreichen Überspringen. Schließen oder
   60 Minuten ohne Antwort überspringen ebenfalls; technische Fehler bleiben Fehler.
   Arbeitsbranches erhalten nach Freigabe Betas, `main` stabile Releases. Siehe `CI.md`.
5. Pull Request nach `main`; alle Pflichtprüfungen müssen erfolgreich sein.

Die CI erhöht bei neuen Breaking Changes Major, bei Features Minor, sonst Patch.
Bereits veröffentlichte Stichpunkte unter `New Version` entfernt die CI nach
erfolgreichen Tests, Sicherheits- und Integrationsprüfungen beim Push auf einen
Arbeitsbranch durch einen Bot-Commit. Diesen mit `git pull --ff-only` übernehmen.
Nur neue/geänderte Stichpunkte gehen in den nächsten Release ein; die stabile
Historie verhindert Wiederholungen auch nach der Bereinigung. Die vollständige
nummerierte Historie steht im jeweiligen Release-Tag.
Veröffentlichung, Beta-Installation und technische Details: [CI.md](CI.md).

## Lokale Tests

Python 3.14.2 oder neuer und Node.js 24 verwenden:

```sh
python -m venv .venv
# Windows PowerShell: Umgebung für die folgenden Befehle aktivieren
.\.venv\Scripts\Activate.ps1
# Linux/macOS stattdessen: source .venv/bin/activate
python -m pip install -r requirements-dev.txt -r requirements-test.txt
python -m pytest -q --cov=custom_components.eos_energiezentrale --cov-branch
node --test tests/*.test.cjs
python -m bandit -r custom_components tools -ll
python -m pip_audit -r requirements-dev.txt -r requirements-test.txt --strict
python tools/release.py validate
```

### Frontend (Vue.js)

Die Panel-Oberfläche ist eine Vue-App in `frontend/` (Vue 3, TypeScript, Vite). Im
Integrationsordner `energy/web` liegen daneben nur `index.html` (Einhängepunkt und
Startmeldung), `loader.js` (lädt Stylesheet und Bundle mit der Build-Version),
`panel.js` (HA-Panel mit der authentifizierten WebSocket-Brücke), `icons.js` und
`style.css`. Lokal bauen und prüfen:

```sh
cd frontend
npm ci            # installiert exakt den Lockfile-Stand, ohne Lifecycle-Skripte (.npmrc)
npm run typecheck # vue-tsc
npm test          # Vitest mit jsdom und den echten Sprachpaketen aus energy/i18n
npm run build     # schreibt energy/web/vue/eos-vue.js
npm audit --audit-level=moderate
```

Das Bundle ist nicht versioniert (`.gitignore`); die CI baut es für jedes Release und
legt es in den Release-Commit. Für einen lokalen Test in Home Assistant nach dem Build
den Ordner `custom_components/eos_energiezentrale` kopieren und HA neu starten.

Unter Windows Vitest aus einem Pfad mit großem Laufwerksbuchstaben starten
(`C:\...`, z. B. in PowerShell); mit `c:\...` findet Vitest seinen Runner nicht.

Struktur (`frontend/src`):

```text
App.vue         Titelleiste, Statusband und die Seite der Adresse; stellt alle Stores bereit
main.ts         Einstieg des Bundles; hängt die App in #app ein
router/         Hash-Routen (#overview, #battery, #car/<id>, #usage/<bericht>, #settings, …)
views/          Seiten, je eine pro Route (Overview, Device/Car, PvWeather, Usage, Notices, Settings)
  __tests__/    Komponententests der Seiten (Vitest)
components/     UI-Bausteine, nach Bereich gruppiert (app/, car/, device/, overview/, settings/, status/, usage/, weather/)
composables/    Wiederverwendbare Composition-API-Logik (useGoalDraft, usePvForecast, useViewport, …)
layouts/        Seitenrahmen (DeviceLayout: Zurück, Titel, Einstellungen)
stores/         Zustand per provide/inject: app (Verbindung, Sprache, Aktualisierung) und je Bereich
utils/          Framework-unabhängige Hilfen: Brücke, Formatierung, Texte, Diagrammmodelle
types/          TypeScript-Typen des Backend-Vertrags und der Host-Schnittstelle
test/           Test-Host, Einhänge-Hilfen, Backend-Brücke und Testdaten (fixtures/)
__tests__/      Tests der App: Start, Brücke und Routen
```

- Der App-Store (`stores/app.ts`) lädt das Sprachpaket (mit Wiederholung, solange die
  Integration startet), fragt den Snapshot alle 5 s und den Verlauf jede Minute ab und
  hält die Browser-Hinweise (Verbindung, Seitenfehler). Alle Bereichs-Stores lesen
  dieselben Refs; keine Seite fragt die Momentwerte selbst ab.
- Anfragen gehen per `postMessage` an `panel.js`, das die HA-WebSocket-API aufruft
  (nur Administratoren). Antworten werden nur vom übergeordneten Panel desselben
  Ursprungs und für diesen Client angenommen; Fehler enthalten nur freigegebene Codes,
  Gründe und Feldnamen. Kein Token gelangt in den iframe.
- Stores sind schlanke Fabriken mit `provide`/`inject`; Pinia wird erst eingeführt,
  wenn ein konkreter Bedarf über diese Fabriken hinausgeht.
- Zeitraum und Einheit der Auswertungen merkt sich der Browser (`localStorage`); bei
  gesperrtem Speicher gilt die Auswahl nur bis zum Neuladen.
- Testdaten mit Backendbezug erzeugt `src/test/backend.ts` über das Python-Backend
  (`tests/backend.cjs`), damit Tests den echten Vertrag nutzen.
- Composition API mit `<script setup lang="ts">`, `provide`/`inject` mit typisierten
  Schlüsseln; keine Options API, kein `v-html`, kein Laufzeit-Templatecompiler
  (CSP ohne `eval`). Backendtexte bleiben Text.
- Fachliche Werte kommen weiter aus dem Backend; Vue übersetzt, formatiert und zeichnet.
- Neue npm-Abhängigkeiten nur mit konkretem Bedarf, mit exakter Version und
  mindestens 14 Tage alt; `npm audit` muss ohne Befund bleiben.

VS Code nutzt weiterhin die Projekt-`.venv` und die zentrale `pytest.ini`.
Nach dem Architekturwechsel die vorhandene Umgebung mit Python 3.14 neu anlegen
oder die beiden Requirements-Dateien in eine kompatible Umgebung installieren.

## Architektur

`custom_components/eos_energiezentrale/energy` enthält die unabhängig von HA
modellierte Regelungslogik, Treiberverträge, EOS-/Influx-Clients und den Verlauf.
`adapter.py` verbindet synchrone Treiber aus einem Executor mit dem HA-Eventloop.
Der Coordinator serialisiert Polling, Steuerbefehle, Einstellungen und Stoppen.
Blockierende HTTP-, Datei- und SQLite-Zugriffe dürfen nicht in den Eventloop.

Fachliche Berechnungen, Statusbewertungen und Warnungsentscheidungen gehören ins
Backend, einschließlich der Anzeigewerte für Energie und Kosten. Das Frontend
übermittelt Eingaben, übersetzt/formatiert Backendwerte und zeichnet die Oberfläche.
Vom Backend erzeugte Warnungen und Fehler benötigen dieselbe Kennung im Backend-Log;
unveränderte Zustände werden gedrosselt, Ursachenwechsel und Behebungen erfasst.
Browserfehler bleiben ausschließlich im Browser; keine Nachlieferung an das
Backend nach Neustarts. Plugin-Lesefehler, unvollständige Messwerte und abgelehnte
Konfigurationen benötigen dagegen Backend-Logeinträge. Siehe [LOGGING.md](LOGGING.md).

Gerätebefehle benötigen passende Domänen und Bestätigungen. Ausschalten und Fehler
müssen neue Regelbefehle verhindern; eine unbestätigte Rückgabe darf nicht als Erfolg
erscheinen. Neue Hardware erweitert die Registries und erhält fachliche Tests.

Die Oberfläche nutzt HA-WebSockets statt eigener Authentifizierung. Keine Tokens,
Passwörter oder Rohfehler mit privaten Daten in Frontend-Antworten, Logs oder Tests
mit echten Zugangsdaten aufnehmen. Sicherheitsprobleme nicht mit privaten
Messwerten in öffentlichen Issues veröffentlichen.

Semgrep-Regeln und ihre sicheren/unsicheren Beispiele werden zusammen unter
`.semgrep/rules` gepflegt. Die native Semgrep-Engine wird geprüft installiert; Einrichtung
und lokale Befehle stehen in [CI.md](CI.md#semgrep-regeln-datenschutz-und-lokale-prüfung).
Keine globalen Ausschlüsse oder pauschalen Unterdrückungen für Fehlalarme einführen.
Regelanpassungen benötigen einen passenden Regressionstest. In GitHub werden nur
geschwärzte SARIF-Berichte bewertet; Rohreports bleiben lokal bzw. in `RUNNER_TEMP`.

Übersetzungen: native HA-Texte in `translations`, Panel-Texte in `energy/i18n`.
Englisch bleibt der Rückfall. UI und Einstellungen müssen auf kleinen Bildschirmen
benutzbar bleiben.

## VS Code: Tests erkennen und ausführen

Im geöffneten Repository einmal **Python: Select Interpreter** aufrufen und
`.venv\Scripts\python.exe` auswählen. `defaultInterpreterPath` ist nur der
Standard für neue Workspaces; eine zuvor gespeicherte Auswahl bleibt erhalten.
Danach **Test: Refresh Tests** ausführen, bei Bedarf **Developer: Reload Window**.

Bei `ModuleNotFoundError: No module named homeassistant` fehlen die
Testabhängigkeiten in genau dieser Umgebung. Ohne Aktivierung eindeutig installieren:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest -q
```

Alternativ installiert die VS-Code-Aufgabe **Tests: Abhängigkeiten installieren**
die beiden Requirements-Dateien über die Projektumgebung.

Wichtig: Home Assistant 2026.11 ben�tigt mindestens Python 3.14.2. Bei einer �lteren Projektumgebung gen�gt eine Paketnachinstallation nicht: Umgebung sichern, mit einer unterst�tzten Python-Version neu erstellen und anschlie�end beide Requirements-Dateien installieren. F�r die Pr�fung immer den eigenen Interpreter der Umgebung verwenden; ein anderer Python-Prozess mit umgebogenem Suchpfad pr�ft weder deren Interpreter noch deren Dateizugriff.


### JavaScript-Tests im VS-Code-Test-Explorer

Die Erweiterung **node:test runner** (`connor4312.nodejs-testing`) ist als
Workspace-Empfehlung hinterlegt. Sie integriert die vorhandenen `node:test`-Tests
ohne Jest/Mocha oder zusätzliche npm-Abhängigkeiten in die native Testansicht.

1. Die empfohlenen Erweiterungen installieren. Python/pytest bleibt unverändert.
2. Node.js 24 verwenden. Die Erweiterung nutzt `node` aus dem PATH; bei einer
   eigenen Installation in den **Benutzereinstellungen** `nodejs-testing.nodejsPath`
   auf die eigene `node.exe` setzen. Maschinenabhängige Pfade nicht ins Repo übernehmen.
3. Nach der Installation **Developer: Reload Window** und **Test: Refresh Tests** aufrufen.
4. Im Test-Explorer erscheinen Python- und JavaScript-Tests. Über die Play-/Debug-Symbole
   einzelne Tests, Dateien oder alle Tests ausführen. Fehler und Ausgaben erscheinen dort.

Die Workspace-Konfiguration beschränkt die JavaScript-Erkennung auf `tests/*.test.cjs`.
Hilfsskripte und virtuelle Python-Umgebungen werden nicht als Tests erkannt. Es gibt
keinen Kompilierungs- oder Paketinstallationsschritt für die JavaScript-Tests.
Alternativ führt **Terminal → Run Task → Tests: JavaScript** alle JavaScript-Tests aus;
die Aufgabe verwendet dieselbe konfigurierte Node-Laufzeit wie der Test-Explorer.

Bei `spawn node ENOENT` ist Node.js für VS Code nicht erreichbar. Den Pfad in den
Benutzereinstellungen korrigieren bzw. nach einer PATH-Änderung VS Code neu starten.

### Python- und JavaScript-Coverage in VS Code

Die Python-Testkonfiguration übergibt pytest-cov ausdrücklich das gesamte
Integrationspaket und aktiviert Branch-Coverage. Damit erscheinen auch noch
nicht ausgeführte Python-Module in der Auswertung; Testdateien werden nicht als
Produktivcode gezählt. `pytest-cov` ist in `requirements-dev.txt` enthalten.

Im Test-Explorer beim Coverage-Symbol das Dropdown **Configure Test Profiles**
öffnen und für Coverage sowohl **Python/pytest** als auch **Node.js** auswählen.
Ein ausschließlich ausgewähltes Node.js-Profil führt keine Python-Coverage aus.
Alternativ beim Python-Testbaum **Run Tests with Coverage** wählen.
Die Ansicht **Test Coverage** zeigt die jeweiligen Testergebnisse; dort bei Bedarf
den Python-Lauf auswählen. Die beiden Erweiterungen liefern getrennte Ergebnisse.
Nach Änderungen **Test: Refresh Tests** ausführen, gegebenenfalls das Fenster neu laden.

Die Aufgabe **Tests: Python mit Coverage** prüft dieselbe Python-Messung im Terminal.
Sie ersetzt nicht den Coverage-Lauf des Test-Explorers, der die Editor-Markierungen liefert.
Da die expliziten pytest-Argumente auch bei normalen Läufen gelten, beim Debuggen
in einer Python-Test-Debugkonfiguration `--no-cov` übergeben, falls Breakpoints
durch die Coverage-Messung beeinträchtigt werden.
