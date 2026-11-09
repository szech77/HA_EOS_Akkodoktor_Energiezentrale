# EOS Energiezentrale

HACS-Custom-Integration für Akkudoktor EOS mit animiertem Stromfluss, Prognosen,
Speichersteuerung und PV-Überschussladen. Ab Version **0.2.0** läuft die
Energiezentrale direkt in Home Assistant. Der EOS-Server bleibt ein separater Dienst.

## Installation

Voraussetzung: Home Assistant **2026.11.0 oder neuer** und ein erreichbarer
EOS-Server. Für die Installation über den Community Store wird zusätzlich HACS benötigt. Für die Installation über HACS muss das GitHub-Repository öffentlich
erreichbar sein; die Änderungen müssen zuvor nach GitHub übertragen worden sein.

1. HACS → Menü → **Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/szech77/HA_EOS_Akkodoktor_Energiezentrale` hinzufügen,
   Kategorie **Integration** wählen und EOS Energiezentrale herunterladen.
3. Home Assistant neu starten.
4. Einstellungen → Geräte & Dienste → Integration hinzufügen → **EOS Energiezentrale**.
5. EOS-Adresse, Quellsensoren, Hardware und technische Grenzen im Assistenten einrichten.
6. Das Panel **EOS Energiezentrale** in der Seitenleiste öffnen. Messwerte zunächst
   im Lesemodus prüfen. Erst danach die Energiesteuerung einschalten.

Alternativ `custom_components/eos_energiezentrale` nach
`/config/custom_components/eos_energiezentrale` kopieren und HA neu starten.
Eine Aufnahme in den HACS-Standardkatalog ist dafür nicht erforderlich.

## Konfiguration

Die Energiezentrale wird unter **Einstellungen → Geräte & Dienste → Integration
hinzufügen → EOS Energiezentrale** eingerichtet. Spätere Änderungen erfolgen über
**EOS Energiezentrale → Konfigurieren**. Der Dialog ist nach Verbindung, Sensoren,
Hardware, technischen Grenzen und Verlauf gegliedert.

Die Integration unterstützt ausschließlich die Einrichtung über die Oberfläche.
Ein eigener Block `eos_energiezentrale:` in `configuration.yaml` wird nicht
unterstützt. Die weiter unten gezeigten YAML-Beispiele gehören zur
Home-Assistant-InfluxDB-Integration und zu optionalen Template-Sensoren.

### EOS-Verbindung und Sprache

| Feld / interner Schlüssel | Beispiel oder Standard | Bedeutung |
|---|---|---|
| EOS-API-Basisadresse / `eos_url` | `http://homeassistant.local:8503` | Erreichbare Adresse des separat laufenden EOS-Servers, einschließlich Port. |
| Panel-Sprache / `language` | `auto` | Übernimmt die Sprache des HA-Frontends. Alternativen: `de`, `en`; Rückfall ist Englisch. |
| EOS-Speicherressource / `battery_resource` | `battery1` | Ressourcen-ID des Hausspeichers im EOS-Plan. |
| EOS-Fahrzeugressource / `vehicle_resource` | `ev1` | Ressourcen-ID des Autos im EOS-Plan. |

Die Adresse enthält nur Schema, Host und gegebenenfalls Port, beispielsweise
`http://192.168.178.56:8503`. Pfade wie `/v1/config` werden von der Integration
angehängt. Zum Prüfen der Erreichbarkeit kannst du im Browser
`http://192.168.178.56:8503/v1/config` öffnen. Die Verbindung muss auch vom
HA-Core-System aus erreichbar sein; `localhost` bezeichnet dessen eigene
Laufzeitumgebung, nicht automatisch eine andere App.

Die Ressourcen-IDs müssen zu deiner EOS-Konfiguration passen und unterschiedlich
sein. Die Integration übernimmt die Zeitzone aus Home Assistant; dafür gibt es
kein eigenes Eingabefeld. Die Sprache nativer HA-Dialoge und Entitäten folgt den
Home-Assistant-Spracheinstellungen; `language` steuert das eigene Panel.

### Quellsensoren

Wähle im Sensor-Dialog die tatsächlichen Entitäts-IDs deiner Installation.
Die folgenden Zuordnungen sind die mitgelieferten Standards und müssen bei
abweichenden Namen ersetzt werden:

| Feld / Schlüssel | Standard-Entität | Erwarteter Wert |
|---|---|---|
| PV-Leistung / `pv_entity` | `sensor.fronius_symo_gen24_pv_power` | Positive Leistung in W oder kW. |
| Gesamter Hausverbrauch / `house_entity` | `sensor.solarnet_leistung_verbrauch` | Positive Leistung in W oder kW, einschließlich Auto und Wärmepumpe. |
| Netzleistung / `grid_entity` | `sensor.fronius_smartmeter_ip_meter_1_power` | W oder kW; positiv = Bezug, negativ = Einspeisung. |
| Wärmepumpenleistung / `heat_entity` | `sensor.wp_strommesser_leistung_w_rmepumpe` | Positive Leistung in W oder kW, einschließlich Standby-Verbrauch. |
| Bezugspreis / `price_entity` | `sensor.blumenstrasse_13_strompreis` | `EUR/kWh`, `€/kWh`, `ct/kWh` oder `c/kWh`. |
| Fahrzeug-SoC / `car_soc_entity` | `sensor.id4_soc` | Numerischer Ladezustand, passend zur folgenden Einheit. |
| Fahrzeug-SoC-Einheit / `car_soc_scale` | `factor` | `factor`: 0–1, beispielsweise `0.33`; `percent`: 0–100, beispielsweise `33`. |

Der dargestellte Hausverbrauch wird so berechnet:

```text
Haus ohne Auto und Wärmepumpe = Gesamtverbrauch − Wallbox-Leistung − Wärmepumpenleistung
```

Der Speicher-SoC wird über die Hardware-Zuordnung konfiguriert und erwartet
**Prozent von 0 bis 100**. Die technische Fahrzeugkapazität wird in **Wh**
eingetragen. **kW** bezeichnet Leistung, **kWh** eine Energiemenge.

### Hardware: Fronius-Speicher und NRGkick

Unter **Konfigurieren → Hardware-Treiber → Fahrzeugname** kannst du das Fahrzeug
benennen, beispielsweise `Mein ID.4`. Der Standard ist **E-Auto**. Der Name erscheint
im Stromfluss, auf der Fahrzeug-Detailseite, in der Modus-Zeitlinie und in den
zugehörigen Sensorbezeichnungen. Zulässig sind 1–60 sichtbare Zeichen; vorhandene
Installationen ohne diese Option verwenden automatisch E-Auto. Die Bezeichnung
ändert weder die EOS-Ressourcen-ID `ev1` noch die konfigurierten Quellsensoren.

Wähle als Speichertreiber **`fronius`** und als Wallbox-Treiber **`nrgkick`**.
Die zugehörigen HA-Integrationen müssen die Sensoren und Stellgrößen bereits
bereitstellen. Aktuell stehen diese beiden Typen im Einrichtungsdialog zur Auswahl.

Die Felder **Speicher-Entitäten (JSON)** und **Wallbox-Entitäten (JSON)** erwarten
ein JSON-Objekt. Wenn die Standard-Entitäten passen, genügt in jedem Feld:

```json
{}
```

Du kannst sämtliche Zuordnungen oder nur einzelne abweichende IDs angeben.
Verwende doppelte Anführungszeichen und keine Kommentare oder abschließenden
Kommas. YAML-Zeilen wie `soc: sensor.mein_sensor` gehören nicht in diese Felder.

**Vollständige Speicher-Zuordnung für Fronius / BYD:**

```json
{
  "mode": "select.byd_battery_box_premium_hv_storage_control_mode",
  "soc": "sensor.byd_battery_box_premium_hv_ladezustand",
  "charge_power": "sensor.fronius_symo_gen24_storage_charging_power",
  "discharge_power": "sensor.fronius_symo_gen24_storage_discharging_power",
  "pv_limit": "number.byd_battery_box_premium_hv_pv_charge_limit",
  "discharge_limit": "number.byd_battery_box_premium_hv_discharge_limit",
  "grid_charge": "number.byd_battery_box_premium_hv_grid_charge_power",
  "grid_discharge": ""
}
```

| Schlüssel | Bedeutung |
|---|---|
| `mode` | Schreibbarer Fronius-Speicher-Steuermodus als `select`-Entität. |
| `soc` | Speicher-Ladezustand in Prozent. |
| `charge_power` | Gemessene Ladeleistung, positiv in W oder kW. |
| `discharge_power` | Gemessene Entladeleistung, positiv in W oder kW. |
| `pv_limit` | Schreibbare PV-Ladebegrenzung in W. |
| `discharge_limit` | Schreibbare Entladebegrenzung in W. |
| `grid_charge` | Schreibbare Netz-Ladeleistung in W. |
| `grid_discharge` | Optionale schreibbare Netz-Entladeleistung in W; leer lassen, wenn nicht vorhanden. |

Die Entladeleistung muss während einer tatsächlichen Entladung einen passenden
Wert liefern. Der Entitätsname allein bestätigt die richtige Zuordnung nicht.
Die Fronius-Stellgrößen benötigen unter anderem die Attribute `min`, `max`,
`step` und die Einheit `W`. Gemessene Leistung und Leistungsbegrenzung sind
unterschiedliche Größen; eine `number`-Begrenzung ersetzt keinen Leistungssensor.

Beispiel für die Änderung nur eines Sensors; die ID ist durch deinen tatsächlichen
Entladeleistungssensor zu ersetzen:

```json
{
  "discharge_power": "sensor.meine_gemessene_speicherentladung"
}
```

**Vollständige Wallbox-Zuordnung für NRGkick:**

```json
{
  "power": "sensor.nrgkick_id_4_gesamt_wirkleistung",
  "status": "sensor.nrgkick_id_4_status",
  "enable": "switch.nrgkick_id_4_laden_aktiviert",
  "current": "number.nrgkick_id_4_ladestromstarke",
  "phases": "number.nrgkick_id_4_phasenanzahl"
}
```

| Schlüssel | Bedeutung |
|---|---|
| `power` | Tatsächliche gesamte Wallbox-Leistung in W oder kW. |
| `status` | Rohstatus; der Treiber erkennt `connected`, `charging` und `wakeup` als verbunden, unabhängig von Groß-/Kleinschreibung. |
| `enable` | Ladefreigabe als schreibbare `switch`-Entität. |
| `current` | Schreibbare Stromvorgabe in A, mit Attributen `step` und `max`. |
| `phases` | Schreibbare Phasenanzahl, Wert `1` oder `3`. |

0,1-A-Regelung setzt voraus, dass die Stromvorgabe diese Schrittweite unterstützt
und als `step` meldet. Gerätebestätigungen werden nach Änderungen geprüft.

### Technische Grenzen

Diese Werte stehen im Bereich **Technische Grenzen** der Integration:

| Schlüssel | Standard | Bereich / Bedeutung |
|---|---|---|
| `capacity_wh` | `77000` | 1000–300000 Wh; nutzbare Fahrzeug-Batteriekapazität für die SoC-Schätzung. |
| `charging_efficiency` | `0.9` | 0,1–1; angenommener Fahrzeug-Ladewirkungsgrad. |
| `grid_limit_w` | `17250` | 1380–100000 W; Begrenzung der gesamten Netzbezugsleistung. |
| `battery_charge_w` | `4760` | 0–50000 W; Ladebasis des Speichers. |
| `battery_discharge_w` | `4760` | 0–50000 W; Entladebasis des Speichers. |
| `allow_battery_export` | `false` | Erlaubnis für erzwungene Speicherentladung ins Netz; benötigt eine passende `grid_discharge`-Entität. |
| `max_current_a` | `16` | 6–32 A; zusätzliche Obergrenze für den Wallbox-Ladestrom. |
| `phase_wait_s` | `60` | 10–600 s; Stabilitätswartezeit für die PV-Phasenumschaltung. |
| `regulation_interval_s` | `20` | 5–120 s; Startvorgabe für das Regelintervall, im Alltag separat einstellbar. |

Die tatsächlichen Geräteobergrenzen gelten zusätzlich. Das gesamte Netzlimit
bildet keine individuelle Überwachung oder Absicherung jeder einzelnen Phase ab.
`NON_EXPORT` sperrt in der Speicherregelung die Entladung; eine anlagenweite
Null-Einspeisung wird damit nicht eingerichtet.

### InfluxDB-Verbindung für historische Daten

InfluxDB **1.x / InfluxQL** ist optional. Ohne Verbindung bleibt der lokale Verlauf
nutzbar. Im Dialog **InfluxDB-Verlauf** eintragen:

| Feld / Schlüssel | Beispiel |
|---|---|
| Adresse / `influx_url` | `http://a0d7b954-influxdb:8086` |
| Datenbank / `influx_database` | `homeassistant` |
| Benutzer / `influx_user` | Vorhandener DB-Benutzer, beispielsweise `homeassistant`; vorzugsweise ein eigener Lesebenutzer. |
| Passwort / `influx_password` | Tatsächliches Passwort dieses Datenbankbenutzers. |

Der Hostname ist ein Beispiel für die entsprechende HA-App. Verwende den Host
deiner Installation; im HA-Core-Container muss dieser auflösbar und erreichbar sein.
Eine leere Adresse deaktiviert den InfluxDB-Zugriff. Pfade wie `/query` werden
automatisch angehängt. InfluxDB 2.x mit Bucket/Token wird aktuell nicht unterstützt.

Die Energiezentrale liest nur aus InfluxDB. Das Schreiben deiner HA-Sensoren
übernimmt weiterhin die normale HA-InfluxDB-Integration aus dem folgenden
YAML-Beispiel. Die Fronius- und NRGkick-Quellsensoren müssen darin enthalten sein.
Der aktuelle Leser erwartet die HA-Tags `domain` und `entity_id` sowie
Measurements nach Einheit, beispielsweise `W`, `kW` und `%`; für einheitenlose
Werte wird auch `state` abgefragt. Eine abweichende eigene Measurement-Struktur
erfordert eine Anpassung des Lesers.

### Alltägliche Ladeeinstellungen

Im Seitenleisten-Panel unter **Einstellungen** und teilweise als native Entitäten:

| Einstellung | Bedeutung |
|---|---|
| Energiesteuerung | Explizite Freigabe der Geräteansteuerung; bleibt über Neustarts erhalten. Bei der ersten Einrichtung aus. |
| Speicher Mindest-SoC | 0–99 %; kleiner als der Maximal-SoC. Startwert 20 %. Wird an EOS übergeben und lokal beachtet. |
| Speicher Maximal-SoC | 1–100 %; größer als der Mindest-SoC. Startwert 100 %. Wird an EOS übergeben und lokal beachtet. |
| Ziel-SoC | 1–100 %; Fahrzeug-Ziel für Terminplanung und Schnellladen. |
| PV-Ziel-SoC | 1–100 %; eigenständiges Ziel für PV-Überschussladen, auch ohne Termin. |
| PV-Überschussladen | Aktiviert die lokale PV-Regelung bis zum PV-Ziel. |
| Schnellladen | Lädt bis zum Ziel-SoC; wird nach Neustart nicht wieder eingeschaltet. |
| Einspeisereserve | 0–500 W; bei 0 W regelt die PV-Ladung möglichst nahe an Null-Netzleistung. |
| Regelintervall | 5–120 s; Mindestabstand zwischen Stromanpassungen, zusätzlich ist eine neue Netzmessung erforderlich. |
| Phasenautomatik | Automatischer Wechsel zwischen ein- und dreiphasigem Laden. |
| Speicherunterstützung | Kann während tatsächlicher Auto-PV-Ladung die EOS-Entladesperre unter Beachtung der SoC-Grenzen aufheben. |
| Abfahrtsplanung | Aus, einmalig mit Datum/Uhrzeit oder wöchentlich mit einzelnen Wochentagen. |

Das Panel übernimmt die vollständige Termin- und Wochentagsauswahl. Für eine
einmalige Planung muss vor der Wahl von `once` über native Entitäten ein gültiger
Abfahrtszeitpunkt gesetzt sein. Im Panel werden die Angaben gemeinsam gespeichert.

### Speichergrenzen an EOS übergeben

1. Im Panel **Einstellungen → Hausspeicher** öffnen.
2. **Speicher Mindest-SoC** und **Speicher Maximal-SoC** setzen, zum Beispiel 30 % und 90 %.
3. **Speichern** drücken. Die Werte gelten auch für die lokale Speicherregelung.
4. Unter den Feldern die Rückmeldung prüfen: **EOS bestätigt: Speicher 30–90 %.**

Die Einstellungen stehen zusätzlich als zwei `number`-Entitäten unter dem Gerät
EOS Energiezentrale zur Verfügung. Ein zusätzlicher Binärsensor meldet
**EOS-Speichergrenzen bestätigt**. Die tatsächlichen Entity-IDs im HA-Gerät nachsehen.
Bei Änderungen einzeln über Entitäten muss nach jedem Schritt Mindest-SoC < Maximal-SoC gelten.

Die Übergabe verwendet die konfigurierte Speicherressource, standardmäßig
`battery1`. In der EOS-Antwort von `GET /v1/config` sind die Werte hier zu finden
(Ausschnitt zur Kontrolle, keine vollständige Konfiguration zum Ersetzen):

```json
{
  "devices": {
    "batteries": {
      "battery1": {
        "min_soc_percentage": 30,
        "max_soc_percentage": 90
      }
    }
  }
}
```

Die Integration liest zuerst die vorhandene Konfiguration, ändert ausschließlich
die beiden Grenzen der ausgewählten Batterie über
`PUT /v1/config/devices/batteries` und liest die Werte zur Bestätigung erneut.
Kapazitäten, Wirkungsgrade, weitere Batterien, Fahrzeuge und Wechselrichter bleiben
erhalten. Die nächste EOS-Optimierung kann diese Grenzen anschließend berücksichtigen;
die Bestätigung bedeutet nicht, dass bereits ein neuer Plan erzeugt wurde.

Speichern im Panel beziehungsweise Ändern einer dieser Zahlenentitäten ist eine
ausdrückliche EOS-Konfigurationsänderung und erfolgt **auch im Lesemodus**. Der
Lesemodus unterbindet weiterhin die Geräteansteuerung. Ohne eine solche Übergabe
werden bestehende EOS-Grenzen beim ersten Einrichten nicht automatisch überschrieben.

Nach der ersten Übergabe bleiben die gewünschten Grenzen über Neustarts erhalten.
Bei einem Fehler wird die Übertragung nach 30 Sekunden erneut versucht, der Status
zeigt die fehlende Bestätigung an. Bestätigte Vorgaben werden alle 60 Sekunden
abgeglichen; abweichende spätere Änderungen direkt in EOS werden dabei auf die in
der Energiezentrale gespeicherten Grenzen zurückgesetzt. Änderungen deshalb über
die Energiezentrale vornehmen. Die gespeicherte Steuerfreigabe wird nach Neustarts wiederhergestellt.

Bestehende Inbetriebnahme-Grenzen aus älteren Integrationsständen werden als
Startwerte übernommen, wenn noch keine alltäglichen Speichergrenzen gespeichert sind.
Sie werden jetzt im Panel und über die Zahlenentitäten gepflegt.

## YAML-Beispiele

Die folgenden Blöcke beziehen sich auf die genannten Home-Assistant-Dateien.
Vorhandene `influxdb:`- und `template:`-Abschnitte entsprechend ergänzen, statt
denselben obersten Schlüssel mehrfach anzulegen. Bei ausgelagerter Konfiguration
die Inhalte in die bereits eingebundenen Dateien übernehmen.

### InfluxDB-Schreibverbindung in configuration.yaml

Beispiel für die vorhandene InfluxDB-1.x-App. Host und Datenbankbenutzer bei Bedarf
anpassen. Der Filter nimmt Sensoren und Binärsensoren auf; vorhandene weitere
Filter deiner Installation beibehalten oder zusammenführen.

```yaml
influxdb:
  api_version: 1
  host: a0d7b954-influxdb
  port: 8086
  database: homeassistant
  username: homeassistant
  password: !secret influx_homeassistant_password
  max_retries: 3
  measurement_attr: unit_of_measurement
  default_measurement: state
  tags_attributes:
    - friendly_name
  include:
    domains:
      - sensor
      - binary_sensor
```

In `/config/secrets.yaml` den tatsächlich vergebenen Wert hinterlegen:

```yaml
influx_homeassistant_password: "HIER_DAS_TATSAECHLICHE_DB_PASSWORT"
```

Im Integrationsdialog für die Energiezentrale wird das **Passwort selbst**
eingetragen. Der Ausdruck `!secret influx_homeassistant_password` wird dort nicht
aufgelöst. Die äußeren YAML-Anführungszeichen gehören nicht zum Passwort.
Falls du für die Energiezentrale einen separaten Lesebenutzer anlegst, dessen
Passwort im Dialog verwenden; die YAML-Schreibverbindung behält ihren Schreibbenutzer.

Offizielle Referenz: [Home Assistant InfluxDB](https://www.home-assistant.io/integrations/influxdb/).

### Optionaler Speicher-SoC-Faktor für einen EOS-Eingang

Wenn ein von dir eingerichteter EOS-Messeingang den Speicher-SoC als Faktor 0–1
erwartet, kann ein Template den Prozentwert umrechnen. Dieser Helfer gehört zur
Messwertversorgung von EOS; im Speicher-Entitäten-JSON bleibt der Prozentsensor.
Existiert der Helfer bereits, dessen Definition anpassen und keine zweite anlegen.

```yaml
template:
  - sensor:
      - name: "BYD HVM SoC"
        unique_id: byd_hvm_soc
        state_class: measurement
        availability: >-
          {{ is_number(states('sensor.byd_battery_box_premium_hv_ladezustand')) }}
        state: >-
          {{ (states('sensor.byd_battery_box_premium_hv_ladezustand') | float(0) / 100) | round(4) }}
```

Beispiel: `55.4` % ergibt `0.554`. Die tatsächliche erzeugte Entity-ID in HA
prüfen; `unique_id` reserviert keine feste Entity-ID. Die Zuordnung dieses Helfers
zum Messeingang erfolgt in deiner EOS-Konfiguration separat.

### Optionaler Fahrzeug-SoC-Faktor

Wenn dein vorhandener Sensor bereits 0–1 liefert, direkt auswählen und
`car_soc_scale: factor` im Dialog wählen. Für einen Prozentsensor genügt stattdessen
`percent`; eine zusätzliche Umrechnung ist für die Energiezentrale nicht nötig.

Falls ein anderer Verbraucher einen Faktor benötigt, ist folgendes Template
möglich. `sensor.mein_fahrzeug_soc_prozent` ist ein Platzhalter und muss ersetzt
werden. Dieser Sensor darf nicht wieder auf sich selbst verweisen.

```yaml
template:
  - sensor:
      - name: "ID4 SoC Faktor"
        unique_id: id4_soc_faktor
        state_class: measurement
        availability: >-
          {{ is_number(states('sensor.mein_fahrzeug_soc_prozent')) }}
        state: >-
          {{ (states('sensor.mein_fahrzeug_soc_prozent') | float(0) / 100) | round(4) }}
```

Die Beispiele sind zwei Alternativen beziehungsweise Ergänzungen innerhalb
deines vorhandenen `template:`-Blocks. Die Verfügbarkeit verhindert, dass ein
fehlender Quellwert als gültiger SoC von 0 ausgegeben wird.
Offizielle Referenz: [Home Assistant Template](https://www.home-assistant.io/integrations/template/).

Nach YAML-Änderungen die HA-Konfiguration prüfen und Home Assistant neu starten;
Template-Änderungen können alternativ über die angebotene Template-Neuladefunktion
übernommen werden. Bei Änderungen am Python-Code der Integration ist ein
HA-Neustart erforderlich; reine Panel-JavaScript-/CSS-Updates benötigen eine
vollständige Browser-Aktualisierung, beispielsweise Strg + F5.

## Steuerfreigabe über Neustarts erhalten

Der Schalter **Energiesteuerung** wird beim bewussten Ein- und Ausschalten
dauerhaft in `.storage/eos_energiezentrale/<config-entry-id>/control.json` gespeichert.
Beim normalen Herunterfahren oder Neuladen werden die Geräte freigegeben, ohne
diese gespeicherte Einstellung auf aus zu setzen.

Nach einem Neustart bleibt ein zuvor aktivierter Schalter eingeschaltet. Die
Anzeige **Aktiv · warte auf Messwerte und Plan** bedeutet, dass die Freigabe
gespeichert ist, die Integration aber noch auf gültige Eingangsdaten und einen
aktuellen EOS-Speicherplan wartet. Anschließend setzt sie die Regelung selbstständig fort.

Ein bewusst ausgeschalteter Schalter bleibt aus. Ein Regelfehler deaktiviert die
Steuerung ebenfalls dauerhaft; zur Wiederaufnahme muss sie ausdrücklich aktiviert
werden. Fehler beim Speichern werden angezeigt. Schnellladen bleibt nach einem
Neustart aus, die übrigen alltäglichen Einstellungen bleiben erhalten.

Beim ersten Update auf diese Funktion die Steuerung einmal aktivieren, damit die
bisher nur im Arbeitsspeicher gehaltene Freigabe dauerhaft gespeichert wird.

## Messwerte prüfen und Anzeige verstehen

Unter **Entwicklerwerkzeuge → Zustände** kontrollieren: Entitäts-ID, Zustand,
Einheit und Meldezeitpunkt. Ein numerischer Wert mit falscher Einheit oder ein
`unavailable`-Zustand ist keine gültige Leistung. Eine fehlende Entität wird
nicht automatisch als ausgeschaltetes Gerät behandelt.

Die Frischegrenzen für die Regelung betragen 45 Sekunden für PV und Netz,
120 Sekunden für Haus-, Wärmepumpen-, Wallbox- und Speicherleistungen und
3600 Sekunden für den Preis. Der Speicher-SoC wird ebenfalls mit 120 Sekunden
geprüft. Maßgeblich ist die letzte Meldung, auch wenn der Zahlenwert gleich bleibt.

Ein letzter gültiger Wärmepumpenwert kann in der Übersicht mit Altersangabe
weiter erscheinen. Der daraus berechnete Hausverbrauch trägt `≈` und den Hinweis
auf die ältere WP-Meldung. Diese Anzeige wird nicht als frische Messung an die
Regelung oder den lokalen Verlauf übergeben.

Die unteren EOS-Modus-Karten zeigen die **Planung**. Im Lesemodus steuert die
Integration keine Geräte; der reale Speicherbetrieb kann daher davon abweichen.
Für den tatsächlichen Stromfluss zählen die konfigurierten Leistungssensoren.


## Wechsel vom bisherigen Energiezentrale-Add-on

Der EOS-Server bleibt als separater Dienst bestehen. Zustände bisheriger
Regelungs-Packages werden von der Integration nicht ausgewertet.

Die Add-on-Optionen werden nicht automatisch aus Supervisor übernommen. Trage sie
im Einrichtungsassistenten erneut ein. Es ist kein Supervisor-Token und kein
Home-Assistant-Zugriffstoken erforderlich. Vorher ein HA-Backup erstellen.

InfluxDB bleibt unverändert nutzbar. Der lokale Kurzzeitverlauf beginnt zunächst neu.
Optional können bei gestopptem Add-on und entladener Integration dessen Dateien
`daily.json` und `history.sqlite3` aus einer Datensicherung nach
`/config/.storage/eos_energiezentrale/<config-entry-id>/` übernommen werden.
Die Integration erzeugt dieses Verzeichnis beim ersten Einrichten. Anschließend
neu laden. Schnellladung wird nicht wiederhergestellt. Die Steuerfreigabe wird separat
in `control.json` gespeichert; fehlt diese Datei bei der erstmaligen Einrichtung, ist die Steuerung aus.

## Oberfläche und native Entitäten

- Animierter Stromfluss mit PV, Netz, Haus, Speicher, Auto und Wärmepumpe.
- Detailseiten mit historischen Messwerten, EOS-Prognosen, Strompreis und Modus-Zeitlinien.
- Native Leistungssensoren in **kW**, SoC in **%**, zusätzlicher Auto-SoC-Faktor **0–1**.
- Native Schalter für Steuerfreigabe, PV-Überschussladen, Schnellladen und Phasenautomatik.
- Ziel-SoC, PV-Ziel, Einspeisereserve und Regelintervall als `number`-Entitäten.
- Einmalige und wiederkehrende Abfahrtsplanung mit Wochentagsauswahl im Panel.
- Geschätzter Auto-SoC während der Ladung, falls das Fahrzeug keine neuen Werte meldet.

Die Entitäten werden über ihre eindeutige ID registriert. Die tatsächlich vergebenen
Entity-IDs findest du unter dem Gerät **EOS Energiezentrale**. Bereits bestehende
Helper werden nicht überschrieben. Einen bisherigen EOS-SoC-Eingang bei Bedarf
auf den neuen nativen Auto-SoC-Faktor umstellen.

Alltagseinstellungen sind im Panel und über native Entitäten erreichbar.
Inbetriebnahme-Einstellungen findest du unter Geräte & Dienste → EOS Energiezentrale
→ **Konfigurieren**. Nach deren Änderung wird die Integration neu geladen. Die
gespeicherte Steuerfreigabe bleibt erhalten und wird nach Prüfung der Eingangsdaten wieder aktiv.

Das eigene Panel ist Administratoren vorbehalten und verwendet die bestehende
HA-Anmeldung. Es gibt keinen zusätzlichen Webserver, Port oder eingebetteten Token.
Die Sprache folgt standardmäßig Home Assistant; Englisch ist der Rückfall.

## Hardware und Daten

Mitgelieferte Treiber: **Fronius GEN24 / BYD über callifo/fronius_modbus** und
**NRGkick**. Generische Treiberverträge und Registries ermöglichen weitere Geräte.
Entitätszuordnungen lassen sich als JSON in den Hardware-Optionen überschreiben.
Siehe [Einrichtung und Betrieb](DOCS.md) und [Contributing](CONTRIBUTING.md).

InfluxDB 1.x ist optional und wird lesend angesprochen. Die Integration hat keine
zusätzlichen Python-Laufzeitabhängigkeiten außerhalb von Home Assistant.

## Entwicklung

Python 3.14.2 oder neuer; Tests gegen Home Assistant 2026.11.0:

```sh
python -m venv .venv
# Windows PowerShell: Umgebung für die folgenden Befehle aktivieren
.\.venv\Scripts\Activate.ps1
# Linux/macOS stattdessen: source .venv/bin/activate
python -m pip install -r requirements-dev.txt -r requirements-test.txt
python -m pytest --cov=custom_components.eos_energiezentrale --cov-branch
node --test tests/*.test.cjs
```

Details zu Prüfungen, Releases und vorbereitetem Branchschutz: [CI.md](CI.md).

## Lizenz

[Apache License 2.0](LICENSE). Private und kommerzielle Nutzung unter den
Lizenzbedingungen; Urheberhinweise siehe [NOTICE](NOTICE).

### Interaktive Energie-Diagramme

Ein Klick auf **Energie** in der Mitte des Stromflussbilds öffnet alle verfügbaren Energieflüsse. Speicher- und Fahrzeugdiagramme enthalten zusätzlich die PV-Messwerte und PV-Prognose. Mausbewegung oder Tippen zeigt Werte und Messzeitpunkte; per Tab und Pfeiltasten ist dieselbe Auswahl möglich. Historie ist durchgezogen, Prognose gestrichelt. Fehlende Daten bleiben Lücken. Die Hausgesamtprognose enthält Auto und Wärmepumpe und wird entsprechend beschriftet.

### Optionale Verbraucher

Neue Einrichtungen starten ohne E-Auto und Wärmepumpe. Unter den Integrationsoptionen aktiviert ein ausgewählter Wärmepumpensensor die Wärmepumpe; ein leeres Feld entfernt sie. Für das E-Auto unter Hardware den Wallbox-Typ `nrgkick` auswählen, zum Deaktivieren `none`. Ohne diese Verbraucher entfallen ihre Knoten, Leitungen und Detailnavigation im Stromfluss. Der Hausverbrauch berücksichtigt nur konfigurierte Verbraucher. Ein konfigurierter, aber ausgefallener Sensor bleibt hingegen ein fehlender Messwert. Bestehende Einrichtungen behalten ihre bisherigen Einstellungen.

### Mehrere Fahrzeuge und Wallboxen

Unter **Integration → Konfigurieren → Fahrzeuge und Wallboxen** können Ladepunkte
über Formulare hinzugefügt, bearbeitet und entfernt werden. Die bisherige
Einzelkonfiguration wird beim ersten Hinzufügen übernommen. Alternativ steht unter
**Hardware → Mehrere Fahrzeuge / Wallboxen** die JSON-Liste zur Verfügung. Ein vollständiges Beispiel steht in
[examples/vehicles.json](examples/vehicles.json). `[]` verwendet weiterhin die
bisherige Einzelkonfiguration. Eine nicht leere Liste ersetzt die Einzelzuordnung.
Bis zu acht Fahrzeug-Wallbox-Paare sind möglich; für jedes Paar Name, stabile `id`,
eigene EOS-`resource` (z. B. `ev1`, `ev2`), SoC-Sensor, Kapazität und die fünf
Wallbox-Entitäten angeben. Die Fahrzeuge müssen auch in EOS angelegt sein.
Die Konfiguration erstellt oder überschreibt keine EOS-Gerätedefinitionen.

In den Alltagseinstellungen das Fahrzeug auswählen und dessen Ziel-SoC,
PV-Ziel, Abfahrt und Schnellladung speichern. Die Speichergrenzen bleiben global.
Der Stromfluss zeigt die gesamte Autoladeleistung; einzelne Fahrzeugkarten öffnen
Messwerte, SoC und den jeweiligen EOS-Zeitplan. Es entstehen eigene native Sensoren
für Leistung, SoC und Status jedes Fahrzeugs. Die Fahrzeug-ID bestimmt deren Identität.

Alle Regler verwenden denselben Netzanschluss. Nicht gemessene Leistungserhöhungen
werden bereits reserviert; Minderungen werden erst nach Messung frei. Bei knappem
Budget hat die Reihenfolge in der Liste Vorrang. Beim Abschalten werden alle Ladepunkte
pausiert und der Speicher freigegeben. Die Hausleistung zieht alle gemessenen
Fahrzeugleistungen genau einmal ab.

Die bisherige EOS-Lösungsantwort enthält nur eine nicht nach Fahrzeugressourcen
aufgeschlüsselte EV-Prognose. In der Mehrfahrzeugansicht werden deshalb keine
Leistungs-/SoC-Prognosen einzelnen Fahrzeugen zugeordnet. PV-Prognose und
ressourcenspezifische EOS-Moduspläne bleiben verfügbar. Fahrzeughistorie wird lokal
ab Einrichtung geführt; ältere individuelle Influx-Verläufe werden hier noch nicht geladen.

### Letzte Sensorwerte anzeigen

Unter **Konfigurieren → Grenzen → Letzte Messwerte anzeigen für** wird die Anzeigedauer in Sekunden eingestellt (Standard 900 = 15 Minuten, Bereich 60–86400). Kurzzeitig fehlende oder nicht mehr frische Messwerte bleiben mit Altersangabe sichtbar. Abgeleitete Leistungen sind als Schätzung markiert. Die Regelung und historischen Messreihen verwenden weiterhin ausschließlich ihre regulär gültigen Werte. Der Anzeigepuffer wird bei einem Integrationsneustart neu aufgebaut.

### Unterschiedliche Aktualisierungszeiten der Messgeräte

Das Stromflussbild verwendet aktuelle Werte, ohne sie allgemein auf alte
Meldezeitpunkte zurückzurechnen. Nur nach einer angeforderten Erhöhung der
Autoladeleistung wird ein dazu passender Anstieg von Hauslast bzw. Quellenleistung
kurz zurückgehalten, solange die tatsächliche Autoleistung noch fehlt. Bis dahin
bleibt der vorherige Messwertsatz sichtbar. Sobald die Wallboxleistung nachzieht,
wird die Anzeige freigegeben; spätestens 30 Sekunden nach dem erkannten Sprung
erscheinen wieder die aktuellen Werte. Neue Ladebefehle verlängern eine bereits
laufende Wartezeit nicht. Der Sollstrom wird niemals als gemessene Leistung ausgegeben.
Unter **Konfigurieren → Grenzen** ist diese reine Anzeigeverzögerung einstellbar;
0 schaltet sie aus. Die bisherige allgemeine zeitliche Anzeigeausrichtung entfällt.

Der Regler wartet weiterhin nach einem Ladebefehl auf das Regelintervall sowie neue
Meldungen von Netzzähler und Wallboxleistung. Bei ausbleibenden Meldungen wird nach
standardmäßig 60 Sekunden pausiert. Netzgrenzüberschreitung, fehlende erforderliche
Messwerte, Abstecken und eine reguläre Stoppvorgabe werden sofort behandelt.
Diese Regelungslogik ist von der 30-Sekunden-Anzeigeverzögerung unabhängig.

### EOS-Abruf vorübergehend nicht verfügbar

Bei einem fehlgeschlagenen oder für ein Fahrzeug unvollständigen Planabruf arbeitet
die EOS-abhängige Ladung bis zu fünf Minuten mit dem letzten gültigen Plan weiter.
Die Frist beginnt beim ersten fehlgeschlagenen Abruf und wird durch weitere Fehler
nicht verlängert. Neue gültige Stoppanweisungen, bekannte geplante Stopps und explizite
Gültigkeitsenden gelten sofort. Ohne vorherigen gültigen Plan wird keine Ladung erfunden.
Nach Ablauf wird die EOS-abhängige Ladung pausiert; die Steuerfreigabe bleibt gesetzt,
damit nach Erholung automatisch fortgesetzt werden kann. Lokale Sicherheitsgrenzen
und die Frische der HA-Messwerte werden weiterhin geprüft. Pro Fahrzeug wird ein
eigener Plan gepuffert. Die Diagnose zeigt den aktiven Puffer und seine Restzeit.


## Verbrauch, Energiequellen und Kosten

Die Übersicht zeigt den bisher erfassten Tagesverbrauch und die variablen Energiekosten
für Haus, Wärmepumpe und E-Auto. Der Hausverbrauch enthält weder Wärmepumpe noch Fahrzeuge.
Optionale Verbraucher werden ausgeblendet. Bei mehreren Fahrzeugen enthält die Übersicht
deren Summe; die Einzelauswertungen sind über die jeweilige Fahrzeug-Detailseite erreichbar.

Auf jeder Verbraucher-Detailseite öffnet **Verbrauch & Kosten** eine eigene Auswertung:

- **Tag:** stündliche Werte; **Monat:** Tageswerte; **Jahr:** Monatswerte.
- Pfeile wechseln den Zeitraum; **Aktuell** springt in den aktuellen Zeitraum.
- Ein Tages-/Monatsbalken öffnet die nächstfeinere Ansicht. Die Datumswahl ermöglicht direkte Sprünge.
- Getrennte gestapelte Diagramme zeigen kWh und Euro nach PV, Akku, Netz und unbekannter Quelle.
- Maus/Fokus zeigt die Werte eines Balkens; die Tabelle enthält die Summen je Quelle.

Die neue lokale Bilanz speichert Stundenaggregate dauerhaft in
`.storage/eos_energiezentrale/<entry_id>/accounting.sqlite3` und ist unabhängig vom
kurzen Diagrammcache. Datenbank und Kostenbestand gehören in die HA-Sicherung.
Messlücken über 120 Sekunden sowie Zeiten während eines Neustarts werden nicht mit
gehaltenen Anzeigewerten aufgefüllt. Die ausgewiesene Beobachtungsdauer macht die Abdeckung sichtbar.

Für Zeiträume vor Beginn der lokalen Bilanz liest die Auswertung vorhandene Messwerte
aus der konfigurierten InfluxDB 1.x. Diese Rekonstruktion verwendet Fünf-Minuten-Mittelwerte,
füllt fehlende Intervalle nicht auf und überlappt die neue Bilanz nicht. Sie ist ausdrücklich
eine Schätzung. Fehlende Preise oder unbekannte anfängliche Akkuenergie bleiben unbekannt.
Historische Auswertungen verwenden für die Rekonstruktion die aktuell eingestellten
PV-Kosten und Speicherparameter; bereits dauerhaft erfasste Bilanzwerte werden nicht neu bewertet.
Die Datenbankabfragen laufen außerhalb der Gerätesteuerung und sind zeitlich begrenzt.

### Einstellungen zur Bilanzierung

Unter **Einstellungen → Kosten & Bilanzierung** stehen zur Verfügung:

| Einstellung | Bedeutung |
| --- | --- |
| Quelle für PV-Kostenansatz | Standard EOS-Einspeisevergütung, zur Laufzeit per REST gelesen; alternativ manuell. |
| PV-Kostenansatz | ct/kWh; im EOS-Modus wird der verwendete Wert angezeigt. Manuelle Vorgabe nur im manuellen Modus. |
| Quelle für Speicherwirkungsgrad | Standard EOS; alternativ manuelle Parameter. |
| Lade-/Entladewirkungsgrad | Jeweils Faktor 0,1 bis 1; nur im manuellen Modus. |
| Speicherkapazität | Wh; im manuellen Modus die eigene nutzbare Kapazität eintragen. |
| Anfangsbestand: Preis | Optionaler Preis je gespeicherter kWh bei der ersten Initialisierung. Leer bedeutet unbekannt. Keine nachträgliche Umbewertung. |

Aus EOS werden `devices.batteries.<battery_resource>.capacity_wh`, `charging_efficiency`
und `discharging_efficiency` gelesen. Dies verändert keine EOS-Konfiguration. Fehlen diese
Werte, bleibt die Bewertung von Akkuenergie unbekannt, bis EOS bereit ist oder manuelle
Parameter eingestellt sind. Der letzte gültige Parametersatz wird während der Laufzeit
weitergenutzt. Die aktuellen verwendeten Parameter werden im Einstellungsbereich angezeigt.

PV, Netz und Akku werden anteilig auf die gleichzeitig gemessenen Verbraucher,
Speicherladung und Einspeisung verteilt. Eine eindeutige physische Quellenzuordnung
pro Verbraucher ist mit den vorhandenen Zählern nicht möglich. Größere Widersprüche
in der Leistungsbilanz erscheinen als unbekannte Quelle. Die Berechnung setzt die
Leistungen als Werte auf derselben AC-Bilanzgrenze voraus; abweichende DC-Speichermessungen
führen zu zusätzlichen Modellabweichungen.

Netzladung erhöht den Akku-Kostenbestand zum jeweiligen Strompreis, PV-Ladung zum
PV-Kostenansatz. Ladeverluste reduzieren die eingelagerte Energie; bei Entladung wird
die für die gelieferte Energie nötige gespeicherte Energie einschließlich Entladeverlusten
ausgebucht. Energie und Kosten werden mit gewichtetem Durchschnitt entnommen.
Der Kostenbestand bleibt über Neustarts erhalten; nicht beobachtete Bestandszunahmen
werden beim Abgleich mit dem SoC als unbekannt behandelt. Es werden keine Grundgebühren
oder Einspeiseerlöse des übrigen Hauses verrechnet. Negative Arbeitspreise sind zulässig.

Bei nur teilweise bekannten Kosten zeigt die UI die bekannte Teilsumme mit `≈` an;
bei vollständig unbekannten Kosten steht `—`. Unbekannte Energie wird nicht als kostenlos bewertet.
Die Auswertung ist eine Energiekostenbilanz und ersetzt keine Stromrechnung.


Der PV-Kostenansatz wird zur Laufzeit aus der **EOS-REST-API** gelesen. Es werden keine
Werte aus einer bereitgestellten Konfigurationssicherung eingebaut. Bei einer konstanten
Einspeisevergütung wird `GET /v1/config` mit dem aktiven `FeedInTariffFixed`-Anbieter
ausgewertet (`feedintariff.feedintarifffixed.feed_in_tariff_amt_kwh`). Die dortigen
€/kWh werden in ct/kWh umgerechnet. Bei zeitabhängigen Fenstern bzw. anderen Anbietern
wird `GET /v1/prediction/series?key=feed_in_tariff_wh` verwendet; dessen €/Wh werden mit
100000 in ct/kWh umgerechnet. Tarifintervalle werden einschließlich negativer Werte beachtet.
Ein fehlender Tarif ist nicht gleich 0: Direkte PV-Nutzung und neue PV-Speicherladungen
werden bis zum Vorliegen eines Tarifs mit unbekannten Kosten geführt. Während eines
vorübergehenden Fehlers bleibt ein zuletzt gelesener konstanter Tarif erhalten; zeitabhängige
Tarife werden nur innerhalb ihrer gültigen Intervalle verwendet. Tarife werden alle fünf
Minuten erneut gelesen, nach Fehlern nach einer Minute.

Die frühere Standardeinstellung 0 wird auf automatische EOS-Übernahme umgestellt;
bereits eingestellte manuelle Werte ungleich 0 bleiben als manuelle Vorgabe erhalten.
Eine bewusste manuelle Vorgabe von 0 ist weiterhin möglich. Änderungen bewerten bereits
gespeicherte Bilanzintervalle und den bisherigen Akku-Kostenbestand nicht rückwirkend neu.
