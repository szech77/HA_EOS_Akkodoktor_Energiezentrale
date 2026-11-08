# CI, Releases und Branchschutz

`main` ist der Hauptbranch. Die CI läuft bei Pushes auf `feature/**`, `bug/**` und
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
