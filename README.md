# Camper Repository

Logbuch für Camper als Web-App (PWA): Tanken, AdBlue, Belege, Campingplätze und Stellplätze. Läuft auf iPhone und PC, speichert lokal im Gerät und gleicht optional über das eigene Dropbox-Konto ab.

Stand: Prototyp 0.2

## Dateien

- `index.html`: die ganze App (Oberfläche, Datenhaltung, Abgleich)
- `manifest.webmanifest`, `sw.js`: Installation auf dem Home-Bildschirm und Offline-Betrieb
- `icons/`: Platzhalter-Icons

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

## Bekannte Grenzen

- Bei Konflikten entscheidet die Uhrzeit der Geräte (höheres `updatedAt` gewinnt).
- Löschmarker werden nie bereinigt, alte Foto-Fassungen bleiben als Dateien liegen.
- Jede Geräte-Datei enthält den kompletten Stand.
- Das Dropbox-Token liegt im Gerätespeicher der App.
