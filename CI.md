# Prüfungen und Veröffentlichung

Der Workflow `.github/workflows/ci.yml` läuft bei Pushes nach `feature/**`, `bug/**` und `main`, bei Pull Requests nach `main` sowie bei Merge-Queue-Prüfungen. Alle Prüfungen laufen vor dem Merge und erneut auf `main`.

## Prüfungen

- Die Python-Tests laufen mit Python 3.13 und 3.14 einschließlich Branch-Coverage. Node prüft die Syntax des Browser-Skripts.
- Bandit prüft den Python-Produktivcode und das Einrichtungsskript auf Sicherheitsprobleme mittlerer und hoher Schwere.
- pip-audit prüft die Python-Entwicklungsabhängigkeiten aus `requirements-dev.txt`. Die Anwendung verwendet zur Laufzeit die Python-Standardbibliothek.
- Trivy sucht nach Geheimnissen im Checkout. Die gebauten Images für amd64 und arm64 werden auf behebbare Sicherheitslücken hoher und kritischer Schwere geprüft. Nicht behebbare Schwachstellen blockieren diesen Lauf nicht. Die Scannergebnisse erscheinen im Actions-Protokoll.
- Der Status Required checks wird nur bei erfolgreichen Tests, Quellcodeprüfungen, Containerprüfungen und gültigen Release-Metadaten erfolgreich.

Actions sind auf konkrete Commit-IDs festgelegt. Dependabot prüft auch diese Verweise sowie die Entwicklungsabhängigkeiten täglich. Der Workflow verwendet standardmäßig nur Leserechte. Zugang zur Paketregistrierung erhält ausschließlich der Veröffentlichungsjob auf `main`.

## Veröffentlichung

Nach erfolgreichen Prüfungen eines Pushs auf main baut der Veröffentlichungsjob ein Image für amd64 und arm64 und lädt es zu GitHub Container Registry hoch. Die Image-Tags sind main, sha-<vollständiger Commit> und die Add-on-Version, beispielsweise 0.1.3.

Nach dem erfolgreichen Container-Publish erstellt derselbe Job automatisch ein GitHub-Release mit dem Tag v<Add-on-Version>. Der Tag zeigt auf genau den geprüften main-Commit. Die Release-Notizen stammen ausschließlich aus dem passenden Versionseintrag des Haupt-Changelogs. Das Add-on-Changelog muss denselben Inhalt enthalten. Der Job erhält dafür contents: write und verwendet den bereitgestellten GITHUB_TOKEN.

Jeder Pull Request nach main muss eine noch unveröffentlichte Add-on-Version und den passenden Changelog-Eintrag enthalten. Der Prüflauf vergleicht die Version mit vorhandenen Git-Tags. Diese Regel gilt auch für Abhängigkeits- und Dokumentationsänderungen, wenn sie nach main veröffentlicht werden sollen.

Jeder neue Versionseintrag enthält **Features**, **Bugfixes**, **Breaking Changes** und **Security**. Verwende „- Keine.“, wenn ein Bereich keine Änderungen enthält. Beschreibe bei Breaking Changes zusätzlich notwendige Migrationsschritte. Version und Changelog werden gemeinsam im Pull Request gepflegt. Die Pipeline erzeugt daraus Release-Notizen und benötigt dafür keinen direkten Commit nach main.

Ein erneuter Lauf für denselben Commit legt kein zweites Release an. Gehört der Versionstag zu einem anderen Commit, weichen bereits veröffentlichte Notizen ab oder existiert ein Entwurf/Vorabrelease, bricht die Veröffentlichung ab. Schlägt der Image-Publish fehl, wird kein GitHub-Release angelegt.

Das Home-Assistant-Add-on bleibt lokal baubar. Die Pipeline installiert oder aktualisiert keine laufende Home-Assistant-App. Die Containerveröffentlichung ist die Auslieferungsstufe dieser Pipeline.

## main schützen

Der Branchschutz ist eine GitHub-Repository-Einstellung. Das JSON-Dokument `.github/main-ruleset.json` beschreibt die Regel. Es muss auf GitHub aktiviert werden.

Die Regel erzwingt Pull Requests, erfolgreiche `Required checks`, einen aktuellen Stand gegenüber `main` und aufgelöste Review-Kommentare. Sie blockiert Force-Push und Löschen. Es gibt keine eingetragenen Ausnahmen. Eine zusätzliche Freigabe durch eine zweite Person ist nicht vorgeschrieben, sodass auch ein einzelner Maintainer eigene Pull Requests mergen kann.

Wenn `main` auf GitHub existiert, kannst du die Regel unter **Settings → Rules → Rulesets → Import a ruleset** importieren. Alternativ kann sie über das mitgelieferte Skript eingerichtet werden. Setze dafür in deiner Shell `GH_TOKEN` auf ein GitHub-Token mit Administrationsrecht für dieses Repository und führe Folgendes im Projektordner aus.

```sh
python tools/configure_github.py --repo szech77/HA_EOS_Akkodoktor_Energiezentrale
```

Das Skript setzt `main` als Standardbranch und erstellt oder aktualisiert die Regel `Protect main`. Es schreibt das Token weder in Dateien noch in Ausgaben. Die Regel aktiviert sich nicht allein durch das Committen der JSON-Datei.

## Kosten und Voraussetzungen

Bandit, pip-audit und Trivy sind frei verfügbare Scanner. GitHub Actions auf Standard-Runnern ist bei öffentlichen Repositories kostenlos. Bei privaten Repositories zählt die Pipeline zum Actions-Freikontingent des GitHub-Plans. Zusätzliche Laufzeit und Paketablage können vom Plan abhängen. Der tägliche Dependabot-Lauf ist separat davon kostenlos.

Branchschutz ist bei öffentlichen Repositories mit GitHub Free verfügbar. Bei privaten Repositories hängt er vom GitHub-Plan ab. Die App verwendet kein kostenpflichtiges CodeQL-/Code-Security-Abonnement.

Die erste GitHub-Ausführung muss zusätzlich den Image-Bau, QEMU und den Zugriff auf die Trivy-Datenbanken prüfen. Eine lokale Docker-Umgebung wird für die Python-Tests nicht benötigt.
