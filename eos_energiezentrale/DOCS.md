# Einrichtung

Trage in der Home-Assistant-App-Konfiguration die Akkudoktor-EOS-Basisadresse ein. Prüfe die Sensorzuordnung und die Hardwaretypen. Mit `battery_type: fronius` und `wallbox_type: nrgkick` sind die integrierten Treiber ausgewählt. JSON-Parameter überschreiben die Standardentitäten.

Die App startet im Lesemodus. Prüfe zuerst Live-Messwerte und EOS-Plan. Beende bestehende Automationen, die dieselben Geräte steuern, bevor du die Steuerung im Dashboard übernimmst. Die App gibt beim normalen Stoppen die Batterie an Auto zurück und pausiert die Wallbox, wenn sie deren Steuerung übernommen hatte.

Ladeziele, PV-Laden und Regelintervall findest du im Dashboard unter **Einstellungen**. Verbindungsdaten und technische Geräteparameter bleiben im Konfigurationsreiter der Home-Assistant-App.
