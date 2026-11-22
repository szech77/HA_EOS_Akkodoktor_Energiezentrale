<p><img src="custom_components/eos_energiezentrale/energy/web/logo.svg" width="96" alt="EOS Energiezentrale Logo"></p>

# EOS Energiezentrale

Victron-Anlagen über die offizielle **Victron GX**-Integration oder
**Victron Venus MQTT / HACS** anbinden:
[Plugin einrichten](VICTRON.md) (Messwerte und optionale ESS-Mode-2-Steuerung).
Alternativ [Victron GX direkt über Modbus TCP](VICTRON_MODBUS.md) anbinden,
ohne zusätzliche Victron-Integration oder HA-Sensoren.

HACS-Custom-Integration für Akkudoktor EOS mit animiertem Stromfluss, Prognosen,
Speichersteuerung und PV-Überschussladen. Ab Version **0.2.0** läuft die
Energiezentrale direkt in Home Assistant. Der EOS-Server bleibt ein separater Dienst.

## Einblick in die Oberfläche

Die folgenden Screenshots zeigen die aktuelle Oberfläche mit **synthetischen
Beispieldaten**, nicht die Messwerte einer echten Anlage. Sichtbare Geräte und
Prognosen hängen von der eigenen Konfiguration und den verfügbaren Daten ab.
Die Beispieldaten verwenden eine geprüfte Leistungsbilanz; Ladezustände und
Tagesenergien werden aus den Leistungen berechnet. [Modellannahmen](docs/screenshots/README.md#plausibilität-der-beispieldaten).

### Übersicht: Energiefluss, Wetter und Tagesbilanz

Die Übersicht verbindet aktuelle Leistungen und Ladezustände mit dem animierten
Energiefluss. Name und Wert stehen unter dem jeweiligen Symbol. Hat ein Gerät einen
offenen Hinweis, trägt sein Symbol ein Warnzeichen; welcher Hinweis zu welchem
Gerät gehört, legt das Backend fest. Ein Klick auf PV öffnet die Auswertung
**PV-Erzeugung**, auf das Wettersymbol **PV & Wetter**, auf den Speicher die Detailansicht, auf Netz die Auswertung Netz & Einspeisung, auf Haus und Wärmepumpe
die Verbrauchsauswertung, auf das Auto die Fahrzeugseite und auf das EOS-Symbol
in der Mitte die Gesamtbilanz. Der
Link **Leistungsverlauf** unter dem Diagramm öffnet alle Leistungskurven.
Darunter steht in voller Breite der EOS-Plan der nächsten 12 Stunden als bedienbarer
Zeitstrahl und die einklappbare Liste **Was als Nächstes passiert** (mit Anzahl der
Einträge; der Browser merkt sich, ob sie auf- oder zugeklappt ist): geplante Moduswechsel von
Speicher und Fahrzeugen, der erwartete Zeitpunkt für einen vollen Speicher und
für das Erreichen des Ladeziels, jeweils mit dem Netzstrompreis zu diesem
Zeitpunkt. Moduswechsel, die kürzer als 30 Minuten gelten, erscheinen nicht in der
Liste. Bei Speicherwechseln steht, was der Speicher laut EOS-Prognose in der ersten
Stunde tut (lädt mit PV-Überschuss, lädt aus dem Netz, deckt das Haus, hält seinen
Ladestand); der EOS-Modus steht klein darunter. Folgen zwei Wechsel mit derselben
Wirkung aufeinander, erscheint nur der erste. Darunter stehen Tagesverbrauch und Kosten nach Verbrauchern.

![Desktop-Übersicht mit Statusband, Energiefluss, EOS-Plan, nächsten Ereignissen und Heute-Kacheln](docs/screenshots/overview.jpg)

### Hausspeicher: Verlauf und EOS-Plan

Die farbige Zeitleiste zeigt vergangene und geplante Betriebsmodi. Darunter stehen
Lade-/Entladeleistung, PV-Produktion, Ladezustand und Strompreis. Durchgezogene
Linien zeigen Messwerte, gestrichelte Linien die Prognose.

![Hausspeicher mit EOS-Moduszeitleiste, Leistungs-, SoC- und Preisverlauf](docs/screenshots/battery.jpg)

<details>
<summary><strong>E-Auto: Ladeleistung, Ladeziel und Prognose</strong></summary>

Die Fahrzeugansicht beantwortet zuerst, ob das Auto rechtzeitig voll ist: Ein
Ring zeigt Ladestand und Ziel, daneben stehen Abfahrt, die noch fehlende Energie
und was EOS plant (z. B. „5,4 kWh aus PV bis 16:00 und 27,5 kWh Netzladen ab
02:00“). Die Schalter PV-Überschussladen, Schnellladen und Phasenautomatik sowie
die eingeklappten Ladegrenzen wirken sofort und melden „Gespeichert“.

Der **EOS-Ladeplan** bis zur Abfahrt (ohne Abfahrt: 24 Stunden) zeigt die
Ladestandskurve mit Zielzeitpunkt, einen antippbaren Zeitstrahl mit den Abschnitten
PV-Überschuss, Pause, Netzladen und Ziel erreicht sowie eine Liste mit Leistung,
Phasen, Energie, Preis und Kosten je Abschnitt. Darunter vergleicht er die Kosten
des Plans mit sofortigem Laden bei voller Leistung (≈, mit dem PV-Anteil aus der
Prognose). Netzstrom wird mit dem Preis des jeweiligen Intervalls, PV-Strom mit der
Einspeisevergütung bewertet. Das Backend leitet die Abschnitte aus der EOS-Prognose
ab; ein Intervall gilt als Netzladen, wenn mehr als die Hälfte aus dem Netz kommt.
Ist Schnellladen an, ist der Plan „überstimmt“; meldet die Wallbox einen Fehler,
ist er „ausgesetzt“; im Lesemodus dient er „nur zur Anzeige“. Ohne EOS-Kurve für
das Fahrzeug gibt es keine Abschnitte und keinen Kostenvergleich.

Die **Ladeziele** erscheinen als kompakte Zeilen mit Ziel-SoC, Termin und nächster
Abfahrt; das Ziel, das den Plan bestimmt, ist hervorgehoben. **Bearbeiten** öffnet
die Details, neue Ziele starten geöffnet, **Speichern** übernimmt alle Ziele.
Darunter folgen EOS-Lademodi, Wallbox-Leistung, PV-Produktion, SoC und
Bezugspreise.
Auch bei nur einem verwalteten Fahrzeug wird eine vorhandene EOS-SoC-Prognose
angezeigt, einschließlich eines eigenen SoC-Diagramms in der gemeinsamen
Autoübersicht. Ohne passende EOS-Kurve wird der aktuelle gültige SoC für die
nächsten 24 Stunden fortgeschrieben. Bei aktiviertem PV-Laden kann das Backend
anhand verfügbarer PV- und Hauslastprognosen einen Anstieg bis zum PV-Ziel
abschätzen, beim Schnellladen einen Anstieg mit maximaler Ladeleistung bis zum
Ladeziel. Die geschätzte Ladeleistung erscheint dann auch im Leistungsdiagramm:
0 kW, solange keine Ladung zu erwarten ist (Fahrzeug getrennt, Ziel erreicht oder
zu wenig PV-Überschuss), sonst die erwartete Leistung; bei mehreren Fahrzeugen
summiert die Gesamtladeleistung die Fahrzeuge, sofern für alle ein Wert vorliegt.
Ohne PV-Prognose für ein Intervall bleibt die Leistung leer. Geschätzt wird nur bei
freigegebener E-Auto-Ladesteuerung, da sonst niemand die Wallbox nach diesen Modi
regelt. Die Anzeige unterscheidet EOS-Prognose und lokale Schätzung;
aktuelle Messwerte und Regelung bleiben davon unabhängig.
Eine dauerhaft mit 0 % belegte EOS-Kurve wird bei bekanntem positivem
Fahrzeug-SoC als unplausibler Platzhalter behandelt. Der Ersatzverlauf beginnt
dann beim aktuellen SoC und berücksichtigt verfügbare PV-Überschussprognosen.

![E-Auto-Ansicht mit Ladeziel, Schaltern, EOS-Ladeplan samt Kostenvergleich und kompakten Ladezielen](docs/screenshots/vehicle.jpg)

</details>

<details>
<summary><strong>PV & Wetter: Prognose und was EOS daraus macht</strong></summary>

Aktuelle PV-Leistung und Wetter, stündliche Leiste mit Wetter über dem erwarteten
PV-Ertrag, Tageskarten für drei Tage und die Folgen für Speicher, Einspeisung und
Auto. Der bisherige Leistungsverlauf ist über **Verlauf & Diagramme** erreichbar.

![PV & Wetter mit stündlicher Prognose, Tageskarten und „Was EOS daraus macht“](docs/screenshots/pv.jpg)

</details>

<details>
<summary><strong>Auswertung: Verbrauch, Herkunft und Kosten</strong></summary>

Jede Auswertung hat Tag/Monat/Jahr, eine Kernaussage, vier Kennzahlen, den Verlauf
nach Herkunft, Preise & Kosten, „Woher kam der Strom?“ und „Was auffällt“.
Der Preis über der Kostenaufschlüsselung ist der energiegewichtete Mittelwert
aus PV, Speicher und Netz für den gewählten Zeitraum. Die Quellen behalten ihre
jeweiligen Preise. Die Monatsansicht im Beispiel enthält die bisher erfassten
Werte vom 8. und 9. November.

![Monatsauswertung Hausverbrauch mit Durchschnittspreis aller Quellen und Aufschlüsselung der Speicherherkunft](docs/screenshots/usage.jpg)

</details>

<details>
<summary><strong>Gesamtbilanz: Durchschnittspreis und Grundgebühr</strong></summary>

Die Gesamtbilanz schlüsselt Netzbezug, direkten PV-Verbrauch und Speicherstrom
nach Herkunft auf. Grundgebühr und Einspeisevergütung sind eigene Bilanzposten;
sie sind nicht im Durchschnittspreis der verbrauchten Energie enthalten.
Eine tägliche Grundgebühr erscheint mit bis zu sechs Nachkommastellen. Die
Berechnung verwendet den eingegebenen Betrag ohne diese Anzeigerundung.

![Gesamtbilanz mit mittlerem Energiepreis, täglicher Grundgebühr und Kosten nach Herkunft](docs/screenshots/costs.jpg)

</details>

<details>
<summary><strong>Tarifeinstellungen: Monats- oder Tagesgebühr und fester kWh-Preis</strong></summary>

Unter **Einstellungen → Kosten → Netztarif und Grundgebühr** erhält jeder
Tarifwechsel einen Eintrag mit **Grundgebühr ab**. Als Betrag sind Monats- oder
Tagesgebühren möglich, auch mit mehr als fünf Nachkommastellen. Je Eintrag wird
zwischen dynamischem Preissensor und festem Brutto-Arbeitspreis in ct/kWh gewählt.
Die Liste kann vergangene und zukünftige Änderungen enthalten.

Rückwirkende Festpreise bewerten auch vorhandene und bereits entladene Netzanteile
des Speichers anhand ihrer Ladetage und einschließlich der Speicherverluste neu.
Aus älteren Stundenbuchungen rekonstruierte Ladeanteile bleiben als Schätzung
gekennzeichnet. Ohne bekannten Ladetag wird kein später beginnender Tarif
unterstellt; ein Eintrag ohne Beginn deckt auch diese Anteile ab.
Der Tarif für die EOS-Planung wird weiterhin separat in EOS eingestellt.

Die Aufnahme zeigt beispielhaft den Wechsel von Monats- zu Tagesgebühr und einen
zukünftigen Festpreis. Die Beträge sind synthetische Beispiele.

![Tarifliste mit Gültigkeitsdatum, Monats- und Tagesgebühr sowie festem Arbeitspreis](docs/screenshots/settings.jpg)

</details>

<details>
<summary><strong>Handyansicht der Übersicht</strong></summary>

Die Oberfläche passt sich schmalen Bildschirmen an. Hier der obere Bereich der
Übersicht; Tagesbilanz und weitere Informationen folgen darunter beim Scrollen.

<img src="docs/screenshots/mobile.jpg" width="375" alt="Oberer Bereich der mobilen Übersicht mit Statusband, Kennzahlen und Energiefluss">

</details>

## Installation

Für die anschließende EOS-Konfiguration steht unter **Einstellungen → EOS-Assistent**
ein geführter Ablauf bereit: Standort mit optionaler Smartphone-Ortung, PV-Flächen,
Geräteprofile, Tarife, Verbrauch und Planung. Er zeigt eine Vorschau und speichert
die bestätigten Änderungen dauerhaft in EOS. Neue Hardware vorher in der
Home-Assistant-Konfiguration der Integration hinzufügen. [Anleitung und Voraussetzungen](EOS_SETUP.md).

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
   im Lesemodus prüfen. Erst danach über **Steuerung übernehmen** im Statusband alle
   steuerbaren Bereiche oder unter **Einstellungen → System → Gerätesteuerung** nur die
   Speichersteuerung bzw. die E-Auto-Ladesteuerung einschalten.

Alternativ `custom_components/eos_energiezentrale` aus einem Release-Tag nach
`/config/custom_components/eos_energiezentrale` kopieren und HA neu starten. Releases
enthalten das gebaute Panel-Bundle `energy/web/vue/eos-vue.js`. Aus einem Quellbranch
vorher das Frontend bauen (Node.js 24):

```sh
cd frontend
npm ci
npm run build
```

Der Build schreibt das Bundle nach `custom_components/eos_energiezentrale/energy/web/vue/`;
danach den gesamten Ordner `custom_components/eos_energiezentrale` kopieren.
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

Die Anbindung unterstützt auch die neue EOS-Batterieprofilstruktur, etwa im
Add-on-Build `0.3.0.dev2611122196862169`.
[Kompatibilität, Feldzuordnung und Hinweise bei fehlender Bestätigung](EOS_COMPATIBILITY.md).

[Backend-/Frontend-Trennung, Warnungen und Diagnose-Logs](LOGGING.md).

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

Wähle im Sensor-Dialog die tatsächlichen Entitäts-IDs deiner Installation. Bei
einer Neuinstallation sind keine Sensoren vorbelegt; leere Felder werden, soweit
möglich, von den eingerichteten Plugins versorgt. Die Entitäten in der Tabelle sind
nur Beispiele. Beim Bezugspreis wird ohne Sensor oder Plugin automatisch der
aktuelle EOS-Preis einschließlich der dort konfigurierten Aufschläge verwendet.
Das Feld dafür leer lassen; ein ausdrücklich eingetragener, nicht verfügbarer
Sensor wird nicht durch EOS ersetzt. EOS-Preise werden jede Minute aus den
Preisprognosen gelesen, unabhängig davon, ob bereits ein Optimierungsplan vorliegt.
Nur das aktuelle Preisintervall und höchstens zwei Minuten alte Abrufe gelten;
Lücken, fehlende Preise und abgelaufene Intervalle bleiben unbewertet:

| Feld / Schlüssel | Beispiel-Entität | Erwarteter Wert |
|---|---|---|
| PV-Leistung / `pv_entity` | `sensor.pv_power` | Positive Leistung in W oder kW. |
| Gesamter Hausverbrauch / `house_entity` | `sensor.house_power` | Positive Leistung in W oder kW, einschließlich Auto und Wärmepumpe. |
| Netzleistung / `grid_entity` | `sensor.grid_power` | W oder kW; positiv = Bezug, negativ = Einspeisung. |
| Wärmepumpenleistung / `heat_entity` | `sensor.heat_pump_power` | Positive Leistung in W oder kW, einschließlich Standby-Verbrauch. |
| Bezugspreis / `price_entity` | `sensor.electricity_price` | Optional. `EUR/kWh`, `€/kWh`, `ct/kWh` oder `c/kWh`. Ohne Sensor oder Plugin-Preis automatisch aus EOS. |
| Fahrzeug-SoC / `car_soc_entity` | `sensor.ev_soc` | Numerischer Ladezustand, passend zur folgenden Einheit. |
| Fahrzeug-SoC-Einheit / `car_soc_scale` | `factor` (Vorgabe) | `factor`: 0–1, beispielsweise `0.33`; `percent`: 0–100, beispielsweise `33`. |
| Fahrzeugreichweite / `car_range_entity` | `sensor.ev_range` | Optional. Reichweite in `km` oder `mi` (wird in km umgerechnet). Nur für die Anzeige. Mit Fahrzeugliste gilt der Sensor am Fahrzeug (`range_entity`); ist dort keiner eingetragen, wird dieser bei genau einem Fahrzeug verwendet. |

Mit einem Reichweitensensor bildet das Backend aus Reichweite und gemessenem SoC
das Verhältnis Kilometer je Prozent. Es wird nur bei einem gemessenen, nicht
geschätzten SoC ab 10 % neu bestimmt und bleibt bis zur nächsten passenden Meldung
erhalten. Die Auto-Ansicht zeigt die aktuelle Reichweite; liefert das Fahrzeug
gerade keine, wird sie aus dem SoC geschätzt (≈). Unter den SoC-Feldern für
PV-Ladeziel, Schnellladeziel und die Ladeziele steht ein SoC-Schieberegler mit dem
eingestellten SoC und der dazu erwarteten Reichweite (z. B. „70 % · ≈ 294 km“).
Regler und Zahlenfeld folgen einander, und die Reichweite aktualisiert sich schon
während des Verschiebens oder Eintippens. PV- und Schnellladeziel werden beim
Loslassen gespeichert, Ladeziele wie bisher mit „Speichern“. Ohne Sensor oder ohne
gelerntes Verhältnis zeigt der Regler nur den SoC. Regelung und Ladeplanung nutzen die
Reichweite nicht. Die Diagnose „Messquellen“ zeigt den Sensorwert.

Der dargestellte Hausverbrauch wird so berechnet:

```text
Haus ohne Auto und Wärmepumpe = Gesamtverbrauch − Wallbox-Leistung − Wärmepumpenleistung
```

Der Speicher-SoC wird über die Hardware-Zuordnung konfiguriert und erwartet
**Prozent von 0 bis 100**. Die technische Fahrzeugkapazität wird in **Wh**
eingetragen. **kW** bezeichnet Leistung, **kWh** eine Energiemenge.

### Hardware: Fronius-Speicher und NRGkick

Das direkte Fronius-Modbus-Plugin unterstützt bis zu acht Wechselrichter mit
eigenen IP-Adressen, Ports und Unit-IDs. An einem oder mehreren Geräten können
Batterien hängen; reine PV-Wechselrichter werden nur gelesen. PV und AC-Leistung
werden über alle Geräte summiert, der gemeinsame Netzanschlusszähler einmal
ausgelesen. Mehrere Batterien erscheinen als gemeinsamer Speicher mit
kapazitätsgewichtetem SoC und individuellen SoC-Grenzen bei der Steuerung.
Die Gesamtkapazität und konfigurierten Gesamtleistungsbudgets werden an die
vorhandene EOS-Speicherressource übergeben. Einrichtung und JSON-Beispiel stehen
unter [Mehrere Wechselrichter und Batteriespeicher](PLUGINS.md#mehrere-wechselrichter-und-batteriespeicher).

Für **NRGkick Gen2** steht das Plugin **NRGkick Gen2 local JSON API**
(`nrgkick_local`) zur Verfügung. Es liest und steuert den NRGkick direkt über
dessen lokale API. Zusätzliche HA-Wallbox-Sensoren oder Steuerentitäten sind dafür
nicht erforderlich. Die JSON-API in der NRGkick-App aktivieren und im Plugin die
lokale API-Adresse eintragen. Das bestehende HA-Plugin `nrgkick` bleibt verfügbar.
Einrichtung, optionale Anmeldung und Phasenumschaltung sind unter
[NRGkick lokal](PLUGINS.md#nrgkick-gen2-direkt-über-die-lokale-json-api) beschrieben.

Adapter-, Strom- und Phasengrenzen bestimmen die an EOS übermittelte maximale
Ladeleistung. Ist der NRGkick nicht erreichbar oder kein Fahrzeug angeschlossen,
wird das Auto ausgegraut und die Fahrzeugplanung deaktiviert. Speicher und andere
Fahrzeuge bleiben regelbar. Ein unbestätigter Ladestopp bleibt als Hinweis sichtbar;
beim Wiederverbinden werden Ladegrenzen und der gespeicherte Zeitplan übernommen.

Alternativ zur Fronius-Steuerung über zusätzliche HA-Entitäten steht das neue
Speicher-Plugin **Fronius GEN24 direct Modbus TCP** (`fronius_modbus`) zur Auswahl.
Es steuert direkt den GEN24 und liest SoC sowie Lade-/Entladeleistung ebenfalls
über Modbus. Zusätzliche Speichersensoren sind nicht erforderlich. Einrichtung,
DC-Leistungsdefinition und Rückgabe an die Automatik stehen in
[Hardware-Plugins](PLUGINS.md#fronius-gen24-direkt-über-modbus-tcp).

Auch die Netzanschlussleistung kann dieses Plugin über den am GEN24 angebundenen
Primärzähler liefern (Gateway-Unit-ID üblicherweise 200). Dafür den Netzsensor unter
**Konfigurieren → Quellsensoren** leeren. Allgemein gilt für Messwerte: Ein explizit
gewählter Sensor hat Vorrang; ohne Sensor kann ein Plugin mit entsprechender
Messfähigkeit einspringen. Fehlt beides, nennt das Panel die fehlende Konfiguration.
Ein vorübergehender Ausfall einer eingerichteten Quelle wird separat angezeigt.

Beim Plugin `fronius_modbus` können **PV-Leistung**, **Hausverbrauch** und
**Netzleistung** gemeinsam leer bleiben. PV kommt aus den PV-Kanälen; Hausverbrauch
wird aus der Summe der konfigurierten AC-Wechselrichterleistungen und dem
Netzanschlusszähler berechnet. Weitere Fronius-Wechselrichter unter
`additional_inverters` eintragen. Bei anderen, nicht erfassten Erzeugern einen
eigenen Hausverbrauchssensor verwenden. Gemeint sind aktuelle
Leistungen in W; ein kumulativer PV-Energiezähler in kWh ist hierfür nicht erforderlich.

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
| `max_phases` | `3` | 1 oder 3; Ladephasen des Fahrzeugs. `1` für ein Auto mit einphasigem Ladegerät, auch je Fahrzeug in der Fahrzeugliste. |
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
| Passwort-Umgebungsvariable / `influx_password_env` | Optional: Name einer Umgebungsvariable im **Home-Assistant-Core-Prozess**. Anstelle des Passworts wird nur dieser Name in der Integration gespeichert. |

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

Im Seitenleisten-Panel unter **Einstellungen** und teilweise als native Entitäten.
Die Einstellungsseite ist in die Bereiche **Speicher**, **E-Auto**, **Kalender**,
**Kosten** und **System** gegliedert; ohne Wallbox entfallen E-Auto und Kalender.
Selten benötigte Regelwerte stehen eingeklappt unter **Expertenwerte**. Sobald
ein Wert geändert wurde, erscheint unten eine Leiste mit der Zahl der Änderungen,
**Verwerfen** und **Speichern**; ein Klick speichert alle Bereiche gemeinsam. Lehnt
das Backend einen Wert ab, steht der Grund direkt am betroffenen Feld (zum Beispiel
an Mindest- und Maximal-SoC, wenn der Mindestwert nicht kleiner ist). Die
**Energiesteuerung** wird im Statusband oben auf jeder Seite geschaltet.

| Einstellung | Bedeutung |
|---|---|
| Energiesteuerung | Explizite Freigabe der Geräteansteuerung aller steuerbaren Bereiche; bleibt über Neustarts erhalten. Bei der ersten Einrichtung aus. Eingeschaltet, solange mindestens ein Bereich gesteuert wird. |
| Speichersteuerung | Freigabe nur für den Speicher. Nur vorhanden, wenn das Speicher-Plugin Lade- und Entladegrenzen setzen kann (z. B. nicht bei Victron ohne aktivierte ESS-Steuerung). |
| E-Auto-Ladesteuerung | Freigabe nur für die Wallbox(en). Nur vorhanden, wenn eine Wallbox konfiguriert ist. |
| Speicher Mindest-SoC | 0–99 %; kleiner als der Maximal-SoC. Startwert 20 %. Wird an EOS übergeben und lokal beachtet. |
| Speicher Maximal-SoC | 1–100 %; größer als der Mindest-SoC. Startwert 100 %. Wird an EOS übergeben und lokal beachtet. |
| Ziel-SoC | 1–100 %; Fahrzeug-Ziel für Terminplanung und Schnellladen. |
| PV-Ziel-SoC | 1–100 %; eigenständiges Ziel für PV-Überschussladen, auch ohne Termin. |
| PV-Überschussladen | Aktiviert die lokale PV-Regelung bis zum PV-Ziel. |
| Schnellladen | Lädt bis zum Ziel-SoC; wird nach Neustart nicht wieder eingeschaltet. |
| Einspeisereserve | 0–500 W; bei 0 W regelt die PV-Ladung möglichst nahe an Null-Netzleistung. |
| Regelintervall | 5–120 s; Mindestabstand zwischen Stromanpassungen, zusätzlich ist eine neue Netzmessung erforderlich. |
| Phasenautomatik | Automatischer Wechsel zwischen ein- und dreiphasigem Laden. Bei einem Fahrzeug mit `max_phases` = 1 bleibt die Wallbox einphasig. |
| Speicherunterstützung | Kann während tatsächlicher Auto-PV-Ladung die EOS-Entladesperre unter Beachtung der SoC-Grenzen aufheben. |
| Speichergestützter PV-Ladestart | Eigener Schalter, standardmäßig aus; ermöglicht den Start bei kleinem Überschuss unterhalb der Fahrzeug-Mindestleistung. Benötigt zusätzlich Speicherunterstützung und aktives PV-Laden. |
| Hausspeicher-Mindest-SoC für unterstützte PV-Ladestarts | Standard 50 %, einstellbar 0–98 %. Wirksam ist die höhere Grenze aus diesem Wert und dem allgemeinen Speicher-Mindest-SoC. Start ab zwei Prozentpunkten darüber, Ende der Unterstützung an der Grenze. |
| Überschusswartezeit | Standard 60 s, einstellbar 10–600 s. Unterbrechungen, fehlende Messwerte oder zu niedriger SoC starten die Wartezeit neu. |
| PV-Überschuss- und Defizitschwelle | Standard 150 W, einstellbar 1–5.000 W. Mindestens dieser Überschuss wird zum Start benötigt. Nach dem Start beendet ein durchgängiges PV-Defizit ab dieser Schwelle über 60 s die Unterstützung. |
| Einphasiges Fahrzeug | Unter **Konfigurieren → Grenzen** bzw. je Fahrzeug in der Fahrzeugliste **Ladephasen des Fahrzeugs** auf `1` setzen. Eine Wallbox mit Phasenumschaltung wird dann fest einphasig geregelt; bei einer Wallbox ohne Umschaltung rechnet die Energiezentrale Leistung und Strom für die eine genutzte Phase. Das Ladeprofil für EOS enthält nur einphasige Leistungen, sodass EOS mit der tatsächlich möglichen Ladeleistung plant. |
| Ladeziele unter Auto | Bis zu 32 aktivierbare Ziele mit eigenem SoC, einmaliger Abfahrt oder wiederkehrend mit Wochentagen und zusätzlichen Feiertagen. |

Beispiel: Bei 500 W PV-Überschuss und einphasiger Mindestladung von 1.380 W
kann der Speicher die fehlenden 880 W bereitstellen. Bei einer Untergrenze von
50 % beginnt die Wartezeit ab 52 % Speicher-SoC. Die Unterstützung endet bei
50 %; ein neuer Start benötigt wieder mindestens 52 %. Die allgemeine
Speicher-Untergrenze und die konfigurierte Entladeleistungsgrenze gelten weiterhin.

Vor der Ladefreigabe wird die Speicherladung gesperrt und Entladung zur
Eigenverbrauchsdeckung bestätigt. Es wird keine erzwungene Netzentladung
verwendet. Während dieser lokalen PV-Unterstützung hat die Deckung der
Fahrzeug-Mindestleistung Vorrang vor dem EOS-Speicherauftrag. Bei ausreichend
PV-Leistung geht die Regelung in normales PV-Laden über; ein späterer Rückgang
aktiviert die Unterstützung innerhalb derselben Ladung ohne erneute Startwartezeit.
Beim Ausschalten des
Features oder bei fehlenden Voraussetzungen endet die Unterstützung; reicht
der reine PV-Überschuss nicht, wird das Fahrzeug pausiert.

Zum Start muss der PV-Überschuss nach Abzug der Einspeisereserve mindestens die
Schwelle (Standard 150 W) während der gesamten Startwartezeit erreichen. Nach dem
Start ist fehlender Überschuss allein kein Stoppgrund: Erst wenn die PV-Leistung
für durchgehend 60 Sekunden um mindestens die Schwelle unter dem Bedarf aller
übrigen Verbraucher liegt, wird pausiert. Das gerade ladende Auto, Speicherladung,
Speicherentladung und die Einspeisereserve werden bei dieser Defizitprüfung
herausgerechnet. Eine Erholung über die Defizitschwelle setzt die Stoppwartezeit
zurück. Beispielsweise wird ein Defizit von 149 W bei der Standardschwelle
weiterhin überbrückt; bei 150 W Defizit startet der 60-Sekunden-Timer. Die
SoC-Untergrenze bleibt ein sofortiger Stoppgrund, soweit Speicherunterstützung
benötigt wird. Ein neuer Ladestart nach einem Stopp benötigt wieder die volle
Startwartezeit und den SoC-Puffer.

Ziel ist eine Netzleistung von 0 W. Mess- und Stellverzögerungen können kurzzeitig
Netzbezug verursachen. Mehr als 100 W Netzbezug über 10 Sekunden stoppt die
Unterstützung als Sicherheitsstopp. Fehlende Messwerte, nicht bestätigte
Gerätebefehle oder unzureichende Speicherleistung werden ebenfalls nicht durch
die PV-Defizitwartezeit überbrückt.
Ein Speicher ohne bestätigbare Lade- und Entladebegrenzung kann den unterstützten
Start nicht freigeben. Die Funktion arbeitet auch bei mehreren Fahrzeugen mit
gemeinsamen Speichergrenzen und konservativer Netzleistungsreservierung.

Das Panel übernimmt die vollständige Termin- und Wochentagsauswahl. Für eine
einmalige Planung muss vor der Wahl von `once` über native Entitäten ein gültiger
Abfahrtszeitpunkt gesetzt sein. Im Panel werden die Angaben gemeinsam gespeichert.

### Speichergrenzen an EOS übergeben

1. Im Panel **Einstellungen → Speicher** öffnen.
2. **Speicher Mindest-SoC** und **Speicher Maximal-SoC** setzen, zum Beispiel 30 % und 90 %.
3. In der Leiste unten **Speichern** drücken. Die Werte gelten auch für die lokale Speicherregelung.
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

### Messwerte an EOS übertragen

EOS liest den Start-Ladestand jedes Speichers und Fahrzeugs für die Optimierung
aus seinem Messwertspeicher (`<Ressource>-soc-factor`). Fehlt ein aktueller Wert,
rechnet EOS mit 0 % und plant zum Beispiel eine volle Ladung aus dem Netz.

Die Energiezentrale überträgt deshalb automatisch, was sie selbst geprüft gemessen hat:

| EOS-Messschlüssel | Quelle in der Energiezentrale |
|---|---|
| `<Speicherressource>-soc-factor` | Speicher-SoC (Faktor 0–1) |
| `<Speicherressource>-charge-power-w`, `-discharge-power-w` | Lade- und Entladeleistung des Speichers in W |
| `<Fahrzeugressource>-soc-factor` | Fahrzeug-SoC, wie ihn Panel und Regelung verwenden |
| `<Fahrzeugressource>-charge-power-w` | Ladeleistung der Wallbox in W |

Gesendet wird über `PUT /v1/measurement/value` mindestens einmal pro Minute,
eine SoC-Änderung ab einem Prozentpunkt sofort. Nur Schlüssel, die EOS unter
`GET /v1/measurement/keys` anbietet, werden geschrieben; die Liste wird alle
15 Minuten neu gelesen. Fehlt ein Messwert oder ist er ungültig, wird nichts
gesendet, nie eine Null. Bei mehreren Fahrzeugen sendet jedes Fahrzeug seine eigenen
Werte; der gemeinsame Speicher wird einmal gesendet. Ältere EOS-Versionen ohne
Mess-API bleiben unberührt (Hinweis im Log). Ein eigener EOS-Messeingang für
dieselben Schlüssel ist damit nicht mehr nötig; die Werte stimmen überein.

Zählerstände (`load_emr_keys`, `pv_production_emr_keys`, Netzbezug/-einspeisung)
werden nicht gesendet: EOS erwartet dort echte, fortlaufende Zählerstände in kWh,
die Energiezentrale misst aber Leistungen.

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

Ein vorhandener gültiger Fahrzeug-SoC darf unverändert bleiben, auch wenn der
Sensor längere Zeit keine Aktualisierung meldet. Ein Wert, dessen letzte Meldung
(`last_reported`, sonst `last_updated`) mehr als 36 Stunden zurückliegt, gilt
jedoch als veraltet und wird weder für Ladeentscheidungen noch als Startwert der
SoC-Schätzung verwendet. Eine SoC-Warnung erscheint erst,
wenn mehr als fünf Minuten durchgehend kein gültiger Wert vorhanden ist. Sobald
wieder ein gültiger Wert vorliegt, verschwindet die Warnung und eine spätere
Unterbrechung erhält erneut die volle Frist. Im Mehrfahrzeugbetrieb gilt dies
für jedes Fahrzeug separat. Die Altersprüfungen anderer Messquellen bleiben bestehen.

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

## Speicher und E-Auto getrennt steuern

Unter **Einstellungen → System → Gerätesteuerung** lassen sich Speicher und E-Auto-Laden
getrennt übernehmen und zurückgeben; beide Aktionen werden dort direkt bestätigt.
**Steuerung übernehmen** im Statusband übernimmt alle steuerbaren Bereiche, **Steuerung
zurückgeben** gibt alle gesteuerten Bereiche zurück. Wird nur ein Bereich gesteuert,
nennt das Statusband, welcher. Ein Bereich wird nur angeboten, wenn ein
passendes steuerbares Gerät konfiguriert ist:

- **Speicher:** Das Speicher-Plugin (bzw. alle Speicher einer Gruppe) muss Lade- und
  Entladegrenzen setzen können. Ein nur lesendes Plugin, z. B. Victron ohne aktivierte
  ESS-Steuerung, liefert weiter Messwerte, bietet aber keine Speichersteuerung an.
- **E-Auto-Laden:** Eine Wallbox muss konfiguriert sein; bei mehreren Fahrzeugen gilt
  die Freigabe für alle Wallboxen.

Ein nicht gesteuerter Bereich erhält keine Befehle der Energiezentrale, auch keine
Freigabe- oder Pausenbefehle; er bleibt in seinem eigenen Automatikbetrieb. Ohne
Speichersteuerung entfallen PV-Ladeunterstützung und der Start mit Speicherunterstützung,
die PV-Überschussladung nutzt dann nur den gemessenen Überschuss. Ohne E-Auto-Ladesteuerung
werden keine Fahrzeugziele an EOS übertragen. Beim Zurückgeben eines Bereichs wird nur
dieser freigegeben (Speicher in den Automatikbetrieb, Wallbox pausiert); der andere
Bereich wird weiter geregelt. Eine nicht bestätigte Freigabe bleibt sichtbar und wird
in jedem Zyklus wiederholt.

Der Schalter **Energiesteuerung** schaltet alle steuerbaren Bereiche gemeinsam; die
Schalter **Speichersteuerung** und **E-Auto-Ladesteuerung** schalten je einen Bereich
und werden nur bei passendem Gerät angelegt.

## Steuerfreigabe über Neustarts erhalten

Im Panel steht der Steuerzustand auf jeder Seite im Statusband oben, zusammen
mit Ursache, Folge und der passenden Aktion **Steuerung übernehmen** oder
**Steuerung zurückgeben**. Beide Aktionen werden direkt im Band bestätigt; die
Bestätigung nennt, was mit Speicher und Wallbox geschieht. Offene Hinweise stehen
als eigene Karten unter **Hinweise**, nach Schwere sortiert, mit derselben
Kennung wie im Integrationslog (zum Beispiel `system/eos` oder `vehicle/2/goal`)
und dem Zeitpunkt seit dem der Hinweis besteht. In den letzten 24 Stunden behobene
Hinweise bleiben dort kurz sichtbar. Fehler, die nur im Browser auftreten (etwa
eine unterbrochene Verbindung), werden als „nur in diesem Browser“ markiert und
nicht an das Backend gemeldet.

Die Steuerfreigabe wird beim bewussten Ein- und Ausschalten dauerhaft in
`.storage/eos_energiezentrale/<config-entry-id>/control_scope.json` (getrennt je
Bereich) gespeichert. Zusätzlich bleibt `control.json` im bisherigen Format erhalten:
Sie ist nur eingeschaltet, wenn alle steuerbaren Bereiche freigegeben sind. Eine ältere
Version übernimmt nach einem Downgrade daher nie mehr Geräte als hier freigegeben;
eine dort später geänderte Freigabe gilt nach dem nächsten Update für alle Bereiche.
Bestehende Installationen übernehmen die bisherige Freigabe für alle steuerbaren Bereiche.
Beim normalen Herunterfahren oder Neuladen werden die Geräte freigegeben, ohne
diese gespeicherte Einstellung auf aus zu setzen.

Nach einem Neustart bleibt ein zuvor aktivierter Schalter eingeschaltet. Die
Anzeige **Aktiv · warte auf Messwerte und Plan** bedeutet, dass die Freigabe
gespeichert ist, die Integration aber noch auf gültige Eingangsdaten und einen
aktuellen EOS-Speicherplan wartet. Anschließend setzt sie die Regelung selbstständig fort.
Den EOS-Speicherplan braucht nur die Speichersteuerung; die Wallbox wird nur geprüft,
wenn die E-Auto-Ladesteuerung freigegeben ist.
Nach einem unsauberen Ende können Geräte noch die letzten Vorgaben halten. Sind
Speicher und Wallbox bereits lesbar, fehlen aber EOS-Plan oder Messwerte, werden
sie während des Wartens freigegeben und die Wallbox pausiert. Ist nur der Speicher
lesbar, wird er allein freigegeben und die Wallbox folgt, sobald sie lesbar ist.
Bei mehreren Fahrzeugen gibt ein noch wartendes Fahrzeug nur seine eigene Wallbox
frei. Fehlgeschlagene Freigaben bleiben sichtbar und werden erneut versucht. Ein
Ausschalten vor dem Wiederanlauf versucht die Freigabe sofort und wiederholt sie
in jedem Zyklus, bis die Geräte sie bestätigen.

Ein bewusst ausgeschalteter Schalter bleibt aus. Ein Regelfehler deaktiviert die
Steuerung ebenfalls dauerhaft; zur Wiederaufnahme muss sie ausdrücklich aktiviert
werden. Ausgenommen ist ein bloßer Verbindungsausfall: Ist ein Gerät nicht
erreichbar (Zeitüberschreitung, abgewiesene oder abgebrochene Verbindung, oder ein
Modbus-Gateway wie der Victron GX meldet sein Zielgerät als nicht erreichbar), gibt die
Energiezentrale die Geräte so weit wie möglich frei und pausiert die Steuerung
(Hinweis `control_resume`). Jede Minute übernimmt sie die zuvor gesteuerten Bereiche
wieder, und wie nach einem manuellen Einschalten erst mit gültigen Messwerten und
EOS-Plan. Hält der Ausfall länger als 30 Minuten an, schaltet sie die Steuerung wie
bei jedem anderen Regelfehler dauerhaft aus. Antwortet ein Gerät dagegen mit einer
Ablehnung oder einer falschen Bestätigung, bleibt es beim sofortigen Ausschalten.
Ein manuelles Ein- oder Ausschalten beendet die automatische Wiederaufnahme.

Meldet der Speicher (etwa ein Victron GX) den Netzstatus selbst, pausiert ein einzelner
fehlgeschlagener Abruf die Steuerung nicht mehr sofort als möglichen Notstrom: Der
zuletzt bestätigte Netzbetrieb gilt bis zu 60 Sekunden weiter. Meldet das Gerät
Notstrom oder einen anderen ausdrücklichen Status, oder ist es länger nicht lesbar,
pausiert die Steuerung wie bisher. Eine bereits laufende Pause endet weiterhin nur
mit einer frischen Meldung des Netzbetriebs. Fehler beim Speichern werden angezeigt. Schnellladen bleibt nach einem
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
geprüft, der Fahrzeug-SoC mit 36 Stunden. Maßgeblich ist die letzte Meldung, auch wenn der Zahlenwert gleich bleibt.
Für PV-Leistung von **0 bis einschließlich 2 W** gilt eine Ausnahme von
**12 Stunden**, weil einige Sensoren nachts kleine Restwerte melden und keine
neuen Meldungen senden. Werte in kW werden vorher in Watt umgerechnet. Dies gilt ebenfalls für
PV-Werte aus generischen HA-Plugins. Fehlende Werte, falsche Einheiten und
zukünftige Zeitstempel werden weiterhin zurückgewiesen; PV-Leistung über 2 W
behält die kurze Frischegrenze.
Die PV-Quellenwarnung erscheint erst nach fünf Minuten ohne gültigen aktuellen
Wert. Nach einem gültigen Wert von 0–2 W wartet sie bis maximal 12 Stunden nach
diesem Messzeitpunkt. Dies deckt auch vorübergehende Modbus-N/A-Werte ab;
wiederholte Ausfälle verlängern die Frist nicht. Der letzte kleine Wert bleibt
mit Altersangabe sichtbar. Ein fehlender aktueller PV-Wert bleibt für Regelung
und Historie ungültig; der Anzeigepuffer ersetzt keine Messung. Falsche Einheiten,
zukünftige Zeitstempel und fehlende Konfiguration werden weiterhin unmittelbar
als Quellenproblem angezeigt. Geräte- und Verbindungsfehler bleiben diagnostizierbar.

Ein letzter gültiger Wärmepumpenwert kann in der Übersicht mit Altersangabe
weiter erscheinen. Der daraus berechnete Hausverbrauch trägt `≈` und den Hinweis
auf die ältere WP-Meldung. Diese Anzeige wird nicht als frische Messung an die
Regelung oder den lokalen Verlauf übergeben.

Zeitstrahl und Liste **Was als Nächstes passiert** zeigen die **Planung**. Im Lesemodus steuert die
Integration keine Geräte; der reale Speicherbetrieb kann daher davon abweichen.
Für den tatsächlichen Stromfluss zählen die konfigurierten Leistungssensoren.

### Diagnose der Messquellen

Unter **Einstellungen → Diagnose · Messquellen** zeigt das Panel alle
konfigurierten Quellen numerisch: Messgröße, Quelle (HA-Sensor mit Entitäts-ID
oder Plugin), aktueller Wert in W, %, oder ct/kWh, Alter der letzten Meldung und
Status. Ungültige oder veraltete Werte erscheinen ohne Zahlenwert mit Grund.
Fehlende Pflichtquellen bleiben sichtbar, nicht konfigurierte optionale Quellen
werden ausgelassen.

Darunter stehen die abgeleiteten Werte, gemessener und berechneter
Hausverbrauch sowie die gerade geschätzten Werte mit Grund (siehe
[Hausverbrauch aus der Energiebilanz](#hausverbrauch-aus-der-energiebilanz)).

### Hausverbrauch aus der Energiebilanz

Der Gesamtverbrauch folgt aus den Quellen: **PV + Netz (Bezug positiv,
Einspeisung negativ) + Speicherentladung − Speicherladung**. Damit geht die
Bilanz immer auf, auch wenn Sensoren zeitversetzt melden oder ein Zähler den
Verbrauch falsch erfasst. Der gemessene Hausverbrauch dient als Rückfall und als
Kontrolle: Weicht er länger als 15 Minuten um mehr als 10 % bzw. 300 W ab,
protokolliert das Backend einmalig `house_total_deviation` (Einstellungen → Geräte
& Dienste → EOS Energiezentrale → Protokolle). Dann fehlt meist eine Quelle,
z. B. eine nicht erfasste Balkon-PV, oder der Zähler misst falsch. Im
Notstrombetrieb gilt weiter die gemessene Wechselrichterleistung.

Fahrzeug und Wärmepumpe werden in diesen Gesamtverbrauch eingepasst. Melden sie
nach einem Schaltvorgang noch den alten Wert, schätzt das Backend für
höchstens 120 Sekunden:

- Hat diese Integration die Ladeleistung geändert, gilt die befohlene Leistung,
  auch beim Start, bevor die Wallbox den Anstieg meldet.
- Fällt die Leistung etwa um den letzten Wert der Wärmepumpe oder des Autos, gilt
  dieses Gerät als abgeschaltet. Der Hausverbrauch behält seinen letzten Wert.
- Sonst werden Fahrzeug und Wärmepumpe anteilig an die verfügbare Leistung angepasst.
- Fehlt ein Messwert kurz, wird der letzte Wert gehalten; fehlt er länger, bleibt
  sein Anteil im Hausverbrauch, damit der Gesamtverbrauch zugeordnet bleibt.
- Fehlt eine einzelne Quelle, folgt sie aus dem gemessenen Hausverbrauch und den
  übrigen Quellen.

Die Auswertung verbucht diese Werte als geschätzt (`≈`). Übersicht und lokaler
Verlauf zeigen nur Werte aus frischen Messungen; geschätzte Hausverbräuche
erscheinen dort nicht. „Unbekannt“ bleibt nur, wenn mehrere Quellen länger als
120 Sekunden fehlen und deshalb keine Bilanz möglich ist. Die Regelung verwendet
weiterhin nur gemessene Werte.

Für Gerätegruppen folgen die Einzelwerte jedes Geräts (z. B. PV, Netz,
Hausverbrauch, Speicher-SoC, Lade- und Entladeleistung), bei mehreren Fahrzeugen
Ladeleistung und SoC je Fahrzeug. Die Anzeige wird mit jedem Snapshot
aktualisiert und enthält keine Zugangsdaten.

**Messwerte kopieren** legt dieselben Werte als ausgerichteten Text in die
Zwischenablage, z. B. zum Einfügen in ein GitHub-Issue. **Messwerte exportieren**
speichert sie als Textdatei `eos-messwerte-<Zeitpunkt>.txt` für eine Analyse.
Ist die Zwischenablage im Browser gesperrt, meldet das Panel dies; der Export
funktioniert weiterhin. Der Text enthält Entitäts-IDs und Messwerte, aber keine
Zugangsdaten. Vor dem Teilen bitte prüfen, ob die Angaben veröffentlicht werden sollen.


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
- Native Schalter für Steuerfreigabe (gesamt sowie getrennt für Speicher und E-Auto), PV-Überschussladen, Schnellladen und Phasenautomatik.
- Ziel-SoC, PV-Ziel, Einspeisereserve und Regelintervall als `number`-Entitäten.
- Einmalige und wiederkehrende Abfahrtsplanung mit Wochentagsauswahl im Panel.
- Geschätzter Auto-SoC während der Ladung, falls das Fahrzeug keine neuen Werte meldet.

Die Entitäten werden über ihre eindeutige ID registriert. Die tatsächlich vergebenen
Entity-IDs findest du unter dem Gerät **EOS Energiezentrale**. Bereits bestehende
Helper werden nicht überschrieben. Einen bisherigen EOS-SoC-Eingang bei Bedarf
auf den neuen nativen Auto-SoC-Faktor umstellen.

Allgemeine Einstellungen für Kosten/Bilanzierung, Hausspeicher, PV-Ladestart und
Regelintervall stehen im Panel unter **Einstellungen**. Fahrzeugbezogene
Ladeoptionen und Ladeziele stehen in der Detailansicht **Auto**.
Native Entitäten ergänzen die Bedienung einzelner Parameter.
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

InfluxDB 1.x ist optional und wird lesend angesprochen. Home Assistant installiert
die Laufzeitabhängigkeit `holidays==0.108` für die lokale Feiertagsermittlung;
die Berechnung benötigt keinen externen Kalenderdienst.

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
cd frontend && npm ci && npm run typecheck && npm test && npm run build
```

Details zu Prüfungen, Releases und vorbereitetem Branchschutz: [CI.md](CI.md).

Versionen vergibt die CI automatisch. Nach den erfolgreichen Prüfungen wartet der
Push-/Merge-Lauf auf deine Antwort im automatisch angelegten GitHub-Issue; der Link
steht in der Zusammenfassung des Jobs **Decide whether to publish a release**.
`szech77` antwortet als eigenen Kommentar exakt **ja** zum Veröffentlichen oder
**nein** zum erfolgreichen Beenden ohne Release. Schließen oder 60 Minuten ohne
Antwort überspringen ebenfalls. Arbeitsbranches liefern nach Freigabe Betas,
`main` stabile Releases. Technische Fehler bleiben Fehler. Details: [CI.md](CI.md).
Für Betas in HACS
**Beta-Versionen anzeigen** aktivieren; der Release-Titel nennt den Branch.
Für Beiträge genügt der Abschnitt **New Version** im [Changelog](CHANGELOG.md).
Die vollständige nummerierte Historie steht im Changelog des jeweiligen Release-Tags.

## Lizenz

[Apache License 2.0](LICENSE). Private und kommerzielle Nutzung unter den
Lizenzbedingungen; Urheberhinweise siehe [NOTICE](NOTICE).

### Interaktive Energie-Diagramme

Ein Klick auf **Energie** in der Mitte des Stromflussbilds öffnet alle verfügbaren Energieflüsse. Speicher- und Fahrzeugdiagramme enthalten zusätzlich die PV-Messwerte und PV-Prognose. Mausbewegung oder Tippen zeigt Werte und Messzeitpunkte; per Tab und Pfeiltasten ist dieselbe Auswahl möglich. Historie ist durchgezogen, Prognose gestrichelt. Fehlende Daten bleiben Lücken. Die Hausgesamtprognose enthält Auto und Wärmepumpe und wird entsprechend beschriftet.

### Optionale Verbraucher

Neue Einrichtungen starten ohne E-Auto und Wärmepumpe. Unter den Integrationsoptionen aktiviert ein ausgewählter Wärmepumpensensor die Wärmepumpe; ein leeres Feld entfernt sie. Für das E-Auto unter Hardware den Wallbox-Typ `nrgkick` auswählen, zum Deaktivieren `none`. Ohne diese Verbraucher entfallen ihre Knoten, Leitungen und Detailnavigation im Stromfluss. Der Hausverbrauch berücksichtigt nur konfigurierte Verbraucher. Ein konfigurierter, aber ausgefallener Sensor bleibt hingegen ein fehlender Messwert. Bestehende Einrichtungen behalten ihre bisherigen Einstellungen.

Ohne E-Auto bzw. Wallbox (`none`) darf die **EOS-Fahrzeugressource** leer bleiben.
Es erfolgen dann keine Fahrzeugplanung, Fahrzeugabgleiche oder SoC-Veröffentlichungen;
PV, Hausverbrauch, Speicher und eine konfigurierte Wärmepumpe arbeiten unabhängig
weiter. Sobald ein Fahrzeug konfiguriert wird, benötigt es eine gültige, eigene
EOS-Ressource; Fahrzeug- und Speicherressource müssen unterschiedlich sein.

### Mehrere Fahrzeuge und Wallboxen

Unter **Integration → Konfigurieren → Fahrzeuge und Wallboxen** können Ladepunkte
über Formulare hinzugefügt, bearbeitet und entfernt werden. Die bisherige
Einzelkonfiguration wird beim ersten Hinzufügen übernommen. Alternativ steht unter
**Hardware → Mehrere Fahrzeuge / Wallboxen** die JSON-Liste zur Verfügung. Ein vollständiges Beispiel steht in
[examples/vehicles.json](examples/vehicles.json). `[]` verwendet weiterhin die
bisherige Einzelkonfiguration. Eine nicht leere Liste ersetzt die Einzelzuordnung.
Bis zu acht Fahrzeug-Wallbox-Paare sind möglich; für jedes Paar Name, stabile `id`,
eigene EOS-`resource` (z. B. `ev1`, `ev2`), SoC-Sensor, optional einen Reichweitensensor (`range_entity`), Kapazität und die fünf
Wallbox-Entitäten angeben. Die Fahrzeuge müssen auch in EOS angelegt sein.
Die Konfiguration erstellt oder überschreibt keine EOS-Gerätedefinitionen.

SoC- und Ladeleistungsprognosen werden im Backend anhand der `device_id` in den
EOS-Optimierungsparametern (`parameters.ev`) beziehungsweise im Ergebnis
(`ev_obj`) der passenden EOS-`resource` zugeordnet. Das gilt auch für eine Liste
mit nur einem Fahrzeug. Die GENETIC-Lösung liefert eine EV-Kurve pro Lauf;
sie erscheint nur bei ihrem Fahrzeug. Fehlende, widersprüchliche oder fremde
IDs werden nicht durch die Listenposition oder das erste Auto ersetzt. Für
andere Fahrzeuge bleiben fehlende Prognosen leer. Ungültige SoC-Werte bleiben
Lücken; die Ladeleistung benötigt zusätzlich gültige Kapazität und Ladeeffizienz.
Eine SoC-Prognose überschreibt keine aktuellen Fahrzeugmesswerte.

Unter **Inbetriebnahme → EOS-Verbindung** erscheint bei einer eingerichteten
Fahrzeugliste für jedes Auto ein eigenes Ressourcenfeld, beschriftet mit Name und
stabiler Fahrzeug-ID. Dort beispielsweise `ev1` dem ID.4 und `ev2` einem zweiten
Fahrzeug zuordnen. Die Ressourcen müssen bereits in EOS vorhanden und untereinander
sowie gegenüber der Speicherressource eindeutig sein. Änderungen werden in derselben
Geräteliste gespeichert, die auch unter **Geräte** bearbeitet wird. Alle Fahrzeuge
verwenden die gemeinsame EOS-API-Basisadresse; es sind keine zusätzlichen
EOS-Verbindungen nötig. Ohne Fahrzeugliste bleibt das Feld für die bisherige
Einzelkonfiguration sichtbar. Neue Fahrzeuge weiterhin unter **Geräte** hinzufügen.

In der Ansicht des Fahrzeugs (bzw. unter **Auto** mit Fahrzeugauswahl) wirken
PV-Überschussladen mit PV-Ziel-SoC, Schnellladen mit eigenem Ziel-SoC sowie die
automatische Phasenwahl sofort. Die Liste **Ladeziele** unterstützt bis zu 32 Einträge je Fahrzeug:
einmalige Abfahrt oder wiederkehrende Abfahrt mit Uhrzeit, Wochentagen und
zusätzlichen Feiertagen, jeweils mit Ziel-SoC und Aktivschalter. Einträge lassen
sich hinzufügen und nach einer Bestätigung entfernen; erst **Speichern** übernimmt
die Änderungen. Inaktive und abgelaufene einmalige Ziele bleiben bearbeitbar.
Das Backend übergibt das zeitlich nächste aktive Ziel an EOS. Bei identischem
Termin gilt der höhere Ziel-SoC. Nach Ablauf wird das nächste Ziel ausgewählt;
EOS muss nach einer Änderung zunächst einen neuen Plan erstellen. Alle Uhrzeiten
verwenden die konfigurierte Anlagenzeitzone. Wiederkehrende Termine in der
Zeitumstellungslücke werden auf die nächste existierende Uhrzeit verschoben;
nicht existierende einmalige Uhrzeiten werden zurückgewiesen.

Unter **Einstellungen → Kalender** Bundesland und gegebenenfalls
Augsburg als örtliche Sonderregelung auswählen. Für betroffene Gemeinden Bayerns,
Sachsens und Thüringens können örtliche katholische Feiertage aktiviert werden.
Diese Auswahl richtet sich nach dem Standort, nicht nach der persönlichen
Konfession. Ohne Bundesland gelten bundesweite gesetzliche Feiertage. Die Option
im Ladeziel ergänzt die Wochentage; sie schließt Feiertage an bereits ausgewählten
Wochentagen nicht aus. Auch reine Feiertagspläne sind möglich.

Bestehende Einzelpläne erscheinen unverändert als ein Ladeziel. Nach dem ersten
Speichern der neuen Liste ersetzt sie den alten Einzelplan. Die nativen Entitäten
für Zeitplan und Abfahrtsdatum/-zeit sind danach nicht verfügbar; die Liste wird
im Fahrzeugpanel bearbeitet. Der native Standard-Ziel-SoC steuert dann nur noch
die Schnellladung. Speichergrenzen, PV-Ladestartparameter, Einspeisereserve,
Regelintervall und Feiertagsregion bleiben für alle Fahrzeuge gemeinsam.
Der Stromfluss zeigt jedes konfigurierte Fahrzeug mit eigenem Namen, Ladeleistung,
fünf SoC-Balken und eigener Verbindung zur Energiezentrale. Dies gilt auch bei nur
einem Fahrzeug. Ein Klick auf das Fahrzeug öffnet dessen Messwerte, SoC und
EOS-Zeitplan. Bis zu acht Fahrzeuge stehen untereinander im Diagramm; dessen Höhe
passt sich der Anzahl sichtbarer Verbraucher an. Nicht angeschlossene oder nicht
erreichbare Fahrzeuge bleiben ausgegraut, ohne Hinweismeldung im Knoten; der
Zustand ist im Tooltip und für Screenreader verfügbar. Unbekannte Messwerte bleiben
unbekannt. Geplante Moduswechsel und das erwartete Erreichen des Ladeziels erscheinen je
Fahrzeug mit dessen Namen in der Liste **Was als Nächstes passiert**. Es entstehen eigene native Sensoren
für Leistung, SoC und Status jedes Fahrzeugs. Die Fahrzeug-ID bestimmt deren Identität.

Alle Regler verwenden denselben Netzanschluss. Nicht gemessene Leistungserhöhungen
werden bereits reserviert; Minderungen werden erst nach Messung frei. Bei knappem
Budget hat die Reihenfolge in der Liste Vorrang. Beim Abschalten werden alle Ladepunkte
pausiert und der Speicher freigegeben. Die Hausleistung zieht alle gemessenen
Fahrzeugleistungen genau einmal ab.

Die EOS-Lösungsantwort enthält eine EV-Prognose. Sie wird nur bei eindeutiger
Zuordnung der gespeicherten `device_id` zum entsprechenden Fahrzeug angezeigt.
Eine ausschließlich aus 0 % bestehende Zukunftskurve hat keinen Vorrang vor
einem bekannten positiven Fahrzeug-SoC. Ohne geplantes Fahrzeug stellt EOS
solche Nullkurven bereit; stattdessen wird der lokale Ersatzverlauf verwendet.
Fremde, fehlende oder widersprüchliche IDs übernehmen keine EOS-Kurve. Für diese
Fahrzeuge zeigt das Backend stattdessen eine ausdrücklich gekennzeichnete lokale
SoC-Schätzung, sofern ein gültiger aktueller SoC vorliegt. Ohne abschätzbare
PV-Ladung bleibt sie konstant. Eine PV-Schätzung benötigt ein angeschlossenes
Fahrzeug, aktiviertes PV-Laden, bekannte Mindest-/Maximalleistung, Kapazität,
Ladeeffizienz sowie Prognosen für PV und Hausverbrauch. Sie berücksichtigt
Einspeisereserve, prognostizierte Speicherladung und andere prognostizierte
Fahrzeuglasten. Bei mehreren PV-Fahrzeugen wird der verbleibende Überschuss
konservativ aufgeteilt. Fehlende Prognoseintervalle werden nicht durch aktuelle
PV-Leistung ersetzt. Die Schätzung ist keine Ladezusage und wird nicht zur
Steuerung oder als Messwert an EOS übergeben. PV-Prognose und ressourcenspezifische
EOS-Moduspläne bleiben verfügbar. Fahrzeughistorie wird lokal ab Einrichtung
geführt; ältere individuelle Influx-Verläufe werden hier noch nicht geladen.

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

Vor dem Planabruf wird `/v1/health` gelesen. Im Text des Statusbands und unter Einrichtung
erscheint **EOS berechnet** mit verstrichenen Sekunden, wenn EOS eine laufende
Phase meldet oder der Laufstart nach dem letzten Abschluss liegt. Ältere
EOS-Versionen liefern nur gerundete Start- und Abschlusszeitpunkte. Ist damit
kein Lauf eindeutig erkennbar, EOS aber erreichbar und ein neuer Plan noch nicht
abrufbar, zeigt das Panel **Warte auf aktuellen EOS-Plan**. Beide Zustände erhalten
ein begrenztes Fenster von fünf Minuten ohne temporäre Plan-/Prognosewarnungen
oder transportbedingte EOS-Synchronisationswarnungen. Wiederholte Statusabrufe
verlängern das Fenster nicht. Ein veralteter oder fehlgeschlagener Health-Abruf
kann Fehler nicht unterdrücken. Gerätestörungen und Konfigurationsfehler bleiben
sichtbar; die Gültigkeit vorhandener Steuerpläne wird nicht verlängert.
Zustandswechsel werden im Integrationslog auf INFO-Ebene protokolliert.
Nutzt die Regelung dabei den letzten gültigen Plan, bleibt das Statusband bei **Steuerung aktiv**; der Hinweis auf den Ersatzplan steht nur als Information im Text.
Solange EOS **berechnet** meldet, liest die Integration die EOS-Prognose nicht neu
ab; Diagramme und Plananzeigen behalten die zuletzt fertige Prognose. Nach dem Ende
der Berechnung wird die neue sofort abgerufen. Meldet EOS länger als 15 Minuten
eine laufende Berechnung, wird die Prognose wieder normal jede Minute abgerufen.

Die Panel-Warnung zur EOS-Prognose (Kennung `system/forecast`) erscheint erst,
wenn der EOS-Prognoseabruf fünf Minuten durchgehend fehlschlägt. Die Frist beginnt
beim ersten Fehlversuch und wird durch weitere Fehler nicht verlängert. Eine
erfolgreiche Prognoseantwort entfernt die Warnung sofort und setzt die Frist
zurück. Fehlerhafte Prognosedaten werden während dieser Wartezeit bereits aus
der Anzeige entfernt; die Live-Messwerte bleiben verfügbar.


## Verbrauch, Energiequellen und Kosten

Die Übersicht zeigt den bisher erfassten Tagesverbrauch und die variablen Energiekosten
für Haus, Wärmepumpe und E-Auto. Der Hausverbrauch enthält weder Wärmepumpe noch Fahrzeuge.
Optionale Verbraucher werden ausgeblendet. Bei mehreren Fahrzeugen enthält die Übersicht
deren Summe; die Einzelauswertungen sind über die jeweilige Fahrzeug-Detailseite erreichbar.

Bei den Kostensummen steht zusätzlich der berechnete Durchschnittspreis in ct/kWh,
beispielsweise **1,00 € · Ø 25 ct/kWh** bei 4 kWh Verbrauch. Dieser Preis wird aus
der gesamten Kostensumme und der zugehörigen Energiemenge berechnet, auch über
mehrere Energiequellen oder zusammengeführte Live- und historische Daten hinweg.
Er steht in den Tageskarten und der Gesamtsumme, unter der Kosten-Kennzahl der
Verbraucher-Detailseiten sowie in den Diagramm-Hinweisen für jeden Zeitraum und
jede Quelle. Die Quellentabelle zeigt ihn in der eigenen Spalte **ct/kWh**.
Bei teilweise unbekannten Kosten wird ein geschätzter Durchschnittspreis mit
**≈** angezeigt. Grundlage sind die bekannten Teilkosten geteilt durch die
zugehörige bewertete Energiemenge. Beispiel: Von 4 kWh sind 2 kWh mit 0,60 €
bewertet; daraus ergibt sich **Ø ≈ 30 ct/kWh**. Die unbekannten 2 kWh werden nicht
als kostenlos in den Nenner eingerechnet. Die Annahme ist, dass der bewertete
Anteil als Schätzgrundlage für den Durchschnitt dienen kann; die UI kennzeichnet
diesen Preis ausdrücklich als Schätzung. Kostensummen bleiben weiterhin bekannte
Teilsummen und werden nicht auf die gesamte Energiemenge hochgerechnet.
Ohne ausreichende bewertete Energiemenge oder ohne Verbrauch bleibt der Preis
**— ct/kWh**. Ein tatsächlich kostenloser bewerteter Verbrauch zeigt **0 ct/kWh**.

Die Kacheln **Heute** in der Übersicht zeigen je Verbraucher Energie, Eigenanteil und
Kosten, dazu **Einspeisung** (Vergütung und Netzbezug) und **Gesamtverbrauch**
(Kosten und Netto). Jede Kachel öffnet ihre Auswertung; der Netz-Knoten im
Energiefluss öffnet **Netz & Einspeisung**, der PV-Knoten **PV-Erzeugung**, Haus und Wärmepumpe ihre Verbrauchsauswertung.

**PV-Erzeugung** macht den Energiefluss je Stunde, Tag oder Monat sichtbar. Oberhalb der
Nulllinie steht der PV-Strom nach Ziel: Haus, E-Auto, Wärmepumpe, Akku laden und
Netzeinspeisung; die Höhe ist die Erzeugung. Unterhalb steht der Verbrauch dieser
Verbraucher, den PV nicht gedeckt hat, nach Herkunft: Akku (PV-geladen, netzgeladen oder
Herkunft unbekannt), Netz oder unbekannte Quelle. So ist erkennbar, ob PV reicht, wie groß
die Unterdeckung ist und wohin der PV-Strom fließt. Akkuladung aus dem Netz zählt weder
als PV-Ziel noch als Unterdeckung. Für den Rest des Zeitraums steht die EOS-Prognose als
umrandeter Balken darüber; sie reicht etwa zwei Tage voraus. In der Tagesansicht zeigt
**kW** dieselbe Aufteilung als Flächen über die Uhrzeit und die Prognose als gestrichelte
Linie; die Anzeige am Mauszeiger nennt alle Werte. Die Aufteilung folgt der Abrechnung
(anteilig nach PV, Netzbezug und Akkuentladung); die Herkunft des Akkustroms stammt in
kWh aus dem Akkubestand, in kW aus dem Anteil der jeweiligen Stunde. Alle Werte berechnet
das Backend.

Alle Auswertungen sind gleich aufgebaut. Oben wechseln Chips zwischen PV-Erzeugung, Haus, Auto
(bei mehreren Fahrzeugen auch je Fahrzeug), Wärmepumpe, Netz & Einspeisung und Gesamt:

- **Tag / Monat / Jahr:** stündliche Werte, Tageswerte oder Monatswerte. Der zuletzt gewählte Zeitraum bleibt lokal im Browser gespeichert; ohne Browserspeicher gilt die Auswahl für die laufende Sitzung.
- **‹ ›** blättern; **Aktuell** springt zurück in den laufenden Zeitraum. Ein Tages- oder Monatsbalken öffnet die nächstfeinere Ansicht, ein Stundenbalken zeigt seine Werte.
- **Kernaussage und vier Kennzahlen:** bei Verbrauchern Verbrauch, Eigenversorgung, Kosten und Ersparnis gegenüber reinem Netzbezug (Eigenstrommenge × Ø-Netzstrompreis des Zeitraums − Eigenstromkosten); in der Gesamtbilanz Verbrauch, Autarkie, Kosten inklusive Grundpreis und Netto; bei Netz & Einspeisung Einspeisung, Bezug, Eigenverbrauchsquote und Autarkie.
- **Verlauf:** gestapelt nach PV, Akku, Netz und unbekannter Quelle; bei Netz & Einspeisung der Bezug nach oben und die Einspeisung nach unten. Die Tagesansicht bietet drei Darstellungen: **kW** zeigt die Leistung über die Uhrzeit als farbig gefüllte, übereinanderliegende Flächen; beim Überfahren mit der Maus (oder Antippen) erscheinen Uhrzeit, Gesamtleistung und die Anteile am Zeiger. Grundlage sind die minütlichen Messwerte des lokalen Verlaufs: Das Backend teilt jeden Messpunkt wie die Abrechnung anteilig auf PV, Akku und Netz auf (bei nicht aufgehender Bilanz auf Unbekannt) und fasst je 2 Minuten zusammen; Lücken über 10 Minuten bleiben Lücken. Der lokale Verlauf reicht etwa zwei Tage zurück; für ältere Tage zeigt kW die Stundenbalken. **kWh** und **€** zeigen Balken je Stunde, ein angeklickter Balken zeigt seine Details. Monat und Jahr bieten kWh und € als Balken je Tag bzw. Monat. Der Umschalter **kWh / €** zeigt statt der Energie die Kosten je Quelle (PV zum PV-Kostenansatz, Akku zum Speicherpreis, Netz zum Bezugspreis) bzw. bei Netz & Einspeisung die Bezugskosten nach oben und die Einspeisevergütung nach unten. Die Beträge je Zeitabschnitt berechnet das Backend; Kosten unbekannter Herkunft fehlen im Balken und sind im Tooltip als bekannter Anteil gekennzeichnet. Die Auswahl merkt sich der Browser.
- **Preise & Kosten:** Bei Verbrauchern und der Gesamtbilanz zeigen das Preisfeld im Kopf und die Überschrift über der Aufschlüsselung den energiegewichteten Durchschnittspreis aus allen Quellen (PV, Speicher und Netz) für den gewählten Zeitraum. Grundlage sind die bekannten Energiekosten geteilt durch die zugehörige bewertete Energiemenge; Schätzungen tragen `≈`, ohne Preisgrundlage steht `—`. Grundpreis und Einspeisevergütung gehören nicht zu diesem Energiepreis. Die Zeilen zeigen Netzbezug, PV direkt (zum PV-Kostenansatz) sowie den Speicherstrom getrennt nach Herkunft seiner Ladung: PV-geladen (PV-Kostenansatz) und netzgeladen (Netzpreis beim Laden), jeweils einschließlich der Speicherverluste, und Summe. Der Speicher führt dafür mit, wie viel seines Inhalts aus PV bzw. dem Netz stammt, und gibt diese Anteile beim Entladen anteilig weiter. Speicherstrom ohne erfasste Herkunft, etwa aus der Zeit vor dieser Aufschlüsselung, steht als „Herkunft unbekannt“ mit dem Speicherpreis. Gesamtbilanz und Netz & Einspeisung enthalten zusätzlich den anteiligen Grundpreis und die Einspeisevergütung; Netz & Einspeisung zeigt den Saldo gegenüber dem Netz einschließlich Speicherladung aus dem Netz.
- **Woher kam der Strom?** bzw. bei Netz & Einspeisung **Wohin ging der PV-Strom?** (direkt verbraucht, in den Speicher, eingespeist).
- **Was auffällt:** Das Backend wählt beste und schwächste Zeitabschnitte, höchste Einspeisung und höchsten Bezug, Tagesdurchschnitte, Ladetage und die Ersparnis aus; die Gesamtbilanz verlinkt hier die einzelnen Verbraucher.
- Auf schmalen Bildschirmen sind Preise, Herkunft und „Was auffällt“ zunächst eingeklappt.

Die neue lokale Bilanz speichert Stundenaggregate dauerhaft in
`.storage/eos_energiezentrale/<entry_id>/accounting.sqlite3` und ist unabhängig vom
kurzen Diagrammcache. Datenbank und Kostenbestand gehören in die HA-Sicherung.
Der letzte Messpunkt wird zusammen mit dem Kostenbestand gespeichert. Nach einem
Neustart oder bei Messlücken bis **sechs Stunden** werden die Werte zwischen dem
letzten und dem nächsten Messpunkt linear angenähert und in höchstens fünf Minuten
langen Abschnitten ausgewertet. Stunden-, Tages- und Zeitumstellungsgrenzen bleiben
erhalten. Solche Verbräuche und ihre Kosten sind mit **≈** gekennzeichnet. Bei einem
einseitig fehlenden Wert dient der verfügbare Nachbarwert als Näherung; fehlen beide,
wird kein beliebiger Nullwert erfunden. Bei längeren Ausfällen bleibt die
Verbrauchslücke offen, während der bekannte Akkupreis erhalten bleibt.

Für Zeiträume vor Beginn der lokalen Bilanz liest die Auswertung vorhandene Messwerte
aus der konfigurierten InfluxDB 1.x. Diese Rekonstruktion verwendet Fünf-Minuten-Mittelwerte,
interpoliert Lücken zwischen Messpunkten bis sechs Stunden und überlappt die neue
Bilanz nicht. Sie ist ausdrücklich eine Schätzung. Für den anfänglichen Akkuinhalt
gelten dieselben Preisannahmen wie für den Live-Bestand; fehlt jede Preisgrundlage,
bleibt der Kostenanteil unbekannt.
Historische Auswertungen verwenden für die Rekonstruktion die aktuell eingestellten
PV-Kosten und Speicherparameter. Bereits dauerhaft bewertete Kosten werden nicht
neu bewertet. Noch unbewertete Akkuanteile erhalten in der Berichtskopie eine
gekennzeichnete Näherung zum verfügbaren Akkupreis, ohne die ursprünglichen
Datenbankeinträge zu überschreiben.
Die Datenbankabfragen laufen außerhalb der Gerätesteuerung und sind zeitlich begrenzt.

### Einstellungen zur Bilanzierung

Unter **Einstellungen → Kosten** stehen zur Verfügung (Wirkungsgrade und
Anfangspreis eingeklappt unter **Wirkungsgrade und Anfangspreis**):

| Einstellung | Bedeutung |
| --- | --- |
| Quelle für PV-Kostenansatz | Standard EOS-Einspeisevergütung, zur Laufzeit per REST gelesen; alternativ manuell. |
| PV-Kostenansatz | ct/kWh; im EOS-Modus wird der verwendete Wert angezeigt. Manuelle Vorgabe nur im manuellen Modus. |
| Quelle für Speicherwirkungsgrad | Standard EOS; alternativ manuelle Parameter. |
| Lade-/Entladewirkungsgrad | Jeweils Faktor 0,1 bis 1; nur im manuellen Modus. |
| Speicherkapazität | Wh; im manuellen Modus die eigene nutzbare Kapazität eintragen. |
| Grundgebühr Netzbezug | Liste mit „Grundgebühr ab“, Betrag in € brutto und Abrechnung pro Monat oder Tag. Tarifwechsel sind rückwirkend und für die Zukunft möglich; je Kalendertag gilt der letzte Eintrag ab seinem Datum. Ein leerer Beginn übernimmt bestehende Monatswerte ab Aufzeichnungsbeginn. Vor dem ersten datierten Eintrag bzw. bei leerer Liste fällt keine Grundgebühr an. Monatsbetrag × 12 / 365 bzw. Tagesbetrag, ohne Zwischenrundung, ab Aufzeichnungsbeginn bis heute; nur Gesamtbilanz und Netz & Einspeisung. Tarifabschnitte werden getrennt ausgewiesen. Standard 0. |
| Stromtarif / Arbeitspreis | Je Eintrag wahlweise dynamischer Preissensor (Standard) oder fester Brutto-Arbeitspreis in ct/kWh, mit demselben Gültigkeitsbeginn wie die Grundgebühr. Direkter Netzbezug und Netzladung des Speichers verwenden den Festpreis; für diesen Zeitraum ist zur Kostenbewertung kein Preissensor erforderlich. Rückwirkende Änderungen bewerten sowohl den aktuellen netzgeladenen Akkuinhalt als auch bereits entladene Netzanteile in vergangenen Auswertungen nach dem jeweiligen Ladetag und einschließlich der Speicherverluste neu. PV-Anteile und Energiemengen bleiben erhalten. Neue Buchungen speichern die Ladetage mit; bei älteren Stundenbuchungen sind Reihenfolge innerhalb der Stunde und damalige Wirkungsgrade nicht vollständig rekonstruierbar, daher ist deren Neubewertung eine gekennzeichnete Schätzung. Ohne rekonstruierbaren Ladetag wird kein später beginnender Tarif unterstellt; ein Eintrag ohne Beginn deckt auch diese Anteile ab. Die Messhistorie wird nicht überschrieben. Die EOS-Planung hat ihre eigene Tarifkonfiguration in EOS. |
| Anfangsbestand: Preis | Optionaler Preis je gespeicherter kWh bei der ersten Initialisierung. Leer: Schätzung als PV-Ladung zum aktuellen PV-Kostenansatz einschließlich Ladeverlusten. |

Bei der Grundgebühr werden auch mehr als fünf Nachkommastellen akzeptiert. Die Tarifanzeige
rundet auf höchstens sechs Nachkommastellen; gespeichert und berechnet wird ohne diese Anzeigerundung.

Aus EOS werden `devices.batteries.<battery_resource>.capacity_wh`, `charging_efficiency`
und `discharging_efficiency` gelesen. Dies verändert keine EOS-Konfiguration. Fehlen diese
Werte, bleibt die Bewertung von Akkuenergie unbekannt, bis EOS bereit ist oder manuelle
Parameter eingestellt sind. Der letzte gültige Parametersatz wird auch über
Neustarts erhalten und bei vorübergehend fehlender EOS-Verbindung als gekennzeichnete
Näherung für diese Auswertung weitergenutzt. Die aktuell verwendeten Parameter
werden im Einstellungsbereich angezeigt.

PV, Netz und Akku werden anteilig auf die gleichzeitig gemessenen Verbraucher,
Speicherladung und Einspeisung verteilt. Eine eindeutige physische Quellenzuordnung
pro Verbraucher ist mit den vorhandenen Zählern nicht möglich. Größere Widersprüche
in der Leistungsbilanz erscheinen als unbekannte Quelle. Die Berechnung setzt die
Leistungen als Werte auf derselben AC-Bilanzgrenze voraus; abweichende DC-Speichermessungen
führen zu zusätzlichen Modellabweichungen.

Unbekannte Herkunft ergänzt die Auswertung nachträglich aus den bekannten
Quellenanteilen davor und danach: Die Anteile von PV, Akku und Netz werden nach
Zeitabstand linear interpoliert und auf den unveränderten unbekannten Verbrauch
verteilt. Die beiden Stützpunkte dürfen höchstens sechs Stunden auseinanderliegen;
ohne beidseitige Grundlage bleibt die Herkunft unbekannt. Bereits bekannte Anteile
werden erhalten. Im kW-Diagramm erfolgt dies vor der Zwei-Minuten-Zusammenfassung
an den vorhandenen Messpunkten; fehlende Messpunkte und Lücken werden nicht ergänzt.
Geschätzte Quellenleistungen tragen im Tooltip **≈**. Die Stützpunkte dürfen auch
vom angrenzenden Tag stammen, soweit der lokale Verlauf sie noch enthält.

Die dauerhafte lokale Bilanz hat nur Stundenaggregate: Dort werden unbekannte
Verbraucheranteile aus den bekannten Anteilen benachbarter Stunden desselben
Verbrauchers geschätzt, bevor die Tages-, Monats- und Jahressummen entstehen.
Auch teilweise bekannte Stunden können mit ihrem bekannten Anteil als Stützpunkt
dienen. Liegt eine Störung innerhalb nur einer Stunde, ist die Ergänzung deshalb
gröber als im Leistungsdiagramm; fehlen Nachbarstunden, bleibt sie offen.
Kosten und Herkunft der Akkuenergie werden anteilig aus diesen Stützpunkten
angenähert; dort fehlende Preise bleiben unbewertet. Die ergänzte Energie und ihre
Kosten sind mit **≈** gekennzeichnet. Dies gilt auch für schon aufgezeichnete lokale
Bilanzdaten. Die gespeicherten Rohaggregate und der laufende Akku-Kostenbestand
werden dabei nicht verändert. Speicherladung und Einspeisung werden nicht auf
diese Weise umverteilt; die Influx-Rekonstruktion bleibt beim oben beschriebenen
Verfahren. Keine dieser Schätzungen fließt in die Gerätesteuerung ein.

Einspeisung und Speicherladung werden je Stunde mitgeschrieben. Die Einspeisung wird
mit dem PV-Kostenansatz (standardmäßig der EOS-Einspeisevergütung) des jeweiligen
Zeitpunkts bewertet; ist er unbekannt, bleibt die Vergütung als unbekannt markiert.
Die Speicherladung wird nach PV und Netz aufgeteilt. Daraus berechnet das Backend
je Zeitraum Autarkie, Eigenverbrauchsquote des PV-Stroms, physischen Netzbezug,
Ø-Netzstrompreis, Ersparnis gegenüber reinem Netzbezug und Netto (Kosten der
Verbraucher + Grundpreis − Einspeisevergütung). Netzgeladene Speicherenergie zählt
dabei nur einmal, nämlich über den Akku-Kostenbestand bei der Entnahme. Autarkie und
Eigenversorgung zählen nur PV-Direktstrom und Speicherstrom, der nicht aus dem Netz
geladen wurde; netzgeladener Speicherstrom ist zeitversetzter Netzstrom. Speicherstrom
ohne erfasste Herkunft (aus der Zeit vor der Herkunftserfassung) zählt weiterhin als
eigene Versorgung. Die Ersparnis bewertet dagegen allen PV- und Speicherstrom, weil
auch günstig geladener Netzstrom gegenüber dem Netzpreis spart. Einspeisung
wird erst ab diesem Update erfasst; ältere Zeiträume zeigen sie nur, soweit sie aus
InfluxDB rekonstruiert werden.

Netzladung erhöht den Akku-Kostenbestand zum jeweiligen Strompreis, PV-Ladung zum
PV-Kostenansatz. Ladeverluste reduzieren die eingelagerte Energie; bei Entladung wird
die für die gelieferte Energie nötige gespeicherte Energie einschließlich Entladeverlusten
ausgebucht. Energie und Kosten werden mit gewichtetem Durchschnitt entnommen.
Der Kostenbestand bleibt über Neustarts erhalten. Ein Messausfall löscht weder
bekannte Kosten noch den zuletzt bewerteten Preis. Der nach einer Lücke gemeldete
SoC begrenzt den Bestand: Minderungen buchen Energie und Kosten proportional aus;
zusätzliche, nicht beobachtete Energie wird zum verfügbaren gewichteten Akkupreis
angenähert. Ist noch kein Akkupreis bekannt, wird der manuelle Anfangspreis oder
der PV-Kostenansatz einschließlich Ladeverlusten verwendet. Auch eine rechnerische
Bestandsunterschreitung bei gemessener Entladung wird mit diesem Preis geschätzt,
statt Strom kostenlos zu behandeln. Es werden keine Grundgebühren
oder Einspeiseerlöse des übrigen Hauses verrechnet. Negative Arbeitspreise sind zulässig.

Ohne ausdrücklich angegebenen Anfangspreis wird der anfängliche Akkuinhalt als
PV-Ladung geschätzt: gespeicherte kWh geteilt durch den Ladewirkungsgrad, bewertet
zum aktuellen PV-Kostenansatz (standardmäßig EOS-Einspeisevergütung). Bei der
Entladung kommen die Entladeverluste hinzu. Auch der noch unbekannte Rest eines
bisherigen Kostenbestands wird einmalig so bewertet; bekannte Kosten bleiben erhalten.
Fehlt jede Preisgrundlage, wartet diese Schätzung auf einen gültigen Wert. Spätere
Datenlücken verwenden den vorhandenen gewichteten Preis als Näherung. Fehlende
Akku-Leistungswerte können für die Auswertung aus PV-Leistung, Netzleistung und
Gesamtverbrauch abgeleitet werden. Die tatsächliche Gerätesteuerung verwendet
weiterhin ausschließlich ihre eigenen gültigen Messwerte.

Bei nur teilweise bekannten Kosten zeigt die UI die bekannte Teilsumme mit `≈` an;
bei vollständig unbekannten Kosten steht `—`. Unbekannte Energie wird nicht als kostenlos bewertet.
Auch vollständig bewertete, aber interpolierte oder geschätzte Werte tragen `≈`.
Das gilt ebenfalls für den berechneten Preis je kWh. Ein echter Null- oder
Negativtarif bleibt ein gültiger Preis; fehlende Preise werden nicht als 0 angesetzt.
Die Auswertung dient der Orientierung und Prognose und ersetzt keine Stromrechnung.


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


## Dynamische Hardware-Plugins

**go-e Charger – lokale HTTP-API v2** bindet neuere go-e Charger direkt über ihre
lokale API an. Ladeleistung, Freigabe, Stromgrenzen und optional die Phasenumschaltung
benötigen keine zusätzliche HA-Wallboxintegration. Die API-Version steht im
Plugin-Namen. [Einrichtung und Voraussetzungen](PLUGINS.md#go-e-charger-direkt-über-die-lokale-http-api-v2).

Für den **Deye SUN-12K-SG04LP3-EU** ist eine lokale Anbindung über ein
Modbus-TCP↔RTU-Gateway verfügbar. Messwerte benötigen keine zusätzliche
HA-Sensorintegration; kompatible Firmware kann optional über den Remote-Modus
mit Watchdog gesteuert werden. Der Monitoring-Anschluss muss zur Hardwareversion
passen. [Anschluss, Einrichtung und Grenzen](PLUGINS.md#deye-sun-12k-sg04lp3-eu-direkt-über-modbus).
Für ein Gateway auf Basis von ESPHome gibt es eine
[Anleitung mit Beispielkonfiguration](docs/deye-esphome-gateway.md).

Speicher-/Wechselrichter und Wallboxen werden über versionierte Interfaces und lokale,
dynamisch erkannte Plugins angebunden. Fronius und NRGkick sind eigene Plugins;
zusätzlich gibt es für beide Gerätearten **Generic Home Assistant**. Plugin-Name,
Fähigkeiten (z. B. Phasenumschaltung) und Konfigurationsfelder kommen vom Plugin.

Unter **Konfigurieren → Geräte → Gerät hinzufügen** zuerst die Geräteart,
dann das Plugin dieses Geräts auswählen und dessen Parameter konfigurieren.
Jeder Speicher, PV-Wechselrichter und jede Wallbox kann ein anderes Plugin nutzen.
Vorhandene Geräte erscheinen dort direkt als Liste mit ihrem Namen. Einen Eintrag
zum Bearbeiten auswählen; „Dieses Gerät entfernen“ in dessen Dialog löscht es nach
Bestätigung. Neue Installationen beginnen mit leerer Liste. Wallboxen werden zusammen
mit ihrem Fahrzeug eingerichtet. Bestehende Fronius-Untergeräte werden beim ersten
Speichern in die allgemeine Geräteliste übernommen. Bis zu acht Speicher/PV-Geräte
sind möglich. Die gemeinsame EOS-Planung mehrerer Batterien bleibt eine Näherung,
die in der Verbindungsansicht gekennzeichnet ist.
Die typisierten Felder erscheinen als native HA-Auswahlfelder; JSON für die gesamte
Hardwarekonfiguration ist im normalen Ablauf nicht mehr erforderlich.

Alle Plugin-Messwerte und Schreibvorgaben durchlaufen eine zentrale Prüfung.
Fehlende Messwerte bleiben fehlend; NaN, falsche Einheiten/Skalen und unmögliche
Werte werden nicht als gültige Regelgrößen übernommen. Ohne deklarierte
Phasenumschaltfähigkeit bleibt die Regelung bei der vorhandenen Phasenanzahl.

Die vollständige Schnittstelle, Plugin-Erweiterung und Beispiele sind in
[PLUGINS.md](PLUGINS.md) beschrieben. Helfer für die generische Anbindung stehen in
[generic_hardware_helpers.yaml](examples/generic_hardware_helpers.yaml).


## Leistungsringe im Stromfluss

Die Außenringe für PV, Akku und E-Auto zeigen die momentane Leistung als linearen
Anteil der Bezugsleistung: Beginn oben bei 12 Uhr, Füllung im Uhrzeigersinn, 25 %
entsprechen einem Viertelkreis. Der übrige Ring ist dunkel. Batterie- und Auto-SoC
bleiben separat innerhalb der Symbole sichtbar.

Das Auto wird in Seitenansicht dargestellt. Wie beim Speicher zeigt der SoC fünf
vertikale Balken in 20-%-Stufen; der Prozentwert bleibt zusätzlich ablesbar. Bei
0 % sind alle fünf Balken leer, bei unbekanntem SoC werden sie ausgeblendet.
In den Fahrzeugkarten gilt dieselbe Darstellung für jedes Auto einzeln.

- **PV:** Bezugsleistung unter **Konfigurieren → Grenzen → PV-Bezugsleistung für den Ring (W)**
  einstellen (`pv_peak_w`, Standard 10000 W). Dies verändert keine Regelgrenze.
- **Akku:** Bezug auf die maximale Lade- bzw. Entladeleistung der Integration, je nach
  aktueller Flussrichtung. Der Ring stellt Leistung und nicht den Ladezustand dar.
- **E-Auto:** maximal mögliche Ladeleistung aus dem eingestellten Maximalstrom,
  höchstens 11 kW. Bei fester Phasenanzahl wird diese berücksichtigt, bei einem
  einphasigen Fahrzeug (`max_phases` = 1) eine Phase; bei mehreren Fahrzeugen werden
  deren Bezugsleistungen addiert.
- **Wärmepumpe:** optional unter **Konfigurieren → Sensoren** eine Entität für die
  Leistungsauslastung (`heat_load_entity`) und die Skalierung (`heat_load_scale`:
  `percent` für 0–100, `factor` für 0–1) auswählen. Ohne Entität bleibt der bisherige
  Ring unverändert. Ungültige Werte werden nicht als 0 interpretiert; bei fehlenden
  Daten bleibt der Leistungsring dunkel. Für diese reine Anzeige gilt der vorhandene
  längere Anzeigepuffer, nicht die kürzere Regelungsfrist.


### Fehler beim Öffnen der Oberfläche

Die UI-Dateien werden pro installiertem Stand gemeinsam versioniert geladen.
Nach einem Update die **vollständige** Integration übertragen und Home Assistant neu
starten, damit die neue Panel-Version registriert wird. Der Button **Erneut versuchen**
lädt die Oberfläche mit einer frischen Cache-Kennung; die Gerätesteuerung wird dadurch
nicht ein-/ausgeschaltet.

Die Meldung nennt den betroffenen Bereich: Sprachpaket, HA-Verbindung, fehlende Datei
oder Darstellung. Bei gemischten Dateiversionen die komplette Integration aktualisieren;
bei einem fehlenden Sprachpaket insbesondere `energy/i18n` mit übertragen. Bei
fehlender Adminberechtigung mit einem Administrator anmelden. Technische Details nennen
Fehlerart und gegebenenfalls die betroffene UI-Datei. Unerwartete Backendfehler stehen
zusätzlich im HA-Protokoll und werden nicht mehr als ungültige Einstellungen gemeldet.
Die frühere pauschale Anzeige `EOS Energiezentrale · /api/language` wurde entfernt.


### Wetter im Energieflussdiagramm

Unter **Einstellungen → Geräte & Dienste → EOS Energiezentrale → Konfigurieren →
Quellsensoren** kann eine optionale `weather.*`-Entität ausgewählt werden. Das
Diagramm zeigt deren aktuelle Wetterlage und Temperatur (°C, °F oder K).
Ohne Auswahl wird die alphabetisch erste verfügbare Wetterentität verwendet;
ohne Wetterentität bleibt die Anzeige verborgen. Nicht verfügbare oder länger
als eine Stunde nicht gemeldete Werte erscheinen als unbekannt, nicht als 0 °C.
Die Wetteranzeige hat keinen Einfluss auf die Energieregelung oder EOS-Prognose.

Ein Klick auf das **Wettersymbol** oder den PV-Knoten öffnet die Ansicht
**PV & Wetter**. Oben stehen die aktuelle PV-Leistung, der heutige Ertrag, der
erwartete Rest und die Prognose für morgen. Darunter folgen das aktuelle Wetter mit
Bewölkung und der Vergleich „PV jetzt ≈ x % der Prognose“, eine stündliche Leiste bis
zum Ende des nächsten Tages mit Wetter, Temperatur und Bewölkung über dem erwarteten
PV-Ertrag je Stunde sowie Tageskarten für heute, morgen und übermorgen. Stunden ohne
PV-Ertrag fasst das Backend zu einem Nachtblock mit Tiefsttemperatur zusammen;
Stunden ohne PV-Prognose bleiben sichtbar und gelten nicht als Nacht. Antippen einer
Stunde zeigt Wetter, Niederschlag, Regenwahrscheinlichkeit und PV-Ertrag. Die
Tageskarten zeigen einen Erwartungswert, keine Spanne. Beginnt die stündliche
Wetterprognose erst mit der nächsten vollen Stunde, zeigt „Jetzt“ das aktuelle Wetter.
Die Leiste lädt neu, wenn sich die PV-Prognose ändert, spätestens alle 15 Minuten;
bis die neue Prognose da ist, bleibt die bisherige Anzeige stehen.

**Was EOS daraus macht** fasst die nächsten 24 Stunden zusammen: deutlich weniger
oder mehr Sonne morgen (unter 50 % bzw. über 150 % von heute), Speicher wird mit PV
voll, Speicher lädt aus dem Netz (Zeitraum, Energie, Ø-Preis), Einspeisung von
PV-Überschuss und Fahrzeuge, die aus dem Netz oder mit PV laden. Das Backend leitet
diese Aussagen aus der EOS-Prognose und dem Ladeplan ab; jede Zeile führt zur
passenden Ansicht. Links führen zu **Verlauf & Diagramme** (bisherige PV-Detailansicht)
und zu **Netz & Einspeisung**.

Die Wetterquelle muss die **stündliche** Home-Assistant-Aktion
[`weather.get_forecasts`](https://www.home-assistant.io/integrations/weather/#action-weatherget_forecasts)
unterstützen. Tagesprognosen werden nicht in Stunden umgerechnet. Die Abfrage reicht
72 Stunden voraus, erfolgt erst beim Öffnen der Ansicht oder nach einer neuen
PV-Prognose und wird fünf Minuten zwischengespeichert. Die ausgewählte Wetterentität
wird nicht durch eine andere Quelle ersetzt. Temperaturwerte verwenden die HA-Einheit;
Niederschlagsmengen werden in mm angezeigt. Unbekannte Werte bleiben Lücken,
insbesondere bedeutet fehlender Niederschlag nicht 0 mm. Die PV-Leiste funktioniert
auch bei einem Wetterfehler; der Grund steht dann über der Leiste.

Nach Updates lädt die Ansicht ein fehlendes Modul bei Bedarf mit der Version des
laufenden Panels nach, auch wenn der Browser noch ein älteres Startskript verwendet.
Schlägt das Nachladen fehl, bleibt die Oberfläche benutzbar, ein Browserhinweis
erscheint und ein erneuter Aufruf der Ansicht versucht es wieder. Bei weiterhin
unvollständigen UI-Dateien die Integration vollständig aktualisieren und die
Oberfläche neu laden.

### Schutz der InfluxDB-Zugangsdaten

Ohne Passwort-Umgebungsvariable speichert Home Assistant das eingegebene Passwort in
seinem Konfigurationseintrag. Es wird beim späteren Öffnen des Formulars nicht
wieder angezeigt; ein leeres, nicht übermitteltes Feld behält das Passwort bei.
Vorhandene Backups und Logdateien werden durch die Migration nicht bereinigt.

Alternativ stellt der Administrator das Passwort vor dem Start des
**Home-Assistant-Core-Prozesses** über eine Umgebungsvariable bereit und trägt nur
deren Namen ein. Die Bereitstellung ist installationsabhängig; eine Variable in
einem separaten Add-on reicht nicht aus. Beim Umstellen wird das gespeicherte
Passwort aus dem aktiven Eintrag entfernt. Ist die Variable nicht vorhanden, kann
die Integration nicht mit diesem Zugang starten. Zugriff auf Prozessumgebung und
Backups muss weiterhin geschützt werden. Ein externer Secret Manager oder eine
TPM-gestützte Bereitstellung kann dafür verwendet werden, wird von dieser
Integration aber nicht selbst eingerichtet oder garantiert.

Für die InfluxDB-Verbindung TLS und ein Benutzerkonto mit möglichst geringen
Leserechten verwenden. Ein Hash mit Salt und Pepper ersetzt dieses Passwort nicht:
für die Anmeldung an InfluxDB benötigt der Client das ursprüngliche Geheimnis.
