# Changelog

Die Release-Pipeline verwendet die Integrationsversion aus manifest.json und die
zugehörigen Änderungen. Releases entstehen nach erfolgreichen Prüfungen auf main.

## 0.7.2 - 2026-11-11

### Features

- Keine.

### Bugfixes

- Die Panel-Warnung „Daten oder Steuerung prüfen · Prognose“ erscheint erst nach fünf Minuten durchgehend fehlgeschlagenem EOS-Prognoseabruf. Eine erfolgreiche Antwort setzt die Frist zurück und entfernt die Warnung sofort. Kurzzeitige Ausfälle und die Startphase lösen die Meldung nicht mehr sofort aus.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.7.1 - 2026-11-11

### Features

- Keine.

### Bugfixes

- Keine SoC-Warnung bei einem vorhandenen, unveränderten Fahrzeug-Ladezustand. Die Warnung erscheint erst nach mehr als fünf Minuten durchgehend ohne gültigen Wert, verschwindet bei Wiederkehr sofort und wird je Fahrzeug getrennt ermittelt. Andere Messquellen behalten ihre bisherigen Altersprüfungen.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.7.0 - 2026-11-11

### Features

- Abschaltbarer, standardmäßig deaktivierter speichergestützter PV-Ladestart bei Überschuss unterhalb der minimalen Fahrzeugladeleistung. Speicher-Untergrenze (Standard 50 %), durchgängige Überschussdauer (Standard 60 s) und Überschuss-/Defizitschwelle (Standard 150 W) sind im Panel und als HA-Entitäten einstellbar. Start mit zwei Prozentpunkten SoC-Hysterese; die allgemeine Speicher-Untergrenze bleibt wirksam.
- Vor dem Ladestart bestätigte Sperre der Speicherladung und Freigabe der Eigenverbrauchsentladung. Die Regelung berücksichtigt ein- und dreiphasige Mindestleistung, verfügbare Entladeleistung und gemeinsame Netzleistungsreservierungen mehrerer Fahrzeuge. PV-Schwankungen während einer laufenden Ladung werden überbrückt: Stopp nach 60 Sekunden durchgehendem PV-Defizit ab der eingestellten Schwelle gegenüber allen übrigen Verbrauchern ohne dieses Auto. Erholung setzt die Stoppwartezeit zurück; Erreichen der SoC-Untergrenze und Sicherheitsfehler stoppen sofort.

### Bugfixes

- Gemeinsame Speicherregeln werden im Mehrfahrzeugbetrieb vor der Regelung an alle Fahrzeuge weitergereicht.

### Breaking Changes

- Keine. Ohne Aktivierung bleibt das bisherige PV-Startverhalten erhalten.

### Security

- Keine.

## 0.6.0 - 2026-11-11

### Features

- Neues Plugin `nrgkick_local` für die lokale NRGkick-Gen2-JSON-API ohne zusätzliche HA-Wallbox-Sensoren oder Steuerentitäten: Leistung, Status, Ladestrom und Gerätegrenzen direkt lesen; Laden pausieren/freigeben und Strom in 0,1-A-Schritten einstellen.
- Optional aktivierte Phasenumschaltung mit bestätigtem Ladestopp, zwei neuen Nullleistungsmessungen und Rückbestätigung der Phaseneinstellung. Hardware-/Adaptergrenzen werden zur Laufzeit berücksichtigt.
- Mehrere direkt angebundene NRGkicks mit gemeinsamer Leistungsreservierung und Erkennung doppelt konfigurierter Geräteadressen.
- Anschlussabhängige Phasenzahl und Ladeleistung aus Geräte-, Adapter- und Netzgrenzen lesen und mit der konfigurierten Stromgrenze als Leistungsgrenzen und Ladestufen an EOS übertragen; Änderungen werden separat rückbestätigt.
- Nicht erreichbare NRGkicks und nicht angeschlossene Fahrzeuge werden ausgegraut und aus der Fahrzeugplanung genommen. Speicher und erreichbare Fahrzeuge bleiben regelbar; unbestätigte Ladestopps bleiben sichtbar und fehlende Verbrauchsmessungen unbekannt. Wiederverbinden stellt die aktuellen Ladegrenzen und den konfigurierten Zeitplan wieder her.

### Bugfixes

- Keine.

### Breaking Changes

- Keine. Das bisherige Plugin `nrgkick` für HA-Entitäten bleibt verfügbar.

### Security

- Optionale Basic-Auth-Anmeldung mit Passwort aus einer HA-Prozess-Umgebungsvariable; keine Passwörter in Plugin-Parametern. Keine HTTP-Weiterleitungen oder Umgebungs-Proxys, begrenzte Antworten und Zeitüberschreitungen sowie bereinigte Fehlermeldungen. Schreibbefehle benötigen ein separates Rücklesen.

## 0.5.0 - 2026-11-11

### Features

- PV-Leistung und gesamter Hausverbrauch ebenfalls über `fronius_modbus`: PV aus den PV-Kanälen, Hausverbrauch aus AC-Wechselrichterleistung und Netzanschlussleistung. Die drei Sensorfelder für PV, Hausverbrauch und Netz können gemeinsam leer bleiben; fehlende Teilwerte bleiben unbekannt.
- Netzanschlussleistung über den Fronius-Smart-Meter-Gateway des GEN24, mit konfigurierbarer Unit-ID und Integer-/Float-SunSpec-Zählermodellen. Optionale Quellsensoren haben Vorrang vor deklarierten Plugin-Messwerten; fehlende Konfiguration und vorübergehend ungültige Quellen werden im Panel getrennt angezeigt. Gemeinsame Netzleistungsreservierung mehrerer Fahrzeuge nutzt dieselbe Quellenwahl.
- Eigenes Speicher-Plugin `fronius_modbus` für direkte Fronius-GEN24-Steuerung über Modbus TCP/SunSpec 124: Lade-/Entladelimits, Entladesperre, erzwungene Ladung und optional Netzentladung sowie Rückgabe an die Automatik. SoC und DC-Lade-/Entladeleistung werden aus SunSpec 124/160 direkt gelesen; zusätzliche HA-Speichersensoren und Steuerentitäten entfallen.
- Automatische SunSpec-Modellerkennung für int+SF und float sowie skalierte, atomar geschriebene Leistungsfenster mit Register-Rückbestätigung und 300 Sekunden Gültigkeit.

### Bugfixes

- Geleerte Quellsensor-Auswahlfelder übernehmen beim Speichern nicht erneut die alten Sensor-IDs; vorhandene Werte werden als löschbare Vorschläge angezeigt.

### Breaking Changes

- Keine. Das bisherige Plugin `fronius` bleibt unverändert verfügbar.

### Security

- Modbus-Antworten werden auf Transaktion, Protokoll, Unit-ID, Funktion und Länge geprüft; fehlende Bestätigungen brechen die Steuerung ab. Geräteerkennung und Parameterprüfung erfolgen vor Steuerbefehlen, Netzentladung benötigt eine zusätzliche Plugin-Freigabe. Modbus TCP bleibt ein unverschlüsseltes lokales Protokoll ohne Authentifizierung.

## 0.4.0 - 2026-11-11

### Features

- Anfänglicher Akkuinhalt ohne Anschaffungspreis wird als PV-Ladung zur Einspeisevergütung bzw. zum manuellen PV-Kostenansatz einschließlich Ladeverlusten geschätzt. Unbekannter Restbestand bestehender Installationen wird einmalig bewertet, bekannte Kosten und vergangene Auswertungen bleiben erhalten.
- PV-Tagesprognosen werden zentral im Backend berechnet, einschließlich lokaler Tagesgrenzen und Zeitumstellung.
- Optional kann das InfluxDB-Passwort aus einer Umgebungsvariable des Home-Assistant-Prozesses bezogen werden.

### Bugfixes

- Veraltete oder ungültig datierte Akkumesswerte werden nicht als aktuelle Werte für die Steuerung verwendet.
- Langsame InfluxDB-Historienabfragen blockieren keine Steuerungsänderungen mehr.
- EOS-Abfragen für Einspeisetarif und Akku-Kostenparameter blockieren die Steuerung nicht mehr; bei zwischenzeitlich geänderten Kosteneinstellungen werden veraltete Antworten verworfen.
- EOS-Plan und Prognose werden unabhängig vom Steuerungslauf abgerufen; geplante Stopps und die zeitlich begrenzte Nutzung des letzten gültigen Plans bleiben wirksam.
- Akku-SoC-Grenzen werden im Hintergrund an EOS übertragen. Zwischenzeitlich geänderte Grenzen bleiben unbestätigt und werden anschließend erneut übertragen.
- E-Auto-Ladeziele werden pro Fahrzeug im Hintergrund übertragen. Überholte Bestätigungen geben keine planbasierte Ladung frei; Änderungen und deaktivierte Planungen werden erneut an EOS gesendet.
- Parallele Konfigurationsänderungen derselben EOS-Instanz aus der Integration werden serialisiert, damit sich Geräteänderungen nicht gegenseitig überschreiben.
- Ein bereits gespeichertes InfluxDB-Passwort wird nicht als Vorgabe im Konfigurationsformular ausgegeben.

### Breaking Changes

- Hardware-Plugin-API 2: Drittanbieter-Plugins müssen die API-Version aktualisieren; Akkutreiber müssen die Zeitstempel ihrer einzelnen Messwerte liefern. Siehe PLUGINS.md.

### Security

- Der Hardwareadapter beschränkt Pluginzugriffe auf die zugeordneten Entitäten. Plugins bleiben vertrauenswürdiger Python-Code und laufen im Home-Assistant-Prozess.
- Für passwortgeschützte InfluxDB-Verbindungen über HTTP wird eine Warnung ausgegeben. Eine durch eine neuere Option überholte Passwortkopie wird bei der Einrichtung entfernt.

## 0.3.3 - 2026-11-11

### Features

- Repositoryweite Agent-Anweisungen für vollständige Pull Requests mit Release-Metadaten, Kompatibilitätsprüfung und Tests ergänzt, insbesondere für die Nachbearbeitung von Dependabot-Updates.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- `github/codeql-action/upload-sarif` für die Veröffentlichung der Sicherheitsberichte in GitHub Code scanning von Commit `5895b2c9be147bc7f1c75ce72c5cb577febb1907` auf `33d7b85da1a04171e211befe2c739303b9a4c066` aktualisiert.

## 0.3.2 - 2026-11-10

### Features

- Keine neuen Funktionen der Energieverwaltung.

### Bugfixes

- CI-Push-Prüfungen laufen auch für `bugfix/**`-Branches.

### Breaking Changes

- Keine.

### Security

- Bandit, pip-audit und Trivy veröffentlichen ihre Findings als SARIF in GitHub Code scanning.
- Secret-Inhalte und Codeausschnitte werden nicht in die Security-Berichte übernommen.
- Berichte werden auch bei Findings übertragen; Scanner- und Uploadfehler blockieren weiterhin die Pflichtprüfung.

## 0.3.1 - 2026-11-10

### Features

- Keine neuen Funktionen.

### Bugfixes

- Beträge unter einem Cent werden mit bis zu vier Euro-Nachkommastellen dargestellt, damit kleine PV-Anteile nicht wie kostenlose Energie wirken.
- Kostenaufteilung unterscheidet Gesamtbetrag in Euro und Preis pro kWh; unvollständige Kosten werden ausdrücklich als bekannter Anteil gekennzeichnet. Tageskosten ohne bekannte Anschaffungspreise erscheinen als unbekannt.
- Screenshot-Simulation nutzt 8,2 ct/kWh PV-Kosten und eine nachvollziehbare Netzladungsbewertung des anfänglichen Akkuinhalts.

### Breaking Changes

- Keine.

### Security

- Keine sicherheitsrelevanten Änderungen.

## 0.3.0 - 2026-11-10

### Features

- Eigenes EOS-Logo als themeabhängiges Home-Assistant-Seitenleistensymbol, global ohne vorheriges Öffnen des Panels geladen.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine sicherheitsrelevanten Änderungen.

## 0.2.0

### Features

- Aktuelles Wettersymbol und Temperatur im Energieflussdiagramm mit optional auswählbarer Home-Assistant-Wetterquelle.

- Lokales Integrationslogo für Home Assistant Geräte & Dienste, mit transparenten hellen und dunklen PNG-Varianten in normaler und doppelter Auflösung.

- JavaScript-Tests im nativen VS-Code-Test-Explorer über node:test runner; Workspace-Empfehlung, begrenzte Test-Erkennung und ausführbare JavaScript-Testaufgabe.

- Eigenständiges SVG-Logo mit türkisem Energiering, zentralem E und Solar-Akzent im Kopfbereich und im klickbaren Zentrum des Energieflussdiagramms.

- Lineare Leistungsringe im Uhrzeigersinn für PV, Akku und Fahrzeuge; optionaler Wärmepumpenring über Prozent-/Faktor-Entität und konfigurierbare PV-Bezugsleistung.

- Versionierte, zur Laufzeit geprüfte Hardware-Interfaces mit Plugin-Namen, Fähigkeiten und dynamischer Erkennung im Plugin-Ordner; Fronius/NRGkick ausgelagert.
- Generische HA-Wallbox-/Speicher-Plugins für Sensoren, native Steuerentitäten und Helfer; zentrale Sanitiser-Grenze und Berücksichtigung fehlender Phasenumschaltung.
- Plugin-gesteuerte Konfigurationsfelder nach der Auswahl; wiederholbarer Hinzufügen-Ablauf für mehrere Wallboxen/Fahrzeuge.

- Tagesverbrauch und Energiekosten in der Übersicht; eigene Tag-/Monats-/Jahresauswertungen für Haus, Wärmepumpe und Fahrzeuge mit Quellenaufteilung, dauerhafter Bilanz und gekennzeichneter Influx-Rekonstruktion.
- Gewichteter Akku-Kostenbestand für gemischte PV-/Netzladung, einstellbarer PV-Kostenansatz sowie Lade-/Entladewirkungsgrad und Kapazität aus EOS oder manuellen Einstellungen.

- Proportionaler SoC-Balken im Autosymbol und in den individuellen Fahrzeugkarten; kein gemeinsamer SoC für mehrere Autos.

- Wärmepumpensymbol als größere SVG-Wärmelinien; Batterie mit fünf SoC-Füllbalken und roter Warnfarbe an der eingestellten SoC-Untergrenze.

- Konfigurierbarer Anzeigepuffer für letzte gültige Sensorwerte (Standard 15 Minuten), ohne veraltete Werte an Regelung oder Historie weiterzugeben.

- Bis zu acht Fahrzeug-/Wallbox-Paare mit eigener Planung, SoC-Verarbeitung, nativen Sensoren und gemeinsamer Reservierung von PV- und Netzanschlussleistung.

- E-Auto und Wärmepumpe optional; neue Einrichtungen ohne diese Verbraucher, ausgeblendete Stromflussknoten und passende Hausverbrauchsberechnung.

- PV-Detailansicht mit Tageserträgen in kWh für heute, morgen und übermorgen sowie Kennzeichnung unvollständiger Prognosen.

- Werteanzeigen per Maus, Touch und Tastatur; PV-Historie und Prognose in Speicher- und Autodiagrammen; gemeinsame Energieflussübersicht über die Mitte des Stromflussbilds.

- Eigene Batterie- und Auto-Symbole im Stromfluss sowie konfigurierbarer Fahrzeugname mit Standard E-Auto, auch für Detailseite, Zeitlinie und Fahrzeugsensoren.

- Steuerfreigabe bleibt über HA-Neustarts und Integrations-Reloads erhalten; Wiederaufnahme wartet auf gültige Eingangsdaten und EOS-Plan, während bewusstes Ausschalten und Regelfehler dauerhaft deaktivieren.

- Mindest- und Maximal-SoC des Hausspeichers als Alltagseinstellungen und native Zahlenentitäten; bestätigte EOS-Übergabe, persistente Wiederholungsversuche und identische lokale Regelgrenzen.

- Animierte Stromfluss-Punkte skalieren ihre Dicke und Länge mit der Leistung auf einer gemeinsamen, begrenzten Skala.

- Installation als HACS-Custom-Integration mit geführter Einrichtung in Home Assistant.
- Native Sensoren, Schalter, Ziel-SoCs, Regelparameter und Abfahrtsplanung.
- Eigenes Seitenleisten-Panel mit vorhandener Stromflussgrafik und Detailseiten.
- Inbetriebnahme-Optionen nach EOS-Verbindung, Sensoren, Hardware, Grenzen und Verlauf gegliedert.
- Native HA-Sprachdateien und Diagnosen ohne Zugangsdaten oder Haushaltsverlauf.
- Tests gegen Home Assistant 2026.11 für Lebenszyklus, Dienste, Einstellungen und authentifizierte Oberfläche.

### Bugfixes

- Deaktivierte Fahrzeugplanung entfernt EOS-Ladeziele auch nach einem Neustart ohne Fahrzeug-SoC; beide Terminformen werden gelöscht und die Abschaltung bestätigt.

- Einheitliche Inhaltsversion für Panel, HTML, JavaScript und CSS verhindert gemischte UI-Dateien nach Updates; aussagekräftige Meldungen für Sprach-, Verbindungs-, Datei- und Darstellungsfehler mit erneutem Ladeversuch und technischen Details.

- PV-Kosten standardmäßig aus der zur Laufzeit gelesenen EOS-Einspeisevergütung statt dem bisherigen Nullwert; manuelle Vorgabe und zeitabhängige Tarifintervalle bleiben berücksichtigt.

- Laufende Fahrzeugladung übernimmt geänderte EOS-Leistungsvorgaben auch ohne erneute Wallbox-Leistungsmeldung; die Messwert-Wartebedingung bleibt auf die reine PV-Nachregelung beschränkt.

- Fünf Minuten Überbrückung für ausgefallene oder unvollständige EOS-Pläne pro Fahrzeug; keine Fristverlängerung durch wiederholte Fehler. HA-Messwerte werden gegen den Zeitpunkt des eingelesenen Zustands statt gegen den Zeitpunkt vor einem langsamen EOS-Abruf geprüft.

- Allgemeine zeitliche Anzeigeausrichtung durch gezielte, auf 30 Sekunden begrenzte Verzögerung bei erwarteter Autoladung ersetzt; bewährte Regler-Warteprüfung bleibt erhalten.

- Asynchrone Netz-/Wallboxmeldungen: zeitlich abgeglichenes Stromflussbild und Prüfung neuer Messungen vor Phasen-, Strom- und PV-Stoppentscheidungen; begrenzte Wartefrist mit Pause bei ausbleibenden Meldungen.

- Fronius wartet bei vorübergehend nicht verfügbaren Leistungsentitäten bis zu 45 Sekunden über mehrere Polls; Freigabe bleibt erhalten, fehlende Bestätigungen geschriebener Sollwerte bleiben Fehler.

- Steuerfehler bleiben im Lesemodus diagnostizierbar; Regelschritt und betroffene Entität bei ausbleibender Bestätigung sowie vollständiger Stacktrace im HA-Log ergänzt.

- Steuerfreigabe wartet auch nach manuellem Aktivieren auf bereite Eingangsdaten und EOS-Plan; unvollständige EOS-Pläne werden als temporärer Abruffehler behandelt und löschen keine Freigabe.

- EOS-Modus- und Wallbox-Statussensoren bleiben Textsensoren; Sprachpakete werden ohne blockierenden Dateizugriff im HA-Eventloop geladen.

- HACS prüft Feature-Branch-Lizenzen lokal, während GitHub-Metadaten auf main validiert werden; Einrichtung von Beschreibung und Topics ergänzt und Energie-Kategorie im Manifest hinterlegt.

- Letzte gültige Wärmepumpenleistung bleibt mit Altersangabe in der Übersicht sichtbar; daraus geschätzter Hausverbrauch ist gekennzeichnet und wird nicht als frischer Regel- oder Verlaufswert verwendet.

- Frisch erneut gemeldete unveränderte Sensorwerte bleiben gültig; HA-Meldezeiten werden ohne veralteten Serialisierungscache gelesen. Speicher- und Hausleistungen bleiben dadurch auch bei inaktiven Verbrauchern sichtbar.

- Seitenleisten-Panel nutzt die volle Fensterhöhe und verfügbare Breite; kein Rückfall auf die iFrame-Standardhöhe.

- Gerätebefehle und Zustandsbestätigungen verwenden direkt die lokale HA-Dienst- und Zustandsverwaltung.
- Entfallene Altregler-Prüfung: vorhandene frühere Helper oder Automationen blockieren die neue Regelung nicht.
- Polling, Einstellungsänderungen und Stoppen werden serialisiert; blockierende Arbeit läuft im Executor.
- Unbestätigte Gerätefreigaben bleiben sichtbar und erneut versuchbar.

### Breaking Changes

- Eigenständiges Add-on, Supervisor-Zugriff, Ingress-Webserver und Docker-Auslieferung entfallen.
- Home Assistant ab 2026.11.0 ist erforderlich; die Entwicklung benötigt Python ab 3.14.2.
- EOS selbst bleibt als separater Dienst bestehen.
- Add-on-Optionen im Integrationsdialog erneut eintragen; native Entitäten besitzen eigene Registry-IDs.
- Lokale Verlaufs- und Alltagsdateien liegen nun unter .storage/eos_energiezentrale/<config-entry-id>.

### Security

- Panelzugriff und Paneländerungen über authentifizierte HA-WebSockets, ausschließlich für Administratoren.
- Kein eigener HTTP-Port und keine Supervisor-/HA-Zugriffstokens im Browser oder in der Integration.
- Herkunfts- und Fensterprüfung für die Panel-Kommunikation; keine beliebigen Serviceaufrufe.
- Bandit, pip-audit, Trivy-Geheimnisscan, hassfest und HACS-Validierung in der Pipeline.

## 0.1.3

### Features

- Automatische GitHub-Releases nach erfolgreichem Container-Publish auf main.
- Versionsgebundene Release-Notizen mit Features, Bugfixes, Breaking Changes und Security.
- CI-Prüfungen für Feature- und Bugfix-Branches, Pull Requests nach main und main.
- Containerbau für amd64 und arm64 sowie versionierte Image-Tags.
- Importierbarer main-Regelsatz und Skript für die Aktivierung des Branchschutzes.
- Tägliche Dependabot-Prüfungen für Docker, GitHub Actions und Entwicklungsabhängigkeiten.
- Zusätzliche fachliche Fehler- und Schnittstellentests für HTTP-Antworten, Gerätebestätigungen, Geräterückgabe und Releases.
- Beitragsleitfaden und Apache License 2.0 einschließlich Urheberhinweisen. Private und kommerzielle Nutzung sind unter den Lizenzbedingungen erlaubt.

### Bugfixes

- Fronius wartet bei vorübergehend nicht verfügbaren Leistungsentitäten bis zu 45 Sekunden über mehrere Polls; Freigabe bleibt erhalten, fehlende Bestätigungen geschriebener Sollwerte bleiben Fehler.

- Steuerfehler bleiben im Lesemodus diagnostizierbar; Regelschritt und betroffene Entität bei ausbleibender Bestätigung sowie vollständiger Stacktrace im HA-Log ergänzt.

- Steuerfreigabe wartet auch nach manuellem Aktivieren auf bereite Eingangsdaten und EOS-Plan; unvollständige EOS-Pläne werden als temporärer Abruffehler behandelt und löschen keine Freigabe.

- EOS-Modus- und Wallbox-Statussensoren bleiben Textsensoren; Sprachpakete werden ohne blockierenden Dateizugriff im HA-Eventloop geladen.

- Keine.

### Breaking Changes

- Keine.

### Security

- Bandit, pip-audit und Trivy prüfen Quellcode, Abhängigkeiten, Geheimnisse und Container in der CI.
- Nicht benötigtes pip einschließlich seiner gebündelten Abhängigkeiten aus dem Laufzeit-Image entfernt; die CI prüft weiterhin den vollständigen Container und dessen Laufzeitimporte.

## 0.1.2

### Features

- Fachliche Regressionstests für Ladeziele, Messwertalter, Phasenwechsel, Speicherfreigabe, Persistenz und Ingress-Grenzen.

### Bugfixes

- Fronius wartet bei vorübergehend nicht verfügbaren Leistungsentitäten bis zu 45 Sekunden über mehrere Polls; Freigabe bleibt erhalten, fehlende Bestätigungen geschriebener Sollwerte bleiben Fehler.

- Steuerfehler bleiben im Lesemodus diagnostizierbar; Regelschritt und betroffene Entität bei ausbleibender Bestätigung sowie vollständiger Stacktrace im HA-Log ergänzt.

- Steuerfreigabe wartet auch nach manuellem Aktivieren auf bereite Eingangsdaten und EOS-Plan; unvollständige EOS-Pläne werden als temporärer Abruffehler behandelt und löschen keine Freigabe.

- EOS-Modus- und Wallbox-Statussensoren bleiben Textsensoren; Sprachpakete werden ohne blockierenden Dateizugriff im HA-Eventloop geladen.

- Die Regelung bleibt nach einer fehlgeschlagenen Geräterückgabe deaktiviert. Eine ausstehende Rückgabe kann erneut versucht werden.
- Vor dem NRGkick-Phasenwechsel werden zwei frische Nullleistungsmessungen nach dem Abschaltbefehl verlangt.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.1.1

### Features

- Sprachpakete für Deutsch und Englisch.
- Automatische Übernahme der Home-Assistant-Sprache mit Englisch als Rückfall.
- Sprachauswahl in der Add-on-Konfiguration.

### Bugfixes

- Fronius wartet bei vorübergehend nicht verfügbaren Leistungsentitäten bis zu 45 Sekunden über mehrere Polls; Freigabe bleibt erhalten, fehlende Bestätigungen geschriebener Sollwerte bleiben Fehler.

- Steuerfehler bleiben im Lesemodus diagnostizierbar; Regelschritt und betroffene Entität bei ausbleibender Bestätigung sowie vollständiger Stacktrace im HA-Log ergänzt.

- Steuerfreigabe wartet auch nach manuellem Aktivieren auf bereite Eingangsdaten und EOS-Plan; unvollständige EOS-Pläne werden als temporärer Abruffehler behandelt und löschen keine Freigabe.

- EOS-Modus- und Wallbox-Statussensoren bleiben Textsensoren; Sprachpakete werden ohne blockierenden Dateizugriff im HA-Eventloop geladen.

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.1.0

### Features

- Erste Energiezentrale mit animiertem Stromfluss und Detailseiten für PV, Netz, Haus, Speicher, Fahrzeug und Wärmepumpe.
- EOS-Planabruf, Leistungs- und SoC-Prognosen sowie Moduszeitleisten.
- Generische Speicher- und Wallbox-Schnittstellen mit Fronius- und NRGkick-Treibern.
- PV-Überschussregelung, Ladeziele, Phasenwahl und SoC-Schätzung.
- InfluxDB-Verlauf und lokaler Verlauf ab App-Start.
- Lesemodus, explizite Steuerungsübernahme und über Ingress erreichbare Oberfläche.

### Bugfixes

- Fronius wartet bei vorübergehend nicht verfügbaren Leistungsentitäten bis zu 45 Sekunden über mehrere Polls; Freigabe bleibt erhalten, fehlende Bestätigungen geschriebener Sollwerte bleiben Fehler.

- Steuerfehler bleiben im Lesemodus diagnostizierbar; Regelschritt und betroffene Entität bei ausbleibender Bestätigung sowie vollständiger Stacktrace im HA-Log ergänzt.

- Steuerfreigabe wartet auch nach manuellem Aktivieren auf bereite Eingangsdaten und EOS-Plan; unvollständige EOS-Pläne werden als temporärer Abruffehler behandelt und löschen keine Freigabe.

- EOS-Modus- und Wallbox-Statussensoren bleiben Textsensoren; Sprachpakete werden ohne blockierenden Dateizugriff im HA-Eventloop geladen.

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

