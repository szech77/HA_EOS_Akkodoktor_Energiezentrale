# ESPHome als Gateway für den Deye SUN-12K-SG04LP3-EU

Die [ESPHome Modbus Bridge von rosenrot00](https://github.com/rosenrot00/esphome_modbus_bridge)
ist **vom Protokoll her für das Deye-Plugin geeignet**. Sie setzt Modbus TCP mit
MBAP-Header in Modbus RTU mit CRC um und liefert die Antwort wieder als Modbus TCP
zurück. Die Energiezentrale verbindet sich mit dem ESP auf Port 502.
Eine zusätzliche ESPHome-Integration oder Sensorzuordnung in Home Assistant ist
dafür nicht erforderlich.

Die Prüfung bezieht sich auf Bridge **2026.10.2**, Commit
[`9119ba5b036af146eb8fb1e4a59aef29d4f63089`](https://github.com/rosenrot00/esphome_modbus_bridge/tree/9119ba5b036af146eb8fb1e4a59aef29d4f63089).
Das Beispiel pinnt diesen Stand und verwendet direkten UART-Zugriff.
Die Protokollimplementierung und das Konfigurationsschema wurden abgeglichen.
Das Beispiel wurde mit **ESPHome 2026.10.2** erfolgreich validiert und dessen
C++-Quellcode generiert; die Variante ohne DE-/RE-Pins wurde ebenfalls validiert.
Ein Test am physischen ESP mit Deye steht aus. Das ist keine Freigabe für jede
ESP-Platine oder Deye-Firmware.

## Warum die Bridge passt

| Anforderung des Plugins | Abgleich mit der Bridge |
| --- | --- |
| Modbus TCP mit Transaktions-ID und Unit-ID | MBAP wird ausgewertet; die Antwort wird der ursprünglichen TCP-Anfrage zugeordnet. |
| FC03: Holding-Register lesen | Wird an den RTU-Teilnehmer weitergegeben; Antwortlänge und CRC werden geprüft. |
| FC16 / `0x10`: Register schreiben | Wird unterstützt; die Bridge prüft die Schreibbestätigung. Das Plugin liest die Register anschließend zusätzlich zurück. |
| Größter Deye-Leseblock: 108 Register | 216 Datenbytes beziehungsweise 221 Byte RTU-Antwort liegen innerhalb der Bridge-Grenzen; das Beispiel verwendet 512 Byte UART-Puffer. |
| Drei Sekunden Plugin-Antwortfrist | Das Beispiel setzt eine RTU-Antwortfrist von einer Sekunde. Bei 9600 Baud benötigt die reine Übertragung der großen Antwort etwa 230 ms; Verarbeitungs- und WLAN-Zeit kommen hinzu. |
| Lesender Betrieb und optionale Steuerung | Beides ist möglich, wenn die IP des HA-Hosts in der Bridge zugelassen ist. Die Firmware-Unterstützung der Deye-Remote-Register bleibt eine separate Voraussetzung. |

Der Begriff „transparent“ im Projektnamen meint hier die Weitergabe der
Modbus-Registerzugriffe **mit Protokollumsetzung**. Ein einfacher UART-TCP-Stream
ohne MBAP/RTU-Umsetzung erfüllt diese Anforderung nicht.

## Hardware vorbereiten

Benötigt werden ein ESP32-WROOM-Entwicklungsboard, eine passende Stromversorgung
und ein RS485-Transceiver mit 3,3-V-kompatiblen Logiksignalen. Ein galvanisch
getrenntes Modul ist für die Verbindung zum Wechselrichter sinnvoll. Ein ESP
allein stellt keine RS485-Schnittstelle bereit.

Das Beispiel gilt für `esp32dev` mit frei verfügbaren GPIO16/17/18. Auf anderen
Boards, insbesondere ESP32-S3, WROVER oder ESP8266, Boarddefinition und Pinbelegung
anpassen; GPIO16/17 können dort anders belegt sein.

| ESP im Beispiel | RS485-Transceiver |
| --- | --- |
| GPIO17, TX | DI |
| GPIO16, RX | RO |
| GPIO18 | DE und `/RE`, sofern das Modul diese gemeinsame Richtungssteuerung erlaubt |
| Versorgung / Bezugspotential | Nach Schaltung und Datenblatt des Moduls; bei galvanischer Trennung die beiden Seiten getrennt betrachten |

Module mit automatischer Sende-/Empfangsumschaltung benötigen keine GPIO18-Verbindung;
dann **beide** Einträge `de_pin` und `re_pin` aus der YAML entfernen.
Die A/B-Leitungen, Polarisation und Terminierung entsprechend den Datenblättern
und der tatsächlichen Businstallation anschließen.

**Deye-Anschluss zuerst klären:** Das aktuelle Betriebshandbuch bezeichnet die
RJ45-Buchse „Modbus“ als reserviert. Bei älteren Hardwareständen gibt es andere
Angaben. Deshalb den für die konkrete Revision freigegebenen RS485-Monitoring-Port
und dessen Belegung bei Deye prüfen. Diese Anleitung gibt bewusst keine
allgemeingültige Deye-RJ45-Pinbelegung vor. BMS-, Zähler- und Parallel-Busse
nicht als beliebige Monitoring-Anschlüsse verwenden.

## ESPHome einrichten

1. [deye_esphome_gateway.yaml](../examples/deye_esphome_gateway.yaml) in das eigene
   ESPHome-Konfigurationsverzeichnis kopieren. ESPHome 2026.10.2 ist der für dieses
   Beispiel gewählte Stand; bei neueren Versionen die Konfiguration erneut prüfen.
2. Die Schlüssel aus
   [deye_esphome_secrets.example.yaml](../examples/deye_esphome_secrets.example.yaml)
   in die eigene `secrets.yaml` übernehmen und die Beispielwerte ersetzen.
   Bei `deye_bridge_ha_client_cidr` die **Quell-IP des Home-Assistant-Hosts** mit
   `/32` eintragen, beispielsweise `192.168.1.20/32`. Das ist nicht die ESP-IP.
   Bei Docker/NAT muss die am ESP tatsächlich sichtbare Quell-IP zugelassen werden.
3. Board, GPIOs und Richtungssteuerung an die Hardware anpassen. Das Beispiel
   verwendet **9600 Baud, 8N1** entsprechend dem Deye-Protokoll; die reale
   Wechselrichtereinstellung muss dazu passen.
4. Im ESPHome Device Builder die Konfiguration validieren und den ESP zunächst per
   USB installieren. Alternativ mit der ESPHome-CLI:

   ```sh
   esphome config deye_esphome_gateway.yaml
   esphome run deye_esphome_gateway.yaml
   ```

5. Dem ESP eine stabile Adresse geben, etwa per DHCP-Reservierung. Das Plugin
   muss diese Adresse im lokalen Netz auf TCP-Port 502 erreichen können.

Das Beispiel benötigt kein `api:` und kein MQTT: Der Datenweg ist
**Energiezentrale → Modbus TCP → ESP → RS485 → Deye**.
OTA dient nur der Firmwarepflege; das OTA-Passwort authentifiziert keine
Modbus-Verbindungen. Der Zugang auf Port 502 wird im Beispiel auf die erlaubte
HA-Quell-IP begrenzt. Es gibt keine Portweiterleitung ins Internet.

Auf derselben UART keinen weiteren unabhängigen `modbus_controller`, `modbus_server`
oder Streamserver starten. Das Beispiel verwendet den direkten UART-Modus der
Bridge. Falls zusätzliche lokale ESPHome-Sensoren benötigt werden, ist die im
Upstream dokumentierte **Shared-Modbus-Hub**-Konfiguration erforderlich; ihre
Richtungssteuerung und Antwortfrist werden am Hub statt an der Bridge eingestellt.
Unabhängige Regler dürfen keine konkurrierenden Deye-Steuerbefehle senden.

## In der Energiezentrale eintragen

Unter **Inbetriebnahme → Geräte → Gerät hinzufügen** den Speicher/Hybrid-
Wechselrichter und das Deye-Modbus-Plugin wählen:

| Plugin-Einstellung | Wert |
| --- | --- |
| `host` | IP oder Hostname des ESP |
| `port` | `502`, passend zu `tcp_port` |
| `unit_id` | Modbus-Adresse des Deye, häufig `1`; die Bridge reicht sie weiter |
| `remote_control` | Zunächst **aus** |
| Gemeinsame Netzzählerquelle | Nur auswählen, wenn dieser Deye den gemeinsamen Netzanschlusswert liefern soll |

Zunächst SoC, PV-, Batterie-, Netz- und Hausleistung mit dem Deye-Display vergleichen.
Für die Plugin-Messwerte die entsprechenden allgemeinen HA-Sensorfelder leer lassen.
Bestehende ausgewählte Sensoren haben weiterhin Vorrang.

Erst danach bei kompatibler Deye-Firmware `remote_control` freigeben und
Laderichtung, Begrenzung, SoC-Abschaltung und Automatik-Rückgabe am Gerät prüfen.
Die Bridge schreibt die Remote-Register nicht selbstständig und implementiert
keinen zusätzlichen Batterie-Watchdog. Der **300-Sekunden-Watchdog im Deye** wird
vom Plugin gesetzt und muss bei unterbrochener Verbindung die Remote-Regelung
beenden. Die unterbrechungsfreie Funktion dieser Kombination ist noch nicht an
realer Hardware bestätigt.

## Wenn keine Werte ankommen

| Beobachtung | Prüfung |
| --- | --- |
| TCP-Verbindung abgewiesen | ESP-IP, Port 502, Erreichbarkeit und `deye_bridge_ha_client_cidr` prüfen. |
| Verbindung steht, aber Timeout | Deye-Port, Unit-ID, 9600/8N1, A/B-Zuordnung und DE-/RE-Steuerung prüfen. Eine falsche Verkabelung lässt sich nicht mit größeren Timeouts beheben. |
| Kurze Antworten funktionieren, Messblock nicht | UART-Puffer 512 Byte, WLAN-Stabilität und RTU-Antwortfrist prüfen; kein paralleler UART-Zugriff. |
| Lesen geht, Schreiben nicht | HA-Quell-IP muss in `trusted_networks` liegen; außerdem Deye-Remote-Firmware und Steuerfreigabe prüfen. |
| „Expected Deye 12 kW ... profile“ | Gerätetyp und Registerprofil passen nicht; nicht mit einem anderen Profil weiterschreiben. |
| Fremde aktive Remote-Regelung | Anderen Regler beenden oder den Deye-Watchdog ablaufen lassen; das Plugin übernimmt keine fremde Steuerung. |

## Quellen und Prüfumfang

- [Bridge-Anleitung, Stand 2026.10.2](https://github.com/rosenrot00/esphome_modbus_bridge/blob/9119ba5b036af146eb8fb1e4a59aef29d4f63089/README.md)
- [Bridge-Protokollimplementierung](https://github.com/rosenrot00/esphome_modbus_bridge/blob/9119ba5b036af146eb8fb1e4a59aef29d4f63089/components/modbus_bridge/modbus_bridge.cpp)
- [Bridge-Konfigurationsschema](https://github.com/rosenrot00/esphome_modbus_bridge/blob/9119ba5b036af146eb8fb1e4a59aef29d4f63089/components/modbus_bridge/__init__.py)
- [Deye-Plugin: Anschluss und Firmwaregrenzen](../PLUGINS.md#deye-sun-12k-sg04lp3-eu-direkt-über-modbus)

Die Eignung ist eine Protokoll-/Quellcodeprüfung mit erfolgreicher
Konfigurationsvalidierung und Codegenerierung. Eine Firmware wurde nicht kompiliert.
Diese Prüfungen ersetzen weder den Test der konkreten Elektronik noch einen
Firmware-Build und einen Test am Wechselrichter.
