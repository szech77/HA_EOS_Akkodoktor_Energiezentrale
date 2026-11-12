# Victron Venus MQTT / HACS

## Einrichtung

Das Speicher-Plugin **Victron Venus MQTT / HACS (Home Assistant)** (`victron_ha`)
verwendet Entitäten der [HACS-Integration von tomer-w](https://github.com/tomer-w/ha-victron-mqtt).
Diese Integration samt MQTT-Verbindung zu Venus OS muss bereits funktionieren.
Das Plugin benötigt weder einen weiteren MQTT-Zugang noch VRM-Zugangsdaten oder
zusätzliche Python-Abhängigkeiten. Es ist kein Adapter für die offizielle
Integration „Victron GX“; andere HACS-Projekte sind nicht geprüft.

Unter **Inbetriebnahme → Geräte → Gerät hinzufügen → Speicher/Hybrid-Wechselrichter**
das Plugin auswählen. Kapazität und zulässige Lade-/Entladeleistung des gesamten
GX-Systems eintragen. Zunächst bleibt **Enable ESS Mode 2 control** ausgeschaltet:
Messwerte werden eingelesen, Steuerungsfähigkeiten ausdrücklich nicht gemeldet.
Entitäts-IDs hängen von der HACS-Konfiguration ab; die folgende Tabelle beschreibt
die auszuwählenden Funktionen, keine festen Entity-IDs.

| Plugin-Feld | Victron-Messung / HACS-Funktion | Einheit / Bedeutung |
| --- | --- | --- |
| `soc` | System battery state of charge | %, erforderlich |
| `battery_power` | System `/Dc/Battery/Power` | W/kW, positiv beim Laden, negativ beim Entladen |
| `battery_voltage` | System battery voltage | V, bei Ladebegrenzung in A erforderlich |
| `grid` | Total grid power | W/kW, positiv bei Bezug, negativ bei Einspeisung |
| `solar` | Total PV power | W/kW, optional; gesamte AC- und DC-PV-Leistung |
| `house_total` | Total AC consumption | W/kW, optional; einschließlich Auto/Wärmepumpe |
| `inverter_ac` | Total signed inverter AC output | W/kW, optional; positiv bei Erzeugung |

Gesamtwerte auswählen, keine einzelne Phase und keine Energiezähler in kWh.
PV weder innerhalb der Anlage noch über weitere Geräte doppelt zählen. Eine
GX-Anlage mit mehreren intern geregelten Batteriemodulen **einmal** konfigurieren:
DVCC-Grenzen und Systemmessungen betreffen die ganze Anlage. Getrennte GX-Systeme
können getrennte Geräte sein, benötigen aber eigene Entitäten und eine passende
lokale Netzmessung für ihren ESS-Regelkreis. EOS plant mehrere Batterien weiterhin
als gemeinsame, angenäherte Speicherressource.

Für den gemeinsamen Netzanschluss und direkten Hausverbrauch das Gerät als
**Netzquelle** markieren. Allgemeine Quellsensoren dürfen dann leer bleiben;
konfigurierte allgemeine Sensoren haben weiterhin Vorrang. Ein ausgewählter
direkter Hausverbrauch hat Vorrang vor der rechnerischen AC-Bilanz. Bei Ausfall
bleibt er unbekannt. Ohne direkten Hausverbrauch benötigt die Ableitung wie bisher
vollständige AC-Leistungen aller Geräte und Netzleistung.

## Optionale ESS-Steuerung

Voraussetzungen: Victron ESS im **Mode 2**, passende Firmware, schreibbare HACS-
`number`-Entitäten und korrekt eingerichteter Netzzähler. Der Adapter wechselt
nicht in Mode 3 oder „External control“. BMS-, DVCC- und Gerätegrenzen bleiben
maßgeblich. Dynamic ESS und konkurrierende Regler für dieselben Stellwerte abschalten.

| Plugin-Feld | HACS-Funktion / Victron-Pfad |
| --- | --- |
| `ess_mode` | ESS **user mode** (`system_ess_batterylife_state`), nicht Hub4/`system_ess_mode` |
| `grid_setpoint` | AC grid power setpoint, `/Settings/CGwacs/AcPowerSetPoint`, W |
| `charge_limit` | Max charge current, `/Settings/SystemSetup/MaxChargeCurrent`, A; alternativ Max charge power, `/Settings/CGwacs/MaxChargePower`, W/kW |
| `discharge_limit` | Max inverter power, `/Settings/CGwacs/MaxDischargePower`, W/kW |

`ess_mode_option` muss zum rohen Select-Zustand passen:
`optimized_no_battery_life` oder `optimized_battery_life`. Das Plugin prüft den
Zustand vor Befehlen und verändert ihn nicht. BatteryLife kann EOS zusätzlich
begrenzen. Fehlen Stellwerte bei älterer Firmware/HACS, nur lesend betreiben.

Vor Aktivierung drei explizite Rückgabewerte setzen:

- `release_setpoint`: Netzsollwert in W, Vorgabe 50 W Bezug.
- `release_charge_limit`: zulässiger nativer Ladewert in der **Einheit der
  ausgewählten Entität**, beispielsweise 60 A, bei einer W-Entität entsprechend W.
- `release_discharge_limit`: zulässiger nativer Entladewert in W bzw. kW.

Diese Werte werden beim Zurückgeben an Victron bestätigt gesetzt, auch nach
Neustarts. Frühere Prozessdaten werden nicht vorausgesetzt. `-1` bedeutet bei
passenden Victron-Entitäten unbegrenzt; nur bewusst verwenden. Werte müssen zu
Min/Max und Schrittweite der Entitäten passen. Danach `control_enabled` einschalten.
Erzwungene Netzeinspeisung separat mit `grid_discharge_supported` freigeben.

EOS-Budgets und individueller SoC begrenzen Laden/Entladen. A-Ladegrenzen werden
mit frischer Batteriespannung umgerechnet und abgerundet. DVCC-Ladestrom begrenzt
auch Solar-Laderegler; ein AC-Ladebudget ist daher nicht immer gleichbedeutend mit
diesem DC-Strom. Der Netzsollwert berücksichtigt Netzleistung und aktuellen
Akku-Leistungsfluss. Jeder Schreibbefehl benötigt eine HA-Zustandsbestätigung,
bevor der nächste erfolgt. Unbestätigte Befehle und Rückgaben bleiben Fehler.

DC-Leistung wird mit `charge_efficiency` und `discharge_efficiency` (jeweils
Standard 0,95) auf AC angenähert. Bei DC-gekoppelter PV und wechselnden Verlusten
bleibt die Energiebilanz eine Näherung. Bestätigte Sollwerte garantieren keine
physisch erreichte Leistung: BMS, Solarertrag, BatteryLife und Geräte begrenzen sie.

Zeitstempel bleiben erhalten: SoC höchstens 360 s, Akku-Leistung/Spannung 120 s,
ausgewählte Netz-/PV-/Hausmessungen hier 45 s alt. MQTT muss auch unveränderte Werte
regelmäßig neu melden. Retained-Zustände ersetzen keine aktuellen Berichte. Bei
veralteten/fehlenden Messwerten werden neue Steuerbefehle zurückgestellt; ein
MQTT-Ausfall kann auch die bestätigte Rückgabe verhindern. Geräteinterne Schutz-
und Watchdog-Funktionen bleiben erforderlich.

Der lokale Verlauf speichert normalisierte Lade-/Entladeleistungen. Ein alter
Influx-Verlauf mit einem vorzeichenbehafteten DC-Sensor ist keine historische
Quelle für zwei unabhängige AC-Leistungssensoren. Verhalten und HA-Konfiguration
sind mit simulierten Entitäten getestet; ein realer Hardwaretest steht aus.

Quellen: [HACS-Integration](https://github.com/tomer-w/ha-victron-mqtt),
[MQTT-Entitätsdefinitionen](https://github.com/tomer-w/victron_mqtt),
[Victron ESS Mode 2/3](https://www.victronenergy.com/live/ess:ess_mode_2_and_3).

## English setup notes

Install and configure tomer-w's Venus MQTT HACS integration first, then add
**Victron Venus MQTT / HACS (Home Assistant)** as a storage device. Select the
actual system SoC (%) and signed DC battery power (+ charge) entities. Optional
grid, PV and AC consumption entities replace general source sensors. Select
totals, avoid duplicate PV accounting, and mark the GX device as the common grid
source to expose its grid/direct consumption readings. General sensors take priority.

Read-only is the default. ESS Mode 2 control requires fresh grid power, the
optimized ESS user-mode select, AC grid setpoint (W), charge limit (A or W/kW),
and inverter power limit (W/kW). A-based charging also requires fresh voltage.
Match `ess_mode_option` to the raw `optimized_no_battery_life` or
`optimized_battery_life` state. The adapter never changes ESS mode or enters Mode 3.
Disable competing controllers; older firmware may lack required controls.

Explicitly configure native charge/discharge limits to restore on release, in
each number entity's own unit, before enabling control. The release grid setpoint
defaults to 50 W import. All values must match entity bounds and steps. Restoration
also works after restart. Each write requires confirmation; stale telemetry blocks
new commands. Forced export requires a separate opt-in. DVCC also limits solar
charging. BMS, BatteryLife and hardware can constrain physically achieved power.

DC/AC efficiencies default to 0.95; powers are estimates, especially with DC-coupled
PV. SoC expires after 360 s, battery power/voltage after 120 s and grid/PV/consumption
after 45 s. Ensure MQTT refreshes unchanged values. A failed link may prevent
confirmed release; retain device-side protections. Configure one GX installation
once, including its internal battery modules. Separate GX installations need their
own entities and suitable local ESS meter boundaries. EOS still pools batteries
as one approximate planning resource. Tests use simulated entities; physical
hardware validation is outstanding.
