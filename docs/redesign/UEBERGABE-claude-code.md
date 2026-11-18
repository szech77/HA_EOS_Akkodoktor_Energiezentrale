# Übergabe: UI-Redesign Energiezentrale (aus Klick-Dummy)

Lege diese Datei und `energiezentrale-klickdummy.html` in den Projektordner (z. B. `docs/redesign/`) und gib Claude Code in VS Code folgenden Auftrag:

> Lies `docs/redesign/UEBERGABE-claude-code.md` und `docs/redesign/energiezentrale-klickdummy.html`. Lege den Branch `feature/ui-redesign` an. Setze das Redesign im bestehenden Frontend um, mit den vorhandenen Komponenten, Styles und API-Endpunkten. Der Klick-Dummy ist die Vorlage für Aufbau und Verhalten, nicht für Daten oder Code: Er enthält nur Beispielwerte. Untersuche zuerst die Projektstruktur, erstelle einen Plan in Etappen und warte auf meine Freigabe, bevor du anfängst.

## Was der Dummy festlegt (Review-Nummern stehen im Dummy)

1. **Statusband** (R1): Steuerzustand mit Ursache, Folge und Aktion auf jeder Seite; Bestätigung inline, kein Browser-Dialog.
2. **Energiefluss** (R2): Name und Wert neben dem Kreis (kein Überlappen bei Zoom); Warnzeichen an Geräten mit Problem; „≈“ für geschätzte oder alte Werte. Klickziele: PV → PV & Wetter, Netz → Netz & Einspeisung, Haus/Wärmepumpe → Auswertung, Auto → Auto-Seite, EOS-Mitte → Gesamtbilanz. Wetter-Icon oben rechts, „Stand“ unten rechts.
3. **EOS-Plan** (R3): bedienbarer Zeitstrahl und eine Liste „Was als Nächstes passiert“; Link zum Ladeplan des Autos.
4. **Auto** (R4–R6, R12): Ziel zuerst; Schalter wirken sofort; Ladeziele als kompakte Zeilen; **EOS-Ladeplan** mit Ladestandskurve, Zeitstrahl (PV / Pause / Netz / Ziel erreicht), Liste und Kostenvergleich Plan gegen Sofortladen; Zustände „überstimmt“ (Schnellladen), „ausgesetzt“ (Wallbox weg) und „nur Anzeige“ (Lesemodus).
5. **Hinweise** (R7): eine Karte pro Problem, nach Schwere sortiert, mit Folge, nächstem Schritt und Backend-Kennung.
6. **Einstellungen** (R8): Bereiche links; Expertenwerte eingeklappt; Fehler direkt am Feld; Speicherleiste nur bei Änderungen. Unter **Kosten**: Einspeisevergütung, Arbeitspreis-Bestandteile, Grundpreise.
7. **Heute-Kacheln → Auswertungen** (R9, R10): Haus, Auto, Wärmepumpe, Einspeisung, Gesamt. Jede Auswertung hat einen Umschalter Tag/Monat/Jahr mit ‹ › zum Blättern, eine Kernaussage, 4 Kennzahlen, einen Verlauf (Netz: Bezug nach oben, Einspeisung nach unten), Preise & Kosten mit Aufschlüsselung des Netzstrompreises, Herkunft bzw. „Wohin ging der PV-Strom?“ und „Was auffällt“.
8. **PV & Wetter** (R13): eigene Ansicht, die sich erst über den PV-Knoten öffnet. Aktuelles Wetter, stündliche Leiste mit Wetter über dem PV-Ertrag, Tageskarten mit Spanne, „Was EOS daraus macht“.
9. **Smartphone hochkant**: Statusband einzeilig; Hinweise als eine Zeile; seitlich wischbare Kacheln und Chips; in Auswertungen sind Preise, Herkunft und „Was auffällt“ eingeklappt.

## Kostenlogik (wie im Dummy)

- Netzbezug: Preis pro kWh = (Börsenpreis + Anbieteraufschlag + Netzentgelt + Konzessionsabgabe + Umlagen + Stromsteuer) × 1,19.
- Eigenstrom (PV direkt und aus dem Speicher) wird mit der entgangenen Einspeisevergütung bewertet.
- Grundpreise pro Monat werden tageweise verteilt und nur in Gesamt sowie Netz & Einspeisung ausgewiesen.
- Netto = Netzbezug + Grundpreise + Eigenstrom − Einspeisevergütung.

## Backend-Voraussetzungen (R11), vor der UI zu klären

1. **Langzeitdaten:** Die InfluxDB hält Rohdaten 30 Tage. Für Monat und Jahr braucht es dauerhaft gespeicherte Stunden- und Tageswerte (Downsampling oder HA-Langzeitstatistik).
2. **Tarifbestandteile:** neue Einstellungsfelder; den Börsenpreis liefert EOS stündlich.
3. **Abrechnung pro Stunde** mit dem jeweiligen Stundenpreis, nicht mit dem Tagesmittel.
4. **Wetter- und PV-Prognose:** aus der in EOS konfigurierten Quelle (stündlich, mit Spanne pro Tag).
5. **Ladeplan Auto:** Segmente (Zeit, Modus, Leistung, Phasen, kWh, Preis) aus dem EOS-Plan bereitstellen.

## Offen

- Original-Logo (SVG) für die Kopfzeile und die Mitte des Energieflusses fehlt noch.
