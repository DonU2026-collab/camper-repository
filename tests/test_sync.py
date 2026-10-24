"""Browser-Test für Camper Repository gegen ein simuliertes Dropbox.

Start:  pip install playwright && playwright install chromium
        python3 tests/test_sync.py

Der Test startet einen lokalen Webserver, öffnet mehrere "Geräte" (getrennte Browser-Kontexte) und
ersetzt Dropbox durch einen Speicher im Testprozess. Es wird nichts im echten Dropbox gelesen oder geschrieben.
"""
import json, hashlib, base64, time, re, sys, urllib.parse, subprocess, os, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="camper-test-"))

PORT = 8765
BASE = f"http://localhost:{PORT}/camper-repository/"
store = {}          # Dropbox-Dateien: Pfad -> Bytes
folders = set()     # angelegte Ordner
codes = {}          # code -> (challenge, redirect_uri)
auth_pending = {}   # state -> challenge
tokens = {}         # access_token -> True
refresh = {}        # refresh_token -> True
log = []
downloads = []
fail = []
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "POST, GET, OPTIONS"}
online = {"v": True}

def b64u(b): return base64.urlsafe_b64encode(b).decode().rstrip("=")
def ok(c, msg):
    print(("  OK   " if c else "  FEHLER ") + msg)
    if not c: fail.append(msg)

def handler(route):
    req = route.request
    url = req.url
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    u = urllib.parse.urlparse(url)
    h = req.headers
    if u.hostname == "www.dropbox.com":
        q = dict(urllib.parse.parse_qsl(u.query))
        log.append(("authorize", q))
        if q.get("client_id") != "7gcrpubuf57ogsc" or q.get("code_challenge_method") != "S256" or q.get("token_access_type") != "offline":
            return route.fulfill(status=400, body="bad authorize")
        code = "CODE" + str(len(codes) + 1)
        codes[code] = (q["code_challenge"], q.get("redirect_uri"))
        if q.get("redirect_uri"):
            loc = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": code, "state": q["state"]})
            return route.fulfill(status=302, headers={"location": loc})
        return route.fulfill(status=200, content_type="text/html", body=f"<html><body>Code: <b>{code}</b></body></html>")
    if u.path == "/oauth2/token":
        f = dict(urllib.parse.parse_qsl(req.post_data or ""))
        if f.get("grant_type") == "authorization_code":
            ch, ru = codes.get(f.get("code"), (None, None))
            good = ch and b64u(hashlib.sha256(f.get("code_verifier", "").encode()).digest()) == ch and f.get("client_id") == "7gcrpubuf57ogsc" and f.get("redirect_uri") == ru
            if not good:
                return route.fulfill(status=400, headers=CORS, content_type="application/json", body=json.dumps({"error": "invalid_grant"}))
            at, rt = "AT" + str(len(tokens) + 1), "RT" + str(len(refresh) + 1)
            tokens[at] = True; refresh[rt] = True
            return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"access_token": at, "refresh_token": rt, "expires_in": 14400, "token_type": "bearer"}))
        if f.get("grant_type") == "refresh_token" and f.get("refresh_token") in refresh:
            at = "AT" + str(len(tokens) + 1); tokens[at] = True
            return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"access_token": at, "expires_in": 14400}))
        return route.fulfill(status=400, headers=CORS, content_type="application/json", body=json.dumps({"error": "invalid_grant"}))
    # API
    if not online["v"]:
        return route.abort("internetdisconnected")
    auth = h.get("authorization", "")
    if auth.replace("Bearer ", "") not in tokens:
        return route.fulfill(status=401, headers=CORS, content_type="application/json", body=json.dumps({"error": {".tag": "expired_access_token"}}))
    if u.hostname == "api.dropboxapi.com":
        if u.path == "/2/files/list_folder":
            p = json.loads(req.post_data)["path"]
            if p not in folders:
                return route.fulfill(status=409, headers=CORS, content_type="application/json", body=json.dumps({"error_summary": "path/not_found/.", "error": {".tag": "path"}}))
            ent = [{".tag": "file", "name": k[len(p) + 1:], "content_hash": hashlib.sha256(store[k]).hexdigest()} for k in store if k.startswith(p + "/")]
            return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"entries": ent, "has_more": False, "cursor": "c"}))
        if u.path == "/2/auth/token/revoke":
            log.append(("revoke", auth)); return route.fulfill(status=200, headers=CORS, content_type="application/json", body="null")
    if u.hostname == "content.dropboxapi.com":
        arg = json.loads(h.get("dropbox-api-arg", "{}"))
        if u.path == "/2/files/upload":
            p = arg["path"]; store[p] = req.post_data_buffer or b""; folders.add(p.rsplit("/", 1)[0])
            return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"name": p.split("/")[-1]}))
        if u.path == "/2/files/download":
            p = arg["path"]; downloads.append(p)
            if p not in store:
                return route.fulfill(status=409, headers=CORS, content_type="application/json", body=json.dumps({"error_summary": "path/not_found/."}))
            return route.fulfill(status=200, headers=CORS, body=store[p])
    return route.fulfill(status=404, headers=CORS, body="unhandled " + url)

def new_device(browser, name):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="allow", accept_downloads=True)
    ctx.route(re.compile(r"https://(www\.dropbox\.com|api\.dropboxapi\.com|content\.dropboxapi\.com)/.*"), handler)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.errs = errs; pg.dname = name
    return ctx, pg

def connect(pg):
    pg.goto(BASE)
    pg.wait_for_selector("#main .top")
    pg.click('[data-tab="more"]')
    pg.click('[data-act="sync-on"]')
    pg.wait_for_url(re.compile(re.escape(BASE) + r"(\?.*)?$"))
    pg.wait_for_function("window.__app && window.__app.SYNC.cfg", timeout=10000)

def wait_sync(pg, timeout=15000):
    pg.wait_for_function("window.__app.SYNC.cfg && window.__app.SYNC.state==='ok' && !window.__app.SYNC.busy && window.__app.SYNC.cfg.lastSync", timeout=timeout)

def sync_now(pg):
    pg.evaluate("window.__app.SYNC.cfg.lastSync=null; window.__app.SYNC.state='idle'")
    pg.evaluate("window.__app.syncNow(true)")
    wait_sync(pg)

ADD = """async (o)=>{
  photoState={data:o.photo||null,had:false,removed:false};
  const v=curV();
  await commit(Object.assign({type:'fuel',vehicleId:v.id,date:o.date,odo:o.odo,liters:o.l,ppl:2,total:o.l*2,full:true,place:''},o.extra||{}),true);
  return S.entries.at(-1).id;
}"""

(TMP / "www").mkdir()
os.symlink(REPO, TMP / "www" / "camper-repository")   # die App läuft im Test unter /camper-repository/ wie auf GitHub Pages
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", str(TMP / "www")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    with sync_playwright() as p:
        br = p.chromium.launch()
        print("1) Gerät A: Anmeldung (PKCE, Weiterleitung)")
        ctxA, A = new_device(br, "A")
        connect(A)
        ok(any(l[0] == "authorize" for l in log), "Anmeldeseite mit PKCE aufgerufen")
        ok(A.evaluate("location.search")=="" , "Adresse nach Rückkehr bereinigt")
        wait_sync(A)
        ok(True, "Abgleich nach Anmeldung gelaufen")
        devfileA = "/devices/" + A.evaluate("window.__app.SYNC.cfg.deviceId") + ".json"
        if devfileA in store:
            st = json.loads(store[devfileA])["state"]
            ok(len(st["entries"]) == 0 and all(v["id"] != "v-demo" for v in st["vehicles"]), "Beispieldaten nicht im Abgleich")
        else:
            ok(True, "Beispieldaten nicht im Abgleich (keine Gerätedatei nötig)")

        print("2) Gerät A: echter Eintrag mit Foto")
        A.evaluate("demoOff()")
        A.evaluate("(()=>{const v=S.vehicles[0];v.name='Camper';stamp(v);delete v.auto;persist()})()")
        eid = A.evaluate(ADD, {"date": "2026-10-01", "odo": 50000, "l": 80, "photo": "data:image/jpeg;base64,QUJDREVGRw=="})
        A.evaluate("window.__app.syncNow(false)")
        time.sleep(0.5); wait_sync(A)
        sync_now(A)
        ok(devfileA in store, "Gerätedatei A in Dropbox")
        stA = json.loads(store[devfileA])["state"]
        ok(any(e["id"] == eid for e in stA["entries"]), "Eintrag in Gerätedatei A")
        rev = [e for e in stA["entries"] if e["id"] == eid][0]["photoRev"]
        ok(("/photos/%s-%s.json" % (eid, rev)) in store, "Foto-Datei photos/<id>-<rev>.json vorhanden (rev=%s)" % rev)
        ok(len([k for k in store if k.startswith("/photos/")]) == 1, "genau eine Foto-Datei")

        print("3) Gerät B: Anmeldung und Übernahme")
        ctxB, B = new_device(br, "B")
        connect(B)
        wait_sync(B)
        B.evaluate("demoOff()")
        sync_now(B)
        okE = B.evaluate("(id)=>!!S.entries.find(e=>e.id===id&&!e.deleted)", eid)
        ok(okE, "Eintrag von A auf B angekommen")
        ph = B.evaluate("(id)=>DB.get('photo:'+id)", eid)
        ok(ph == "data:image/jpeg;base64,QUJDREVGRw==", "Foto auf B vorhanden und unverändert")
        ok(B.evaluate("vehicles().some(v=>v.name==='Camper')"), "Fahrzeug von A auf B")

        print("4) Konflikt und Löschen")
        A.evaluate("(id)=>{const e=S.entries.find(x=>x.id===id);e.liters=11;stamp(e);persist()}", eid)
        time.sleep(0.2)
        B.evaluate("(id)=>{const e=S.entries.find(x=>x.id===id);e.liters=22;stamp(e);persist()}", eid)   # später, gewinnt
        sync_now(A); sync_now(B); sync_now(A)
        la = A.evaluate("(id)=>S.entries.find(x=>x.id===id).liters", eid)
        lb = B.evaluate("(id)=>S.entries.find(x=>x.id===id).liters", eid)
        ok(la == 22 and lb == 22, "Konflikt: später geändert gewinnt (A=%s, B=%s)" % (la, lb))
        B.evaluate("(id)=>removeEntry({id})", eid)
        sync_now(B); sync_now(A)
        ok(A.evaluate("(id)=>S.entries.find(x=>x.id===id).deleted===true", eid), "Löschen von B kommt bei A an (Marker)")

        print("5) Neues Foto, neue Fassung")
        eid2 = A.evaluate(ADD, {"date": "2026-10-05", "odo": 50500, "l": 60, "photo": "data:image/jpeg;base64,Rk9UTzE="})
        sync_now(A); sync_now(B)
        ok(B.evaluate("(id)=>DB.get('photo:'+id)", eid2) == "data:image/jpeg;base64,Rk9UTzE=", "zweiter Beleg samt Foto auf B")
        A.evaluate("""async (id)=>{photoState={data:'data:image/jpeg;base64,Rk9UTzI=',had:true,removed:false};const e=S.entries.find(x=>x.id===id);await commit(Object.assign({},e),false)}""", eid2)
        sync_now(A); sync_now(B)
        ok(B.evaluate("(id)=>DB.get('photo:'+id)", eid2) == "data:image/jpeg;base64,Rk9UTzI=", "geändertes Foto (neue photoRev) kommt an")
        ok(len([k for k in store if k.startswith("/photos/" + eid2)]) == 2, "alte Foto-Fassung bleibt als Datei liegen (bekannte Grenze)")

        print("5b) Unveränderte Dateien werden nicht erneut geladen, Nachsehen bei offener App")
        sync_now(B); downloads.clear(); sync_now(B)
        dev_dl = [d for d in downloads if d.startswith("/devices/")]
        ok(len(dev_dl) == 0, "zweiter Abgleich ohne Änderung lädt keine Geräte-Datei (geladen: %d)" % len(dev_dl))
        A.evaluate("window.__app.SYNC.pollMs=1000"); B.evaluate("window.__app.SYNC.pollMs=1000")
        eid3 = A.evaluate(ADD, {"date": "2026-10-08", "odo": 51000, "l": 40})
        A.evaluate("window.__app.syncNow(false)")
        try:
            B.wait_for_function("(id)=>!!S.entries.find(e=>e.id===id)", arg=eid3, timeout=25000); got=True
        except Exception: got=False
        ok(got, "Eintrag von A erscheint auf B ohne Eingriff (automatisches Nachsehen)")
        B.evaluate("window.__app.SYNC.pollMs=60000"); A.evaluate("window.__app.SYNC.pollMs=60000")

        print("6) Neuladen, Offline, Trennen")
        B.reload(); B.wait_for_selector("#main .top")
        B.wait_for_function("window.__app && window.__app.SYNC.cfg")
        ok(True, "Verbindung nach Neuladen noch da")
        B.evaluate("window.__app.SYNC.cfg.access=null")   # Token-Erneuerung testen
        sync_now(B)
        ok(B.evaluate("window.__app.SYNC.state") == "ok", "Abgleich nach Token-Erneuerung")
        online["v"] = False
        B.evaluate("window.__app.syncNow(false)")
        try:
            B.wait_for_function("window.__app.SYNC.state==='offline'", timeout=6000); off=True
        except Exception: off=False
        ok(off, "Offline erkannt, Zustand: " + B.evaluate("window.__app.SYNC.state"))
        online["v"] = True
        sync_now(B)
        B.click('[data-tab="home"]')
        ok(B.locator(".sync .dot").count() == 1 and "Dropbox aktuell" in B.locator(".sync").inner_text(), "Statusanzeige auf Startseite: " + B.locator(".sync").inner_text())
        B.screenshot(path=str(TMP / "home.png"))
        B.click('[data-tab="more"]'); B.screenshot(path=str(TMP / "more.png"), full_page=True)
        B.click('[data-act="sync-off"]')
        B.wait_for_function("!window.__app.SYNC.cfg")
        for _ in range(25):
            if any(l[0] == "revoke" for l in log): break
            B.wait_for_timeout(200)
        ok(any(l[0] == "revoke" for l in log), "Token beim Trennen widerrufen")
        ok(B.evaluate("S.entries.filter(e=>!e.deleted).length") >= 1, "Daten nach Trennen noch auf Gerät")

        print("7) Anmeldung mit Code (ohne Weiterleitung)")
        ctxC, C = new_device(br, "C")
        C.goto(BASE); C.wait_for_selector("#main .top"); C.click('[data-tab="more"]'); C.click('[data-act="sync-code"]')
        href = C.locator('a:has-text("Dropbox öffnen")').get_attribute("href")
        ok("redirect_uri" not in href, "Code-Anmeldung ohne redirect_uri")
        code = "CODE" + str(len(codes) + 1)
        # Dropbox-Seite simulieren: Autorisierung aufrufen
        pg2 = ctxC.new_page(); pg2.goto(href); shown = pg2.locator("b").inner_text(); pg2.close()
        C.fill("#dbx-code", shown); C.click('[data-act="sync-code-ok"]')
        C.wait_for_function("window.__app.SYNC.cfg", timeout=8000)
        ok(True, "Anmeldung per Code erfolgreich")
        sync_now(C)
        C.evaluate("demoOff()")
        sync_now(C)
        ok(C.evaluate("S.entries.filter(e=>!e.deleted).length") >= 1, "Gerät C hat nach Code-Anmeldung die Daten")

        print("8) Falscher state / Abbruch")
        D_ctx, D = new_device(br, "D")
        D.goto(BASE + "?code=X&state=falsch"); D.wait_for_selector("#main .top")
        ok(D.evaluate("window.__app.SYNC.cfg")==None, "falscher state wird abgelehnt")
        ok("?" not in D.evaluate("location.href"), "Adresse bereinigt")
        D.goto(BASE + "?error=access_denied"); D.wait_for_selector("#main .top")
        ok(D.evaluate("window.__app.SYNC.cfg")==None, "Abbruch-Antwort verarbeitet")

        print("9) PWA: Manifest, Service Worker, Offline, Sicherung")
        E_ctx, E = new_device(br, "E")
        E.goto(BASE); E.wait_for_selector("#main .top")
        E.wait_for_function("navigator.serviceWorker.ready.then(()=>true)", timeout=8000)
        E.reload(); E.wait_for_selector("#main .top")
        ok(E.evaluate("!!navigator.serviceWorker.controller"), "Service Worker aktiv und steuert die Seite")
        mf = E.evaluate("fetch(document.querySelector('link[rel=manifest]').href).then(r=>r.json())")
        ok(mf["start_url"] == "./" and mf["scope"] == "./", "Manifest mit relativem Start (Unterpfad-tauglich)")
        for ic in mf["icons"]:
            r = E.evaluate("(u)=>fetch(u).then(r=>r.status)", BASE + ic["src"])
            ok(r == 200, "Icon " + ic["src"])
        ok(E.evaluate("fetch(document.querySelector('link[rel=apple-touch-icon]').href).then(r=>r.status)") == 200, "apple-touch-icon erreichbar")
        E_ctx.set_offline(True)
        E.reload(); E.wait_for_selector("#main .top", timeout=8000)
        ok(True, "App startet offline aus dem Zwischenspeicher")
        E_ctx.set_offline(False)
        E.click('[data-tab="more"]')
        with E.expect_download() as dl:
            E.click('[data-act="export"]')
        d = dl.value
        path = d.path(); data = json.load(open(path))
        ok(data["app"] == "camper-repository" and "state" in data, "Sicherung wird als Datei geladen: " + d.suggested_filename)
        console_errs = [x for pg in (A, B, C, D, E) for x in pg.errs if "favicon" not in x and "Failed to load resource" not in x and "ERR_" not in x]
        ok(not console_errs, "keine JS-Fehler: " + "; ".join(console_errs[:3]))
        br.close()
finally:
    srv.terminate()
print("\nErgebnis:", "ALLES OK" if not fail else "%d FEHLER" % len(fail))
for f in fail: print(" -", f)
sys.exit(1 if fail else 0)
