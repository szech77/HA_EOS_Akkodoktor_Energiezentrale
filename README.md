# EOS Energiezentrale für Home Assistant

Installierbarer Quellstand für eine lokale Home-Assistant-App auf **amd64** und **aarch64**. Die Oberfläche läuft über Ingress und bündelt Stromfluss, Detailseiten, EOS-Planung und Alltagsparameter. Sie nutzt die vorhandenen Geräte-Integrationen und den laufenden Akkudoktor-EOS-Dienst.

## Lokale Installation

1. Kopiere den Unterordner `eos_energiezentrale` in das lokale App-Verzeichnis `/addons/` des Home-Assistant-Hosts. Der Zielpfad ist `/addons/eos_energiezentrale/config.yaml`.
2. Öffne in Home Assistant **Einstellungen → Apps**, lade den App-Store neu und installiere **EOS Energiezentrale** aus den lokalen Apps. Das Image wird dort gebaut. Die erste Installation benötigt Zugriff auf das Python-Basisimage und die Debian-Paketquelle.
3. Öffne den Reiter **Konfiguration**. Prüfe `eos_url` (Basisadresse einschließlich Port), die Sensorentitäten, `battery_resource` und `vehicle_resource`. Für vorhandenen InfluxDB-Verlauf trage die Basisadresse sowie die Datenbank und einen Lesezugang ein. Für deine Installation lautet die Datenbank `homeassistant`. Die Integration schreibt ihre Daten wie bisher in InfluxDB. Die App nutzt InfluxQL für Version 1.x.
4. Starte die App und öffne ihre Weboberfläche. Sie startet im **Lesemodus**. Prüfe den Stromfluss, beide Moduszeitleisten, den Preis und den EOS-Verbindungsstatus. Bei fehlender InfluxDB-Anbindung beginnt der lokale Verlauf ab App-Start.
5. Wenn die App übernehmen soll, deaktiviere die bisherigen NRGkick- und Fronius-Automationen, die Gerätebefehle schreiben. Die Freigabeschalter der bisherigen EOS-Packages müssen ebenfalls aus sein. Die App prüft bekannte Konfliktentitäten. Prüfe eigene Automationen separat. Wähle anschließend im Dashboard **Einstellungen → Steuerung übernehmen**. Die Übernahme gilt bis zur Rückgabe oder zum nächsten App-Neustart.

Die vorhandenen Integrationen für Fronius, NRGkick und die Fahrzeugdaten liefern weiterhin die Entitäten. Das Add-on installiert diese Integrationen oder Akkudoktor EOS nicht selbst. Für den geschätzten SoC kann die EOS-Zuordnung `ev1-soc-factor` auf `sensor.eos_energiezentrale_id4_soc` zeigen. Dieser Faktor wird bei aktiver Steuerungsübernahme veröffentlicht. Die bisherige Zuordnung zu `sensor.id4_soc` funktioniert weiterhin als Fahrzeugquelle.

## Konfiguration und eigene Hardware

| Option | Bedeutung |
| --- | --- |
| `battery_type` | Treiber für den Hausspeicher. Enthalten ist `fronius`. |
| `wallbox_type` | Treiber für die Wallbox. Enthalten ist `nrgkick`. |
| `battery_parameters`, `wallbox_parameters` | JSON-Objekt mit Parametern des ausgewählten Treibers. `{}` verwendet die hinterlegten Entitäten. |
| `battery_resource`, `vehicle_resource` | EOS-Ressourcen im Plan, normalerweise `battery1` und `ev1`. |
| `grid_limit_w`, Speicher-SoC-Grenzen, Leistungsgrenzen | Technische Grenzen für den Betrieb. |
| `car_soc_entity`, `car_soc_scale` | Fahrzeug-SoC als Faktor `factor` oder Prozent `percent`. |

Beispiel für `wallbox_parameters` als Textfeld

```json
{"power":"sensor.meine_wallbox_leistung","status":"sensor.meine_wallbox_status","enable":"switch.meine_wallbox_freigabe","current":"number.meine_wallbox_strom","phases":"number.meine_wallbox_phasen"}
```

Der Fronius-Treiber akzeptiert `mode`, `soc`, `charge_power`, `discharge_power`, `pv_limit`, `discharge_limit`, `grid_charge` und optional `grid_discharge`. Erzwungene Netzentladung benötigt sowohl die konfigurierte Entität als auch die explizite Option `allow_battery_export`.

Neue Hardware implementiert `BatteryDriver` oder `WallboxDriver` in `energy/drivers.py` und wird in `BATTERY_DRIVERS` bzw. `WALLBOX_DRIVERS` registriert. Ein Treiber nimmt den Home-Assistant-Client und sein Parameterobjekt entgegen. Der Speicher übersetzt `BatteryCommand` in seine Gerätebefehle. Die Wallbox liefert eine normalisierte `WallboxReading` und bestätigt beim Phasenwechsel eine sichere Ladepause, bevor sie den Wechsel freigibt. Treiber für andere Protokolle können ihre eigene Transportimplementierung mitbringen. Treiber werden aus der mitgelieferten Registrierung ausgewählt. Neue Klassen erfordern einen Image-Neubau.

## Daten und Regelung

- Der Hauswert zieht ID.4 und Wärmepumpe vom gemessenen Gesamtverbrauch ab. Fehlende Messungen erscheinen als Lücke.
- Die Detailseiten kombinieren Messwerte mit der verfügbaren GENETIC-Prognose und zeigen EOS-Modi. Die App erfindet keine Wärmepumpenprognose. Der Modusverlauf wird lokal ab App-Start aufgebaut. Der 24-Stunden-Verlauf nutzt bei verfügbarer Verbindung auch die von Home Assistant in InfluxDB geschriebenen Leistungsmessungen.
- Die Alltagsoberfläche speichert Ladeziele, Abfahrtszeiten, PV-Einspeisereserve und das Regelintervall unter `/data`. Schnellladen wird beim Neustart ausgeschaltet.
- Das SoC-Modell übernimmt neue Fahrzeugmeldungen und schätzt Zwischenwerte aus Ladeleistung, Kapazität und Ladeeffizienz. Bei einer Messlücke wird fehlende Ladeenergie nicht fortgeschrieben. Die Regelung verwendet die Schätzung als Zielkriterium.
- Die Regelung wählt vor dem Start passende Phasen, prüft neue Netzzählerwerte vor PV-Korrekturen und verwendet die vom Wallbox-Treiber gemeldete Schrittweite. Batteriestützung bei laufender PV-Autoladung bleibt an gemessene Ladeleistung und Speicher-SoC gebunden.
- Die UI öffnet keinen separaten öffentlichen Port. Die Serververbindung wird auf den Ingress-Proxy eingeschränkt. Schreibaktionen verlangen JSON und einen anwendungsspezifischen Request-Header. Zugangsdaten verbleiben serverseitig. Browseranfragen können weder beliebige URLs abrufen noch beliebige Home-Assistant-Dienste aufrufen.

## Tests

```sh
cd eos_energiezentrale
python -m pytest -q
python -m pytest --cov=energy --cov-report=term-missing
node --check energy/web/app.js
```

Die Tests verwenden simulierte Geräte und HTTP-Antworten. Der lokale Quellstand muss auf dem Zielsystem gebaut und im Lesemodus mit den dortigen Entitäten und API-Versionen geprüft werden.

Die fachlichen Regressionstests decken insbesondere die Bestätigung von EOS-Ladezielen, Stromrundung, Regelintervall und Messwertalter, SoC-Schätzung und Zielabschaltung, Wolkenpausen und bestätigte Phasenwechsel, die Speicherfreigabe sowie die Geräterückgabe bei Kommunikationsfehlern ab. Weitere Tests prüfen InfluxDB-Einheiten, Prognoselücken, Treiberparameter, persistierte Einstellungen, Sprache und die Ingress-Schreibgrenzen. Die Darstellung im Browser sowie das Zeitverhalten am realen Wechselrichter und an der Wallbox werden davon nicht abgedeckt.

## Sprache der Oberfläche

Die Sprache wird unter **Einstellungen → Apps → EOS Energiezentrale → Konfiguration → Sprache** eingestellt. Voreingestellt ist `auto`. Das Dashboard übernimmt beim Öffnen nach Möglichkeit die in Home Assistant eingestellte Sprache. Kann es die Sprache nicht lesen oder fehlt das Sprachpaket, verwendet es Englisch. Mit `de` oder `en` lässt sich die Sprache fest einstellen. Nach einer Änderung der Add-on-Option ist ein App-Neustart erforderlich.

Für eine weitere Sprache kopiere `energy/i18n/en.json` nach `energy/i18n/<Sprachcode>.json`, setze `locale` auf das passende BCP-47-Format und übersetze die Werte in `messages`. Die Schlüssel und Platzhalter wie `{start}` und `{energy}` bleiben bestehen. Die Texte werden als Klartext behandelt. Fehlende Übersetzungen übernimmt die App aus dem englischen Katalog.

Ergänze den Dateicode in `config.yaml` bei `schema.language` in der Liste der auswählbaren Sprachen. Wenn auch die Beschriftungen der Add-on-Konfiguration übersetzt werden sollen, kann dafür eine Home-Assistant-Datei unter `translations/<Sprachcode>.yaml` hinzukommen. Baue anschließend das Add-on-Image neu.

## Changelog und Beitr?ge

Die bisherigen Entwicklungsst?nde findest du im [Changelog](CHANGELOG.md). Hinweise zu Entwicklungsumgebung, Tests, Hardwaretreibern und Pull Requests stehen im [Beitragsleitfaden](CONTRIBUTING.md).

## Lizenz

Die eigenen Projektbestandteile stehen unter der [Apache License 2.0](LICENSE), SPDX-Kennung `Apache-2.0`. Die Lizenz erlaubt private und kommerzielle Nutzung, Bearbeitung und Weitergabe unter ihren Bedingungen. Die Urheberhinweise stehen in [NOTICE](NOTICE).

Auch [Akkudoktor EOS](https://github.com/Akkudoktor-EOS/EOS/blob/main/LICENSE) verwendet Apache 2.0. Für separat verwendete Drittkomponenten gelten deren jeweilige Lizenzen. Die bisherige Einschränkung auf private, nichtkommerzielle Nutzung entfällt.
