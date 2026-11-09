# Hardware-Plugins

Die Energiezentrale entdeckt lokale Plugins beim Start aus
`custom_components/eos_energiezentrale/energy/plugins/`. Ein Registry-Eintrag im
Controller ist nicht nötig. Änderungen an installiertem Python-Code werden nach
Neustart von Home Assistant wirksam. Fronius, NRGkick und die beiden generischen
HA-Plugins nutzen denselben Vertrag. Vorhandene IDs `fronius`, `nrgkick` und `none`
bleiben erhalten.

## Einrichtung in Home Assistant

Unter **Einstellungen → Geräte & Dienste → EOS Energiezentrale → Konfigurieren**:

1. **Hardware:** Speicher-/Wechselrichter-Plugin und optionales Wallbox-Plugin auswählen.
2. Im folgenden Schritt erscheinen die Felder des ausgewählten Plugins, einschließlich
   Entitätsauswahl, Auswahllisten und Schaltern. Die Parameter werden nicht zentral hartcodiert.
3. Speichern. Bereits konfigurierte Fronius-/NRGkick-Entitäten bleiben übernommen.

Für weitere Fahrzeuge/Wallboxen: **Fahrzeuge und Wallboxen → Hinzufügen → Plugin auswählen
→ Fahrzeugdaten und Plugin-Felder ausfüllen → bestätigen**. Für jede zusätzliche
Wallbox wiederholen. Jede Wallbox benötigt eine eigene stabile Fahrzeug-ID, eine eigene
EOS-Ressource und eigene Steuerungs- und Leistungsmessentitäten. Bis zu acht Paare
werden unterstützt. Bearbeiten und Entfernen erfolgen im gleichen Verwaltungsmenü.
Der Hausspeicher bleibt eine gemeinsame Ressource. Sobald Fahrzeugprofile angelegt sind,
werden deren Wallboxen ausschließlich im Fahrzeugmenü bearbeitet; Hardware zeigt dann
nur die gemeinsame Speicherkonfiguration.

## Generische HA-Wallbox

Das Plugin `generic` bindet native HA-Entitäten oder Helfer an:

| Feld | Zulässige Entitäten / Bedeutung |
| --- | --- |
| `power` | `sensor`, tatsächliche Leistung in W oder kW. |
| `status` | Optionaler `sensor`/`input_select`; `status_map` bildet Gerätestatus auf den Vertrag ab. |
| `plugged` | Optionaler `binary_sensor`/`input_boolean`; an/aus. Status oder Steckerkennung ist erforderlich. |
| `enable` | `switch`/`input_boolean`, Ladefreigabe. |
| `current` | `number`/`input_number`, Sollstrom in A mit `step` und `max`; z. B. 0,1 A. |
| `phases` | Steuerung über `number`/`input_number`/`select`/`input_select`. Ohne Umschaltung ist auch ein `sensor` möglich. Werte 1 oder 3. |
| `phase_feedback` | Tatsächliche Phasenanzahl aus `sensor`/`number`/`select`. Bei Phasen-Helfern und aktivierter Umschaltung erforderlich. |
| `phase_switching` | Gibt die tatsächlich vorhandene Fähigkeit an. Bei `false` fordert der Regler keinen Phasenwechsel an. |
| `status_map` | JSON-Objekt: gemeldeter Status → `connected`, `charging`, `wakeup`, `disconnected`, `unknown`, `unavailable` oder `error`. Groß-/Kleinschreibung der Eingänge wird normalisiert. |

Bei reiner Steckerkennung wird `charging` aus Ladefreigabe und gemessener Leistung
abgeleitet. Bei Helfern müssen eigene HA-Automationen die Befehle zur Hardware
weitergeben. Die Messsensoren müssen echte Rückmeldungen liefern. Die Rückmeldung
eines Helfers bestätigt nur dessen Zustand, nicht den Zustand der Hardware.
Der Phasenwechsel wartet weiterhin auf deaktivierte Ladung, neue Nullleistungsmessungen
und die tatsächliche Rückmeldung der Phasenanzahl. Eine Einstellung ohne Umschaltfähigkeit
bleibt bei der vorhandenen Phasenanzahl, auch wenn die globale Phasenautomatik aktiviert ist.

Beispiel für eine Wallbox mit fester Phasenanzahl:

```json
{
  "power": "sensor.meine_wallbox_leistung",
  "plugged": "binary_sensor.meine_wallbox_eingesteckt",
  "enable": "input_boolean.eos_wallbox_laden",
  "current": "input_number.eos_wallbox_strom",
  "phases": "sensor.meine_wallbox_phasen",
  "phase_switching": false
}
```

## Generischer HA-Speicher / Wechselrichter

| Feld | Bedeutung |
| --- | --- |
| `soc` / `soc_scale` | SoC-Sensor; Prozent 0–100 oder Faktor 0–1. |
| `charge_power` / `discharge_power` | Separate, nichtnegative Sensorwerte in W/kW. |
| `mode` | `select`/`input_select` für den normalisierten Betriebsmodus. |
| `charge_limit` / `discharge_limit` | `number`/`input_number` in W/kW; `min<=0`, `max>0`, `step>0`. |
| `grid_charge_supported` | Fähigkeit zum erzwungenen Laden aus dem Netz. |
| `grid_discharge_supported` | Fähigkeit zum erzwungenen Einspeisen aus dem Akku; standardmäßig aus. Die globale Exportfreigabe bleibt zusätzlich erforderlich. |
| `mode_map` | Normalisierter Modus → Option der eigenen HA-Entität. |

Standardmodi sind `auto`, `limits`, `block_discharge`, `grid_charge`, `grid_discharge`.
Die Limits werden vor dem Modus gesetzt. Bei `block_discharge` und `grid_charge` wird
das Entladelimit auf 0 gesetzt. Bei `grid_discharge` wird das Ladelimit auf 0 gesetzt.
`release()` gibt den Modus an `auto` zurück. Die Helfer aus
`examples/generic_hardware_helpers.yaml` können für eigene Automationen verwendet werden.
Es werden keine beliebigen HA-Dienste aus Konfigurationstext ausgeführt.

## Eigenes Plugin entwickeln

Der Vertrag ist in `energy/contracts.py`, die zentrale Prüfung in `energy/sanitiser.py`,
die Erkennung in `energy/plugin_registry.py` definiert. API-Version 1 verlangt:

- Eine konkrete Unterklasse von `BatteryDriver` bzw. `WallboxDriver`.
- `info = PluginInfo(identifier, name, kind, api_version=1)` mit stabiler ID,
  Anzeigename und Art `battery`/`wallbox`.
- Typisierte `BatteryFeatures` bzw. `WallboxFeatures`. Fähigkeiten dürfen konfigurationsabhängig
  im Konstruktor gesetzt werden; es sind echte boolesche Werte erforderlich.
- `configuration`: ein Tupel aus `PluginField`-Deskriptoren. Jeder beschreibt Schlüssel,
  Label, Typ (`entity`, `boolean`, `number`, `choice`, `json`, `text`), Pflichtfeld,
  Standardwert und gegebenenfalls Entitätsdomänen/Auswahlwerte.
- Konstruktor `__init__(self, ha, params)` ohne zusätzliche Argumente.
- Ein `ids`-Mapping mit den kanonischen Entitätsnamen (siehe vorhandene Implementierungen),
  das nach Konstruktion geprüft und schreibgeschützt wird.
- Export `PLUGINS = (MeineImplementierung,)` auf Modulebene.

Speicher implementieren `_read(self, states, now)`, `_apply(self, command, states)`
und `_release(self, states)`. Wallboxen implementieren `_read(self, states, now)`,
`_pause(self, state)`, `_phase(self, phases, state)` und `_charge(self, amps, state)`.
Die öffentlichen Methoden `read`, `apply`, `release`, `pause`, `phase`, `charge`
bleiben dem Vertrag vorbehalten und dürfen nicht überschrieben werden. Sie führen
die zentrale Prüfung aus. `_phase` liefert ausschließlich `bool`, die anderen
Schreiboperationen `None`. Asynchrone oder abweichende Signaturen werden abgewiesen.

`_read` liefert unveränderliche `BatteryReading`- bzw. `WallboxReading`-Werte.
Einheiten sind Prozent, Watt, Ampere, Phasen 1/3 und zeitzonenbehaftete Zeitstempel.
Ungültige, negative oder nicht endliche Messwerte werden als fehlend behandelt,
nicht auf 0 geklemmt. Nicht vertragsgemäße Datentypen führen zu einem Vertragsfehler.
Wallbox-Leistungsmessungen ohne aktuelle Zeitmarke werden nicht zur Regelung verwendet.
Nicht unterstützte Befehle und ungültige Strom-/Leistungsvorgaben werden vor dem
Hardwareaufruf abgewiesen.

Die Erkennung prüft Metadaten, Version, Konfiguration und Methodensignaturen. Defekte
Module oder doppelte IDs werden abgewiesen und in den Integrationsdiagnosen unter
`plugin_errors` ausgewiesen; andere Plugins bleiben verfügbar. Unbekannte Typnamen
werden nicht als Python-Importpfade interpretiert. Es wird nur vertrauenswürdiger,
lokal installierter Python-Code aus dem Plugin-Paket geladen. Ein Plugin läuft im
HA-Prozess; der Sanitiser ist eine Daten-/Vertragsgrenze und keine Sandbox für fremden Code.
