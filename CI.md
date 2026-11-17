# CI, Releases und Branchschutz

`main` ist der Hauptbranch. Die CI läuft bei Pushes auf `feature/**`, `bug/**`, `bugfix/**` und
`main`, bei Pull Requests nach main sowie in einer Merge Queue.

Verpflichtender Sammelstatus: **Required checks**. Er hängt ab von:

- Fachlichen Tests und HA-Schnittstellentests mit Python 3.14 / HA 2026.11.0.
- JavaScript-Syntax und Tests der authentifizierten Panel-Kommunikation.
- Bandit, pip-audit für Entwicklungs-/HA-Testabhängigkeiten und Trivy-Geheimnisscan.
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
keine zweite Beta. Die Beta des ursprünglichen Pushes bleibt an dessen geprüften
Quellcommit gebunden. Die Sammelprüfung des Push-Laufs verlangt zusätzlich eine
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

Nach **allen** erfolgreichen Pflichtprüfungen gelten folgende Kanäle:

| Auslöser im Originalrepository | Veröffentlichung |
| --- | --- |
| Push auf `feature/**`, `bug/**`, `bugfix/**` | `vX.Y.Zb<GitHub-Run-ID>` als GitHub-Prerelease |
| Push/Merge nach `main` | `vX.Y.Z` als stabiles, neuestes Release |
| Pull Request, Merge Queue, Fork, manueller Lauf | Nur Prüfungen, keine Veröffentlichung |

Der Publish-Job prüft ausdrücklich `!cancelled()` und ein erfolgreiches
`needs.required.result`. Das ist auch nach einem grünen Sammelstatus nötig:
GitHubs implizites `success()` berücksichtigt übersprungene Vorgänger entlang
der Abhängigkeitskette. Auf `main` ist die Branch-Changelog-Bereinigung absichtlich
übersprungen; das darf die stabile Veröffentlichung nicht überspringen. Die
explizite Statusfunktion hebt nur diese implizite Sperre auf. Fehlgeschlagene,
übersprungene oder abgebrochene Pflichtprüfungen geben keinen Release frei.

Jeder neue Branchlauf erhält eine eindeutige Beta-Nummer, etwa
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

Bandit, pip-audit und Trivy veröffentlichen ihre Befunde als SARIF unter
**Repository → Security → Code scanning**. Die Tools behalten getrennte Namen:
**Bandit**, **pip-audit**, **Trivy Secrets**. Die Action erzeugt keine Issues und
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
