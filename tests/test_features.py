"""Browser-Test für Termine, Countdown, Kalenderdatei und Belegerkennung.

Start:  pip install playwright pillow && playwright install chromium
        python3 tests/test_features.py

Der Test erzeugt selbst einen Tankbeleg als Bild (kein echtes Foto) und prüft die Erkennung damit.
Echte Belege mit Knicken, Schatten und Thermopapier sind damit NICHT abgedeckt.
"""
import json, re, sys, time, subprocess, os, tempfile, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont, ImageFilter

REPO = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="camper-feat-"))
PORT = 8766
BASE = f"http://localhost:{PORT}/camper-repository/"
fail = []


def ok(c, msg):
    print(("  OK   " if c else "  FEHLER ") + msg)
    if not c:
        fail.append(msg)


def make_receipt(path, d):
    ds = d.strftime("%d.%m.%Y")
    lines = ["      ARAL Tankstelle", "   Musterstr. 12", "   12345 Musterstadt", "", f"Datum: {ds}   Zeit: 08:15",
             "Zapfsaeule 4", "Diesel", "Menge        62,45 l", "Preis      1,689 EUR/l", "Brutto     105,48 EUR",
             "MwSt 19%    16,84 EUR", "EC-Karte   105,48 EUR", "", "Vielen Dank fuer Ihren Besuch"]
    font = None
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",):
        if os.path.exists(f):
            font = ImageFont.truetype(f, 30)
    im = Image.new("RGB", (620, 60 + 44 * len(lines)), (245, 245, 240))
    dr = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        dr.text((30, 30 + 44 * i), ln, fill=(25, 25, 25), font=font)
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    im.save(path)


def check_ics(txt, due, lead):
    ok(txt.startswith("BEGIN:VCALENDAR\r\n") and txt.endswith("END:VCALENDAR\r\n"), "ICS: Rahmen und CRLF")
    ok("\n" not in txt.replace("\r\n", ""), "ICS: nur CRLF-Zeilenenden")
    ok(max(len(l.encode()) for l in txt.split("\r\n")) <= 75, "ICS: keine Zeile über 75 Byte")
    ok(f"DTSTART;VALUE=DATE:{due.replace('-', '')}" in txt, "ICS: Ganztagstermin am Fälligkeitstag")
    ok(txt.count("BEGIN:VALARM") == 2 * txt.count("BEGIN:VEVENT") == txt.count("END:VALARM"), "ICS: zwei Alarme je Termin (Vorlauf und Fälligkeitstag)")
    ok(f"TRIGGER:-P{lead - 1}DT15H" in txt, f"ICS: Vorlauf-Alarm {lead} Tage vorher, 9:00 Uhr")
    ok("TRIGGER:PT9H" in txt, "ICS: Alarm am Fälligkeitstag, 9:00 Uhr")
    ok(txt.count("BEGIN:VEVENT") == txt.count("END:VEVENT") >= 1, "ICS: VEVENT ausgeglichen")


(TMP / "www").mkdir()
os.symlink(REPO, TMP / "www" / "camper-repository")
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", str(TMP / "www")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(BASE)
        pg.wait_for_selector("#main .top")
        pg.wait_for_function("window.__app")

        print("1) Hilfsfunktionen")
        ev = lambda js, *a: pg.evaluate(js, *a) if a else pg.evaluate(js)
        ok(ev("addMonths('2026-01-31',1)") == "2026-02-28", "Monatsende wird abgeschnitten (31.01. + 1 Monat)")
        ok(ev("addMonths('2026-11-15',3)") == "2027-02-15", "Jahreswechsel bei addMonths")
        ok(ev("addMonths('2028-02-29',12)") == "2029-02-28", "Schaltjahr + 12 Monate")
        today = datetime.date.today()
        ok(ev(f"daysTo('{(today + datetime.timedelta(days=10)).isoformat()}')") == 10, "daysTo: 10 Tage in der Zukunft")
        ok(ev(f"daysTo('{(today - datetime.timedelta(days=3)).isoformat()}')") == -3, "daysTo: 3 Tage überfällig")

        print("2) Termin anlegen, Countdown, Startseite")
        ok(pg.locator('[data-tab="rem"]').count() == 1, "Tab „Termine“ vorhanden")
        box = pg.locator(".tabs").bounding_box()
        tabs = pg.locator(".tabs > .tab, .tabs > .add")
        right = max(tabs.nth(i).bounding_box()["x"] + tabs.nth(i).bounding_box()["width"] for i in range(tabs.count()))
        ok(right <= 390.5, "Tab-Leiste passt in 390 px Breite (rechte Kante %.1f)" % right)
        overflow = ev("[...document.querySelectorAll('.tab span:last-child')].some(e=>e.scrollWidth>e.clientWidth+1)")
        ok(not overflow, "Tab-Beschriftungen werden nicht abgeschnitten")
        pg.click('[data-tab="rem"]')
        ok("Noch keine offenen Termine" in pg.inner_text("#main"), "leerer Zustand")
        pg.click('[data-act="rem-new"]')
        pg.wait_for_selector("#r-k")
        ok(pg.input_value("#r-r") == "24" and pg.input_value("#r-l") == "30", "TÜV-Vorschlag: alle 2 Jahre, 30 Tage vorher")
        due = (today + datetime.timedelta(days=12)).isoformat()
        pg.fill("#r-d", due)
        pg.click("#sh-save")
        pg.wait_for_selector(".cd")
        ok(pg.inner_text(".cd .n") == "12", "Countdown zeigt 12 Tage")
        ok("soon" in pg.get_attribute(".cd", "class"), "Termin im Vorlauf ist hervorgehoben")
        ok(pg.locator('[data-tab="rem"].alert').count() == 1, "Tab zeigt Hinweispunkt")
        pg.click('[data-tab="home"]')
        ok(pg.locator("#main .cd").count() == 1 and "Nächste Termine" in pg.inner_text("#main"), "Startseite zeigt den nächsten Termin")

        print("3) Weitere Termine, Reihenfolge, überfällig, heute")
        ev("""()=>{const v=curV();const mk=(t,k,off,rep,lead)=>{const d=new Date();d.setDate(d.getDate()+off);const iso=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
          S.reminders.push({id:crypto.randomUUID(),title:t,kind:k,vehicleId:v.id,due:iso,repeat:rep,lead:lead,note:'',done:false,deleted:false,createdAt:Date.now(),updatedAt:Date.now()})};
          mk('Gasprüfung','gas',-3,24,30);mk('Versicherung','ins',0,12,30);mk('Reifenwechsel','tyres',200,6,14)}""" .replace("()=>", "()=>", 1))
        pg.evaluate("render()")
        pg.click('[data-tab="rem"]')
        titles = pg.locator(".cd .k").all_inner_texts()
        ok(titles[:3] == ["Gasprüfung", "Versicherung", "TÜV / HU"], "Sortierung nach Datum: " + ", ".join(titles))
        ok("over" in pg.locator(".cd").nth(0).get_attribute("class") and "überfällig" in pg.locator(".cd .u").nth(0).inner_text(), "überfälliger Termin markiert")
        ok(pg.locator(".cd .n").nth(1).inner_text() == "Heute", "heute fälliger Termin zeigt „Heute“")
        pg.screenshot(path=str(TMP / "termine.png"), full_page=True)

        print("4) Erledigt: Wiederholung und einmalig")
        pg.locator(".cd").nth(0).click()
        pg.wait_for_selector("#r-done")
        pg.click("#r-done")
        pg.wait_for_selector(".cd")
        gas = ev("S.reminders.find(r=>r.title==='Gasprüfung')")
        exp = ev(f"addMonths('{(today - datetime.timedelta(days=3)).isoformat()}',24)")
        ok(gas["due"] == exp and not gas["done"], "Wiederkehrender Termin springt auf " + exp)
        ev("""()=>{const v=curV();S.reminders.push({id:'once',title:'Einmalig',kind:'other',vehicleId:null,due:'2099-01-01',repeat:0,lead:0,done:false,deleted:false,createdAt:1,updatedAt:1});render()}""")
        ev("remDone(S.reminders.find(r=>r.id==='once'))")
        o = ev("S.reminders.find(r=>r.id==='once')")
        ok(o["done"] and o["doneAt"], "Einmaliger Termin wird als erledigt abgelegt")
        pg.click('[data-tab="rem"]')
        ok("Erledigt" in pg.inner_text("#main") and "Einmalig" in pg.inner_text("#main"), "Erledigt-Liste zeigt ihn")

        print("5) Kalenderdatei")
        pg.click('[data-tab="rem"]')
        with pg.expect_download() as dl:
            pg.click('[data-act="rem-ics-all"]')
        d = dl.value
        txt = open(d.path(), encoding="utf-8", newline="").read()
        ok(d.suggested_filename.endswith(".ics"), "Download heißt " + d.suggested_filename)
        check_ics(txt, due, 30)
        ok("RRULE:FREQ=YEARLY;INTERVAL=2" in txt, "ICS: Wiederholung alle 2 Jahre")
        ok(txt.count("BEGIN:VEVENT") == 4, "ICS: alle 4 offenen Termine")
        sample = ev("buildIcs([{id:'x',title:'Test; mit, Sonderzeichen äöü und eine sehr lange Bezeichnung die gefaltet werden muss weil sie über fünfundsiebzig Byte geht',due:'2027-03-05',repeat:0,lead:1,note:'Zeile1\\nZeile2',updatedAt:5}])")
        ok(max(len(l.encode()) for l in sample.split("\r\n")) <= 75 and "TRIGGER:-PT15H" in sample, "ICS: Faltung, Vorlauf 1 Tag")
        ok("\\;" in sample and "\\," in sample and "\\n" in sample, "ICS: Sonderzeichen maskiert")

        print("6) Bearbeiten, Löschen, Sicherung")
        pg.click('[data-tab="rem"]')
        pg.locator(".cd", has_text="TÜV / HU").click()
        pg.wait_for_selector("#r-t")
        pg.fill("#r-t", "TÜV neu")
        pg.click("#sh-save")
        pg.wait_for_selector(".cd")
        ok(ev("S.reminders.filter(r=>r.title==='TÜV neu').length") == 1 and ev("S.reminders.filter(r=>r.title==='TÜV / HU').length") == 0, "Bearbeiten legt keinen zweiten Termin an")
        n0 = ev("S.reminders.length")
        pg.locator(".cd", has_text="Reifenwechsel").click()
        pg.click("#sh-del"); pg.click("#sh-yes")
        pg.wait_for_selector(".cd")
        ok(ev("S.reminders.find(r=>r.title==='Reifenwechsel').deleted") is True and ev("S.reminders.length") == n0, "Löschen setzt nur den Löschmarker")
        ok(ev("syncSet().reminders.length") == ev("S.reminders.length"), "Termine sind im Abgleichsstand enthalten")
        j = ev("JSON.stringify({app:'camper-repository',version:1,state:S,photos:{}})")
        ev("S.reminders=[]; persist()")
        ev("""async(j)=>{const f=new File([j],'b.json');await importData(f)}""", j)
        pg.wait_for_function("S.reminders.length>0")
        ok(ev("S.reminders.length") == n0, "Wiederherstellen bringt die Termine zurück")
        ok(not errs, "keine JS-Fehler: " + "; ".join(errs[:3]))

        print("7) Belegerkennung: Auswertung des Textes")
        P = lambda t, k="fuel": ev("([t,k])=>parseReceipt(t,k)", [t, k])
        r = P("ARAL Tankstelle\n12345 Musterstadt\nDatum: 14.10.2026\nMenge 62,45 l\nPreis 1,689 EUR/l\nBrutto 105,48 EUR")
        ok(r.get("liters") == 62.45 and r.get("ppl") == 1.689 and r.get("total") == 105.48 and r.get("date") == "2026-10-14", "Standardbeleg: %s" % json.dumps(r))
        ok(r.get("place") == "Aral, Musterstadt", "Tankstelle und Ort: " + str(r.get("place")))
        r = P("Shell\nDiesel 48,12 l\n1,799 EUR/l\n86,56 EUR\nMwSt 13,82\n02.03.26")
        ok(r.get("liters") == 48.12 and r.get("total") == 86.56 and r.get("date") == "2026-03-02", "Betrag ohne Stichwort, Datum 2-stellig: %s" % json.dumps(r))
        r = P("Datum 31.02.2026\nDatum 05.13.2026\nMenge 10,00 l")
        ok("date" not in r, "ungültige Daten werden verworfen")
        r = P("Datum 01.01.2099\n")
        ok("date" not in r, "Datum in der Zukunft wird verworfen")
        r = P("AdBlue 9,80 l\n1,29 EUR/l\nGesamt 12,64 EUR", "adblue")
        ok(r.get("liters") == 9.8 and r.get("total") == 12.64, "AdBlue-Beleg: %s" % json.dumps(r))
        r = P("nur Text ohne Zahlen")
        ok(not r, "kein Treffer bei Text ohne Werte")

        print("8) Belegerkennung: Foto im Formular (Texterkennung im Browser)")
        img = TMP / "beleg.png"
        rd = today - datetime.timedelta(days=3)
        make_receipt(img, rd)
        pg.click('[data-tab="home"]')
        n_entries = ev("S.entries.filter(e=>!e.deleted).length")
        pg.click('[data-new="fuel"]')
        pg.wait_for_selector("#ph-in", state="attached")
        pg.set_input_files("#ph-in", str(img))
        t0 = time.time()
        pg.wait_for_function("document.querySelector('#ocr-box') && /Aus dem Beleg gelesen|konnten keine Werte|nicht verfügbar/.test(document.querySelector('#ocr-box').innerText)", timeout=120000)
        print("      Dauer der Erkennung: %.1f s" % (time.time() - t0))
        print("      Rohtext:", repr(ev("OCR.lastText")[:300]))
        vals = {k: pg.input_value("#" + k) for k in ("f-d", "f-l", "f-p", "f-t", "f-pl")}
        print("      Felder:", vals)
        ok(vals["f-l"] == "62,45", "Menge übernommen: " + vals["f-l"])
        ok(vals["f-p"] == "1,689", "Preis je Liter übernommen: " + vals["f-p"])
        ok(vals["f-t"] == "105,48", "Betrag übernommen: " + vals["f-t"])
        ok(vals["f-d"] == rd.isoformat(), "Datum übernommen: " + vals["f-d"])
        ok("Aral" in vals["f-pl"], "Tankstelle übernommen: " + vals["f-pl"])
        ok(pg.input_value("#f-o") == "", "Kilometerstand bleibt leer")
        ok(ev("S.entries.filter(e=>!e.deleted).length") == n_entries, "Es wurde nichts automatisch gespeichert")
        pg.screenshot(path=str(TMP / "ocr.png"))
        # vorhandene Eingaben dürfen nicht überschrieben werden
        pg.fill("#f-o", "123456")
        pg.fill("#f-l", "10,00")
        pg.set_input_files("#ph-in", str(img))
        pg.wait_for_function("/Aus dem Beleg gelesen|konnten keine/.test(document.querySelector('#ocr-box').innerText)", timeout=120000)
        pg.wait_for_timeout(500)
        ok(pg.input_value("#f-l") == "10,00", "bereits eingetragene Menge bleibt unverändert")
        ok(pg.input_value("#f-o") == "123456", "Kilometerstand bleibt")
        pg.click("#sh-save")
        pg.wait_for_selector("#sheet", state="hidden")
        e = ev("S.entries.filter(x=>!x.deleted&&x.type==='fuel').at(-1)")
        ok(e["photo"] is True and e["odo"] == 123456, "Speichern mit Foto funktioniert danach normal")

        print("9) Offline")
        ctx.set_offline(True)
        pg.click('[data-new="fuel"]')
        pg.wait_for_selector("#ph-in", state="attached")
        pg.set_input_files("#ph-in", str(img))
        pg.wait_for_function("/Aus dem Beleg gelesen|konnten keine|nicht verfügbar|Internet/.test(document.querySelector('#ocr-box').innerText)", timeout=120000)
        print("      Offline-Ergebnis:", pg.inner_text("#ocr-box")[:120])
        ctx.set_offline(False)
        ok(True, "Offline bricht nicht ab")
        console_errs = [x for x in errs if "favicon" not in x and "Failed to load resource" not in x and "ERR_" not in x]
        ok(not console_errs, "keine JS-Fehler: " + "; ".join(console_errs[:3]))
        br.close()
finally:
    srv.terminate()
print("\nErgebnis:", "ALLES OK" if not fail else "%d FEHLER" % len(fail))
for f in fail:
    print(" -", f)
print("Bilder:", TMP)
sys.exit(1 if fail else 0)
