# EOS-Versionen und Batterieprofile

Die Energiezentrale unterstützt die bisherige flache Batterie-/Fahrzeugkonfiguration
und die Profilstruktur des EOS-Add-ons **0.3.0.dev2611122196862169**. Erkennung pro
Gerät über die zurückgegebenen Konfigurationsfelder, nicht über eine fest kodierte
Liste von Entwicklungsversionsnummern. Verschiedene Geräte bleiben getrennt;
die vorhandene Serialisierung von Konfigurationsänderungen bleibt erhalten.

| Bedeutung | Bisher | Profilstruktur |
| --- | --- | --- |
| Installierte Kapazität schreiben | `capacity_wh` | `profile_adjustment.nominal_capacity_wh` |
| Ladeleistung schreiben | `max_charge_power_w` | `profile_adjustment.max_charge_power_w` |
| Entladeleistung schreiben | `max_discharge_power_w` | `profile_adjustment.max_discharge_power_w` |
| Kapazität für Kosten lesen | `capacity_wh` | `effective_nominal_capacity_wh` |
| Ladewirkungsgrad lesen | `charging_efficiency` | `effective_charging_efficiency` |
| Entladewirkungsgrad lesen | `discharging_efficiency` | `effective_discharging_efficiency` |

SoC-Ziele, Ladefaktoren (`charge_rates`) und Mindestladeleistung bleiben auf der
bisherigen Ebene. Ausgewählte Batterieprofile und zusätzliche Einstellungen
(beispielsweise Intervalle für Vollladungen) werden nicht ersetzt. Berechnete
`effective_*`- und `measurement_*`-Ausgaben werden beim Schreiben weggelassen;
EOS berechnet sie selbst erneut.

## Wenn eine Bestätigung weiterhin fehlt

Die Energiezentrale prüft nach einem Update sowohl die übernommene Anpassung als
auch die aufgelöste Kapazität bzw. Leistung. Ein Profil kann einen eingetragenen
Installationswert zusätzlich begrenzen. Dann passt der Bezugswert für die
Planfaktoren nicht zur lokalen Steuerung; die Abweichung bleibt deshalb sichtbar.
Die Warnung darf nicht durch eine bloße Schreibbestätigung unterdrückt werden.

In EOS prüfen:

- Ist das konfigurierte Fahrzeug bzw. der Speicher unter derselben Ressourcen-ID vorhanden?
- Ist `battery_profile` verfügbar und für das tatsächliche Gerät geeignet?
- Enthält `profile_adjustment.nominal_capacity_wh` bei generischen Profilen die korrekte Kapazität?
- Stimmen die `effective_max_*_power_w`-Werte nach der Anpassung mit den Grenzen
  überein, welche die Energiezentrale übertragen soll?

Das Plugin wechselt keine Profile automatisch und erhöht keine technischen
Profilgrenzen. Für einen echten Konflikt muss die Konfiguration fachlich passend
korrigiert werden. Das neue EOS-Profilmodell verlangt **positive** Leistungs-
Anpassungen; null kann dort nicht als Lade-/Entladesperre übertragen werden.
Solche Synchronisierungen bleiben unbestätigt, statt einen Ersatzwert von 1 W
oder eine unbegrenzte Leistung zu verwenden. Lokale Hardwaregrenzen bleiben aktiv.

Für abwesende Fahrzeuge wird `charge_rates=[0]` gesetzt und das Ladeziel entfernt.
Im Profilmodell bleibt die konfigurierte SoC-Spanne 0–100 %, damit technische
Profilgrenzen auflösbar bleiben. Eine unveränderte positive Nennleistung ist
dabei keine Ladefreigabe. Beim Wiederverbinden werden die erkannten Ladegrenzen
und anschließend das geplante Ladeziel erneut synchronisiert.

Die Kostenschätzung verwendet die `effective_*`-Kapazität und Wirkungsgrade aus
EOS. Diese Profilwerte gelten am Referenzbetriebspunkt und sind eine Näherung,
keine zeitaktuelle Messung der Verluste. Fehlen sie, wird keine Null-Effizienz
oder Null-Kapazität erfunden; die bestehende Kostenlogik behandelt den Abruf als
vorübergehend nicht verfügbar und erhält ihren letzten gültigen Bestand.

Vertragsgrundlage:
[EOS-Batterieeinstellungen im betroffenen Build](https://github.com/Akkudoktor-EOS/EOS/blob/7e10f64048657795271df2a62b1cfbb92ca0329c/src/akkudoktoreos/devices/settings/batterysettings.py).
Die Regressionstests verwenden einen lokalen API-Vertrag mit alten und neuen
Antworten; ein Test gegen die konkrete laufende Kundeninstallation steht aus.

## English

Both legacy flat EOS settings and the battery-profile API in development build
0.3.0.dev2611122196862169 are supported. Detection uses returned fields per device,
not version string comparisons. Capacity and power adjustments are merged into
`profile_adjustment`; selected profiles, unrelated adjustments and other devices
are preserved. Computed `effective_*` and `measurement_*` outputs are not sent back.
Targets, charging rates and minimum charging power remain at the top level.

Confirmation checks both configured adjustments and their resolved effective
values. An unresolved profile or a different effective power remains an error:
local control and EOS factors must use matching power ratings. Select a suitable
profile and correct capacity in EOS; the integration does not replace profiles
or raise their technical limits. Zero power adjustments are unsupported by the
new API and rejected before writing, never replaced with a fictitious positive
or unlimited rating.

Absent vehicles use zero charge rates and cleared goals, with the profile's
configured SoC policy range kept at 0–100 %. Positive nameplate power does not
enable charging. Reconnection re-synchronizes limits and goals. Accounting reads
resolved effective capacity/efficiencies at the profile reference point; missing
values remain unavailable, while the existing ledger retains its last valid data.
Tests cover both API contracts; validation against the customer's running EOS
instance remains outstanding.
