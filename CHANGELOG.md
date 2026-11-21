# Changelog

## 0.24.5b44923895698 - 2026-11-21

### Features

- Keine.

### Bugfixes

- Ein einzelner fehlgeschlagener Abruf des Victron GX (oder eines anderen Speichers, der den Netzstatus meldet) pausiert die Steuerung nicht mehr sofort als möglichen Notstrom. Bisher gab die Energiezentrale dann den Speicher frei und stoppte die Wallbox, sodass ein Auto mitten im Laden stehen blieb (Issue #33). Jetzt gilt der zuletzt bestätigte Netzbetrieb bis zu 60 Sekunden weiter; meldet das Gerät Notstrom oder einen anderen ausdrücklichen Status, oder ist es länger nicht lesbar, pausiert die Steuerung wie bisher. Eine laufende Pause endet weiterhin nur mit einer frischen Meldung des Netzbetriebs.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.24.4 - 2026-11-21

### Features

- Keine.

### Bugfixes

- Ein kurzer Verbindungsausfall zu Speicher oder Wallbox schaltet die Steuerung nicht mehr dauerhaft aus. Bisher deaktivierte eine Zeitüberschreitung beim Cerbo die Steuerung bis zum manuellen Einschalten, und der Speicher lief über Nacht ohne EOS-Vorgaben (Issue #33). Jetzt gibt die Energiezentrale die Geräte so weit wie möglich frei, zeigt den Hinweis „Gerät nicht erreichbar“ (`control_resume`) und übernimmt die zuvor gesteuerten Bereiche jede Minute wieder, erst mit gültigen Messwerten und EOS-Plan. Nach 30 Minuten ohne Verbindung bleibt die Steuerung wie bisher aus. Ablehnungen oder falsche Bestätigungen eines Geräts sowie ein manuelles Ausschalten beenden die Steuerung weiterhin sofort.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.24.3 - 2026-11-21

### Features

- Keine.

### Bugfixes

- Abhängigkeit `holidays` von 0.108 auf 0.109 aktualisiert (`requirements-test.txt`); automatisch erfasst.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.24.2 - 2026-11-20

### Features

- Keine.

### Bugfixes

- Mit einer Fahrzeugliste überträgt die Energiezentrale jetzt auch den Ladestand sowie die Lade- und Entladeleistung des gemeinsamen Speichers an den Messwertspeicher von EOS; bisher gingen nur die Fahrzeugwerte dorthin (Issue #33). Ohne Speicher-SoC rechnete EOS mit einem leeren Speicher und gab ihn nicht zur Entladung frei, sodass etwa ein Victron GX nachts dauerhaft mit Entladegrenze 0 (ESS #7) lief. Der Speicher wird einmal für die ganze Flotte gesendet.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.24.1 - 2026-11-20

### Features

- Keine.

### Bugfixes

- Victron GX direkt (Modbus TCP): Die Speichersteuerung brach ab, weil Venus OS einen geschriebenen Netzsollwert bzw. eine Entladegrenze quittiert, beim sofortigen Zurücklesen aber noch den alten Wert meldet (Issue #33). Das Plugin liest jetzt bis zu einer Sekunde lang alle 100 ms zurück und akzeptiert weiterhin nur den angeforderten Wert. Schlägt die Bestätigung fehl, nennen Hinweis, Log und Diagnosedaten die Ursache als feste Kennung (`reason`: z. B. `readback_mismatch` oder `not_acknowledged`); das gilt für alle Modbus-Plugins.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.24.0 - 2026-11-20

### Features

- Die Energiezentrale überträgt ihre gemessenen Werte automatisch an den Messwertspeicher von EOS: Ladestand (als Faktor 0–1) sowie Lade- und Entladeleistung des Speichers, Ladestand und Ladeleistung jedes Fahrzeugs. EOS nimmt den Start-Ladestand für die Optimierung aus diesen Messwerten und rechnete ohne eigenen Messeingang mit 0 % – etwa mit einer vollen Netzladung für ein fast volles Auto (Issue #33). Gesendet wird mindestens einmal pro Minute und bei einer SoC-Änderung ab einem Prozentpunkt sofort, nur für Schlüssel, die EOS anbietet, und nie ein Ersatzwert für einen fehlenden Messwert. Fehler erscheinen als Hinweis `eos_measurements`; die Diagnosedaten zeigen gesendete und in EOS fehlende Schlüssel. EOS-Versionen ohne Mess-API bleiben unverändert.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.23.0 - 2026-11-20

### Features

- Panel-Redesign, Teil 1: Ein Statusband auf jeder Seite zeigt den Steuerzustand mit Ursache, Folge und der passenden Aktion. „Steuerung übernehmen“ und „Steuerung zurückgeben“ werden direkt im Band bestätigt, statt über einen Browser-Dialog bzw. ohne Rückfrage; der Schalter liegt nicht mehr unten in den Einstellungen. Die bisher zu einem Absatz verketteten Meldungen erscheinen als eine Karte pro Hinweis, nach Schwere sortiert, mit Backend-Kennung, Zeitpunkt seit Auftreten und Link zur betroffenen Geräteseite; die neue Seite „Hinweise“ zeigt zusätzlich die in den letzten 24 Stunden behobenen Hinweise. Kurze Meldungen wie „Ladeziel“ oder „Gerätefreigabe“ sind ganze Sätze mit Folge und nächstem Schritt. Die Navigation enthält „Auto“ und „Hinweise“ mit Zähler und liegt auf dem Smartphone unten. Die Vorlage liegt unter `docs/redesign/`.
- Panel-Redesign, Teil 2: Im Energiefluss stehen Name und Wert zentriert unter dem Symbol; die Knoten sitzen näher an der Mitte. Geräte mit offenem Hinweis tragen ein Warnzeichen; die Zuordnung von Hinweis zu Gerät bzw. Fahrzeug liefert das Backend (`node_problems`). Haus und Wärmepumpe öffnen ihre Verbrauchsauswertung, das EOS-Symbol die Gesamtbilanz; der Leistungsverlauf bleibt über einen Link erreichbar. Unter dem Energiefluss zeigt die Übersicht in voller Breite den EOS-Speicherplan der letzten 3 und nächsten 12 Stunden als bedienbaren Zeitstrahl sowie die einklappbare Liste „Was als Nächstes passiert“ (`plan_events`, mit Anzahl der Einträge; auf- oder zugeklappt merkt sich der Browser): Moduswechsel von Speicher und Fahrzeugen in Alltagssprache (Wechsel unter 30 Minuten werden ausgelassen; bei Speicherwechseln steht die Wirkung laut EOS-Prognose, z. B. „hält seinen Ladestand“ statt „lädt mit PV-Überschuss“ in der Nacht, der EOS-Modus steht darunter), der erwartete Zeitpunkt für vollen Speicher und erreichtes Ladeziel aus der EOS-Prognose, jeweils mit dem Netzstrompreis zu diesem Zeitpunkt. Sie ersetzt die Kacheln „Nächster EOS-Modus“. Eine vierte Kennzahl zeigt den Speicher-Ladestand.
- Panel-Redesign, Teil 3: Die Einstellungen sind in die Bereiche Speicher, E-Auto, Kalender, Kosten und System gegliedert; Expertenwerte sowie Wirkungsgrade und Anfangspreis sind eingeklappt. Statt drei getrennter Speichern-Knöpfe erscheint nur bei ungespeicherten Änderungen eine Leiste mit Änderungszahl, „Verwerfen“ und „Speichern“, die alle Bereiche gemeinsam speichert. Abgelehnte Werte werden direkt am Feld markiert: Das Backend liefert dafür Grund und Feldnamen aus festen Listen (`translation_placeholders` der HA-Fehlermeldung, ohne eingegebene Werte); auch die Kosteneinstellungen melden ihre Fehler jetzt so. Ohne lokale Änderungen übernimmt das Formular Änderungen aus dem Backend, etwa über native Entitäten.
- Panel-Redesign, Teil 4: Die Verbrauchsbilanz schreibt Einspeisung (bewertet mit der EOS-Einspeisevergütung bzw. dem manuellen PV-Kostenansatz) und Speicherladung (nach PV und Netz) stündlich mit. Der Bericht enthält eine im Backend berechnete Bilanz (`balance`) mit Verbrauch, Autarkie, Eigenverbrauchsquote, physischem Netzbezug, Ø-Netzstrompreis, Einspeisung und Vergütung, anteiligem Grundpreis, Ersparnis und Netto; netzgeladene Speicherenergie wird nicht doppelt gezählt. Neu unter Einstellungen › Kosten ist ein Grundpreis gesamt in €/Monat (Standard 0), der tageweise verteilt wird. Einspeisung wird ab diesem Update erfasst.
- Panel-Redesign, Teil 5: Die Auswertungen sind neu aufgebaut. Chips wechseln zwischen Haus, Auto, Wärmepumpe, Netz & Einspeisung und Gesamt; Tag/Monat/Jahr mit ‹ › zum Blättern. Jede Auswertung zeigt eine Kernaussage, vier Kennzahlen, den Verlauf, Preise & Kosten, Herkunft bzw. „Wohin ging der PV-Strom?“ und „Was auffällt“; Kennzahlen, Ersparnis und auffällige Zeitabschnitte berechnet das Backend. Neu ist die Auswertung Netz & Einspeisung mit Bezug nach oben und Einspeisung nach unten, Grundpreis und Saldo; der Netz-Knoten im Energiefluss öffnet sie. Die Heute-Kacheln enthalten Einspeisung und Gesamtbilanz mit Netto. Das separate Kostendiagramm und die Datumswahl entfallen. Auf dem Smartphone sind die unteren Bereiche eingeklappt.
- Panel-Redesign, Teil 6: Die Auto-Ansicht zeigt zuerst das Ziel (Ladestand-Ring, Abfahrt, fehlende Energie und was EOS plant). PV-Überschussladen, Schnellladen, Phasenautomatik und die Ladegrenzen speichern sofort. Neu ist der EOS-Ladeplan bis zur Abfahrt mit Ladestandskurve, Zeitstrahl (PV-Überschuss, Pause, Netzladen, Ziel erreicht), Abschnittsliste mit Leistung, Phasen, kWh, Preis und Kosten sowie einem Kostenvergleich mit sofortigem Laden. Das Backend berechnet die Abschnitte aus der EOS-Prognose (Netzstrom zum Intervallpreis, PV-Strom zur Einspeisevergütung) und den Zustand „überstimmt“ (Schnellladen), „ausgesetzt“ (Wallbox-Fehler), „nur Anzeige“ (Lesemodus) oder „nicht verbunden“. Abschnitte unter 10 Minuten zwischen zwei gleichartigen Abschnitten werden mit diesen zusammengefasst, ohne die kWh-Summen nach PV und Netz zu ändern. Ladeziele erscheinen als kompakte Zeilen; Bearbeiten öffnet die Details.
- Panel-Redesign, Teil 7: Die neue Ansicht PV & Wetter ersetzt den Wetter-Dialog und öffnet sich über den PV-Knoten oder das Wettersymbol. Sie zeigt PV jetzt, heute erzeugt, Rest und morgen, das aktuelle Wetter mit Bewölkung und „PV jetzt ≈ x % der Prognose“, eine stündliche Leiste bis Ende morgen mit Wetter über dem erwarteten PV-Ertrag (Nachtstunden zusammengefasst) und Tageskarten für drei Tage ohne Spanne. „Was EOS daraus macht“ nennt weniger/mehr Sonne morgen, Speicher voll per PV, Netzladen des Speichers, Einspeisung und Fahrzeug-Netzladen; das Backend berechnet Stunden, Tage und diese Aussagen. Die Wetterabfrage liefert dafür die Bewölkung und reicht 72 statt 24 Stunden voraus. Die nicht mehr genutzte 24-Stunden-PV-Zusammenfassung des Dialogs entfällt.
- Speicher und E-Auto-Laden lassen sich unter Einstellungen › System › Gerätesteuerung getrennt übernehmen und zurückgeben, jeweils mit Bestätigung im Panel; dazu gibt es die Schalter „Speichersteuerung“ und „E-Auto-Ladesteuerung“. Ein Bereich wird nur angeboten, wenn ein passendes steuerbares Gerät konfiguriert ist: ein Speicher-Plugin mit Lade- und Entladegrenzen (z. B. nicht Victron ohne aktivierte ESS-Steuerung) bzw. eine Wallbox. Ein nicht gesteuerter Bereich erhält keine Befehle; ohne Speichersteuerung entfällt die Speicherunterstützung beim PV-Laden. „Steuerung übernehmen“ im Statusband und der Schalter „Energiesteuerung“ schalten weiterhin alle steuerbaren Bereiche gemeinsam; die Bestätigung im Band nennt nur die vorhandenen bzw. gesteuerten Geräte, und bei nur einem gesteuerten Bereich sagt das Band, welcher es ist. Bestehende Freigaben gelten für alle steuerbaren Bereiche; die Auswahl wird zusätzlich in `control_scope.json` gespeichert, `control.json` behält ihr bisheriges Format für ältere Versionen.
- Einstellungen › System enthält die Diagnose „Messquellen“: alle konfigurierten Quellen mit Quelle, aktuellem Zahlenwert, Alter und Status, die abgeleiteten Hausverbrauchswerte, die Energiebilanz mit Bilanzrest und erlaubter Abweichung sowie die Einzelwerte der Geräte (einschließlich Lade- und Entladeleistung je Speicher) und Fahrzeuge. Die Bilanzregel ist dieselbe wie in der Auswertung; ein großer Rest erklärt dort verbuchte „Unbekannt“-Anteile. Mit „Messwerte kopieren“ landen die Werte als Text in der Zwischenablage, mit „Messwerte exportieren“ als Textdatei für eine Analyse.
- Ohne passende EOS-Fahrzeugprognose zeigt die lokale Schätzung jetzt auch die erwartete Ladeleistung in der Zukunft: 0 kW, solange keine Ladung zu erwarten ist (Fahrzeug getrennt, Ladeziel erreicht oder zu wenig PV-Überschuss), sonst die geschätzte PV-Überschussleistung. Neu ist die Schätzung beim Schnellladen mit maximaler Ladeleistung bis zum Ladeziel, samt SoC-Verlauf. Die Gesamtladeleistung mehrerer Fahrzeuge summiert diese Werte, sofern für alle Fahrzeuge ein Wert vorliegt. Geschätzt wird nur bei freigegebener E-Auto-Ladesteuerung; im Lesemodus wird der aktuelle SoC weiterhin fortgeschrieben. Die Schätzung bleibt reine Anzeige und fließt nicht in die Regelung ein.
- Unter „Preise & Kosten“ wird der bisherige Posten „Eigenstrom“ aufgeschlüsselt in PV direkt, Speicher PV-geladen und Speicher netzgeladen, jeweils mit Energiemenge, Preis und Kosten. Netzgeladener Speicherstrom gilt damit nicht mehr als Eigenstrom. Der Speicher erfasst dafür ab diesem Update, welcher Anteil seines Inhalts aus PV bzw. dem Netz stammt; Speicherstrom aus der Zeit davor oder bei unvollständigen Messwerten steht als „Herkunft unbekannt“. Der Hinweis zur Ersparnis spricht von „PV- und Speicherstrom“.
- Optionaler Reichweitensensor je Fahrzeug (`car_range_entity` bzw. `range_entity` in der Fahrzeugliste, km oder mi; bei genau einem Fahrzeug in der Liste gilt ohne eigenen Fahrzeugsensor der Sensor aus den Quellsensoren): Das Backend bildet aus Reichweite und gemessenem SoC (ab 10 %) das Verhältnis Kilometer je Prozent. Die Auto-Ansicht zeigt die aktuelle Reichweite (ohne aktuelle Fahrzeugmeldung aus dem SoC geschätzt), und PV-Ladeziel, Schnellladeziel und die Ladeziele haben je einen SoC-Schieberegler, der schon während des Verschiebens oder Eintippens SoC und erwartete Reichweite zeigt (z. B. „70 % · ≈ 294 km“). PV- und Schnellladeziel werden beim Loslassen gespeichert. Ohne gelerntes Verhältnis zeigt der Regler nur den SoC. Die Diagnose „Messquellen“ zeigt den Sensor. Regelung und Planung nutzen die Reichweite nicht.
- Neue Auswertung **PV-Erzeugung**, erreichbar über den PV-Knoten im Energiefluss: Sie zeigt je Stunde, Tag oder Monat oberhalb der Nulllinie, wohin der PV-Strom fließt (Haus, E-Auto, Wärmepumpe, Akku laden, Netzeinspeisung), und darunter den Verbrauch, den PV nicht gedeckt hat, nach Herkunft (Akku PV-geladen, netzgeladen oder unbekannt, Netz, unbekannte Quelle). Dazu Eigenverbrauchsquote, Einspeisung und die EOS-Prognose für den Rest des Zeitraums als umrandete Balken. Die Tagesansicht in kW zeigt dieselbe Aufteilung als Flächen mit Prognoselinie und allen Werten am Mauszeiger. Das Backend liefert dafür `pv_flow` und `pv_gap` je Abschnitt, je Leistungspunkt und als Summe sowie `pv_forecast`. Das Wettersymbol öffnet weiterhin PV & Wetter.
- Die Tagesansicht der Auswertungen bietet zusätzlich die Darstellung **kW**: den Leistungsverlauf über die Uhrzeit als farbig gefüllte, gestapelte Flächen je Energiequelle (bei Netz & Einspeisung Bezug nach oben, Einspeisung nach unten). Beim Überfahren mit der Maus oder Antippen zeigt eine Anzeige am Zeiger Uhrzeit, Gesamtleistung und Anteile. Das Backend berechnet den Verlauf aus den minütlichen Messwerten des lokalen Verlaufs mit derselben Aufteilung wie die Abrechnung, als 2-Minuten-Mittel, und liefert ihn im Tagesbericht als `power_profile`. Für Tage außerhalb des lokalen Verlaufs (etwa zwei Tage) zeigt kW die Stundenbalken. kWh und € bleiben Balken je Stunde mit Details zum angeklickten Balken; Monat und Jahr bieten kWh und €.
- Die Auswertungen haben im Verlauf einen Umschalter **kWh / €** (in der Tagesansicht zusätzlich kW): Verbraucher und Gesamtbilanz zeigen dann die Kosten je Energiequelle, Netz & Einspeisung die Bezugskosten (einschließlich Speicherladung aus dem Netz) nach oben und die Einspeisevergütung nach unten. Die Bilanz liefert dafür je Zeitabschnitt `grid_import_eur`, `export_eur` und `cost_partial`. Die Auswahl merkt sich der Browser. Überlappende Achsenbeschriftungen bei sehr kleiner Einspeisung oder kleinem Bezug entfallen.
- Die Titelleiste mit Logo und Navigation bleibt beim Scrollen oben sichtbar. Die Bereichsliste der Einstellungen und Sprungziele wie „Zum Ladeplan“ halten dabei Abstand zur Titelleiste; auf schmalen Bildschirmen bleibt die Navigation wie bisher unten.
- Autarkie, Eigenversorgung, „aus eigener Erzeugung“ und „Bester Tag/Stunde/Monat“ zählen netzgeladenen Speicherstrom nicht mehr als eigene Versorgung, sondern nur PV-Direktstrom und Speicherstrom ohne Netzladung. Speicherstrom ohne erfasste Herkunft zählt wie bisher als eigene Versorgung. Die Ersparnis gegenüber Netzstrom bewertet weiterhin allen PV- und Speicherstrom.

### Bugfixes

- Victron GX direkt (Modbus TCP): Liest das Plugin Netzleistung und System-AC-Verbrauch, ergibt sich die angezeigte und abgerechnete Lade- bzw. Entladeleistung jetzt aus der AC-Bilanz des GX (PV + Netz − Verbrauch) statt aus der DC-Akkuleistung mit geschätztem Wirkungsgrad. Bisher landeten die tatsächlichen Wandlungsverluste beim Laden als Hausverbrauch, bei 5 kW Netzladung mehrere hundert Watt (Issue #33). Weicht die Bilanz um mehr als 500 W bzw. 25 % von der Näherung ab, etwa weil eine PV-Quelle nicht gelesen wird, gilt wie bisher die Näherung. Die Steuerung rechnet unverändert mit der Näherung; die Diagnose zeigt die verwendete Methode.
- Während EOS einen neuen Plan berechnet, springen Diagramme und Plananzeigen nicht mehr auf einen Zwischenstand: Die EOS-Prognose wird in dieser Zeit nicht neu abgerufen, die zuletzt fertige bleibt sichtbar, und die neue wird direkt nach Ende der Berechnung geholt. Meldet EOS länger als 15 Minuten eine laufende Berechnung, gilt wieder der normale Abruf jede Minute.
- Eine Neuinstallation startet ohne vorbelegte Quellsensoren. Bisher waren für PV, Hausverbrauch, Netz, Wärmepumpe, Strompreis und Fahrzeug-SoC Entitätsnamen einer Beispielanlage vorbelegt, die bei anderen Anlagen nicht existieren. Bestehende Installationen behalten ihre gespeicherte Zuordnung. README und DOCS zeigen neutrale Beispielnamen.
- Energiefluss einheitlich gestaltet: PV hat ein Liniensymbol wie die übrigen Knoten statt eines Emojis, alle Knoten zeigen denselben Kreis in ihrer Farbe (bei vorhandener Referenz mit Auslastungsbogen), Erzeuger und Verbraucher stehen auf gleichen Höhen und die Leitungen laufen spiegelbildlich ins Zentrum. Auf schmalen Bildschirmen rücken die Spalten nach außen, damit die Darstellung die Breite nutzt.
- Rechnet EOS gerade oder antwortet kurz nicht, zeigt das Statusband nicht mehr eine Warnung „EOS-Ersatzplan“, sondern wie im Normalbetrieb „Steuerung aktiv“. Dass bis zu fünf Minuten der letzte gültige Plan gilt und auf den neuen Plan gewartet wird, steht als Information im Text. Auch „EOS berechnet“ bzw. „Warte auf aktuellen EOS-Plan“ steht nicht mehr in der Überschrift, sondern im Text.
- PV & Wetter flackert nicht mehr: Die Stundenleiste lud bei jeder Aktualisierung (alle 5 s) neu und war dabei kurz leer, weil sich die Rest-PV für heute und die E-Auto-Schätzung ständig ändern. Sie lädt jetzt nur bei geänderter PV-Prognose bzw. spätestens alle 15 Minuten neu und behält währenddessen die bisherige Anzeige. „Jetzt“ zeigt das aktuelle Wetter statt des Symbols für unbekanntes Wetter, wenn die stündliche Prognose erst mit der nächsten vollen Stunde beginnt.
- Die Zeitstrahlen (EOS-Plan in der Übersicht, Lademodi in der Geräteansicht, Auto-Ladeplan) platzieren jeden Abschnitt nach seiner Zeit. Bisher reihte das Layout die Abschnitte aneinander und gab jedem einige Pixel Rand dazu; bei vielen kurzen EOS-Wechseln verschob sich der Plan dadurch vor die „Jetzt“-Linie. Verlauf und Plan werden zudem an der Messzeit des Snapshots getrennt, an der auch „Jetzt“ steht.
- Die Verbrauchs- und Kostenbilanz fällt nicht mehr aus („vorübergehend nicht verfügbar“, PV heute „—“), wenn zuvor eine neuere Version zusätzliche Abrechnungseinstellungen wie den Grundpreis gespeichert hat. Solche Einstellungen werden beim Laden übersprungen und beim Speichern unverändert erhalten; unbekannte Eingaben aus dem Panel werden weiterhin abgelehnt.
- Die Diagnose „Messquellen“ zeigt beim Fahrzeug-SoC den Wert des konfigurierten Sensors. Bisher stand dort bei mehreren Fahrzeugen bzw. Ladepunkten „—“, obwohl der Sensor einen gültigen Wert lieferte; eine SoC-Schätzung ersetzt den Sensorwert dort nicht.
- Der Hausverbrauch folgt jetzt aus der Energiebilanz der Quellen (PV + Netz + Speicherentladung − Speicherladung) statt aus dem gemessenen Gesamtverbrauch. Dadurch entstehen in der Auswertung keine „Unbekannt“-Anteile mehr durch zeitversetzte Sensoren oder einen falsch messenden Zähler (z. B. Victron-GX-Verbrauch beim Entladen, Issue #33). Fahrzeug und Wärmepumpe werden in den Gesamtverbrauch eingepasst; melden sie nach einem Schaltvorgang noch den alten Wert, schätzt das Backend höchstens 120 Sekunden lang (befohlene Ladeleistung dieser Integration, Einbruch um den letzten Gerätewert, sonst anteilig). Kurz fehlende Werte werden gehalten, eine einzelne fehlende Quelle folgt aus dem gemessenen Hausverbrauch. Die Auswertung verbucht diese Anteile als geschätzt; Übersicht und lokaler Verlauf zeigen keine geschätzten Hausverbräuche, die Regelung nutzt weiter nur Messwerte. Der gemessene Hausverbrauch bleibt Rückfall und Kontrolle: Eine Abweichung über 15 Minuten wird einmalig als `house_total_deviation` protokolliert und in der Diagnose angezeigt. Im Notstrombetrieb gilt weiter die Wechselrichterleistung. „Unbekannt“ bleibt nur, wenn mehrere Quellen länger als 120 Sekunden fehlen.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.22.4 - 2026-11-20

### Features

- Keine.

### Bugfixes

- Release-Prozess: Patch- und Minor-Updates gepinnter Abhängigkeiten (`requirements-dev.txt`, `requirements-test.txt`, GitHub Actions) erhalten in den Release-Notes automatisch einen Eintrag, wenn kein eigener Stichpunkt sie nennt. Reine Dependabot-PRs scheitern damit nicht mehr an der Versionsplanung. Major-Updates und unlesbare Versionen verlangen weiterhin einen eigenen Eintrag.
- Abhängigkeit `homeassistant` von 2026.11.1 auf 2026.11.2 aktualisiert (`requirements-test.txt`); automatisch erfasst.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.22.3 - 2026-11-18

### Features

- Keine.

### Bugfixes

- Einen nicht bestätigten Stopp einer nicht erreichbaren HA-Wallbox (Status unbekannt) als sichtbaren Fehler `wallbox_stop` melden und in jedem Zyklus wiederholen, statt die Steuerung dauerhaft auszuschalten. Bei unverfügbarer Ladefreigabe nur kurz auf die Bestätigung warten; eine bereits gemeldete Pause benötigt keine zusätzliche Abfrage. Erreichbare Wallboxen ohne Stoppbestätigung bleiben Steuerfehler.
- Den ausdrücklich gemeldeten Netzbetrieb einer konfigurierten HA-Statusentität nicht mehr wegen eines alten Meldezeitpunkts als unbekannt pausieren. Nicht verfügbare oder unerwartete Zustände pausieren weiterhin; die Netzwiederkehr nach einer Pause verlangt weiterhin einen frischen Netzbetriebsstatus. Bei unbekanntem Status schalten gleichzeitige Lesefehler von Speicher oder Wallbox die Steuerung nicht mehr dauerhaft aus, auch im Mehrfahrzeugbetrieb.
- Während der Wiederanlauf auf EOS oder Messwerte wartet, einen lesbaren Speicher auch bei noch nicht lesbarer Wallbox freigeben; die Wallbox wird freigegeben, sobald sie lesbar ist. Im Mehrfahrzeugbetrieb gibt ein noch wartendes Fahrzeug nur seine eigene Wallbox frei und pausiert keine bereits regelnde Wallbox mehr.
- Nach dem Ausschalten fehlgeschlagene Gerätefreigaben in jedem Zyklus wiederholen, bis sie bestätigt sind.
- Die Quelldiagnose bewertet den Fahrzeug-SoC mit derselben 36-Stunden-Grenze wie die Regelung, auch für Plugin-Werte.

### Breaking Changes

- Keine.

### Security

- Stoppbefehle der Plugins `nrgkick_local` und `goe_http_v2` auch dann senden, wenn eine abgebrochene Abfrage noch offen ist; dafür ist genau eine zusätzliche Anfrage reserviert. Ohne Bestätigung bleibt der Stopp ein Fehler.
- EOS-, InfluxDB- und Fronius-Solar-API-Anfragen zusätzlich zur Inaktivitätsfrist von 5 s mit einer Gesamtfrist von 30 s je Anfrage begrenzen. Solange eine abgebrochene Anfrage an denselben Dienst offen ist, scheitern weitere Anfragen dorthin sofort; so können auch verspätet abgeschlossene Konfigurationsschreibvorgänge keine neueren überholen.

## 0.22.2 - 2026-11-17

### Features

- Keine.

### Bugfixes

- Generische und HA-basierte NRGkick-Wallboxen melden einen Stopp nur noch als erfolgreich, wenn die Ladefreigabe `off` bestätigt. Bei nicht verfügbarer oder fehlender Freigabe-Entität den Stopp trotzdem anfordern; eine fehlende Bestätigung bleibt ein sichtbarer Steuerfehler, auch bei Sicherheitsstopps und beim Ausschalten.
- Einen konfigurierten oder vom Gerät gemeldeten, aber nicht verfügbaren, veralteten oder fehlenden Netzbetriebsstatus wie Notstrom behandeln: Speicher und Wallboxen freigeben, keine neuen Regelbefehle senden und erst nach frischem Netzbetriebsstatus fortsetzen, auch beim Start und im Mehrfahrzeugbetrieb. Der gespeicherte Steuerungswunsch bleibt erhalten.
- Nach einem Neustart mit gespeicherter Steuerfreigabe die Geräte als möglicherweise noch angesteuert behandeln. Ausschalten vor dem Wiederanlauf gibt Speicher und alle Wallboxen frei. Sind die Geräte lesbar, fehlen aber EOS-Plan oder Messwerte, werden sie während des Wartens freigegeben; fehlgeschlagene Freigaben bleiben sichtbar und werden wiederholt.
- Fahrzeug-SoC-Werte, deren letzte Meldung mehr als 36 Stunden zurückliegt, nicht mehr als Regelgrundlage oder Startwert der SoC-Schätzung verwenden und nach fünf Minuten ohne gültigen Wert als nicht verfügbar melden.

### Breaking Changes

- Keine.

### Security

- Lokale HTTP-Anfragen der Plugins `nrgkick_local` und `goe_http_v2` zusätzlich zur Socket-Inaktivitätsfrist mit einer Gesamtfrist begrenzen (NRGkick 5 s, go-e Inaktivitätsfrist plus 2 s). Tröpfelnd gesendete Header oder Antworten können Abfragen, Ausschalten und das Entladen der Integration nicht mehr über die Regelungssperre blockieren; solange eine abgebrochene Anfrage offen ist, scheitern weitere Anfragen an dasselbe Gerät sofort als Gerätefehler.

## 0.22.1 - 2026-11-17

### Features

- Keine.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Semgrep CE 1.185.0 als zusätzlichen verpflichtenden Python-/JavaScript-Scanner im CI-Job `security` mit sieben versionierten, vor jedem Scan getesteten Projektregeln integrieren. Nur die native Engine aus dem exakt gepinnten offiziellen PyPI-Wheel nach Größen- und SHA-256-Prüfung verwenden; bestehende Scanner erhalten. Befunde mit stabilen Regel-IDs, CWE-Zuordnung, Priorität, Behebungshinweisen und Fundstellen über geschwärzte SARIF-Berichte in GitHub Code Scanning bewertbar machen. Rohcode, expandierte Variablen und private Inhalte nicht hochladen; `nosemgrep`-Unterdrückungen nicht akzeptieren. Unvollständige Scans, fehlgeschlagene Regeltests, kaputte Berichte, Scanner-, Installations- oder Uploadfehler blockieren. PyYAML 6.0.3 explizit als Entwicklungsabhängigkeit für den Regelkatalog aufnehmen.

## 0.22.0 - 2026-11-17

### Features

- Security Policy für das melden von Verwundbarkeiten wurde hinzugefügt

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.21.0 - 2026-11-17

### Features

- Im bestätigten Notstrombetrieb die frische, summierte AC-Ausgangsleistung der konfigurierten Wechselrichter als Gesamtverbrauch verwenden. Gemessene Wallbox- und Wärmepumpenleistungen weiter separat abziehen; ungültige oder veraltete AC-Werte nicht ersetzen und nach Netzwiederkehr die normale Verbrauchsquelle verwenden. Notstrom als nativen Home-Assistant-Binärsensor mit nicht verfügbarem Zustand bei unbestätigtem Status bereitstellen. E-Auto-Laden während der aktiven Notstrompause standardmäßig auch nach erneutem Start stoppen; manuelles Laden optional über die technischen Grenzen erlauben, während EOS pausiert bleibt.
- Bestätigten Notstrom im Energieflussdiagramm zusätzlich mit einem roten Haus-/Blitz-Piktogramm am ausgegrauten Netzsymbol kennzeichnen. Bei Netzwiederkehr oder unbestätigtem Status das Piktogramm ausblenden.
- Notstrombetrieb anhand bestätigter, aktueller Gerätestatus im Backend erkennen und im Panel anzeigen. Im Energiestrom-Diagramm das öffentliche Netz ausgrauen und dessen Flussanimation unterdrücken, ohne Messwerte umzuschreiben. Fronius automatisch über den zugehörigen HA-Notstromsensor oder beim direkten Modbus-Plugin ergänzend über die lokale Solar API erkennen; Victron GX über den Inselstatus und weitere Systeme über eine optionale HA-Statusquelle unterstützen. Unbekannte/veraltete Zustände, Speichergruppen, Rückkehr zum Netz und deduplizierte Backend-Meldungen berücksichtigen; Deutsch und Englisch ergänzen.
- Beim Push auf Arbeitsbranches nach erfolgreichen Tests, Sicherheits- und Integrationsprüfungen bereits stabil veröffentlichte Stichpunkte aus `New Version` durch einen Bot-Commit entfernen und dessen Stand vollständig erneut prüfen. Neue Einträge und die vorhandene Historie erhalten; parallele Pushes nicht überschreiben. Die stabile Release-Historie auch nach bereinigten Quellständen zur Vermeidung doppelter Release-Einträge berücksichtigen.

### Bugfixes

- Stabile Releases nach einem Merge nach `main` trotz absichtlich übersprungener Branch-Changelog-Bereinigung veröffentlichen. Den Publish-Job mit einer expliziten Statusfunktion und erfolgreichem `required`-Ergebnis freigeben; bei fehlgeschlagenen/übersprungenen Pflichtprüfungen, Abbruch oder nicht vorgesehenem Auslöser weiterhin keine Veröffentlichung starten. Regression für stabile Releases und Beta-Branches ergänzen.
- Bestätigten Notstrom als normalen Pausenzustand statt als Messwertfehler darstellen. Netz-/Hausmesswertwarnungen nur für erwartbare Ausfälle im bestätigten Notstrom unterdrücken; andere Fehler sichtbar lassen. Speicher und Wallboxen freigeben/pausieren, den Steuerungswunsch auch bei mehrtägigen Ausfällen erhalten und erst nach bestätigter Netzwiederkehr, gültigen Messwerten und gültigem Plan automatisch weiterregeln. Unbestätigte Freigaben und unbekannter Netzstatus verhindern den Wiederanlauf; manuelles Ausschalten bleibt bestehen. Auch mehrere Wallboxen berücksichtigen.
- Bei aktivierter Fronius-Modbus-Notstromerkennung ein fehlendes Solar-API-Feld `BackupMode` als unbestätigten Status anzeigen und im Backend protokollieren. Die Statusquelle nicht mehr still als nicht unterstützt behandeln; Erkennung bei ausgefallenem Smart Meter durch Regressionstests absichern.
- Die CI-Versionsplanung nach Squash-Merges oder Rebases auch für weitergeführte Branches mit identischem vollständigem stabilem Quellstand ermöglichen. Wirklich veraltete Branches weiterhin zurückweisen. Den Unterschied zwischen `New Version` im Quellbranch und nummeriertem Changelog im veröffentlichten Release-Tag dokumentieren.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.20.0 - 2026-11-17

### Features

- Versionen aus den neuen Changelog-Einträgen automatisch berechnen. Arbeitsbranches nach erfolgreichen Pflichtprüfungen als Beta veröffentlichen; stabile Versionen ausschließlich auf main erzeugen. Versionsnummer, Datum und archiviertes Changelog in unveränderlichen Release-Snapshots generieren, ohne Bot-Push auf geschützte Branches.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.19.0 - 2026-11-16

### Features

- Allgemeine Einstellungen für Kosten, Hausspeicher und E-Auto-Regelparameter von der Ladeplanung in der Autoansicht trennen. Je Fahrzeug bis zu 32 aktivierbare Ladeziele mit einmaliger oder wiederkehrender Abfahrt, Wochentagen, zusätzlichen Feiertagen und eigenem Ziel-SoC speichern. Hinzufügen und Löschen mit Bestätigung unterstützen; bestehende Einzelpläne übernehmen. Auswahl des nächsten Ziels, Zeitzonenbehandlung und Übergabe an EOS vollständig im Backend ausführen.
- Deutsche Feiertage lokal anhand von Bundesland, Augsburger Sonderregelung und örtlich geltenden katholischen Feiertagen bestimmen. Dafür die neue Laufzeit- und Testabhängigkeit `holidays==0.108` verwenden. Deutsch und Englisch pflegen.
- Ohne passende EOS-Fahrzeugkurve den gültigen aktuellen SoC für 24 Stunden fortschreiben. Bei aktiviertem PV-Laden mit bekannten Ladegrenzen und Prognosen für PV und Hauslast den möglichen SoC-Anstieg im Backend abschätzen, Ladeeffizienz, PV-Ziel, prognostizierte Speicherladung und weitere Fahrzeuge berücksichtigen. EOS-Kurve und lokale Schätzung in der Anzeige unterscheiden; lokale Schätzungen ausschließlich zur Visualisierung verwenden.

### Bugfixes

- Eine dauerhafte EOS-Fahrzeug-Nullkurve bei bekanntem positivem SoC als Platzhalter zurückweisen. In diesem Fall den aktuellen SoC fortschreiben oder bei aktiviertem PV-Laden den lokalen PV-Ersatzverlauf verwenden; reguläre EOS-Kurven und reale 0-%-Ausgangswerte erhalten. Rohdaten, Messwerte und Steuerpläne nicht verändern.
- Gemeinsame E-Auto-Regelparameter und Feiertagsregion unmittelbar an alle Fahrzeugregler weitergeben. Ungültige Ladeziele und Feiertagseinstellungen mit strukturiertem Fehlergrund im Backend protokollieren.
- In der gemeinsamen Autoansicht für jedes Fahrzeug ein eigenes SoC-Diagramm einschließlich Zukunftskurve anzeigen, auch bei nur einem Fahrzeug. Historie, Prognose und interaktive Diagrammmodelle je Fahrzeug trennen.
- Unveränderte PV-Messwerte von 0 bis einschließlich 2 W bis zu 12 Stunden als gültig behandeln, einschließlich generischer HA-Plugins und der Quelldiagnose. Sensorwerte in kW vorher umrechnen. PV-Werte über 2 W und andere Leistungswerte weiterhin zeitnah auf Veraltung prüfen.
- Zeitweise fehlende PV-Messwerte getrennt von ihrer Regelgültigkeit behandeln: Quellenwarnung nach fünf Minuten ohne gültigen Wert, nach zuletzt 0–2 W spätestens 12 Stunden nach diesem Messwert. Wiederholte Fehlversuche verlängern die Frist nicht. Den kleinen letzten Wert im Backend nur für die Anzeige mit Altersangabe erhalten; Modbus-N/A, fehlende Werte und ungültige Messungen nicht als frische Regelwerte verwenden. Auch die gemeinsame Fahrzeugansicht berücksichtigt diese PV-Warnfrist.
- EOS-Health vor dem Planabruf abfragen und Berechnungen beziehungsweise das Warten auf einen aktuellen Plan mit Laufzeit im Kopfbereich anzeigen. Bei erreichbarem EOS temporäre Plan-, Prognose- und transportbedingte Synchronisationsfehler höchstens fünf Minuten zurückstellen; wiederholte Abfragen verlängern das Fenster nicht. Gerätestörungen, Konfigurationsfehler und explizite Plangültigkeitsgrenzen erhalten. Zustandswechsel im Backend protokollieren.

### Breaking Changes

- Nach dem ersten Speichern der Ladezielliste werden die bisherigen nativen Entitäten für Einzelzeitplan und Abfahrtsdatum/-zeit als nicht verfügbar markiert; Ladeziele werden im Fahrzeugpanel bearbeitet. Der bisherige Standard-Ziel-SoC bleibt als Schnellladeziel erhalten. Bis dahin funktionieren bestehende Einzelpläne und native Zeitplaneinstellungen weiter.

### Security

- Keine.

## 0.18.2 - 2026-11-16

### Features

- Keine.

### Bugfixes

- Fahrzeug-SoC- und Ladeleistungsprognosen aus EOS auch in der Fahrzeugverwaltung anzeigen, einschließlich Anlagen mit nur einem E-Auto. Die EV-Kurve anhand der in der Optimierung gespeicherten `device_id` exakt der konfigurierten EOS-Fahrzeugressource zuordnen; auch nach Umordnung oder Wechsel der prognostizierten Ressource keine Kurve einem anderen Fahrzeug zuweisen. Fehlende, widersprüchliche oder fremde IDs bleiben ohne Fahrzeugprognose. Messwerte und gemeinsame PV-Prognosen erhalten; ungültige SoC-Werte bleiben Lücken, Leistungswerte benötigen gültige Kapazität und Ladeeffizienz. Deutsche und englische Hinweise aktualisieren.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.18.1 - 2026-11-16

### Features

- Victron-Firmwarediagnose in den Einstellungen und im HA-Diagnoseexport anzeigen: verwendete, automatisch erkannte und manuell konfigurierte Venus-OS-Version, Herkunft der Version, Registerstatus und rohe Firmwarewörter. Für Geräte ohne Versionsregister eine optionale manuelle Versionsangabe ergänzen; Deutsch und Englisch pflegen.

### Bugfixes

- Victron-GX-Messwerte auch mit Venus OS vor 3.50 lesen, sofern die ausgewählten Systemregister verfügbar und gültig sind. Das Firmwarefeld vollständig über Register 834/835 lesen und ungültige Versionscodierungen mit `firmware_invalid` von Kommunikationsfehlern unterscheiden.
- Das erst mit Venus OS 3.70 eingeführte Firmware-Register 834/835 nicht mehr als Voraussetzung für Messwerte behandeln. Reservierte Wörter `0xFFFF/0xFFFF` oder ein ausdrücklich nicht unterstütztes Register erlauben weiterhin gültige Messungen. Bei fehlender Version gilt die Reihenfolge automatische Erkennung, manuelle Angabe, Standardannahme 3.50–3.69; damit werden ohne weitere Konfiguration 2716/2717 statt des Legacy-Sollwerts verwendet. Die Standardannahme ausdrücklich in Einstellungen, Diagnosedaten und INFO-Log kennzeichnen. Kommunikationsfehler und beschädigte Versionsdaten bleiben Abbruchgründe; automatisch gelesene Versionen haben Vorrang vor der manuellen Ersatzangabe.
- ESS-Mode-2-Steuerung auf älterem Venus OS nach zusätzlicher Legacy-Freigabe über Register 2700 ermöglichen; ab 3.50 weiterhin den flüchtigen 32-Bit-Sollwert 2716/2717 verwenden. Alte Sollwerte auf den vorzeichenbehafteten 16-Bit-Bereich prüfen, bevor Leistungsgrenzen verändert werden; unveränderte Sollwerte nicht erneut schreiben und jeden Schreibzugriff bestätigen. Bei alten Servern darf ausschließlich ein ausdrücklich als nicht vorhanden gemeldetes Dynamic-ESS-Register durch die manuelle Bestätigung „Dynamic ESS ausgeschaltet“ ersetzt werden. Aktives Dynamic ESS, sonstige Modbus-Fehler und moderne Server mit fehlendem Prüfregister verhindern weiterhin Befehle. Dauerhafte Legacy-Schreibzugriffe und die manuelle Schutzprüfung im Backend protokollieren; Hinweise und Freigabe auf Deutsch und Englisch dokumentieren.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.18.0 - 2026-11-16

### Features

- Gesamtverbrauch in der Tagesübersicht als eigene Karte mit Verbrauch, Kosten und gewichtetem Durchschnittspreis anzeigen. Die Karte öffnet eine Tages-, Monats- oder Jahresauswertung mit Energie- und Kostendiagrammen sowie Quellenaufteilung. Haus, Wärmepumpe und die gemeinsame Fahrzeugbilanz im Backend zusammenführen; einzelne Fahrzeuge nicht doppelt zählen. Bestehende Messwerte, historische Rekonstruktion, Schätzungen und unbekannte Kostenanteile einbeziehen. Deutsche und englische Beschriftung ergänzen.

### Bugfixes

- GitHub-Sponsoring aus `szech77-patch-1` integrieren und `.github/FUNDING.yml` korrigieren: Für GitHub Sponsors den Benutzernamen `szech77` statt der vollständigen Profil-URL hinterlegen.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.7 - 2026-11-15

### Features

- Keine.

### Bugfixes

- Geräteübersicht mit beschrifteten Messwerten für PV-Leistung, Wechselrichter-AC-Leistung, Hausverbrauch und Netzanschluss verständlicher darstellen. Nur vom jeweiligen Plugin angebotene Werte anzeigen; fehlende unterstützte Messwerte weiterhin als unbekannt kennzeichnen. Victron zeigt dadurch keinen irreführenden AC-Platzhalter mehr.
- Bei ungültiger Victron-Modbus-Konfiguration das betroffene Feld mit konkreten Vorgaben auf Deutsch und Englisch anzeigen, etwa fehlende Rückgabewerte bei aktivierter ESS-Steuerung, ungültige Wirkungsgrade, Portnummern oder Leistungsgrenzen. Geräteverwaltung und Plugin-Einstellungen nutzen dieselben sicheren Meldungen; Fehler weiterhin im Backend protokollieren.
- Dezimalwerte in nativen Plugin-Einstellungen zulassen. Die von Home Assistant vorbelegte Ganzzahl-Schrittweite durch freie Dezimaleingabe ersetzen, damit etwa Victron-Wirkungsgrade von 0,95 gespeichert werden können. Fachliche Wertebereiche und Ganzzahlvorgaben werden weiterhin unverändert im Backend geprüft.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.6 - 2026-11-15

### Features

- Keine.

### Bugfixes

- Betrieb ohne E-Auto mit leerer oder fehlender EOS-Fahrzeugressource ermöglichen. Neue Einrichtungen starten ohne vorgegebene Fahrzeugressource; Konfiguration und Laufzeit verlangen sie nur für konfigurierte Fahrzeuge. Ohne E-Auto keine Fahrzeugplanung, Ladezielabgleiche oder SoC-Veröffentlichung ausführen; die Speicherregelung bleibt unabhängig.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.5 - 2026-11-14

### Features

- Den zuletzt gewählten Zeitraum der Kostenauswertung (Tag, Monat oder Jahr) lokal im Browser merken und beim erneuten Öffnen wiederherstellen. Auch der Wechsel über Diagrammbalken wird gespeichert; ohne verfügbaren Browserspeicher bleibt die Bedienung möglich.

### Bugfixes

- Beim Speichern von Fahrzeugvorgaben die Bestätigung unveränderter Speichergrenzen und laufende Abgleiche erhalten. Ein neues Ladeziel löst keinen zusätzlichen Speicherabgleich aus; die erstmalige Übernahme und tatsächlich geänderte Grenzen werden weiterhin synchronisiert.
- Die Übertragung neuer Fahrzeugvorgaben und das Warten auf eine aktualisierte EOS-Fahrzeugplanung als eigenen Status anzeigen. Die bestehende Freigabe anhand des Plan-Erzeugungszeitpunkts bleibt erhalten; echte API-Fehler, Ersatzplan-Warnungen und fehlende Messwerte bleiben sichtbar. Wartezeiten und Wiederholungsintervalle dokumentieren.
- Fehlgeschlagene EOS-Abgleiche von Ladeziel, Fahrzeug- und Speichergrenzen mit Vorgang und Fehlerklasse im HA-Protokoll festhalten. Gleiche laufende Fehler nicht bei jedem Wiederholungsversuch erneut protokollieren; private Fehlermeldungen, Adressen und Konfigurationswerte ausschließen.
- Warnungen, Steuerungsstatus, Quellenbewertung, PV-Energiesummen, Bilanzzusammenführung, gewichtete Preise und Modusintervalle im Backend ermitteln. Das Panel stellt die gelieferten Werte und Meldungen dar; lokale Abfahrtsvorgaben in der Anlagenzeitzone auswerten und nicht existierende Sommerzeit-Uhrzeiten ablehnen.
- Alle Backend-Warnungen unabhängig vom geöffneten Panel mit gemeinsamen Kennungen, sicheren Fehlerursachen, HTTP-Status und begrenztem Aufrufpfad protokollieren. Ursachenwechsel und Behebungen festhalten, unveränderte Fehler deduplizieren und die letzten 50 Übergänge in Diagnosedaten bereitstellen. HTTP-Abrufzeiten bei DEBUG erfassen. Browserfehler ausschließlich lokal behandeln; keine Nachlieferung nach HA-Neustarts. Bereits gepufferte Meldungen alter Panels ohne Logeintrag verwerfen.
- Plugin-Lesefehler, intern abgefangene Teilfehler, unvollständige oder ungültige Rückgaben und fehlende Wallbox-Steuerdaten an der gemeinsamen Leseschnittstelle protokollieren, auch bei anderweitig ausgewählten HA-Messquellen. Plugin und Geräteposition, betroffene Messwerttypen, Fehlerklasse und gegebenenfalls Modbus-Registerkontext ausgeben; Nullwerte und abgewählte optionale Quellen erhalten. Native Konfigurationsdialoge und fehlgeschlagene Integrationseinrichtung mit sicheren Ursachen und Parameterbezeichnungen protokollieren; keine Werte, Adressen oder Zugangsdaten übernehmen.

- Alle drei Victron-Plugins gezielt auf Fehlerprotokollierung prüfen und ergänzen: fehlende HA-Entitäten, falsche Einheiten und veraltete Messungen unterscheiden; Fehler beim Ermitteln von Leistungsgrenzen, bei ESS-Prüfungen, Schreibbestätigungen und Gerätefreigaben mit Plugin, Vorgang und sicherem Register- bzw. Parameterkontext protokollieren. Steuerfehler erst nach erfolgreichem entsprechenden Vorgang auflösen; Konfigurationsfehler mit betroffenen Feldnamen kennzeichnen.

- Deye-Modbus, Generic-Speicher/-Wechselrichter/-Wallbox und Fronius über HA um konkrete Lese-, Konfigurations- und Steuerfehlerkontexte ergänzen. Deye-Registerfehler und abgelehnte Teilwerte sowie fehlgeschlagene Aktivierung und Rücksetzung getrennt erfassen. HA-Quellenursachen und feste Steuerparameter erhalten; Fronius-Wartefristen und noch unbestätigte Phasenumschaltungen korrekt im Fehlerverlauf berücksichtigen. Gültige Nullwerte und abgewählte optionale Quellen weiterhin akzeptieren.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.3 - 2026-11-13

### Features

- Keine.

### Bugfixes

- Lesefehler einzelner Anlagengeräte in den HA-Diagnosedaten ausgeben. Für Victron GX zusätzlich Phasenzahl, ausgewählte Messquellen, Steuerungsfreigabe und den fehlgeschlagenen Leseabschnitt mit Registerbereich und gegebenenfalls Modbus-Ausnahmecode erfassen. Gerätenamen, Adressen, Seriennummern, Messwerte und rohe Fehlermeldungen bleiben ausgeschlossen; erfolgreiche Abfragen löschen den Lesefehler. Die Ablehnung unvollständiger Messungen und die Steuerungsprüfungen bleiben erhalten.
- Fehlersuche für dreiphasige Victron-Anlagen mit Fronius am AC-Ausgang dokumentieren; die vorbelegte DC-PV-Quelle ist nur bei tatsächlich vorhandenen DC-Ladereglern geeignet.
- Dynamische Plugin-Felder und Auswahllisten für alle mitgelieferten Speicher-, Wechselrichter- und Wallbox-Plugins lokalisieren. Übersetzte Beschriftungen auch direkt im Formular mitsenden, damit der innere Dialog „Plugin-Einstellungen“ ohne eigene Übersetzungsauflösung lesbar bleibt; native HA-Übersetzungsschlüssel erhalten. Sprache aus dem HA-Dialogkontext übernehmen, ersatzweise die HA-Sprache und Englisch nutzen. Übersetzungsdateien ausschließlich im Executor laden. Gilt für Einrichtung, Gerätebearbeitung, Fahrzeug-/Wallbox-Dialoge und die bisherige Hardwarekonfiguration.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.2 - 2026-11-13

### Features

- Keine.

### Bugfixes

- EOS-Konfiguration mit Batterieprofilen (u. a. `0.3.0.dev2611122196862169`) neben der bisherigen flachen Struktur unterstützen. Kapazität und Lade-/Entladegrenzen in `profile_adjustment` zusammenführen; ausgewählte Profile, zusätzliche Anpassungen und andere Geräte erhalten. Berechnete `effective_*`- und Messschlüssel-Felder nicht in Schreibanfragen zurücksenden, auch beim Aktualisieren von Fahrzeug-Ladezielen.
- Ladegrenzen erst nach bestätigter Konfiguration und passenden aufgelösten Profilwerten freigeben. Nicht auflösbare Profile oder abweichende wirksame Leistungen bleiben Fehler. Für abwesende Fahrzeuge Ladefaktoren auf null setzen und Ziele entfernen, ohne die technische Profilspanne mit einer maximalen SoC-Grenze von null zu blockieren. Nicht darstellbare Null-Leistungsgrenzen im neuen Profilmodell vor dem Schreiben ablehnen.
- Kapazität und Wirkungsgrade für die Akkukostenschätzung aus aufgelösten EOS-Profilwerten lesen. Fehlende Werte bleiben unbekannt und werden nicht durch erfundene Nullwerte ersetzt. Einrichtung und Einschränkungen der neuen Struktur dokumentieren.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.1 - 2026-11-12

### Features

- Keine.

### Bugfixes

- HTTP-Clients für go-e HTTP API v2 und NRGkick Local erst beim ersten API-Zugriff im Executor erzeugen und anschließend wiederverwenden. Plugin-Konstruktion und Konfigurationsprüfung laden damit keine TLS-Zertifikate mehr im Home-Assistant-Eventloop, auch bei HTTP-Adressen. TLS-Prüfung, Redirect-Sperre und Proxy-Verzicht bleiben erhalten; fehlgeschlagene Initialisierungen werden als Gerätefehler behandelt und beim nächsten Zugriff erneut versucht.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.17.0 - 2026-11-12

### Features

- Direktes Speicher-Plugin „Victron GX direct Modbus TCP“ für Venus OS ab 3.50 hinzufügen. Akku-SoC, Spannung, Lade-/Entladeleistung, Netzanschluss, Hausverbrauch und ausgewählte AC-/DC-PV-Quellen ohne zusätzliche HA-Integration oder Sensoren lesen. Anlagen mit einer oder drei Phasen unterstützen; eine GX-Anlage als ein Gerät konfigurieren.
- Optionale ESS-Mode-2-Steuerung mit bestätigten DVCC-Ladestrom- und Entladeleistungsgrenzen sowie flüchtigem 32-Bit-Netzsollwert. SoC-/Leistungsgrenzen berücksichtigen, Dynamic ESS bzw. Inselbetrieb vor neuen Befehlen abweisen und explizite native Rückgabewerte nach Neustarts bestätigen. Standardmäßig lesend, erzwungene Einspeisung zusätzlich freigeben. Registerskalierungen, Einrichtung und Grenzen auf Deutsch und Englisch dokumentieren.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.16.0 - 2026-11-12

### Features

- Eigenes Speicher-Plugin „Victron GX (Home Assistant official)“ für die offizielle Home-Assistant-Integration hinzufügen. Messwerte und optionale ESS-Mode-2-Steuerung über auswählbare Entitäten; standardmäßig lesend. Gemeinsame Victron-Logik erhält bestätigte Befehle, SoC-/Leistungsgrenzen, Frischeprüfungen und explizite Rückgabewerte auch nach Neustarts. Die HACS-Auswahl bleibt unverändert verfügbar. Einrichtung und Wechsel zwischen den Integrationen dokumentiert.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.15.0 - 2026-11-12

### Features

- Speicher-Plugin „Victron Venus MQTT / HACS (Home Assistant)“ mit auswählbaren SoC-, DC-Leistungs-, Spannungs-, PV-, Netz- und Hausverbrauchsentitäten. Lesender Betrieb als Vorgabe; optionale ESS-Mode-2-Steuerung mit bestätigten Lade-/Entladegrenzen, Netzsollwert, SoC-Grenzen und expliziten nativen Rückgabewerten für Neustarts. Erzwungene Einspeisung separat freigeben. DC/AC-Wirkungsgrade konfigurierbar; Einrichtung und Grenzen auf Deutsch und Englisch dokumentiert.
- Direkt gemeldeten Hausverbrauch der gewählten Geräte-Netzquelle auch ohne vollständige AC-Einzelmessungen nutzen. Victron-SoC-Berichte bis 360 Sekunden akzeptieren, ohne Zeitstempel zu erneuern oder die Leistungsfristen anderer Plugins zu verändern.

### Bugfixes

- SoC- und Verteilungskontext beim Neutralisieren mehrerer Speicher erhalten, damit Plugins mit notwendigen SoC-Grenzen auch im gemeinsamen Speicherpool funktionieren.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.14.0 - 2026-11-12

### Features

- Verbrauchs- und Akkukostenschätzung über Messlücken und Neustarts fortsetzen. Letzten Messpunkt, gewichteten Akkupreis und gültige Speicherparameter gemeinsam mit dem Kostenbestand speichern. Lücken bis sechs Stunden zwischen Messpunkten interpolieren, geschätzte Bestände mit dem beobachteten SoC abgleichen und Haus, Wärmepumpe sowie Fahrzeuge mit derselben Akkubewertung versorgen.
- Interpolierte Energiemengen und angenäherte Kosten einschließlich Influx-Rekonstruktion mit „≈“ kennzeichnen. Bei längeren Ausfällen den Akkupreis erhalten und den Bestand am neuen SoC ausrichten, ohne tagelange Verbräuche aus Momentanwerten zu erfinden. Bestehende unbewertete Akkuanteile in Berichtskopien schätzen, ohne gespeicherte historische Kosten zu überschreiben.

### Bugfixes

- Messlücken und fehlende Akku-Leistungswerte löschen nicht mehr den bekannten Kostenbestand. Fehlenden Akku-Leistungsfluss bei vollständiger AC-Bilanz daraus ableiten; bei unzureichendem rechnerischem Bestand den zuletzt bewerteten Preis als Schätzung fortführen. Ohne jede Preisgrundlage bleiben Kosten unbekannt; echte Null- und Negativtarife bleiben gültig.
- Kleine bewertete Verbrauchsanteile erhalten ebenfalls einen Preis je kWh. Datenbankfehler rollen Kostenbestand und Messpunkt gemeinsam zurück, damit ein erneuter Versuch keine Energie doppelt zählt. Vorhandene Datenbankeinträge ohne Schätzfelder bleiben lesbar.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.13.0 - 2026-11-12

### Features

- Das Wettersymbol im Stromflussdiagramm öffnet eine Wetter-/PV-Vorhersage für die nächsten 24 Stunden. Oben stehen stündliche Wetterlage, Temperatur und Niederschlagsmenge aus Home Assistant, darunter die EOS-PV-Prognose mit Ertrag und Spitzenleistung. Beide Diagramme verwenden denselben Zeitraum und eine gemeinsame Auswahl per Maus, Touch oder Tastatur. Responsiver Dialog mit hellem/dunklem Design, Escape und Rückkehr des Tastaturfokus.
- Stündliche Prognosen derselben Wetterentität wie im Energiefluss über `weather.get_forecasts` abrufen und fünf Minuten zwischenspeichern. Wetterabfragen laufen unabhängig von der Gerätesteuerung. Fehlende Stunden, nicht unterstützte Quellen und Ausfälle bleiben sichtbar; der PV-Bereich bleibt unabhängig verfügbar. Teilweise PV-Prognosen kennzeichnen und Erträge nur aus vorhandenen, überlappungsfrei auf 24 Stunden begrenzten Intervallen berechnen.

### Bugfixes

- Das Wettermodul bei Bedarf mit der Version des laufenden Panels nachladen, wenn ein älteres zwischengespeichertes Startskript es noch nicht kennt. Lade- und Dialogfehler abfangen, damit ein Klick auf das Wettersymbol die Energieübersicht nicht ausblendet. JavaScript-Ausführungsfehler von fehlenden Dateien unterscheiden und technische Details ohne rohe Fehlertexte anzeigen.

### Breaking Changes

- Keine.

### Security

- Neue reine Leseaktion hinter der bestehenden Home-Assistant-Administratorprüfung; Wetterquelle ausschließlich aus der Integrationskonfiguration bestimmen. Anbieter-Rohfehler nicht an das Panel weitergeben; Quellenbezeichnungen als Text darstellen.

## 0.12.0 - 2026-11-12

### Features

- Unter „Inbetriebnahme → EOS-Verbindung“ alle konfigurierten Fahrzeuge mit Name und stabiler ID anzeigen und ihre individuellen EOS-Ressourcen bearbeiten. Die Zuordnung wird direkt in der bestehenden Geräteliste gespeichert; alle Fahrzeuge verwenden weiterhin eine gemeinsame EOS-Verbindung. Ohne Fahrzeugliste bleibt die bisherige Einzelzuordnung verfügbar. Deutsche und englische Einrichtungshinweise ergänzen.

### Bugfixes

- Bei einer Fahrzeugliste nicht länger die ungenutzte einzelne Fahrzeugressource prüfen oder als aktive Zuordnung anzeigen. Unvollständige, doppelte, ungültige und mit der Speicherressource kollidierende Zuordnungen ohne Teiländerungen ablehnen; Fahrzeugeinstellungen und Plugin-Konfiguration erhalten.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.11.0 - 2026-11-11

### Features

- Bis zu acht konfigurierte Fahrzeuge einzeln im Stromflussdiagramm mit Name, eigener Ladeleistung, fünf SoC-Balken und eigener Flusslinie darstellen. Ein Klick öffnet die jeweilige Fahrzeug-Detailseite. Die Diagrammhöhe passt sich der Anzahl sichtbarer Verbraucher an. Unterhalb der Übersicht zeigen eigene Modus-Kacheln für jedes Auto den aktuellen EOS-Modus und den nächsten geplanten Moduswechsel; Name und Detailverknüpfung bleiben erhalten.

### Bugfixes

- Auch bei genau einem Fahrzeug aus der Geräteliste dessen SoC im Diagramm anzeigen. Messwerte, gehaltene Anzeigen und Bezugsleistungen der Leistungsringe je Fahrzeug verwenden, statt sie aus der Flottensumme zu übernehmen.
- Nicht angeschlossene oder nicht verfügbare Fahrzeuge einzeln ausgrauen; Status nur im Tooltip und für Screenreader anzeigen, ohne Hinweismeldung im Diagrammknoten. Unbekannte Leistungen und SoC-Werte nicht durch Werte anderer Fahrzeuge ersetzen.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.10.0 - 2026-11-11

### Features

- Neues Wallbox-Plugin „go-e Charger – lokale HTTP-API v2“ (`goe_http_v2`) für die direkte lokale Anbindung ohne zusätzliche HA-Mess- und Steuerentitäten. API-Version im auswählbaren Namen kennzeichnen; Ladestatus, Leistung und Strom-/Phasengrenzen aus gefilterten API-v2-Abfragen lesen und an EOS weitergeben. Gerätevariante, eingestellte Maximalstromgrenze, Typ-2-Kabel und 16-A-Adapter berücksichtigen.
- Bestätigte Ladestromvorgabe, Ladefreigabe und Pause sowie optional freigegebene 1-/3-Phasenumschaltung mit stromfreiem Zwischenzustand unterstützen. Nicht angeschlossenes Fahrzeug und nicht erreichbarer Charger deaktivieren den optionalen Ladepunkt, ohne unbekannte Leistungen als 0 zu melden.

### Bugfixes

- Keine.

### Breaking Changes

- Keine. go-e HTTP-API v1 und Cloud-API sind nicht Teil dieses zusätzlichen Plugins.

### Security

- Schreibbefehle auf `amp`, `frc` und `psm` begrenzen, API-Annahme und zurückgelesene Einstellungen prüfen. Vor dem Ladestart aktuelle Grenzen erneut lesen. Umleitungen und System-HTTP-Proxys deaktivieren; Rohantworten und Netzwerkadressen nicht in Fehlermeldungen ausgeben.

## 0.9.0 - 2026-11-11

### Features

- ESPHome Modbus Bridge von rosenrot00, Stand 2026.10.2, anhand von Protokoll und Quellcode als Gateway für das Deye-Plugin abgleichen. Anleitung und gepinntes ESP32-Beispiel mit RS485-Einstellungen, HA-Quell-IP-Freigabe und schrittweiser Inbetriebnahme ergänzen. Hardwaretest steht aus.
- Deye SUN-12K-SG04LP3-EU direkt über ein Modbus-TCP↔RTU-Gateway anbinden: SoC, Lade-/Entladeleistung, PV-Leistung, Netzanschlussleistung, AC-Leistung und nativen Hausverbrauch ohne zusätzliche HA-Sensorintegration lesen. Als Speicher oder ausschließlich lesenden Wechselrichter in der Geräteliste einrichten, auch gemeinsam mit Fronius und anderen Plugins.
- Optionalen Deye-Remote-Modus für kompatible Firmware mit bestätigten Leistungsvorgaben und 300-Sekunden-Watchdog unterstützen. Normale Eigenverbrauchsregelung, Entladesperre, Netzladung und ausdrücklich freigegebene Batterieeinspeisung berücksichtigen Geräte-/BMS-Stromgrenzen und frische individuelle SoC-Grenzen. Remote-Steuerung bleibt bei der Einrichtung zunächst ausgeschaltet.

### Bugfixes

- Keine.

### Breaking Changes

- Keine. Der Plugin-Vertrag erhält die optionale Kennzeichnung `uses_dispatch_context`, damit auch einzelne Speicher die aktuellen SoC-Grenzen und den Bedarf zur PV-Ladeunterstützung erhalten können.

### Security

- ESPHome-Gateway-Beispiel auf die eingetragene HA-Quell-IP begrenzen und WLAN-/OTA-Zugangsdaten über eine separate Secrets-Datei einbinden.
- Deye-Schreibzugriffe auf das geprüfte dreiphasige 12-kW-Niedervoltprofil und die Remote-Register begrenzen. Keine laufenden Schreibzugriffe auf Batterie-Grundeinstellungen oder Ladezeitpläne. Unbestätigte Vorgaben, fremde Remote-Steuerung und nicht unterstützte Firmware bleiben Fehler; reine PV-Plugins besitzen keine Schreibmethoden.

## 0.8.0 - 2026-11-11

### Features

- Unter Inbetriebnahme → Geräte alle bereits eingerichteten Speicher, Wechselrichter und Wallboxen mit ihrem Namen direkt als auswählbare Liste anzeigen. Neue Installationen starten ohne Geräte. „Gerät hinzufügen“ steht unter der Liste; bestehende Einträge öffnen ihre Bearbeitung und können dort mit Bestätigung entfernt werden.
- Allgemeine Geräteverwaltung mit Hinzufügen, Bearbeiten und Entfernen. Jeder Speicher und reine PV-Wechselrichter erhält ein eigenes Plugin mit eigenem Formular; Wallboxen sind über denselben Gerätedialog erreichbar und behalten die Plugin-Auswahl je Fahrzeug. Bestehende Fronius-Untergeräte werden beim Bearbeiten in eigenständige Geräte übernommen. Gemischte Speicher-Plugins, ein eigener Nur-Lese-Vertrag für PV-Wechselrichter sowie direkte Fronius- und generische HA-Wechselrichter werden unterstützt.
- Genau eine Gerätequelle für den gemeinsamen Netzzähler auswählen. PV-Leistung und vollständige AC-Hausbilanzen aus den Plugin-Messwerten bilden; vorhandene HA-Quellsensoren behalten Vorrang. Die Anzeige kennzeichnet die gemeinsame EOS-Speicherplanung bei mehreren Batterien als Näherung.
- Fronius-Modbus-Plugin um bis zu acht Wechselrichter mit eigenen IP-Adressen, Ports und Unit-IDs erweitern. Zusätzliche Geräte können reine PV-Wechselrichter oder weitere Batteriespeicher sein. PV-Leistung wird vollständig summiert; Hausverbrauch entsteht aus der gesamten AC-Leistung und genau einem gemeinsamen Netzanschlusszähler, dessen Gateway separat konfigurierbar ist.
- Mehrere Batterien als gemeinsame EOS-Speicherressource: kapazitätsgewichteter SoC, summierte Lade-/Entladeleistung und Verteilung des gemeinsamen Leistungsbudgets nach verfügbarem Energieinhalt beziehungsweise freier Kapazität. SoC-Grenzen gelten je Batterie; Richtungswechsel und geänderte Gerätesteuerungen werden vor einer neuen Verteilung neutralisiert. PV-Ladestart prüft die tatsächlich verfügbare Gruppenleistung vor der Fahrzeugfreigabe.
- Gesamtkapazität, konfigurierte Gesamtleistungsgrenzen und SoC-Grenzen der Speichergruppe mit Rückbestätigung an EOS übertragen. Die Kostenbilanz verwendet die konfigurierte Gesamtkapazität bereits vor der EOS-Bestätigung. Einstellungen zeigen Messwerte und Verfügbarkeit jedes Wechselrichters.

### Bugfixes

- Beschriftungen der Konfigurationsmenüs direkt mit der HA-Menüantwort ausgeben. Geräte-, Inbetriebnahme- und Fahrzeugmenüs zeigen damit auch ohne neu geladene Frontend-Übersetzungen lesbare Einträge; Deutsch und Englisch einschließlich Sprachrückfall bleiben unterstützt.

### Breaking Changes

- Keine. Bestehende Einzelwechselrichter-Konfigurationen bleiben gültig. Der Plugin-Vertrag wird um optionale Angaben für die Verteilung von Speicherbefehlen ergänzt.

### Security

- Reine PV-Geräte erhalten keine Schreibbefehle. Ungültige oder doppelte Gerätekonfigurationen werden ohne Netzwerkzugriff abgelehnt; unvollständige Messungen werden nicht als Nullleistung oder vollständige Anlagensumme ausgegeben.

## 0.7.4 - 2026-11-11

### Features

- Berechneten Durchschnittspreis in ct/kWh direkt bei den Kostensummen anzeigen: Tagesübersicht mit Gesamtsumme und Verbraucherkarten, Kosten-Kennzahl auf den Detailseiten sowie Diagramm-Hinweise je Zeitraum und Energiequelle. Quellentabellen behalten ihre eigene Preisspalte. Bei teilweise bekannten Kosten wird der Preis aus dem bewerteten Energieanteil geschätzt und mit ≈ gekennzeichnet; ohne bewertete Energiemenge oder Verbrauch bleibt er unbekannt. Bekannte Kostenteilsummen werden nicht als Kosten für die gesamte Energiemenge ausgegeben.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

## 0.7.3 - 2026-11-11

### Features

- Autosymbol in der Energieübersicht und den Fahrzeugkarten in Seitenansicht. Fünf vertikale SoC-Balken zeigen den Ladestand analog zum Speichersymbol in 20-%-Stufen; unbekannter SoC blendet die Balken aus und bleibt von 0 % unterscheidbar.

### Bugfixes

- Keine.

### Breaking Changes

- Keine.

### Security

- Keine.

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
