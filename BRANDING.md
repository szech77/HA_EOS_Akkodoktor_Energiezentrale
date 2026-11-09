# EOS Energiezentrale – Logo

Das freigegebene Zeichen kombiniert ein zentrales E mit einem offenen Energiering
und einem goldenen Solar-Punkt. Die Umsetzung ist ein eigenständiges SVG ohne
eingebundene Schriftarten, Rasterbilder oder externe Ressourcen.

- Master: `custom_components/eos_energiezentrale/energy/web/logo.svg`
- Türkis: `#55C7CB`
- Solar-Gold: `#FFCB62`
- Dunkler Hintergrund: `#10151D`
- Heller Vordergrund: `#EEF4FC`

Im Panel wird das Zeichen über das Symbol `logo.svg#mark` wiederverwendet. Das E
übernimmt die aktuelle Textfarbe, sodass es auf hellen und dunklen Flächen lesbar
bleibt. Die eigenständig geöffnete SVG-Datei berücksichtigt das Farbschema des Browsers.
Der Kopfbereich verwendet eine übersetzbare Wortmarke, die Diagrammmitte das
kompakte Zeichen ohne sichtbare Beschriftung; der Link bleibt zugänglich benannt.

Der Klick auf die Mitte öffnet weiterhin die gemeinsame Energieübersicht.
Das Logo ist Bestandteil der versionierten UI-Dateien, damit Logo-Updates keinen
separaten Browser-Cache zurücklassen. Die Gestaltung bezeichnet diese Integration
und ist kein offizielles Logo von Home Assistant, Akkudoktor EOS oder Fronius.

## Home Assistant: Geräte & Dienste

Die Integration liefert ihr Zeichen zusätzlich unter
`custom_components/eos_energiezentrale/brand/` aus:

- `icon.png` und `icon@2x.png`: 256 × 256 und 512 × 512 Pixel für helle Oberflächen.
- `dark_icon.png` und `dark_icon@2x.png`: entsprechende Varianten für dunkle Oberflächen.

Alle PNGs haben einen transparenten Hintergrund und stammen aus dem SVG-Master.
Home Assistant unterstützt diese lokalen Brand-Dateien seit Version 2026.3 und
verwendet das Icon auch als Logo, wenn keine separate Wortmarke vorhanden ist.
Es ist kein zusätzlicher Manifest-Eintrag und kein Download von einem externen
Bilddienst nötig. Bei manueller Installation den gesamten Integrationsordner
einschließlich `brand` kopieren, Home Assistant neu starten und die Seite neu laden.

Vorgaben: https://contributors.home-assistant.io/core/integrations/brands/


## Seitenleisten-Symbol

`energy/web/icons.js` registriert `eos-energy:logo` über Home Assistants
Custom-Icon-Schnittstelle. Die Pfadkontur ist aus dem SVG-Master abgeleitet;
Home Assistant färbt sie entsprechend dem Seitenleisten-Theme ein.
Das Modul wird global und mit derselben Build-Version wie das Panel geladen,
damit das Symbol auch vor dem ersten Öffnen des Panels verfügbar ist.
Nach der Installation Home Assistant neu starten und das gesamte HA-Frontend
neu laden. Eine zusätzliche Lovelace-Ressource ist nicht erforderlich.
