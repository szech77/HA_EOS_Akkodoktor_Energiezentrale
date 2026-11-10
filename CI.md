# CI, Releases und Branchschutz

`main` ist der Hauptbranch. Die CI läuft bei Pushes auf `feature/**`, `bug/**`, `bugfix/**` und
`main`, bei Pull Requests nach main sowie in einer Merge Queue.

Verpflichtender Sammelstatus: **Required checks**. Er hängt ab von:

- Fachlichen Tests und HA-Schnittstellentests mit Python 3.14 / HA 2026.11.0.
- JavaScript-Syntax und Tests der authentifizierten Panel-Kommunikation.
- Bandit, pip-audit für Entwicklungs-/HA-Testabhängigkeiten und Trivy-Geheimnisscan.
- Home-Assistant-hassfest und HACS-Validierung. Der Brands-Katalog ist für dieses
  benutzerdefinierte Repository nicht erforderlich und wird nicht geprüft.
- Manifest-Version, Changelog-Kategorien und Schutz vor Wiederverwendung eines Tags.

Das HACS-Paket hat keine eigenen zusätzlichen Python-Laufzeitabhängigkeiten.
Containerbau, Container-Vulnerability-Scan und GHCR-Publish entfallen, weil kein
eigenes Laufzeit-Image mehr ausgeliefert wird.

Auf main erzeugt ein erfolgreicher Lauf ein GitHub-Release `v<manifest-version>`
am exakt geprüften Commit. HACS lädt `custom_components/eos_energiezentrale` aus
dem Repository-Release. Es sind weder Docker-Images noch Bot-Commits nach main nötig.
Für jeden neuen Release die Version in `manifest.json` erhöhen und einen passenden
Changelog-Eintrag mit Features, Bugfixes, Breaking Changes und Security anlegen.

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
