# UI-Screenshots

Echte Browseraufnahmen des integrierten Panels mit deutschem Sprachpaket; keine
Entwurfsgrafiken. Die Desktop-Ansichten sind 1210 Pixel breit. Die JPEGs sind
direkte Browseraufnahmen ohne Browser- oder Home-Assistant-Seitenleiste. Es werden
keine Serveradressen, Standortkoordinaten oder Zugangsdaten gezeigt.

**Echte Anlage** (Stand 24. November 2026, Microsoft Edge): `overview.jpg`,
`mobile.jpg`, `battery.jpg`, `vehicle.jpg`, `pv.jpg`, `usage.jpg` und `costs.jpg`
zeigen die Messwerte, Prognosen, Pläne und Kosten einer laufenden Installation des
Projektautors. Die Werte sind nicht nachbearbeitet.

**Beispieldaten** (Stand 22. November 2026, Chrome): `settings.jpg`, `wizard.jpg`
und `wizard-mobile.jpg` verwenden synthetische Daten aus `tools/demo-data.cjs`.

- `overview.jpg`: Desktop-Übersicht mit Statusband, Energiefluss, EOS-Plan, nächsten
  Ereignissen und Heute-Kacheln.
- `battery.jpg`: Speicherverlauf, EOS-Modi und Prognosen.
- `vehicle.jpg`: Auto-Ansicht mit Ladezustand, Ladeschaltern, Ladeplan, Ladezielen
  sowie Lademodi, Wallbox-Leistung, SoC und Strompreis.
- `pv.jpg`: PV & Wetter mit stündlicher Prognose, Tageskarten und Planfolgen.
- `usage.jpg`: Monatsauswertung Hausverbrauch mit Durchschnittspreis aller Quellen
  und Speicherherkunft.
- `costs.jpg`: monatliche Gesamtbilanz mit täglicher Grundgebühr und Kostenanteilen.
- `settings.jpg`: Tarifliste mit Monats- und Tagesgebühr sowie festem kWh-Preis.
- `wizard.jpg`: neuer EOS-Einrichtungsassistent, Standortschritt mit manueller
  Eingabe sowie optionaler Browserortung und Übernahme aus Home Assistant.
- `wizard-mobile.jpg`: mobiler Ausschnitt des Standortschritts; der vollständige
  Formularbereich ist sichtbar. Die GPS-Abfrage wurde für die Aufnahmen nicht
  verwendet; Koordinaten und EOS-Konfiguration sind synthetische Testdaten.
- `mobile.jpg`: oberer Bereich der Übersicht mit 390 × 844 Pixeln einschließlich
  der unteren Navigationsleiste.

Bei Änderungen am Layout oder an sichtbaren Funktionen die betroffenen Aufnahmen
aktualisieren. Einstellungen und Assistent weiterhin nur mit Beispieldaten aufnehmen,
damit keine Konfiguration, Standortdaten oder Zugangsdaten sichtbar werden. Die
deutsche Sprache sowie die Aufnahme ohne Browser- oder Home-Assistant-Seitenleiste
beibehalten.


## Plausibilität der Beispieldaten

Dieser Abschnitt gilt für die Aufnahmen mit Beispieldaten und das Modell, mit dem
sie erzeugt werden.

Die Daten stammen aus `tools/demo-data.cjs`, einem deterministischen, vereinfachten
AC-Bus-Modell ausschließlich für die Dokumentation. Es ist keine EOS-Optimierung
und kein Bestandteil der Gerätesteuerung.

Für jedes Zweiminutenintervall gilt:

```text
PV + Netzbezug + Akkuentladung
  = Haus ohne Auto/WP + Wärmepumpe + Auto + Akkuladung + Einspeisung
```

Aktueller Zeitpunkt: 09.11.2026, 12:00 Uhr Europe/Berlin.
6,20 kW PV decken 0,85 kW Haus, 0,50 kW Wärmepumpe, 3,45 kW Auto und
1,40 kW Speicherladung; der Netto-Netzfluss beträgt 0 kW.
Das Auto lädt dabei einphasig mit 15 A bei angenommenen 230 V.

Die SoC-Verläufe entstehen durch Integration der Lade-/Entladeleistung bei
11,059 kWh Speicherkapazität und 77 kWh Fahrzeugkapazität. Berücksichtigt werden
95 % Lade- und Entladewirkungsgrad des Speichers sowie 90 % Ladewirkungsgrad des
Autos. Verluste werden bei der gespeicherten Energie berücksichtigt, nicht als
zusätzliche Verbraucher im AC-Bus doppelt gezählt. Das geparkte Fahrzeug hat in
diesem Beispiel keinen Fahrverbrauch und erreicht sein 70-%-Ziel vor der Abfahrt.

Die Tagesbilanzen werden ab lokaler Mitternacht bis zum Aufnahmezeitpunkt aus
denselben Leistungen integriert. Für die Monats- und Jahresbilanz sind Daten vom
8. November, 12:00 Uhr, bis 9. November, 12:00 Uhr vorhanden; die übrigen Tage sind
keine als null angenommenen Messwerte. Kosten nutzen den zeitabhängigen Netzpreis,
0,082 €/kWh PV-Opportunitätskosten und einen gewichteten Kostenbestand des Speichers
einschließlich Umwandlungsverlusten. Gleichzeitige Quellen werden proportional
auf Verbraucher verteilt; dies ist eine Modellannahme, keine gemessene Zuordnung.

Die Tests in `tests/demo_data.test.cjs` prüfen Leistungsbilanz, SoC-Änderungen,
Kapazitäts-/Leistungsgrenzen, Tagesintegrale, Kosten-/Quellensummen sowie das
Ladeziel und die Übereinstimmung der Modi mit dem Ladeverlauf:

```sh
node --test tests/demo_data.test.cjs
```


Der vor dem gezeigten Verlauf vorhandene Akkuinhalt wird als Netzladung zu
24 ct/kWh AC-Eingangspreis angesetzt. Seine gespeicherte Energie enthält bereits
die Ladekosten einschließlich 95 % Ladewirkungsgrad; bei Abgabe kommen die
Entladeverluste hinzu. Ein willkürlicher Startpreis von 14 ct/kWh wird nicht verwendet.

## Tarifbeispiele

Die Einstellungen zeigen drei aufeinanderfolgende Einträge, jeweils brutto:

- Ab 1. Oktober: 17,57 € pro Monat und dynamischer Netzpreis.
- Ab 1. November: 0,585616438356 € pro Tag und dynamischer Netzpreis.
- Ab 1. Dezember: 0,6001234567 € pro Tag und fester Netzpreis von 29,99 ct/kWh.

Der Dezembertarif liegt nach dem simulierten Aufnahmezeitpunkt und beeinflusst
die Novemberbilanz nicht. Dort werden zwei erfasste Kalendertage mit der
Novembergebühr berechnet; die Tarifanzeige rundet auf 0,585616 €/Tag. Im Eingabefeld
bleiben die zusätzlichen Nachkommastellen sichtbar. Die Beispiele sind keine
Preisangaben eines Anbieters.
