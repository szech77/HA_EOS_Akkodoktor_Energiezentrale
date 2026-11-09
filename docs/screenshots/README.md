# UI-Screenshots

Echte Browseraufnahmen des integrierten Panels, erstellt mit synthetischen
Beispieldaten und deutschem Sprachpaket. Es werden keine privaten Messwerte,
Serveradressen oder Zugangsdaten gezeigt. Die Screenshots bilden den Stand der
Oberfläche vom 9. November 2026 ab und sind keine Entwurfsgrafiken.

- `overview.png`: Desktop-Übersicht einschließlich Tagesverbrauch und Kosten.
- `battery.png`: Speicherverlauf, EOS-Modi und Prognosen.
- `vehicle.png`: Fahrzeugplanung und Ladeverlauf.
- `solar.png`: PV-Ertrag und Prognosen für drei Tage.
- `mobile.png`: oberer Bereich der Übersicht bei 390 Pixeln Breite.

Bei Änderungen am Layout oder an sichtbaren Funktionen die betroffenen Aufnahmen
aktualisieren. Weiterhin ausschließlich Beispieldaten verwenden und die deutsche
Sprache sowie die Aufnahme ohne Browser- oder Home-Assistant-Seitenleiste beibehalten.


## Plausibilität der Beispieldaten

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
denselben Leistungen integriert. Kosten nutzen den zeitabhängigen Netzpreis,
0,08 €/kWh PV-Opportunitätskosten und einen gewichteten Kostenbestand des Speichers
einschließlich Umwandlungsverlusten. Gleichzeitige Quellen werden proportional
auf Verbraucher verteilt; dies ist eine Modellannahme, keine gemessene Zuordnung.

Die Tests in `tests/demo_data.test.cjs` prüfen Leistungsbilanz, SoC-Änderungen,
Kapazitäts-/Leistungsgrenzen, Tagesintegrale, Kosten-/Quellensummen sowie das
Ladeziel und die Übereinstimmung der Modi mit dem Ladeverlauf:

```sh
node --test tests/demo_data.test.cjs
```
