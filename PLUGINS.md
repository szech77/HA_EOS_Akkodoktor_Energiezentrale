# Hardware-Plugins

## Victron Venus MQTT / HACS

`victron_ha` übernimmt Messwerte und optional bestätigte ESS-Mode-2-Steuerung
über **Victron Venus MQTT** aus HACS. Das Plugin startet lesend; Entitäten,
Grenzen und Rückgabewerte werden explizit zugeordnet.
[Einrichtung, Entitätszuordnung und Grenzen](VICTRON.md).

Die Energiezentrale entdeckt lokale Plugins beim Start aus
`custom_components/eos_energiezentrale/energy/plugins/`. Ein Registry-Eintrag im
Controller ist nicht nötig. Änderungen an installiertem Python-Code werden nach
Neustart von Home Assistant wirksam. Fronius, NRGkick und die beiden generischen
HA-Plugins nutzen denselben Vertrag. Vorhandene IDs `fronius`, `nrgkick` und `none`
bleiben erhalten.

## Einrichtung in Home Assistant

Unter **Einstellungen → Geräte & Dienste → EOS Energiezentrale → Konfigurieren**:

1. **Geräte → Gerät hinzufügen:** Speicher/Hybrid-Wechselrichter, reinen
   PV-Wechselrichter oder Wallbox auswählen.
2. Für genau dieses Gerät ein installiertes Plugin wählen. Anschließend erscheinen
   dessen eigene Felder, einschließlich Entitätsauswahl, Auswahllisten und Schaltern.
3. Namen und stabile ID vergeben, Plugin konfigurieren und speichern. Die Seite
   **Geräte** zeigt alle bereits eingerichteten Geräte mit ihrem Namen und einem
   Pfeil zum Öffnen; neue Installationen starten mit leerer Liste. Unter der Liste
   steht **Gerät hinzufügen**. Einen vorhandenen Eintrag auswählen, um ihn zu
   bearbeiten. Die Bearbeitung erlaubt auch den Wechsel des Plugins;
   die bisherigen Plugin-Parameter werden dabei nicht in das neue Plugin übernommen.
   **Dieses Gerät entfernen** in der Plugin-Auswahl markieren und im folgenden
   Dialog **Entfernen bestätigen** aktivieren. Dies entfernt nur das ausgewählte
   Gerät aus der Integration. Ohne Bestätigung kehrt der Dialog zur Liste zurück.

Beim ersten Einrichten können mehrere Speicher und PV-Wechselrichter nacheinander
angelegt werden; **Weiter** führt zu den technischen Grenzen. Fahrzeuge/Wallboxen
lassen sich danach in den Optionen hinzufügen. Bestehende einzelne Speicher und
Fronius-Untergeräte erscheinen automatisch in der Liste; bis zur ersten gespeicherten
Geräteänderung wird die bestehende Konfiguration weiterverwendet. Die bisherigen
einzelnen Hardwarefelder bleiben für bestehende Konfigurationsclients kompatibel.

Die Geräteliste ist herstellerunabhängig: Fronius-Modbus und generische
HA-Speicher können gemeinsam betrieben werden. Für reine PV-Wechselrichter gibt es
ein direktes Fronius-Modbus-Plugin sowie ein generisches HA-Plugin mit PV- und
vorzeichenbehafteter AC-Leistung. Neue lokal installierte Plugins erscheinen in
der passenden Geräteart automatisch. Ein Hybrid-Wechselrichter mit Batterie wird
einmal als Speicher angelegt, um PV-/AC-Leistung nicht doppelt zu zählen.

Genau ein Gerät darf als Quelle des gemeinsamen Netzanschlusswerts markiert sein.
Die gewählte Plugin-Konfiguration muss diesen Wert anbieten. Bei Fronius steuert
dieser Schalter die Abfrage des Gateway-Zählers; die anderen Fronius-Geräte lesen
keinen weiteren Netzzähler. Alternativ bleibt der vorhandene allgemeine
Netzsensor konfiguriert. Allgemeine Quellsensoren haben weiterhin Vorrang.
PV-Leistungen werden summiert; Hausverbrauch wird nur bei vollständigen
AC-Messungen aller Geräte plus Netzleistung abgeleitet. Ein generischer Speicher
kann PV-, AC- und Netzleistung optional ebenfalls als Plugin-Messwerte liefern.
Fehlende Quellen bleiben in der UI als fehlende Konfiguration erkennbar.

Es sind bis zu acht Speicher/PV-Geräte möglich. Mehrere Batterien benötigen
jeweils ihre Kapazität und maximale Lade-/Entladeleistung. Das gemeinsame Budget
aus **Technische Grenzen** gilt zusätzlich. Meldet ein Speicher-Plugin aktuelle
Leistungsgrenzen, begrenzen diese die Zuteilung ebenfalls. Bei gemischten Plugins
werden vor jeder Verteilung zunächst neutrale Grenzen auf allen Speichern bestätigt;
reine PV-Plugins besitzen keine Schreibmethoden. Bei Fehlern wird die Automatik-Rückgabe
auf allen Speichern versucht. Die letzte Batterie kann entfernt werden; ohne
Speicher bleibt die Speichersteuerung unbenutzbar und die Verbindungsansicht zeigt
einen Konfigurationshinweis.

**Planungsgrenze:** Mehrere Batterien werden weiterhin als gemeinsame
EOS-Speicherressource modelliert. Unterschiedliche SoC-Stände und Leistungsgrenzen
können dazu führen, dass eine geplante Gesamtleistung nicht erreichbar ist. Dies
wird in den Verbindungen als Näherung gekennzeichnet. Die Geräteliste erzeugt
keine unabhängigen EOS-Pläne pro Batterie.

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
| `grid_meter_host` | Optionaler Host des Zähler-Gateways; leer verwendet den Hauptwechselrichter. Kann auch ein anderer Wechselrichter der Anlage sein. |
| `grid_meter_port` | Gateway-Port; Standard 0 übernimmt den Port des Hauptwechselrichters. |
| `battery_capacity_wh` | Kapazität der Batterie am Hauptwechselrichter in Wh, passend zu ihrer SoC-Skala. Bei mehreren Batterien erforderlich; 0 bedeutet im Einzelbetrieb unverändert die Kapazität aus EOS verwenden. |
| `additional_inverters` | JSON-Objekt mit bis zu sieben zusätzlichen Wechselrichtern. Standard `{}` erhält den Einzelbetrieb. Definition siehe unten. |

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

### Mehrere Wechselrichter und Batteriespeicher

`host` bezeichnet weiterhin den **Hauptwechselrichter mit Batterie**. Unter
`additional_inverters` werden weitere Geräte anhand eindeutiger Namen angegeben.
Jedes Gerät besitzt einen eigenen `host`, optional `port` (Standard 502) und
`unit_id` (Standard 1). `battery: false` ist der Standard für reine PV-Geräte;
`battery: true` verlangt zusätzlich `capacity_wh`. Bei mehreren Batterien muss
auch `battery_capacity_wh` des Hauptgeräts gesetzt sein. Maximal acht
Wechselrichter einschließlich des Hauptgeräts sind erlaubt.

Beispiel: drei Wechselrichter, davon zwei mit Batterie:

```json
{
  "host": "192.0.2.10",
  "battery_capacity_wh": 10000,
  "grid_meter_enabled": true,
  "grid_meter_unit_id": 200,
  "additional_inverters": {
    "dach": {"host": "192.0.2.11", "battery": false},
    "garage": {"host": "192.0.2.12", "battery": true, "capacity_wh": 20000}
  }
}
```

`additional_inverters` bleibt als bisheriges JSON-Format lesbar. Neue Geräte
werden stattdessen einzeln unter **Geräte → Gerät hinzufügen** eingerichtet;
die allgemeine Liste erlaubt unterschiedliche Plugins pro Gerät. Beim Speichern
wird nur die Konfiguration geprüft; es werden
keine Verbindungen oder Steuerbefehle ausgelöst. Doppelte Kombinationen aus
Host, Port und Unit-ID sind unzulässig. Unterschiedliche DNS-/IP-Aliase desselben
physischen Geräts dürfen ebenfalls nicht mehrfach eingetragen werden.

Reine PV-Wechselrichter werden ausschließlich gelesen und brauchen kein
Speichermodell 124. Die PV-Leistung stammt aus MPP1/MPP2 in Modell 160 oder,
wenn dieses fehlt, aus `DCW` des SunSpec-Wechselrichtermodells 101–103/111–113.
Vorhandene, aber ungültige MPPT-Daten werden nicht durch andere Quellen ersetzt.
Ein als PV-Gerät konfigurierter Wechselrichter mit erkennbarer Batterieaktivität
wird als unvollständige Messquelle behandelt; seine Batterie muss konfiguriert werden.
Es gelten die offiziellen [SunSpec-Invertermodelle](https://github.com/sunspec/models/tree/master/json)
und die vorhandenen Fronius-Registerkonventionen; reine 700er-Modelle bleiben ausgeschlossen.

Die gemeinsame PV-Leistung ist die Summe aller PV-Messungen. Der Hausverbrauch
ist **Summe aller AC-Wechselrichterleistungen plus vorzeichenbehafteter Netzleistung**.
Akkuentladung und Netzladung sind bereits in den AC-Leistungen enthalten. Der
gemeinsame Zähler wird pro Poll einmal gelesen; mit `grid_meter_host` und
`grid_meter_port` kann sein Gateway auf einem anderen Gerät liegen. Ein fehlender
Teilwert macht die entsprechende Summe unbekannt. Ein ausgefallenes PV-Gerät
wird nicht als 0 W bewertet; weiterhin gültige Speicherwerte bleiben verfügbar.

Mehrere Batterien bilden **einen Speicherpool mit einer EOS-Ressource**. Ihr SoC
ist nach den eingestellten Kapazitäten gewichtet; Lade- und Entladeleistung werden
summiert. Im Beispiel ergeben 20 % von 10 kWh und 80 % von 20 kWh einen gemeinsamen
SoC von 60 %. Die Gesamtleistungsgrenzen unter **Grenzen** sind Budgets für den
gesamten Pool. Sie werden zusammen mit der Summenkapazität und den SoC-Grenzen
auch bei ausgeschalteter Steuerfreigabe an die vorhandene EOS-Speicherressource
übertragen und zurückgelesen. Die Ressource muss bereits in EOS existieren.
Kapazität und Kostenerfassung verwenden dieselbe Gruppenkapazität; separate
EOS-Speicherpläne oder Kostenbestände je physischer Batterie werden nicht angelegt.
Die gemeinsamen Lade-/Entladewirkungsgrade bleiben aus EOS oder den manuellen
Bilanzparametern einstellbar. Bei unterschiedlichen Batterien sind passende
gemeinsame Wirkungsgrade als Näherung zu verwenden.

Vor Gruppenbefehlen werden alle Batterien frisch gelesen. Ladeleistung wird nach
freier Kapazität, Entladeleistung nach Energie oberhalb der SoC-Untergrenze verteilt,
jeweils begrenzt durch die Gerätereferenzleistung. Die SoC-Grenzen gelten für jede
Batterie einzeln, auch die höhere Grenze bei PV-Ladeunterstützung. Für normalen
Eigenverbrauch wird eine gemeinsame Richtung und ein gemeinsames Leistungsbudget
verwendet. Jede Hybridanlage muss für die passende Eigenverbrauchsregelung am
gemeinsamen Netzanschlusspunkt eingerichtet sein. Unabhängige parallel schreibende
Regler sind weiterhin unzulässig. Ein Ladestart mit Speicherunterstützung verlangt
genügend freigegebene Gruppenleistung vor dem Einschalten des Fahrzeugs.

Bei Richtungswechsel oder verändertem Steuerzustand werden zunächst neutrale
Grenzen auf allen Batterien bestätigt. Bei Umverteilung werden Reduzierungen vor
Erhöhungen geschrieben. Scheitert eine Gruppensteuerung, wird die Rückgabe an
Automatik auf allen Speichergeräten versucht; Fehler werden weiterhin gemeldet.
Ohne vollständigen Speicher-SoC oder Speichertelemetrie wird keine Teilgruppe als
vollständiger Speicher gesteuert. Unter **Einstellungen → Verbindungen** erscheinen
Anzahl, Kapazität und die Messwerte jedes Geräts. Die Mehrgeräte-Funktion ist mit
lokalen Modbus-TCP-Geräteemulatoren geprüft; ein Test an realer Hardware steht aus.

### Messwerte und Steuerung

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
| `pv_entity` | Summe der PV-Leistung aller konfigurierten Wechselrichter; MPP1/MPP2 aus SunSpec 160, bei reinen PV-Geräten alternativ DCW aus dem Wechselrichtermodell. Aktuelle DC-Leistung in W, kein kumulativer kWh-Zähler. |
| `grid_entity` | AC-Wirkleistung des konfigurierten Primärzählers; Bezug positiv, Einspeisung negativ. |
| `house_entity` | Gesamter Hausverbrauch einschließlich Fahrzeugen und Wärmepumpe: Summe der AC-Leistungen aller konfigurierten Wechselrichter plus vorzeichenbehaftete Netzleistung. SunSpec 101–103 und 111–113 werden unterstützt. |

Für Netz- und Hausleistung muss die Zählerabfrage aktiviert und der Primärzähler
am Netzanschlusspunkt vorhanden sein. Die Hausbilanz setzt voraus, dass die
AC-Leistung aller konfigurierten Wechselrichter die Erzeuger am Messpunkt erfasst.
Weitere Fronius-Geräte in `additional_inverters` eintragen. Bei anderen, nicht
erfassten Erzeugern einen eigenen Hausverbrauchssensor wählen;
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

## Deye SUN-12K-SG04LP3-EU direkt über Modbus

Das Plugin **Deye SUN-12K-SG04LP3-EU / Modbus TCP gateway** (`deye_modbus`)
liest den dreiphasigen 12-kW-Niedervolt-Wechselrichter lokal. Eine zusätzliche
Home-Assistant-Integration oder HA-Mess-/Steuerentitäten sind nicht erforderlich.
Benötigt wird ein **echtes Modbus-TCP↔Modbus-RTU-Gateway** zum passenden seriellen
Monitoring-Anschluss des Wechselrichters. Das Protokoll nennt 9600 Baud, 8 Datenbits,
keine Parität, 1 Stoppbit; die Gateway-Einstellung und die Geräteadresse müssen
zur tatsächlichen Wechselrichtereinstellung passen.

Die RJ45-Buchse mit Aufschrift „Modbus“ ist kein Ethernet-Anschluss. Das aktuelle
Deye-Handbuch bezeichnet sie als reserviert; ältere Handbuchstände zeigen eine
RS485-Belegung mit dem Hinweis, dass der Anschluss bei manchen Hardwareversionen
nicht nutzbar ist. Vor Beschaffung/Verdrahtung des Gateways den für die konkrete
Hardwareversion freigegebenen Monitoring-Anschluss bei Deye bestätigen lassen.
BMS-, Meter- und Parallel-Anschlüsse nicht als gleichwertige Netzwerkbuchsen behandeln.
Ein transparenter TCP-Serialserver mit unveränderten RTU-Frames ist für dieses
Plugin ebenso wenig geeignet wie ein ausschließlich Solarman-V5-fähiger Logger
auf Port 8899. Dieses Plugin implementiert standardisiertes Modbus TCP mit MBAP.
Cloud-API, Solarman-V5 und direkt angeschlossene USB-Serielladapter sind nicht enthalten.

Als ESPHome-Gateway ist die
[Modbus Bridge von rosenrot00](https://github.com/rosenrot00/esphome_modbus_bridge)
vom Protokoll her geeignet: echte MBAP↔RTU-Umsetzung, FC03/FC16, passende
Puffergrenzen sowie Erhalt von Unit- und Transaktions-ID. Geprüfter Stand:
2026.10.2 (`9119ba5b036af146eb8fb1e4a59aef29d4f63089`). Ein Test mit ESP und Deye
steht aus. [Anleitung, Verdrahtungsvoraussetzungen und ESPHome-Beispiel](docs/deye-esphome-gateway.md).

Einrichtung: **Inbetriebnahme → Geräte → Gerät hinzufügen → Speicher /
Hybrid-Wechselrichter → Deye ...**. Für einen Deye ohne Batterie die gleichnamige
ausschließlich lesende Variante unter **PV-Wechselrichter ohne Batterie** wählen.

| Parameter | Bedeutung |
| --- | --- |
| `host` | Lokale IP / Hostname des TCP↔RTU-Gateways, nicht die Cloud-Adresse. |
| `port` | Standard-Modbus-TCP-Port, Vorgabe 502. |
| `unit_id` | Eingestellte Modbus-Adresse des Deye, Vorgabe 1. |
| `grid_meter_enabled` | Netz-/Hauswerte bereitstellen. In der Geräteliste bestimmt dies die Auswahl der gemeinsamen Netzzählerquelle. |
| `grid_meter_invert` | Vorzeichen der Netzleistung bei abweichender Messrichtung umkehren; kanonisch ist Bezug positiv. |
| `remote_control` | Speichersteuerung für nachweislich kompatible Remote-Firmware freischalten; Vorgabe **aus**, Messwerterfassung funktioniert unabhängig davon. |
| `grid_discharge_supported` | Erzwungene Batterieeinspeisung ausdrücklich erlauben, Vorgabe aus. |
| `minimum_soc`, `maximum_soc` | Zusätzliche individuelle SoC-Grenzen, Vorgabe 10 / 100 %. Die aktuellen Grenzen der Energiezentrale gelten zusätzlich, ebenso die höhere PV-Ladeuntergrenze. |

Die allgemeinen Sensorfelder für PV, Netz und Haus können leer bleiben. Ein
weiterhin ausgewählter HA-Sensor hat Vorrang. Gelesen werden SoC 588,
vorzeichenbehaftete DC-Batterieleistung 590, PV1/PV2 672/673 und die
32-Bit-Leistungen für Netz 625/690, Wechselrichter-AC 636/694 und nativen
Hausverbrauch 653/659 (jeweils Low-/High-Word). Batterieentladung ist positiv;
negative Batterieleistung wird als Ladung ausgegeben. Messwerte werden nicht aus
fehlenden Registern als 0 erfunden. Die Identifikation verlangt LV-Dreiphasentyp,
12000 W Nennleistung, zwei MPPT und höchstens einen Batterieeingang. Andere
Deye-Typen, insbesondere HP3 oder einphasige Geräte, benötigen ein eigenes Profil.

**Remote-Steuerung:** Die Firmware muss Register 1100/1101 sowie 1104/1105/1109
gemäß dem verlinkten V105-Protokoll unterstützen. Bei freigeschalteter Steuerung
wird ein 300-Sekunden-Watchdog bestätigt, Batterie-Leistungsregelung gewählt und
der Remote-Modus zuletzt aktiviert. Jeder Befehl erneuert den Watchdog.
Leistung wird mit 0,1 % der geprüften 12 kW quantisiert (12 W je Schritt), stets
zum kleineren Betrag. Negative Sollleistung lädt, positive entlädt. PV läuft bei
der gewählten Batterieseitenregelung weiter. Normale Eigenverbrauchsregelung
passt den Batteriesollwert pro Regelzyklus anhand der aktuellen Netz- und
Batterieleistung an; sofortige, unterbrechungsfreie Nullbezugsregelung ist damit
nicht garantiert. Ohne eigene Netzzählerquelle wird der gemeinsame frische Bedarf
der Energiezentrale verwendet. Netzladung/-einspeisung verwenden explizite Sollwerte.

Lade-/Entladeleistung wird durch die konfigurierten Budgets, Register 108/109
und bei Lithiumkonfiguration die BMS-Stromfreigaben 212/213 begrenzt.
Fehlende Batterietelemetrie verhindert neue Speicherbefehle. Ohne erfolgreiche
Rückbestätigung wird kein Erfolg gemeldet. Eine fremde aktive Remote-Regelung
wird nicht übernommen. Nach einem Prozessabbruch kann deshalb bis zum Ablauf des
Watchdogs eine aktive alte Remote-Regelung gemeldet werden. Die normale Rückgabe
bestätigt Remote-Modus 0; fehlgeschlagene Rückgaben bleiben sichtbar.
Es werden keine ToU-Zeitpläne, Netzstandards oder Batterie-Grundparameter geändert.
Bei älterer oder abweichender Firmware bleiben die Messwerte nutzbar, während
Remote-Schreibbefehle abgewiesen werden. Kein automatischer EEPROM-Fallback.

Die Implementierung ist mit einem lokalen Modbus-TCP-Geräteemulator, einschließlich
gemischter Deye-/Fronius-Anlagen, geprüft. Ein Test am konkreten Deye und seiner
Firmware steht aus; vor Freigabe der Remote-Steuerung sind Richtung, Skalierung,
SoC-Verhalten, Watchdog und Rückgabe am Gerät zu bestätigen.

Quellen: [Deye-Betriebshandbuch V3.3](https://www.deyeinverter.com/deyeinverter/2026/03/19/BManualSUN-5-12K-SG04LP3-EU20260319en.pdf),
[Deye-Dreiphasenprotokoll V105.4, insbesondere S. 3–5, 33–38 und 41](https://github.com/user-attachments/files/22990113/MODBUS.RTU.V105.4-20240814.pdf).

## go-e Charger direkt über die lokale HTTP-API v2

Das Plugin **go-e Charger – lokale HTTP-API v2** (`goe_http_v2`) steuert einen
lokal erreichbaren go-e Charger über `/api/status` und `/api/set`. Die API-Version
steht ausdrücklich im auswählbaren Namen. Benötigt werden die in der go-e-App
freigeschaltete **lokale HTTP-API v2** und Firmware **051.4 oder neuer** für das
verwendete CSV-Statusfilterformat. Ältere Geräte mit ausschließlich HTTP-API v1
benötigen ein anderes Plugin. Cloud-API und Cloud-Token werden nicht verwendet.

Einrichtung: **Inbetriebnahme → Geräte → Gerät hinzufügen → Wallbox mit
Fahrzeug → go-e Charger – lokale HTTP-API v2**. Danach Fahrzeugdaten und
Plugin-Felder ausfüllen. Mehrere go-e Charger können als getrennte Fahrzeuge mit
eigenen URLs und EOS-Ressourcen angelegt werden.

| Parameter | Bedeutung |
| --- | --- |
| `url` | Lokale Basisadresse, z. B. `http://192.168.1.50`, ohne `/api`, Pfad, Zugangsdaten oder Cloud-Token. |
| `phase_switching` | 1-/3-Phasenumschaltung für unterstützte Hardware ausdrücklich freigeben; Vorgabe aus. Verfügbarkeit wird zusätzlich aus API-Messungen und Phasensteuerung geprüft. |
| `nominal_voltage` | Nennspannung zwischen Phase und Neutralleiter für die EOS-Leistungsrechnung, Vorgabe 230 V. Keine schwankenden Momentanwerte als neue Gerätenennleistung synchronisieren. |

Eine separate go-e-Integration und Sensoren/Steuerentitäten für Ladeleistung,
Strom, Ladefreigabe und Phasen sind nicht erforderlich. Der Fahrzeug-SoC wird
von diesen Basis-API-Feldern nicht geliefert und muss bei Bedarf aus einer eigenen
Fahrzeugquelle kommen. Die bestehende UI zeigt eine fehlende SoC-Quelle an.

`nrg[11]` wird gemäß API-v2-Format als **Watt** gelesen; es erfolgt keine
API-v1-Skalierung. `car` unterscheidet kein Fahrzeug, verbunden/wartend,
ladend und Fehler. Ein abgeschlossenes Laden (`car=4`) bedeutet weiterhin ein
angeschlossenes Fahrzeug. `err` wird zusätzlich ausgewertet. Fehlende oder ungültige
Messwerte bleiben unbekannt, insbesondere wird ein ausgefallener Charger nicht
als 0 W verbucht. Als optionaler Ladepunkt wird er bei Ausfall oder fehlendem Auto
für die EOS-Ladeplanung inaktiv behandelt.

Maximalstrom entsteht konservativ aus `var` (11 kW / 16 A oder 22 kW / 32 A),
`ama`, angeschlossenem Typ-2-Kabel `cbl` und Adapterkennung `adi`.
Phasenverfügbarkeit wird aus `pha` beziehungsweise den vorhandenen Spannungen
bestimmt; `psm`, `pnp` und gegebenenfalls `fsp` liefern Phasenmodus/-rückmeldung.
Ohne zuverlässige Grenzen wird kein Ladeprofil erfunden. Die gemeinsame Regelung
arbeitet mit **6 A Mindeststrom**; `mca` muss deshalb 6 melden. Bei fehlendem oder
abweichendem Mindeststrom bleiben Messwerte sichtbar, der Ladestart wird blockiert.
Die zusätzliche Maximalstromgrenze des Fahrzeugs in der Energiezentrale gilt weiter.
Diese Daten beschreiben die Ladestation, nicht automatisch die maximale Ladeleistung
des fahrzeugeigenen Ladegeräts.

Steuerung erfolgt ausschließlich über `amp` (ganze Ampere), `frc=1` (Pause),
`frc=2` (Freigabe) und bei aktivierter Phasenumschaltung `psm=1`/`2` (1-/3-phasig).
Schreiben verlangt sowohl eine positive API-Antwort als auch passende zurückgelesene
Werte. Die go-e-Ladelogik aktualisiert ihre Ergebnisse etwa einmal pro Sekunde;
das Plugin wartet begrenzt auf die Bestätigung. Vor dem Einschalten werden
Kabel-/Adaptergrenzen, Fahrzeuganwesenheit und Phasen erneut geprüft. Strom wird
vor Freigabe gesetzt. Eine fehlgeschlagene Vorgabe löst einen bestätigten
Pauseversuch aus; nicht bestätigte Pausen bleiben Steuerfehler.

Die Phasenumschaltung pausiert zuerst, verlangt danach zwei frische stromfreie
Messungen mit mindestens drei Sekunden Abstand und prüft neben höchstens 30 W
auch maximal 0,2 A je Phase. Anschließend wird die Einstellung geschrieben und
auf die Phasenrückmeldung gewartet, bevor wieder geladen werden darf. Eine offene
Umschaltung blockiert den Ladestart; fehlende Bestätigung wird nach 45 Sekunden als
Fehler gemeldet. Ein zweiphasiger Netzanschluss wird vom 1-/3-Phasenmodell nicht
als vollständige Ladequelle behandelt. Bei deaktivierter automatischer Umschaltung
einen passenden festen Phasenmodus in der go-e-App einstellen.

Die Energiezentrale verwendet eine erzwungene Freigabe (`frc=2`), die native
Ladezeitpläne übersteuern kann. Für denselben Ladepunkt nur einen schreibenden
Energieregler verwenden. Die lokale API im geschützten LAN betreiben;
keine Internet-Portweiterleitung einrichten. Das Plugin verändert keine WLAN-,
RFID-, Cloud- oder Sicherheitskonfiguration und umgeht keine elektrischen
Schutzfunktionen der Wallbox.

Getestet mit lokalem HTTP-Geräteemulator und den nativen HA-Konfigurationsformularen.
Ein Test mit realem go-e Charger und konkreter Firmware steht aus.

Quellen: [Hersteller: lokale HTTP-API v2](https://github.com/goecharger/go-eCharger-API-v2/blob/main/http-en.md),
[API-Felder](https://github.com/goecharger/go-eCharger-API-v2/blob/main/API_KEYS_FIRMWARE/apikeys-en.md),
[Phasensteuerung `psm`](https://github.com/goecharger/go-eCharger-API-v2/blob/main/modbus-en.md),
[Aktualisierung der Ladelogik](https://github.com/goecharger/go-eCharger-API-v2/blob/main/introduction-en.md).

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

Die maximale nutzbare Phasenzahl ergibt sich aus `connector.phase_count`, den
erkannten `grid.phases` und der erlaubten Phaseneinstellung. Die Ladeleistung
wird aus Phasenzahl, `grid.voltage` und dem kleinsten Wert von Geräte-, Adapter-
und konfigurierter Stromgrenze berechnet. Beispielsweise ergibt ein einphasiger
10-A-Adapter bei 230 V höchstens 2.300 W. Das Plugin meldet diese Grenzen im
Status. EOS erhält `max_charge_power_w`, `min_charge_power_w` und passende
`charge_rates`; ein eigenes Feld für maximale Phasenzahl bietet das geprüfte
EOS-Schema nicht. Die Synchronisierung liest die EOS-Konfiguration zurück,
erhält andere Fahrzeuge und läuft in Home Assistant im Hintergrund. Neue
EOS-Ladepläne werden erst nach Bestätigung der Grenzen verwendet.

Bei abgestecktem Fahrzeug oder nicht erreichbarem NRGkick bleibt das Fahrzeug
in der Ansicht ausgegraut. EOS erhält `charge_rates: [0.0]` und gelöschte
Ladeziele, während die erforderliche positive Leistungsgrenze erhalten bleibt.
Der gespeicherte Zeitplan bleibt lokal erhalten und wird beim Wiederverbinden
mit den dann aktuellen Anschlussgrenzen wiederhergestellt. Dafür muss das
Fahrzeug bereits als eigene Ressource in EOS konfiguriert sein. Fehler dieser
Wallbox schalten Speicherregelung und andere erreichbare Fahrzeuge nicht ab.
Ein frischer gemeinsamer Netzleistungsmesswert und konservative Reservierungen
begrenzen weiterhin die Gesamtlast. Fehlende Fahrzeugleistung bleibt für die
Bilanz unbekannt und wird nicht als gemessener Nullverbrauch gespeichert.

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
Stop bleibt als eigener Hinweis sichtbar und wird bei aktiver Regelung erneut
versucht. Ein Kommunikationsausfall kann auch ein weiterhin ladendes Gerät
betreffen. Getestet wird gegen einen
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

- Eine konkrete Unterklasse von `BatteryDriver`, `WallboxDriver` oder `InverterDriver`.
- `info = PluginInfo(identifier, name, kind, api_version=2)` mit stabiler ID,
  Anzeigename und Art `battery`/`wallbox`/`inverter`.
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

Reine PV-Wechselrichter verwenden `PluginInfo(..., kind="inverter")` und
implementieren ausschließlich `_read(self, states, now) -> InverterReading`.
`InverterReading.measurements` enthält deklarierte `Measurement`-Werte für `solar`,
`inverter_ac` und optional `grid`. `inverter_ac` ist vorzeichenbehaftete AC-Leistung
des einzelnen Wechselrichters, kein Hausverbrauch. Die öffentliche Methode `read`
bleibt auch hier unverändert; Schreibmethoden sind nicht Teil dieses Vertrags.
Die IDs der Plugins sind je Geräteart eindeutig; `fronius_modbus` und `generic`
dürfen daher sowohl als Speicher- als auch als PV-Plugin vorkommen.

`provides_site_consumption = True` kennzeichnet eine gemessene Haus-Gesamtleistung
der Anlage in `house_total`. Die gewählte Netzquelle darf damit einen direkten
Hausverbrauch liefern. Ohne diese Kennzeichnung wird eine geräteweise aus Netz
und Wechselrichterleistung abgeleitete Messung nicht als Standortsumme verwendet.

Speicher können `power_limits(self, states)` implementieren und aktuelle
Hardwaregrenzen als Tupel `(max_charge_w, max_discharge_w)` melden. `None` verwendet
die je Gerät konfigurierten Grenzen. Das Lesen darf keine Steuerbefehle auslösen;
ungültige Grenzen verhindern neue Gruppenbefehle. Fronius-Modbus und der generische
HA-Speicher melden ihre Register- beziehungsweise Leistungsentitätsgrenzen.

`BatteryCommand` enthält zusätzlich optionale Angaben für Speicherpools:
`min_soc`, `max_soc`, `net_demand_w` und `required_discharge_w` (Standard 0).
Die beiden SoC-Werte sind pro Gerät anzuwendende Entlade-/Ladegrenzen.
`net_demand_w` beschreibt den gemeinsamen Bedarf vor Speicherunterstützung;
positiv bedeutet Entladebedarf, negativ Ladeüberschuss. `required_discharge_w`
verlangt eine vor dem PV-Ladestart verfügbare Gruppenleistung. Einzelgeräte können
diese Angaben weiterhin ignorieren. Ein Plugin mit
`requires_dispatch_context = True` erhält sie vom Controller; fehlender oder
ungültiger Kontext darf keine ungesicherte Gruppensteuerung auslösen.
Ein einzelnes Speicher-Plugin kann mit `uses_dispatch_context = True` dieselben
Angaben anfordern, ohne eine Speichergruppe oder Kapazitätssynchronisation zu melden.
Die allgemeine Geräteliste reicht diese Angaben auch an einzelne Speicher weiter.

`_read` liefert unveränderliche `BatteryReading`- bzw. `WallboxReading`-Werte.
Einheiten sind Prozent, Watt, Ampere, Phasen 1/3 und zeitzonenbehaftete Zeitstempel.
Ungültige, negative oder nicht endliche Messwerte werden als fehlend behandelt,
nicht auf 0 geklemmt. Nicht vertragsgemäße Datentypen führen zu einem Vertragsfehler.
Akkutreiber müssen für jeden vorhandenen Wert den zugehörigen zeitzonenbehafteten
Messzeitpunkt in `BatteryReading.soc_sample`, `charge_sample` bzw. `discharge_sample`
liefern. Fehlende, zukünftige oder 120 Sekunden alte Messwerte werden verworfen;
der Messzeitpunkt darf nicht durch den Zeitpunkt des Leseaufrufs ersetzt werden.
Nur für SoC darf ein Treiber mit `soc_max_age` ein begründetes Meldeintervall bis
höchstens 360 Sekunden angeben (Victron: 360 s). Standard und Leistungsfrist
bleiben 120 Sekunden; auch ein Speicherpool validiert jedes Gerät zuerst einzeln.
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
