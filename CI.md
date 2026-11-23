# CI, Releases und Branchschutz

`main` ist der Hauptbranch. Die CI läuft bei Pushes auf `feature/**`, `bug/**`, `bugfix/**` und
`main`, bei Pull Requests nach main sowie in einer Merge Queue.

Verpflichtender Sammelstatus: **Required checks**. Er hängt ab von:

- Fachlichen Tests und HA-Schnittstellentests mit Python 3.14 / HA 2026.11.0.
- JavaScript-Syntax und Tests der authentifizierten Panel-Kommunikation.
- Frontend unter `frontend/`: `npm ci --ignore-scripts`, Typprüfung (`vue-tsc`),
  Komponententests (Vitest) und Build des Vue-Bundles; `npm audit --audit-level=moderate`
  im Sicherheitsjob.
- Bandit, Semgrep CE für Python/JavaScript (Regeltests und Scan), pip-audit für
  Entwicklungs-/HA-Testabhängigkeiten und Trivy-Geheimnisscan.
- Home-Assistant-hassfest und HACS-Validierung. Der Brands-Katalog ist für dieses
  benutzerdefinierte Repository nicht erforderlich und wird nicht geprüft.
- Changelog-Kategorien, automatische Versionsplanung und Schutz vor Wiederverwendung eines Tags.

Containerbau, Container-Vulnerability-Scan und GHCR-Publish entfallen, weil kein
eigenes Laufzeit-Image mehr ausgeliefert wird.

## Automatische Versionierung und Betas

Im Quellbranch wird ausschließlich der oberste Changelog-Abschnitt gepflegt:

```markdown
## New Version

### Features

- Neue Funktion beschreiben.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.
```

Die CI ermittelt die nächste Version aus dem letzten stabilen Release und den
bereits belegten stabilen Tags. Neue Einträge unter `Breaking Changes` erhöhen
Major (auch von 0.x auf 1.0.0), `Features` Minor, sonst `Bugfixes`/`Security` Patch.
Die höchste betroffene Kategorie entscheidet. Aus 0.19.0 wird beispielsweise
0.20.0 für ein Feature oder 0.19.1 für einen Fehlerfix.

Die Stichpunkte werden mit `New Version` des zuletzt stabil veröffentlichten
Quellcommits und der nummerierten stabilen Release-Historie verglichen. Bereits
veröffentlichte Einträge werden nicht erneut gezählt, auch wenn sie aus späteren
Quellbranches bereits entfernt wurden. Neue/geänderte Stichpunkte müssen das neue
Verhalten beschreiben. Ohne neue Einträge schlägt die Versionsplanung fehl.
Veröffentlichte nummerierte Einträge bleiben erhalten; Betas verbrauchen keine
Einträge für das nächste stabile Release.

### Automatische Einträge für Abhängigkeitsupdates

Die Versionsplanung vergleicht außerdem die gepinnten Abhängigkeiten mit dem
zuletzt stabil veröffentlichten Quellcommit: exakte Pins (`name==version`) in
`requirements-dev.txt` und `requirements-test.txt`, exakte Versionen in
`dependencies`/`devDependencies` von `frontend/package.json` (auch npm-Aliase mit
exakter Zielversion wie `npm:@typescript/typescript6@6.0.2`) sowie Actions mit vollständigem
Commit-SHA in `.github/workflows/*.yml` und `*.yaml`. Versionskommentare
(`uses: owner/action@<sha> # vX.Y.Z`) werden zusätzlich ausgewertet. Für jedes
geänderte Patch- oder Minor-Update, das in
keinem neuen Stichpunkt namentlich genannt ist, ergänzt sie in den Release-Notes
einen `Bugfixes`-Eintrag, zum Beispiel:

```markdown
- Abhängigkeit `homeassistant` von 2026.11.1 auf 2026.11.2 aktualisiert (`requirements-test.txt`); automatisch erfasst.
```

Ein reiner Dependabot-PR für ein solches Update braucht damit keinen eigenen
Changelog-Eintrag und ergibt ein Patch-Release. Der Eintrag entsteht nur in den
Release-Notes; `CHANGELOG.md` im Quellbranch bleibt unverändert, und kein Workflow
schreibt in den Pull Request. Ein eigener Stichpunkt, der die Abhängigkeit nennt,
ersetzt den automatischen Eintrag.

Auch reine Commit-Updates von Actions ohne Versionskommentar, beispielsweise
`home-assistant/actions/hassfest`, erzeugen automatisch einen `Bugfixes`-Eintrag
mit beiden vollständigen Commit-SHAs. Die Planung behauptet dafür weder eine
Patch-/Minor-Version der Action noch API-Kompatibilität oder eine Sicherheitskorrektur.
Ohne andere Änderungen ergibt das ein Patch-Release dieser Integration.
Ein Wechsel zwischen Commit-Pins und Versionskommentaren sowie ein geänderter
Commit bei gleich gebliebenem Versionskommentar werden ebenfalls erfasst.
Eine bloße Kommentaränderung bei unverändertem Commit zählt nicht als Update;
bewegliche Tags, Branchreferenzen und verkürzte Hashes bleiben ausgeschlossen.
Mehrfach verwendete identische Updates erscheinen nur einmal in den Release-Notes.
Ein eigener Stichpunkt mit dem Action-Namen ersetzt auch den automatischen
Commit-Eintrag. Kompatibilitätsprüfung und alle Pflichtchecks bleiben erforderlich.

Erkennbare Major-Updates (geänderte erste Versionsstelle, bei Kalenderversionen wie
`2026.11.x` geändertes Jahr oder geänderter Monat) und nicht lesbare Versionen
stoppen die Versionsplanung, bis ein eigener Stichpunkt die Abhängigkeit nennt
und die geprüfte Auswirkung beschreibt. Neu hinzugefügte oder entfernte
Abhängigkeiten werden nicht automatisch erfasst.
Bei npm-Alias-Updates steht der Aliasname mit der Zielversion im Eintrag;
Versionsbereiche und Tags bleiben von der automatischen Erkennung ausgeschlossen.

Bei einem Push auf `feature/**`, `bug/**` oder `bugfix/**` entfernt die CI im
Originalrepository bereits stabil veröffentlichte Stichpunkte aus `New Version`.
Dafür müssen Tests, Sicherheits- und Integrationsprüfungen erfolgreich sein.
Ein Bot-Commit ändert ausschließlich diesen Entwurfsabschnitt; neue/geänderte
Einträge, alle vier Kategorien und die vorhandene nummerierte Historie bleiben
erhalten. Leere Kategorien enthalten `- Keine.`. Mit `git pull --ff-only` wird
der Bot-Commit anschließend auch lokal übernommen.

Da ein Push mit `GITHUB_TOKEN` keinen weiteren Push-Lauf startet, löst die CI
ausdrücklich einen `workflow_dispatch` für den bereinigten Branch aus. Dieser
prüft den neuen Commit vollständig, bereinigt aber nicht erneut und veröffentlicht
kein Release und fordert auch keine Release-Freigabe an.
Die Sammelprüfung des Push-Laufs verlangt zusätzlich eine
erfolgreiche Bereinigung beziehungsweise einen bestätigten unveränderten Entwurf.
Fehler bei Branch-Update oder Folgeprüfung werden nicht als Erfolg gewertet.
Die Dispatch-Ausnahme ist im [GitHub-Verhalten für GITHUB_TOKEN](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)
beschrieben.

Neuere oder zwischenzeitlich gepushte Commits werden nicht überschrieben; die CI
verwendet ausschließlich Fast-Forward-Updates. Nach einem Dispatch-Fehler kann
derselbe Lauf den schon angelegten Bereinigungscommit wiederverwenden. Branchschutz
wird nicht umgangen: Verbietet eine Regel Bot-Updates auf dem Arbeitsbranch,
schlägt die Bereinigung sichtbar fehl. `main`, Forks und Pull-Request-Läufe werden
nicht automatisch beschrieben.

Pushes und Merges starten weiterhin alle Pflichtprüfungen. Nach **allen**
erfolgreichen Pflichtprüfungen wartet derselbe Lauf im Job `release_decision`
auf eine Ja/Nein-Antwort im automatisch angelegten GitHub-Issue. Ohne ausdrückliches
Ja starten weder der Release-Build noch die Veröffentlichung. Nach der Entscheidung
gelten folgende Kanäle:

| Auslöser im Originalrepository | Veröffentlichung |
| --- | --- |
| Push auf `feature/**`, `bug/**`, `bugfix/**`, danach Freigabe | `vX.Y.Zb<GitHub-Run-ID>` als GitHub-Prerelease |
| Push/Merge nach `main`, danach Freigabe | `vX.Y.Z` als stabiles, neuestes Release |
| Nein, Schließen ohne Antwort oder 60 Minuten ohne Entscheidung | Kein Release; Entscheidung erfolgreich, Publish-Job übersprungen, Workflow grün |
| Pull Request, Merge Queue, Fork, manueller Lauf, Bot-Folgeprüfung | Nur Prüfungen, keine Freigabeanfrage und keine Veröffentlichung |

Im betreffenden Lauf unter **Actions → CI → Decide whether to publish a release**
steht der Issue-Link im Log und in der Job-Zusammenfassung. Das Issue nennt Branch,
Kanal, vollständigen geprüften Quellcommit, Laufnummer und Versuch und wird
`szech77` zugewiesen. Als **eigenen Kommentar** exakt antworten:

- **`ja`** oder **`yes`**: Diesen geprüften Stand veröffentlichen.
- **`nein`** oder **`no`**: Erfolgreich ohne Release abschließen.

Groß-/Kleinschreibung und umgebende Leerzeichen sind egal. Nur die erste eindeutige
Antwort des konfigurierten menschlichen Freigebers zählt. Andere Benutzer, Bots,
Zitate und Sätze wie „ich sage ja“ geben nichts frei. Ohne gültige Antwort bedeutet
auch das Schließen des Issues „kein Release“. Das Skript fragt alle 15 Sekunden ab;
nach 60 Minuten ohne Antwort endet es ebenfalls erfolgreich ohne Release. Der Job
hat 65 Minuten einschließlich Einrichtung und Aufräumen und belegt beim Warten
einen Runner. Fehler beim API-Zugriff, ungültige API-Antworten oder fehlgeschlagenes
Aufräumen schlagen den Entscheidungsschritt fehl; sie werden nicht als Nein gewertet.

`tools/release_approval.py` verwendet nur Python-Standardbibliothek und den
vorhandenen GitHub-Client. Der Entscheidungsjob hat `contents: read` und
`issues: write`, aber keine Schreibrechte auf Quellcode oder Releases. Das Issue
wird in einem `always()`-Schritt auch nach Fehlern oder Abbruch geschlossen, soweit
der Runner und die GitHub-API dies noch ausführen können. Jeder neue Versuch legt
eine neue Anfrage an und übernimmt keine frühere Freigabe. Ein neuer Push auf einen
Arbeitsbranch kann einen älteren wartenden Lauf nach der bestehenden Concurrency-Regel
abbrechen. Der gewöhnliche Frontend-Build im Testjob bleibt Teil der Pflichtprüfungen.

Die bisherige geschützte Umgebung `release` wird vom Workflow nicht mehr verwendet;
ihre Repository-Einstellungen müssen nicht geändert werden. Es erscheint kein
**Review deployments** mehr. GitHubs native Ablehnung würde weiterhin den Lauf
fehlschlagen lassen; stattdessen ist Nein hier ein reguläres Skriptergebnis.
Referenzen: [GitHub: Issue-Kommentare](https://docs.github.com/en/rest/issues/comments),
[GitHub: Deployment-Ablehnung](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments).

Der Publish-Job prüft ausdrücklich `!cancelled()`, ein erfolgreiches
`needs.required.result`, einen erfolgreichen Entscheidungsjob und dessen Ausgabe
`approved == 'true'` sowie Push-Ereignis, Originalrepository und erlaubte Quellbranches.
Ohne Ja wird der Publish-Job übersprungen; echte Veröffentlichungsfehler bleiben rot.
Das ist auch nach einem grünen Sammelstatus nötig:
GitHubs implizites `success()` berücksichtigt übersprungene Vorgänger entlang
der Abhängigkeitskette. Auf `main` ist die Branch-Changelog-Bereinigung absichtlich
übersprungen; das darf die Issue-Anfrage und die anschließende stabile
Veröffentlichung nicht überspringen. Die
explizite Statusfunktion hebt nur diese implizite Sperre auf. Fehlgeschlagene,
übersprungene oder abgebrochene Pflichtprüfungen geben keinen Release frei.

Jeder freigegebene Branchlauf erhält eine eindeutige Beta-Nummer, etwa
`0.20.0b123456789`. Wiederholungen desselben Laufs verwenden dieselbe Version,
denselben Tag und dieselben Release Notes; bestehende Tags werden nie verschoben.
Betas verändern nicht das neueste stabile Release. Für Betas in HACS
**Beta-Versionen anzeigen** aktivieren und die gewünschte Version auswählen;
der Release-Titel nennt den Quellbranch.

`manifest.json` enthält im Quellbranch den Entwicklungsplatzhalter `0.0.0`.
Die Pipeline erstellt über die GitHub-API einen separaten Metadatencommit mit
dem exakt geprüften Quellcommit als direktem Elterncommit. Nur Manifest-Version,
datierter Changelog und `.release-source.json` mit Quell-SHA und Prüfsummen
werden ergänzt. Der Release-Tag zeigt auf diesen Commit; der Anwendungscode
stammt vollständig aus dem geprüften Stand. HACS erhält dadurch immer eine zum
Tag passende Manifest-Version. Der Default-Branch wird in HACS ausgeblendet.

Die Pipeline schreibt keine Bot-Commits auf `main` und benötigt keinen
Branchschutz-Bypass und kein persönliches Token. Der Bereinigungsjob für
Arbeitsbranches hat `contents: write` und für die Folgeprüfung `actions: write`;
der Publish-Job hat ausschließlich `contents: write`. Versionsplanung und
PR-Prüfungen bleiben lesend. Die nummerierte Historie wird aus dem letzten stabilen Release übernommen
und steht vollständig im Changelog der Release-Tags, nicht automatisch im
Quellbranch. Dort bleibt `## New Version` als Eingabebereich für die nächste
Version stehen; auf Arbeitsbranches bereinigt die CI dessen alte Einträge beim
nächsten erfolgreichen Push-Lauf. Im veröffentlichten Code unter
**Releases → Tag → CHANGELOG.md** wird diese Überschrift durch Version und Datum
ersetzt; auch die Quellcodearchive des Tags enthalten diesen nummerierten Stand.

Alte Branches müssen vor der Veröffentlichung den letzten stabilen Quellstand
übernehmen. Nach einem Squash-Merge oder Rebase erkennt die Versionsplanung auch
einen Commit mit identischem vollständigem Git-Dateibaum in der Branchhistorie
als diesen Quellstand an. Gleiche Changelog- oder Manifest-Dateien allein reichen
nicht aus. Fehlen stabile Änderungen, bleibt die Veröffentlichung gesperrt.
Auf `main` werden laufende Releases durch einen neuen Push nicht abgebrochen.

Lokal prüft `python tools/release.py validate` die Eingaben. Eine lesende Vorschau
für einen bereits auf GitHub vorhandenen Quellcommit ist beispielsweise:

```sh
python tools/release.py plan --repository szech77/HA_EOS_Akkodoktor_Energiezentrale --commit <vollständige-SHA> --channel beta --beta-number 123456789 --branch feature/meine-aenderung
```

Die Veröffentlichung akzeptiert nur den Changelog des angegebenen Quellcommits.
Nicht committete Änderungen sind keine gültige Release-Grundlage. Tags/Releases
werden ausschließlich durch die Pipeline veröffentlicht.

`main-ruleset.json` und `tools/configure_github.py` bleiben für den Branchschutz
vorbereitet. Ihre bloße Existenz aktiviert ihn nicht: Ein Repository-Administrator
muss den Regelsatz über GitHub oder das Skript mit geeignetem Token einrichten.
Direkte Pushes verbieten und **Required checks** als Pflichtprüfung hinterlegen.

Die eingesetzten Scanner sind frei verfügbar. GitHub-Actions-Kosten richten sich
nach Repository-Sichtbarkeit, Tarif und genutztem Kontingent. HACS benötigt ein
erreichbares öffentliches Repository; das ist vor Veröffentlichung zu prüfen.


## Gebautes Frontend im Release

Das Vue-Bundle `custom_components/eos_energiezentrale/energy/web/vue/` ist nicht im
Quellbaum versioniert. Der Publish-Job baut es aus dem geprüften Quellcommit
(`npm ci --ignore-scripts`, `npm run build`, ohne npm-Cache im schreibberechtigten Job)
und `tools/release.py publish` legt die gebauten `.js`/`.css`-Dateien zusammen mit
Manifest, Changelog und `.release-source.json` in den Release-Commit. Ohne Bundle
bricht die Veröffentlichung ab. `.release-source.json` enthält `bundle_sha256` über
Pfade und Inhalte der ausgelieferten Bundle-Dateien. HACS installiert diesen Tag-Stand.

## HACS-Prüfungen für Repository-Metadaten

HACS liest Beschreibung, Topics und die von GitHub erkannte Lizenz aus den
Repository-Metadaten. Eine LICENSE-Datei nur im Feature-Branch reicht für die
GitHub-Lizenzerkennung noch nicht aus. Deshalb werden in Feature-/Bugfix-Branches,
Pull Requests und der Merge Queue diese drei externen Checks übersprungen;
`tools/validate_hacs_metadata.py` prüft dort weiterhin die vollständige Apache-2.0-
Lizenz im Root und Integrationsordner sowie die vorgesehenen Metadaten. Auf main
bleiben die GitHub-Prüfungen aktiv. Quellcode- und Sicherheitsprüfungen laufen unverändert.

Vor dem ersten Merge nach main unter GitHub → Repository → **About → Zahnrad**
eine Beschreibung und Topics setzen. Die vorgesehenen Werte stehen in
`.github/repository-metadata.json`. Beispielbeschreibung:

> Home Assistant integration for Akkudoktor EOS with solar surplus EV charging, battery control and energy dashboards.

Topics: `home-assistant`, `hacs`, `akkudoktor-eos`, `energy-management`,
`solar-energy`, `ev-charging`.

Alternativ mit einem vorhandenen `GH_TOKEN` mit Repository-Administrationsrechten:

```sh
python tools/configure_github.py --repo szech77/HA_EOS_Akkodoktor_Energiezentrale --metadata-only
```

Diese Variante ergänzt fehlende Beschreibung und Topics, erhält vorhandene Topics
und verändert weder den Hauptbranch noch Branchschutzregeln. Die Apache-Lizenz
kommt regulär mit dem Pull Request nach main; dafür ist kein direkter Push nötig.
Eine automatische Änderung von GitHub-Repository-Einstellungen ist mit den
normalen Leserechten dieses CI-Jobs nicht möglich.


## Findings in GitHub Security / Code scanning

Bandit, Semgrep, pip-audit und Trivy veröffentlichen ihre Befunde als SARIF unter
**Repository → Security → Code scanning**. Die Tools behalten getrennte Namen:
**Bandit**, **Semgrep**, **pip-audit**, **Trivy Secrets**.
Die Action erzeugt keine Issues und
keine PR-Kommentare. Ergebnisse eines Feature-Branches lassen sich über den
Branchfilter auswählen; die Standardansicht zeigt Ergebnisse des Default-Branches.

`tools/security_sarif.py` konvertiert die JSON-Reports, ordnet Fundstellen zu und
schreibt auch bei einem erfolgreichen Scan ohne Findings einen leeren SARIF-Report,
damit GitHub behobene Befunde schließen kann. Direkte Abhängigkeiten werden ihrer
Requirements-Zeile zugeordnet; transitive Abhängigkeiten erscheinen am Anfang von
`requirements-test.txt` und werden ausdrücklich als transitiv gekennzeichnet.
pip-audit liefert keinen CVSS-Wert; die Konvertierung erfindet keine Schweregrade.

Scanner dürfen nach Findings zunächst weiterlaufen, damit alle Berichte hochgeladen
werden. Der abschließende Schritt prüft die ursprünglichen Scanner-Exitcodes und
den Upload: Findings, unvollständige Scans, kaputte Reports oder Uploadfehler lassen
**Source security** und damit **Required checks** weiterhin fehlschlagen.

Nur der Security-Job erhält `security-events: write`; Checkout-Zugangsdaten werden
nicht gespeichert. Es werden keine privilegierten `pull_request_target`-Workflows
verwendet. Der Upload nutzt ausschließlich den kurzlebigen `GITHUB_TOKEN`.
Rohberichte liegen außerhalb des Checkouts in `RUNNER_TEMP` und werden nicht als
Artefakt hochgeladen. Bei möglichen Secrets enthalten SARIF-Berichte nur Regel und
Fundstelle, keine gefundenen Werte oder Codeausschnitte. Trivy-Findings erscheinen
als Code-Scanning-Befunde, nicht als native GitHub-Secret-Scanning-Alerts.

Für öffentliche GitHub-Repositories ist Code scanning kostenlos verfügbar; es
ist dafür kein kostenpflichtiges Advanced-Security-Abo erforderlich. Bei privaten
Repositories muss GitHub Code Security freigeschaltet sein. Die erste erfolgreiche
SARIF-Übertragung richtet die Analysen ein; es sind keine zusätzlichen persönlichen
Tokens nötig. Falls GitHub den Upload wegen einer Repository-/Organisationsrichtlinie
ablehnt, unter **Settings → Advanced Security / Code security** die Freigabe prüfen.
Die Pipeline überspringt diesen Fehler nicht stillschweigend.

Referenz: https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file

### Semgrep-Regeln, Datenschutz und lokale Prüfung

Verwendet wird ausschließlich die native Semgrep-CE-Engine `semgrep-core`, nicht
die Python-CLI. `tools/install_semgrep.py` lädt das in `.semgrep/tool.json` exakt
gepinnte offizielle PyPI-Wheel (Linux bzw. Windows x86_64) ohne Weiterleitungen
nur von `files.pythonhosted.org`, prüft Größe und SHA-256 und extrahiert nur die
Engine und ihre mitgelieferten Bibliotheken (unter Linux im Unterordner `libs/`).
Es werden keine Python-Pakete installiert; Home-Assistant-Laufzeit- und
Testabhängigkeiten bleiben unverändert. `PyYAML` ist eine explizite
Entwicklungsabhängigkeit für den versionierten Regelkatalog.

Dependabot und pip-audit erfassen `.semgrep/tool.json` nicht. Ein Semgrep-Update
erfolgt manuell in einem eigenen PR: Release Notes lesen, `version` sowie `url`,
`sha256` und `size` beider Wheels aus `https://pypi.org/pypi/semgrep/<version>/json`
übernehmen, Regeltests und Scan ausführen und `New Version` ergänzen.
`semgrep-core` akzeptiert mit `-lang` nur eine Zieldatei; deshalb läuft je Datei
und Regelgruppe ein eigener, einzeln validierter Engine-Aufruf.

`.semgrep/rules` enthält sieben eigene Apache-2.0-Regeln und zugehörige positive
und negative Beispiele: Python-Shell-Aufrufe, dynamische Codeausführung,
deaktivierte TLS-Prüfung, JavaScript-Codeauswertung, beliebige `postMessage`-
Zielursprünge und DOM-XSS aus URL-Daten bzw. Inline-Message-Callbacks.
Der getestete Panel-Encoder `html()` und DOMPurify werden in der DOM-Regel als
Sanitizer berücksichtigt. Dies ist ein begrenzter, gezielt gepflegter Regelsatz,
keine vollständige Sicherheitsprüfung oder funktionsübergreifende Taint-Analyse.

`tools/semgrep_scan.py` führt lokale Regeln ohne Semgrep-Login/Cloud-Konfiguration,
ohne Metrik- oder Versionsabfragen aus. Gescannt werden alle `.py`-/`.js`-Dateien
in `custom_components` und `tools`; Fixture-Dateien bleiben ausschließlich im
Regeltest. `nosemgrep`-Kommentare unterdrücken keine Funde; solche Funde bleiben
blockierend. Regeltests müssen jede Regel mit mindestens einem positiven und einem
negativen Beispiel prüfen. Scanversion, Exitcode,
Dateivollständigkeit, übersprungene Regeln und Parser-/Timeoutfehler werden geprüft.
Ein fehlerhafter Regeltest verhindert den Scan; unvollständige Berichte erzeugen
keinen scheinbar sauberen Semgrep-SARIF-Report. Andere Scannerberichte werden
weiterhin verarbeitet und hochgeladen.

Für GitHub werden ausschließlich die versionierten Regelbeschreibungen mit
stabiler ID, Behebungshilfe, CWE-Tags, Präzision, Regelpriorität und Fundstelle
übernommen. Die `security-severity`-Werte sind bewusst festgelegte Prioritäten
der eigenen Regeln, keine berechneten CVSS-Werte für konkrete Befunde.
Expandierte Meldungen, Matches, Variablenwerte, Codeausschnitte, Autofixes und
Dataflow-Traces aus Rohreports bleiben unveröffentlicht. `upload-sarif` ergänzt
Fingerprints, damit GitHub Befunde über Läufe hinweg zuordnen kann.

Unter **Security → Code scanning → Tool: Semgrep** können Findings nach Branch,
Regel und Schweregrad geprüft und beispielsweise als Fehlalarm bewertet werden.
Eine dortige Bewertung hebt die lokale CI-Sperre nicht automatisch auf: Ein
Fehlalarm wird durch eine begründete, eng gefasste Regelkorrektur mit Regressionstest
behoben. Installations-, Scanner-, Regeltest- und Uploadfehler bleiben Pflichtfehler.

Lokal unter PowerShell (Projektumgebung verwenden; die Engine landet im
ignorierten Verzeichnis `.semgrep-native`):

```powershell
.\.venv\Scripts\python.exe tools/install_semgrep.py
.\.venv\Scripts\python.exe tools/semgrep_scan.py --test
.\.venv\Scripts\python.exe tools/semgrep_scan.py --output "$env:TEMP/semgrep.json"
```

Unter Linux entsprechend `.venv/bin/python` verwenden; macOS und ARM werden vom
Installer nicht unterstützt. Ohne `--executable` nutzt `semgrep_scan.py` die
Engine aus `.semgrep-native/<version>`. Exitcode 0 bedeutet keine Funde, 1 Funde
und 2 einen unvollständigen Scan oder fehlgeschlagene Regeltests. Rohreports
nicht als Artefakt oder Issue-Anhang veröffentlichen.
Referenzen: [Semgrep CE in CI](https://docs.semgrep.dev/deployment/oss-deployment),
[GitHub SARIF-Unterstützung](https://docs.github.com/en/code-security/reference/code-scanning/sarif-support-for-code-scanning).
