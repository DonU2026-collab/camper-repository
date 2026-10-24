# Camper Repository

Logbuch für Camper als Web-App (PWA): Tanken, AdBlue, Belege, Campingplätze und Stellplätze. Läuft auf iPhone und PC, speichert lokal im Gerät und gleicht optional über das eigene Dropbox-Konto ab.

Stand: Prototyp 0.3

## Dateien

- `index.html`: die ganze App (Oberfläche, Datenhaltung, Abgleich)
- `manifest.webmanifest`, `sw.js`: Installation auf dem Home-Bildschirm und Offline-Betrieb
- `icons/`: Platzhalter-Icons
- `ocr/`: Texterkennung für Tankbelege (tesseract.js, läuft im Gerät, siehe `ocr/README.md`)
- `tests/`: Browser-Tests (`test_sync.py` Abgleich und PWA, `test_features.py` Termine, Kalenderdatei, Belegerkennung)

## Veröffentlichung (GitHub Pages)

1. Repository → Settings → Pages → Branch `main`, Ordner `/ (root)`.
2. Adresse der App: `https://donu2026-collab.github.io/camper-repository/`

## Dropbox-Abgleich einrichten

In der Dropbox-App-Konsole (App-Typ „App folder“, Rechte `files.content.read` und `files.content.write`) unter „Redirect URIs“ genau diese Adresse eintragen, mit Schrägstrich am Ende:

```
https://donu2026-collab.github.io/camper-repository/
```

Der App-Key steht in `index.html` (`DBX_KEY`). Er ist kein Geheimnis. Die Anmeldung läuft per OAuth mit PKCE, ohne Server.

Ordner in der Dropbox des Anwenders: `devices/<Geräte-ID>.json` (kompletter Stand, nur dieses Gerät schreibt) und `photos/<Eintrag-ID>-<photoRev>.json` (Belegfotos, einmal geschrieben).

## Termine und Countdown

Eigener Tab „Termine“ mit Tageszahlen bis zur Fälligkeit (TÜV, Gasprüfung, Inspektion, Versicherung, Reifenwechsel). Fälligkeit nur nach Datum, optional wiederkehrend. Die Startseite zeigt die nächsten zwei. Die Erinnerung läuft über eine Kalenderdatei (.ics) mit Alarm am Vorlauftag und am Fälligkeitstag, jeweils 9:00 Uhr. Die Termine werden wie alle Einträge über Dropbox abgeglichen.

## Belegerkennung

Nach einem Foto im Tank- oder AdBlue-Formular liest die App Datum, Menge, Preis je Liter, Betrag und Tankstelle und trägt sie in leere Felder ein. Gespeichert wird nie automatisch. Der Kilometerstand steht nicht auf dem Beleg.

## Bekannte Grenzen

- Bei Konflikten entscheidet die Uhrzeit der Geräte (höheres `updatedAt` gewinnt).
- Löschmarker werden nie bereinigt, alte Foto-Fassungen bleiben als Dateien liegen.
- Jede Geräte-Datei enthält den kompletten Stand.
- Das Dropbox-Token liegt im Gerätespeicher der App.
- Die Belegerkennung ist nur mit selbst erzeugten Beleg-Bildern getestet, nicht mit echten Thermobelegen.
- Die Erinnerung ist ein Kalender-Alarm. Die App sendet im Hintergrund keine Mitteilungen.
- Der Import der .ics-Datei auf dem iPhone ist noch nicht auf einem echten Gerät geprüft.
