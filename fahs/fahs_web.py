# -*- coding: utf-8 -*-
"""
لوحة التحكم ديال «فحص» فالمتصفح.
السيرفر كيخدم غير على 127.0.0.1 — حتى جهاز آخر ما يقدر يدخل ليه.
"""
import os
import re
import sys
import json
import glob
import time
import secrets
import datetime
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

F = None                      # الموديول fahs
TOKEN = secrets.token_urlsafe(24)
LOCK = threading.Lock()
JOB = {"running": False, "mode": None, "result": None, "error": None, "started": 0}
HERE = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(os.path.expanduser("~"), ".fahs", "history")
_adb_cache = {"t": 0}


# ───────────────────────── الفحص ─────────────────────────
def build_result(mode):
    sections = [s for s in F.EVENTS if s["title"] and s["title"] != "الخلاصة"]
    findings = []
    for sec in sections:
        for it in sec["items"]:
            if it["kind"] in ("bad", "warn"):
                findings.append(dict(it, section=sec["title"]))
    findings.sort(key=lambda x: 0 if x["kind"] == "bad" else 1)
    return {
        "mode": mode,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "score": F.score(),
        "counts": dict(F.COUNTS),
        "device": dict(F.DEVICE),
        "adb": F.ADB,
        "sections": sections,
        "findings": findings,
        "risky": [{"pkg": p, "why": w} for p, w in sorted(F.RISKY.items())],
    }


def save_history(res):
    try:
        os.makedirs(HIST_DIR, exist_ok=True)
        name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        with open(os.path.join(HIST_DIR, name), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        files = sorted(glob.glob(os.path.join(HIST_DIR, "*.json")))
        for old in files[:-40]:
            os.remove(old)
    except Exception:
        pass


def scan_worker(mode):
    try:
        F.reset_state()
        F.detect_adb()
        F.load_packages()
        F.load_uid_map()
        F.run_steps(mode)
        res = build_result(mode)
        F.save_report()
        if mode != "wifi":
            F.save_state(res["score"])
        save_history(res)
        JOB["result"] = res
    except Exception as e:
        JOB["error"] = str(e)
    finally:
        JOB["running"] = False


def start_scan(mode):
    with LOCK:
        if JOB["running"]:
            return False
        JOB.update(running=True, mode=mode, result=None, error=None, started=time.time())
    threading.Thread(target=scan_worker, args=(mode,), daemon=True).start()
    return True


def history(limit=40):
    out = []
    for path in sorted(glob.glob(os.path.join(HIST_DIR, "*.json")))[-limit:]:
        try:
            with open(path, encoding="utf-8") as f:
                r = json.load(f)
            out.append({"id": os.path.basename(path)[:-5], "date": r.get("date"),
                        "score": r.get("score"), "mode": r.get("mode"),
                        "counts": r.get("counts")})
        except Exception:
            continue
    return out[::-1]


def history_item(hid):
    if not re.fullmatch(r"\d{8}_\d{6}", hid or ""):
        return None
    try:
        with open(os.path.join(HIST_DIR, hid + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ───────────────────────── ADB ─────────────────────────
def adb_status(force=False):
    if force or time.time() - _adb_cache["t"] > 5:
        if not JOB["running"]:
            F.detect_adb()
        _adb_cache["t"] = time.time()
    return F.ADB


SCREENS = {
    "about": ("android.settings.DEVICE_INFO_SETTINGS",),
    "dev": ("com.android.settings/.Settings$WirelessDebuggingActivity",
            "android.settings.APPLICATION_DEVELOPMENT_SETTINGS"),
    "devonly": ("android.settings.APPLICATION_DEVELOPMENT_SETTINGS",),
    "apps": ("android.settings.MANAGE_APPLICATIONS_SETTINGS",),
}


def open_screen(name):
    intents = SCREENS.get(name)
    if not intents:
        return False
    if F.ADB:  # ADB يقدر يحل الصفحات حتى من الخلفية
        for it in intents:
            flag = "-n" if "/" in it else "-a"
            out = F.sh(f"am start {flag} '{it}'", 10)
            if out and "Error" not in out:
                return True
    return F.open_screen(*intents)


def adb_pair(port, code):
    port, code = str(port).strip(), re.sub(r"\D", "", str(code))
    if not port.isdigit() or len(code) != 6:
        return {"ok": False, "msg": "البورت ولا الرمز غالط (الرمز 6 أرقام)"}
    out = F.run(f"adb pair localhost:{port} {code} 2>&1", 20)
    if "Successfully" not in out:
        return {"ok": False, "msg": "الإقران ما نجحش. تأكد من الرمز وخلي النافذة مفتوحة.",
                "detail": out[-200:]}
    time.sleep(1)
    for p in sorted((F.adbd_ports() or set()) - {int(port)}) or [5555]:
        F.run(f"adb connect localhost:{p} 2>&1", 8)
    F.detect_adb()
    if F.ADB:
        return {"ok": True, "adb": F.ADB}
    return {"ok": False, "paired": True,
            "msg": "الإقران نجح ولكن الاتصال لا. كتب البورت لي فوق فصفحة «تصحيح الأخطاء اللاسلكي»."}


def adb_connect(port=None):
    if port:
        F.run(f"adb connect localhost:{int(port)} 2>&1", 8)
    F.detect_adb()
    return {"ok": bool(F.ADB), "adb": F.ADB}


def adb_off():
    if not F.ADB:
        return {"ok": False, "msg": "ADB ما متصلش"}
    serial = F.ADB

    def later():
        time.sleep(1)
        F.run(f"adb -s {serial} shell settings put global adb_wifi_enabled 0", 5)
        F.run(f"adb -s {serial} shell settings put global adb_enabled 0", 5)
        F.ADB = None
    threading.Thread(target=later, daemon=True).start()
    return {"ok": True}


def install_adb():
    if F.shutil.which("adb"):
        return {"ok": True}
    F.run("pkg install -y android-tools 2>&1", 300)
    return {"ok": bool(F.shutil.which("adb"))}


def uninstall(pkg):
    if not re.fullmatch(r"[A-Za-z0-9_.]+", pkg or ""):
        return {"ok": False}
    F.sh(f"am start -a android.intent.action.DELETE -d package:{pkg}", 10)
    return {"ok": True}


def fix_background():
    """كنمنعو Android يقتل Termux (Phantom Process Killer). محتاج ADB."""
    if not F.ADB:
        return {"ok": False, "msg": "خاص ADB يكون متصل باش ندير هادشي"}
    F.sh("/system/bin/device_config set_sync_disabled_for_tests persistent", 10)
    F.sh("/system/bin/device_config put activity_manager max_phantom_processes 2147483647", 10)
    F.sh("settings put global settings_enable_monitor_phantom_procs false", 10)
    # نحيدو Termux من تحسين البطارية
    F.sh("dumpsys deviceidle whitelist +com.termux", 10)
    F.sh("cmd appops set com.termux RUN_ANY_IN_BACKGROUND allow", 10)
    return {"ok": True}


def pw_check(password):
    """فحص كلمة سر بـ k-anonymity. كلمة السر ما كتتسجل ولا كتخرج كاملة."""
    if not password:
        return {"ok": False}
    n = F.pwned_password(password)
    level, notes = F.password_strength(password)
    return {"ok": True, "count": n, "level": level, "notes": notes,
            "online": n >= 0}


def email_check(email, api_key):
    email = (email or "").strip()
    if "@" not in email:
        return {"ok": False, "msg": "البريد غالط"}
    if not (api_key or "").strip():
        return {"ok": False, "need_key": True}
    r = F.pwned_email(email, api_key.strip())
    if not r.get("ok"):
        return r
    out = []
    for b in r["breaches"]:
        out.append({"name": b.get("Title") or b.get("Name"),
                    "date": b.get("BreachDate", ""),
                    "data": b.get("DataClasses", [])[:8]})
    out.sort(key=lambda x: x["date"], reverse=True)
    return {"ok": True, "breaches": out}


def gen_pw(length, symbols, pron):
    length = max(8, min(64, int(length or 18)))
    return {"ok": True, "pw": F.gen_password(length, bool(symbols), bool(pron))}


def audio_state():
    st = F.audio_status()
    out = {"adb": st["adb"], "streams": [], "bt": st.get("bt")}
    for s in (st["termux"] or []):
        out["streams"].append({"name": F.AUDIO_STREAMS.get(s["stream"], s["stream"]),
                               "key": s["stream"], "vol": s["volume"], "max": s["max_volume"]})
    out["mono"] = st.get("mono") == "1"
    return out


def audio_action(name):
    if name == "max":
        return F.audio_max()
    if name == "bt":
        return F.audio_bt_fix(True)
    if name == "center":
        return F.audio_balance_center()
    if name == "mono_on":
        return F.audio_mono(True)
    if name == "stereo":
        F.audio_mono(False)
        return F.audio_balance_center()
    return {"ok": False}


def status():
    return {
        "version": F.VERSION,
        "adb": adb_status(),
        "adb_installed": bool(F.shutil.which("adb")),
        "ports_readable": F.adbd_ports() is not None,
        "device": {"brand": F.prop("ro.product.brand"),
                   "model": F.prop("ro.product.model"),
                   "android": F.prop("ro.build.version.release")},
        "last": (history(1) or [None])[0],
    }


def job_state():
    st = {"running": JOB["running"], "mode": JOB["mode"], "error": JOB["error"],
          "step": F.STEP.get("i", 0), "total": F.STEP.get("total", 0),
          "title": F.STEP.get("title", ""),
          "elapsed": int(time.time() - JOB["started"]) if JOB["started"] else 0}
    if not JOB["running"] and JOB["result"]:
        st["result"] = JOB["result"]
    return st


# ───────────────────────── HTTP ─────────────────────────
def page():
    for path in (os.path.join(HERE, "fahs_web.html"),
                 os.path.join(F.PREFIX, "share", "fahs", "fahs_web.html")):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read().replace("__FAHS_TOKEN__", TOKEN)
    return "<h1>fahs_web.html missing — reinstall fahs</h1>"


class Handler(BaseHTTPRequestHandler):
    server_version = "fahs"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _authed(self):
        return secrets.compare_digest(self.headers.get("X-Fahs-Token", ""), TOKEN)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain")
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, page(), "text/html; charset=utf-8")
        if not self._authed():
            return self._json({"error": "token"}, 403)
        if path == "/api/status":
            return self._json(status())
        if path == "/api/job":
            return self._json(job_state())
        if path == "/api/history":
            return self._json(history())
        if path.startswith("/api/history/"):
            item = history_item(path.rsplit("/", 1)[1])
            return self._json(item or {"error": "not found"}, 200 if item else 404)
        if path == "/api/adb/ports":
            p = F.adbd_ports()
            return self._json({"ports": sorted(p) if p is not None else None})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._host_ok() or not self._authed():
            return self._json({"error": "forbidden"}, 403)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            body = {}
        path = self.path.split("?")[0]
        if path == "/api/scan":
            mode = body.get("mode", "full")
            if mode not in F.STEPS:
                return self._json({"ok": False}, 400)
            return self._json({"ok": start_scan(mode)})
        if path == "/api/open":
            return self._json({"ok": open_screen(body.get("screen", ""))})
        if path == "/api/uninstall":
            return self._json(uninstall(body.get("pkg", "")))
        if path == "/api/adb/install":
            return self._json(install_adb())
        if path == "/api/adb/connect":
            return self._json(adb_connect(body.get("port")))
        if path == "/api/adb/pair":
            return self._json(adb_pair(body.get("port", ""), body.get("code", "")))
        if path == "/api/fix-bg":
            return self._json(fix_background())
        if path == "/api/adb/off":
            return self._json(adb_off())
        if path == "/api/pw-check":
            return self._json(pw_check(body.get("password", "")))
        if path == "/api/email-check":
            return self._json(email_check(body.get("email", ""), body.get("key", "")))
        if path == "/api/gen-pw":
            return self._json(gen_pw(body.get("length", 18),
                                     body.get("symbols", True), body.get("pron", False)))
        if path == "/api/audio":
            return self._json(audio_state())
        if path == "/api/audio/do":
            return self._json(audio_action(body.get("action", "")))
        self._json({"error": "not found"}, 404)


def serve(fahs_module):
    global F
    F = fahs_module
    F.WEB = True
    srv = None
    for port in range(8080, 8091):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if not srv:
        print("ما لقيتش بورت خاوي بين 8080 و 8090")
        return
    url = f"http://localhost:{srv.server_address[1]}/"
    ar = F._ar
    print()
    print(f"  {F.G}{ar('✅ لوحة التحكم خدامة')}{F.N}")
    print(f"  {F.BOLD}{F.W}{url}{F.N}")
    print(f"  {F.D}{ar('حل هاد الرابط فالمتصفح. باش توقفها: Ctrl + C')}{F.N}")
    print(f"  {F.D}{ar('خلي Termux محلول فالخلفية ملي كتستعمل الموقع.')}{F.N}")
    # كنمنعو التيليفون ينعس Termux ملي يكون فالخلفية
    if F.shutil.which("termux-wake-lock"):
        F.run("termux-wake-lock", 5)
    if F.ADB or (F.detect_adb() or F.ADB):
        fix_background()
    if F.shutil.which("termux-open-url") and "--no-open" not in sys.argv:
        F.run(f"termux-open-url {url}", 5)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  " + ar("تسدات لوحة التحكم."))
    finally:
        srv.server_close()
        if F.shutil.which("termux-wake-unlock"):
            F.run("termux-wake-unlock", 5)
