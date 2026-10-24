# Tests

`test_sync.py` prüft die App in einem echten Browser (Chromium) gegen ein **simuliertes** Dropbox:

- Anmeldung mit PKCE, per Weiterleitung und per Code, falscher `state`, Abbruch
- zwei Geräte: Übernahme, Konflikt (später geändert gewinnt), Löschen, Belegfotos samt neuer Fassung
- unveränderte Dateien werden nicht erneut geladen, automatisches Nachsehen bei offener App
- Token-Erneuerung, Neuladen, Offline, Trennen mit Widerruf
- Manifest, Service Worker, Start der App offline, Sicherung als Download

Start:

```
pip install playwright
playwright install chromium
python3 tests/test_sync.py
```

Der Test legt keine Dateien im Repository an und greift nicht auf das echte Dropbox zu.
Er ersetzt keinen Test auf dem iPhone und gegen das echte Dropbox.
