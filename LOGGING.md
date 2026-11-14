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

## Browser- und Verbindungsfehler

Ladefehler von UI-Dateien, Darstellungsfehler und fehlgeschlagene Verbindungen sind
Browserereignisse. Sie werden mit festen Codes an das Backend gemeldet und dort
protokolliert. Der Kanal nutzt die bestehende HA-Authentifizierung und
Administratorprüfung. Er akzeptiert keine freien Fehlermeldungen oder Messdaten.

Solange die Verbindung unterbrochen ist, ist kein sofortiger Backend-Logeintrag
möglich. Das offene Panel puffert bis zu 32 Ereignisse und übermittelt sie nach
Wiederherstellung der Verbindung; bei Übertragungsfehlern wird frühestens nach
30 Sekunden erneut versucht. Die Browserkonsole enthält ebenfalls den festen Code.
Beim Schließen des Panels kann ein noch nicht übertragener Puffer verloren gehen.
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

Browser-only failures use a coded, authenticated administrator-only reporting
channel. During a connection outage the open panel queues up to 32 events for
delivery after reconnecting, retrying no sooner than 30 seconds after failure.
Closing the panel may lose undelivered events; immediate server logging while
disconnected is impossible. Other integrations' service failures remain HA/the
respective integration's responsibility.
