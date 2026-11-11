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

## Fronius GEN24 direkt über Modbus TCP

Das zusätzliche Speicher-Plugin **Fronius GEN24 direct Modbus TCP** (`fronius_modbus`)
liest und schreibt direkt auf dem Wechselrichter. Die bisherige Auswahl `fronius` für
`callifo/fronius_modbus` bleibt bestehen. Keine automatische Umstellung bestehender
Installationen; die neue Auswahl bewusst in der Hardwarekonfiguration vornehmen.

Voraussetzungen am GEN24: Modbus TCP aktivieren (üblicherweise Port 502),
**Wechselrichter-Steuerung über Modbus** zulassen und die Steuerprioritäten passend
setzen. Für Netzladung zusätzlich **Batterieladung aus dem öffentlichen Netz** erlauben.
Nur eine Anwendung darf den Speicher regeln; parallele EOS-/evcc-/HA-Regler deaktivieren.
Es werden GEN24-Geräte mit SunSpec-Modellen 124 und 160 unterstützt, keine RTU-Verbindung
und keine ausschließliche 700er-Modellimplementierung.

| Feld | Bedeutung |
| --- | --- |
| `host` | Lokale IP-Adresse oder Hostname des GEN24; keine URL. |
| `port` | TCP-Port, Standard 502. |
| `unit_id` | Unit-ID, Standard 1 (GEN24-Wechselrichter); keine Broadcast-ID 0. |
| `grid_meter_enabled` | Netzanschlusszähler über den GEN24 lesen, Standard an. Nur für einen tatsächlich am Netzanschlusspunkt installierten Primärzähler verwenden. |
| `grid_meter_unit_id` | Gateway-Unit-ID dieses Zählers, Standard 200. Dies ist nicht die Wechselrichter-ID 1. |
| `grid_meter_invert` | Vorzeichen des Zählers umkehren, Standard aus; im Panel muss Bezug positiv und Einspeisung negativ sein. |
| `grid_discharge_supported` | Erzwungene Netzentladung ausdrücklich erlauben, Standard aus. Die globale Exportfreigabe gilt zusätzlich. |

Beispiel der gespeicherten Plugin-Parameter (die Einrichtung bietet einzelne Felder):

```json
{
  "host": "192.0.2.10",
  "port": 502,
  "unit_id": 1,
  "grid_meter_enabled": true,
  "grid_meter_unit_id": 200,
  "grid_meter_invert": false,
  "grid_discharge_supported": false
}
```

SoC (`ChaState`) wird einschließlich Skalierungsfaktor aus Modell 124 gelesen.
Lade- und Entladeleistung stammen aus `DCW` der Batteriekanäle 3 und 4 in Modell 160;
PV-Kanäle 1 und 2 werden nicht als Batterie ausgewertet. Modelladressen und
Kanalanordnung werden erkannt. Alle drei Werte werden bei jedem Poll neu abgefragt,
ohne gespeicherte Altwerte als aktuelle Messungen auszugeben. Fehlende Kanäle,
nicht implementierte Register oder ungültige Skalierung bleiben unbekannt; echte
Nullwerte bleiben gültig. Verbindungs- und Protokollfehler lösen den bestehenden
Steuerfehlerpfad einschließlich Rückgabeversuch aus.

Für dieses Plugin sind keine zusätzlichen HA-Sensoren, Templates oder
`select`-/`number`-Steuerentitäten erforderlich. Für den Netzanschlusswert unter
**Quellsensoren** die Netzsensor-Auswahl leeren. Ein dort ausgewählter Sensor hat
weiterhin Vorrang. Der am GEN24 angebundene Netzanschlusszähler wird über seine
Gateway-Unit-ID gelesen; SunSpec 201–203 und 211–213 werden erkannt. Fehlt der Zähler
oder ist er unerreichbar, bleibt der Netzwert unbekannt, während die verfügbaren
Speichermesswerte weiter angezeigt werden. Bei deaktivierter Zählerabfrage meldet
das Plugin Netzleistung und abgeleiteten Hausverbrauch nicht als Fähigkeiten.
Die PV-Leistung wird unabhängig davon direkt gelesen. Keine neuen
Python-Abhängigkeiten nötig. Ältere Entwicklungsversionen dieses Plugins mit
Sensorparametern bei der Einrichtung erneut auswählen bzw. die veralteten
`soc`-/`charge_power`-/`discharge_power`-Parameter entfernen.

Die drei allgemeinen Sensorfelder **PV-Leistung**, **Gesamter Hausverbrauch** und
**Netzleistung** können bei diesem Plugin gemeinsam leer bleiben:

| Leeres Sensorfeld | Wert aus `fronius_modbus` |
| --- | --- |
| `pv_entity` | Summe der vorhandenen PV-Kanäle MPP1/MPP2 aus SunSpec 160; aktuelle DC-Leistung in W. Dies ist kein kumulativer kWh-Zähler. |
| `grid_entity` | AC-Wirkleistung des konfigurierten Primärzählers; Bezug positiv, Einspeisung negativ. |
| `house_entity` | Gesamter Hausverbrauch einschließlich Fahrzeugen und Wärmepumpe: AC-Ausgangsleistung des GEN24 plus vorzeichenbehaftete Netzleistung. SunSpec 101–103 und 111–113 werden unterstützt. |

Für Netz- und Hausleistung muss die Zählerabfrage aktiviert und der Primärzähler
am Netzanschlusspunkt vorhanden sein. Die Hausbilanz setzt voraus, dass die
AC-Leistung dieses GEN24 alle Erzeuger am Messpunkt erfasst. Bei weiteren, nicht
erfassten Wechselrichtern oder Erzeugern einen eigenen Hausverbrauchssensor wählen;
dieser hat weiterhin Vorrang. Akkuentladung und Netzladung sind bereits in der
AC-Leistung enthalten und werden nicht nochmals addiert oder subtrahiert.
Fehlende Teilmessungen und negative, widersprüchliche Hausbilanzen bleiben unbekannt.

Fronius meldet PV- und Batteriekanäle als **DC-Leistung**. Die Werte werden ohne
unbelegte Umrechnung in W übernommen. In einer AC-basierten Hausbilanz können
Umwandlungsverluste deshalb Abweichungen der Quellenzuordnung und Kostenbewertung
verursachen; größere Bilanzabweichungen bleiben gemäß Bilanzmodell unbekannt.
Der Hausverbrauch selbst wird aus den AC-Messwerten berechnet.
Ältere Influx-Historien der bisherigen externen Speichersensoren werden diesem
Plugin ohne deren Entitätszuordnung nicht automatisch zugerechnet. Die interne
Aufzeichnung der neuen Live-Messungen läuft regulär weiter.

Der Treiber erkennt SunSpec-Modell 124 dynamisch und prüft den Hersteller. Er liest
Referenzleistung und Skalierungsfaktoren vom Gerät. Lade-/Entladegrenzen werden
gemeinsam geschrieben und zurückgelesen; eine Registerbestätigung bestätigt den
Sollwert, nicht das Erreichen der gewünschten Leistung. Geräteschutz und Prioritäten
können die tatsächliche Leistung begrenzen. Eine fehlerhafte oder ausbleibende
Rückbestätigung wird als Steuerfehler behandelt.

Jeder Steueraufruf erneuert `InOutWRte_RvrtTms` auf 300 Sekunden. Ohne weitere
Aufrufe laufen die externen Leistungsgrenzen am Wechselrichter aus. Firmware, die
diesen Wert nicht schreiben und zurückbestätigen kann, wird nicht ohne Zeitbegrenzung
weitergesteuert. Bei normaler Rückgabe wird `StorCtl_Mod=0` bestätigt und die zuvor
gelesene Netzladefreigabe wiederhergestellt. Nach einem Prozessabbruch wird bei der
nächsten Rückgabe die externe Leistungssteuerung deaktiviert; eine vorherige
Netzladefreigabe kann dann mangels ursprünglichem Zustand nicht rekonstruiert werden.
Der Timer setzt nur die Leistungsgrenzen zurück, nicht alle sonstigen Einstellungen.

Modbus TCP bietet weder Verschlüsselung noch Anmeldung. Nur im geschützten lokalen
Netz betreiben und den Port nicht ins Internet freigeben. Die Implementierung ist
mit einem lokalen TCP-Geräteemulator getestet; ein Test am eigenen GEN24 inklusive
Verbindungsausfall und Automatik-Rückgabe ist vor unbeaufsichtigtem Betrieb erforderlich.

Referenzen: [Fronius GEN24 Modbus-Handbuch](https://manuals.fronius.com/html/4204102649/en-US.html),
[SunSpec-Modell 124](https://github.com/sunspec/models/blob/master/json/model_124.json),
[SunSpec-Modell 160](https://github.com/sunspec/models/blob/master/json/model_160.json).

## NRGkick Gen2 direkt über die lokale JSON-API

Das Wallbox-Plugin **NRGkick Gen2 local JSON API** (`nrgkick_local`) benötigt keine
zusätzliche NRGkick-Integration und keine HA-Mess- oder Steuerentitäten. Das bisherige
Plugin `nrgkick` bleibt für bestehende HA-Entitäten erhalten. Die Einrichtung erfolgt
unter **Konfigurieren → Hardware** oder im Plugin-Schritt eines Fahrzeugs unter
**Fahrzeuge und Wallboxen**. Vorher die lokale JSON-API in der NRGkick-App aktivieren.
Unterstützt wird die dokumentierte Gen2-API, nicht die ältere Gen1-Anbindung.

| Feld | Bedeutung |
| --- | --- |
| `url` | Lokale API-Basisadresse, z. B. `http://192.0.2.20`; optional mit Port. Keine Zugangsdaten, API-Pfade oder Query-Parameter in die URL eintragen. |
| `phase_switching` | Standard aus. Nur aktivieren, wenn die Phasenumschaltung in der NRGkick-App eingeschaltet und am Gerät unterstützt ist. Einphasige Adapter/Netzanschlüsse deaktivieren diese Fähigkeit zur Laufzeit. |
| `username` | Optionaler Benutzername der in der NRGkick-App eingerichteten Basic-Auth-Anmeldung. |
| `password_env` | Optionaler Name einer Umgebungsvariable mit dem API-Passwort im Home-Assistant-Core-Prozess; gemeinsam mit `username` konfigurieren. |

```json
{
  "url": "http://192.0.2.20",
  "phase_switching": false,
  "username": "",
  "password_env": ""
}
```

Bei aktivierter Anmeldung beispielsweise `username: "local"` und
`password_env: "NRGKICK_API_PASSWORD"` eintragen. Die Variable vor dem Start des
HA-Core-Prozesses bereitstellen; eine Variable nur in einem separaten Add-on genügt
nicht. Das Passwort wird erst für die Anfrage gelesen und nicht als Plugin-Parameter
gespeichert. Konfiguration und Diagnosen enthalten keine Passwortkopie. HTTP Basic
Auth verschlüsselt die Übertragung nicht; die API ausschließlich im geschützten
lokalen Netz betreiben. HTTPS wird mit Zertifikatsprüfung verwendet, sofern am
Gerät verfügbar. Weiterleitungen und Umgebungs-Proxys werden nicht benutzt.

`/info` liefert Geräte-/Adaptergrenzen und die angeschlossenen Phasen; `/values`
liefert aktuelle Gesamtwirkleistung und Gerätestatus; `/control` liefert die
eingestellten Ladeparameter. Es werden frische Abfragen ohne alten Messwertcache
verwendet. Fehlende, fehlerhafte oder ungültige Daten bleiben unbekannt. Die gültige
Maximalstromstärke ist durch Gerät und Adapter begrenzt und wird vor Ladebefehlen
erneut geprüft. Der Regler berücksichtigt zusätzlich die eigenen technischen
Grenzen und die gemeinsame Netzanschlussleistung. Stromvorgaben erfolgen in 0,1 A.

Jeder Schreibaufruf wird durch einen separaten Leseaufruf auf `/control` bestätigt.
Zum Start wird zuerst der Strom bestätigt und erst danach eine bestehende Pause
aufgehoben. Vorhandene Energie-Limits oder andere NRGkick-Einstellungen werden
nicht gelöscht. `charge_permitted` und Gerätefehler werden gelesen; das Plugin
umgeht keine Schutzfunktionen des NRGkick. Fehler-/RCD-Zustände verhindern neue
Ladefreigaben. Auch bei ausgefallener Messwertabfrage wird beim Stoppen eine
unabhängige, bestätigte Pause über `/control` versucht.

Die optionale Phasenumschaltung verwendet nur 1 und 3 Phasen. Sie pausiert zuerst,
wartet auf zwei neue Nullleistungsmessungen mit mindestens drei Sekunden Abstand,
schreibt dann die Phaseneinstellung und wartet auf deren erneute Rückmeldung.
Die dokumentierte Einstellung ist eine maximale Phasenanzahl; bei geöffneten
Relais wird diese bestätigte Vorgabe angezeigt, beim Laden die Relaisrückmeldung.
Eine unbestätigte Umschaltung führt nach 45 Sekunden zu einem Steuerfehler.

Für mehrere Fahrzeuge jeden physischen NRGkick genau einmal zuordnen. Identische
Adressen einschließlich normalisierter Standardports werden zurückgewiesen;
unterschiedliche Hostnamen/IP-Aliase desselben Geräts nicht parallel verwenden.
Die Leistungsreservierung benötigt keine HA-Steuerentitäten und berücksichtigt
auch bereits freigegebene Geräte, deren Leistungsaufnahme noch nicht gemeldet ist.
Der Fahrzeug-SoC kommt weiterhin aus einer eigenen Fahrzeugdatenquelle: Die
NRGkick-API liefert keinen Fahrzeug-Akkuladestand. Verbrauch und Kosten werden aus
der API-Leistung in der bestehenden Bilanz erfasst.

Die dokumentierte API bietet keinen Lade-Watchdog. Bei vollständigem Netzausfall
kann ein Ladestopp nicht bestätigt oder garantiert werden; ein fehlgeschlagener
Stop bleibt als ausstehende Geräterückgabe sichtbar. Getestet wird gegen einen
lokalen HTTP-Geräteemulator. Vor unbeaufsichtigtem Betrieb am eigenen Gerät
Ladestopp, Stromgrenzen und gegebenenfalls Phasenumschaltung prüfen.

Quelle: [Offizielle NRGkick-Gen2-API-Dokumentation](https://nrgkick.com/wp-content/uploads/local_api_docu_simulate-1.html).

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

Direkt angebundene Wallboxen ohne HA-Entitäten können `device_key` als stabile,
konfigurationsbasierte Gerätekennung setzen (beispielsweise normalisierte
API-Adresse ohne Zugangsdaten). Der Standard ist `None` für bisherige Plugins.
Eine identische Kennung darf nicht zwei Fahrzeugen zugeordnet werden. Für direkte
Wallboxen reserviert die Flottenregelung bestätigte Stromvorgaben unabhängig von
HA-Serviceaufrufen. Die erforderlichen `ids`-Schlüssel bleiben vorhanden, dürfen
bei direktem Zugriff aber leere Werte enthalten.

### Zusätzliche Messwerte als Sensoralternative

Die Plugin-API 2 erhält eine additive, optionale Erweiterung. Vorhandene Plugins
bleiben kompatibel. `measurement_keys` deklariert als Tupel die vom eingerichteten
Plugin bereitgestellten Werte; nach der Parameterprüfung darf das Tupel von den
tatsächlich aktivierten Fähigkeiten abhängen. Im Panel werden neben den
Steuerfähigkeiten auch diese Messfähigkeiten angezeigt.

Zusätzliche Werte stehen im Feld `measurements` von `BatteryReading` bzw.
`WallboxReading`, jeweils als `Measurement(value, sample)`. `sample` ist ein
zeitzonenbehafteter Beobachtungszeitpunkt. Werte sind in W, SoCs/Auslastung in %
und Preise in ct/kWh zu liefern. Netzleistung ist positiv bei Bezug und negativ
bei Einspeisung. Die Basis-`read()`-Methode prüft deklarierte Schlüssel, Datentypen,
Wertebereiche und Messwertalter. Fehlende oder veraltete Werte werden niemals 0.
Die bisherigen festen Felder für Speicher und Wallbox bleiben bestehen.

```python
measurement_keys = BatteryDriver.measurement_keys + ("grid",)
# Im Ergebnis von _read(), zusätzlich zu den normalen Speicherfeldern:
extra = {"grid": Measurement(grid_watts, grid_observed_at)}
result = BatteryReading(soc, charge, discharge,
                        soc_at, charge_at, discharge_at, measurements=extra)
```

Für die allgemeinen Quellsensoren unterstützt die Auflösung `solar`, `grid`,
`house_total`, `heat`, `price`, `car_soc` und `heat_load`. Explizit konfigurierte
HA-Sensoren haben Vorrang, auch bei einem Ausfall; es gibt dabei keinen stillen
Wechsel auf einen anderen Messpunkt. Ohne Sensor wird zuerst das Speicher-,
anschließend das Wallbox-Plugin berücksichtigt. Die Auswahl wird je Poll für
Regelung, Anzeige, Live-Verlauf und Kostenbilanz gemeinsam angewendet. In der
Mehrfahrzeugregelung bleiben bereits reservierte Netzleistungen berücksichtigt.

Ohne Quelle zeigt das Panel die konkret fehlende Konfiguration. Eine konfigurierte
Quelle ohne gültigen Messwert erhält einen separaten Verfügbarkeitshinweis.
Deaktivierte optionale Verbraucher benötigen keine Messquelle. Preise und
Fahrzeug-SoC bleiben bei fehlenden Werten unbekannt; die Hinweise ersetzen keine
Messwerte und heben keine Sicherheitsbedingungen der Regelung auf. Das Wetter
bleibt bei seiner bisherigen optionalen HA-Wetterquelle.

Der Vertrag ist in `energy/contracts.py`, die zentrale Prüfung in `energy/sanitiser.py`,
die Erkennung in `energy/plugin_registry.py` definiert. API-Version 2 verlangt:

- Eine konkrete Unterklasse von `BatteryDriver` bzw. `WallboxDriver`.
- `info = PluginInfo(identifier, name, kind, api_version=2)` mit stabiler ID,
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
Akkutreiber müssen für jeden vorhandenen Wert den zugehörigen zeitzonenbehafteten
Messzeitpunkt in `BatteryReading.soc_sample`, `charge_sample` bzw. `discharge_sample`
liefern. Fehlende, zukünftige oder 120 Sekunden alte Messwerte werden verworfen;
der Messzeitpunkt darf nicht durch den Zeitpunkt des Leseaufrufs ersetzt werden.
Wallbox-Leistungsmessungen ohne aktuelle Zeitmarke werden nicht zur Regelung verwendet.
Nicht unterstützte Befehle und ungültige Strom-/Leistungsvorgaben werden vor dem
Hardwareaufruf abgewiesen.

Die Erkennung prüft Metadaten, Version, Konfiguration und Methodensignaturen. Defekte
Module oder doppelte IDs werden abgewiesen und in den Integrationsdiagnosen unter
`plugin_errors` ausgewiesen; andere Plugins bleiben verfügbar. Unbekannte Typnamen
werden nicht als Python-Importpfade interpretiert. Es wird nur vertrauenswürdiger,
lokal installierter Python-Code aus dem Plugin-Paket geladen. Ein Plugin läuft im
HA-Prozess; der Sanitiser ist eine Daten-/Vertragsgrenze und keine Sandbox für fremden Code.

Der bereitgestellte Hardwareadapter erlaubt ausschließlich Entitäten, die das Plugin
über sein validiertes `ids`-Mapping zugeordnet hat. Während des Konstruktors ist noch
kein Entitätszugriff möglich. Dies schützt vor versehentlichen Zugriffen, stellt
aber keine Sicherheits-Sandbox für bösartigen Python-Code dar.
