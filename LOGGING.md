# Backend, Oberfläche und Protokollierung

Die Regelung läuft im Backend auch bei geschlossenem Panel. Geräte- und EOS-Abrufe,
Bestätigungen, Fristen, Messwertgültigkeit und Steuerbefehle werden dort geprüft.
Auch fachliche Anzeigewerte entstehen im Backend: PV-Tagesenergie und -Prognosesummen,
zusammengeführte Verbrauchsbilanzen, gewichtete Preise, nächste Planmodi und
Zeitintervalle mit Datenlücken. Lokale Abfahrtsvorgaben werden in der Anlagenzeitzone
interpretiert; nicht existierende Uhrzeiten beim Sommerzeitwechsel werden abgelehnt.

Das Frontend übermittelt Eingaben und stellt die Antworten dar. Übersetzung,
Zahlen-/Datumsformatierung, Diagrammkoordinaten, Auswahl und Bedienung bleiben im
Browser. Browserseitige Eingabehilfen ersetzen keine Backendvalidierung. Es gibt
keine browserseitige Ladefreigabe oder Ersatzberechnung bei fehlenden Backendwerten.

## Warnungen und Fehler

Ohne Strompreis-Sensor oder Plugin-Preis wird der EOS-Preis als Quelle `eos`
ausgewiesen. Fehlgeschlagene oder unvollständige Preisabrufe verwenden die Kennung
`system/eos_price` mit festen Fehlerdetails, unabhängig von Browserabrufen.
HTTP-Debugmeldungen verwenden `eos_prediction_series`, ohne URL, Rohantwort oder
Preiswerte zu protokollieren. Erfolgreiche Folgeabrufe beheben die Meldung.
Nicht mehr aktuelle Preisintervalle und mindestens zwei Minuten alte Abrufe
werden für Livewerte, Steuerung und neue Bilanzbuchungen verworfen.

Der EOS-Einrichtungsassistent verwendet die Kennung `api/eos_setup` für Anzeige,
Backend-Log und Diagnose. Ungültige Eingaben, abgelaufene Vorschauen,
Konfigurationskonflikte sowie fehlende Schreib-/Speicherbestätigungen werden dort
mit festen Ursachenkennungen erfasst und dedupliziert. Koordinaten, vollständige
Konfigurationen, Vorschauwerte, Tokens und Anbieterzugangsdaten werden nicht
protokolliert. Ein Smartphone-Ortungsfehler bleibt ausschließlich im Browser.
Die Plansperre nach einer Änderung wird als `setup_plan_pending` im bestehenden
EOS-Planfehler erfasst und mit einem neuen gültigen Plan behoben.

Bestätigter Notstrombetrieb erscheint als normale Information (`INFO`)
`backup_power_active`, ein nicht
bestätigter zuvor unterstützter oder konfigurierter Status als
`backup_power_unknown`. Beide verwenden die gemeinsame Kennung
`system/power_supply` in Anzeige, Backend-Log und Diagnosedaten. Der Wechsel
zu unbekannt bleibt eine aktive Warnung; bestätigter Netzbetrieb behebt sie.
Die Betriebszustände `backup` und `power_supply_waiting` beschreiben die
automatische Regelpause mit erhaltenem Steuerungswunsch. Erwartbar nicht
verfügbare Netz-/Hausmesswerte erzeugen nur bei bestätigtem Notstrom keine
Panel-Warnung; Rohmesswerte und Plugin-Diagnosen bleiben erhalten. Unbestätigte
Freigaben sind weiterhin Fehler. Der Wiederanlauf benötigt bestätigten
Netzbetrieb, erfolgreiche Freigabe und die normalen gültigen Regelgrundlagen.
Die im Notstrom abgeleitete Gesamtverbrauchsquelle ist in `source_configuration`
als Typ `backup` mit Eingangsgröße `inverter_ac` gekennzeichnet. Fehlende oder
ungültige AC-Werte bleiben als Verbrauchswarnung sichtbar. Eine erneut gestartete
Wallbox wird bei aktiver Standardsperre wieder gestoppt; unbestätigte Stopps
verwenden weiterhin `wallbox_stop`. Der native Binärsensor `backup_power` gibt
nur bestätigte Betriebszustände aus; normale Informationsmeldungen aktivieren
den Problembinärsensor nicht.

Kurze Kommunikationsfehler mit EOS (Zeitüberschreitung, abgewiesene oder
abgebrochene Verbindung, HTTP 408/409/423/429/500/502/503/504) erscheinen erst als
Hinweis und Warnung im Log, wenn sie zwei Minuten anhalten. Das betrifft
`system/eos`, `system/eos_price`, `system/eos_measurements`, `system/goal`,
`system/battery_limits`, `system/vehicle_limits` sowie `accounting/eos_error` und
`accounting/pv_error`. So erzeugt ein EOS, das während der Optimierung kurz nicht
antwortet, keine Meldungsflut. Die Regelung sieht den Fehler sofort; er wird nur
für Anzeige und Log zurückgehalten. Jeder fehlgeschlagene Abruf steht weiterhin
als DEBUG-Eintrag `Backend request failed` im Log. Andere Fehler, etwa HTTP 404
oder ungültige Antworten, erscheinen sofort. Ein angezeigter Hinweis bleibt bis zur
Behebung sichtbar, auch wenn die Ursache zu einer Zeitüberschreitung wechselt.
Die Wartezeit auf EOS-Antworten ist mit `eos_timeout_s` einstellbar (Standard
10 Sekunden); InfluxDB und die Fronius Solar API verwenden weiterhin 5 Sekunden.

Das Backend liefert `notices` mit Kennung, Schweregrad und Kontext. Dieselben
Meldungen erzeugen die HA-Problemanzeige und Einträge unter
`custom_components.eos_energiezentrale`, unabhängig davon, ob ein Browser sie abruft.

- **WARNING:** fehlende/veraltete Messquellen, fehlgeschlagene EOS-Abgleiche,
  Planabrufe, Verlaufs-/Bilanzabrufe und abgelehnte API-Eingaben.
- **ERROR:** Regelungsfehler, nicht bestätigtes Stoppen oder Freigeben von Geräten
  sowie fehlgeschlagene Speicherung der Steuerfreigabe.
- **INFO:** Behebung eines Problems und Wechsel des Steuerungsstatus, einschließlich
  regulärem Warten auf eine neue Fahrzeugplanung. Das Erreichen des Speicher-Minimums
  ist ebenfalls ein Informationsereignis.
- **DEBUG:** Beginn, Ende, Fehlerklasse und Dauer von HTTP-Abrufen, mit festen
  Vorgangsbezeichnungen wie `eos_plan` oder `eos_vehicle_config`.

Die Übertragung der Messwerte an EOS (Ladestand und Leistung von Speicher und
Fahrzeugen) meldet Fehler als Warnung `eos_measurements` und wiederholt sie nach
einer Minute. Bietet EOS keine Mess-API, steht einmalig
`eos_measurements_unsupported` im Log (INFO); fehlen Schlüssel in EOS, nennt
`eos_measurement_keys_missing` einmalig die betroffenen Schlüssel. Die Diagnosedatei
enthält unter `eos_measurements`, ob die API unterstützt wird, welche Schlüssel
gesendet werden, welche fehlen und wann zuletzt gesendet wurde, ohne Messwerte.

Ein einzelner fehlgeschlagener Abruf eines Speichers, der den Netzstatus selbst
meldet, erzeugt `backup_power_unknown` erst, wenn der zuletzt bestätigte Netzbetrieb
älter als 60 Sekunden ist; der Lesefehler bleibt als `plugin_read_failed` sichtbar.

Ist ein Gerät während der Steuerung nicht erreichbar (auch Modbus-Ausnahme 10 oder 11
eines Gateways wie des Victron GX), erscheint statt `runtime`
die Warnung `control_resume`: Die Steuerung ist pausiert und wird jede Minute
wieder aufgenommen. Gelingt ein Regelzyklus, wird `control_resume` als behoben
protokolliert. Nach 30 Minuten ohne Verbindung wird daraus der Fehler `runtime`,
und die Steuerung bleibt aus. Eine nicht bestätigte Freigabe während des Ausfalls
bleibt der Fehler `release`.

Die Meldungskennung bleibt zwischen Anzeige, Log und Diagnosedaten gleich.
`sources_unavailable` enthält beispielsweise den Messwerttyp `solar`, die Ursache
`stale` und die erlaubte Höchstaltergrenze. EOS-Fehler enthalten nach Möglichkeit
HTTP-Status, Fehlerklasse, Verbindungsursache oder feste Ursachenkennungen wie
`effective_limits_differ` samt betroffenen Feldnamen. Ein begrenzter Aufrufpfad
enthält nur Modul, Funktion und Zeilennummer, ohne absolute Dateipfade oder Quelltext.

Ein unverändertes Problem wird nicht bei jedem Poll erneut protokolliert. Beim
Auftreten, bei einer Änderung der Ursache und bei Behebung entsteht ein Eintrag.
Die Diagnosedatei enthält unter `issues` die aktiven Meldungen und die letzten
50 Übergänge seit dem Start. Für ältere Ereignisse dient das Home-Assistant-Log.
Adressen, Zugangsdaten, Namen, Messwerte, Ladeziele, rohe Antworten und rohe
Exception-Texte werden nicht in diese Diagnoseeinträge übernommen.

Für zusätzliche Informationen kann der vorhandene `logger`-Abschnitt in
`configuration.yaml` beispielsweise um Folgendes ergänzt werden:

```yaml
logger:
  default: warning
  logs:
    custom_components.eos_energiezentrale: info
```

Für die Dauer einer Fehlersuche kann statt `info` der Wert `debug` genutzt werden.
Home Assistants eigene Log-Konfiguration entscheidet über Speicherung und Filterung.
Bei einem auf `error` eingeschränkten Logger werden Warnungen entsprechend gefiltert.

## Plugin- und Konfigurationsfehler

Die gemeinsame Plugin-Leseschnittstelle protokolliert auch Ausfälle, die nicht in
einer ausgewählten Haus-/PV-Quelle sichtbar werden. Das umfasst geworfene und intern
abgefangene Lesefehler, fehlende bzw. ungültige Messwerte, unbekannte Gerätezustände
und fehlende Steuerdaten angeschlossener Wallboxen. Gültige Nullwerte sind keine
Fehler; abgewählte optionale Messquellen werden nicht verlangt.

Die Einträge nennen die Plugin-Kennung und einen technischen Ort wie `device/2`
oder `vehicle/1/wallbox`. Nummern entsprechen der Reihenfolge der Geräte bzw.
Fahrzeuge. Bei Victron-Modbusfehlern werden Leseabschnitt, Unit, Registeradresse,
Anzahl und Ausnahme-Code übernommen, soweit vorhanden. Wiederholungen werden pro
Plugin-Instanz dedupliziert; ein wieder erfolgreicher Abruf erzeugt einen INFO-Eintrag.
Dies gilt auch für die bisherige Fronius-Speichergruppe.

Alle drei Victron-Plugins (`victron_modbus`, `victron_ha`, `victron_gx`) erfassen
zusätzlich Fehler beim Ermitteln der Leistungsgrenzen, bei ESS-Steuerbefehlen und
bei der Gerätefreigabe als `plugin_operation_failed` mit eigenem Vorgang im Ort
(z. B. `device/1/apply`). Modbusfehler enthalten den aktuellen Registerkontext,
HA-basierte Fehler den festen Steuerparameter und Prüfschritt. Fehlende Entitäten,
nicht verfügbare Zustände, falsche Einheiten und veraltete Messungen bleiben als
unterschiedliche Ursachen erkennbar. Ein erfolgreicher Leseabruf bestätigt keinen
fehlgeschlagenen Steuerbefehl; erst der erfolgreiche jeweilige Vorgang behebt ihn.
Diese Prüfung nutzt simulierte GX-/HA-Antworten und ersetzt keinen Hardwaretest.

Deye-Modbus protokolliert für Speicher und PV-Wechselrichter den fehlgeschlagenen
Leseabschnitt, die konfigurierte Unit-ID, Registeradresse, Anzahl und gegebenenfalls
den Modbus-Ausnahme-Code. Ungültige Teilwerte behalten ihre Feldadresse; gültige
übrige Werte bleiben erhalten. Fernsteuerung, Leistungsgrenzen und Freigabe werden
als eigene Vorgänge überwacht. Schlägt nach einer Aktivierung auch das Rücksetzen
fehl, bleiben beide Ursachen getrennt sichtbar.

Generic-Speicher, -Wechselrichter und -Wallbox sowie Fronius über HA unterscheiden
fehlende Entitäten, nicht verfügbare Zustände, ungültige Einheiten und veraltete
Messungen. Wallbox-Steuerdaten nennen nur feste Parameter wie `current` oder
`phase_feedback`, niemals Entitätsnamen. Steuerfehler enthalten den jeweiligen
Vorgang und Prüfschritt. Normales Warten auf Phasenrückmeldung bleibt fehlerfrei;
eine zuvor fehlgeschlagene Umschaltung wird erst durch bestätigte Phasen behoben.
Fronius behält seine Wartefrist für modusabhängige Leistungsentitäten bei und
protokolliert sowohl das Warten als auch den Ablauf der Bestätigungsfrist.

Fehler beim Laden von Plugins, bei der Integrationseinrichtung und in den nativen
HA-Konfigurationsdialogen werden ebenfalls im Backend erfasst. Bei einem ungültigen
Plugin-Parameter wird dessen Feldname statt seines Inhalts protokolliert. Aktive
Plugin-Leseprobleme und Konfigurationsereignisse stehen zusätzlich in den Diagnosen.

## Browser- und Verbindungsfehler

Ladefehler von UI-Dateien, Darstellungsfehler und fehlgeschlagene Verbindungen sind
Browserereignisse. Sie bleiben in der Oberfläche bzw. Browserkonsole. Es gibt weder
einen Meldepuffer noch eine Nachlieferung an das Backend, auch nicht nach einem
HA-Neustart. Frühere Panels können noch alte Meldungen gepuffert haben: Diese
werden ohne Auswertung, Speicherung oder Logeintrag quittiert und verworfen.
Auch normale Panelanfragen während des HA-Starts erzeugen keinen zusätzlichen
Integrations-Logeintrag für den vorübergehenden Zustand „noch nicht geladen“.
Meldungen anderer HA-Integrationen, etwa `cover/set_cover_position`, gehören zum
HA-Core bzw. zur betroffenen Integration und werden nicht als EOS-Fehler ausgegeben.

## English

Device control, EOS requests, confirmations, measurement freshness, deadlines and
all domain calculations run in the backend. This includes PV energy/forecast
totals, merged accounting totals, weighted prices and plan/gap classification.
Local departure input uses the installation timezone. The frontend handles input,
translation, formatting and drawing, and consumes backend notices/statuses directly.

Every backend notice is logged even without an open panel. Unchanged incidents
are deduplicated; activation, changed causes and recovery are recorded. Warning
and error events contain stable codes, exception/HTTP context and safe field names;
they never include addresses, credentials, device names, measurements, targets or
raw exception messages. Diagnostics retain the last 50 transitions in memory.
INFO includes recovery/normal waiting; DEBUG adds bounded HTTP operation timings.

Short EOS communication failures (timeout, refused or dropped connection, HTTP
408/409/423/429/500/502/503/504) become a notice and a log warning only once they
last two minutes. This covers `system/eos`, `system/eos_price`,
`system/eos_measurements`, `system/goal`, `system/battery_limits`,
`system/vehicle_limits`, `accounting/eos_error` and `accounting/pv_error`, so an EOS
that briefly stops answering while it optimizes does not flood the notices.
Control sees the failure at once; only display and log wait. Every failed request
is still logged at DEBUG as `Backend request failed`. Other failures, such as HTTP
404 or an invalid response, are shown at once, and a shown notice stays until it is
resolved. The EOS response timeout is configurable as `eos_timeout_s` (default
10 seconds); InfluxDB and the Fronius Solar API keep 5 seconds.

A device that cannot be reached during control (timeout, refused or dropped
connection, or Modbus gateway exception 10/11) raises the warning `control_resume` instead of `runtime`: control is
paused, not stored as switched off, and taken back every minute once readings and
an EOS plan are valid. After 30 minutes it becomes the `runtime` error and control
stays off. Refusals and wrong confirmations of a device still switch control off.

A single failed read of a storage device that reports the power supply raises
`backup_power_unknown` only once the last confirmed grid report is older than
60 seconds; the read failure itself stays visible as `plugin_read_failed`.

Plugin reads are monitored independently of the selected HA measurement sources.
Exceptions, suppressed partial failures, incomplete/invalid telemetry and missing
charger controls are logged per instance, with plugin ID, ordinal scope and safe
protocol context. Valid zero readings and disabled optional sources remain valid.
Native configuration forms, plugin registration and integration setup log rejected
configurations with parameter names, never parameter values.

All three Victron plugins (`victron_modbus`, `victron_ha`, `victron_gx`) also log
power-limit, ESS command and release failures as `plugin_operation_failed`, with
the operation in the scope (for example `device/1/apply`). Safe details identify
the Modbus register or fixed HA control parameter and validation step. Missing
entities, unavailable states, invalid units and stale samples have distinct causes.
A successful read cannot resolve a failed command; only that operation's success
resolves it. Simulated GX/HA regression tests do not replace hardware testing.

Deye storage and PV drivers include the failed read stage, configured unit ID,
register address/count and Modbus exception code when available. Invalid partial
values retain their field address while other valid readings remain available.
Remote control, power limits and release have separate incidents. A failed
activation and a failed cleanup retain both causes independently.

Generic storage/inverter/wallbox drivers and Fronius HA distinguish missing entities,
unavailable states, invalid units and stale samples. Wallbox control diagnostics
use fixed parameter names, never entity IDs. Command failures include the operation
and validation step. Normal pending phase feedback is not an error and cannot
resolve a previously failed switch. Fronius retains its mode-dependent limit wait
period and logs both the pending control and confirmation timeout.

Browser-only failures stay in the browser. They are neither queued nor forwarded
to the backend after reconnect/restart. Old reports from cached previous panels are
acknowledged and discarded without logging or persistence. Ordinary panel requests
during HA startup do not produce integration-not-ready log spam. Other integrations'
service failures remain HA/the respective integration's responsibility.
