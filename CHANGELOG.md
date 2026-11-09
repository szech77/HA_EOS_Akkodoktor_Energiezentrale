# Changelog

Die Release-Pipeline verwendet die Integrationsversion aus manifest.json und die
zugehörigen Änderungen. Releases entstehen nach erfolgreichen Prüfungen auf main.

## 0.2.0

### Features

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

