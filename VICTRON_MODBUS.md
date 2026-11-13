# Victron GX direkt über Modbus TCP

Das Plugin **Victron GX direct Modbus TCP** (`victron_modbus`) verbindet sich lokal
mit dem GX-Gerät. Es benötigt keine zusätzliche Victron-HA-Integration, MQTT-
Verbindung, VRM-Anmeldung oder HA-Sensoren. Bestehende HA-/HACS-Plugins bleiben
unverändert verfügbar. Die synchronen Modbus-Abfragen laufen im HA-Executor.

## Voraussetzungen und Einrichtung

1. Venus OS **3.50 oder neuer**, GX mit Systemdienst und unterstützten Registern.
   Am GX unter **Einstellungen → Dienste → Modbus TCP** den Dienst aktivieren.
   Nur im vertrauenswürdigen lokalen Netz verwenden; keine Internetfreigabe.
2. Unter **Inbetriebnahme → Geräte → Gerät hinzufügen → Speicher/Hybrid-Wechselrichter**
   das Plugin wählen. GX-IP/Hostname und Port (Standard 502) eintragen.
   Systemmessungen und ESS verwenden fest **Unit-ID 100**; die einzelnen
   Wechselrichter-/Batterie-Unit-IDs müssen nicht eingegeben werden.
3. **Phasen:** eine oder drei, passend zur gesamten Anlage. Nur vorhandene
   PV-Quellen einschalten: DC-PV ist vorbelegt, AC-PV am Eingang und Ausgang
   werden separat aktiviert. Ohne PV alle drei Quellen abschalten.
   Die Werte sind Leistungen in W, keine täglichen Energiezähler.
4. Kapazität und maximale Lade-/Entladeleistung der gesamten GX-Anlage eintragen.
   Für Netz und optional direkten Hausverbrauch den Eintrag als **Netzquelle**
   markieren. Allgemeine Quellsensoren dürfen leer bleiben; konfigurierte
   allgemeine Sensoren haben Vorrang.
5. Zuerst lesend prüfen. **Enable ESS Mode 2 control** bleibt standardmäßig aus.

Eine GX-Anlage wird einschließlich intern geregelter Batteriemodule nur **einmal**
angelegt. Ebenso PV-Leistung nicht zusätzlich über Geräte erfassen, die das GX
bereits in seine Summe einbezieht. Getrennte GX-Anlagen dürfen eigene Geräte sein;
jede braucht eine passende lokale Netzmessung für ihren ESS-Regelkreis. Die
übergreifende EOS-Planung bleibt eine gemeinsame Speicher-Näherung.

## ESS-Steuerung einschalten

Vorausgesetzt werden eingerichtetes ESS, **aktives DVCC**, funktionierende
Netzmessung und Netzbetrieb. DVCC wird vom Plugin nicht eingeschaltet und kann
über die verwendeten Register nicht unabhängig verifiziert werden. Die Freigabe
bestätigt daher, dass DVCC am GX geprüft wurde. Dynamic ESS und andere Regler für
dieselben Stellwerte abschalten. Das Plugin prüft Dynamic-ESS-Modus 5423 = 0,
ESS/Hub4-Modus 2902 = 1 oder 2 und optimierte BatteryLife-Zustände; es ändert
diese Einstellungen nicht und wechselt nicht in Mode 3.

- `max_charge_current`: maximaler systemweiter DVCC-Ladestrom in **A DC**.
- `max_discharge_power`: zulässige Entladeleistung in **W**, in 10-W-Schritten.
- `release_setpoint`: Netzsollwert bei Rückgabe, Standard **50 W Bezug**.
- `release_charge_current`: expliziter nativer Ladestrom bei Rückgabe, ganze A;
  `-1` nur bewusst verwenden, dies hebt die DVCC-Strombegrenzung auf.
- `release_discharge_power`: explizite **endliche** native Entladegrenze bei
  Rückgabe, W in 10-W-Schritten. `-1` wird hier abgelehnt, weil das ältere Register
  2704 den Wert mit Faktor 0,1 nicht eindeutig als -1 W übertragen kann.

Die beiden Rückgabegrenzen müssen vor der Steuerungsfreigabe gesetzt werden.
Sie gelten auch nach Neustarts, ohne gespeicherte frühere Prozesszustände.
Die Freigabe `grid_discharge_supported` erlaubt zusätzlich erzwungene Einspeisung.

Das Plugin liest vor jedem Regelbefehl erneut Messwerte. Ein Abfrageblock darf
höchstens zehn Sekunden dauern. Ungültige Messwerte, unerwartete Firmware,
fehlender Netzbetrieb oder unpassende ESS-Zustände verhindern neue Befehle.
Jeder geänderte Stellwert wird durch Modbus-Rücklesen bestätigt; ein Fehler stoppt
die weiteren Befehle. Eine gescheiterte Rückgabe bleibt als Fehler sichtbar.
Die Rückgabe benötigt keine Akku-Leistungsmessung, prüft aber weiterhin GX und
ESS/Dynamic ESS, damit fremde Regelmodi nicht überschrieben werden.

Der flüchtige Netzsollwert 2716/2717 vermeidet wiederholte persistente Writes
auf die alten Sollwertregister. Bei einem Kommunikationsausfall gibt es über
diesen Weg jedoch **keinen garantierten automatischen Timeout** der Stellwerte.
Sie können am GX bestehen bleiben; Geräte-/BMS-Schutz und eine passende lokale
Ausfallstrategie sind weiter erforderlich.

## Messungen, Register und Grenzen

| Funktion | Register (Unit-ID 100, direkte Adressen) | Format |
| --- | --- | --- |
| GX-Identität / Firmware | 800–805 / 834 | MAC-Seriennummer / hexadezimale Version |
| Akkuspannung / DC-Leistung / SoC | 840 / 842 / 843 | 0,1 V / signed W, positiv Laden / % |
| DC-PV | 850 | W |
| AC-PV Ausgang / Eingang | 808–810 / 811–813 | W je konfigurierter Phase |
| Gesamter AC-Verbrauch | 817–819 | W je konfigurierter Phase, einschließlich Auto/Wärmepumpe |
| Netzleistung | 820–822 | signed W je Phase, positiv Bezug |
| Aktiver Eingang | 826 | 1 = Netz, vor Steuerbefehlen erforderlich |
| Entladegrenze / DVCC-Ladestrom | 2704 / 2705 | W = signed Register × 10 / ganze A |
| Flüchtiger Netzsollwert | 2716–2717 | signed 32-Bit W, höchstes Wort zuerst |

Die verwendeten Leistungs-Messregister sind 16 Bit: Akkuleistung und Netzleistung
je Phase müssen strikt zwischen −32768 und 32766 W liegen; PV/Verbrauch je Phase
unter 65534 W. Auch die vom GX verwendete obere Sättigungsgrenze max−1 wird
als ungültig zurückgewiesen. Für größere Anlagen
oder weitere Quellen (z. B. Generator-PV) zunächst die HA-/MQTT-Anbindung verwenden.
Das Plugin fällt bei fehlenden Registern nicht auf erfundene Nullwerte zurück.
Venus kann allerdings selbst fehlende D-Bus-Werte als 0 bereitstellen; Modbus
liefert dazu keinen Messzeitstempel oder vollständigen Qualitätsstatus. Ein
erfolgreicher Read beweist deshalb nicht die Aktualität jedes internen Sensors.

DC-Akkuleistung wird mit `charge_efficiency` und `discharge_efficiency` (Standard
je 0,95) auf AC angenähert. A-Ladebudgets werden mit aktueller Spannung umgerechnet
und abgerundet. DVCC begrenzt auch Solarladung. DC-PV, Verbraucher im DC-System und
wechselnde Verluste begrenzen die Genauigkeit der AC-Näherung. BMS, BatteryLife und
Geräte begrenzen weiterhin die real erreichbare Leistung; bestätigte Registerwerte
garantieren keine tatsächlich erreichte Lade-/Entladeleistung.

Verhalten, Fehler und Rückgaben sind gegen einen lokalen Modbus-TCP-Testserver
getestet. Ein Test an echter Victron-Hardware steht aus.

Quellen: [GX Modbus-Handbuch](https://www.victronenergy.com/live/ccgx:modbustcp_faq),
[ESS Mode 2/3](https://www.victronenergy.com/live/ess:ess_mode_2_and_3),
[Registerliste 3.81](https://www.victronenergy.com/upload/documents/CCGX-Modbus-TCP-register-list-3.81.xlsx),
[Victron-Serverimplementierung](https://github.com/victronenergy/dbus_modbustcp).

## Fehlersuche bei „Messwerte unvollständig“

Bei drei Phasen mit einem Fronius Symo am **AC-Ausgang** des MultiPlus-II:
`phases = 3`, `ac_pv_output_enabled = true`, `ac_pv_input_enabled = false`.
Ohne zusätzliche DC-Solarladeregler auch `dc_pv_enabled = false` setzen.
Die vorbelegte DC-PV-Quelle passt nicht zu einer ausschließlich AC-gekoppelten
PV-Anlage. Bei weiteren tatsächlich vorhandenen PV-Quellen diese zusätzlich
aktivieren. Das Plugin errät die Topologie nicht.

Ab Version 0.17.3 enthalten die heruntergeladenen HA-Diagnosedaten unter
`devices` die Geräte in konfigurierter Reihenfolge (Nummer statt privatem Namen),
Plugin, Verfügbarkeit und Lesefehlerklasse. Bei Victron enthält `configuration`
Phasenzahl, ausgewählte Messquellen und Steuerungsfreigabe. `failure` nennt den
Leseabschnitt, Unit-ID, Registeradresse, Anzahl und gegebenenfalls den numerischen
Modbus-Ausnahmecode. Nach erfolgreichem Lesen wird der Fehler gelöscht. Host,
Port, Seriennummer, Kapazität, Messwerte und rohe Fehlermeldungen fehlen bewusst.

- `identity` / 800: Verbindung, aktivierten Modbus-TCP-Dienst und Systemdienst
  auf Unit-ID 100 prüfen. `firmware` / 834: Venus OS ab 3.50 erforderlich.
- `battery` / 840–843: Akkuspannung, Leistung und SoC am GX prüfen.
- `dc_pv` / 850, `ac_pv_input` / 811–813, `ac_pv_output` / 808–810:
  eingeschaltete Quellen mit der tatsächlichen Installation abgleichen.
- `grid` / 820–822 oder `consumption` / 817–819: Phasenauswahl und die am GX
  verfügbaren Netz-/Verbrauchsmessungen prüfen.
- `snapshot_timeout`: Der gesamte Lesevorgang dauerte länger als zehn Sekunden.

Code 2 bedeutet eine ungültige Registeradresse, Code 10 einen nicht verfügbaren
Gateway-Pfad und Code 11 ein nicht gefundenes Zielgerät. Den letzten Fehler am
GX unter **Einstellungen → Dienste → Modbus TCP** ergänzend prüfen.
Ein fehlgeschlagener ausgewählter Messkanal verwirft weiterhin den gesamten
Gerätesnapshot; fehlende Werte werden nicht als null oder als alte Messung genutzt.
`AC —` ist bei diesem Plugin auch im Erfolgsfall möglich: Es liefert keine
separate Wechselrichter-AC-Leistung (`inverter_ac`).

Vier Steuerfunktionen mit „Nein“ sind bei ausgeschaltetem `control_enabled`
erwartet. Das Einschalten der ESS-Steuerung repariert keine fehlenden Messungen.
`vehicle_limits` betrifft die Übernahme der Fahrzeug-Ladegrenzen durch EOS;
dieser Fehler ist getrennt von der Victron-Leseverbindung zu untersuchen.

## English setup

Enable Modbus TCP on a GX running Venus OS 3.50 or newer. Add **Victron GX direct
Modbus TCP** as one storage device in EOS; configure its host/port, one or three
phases and only the installed DC/AC PV sources. System/ESS Unit-ID is fixed at 100.
No HA sensor entities or other Victron integration are required. Mark the device
as the common grid source to expose grid/consumption. General sensors take priority.
Do not count a GX installation or its PV sources twice.

Read-only is the default. Control requires optimized ESS Mode 2, DVCC enabled,
grid-connected operation, working grid measurements and Dynamic ESS disabled.
DVCC enablement cannot be independently verified through these registers; check
it on the GX before enabling control. Other controllers must not write the same
settings. No ESS mode or protection settings are changed.

Configure maximum charge current (A DC), inverter power (W, multiples of 10), and
explicit native release values. Release grid setpoint defaults to 50 W import.
Release charge current permits -1 (unlimited); release inverter power must be
finite and nonnegative because legacy register 2704 has a 0.1 scale factor.
Restore values work after restart. Forced export needs separate opt-in. Writes
require readback confirmation. Snapshot duration is bounded to 10 seconds; failed
reads, invalid values or wrong operating modes prevent new commands.

Telemetry uses 16-bit registers: battery/grid power per phase must be strictly
inside −32768…32766 W, PV/consumption below 65534 W per phase. Endpoints, including
the GX's max−1 saturation value, are rejected.
Larger systems should use the HA/MQTT plugins. Missing requests are errors, but
Venus may itself return 0 for missing internal data: Modbus has no full freshness
or quality information. Efficiencies (default 0.95) approximate DC/AC conversion.
DVCC also limits solar charging; BMS and hardware can constrain achieved power.
Communication loss does not guarantee automatic expiry of the settings. Retain
device-side protections and a suitable local failure strategy. Tests use a local
protocol emulator; real-hardware validation remains outstanding.

### Troubleshooting incomplete measurements

For a three-phase MultiPlus-II installation with a Fronius Symo on **AC out**,
select three phases and enable AC-output PV. Disable AC-input PV unless installed;
disable the default DC-PV source if there are no DC solar chargers. Enable any
additional sources only when physically present.

Since 0.17.3, downloaded HA diagnostics include `devices` in configuration order,
using a number instead of the private device name. They report the plugin,
availability and read error type. Victron also reports phase/source/control
selection under `configuration` and the failed stage, unit, register range and
optional numeric Modbus exception code under `failure`. A successful read clears
the error. Hosts, ports, serials, capacities, measurements and raw errors are
excluded. Stages identify identity (800), firmware (834), battery (840–843), DC PV
(850), AC-input PV (811–813), AC-output PV (808–810), grid (820–822), consumption
(817–819), or a snapshot exceeding ten seconds (`snapshot_timeout`).

Check the GX's last Modbus TCP error as well: code 2 means an illegal register
address, 10 an unavailable gateway path and 11 an unknown target device. Any failed
selected channel still invalidates the device snapshot; missing data is never
replaced with zero or a cached reading. `AC —` can appear even on successful
reads because this plugin does not provide separate `inverter_ac` power.
Control capabilities set to “No” are expected in read-only mode; enabling control
does not repair telemetry. `vehicle_limits` concerns EOS vehicle charging limits
and must be investigated separately.
