# Einrichtung und Betrieb

## EOS-Verbindung

Die Basisadresse enthält nur Schema, Host und Port, zum Beispiel
`http://homeassistant.local:8503`. Kein `/v1/config` anhängen.
Die Verbindung wird bei der Einrichtung mit `GET /v1/config` geprüft.
Ein Optimierungsplan darf beim Start noch fehlen; Live-Werte bleiben dann nutzbar.
Ressourcen heißen standardmäßig `battery1` und `ev1` und müssen unterschiedlich sein.

## Quellsensoren

PV und Netz sollten lokal und zeitnah aktualisiert werden. Standardzuordnungen:

| Größe | Entität | Erwartung |
|---|---|---|
| PV | `sensor.fronius_symo_gen24_pv_power` | W oder kW, positiv |
| Netz | `sensor.fronius_smartmeter_ip_meter_1_power` | W oder kW, Bezug positiv, Einspeisung negativ |
| Haus gesamt | `sensor.solarnet_leistung_verbrauch` | einschließlich Auto und Wärmepumpe |
| Wärmepumpe | `sensor.wp_strommesser_leistung_w_rmepumpe` | W oder kW |
| Auto-SoC | `sensor.id4_soc` | Faktor 0–1; alternativ Prozent im Dialog wählen |

Preis: EUR/kWh oder ct/kWh. Die Anzeige erfolgt in ct/kWh.
Für den dargestellten Hausverbrauch werden Auto und Wärmepumpe vom Gesamtverbrauch
abgezogen. Fehlende Messwerte werden nicht als Null ausgegeben.

## Hardware

Die Fronius-Modbus- und NRGkick-Integrationen müssen bereits eingerichtet sein.
Die Energiezentrale nutzt deren native Dienste und prüft Gerätebestätigungen.
Die Defaults im jeweiligen Treiber lassen sich mit JSON-Objekten überschreiben,
zum Beispiel `{"mode":"select.mein_speicher_modus"}` oder
`{"current":"number.mein_ladestrom"}`. Zulässig sind ausschließlich die im Treiber
definierten Schlüssel und Entitätsdomänen. Kein frei ausführbarer Plugin-Code im UI.

Neue Treiber implementieren `BatteryDriver` oder `WallboxDriver` in
`custom_components/eos_energiezentrale/energy/drivers.py` und werden in der
entsprechenden Registry sowie der Typauswahl registriert. Fachliche Tests ergänzen.

## Regelung

Die Integration prüft alle fünf Sekunden, einschließlich jeder vollen Minute.
EOS-Pläne werden höchstens alle 15 Sekunden, Prognosen alle 60 Sekunden abgerufen.
Bereits gelesene zukünftige Anweisungen werden anhand ihrer Ausführungszeit aktiviert.
Das Strom-Regelintervall begrenzt die Schreibfrequenz; eine neue Netzmessung nach dem
letzten Schreibvorgang ist ebenfalls erforderlich.

Das PV-Regelbudget berücksichtigt Netzleistung und Speicherentladung. Während
laufender PV-Autoladung darf die optionale Speicherunterstützung die EOS-Sperre
aufheben, soweit Speichergrenzen und Messwerte das zulassen. Für Fronius gilt
standardmäßig 4760 W als Lade- und Entladebasis. Netzlimit: 17250 W.

Phasenwechsel benötigen stabilen Überschuss beziehungsweise Mangel über die
eingestellte Wartezeit (standardmäßig 60 s). Vor dem Umschalten werden frische
Nullleistungsmessungen nach Abschalten verlangt. Stromauflösung und maximaler
Strom werden aus der Wallbox-Entität berücksichtigt; 0,1 A sind bei passender
Geräte-Schrittweite möglich.

`NON_EXPORT` sperrt hier die Speicherentladung; es setzt keine anlagenweite
dynamische Null-Einspeisung um. Fehlender oder abgelaufener Plan gibt den Speicher
zurück. Fehler bei Gerätebefehlen deaktivieren die Regelung. Eine unbestätigte
Rückgabe bleibt als Störung sichtbar und kann mit Ausschalten erneut versucht werden.

## Speichergrenzen

Mindest- und Maximal-SoC werden unter Panel → Einstellungen → Hausspeicher oder
über die zugehörigen Zahlenentitäten eingestellt. Mindest-SoC muss kleiner als
Maximal-SoC sein; gültiger Gesamtbereich ist 0–100 %. Lokale Regelung und EOS
verwenden dieselben gewünschten Grenzen.

Beim Speichern beziehungsweise Ändern der Zahlenentitäten werden die Werte auch
im Lesemodus an `devices.batteries.<battery_resource>` in EOS übergeben und
zurückgelesen. Ein eigener Status im Panel und ein Binärsensor zeigen die
Bestätigung. Die Geräteansteuerung wird dadurch nicht aktiviert. Bestehende
EOS-Grenzen werden ohne diese ausdrückliche Übergabe nicht automatisch übernommen.

Gespeicherte Vorgaben werden nach Neustarts weiter synchronisiert. Bei Fehlern
erfolgt nach 30 Sekunden ein weiterer Versuch; bestätigte Werte werden alle
60 Sekunden überprüft und bei externen Abweichungen wiederhergestellt. Andere
Batterieparameter und Geräte bleiben erhalten. Die nächste EOS-Optimierung
erstellt den Plan unter Berücksichtigung der geänderten Konfiguration.

## Alltagsplanung

Ziel-SoC zur Abfahrt und separates PV-Ziel sind unabhängig. PV-Überschussladen
funktioniert ohne zeitlichen Termin bis zum PV-Ziel. Schnellladen nutzt das Planziel
und wird nach Neustart nicht automatisch wieder eingeschaltet.
Einmalige Termine benötigen einen ISO-Zeitstempel mit Zeitzone; im Panel erzeugt
die Datumsauswahl diesen automatisch. Wiederkehrende Termine verwenden die
Home-Assistant-Zeitzone und ausgewählte Wochentage.

## Verlauf und Speicherung

Lokale Mess- und Modusdaten werden minütlich für zwei Tage in SQLite gespeichert.
InfluxDB 1.x ergänzt die letzten 24 Stunden; diese Verbindung ist optional.
Konfiguriere einen reinen Lesebenutzer. Zugangsdaten bleiben in der HA-Konfiguration
und werden weder an den Browser geschickt noch in Diagnosen ausgegeben.
Aktiviere die normale Home-Assistant-InfluxDB-Integration für die gewünschten
nativen Energiezentrale-Entitäten, wenn sie langfristig aufgezeichnet werden sollen.

Eigene Daten liegen unter `.storage/eos_energiezentrale/<config-entry-id>/`.
Sie werden bei Updates nicht aus dem HACS-Codeverzeichnis überschrieben und sind
Teil einer vollständigen HA-Konfigurationssicherung. Beim Entfernen der Integration
bleiben sie zur Wiederherstellung erhalten.

## Sprache

`auto` übernimmt die Frontend-Sprache von Home Assistant; nicht unterstützte
Sprachen fallen auf Englisch zurück. Inbetriebnahme-Option: `auto`, `en`, `de`.
Panel-Sprachdateien liegen in `energy/i18n`, native Dialog- und Entitätstexte in
`translations`. Weitere Sprachen ergänzen beide Bereiche, die Sprachauswahl und Tests.
