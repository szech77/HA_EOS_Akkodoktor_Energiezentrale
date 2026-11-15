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
