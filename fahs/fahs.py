#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فحص — أداة كتفحص التيليفون من Termux (بلا root)
كتشوف: root، ADB، التطبيقات المشبوهة، الشبكة، الملفات، Termux راسو، وصحة الجهاز.
"""
import os
import re
import sys
import json
import shutil
import datetime
import textwrap
import shlex
import subprocess

VERSION = "2.0"

# ───────────────────────── العربية ─────────────────────────
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def _ar(t):
        return get_display(arabic_reshaper.reshape(t), base_dir="R")
except Exception:  # إلا ما كانتش المكتبات، كنطبعو النص كيف ما هو
    def _ar(t):
        return t

R, G, Y, B, C, W, D, BOLD, N = (
    "\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[96m",
    "\033[97m", "\033[2m", "\033[1m", "\033[0m",
)
if not sys.stdout.isatty() or "--no-color" in sys.argv:
    R = G = Y = B = C = W = D = BOLD = N = ""

WIDTH = max(30, min(shutil.get_terminal_size((45, 20)).columns, 70))

REPORT = []          # النص العادي ديال التقرير (باش يتحفظ فملف)
FINDINGS = []        # (مستوى, نص, نصيحة)
COUNTS = {"ok": 0, "warn": 0, "bad": 0}
RISKY = {}           # تطبيق ← السبب (باش نقترحو المسح فاللخر)


def flag(pkg, why):
    RISKY.setdefault(pkg, why)
ICONS = {"ok": "🟢", "warn": "🟡", "bad": "🔴", "info": "🔵", "sub": "  •"}
COLORS = {"ok": G, "warn": Y, "bad": R, "info": C, "sub": W}


def show(text, kind="info"):
    """كنطبع سطر عربي مقسوم على عرض الشاشة باش ما يتقلبش."""
    icon = ICONS[kind]
    color = COLORS[kind]
    REPORT.append(f"{icon} {text}")
    lines = textwrap.wrap(text, WIDTH - 5) or [""]
    for i, line in enumerate(lines):
        visual = _ar(line)
        mark = icon if i == 0 else "  "
        if kind == "sub":
            mark = "•  " if i == 0 else "   "
        pad = max(0, WIDTH - 1 - len(visual) - 3)
        # محاذاة لليمين بحال الكتابة العربية
        print(f"{color}{' ' * pad}{visual} {mark}{N}")


def ok(text):
    COUNTS["ok"] += 1
    show(text, "ok")


def warn(text, advice=""):
    COUNTS["warn"] += 1
    FINDINGS.append(("warn", text, advice))
    show(text, "warn")


def bad(text, advice=""):
    COUNTS["bad"] += 1
    FINDINGS.append(("bad", text, advice))
    show(text, "bad")


def info(text):
    show(text, "info")


def sub(text):
    show(text, "sub")


STEP = {"i": 0, "total": 0}


def rline(text, color=""):
    """سطر عربي محاذي لليمين."""
    v = _ar(text)
    print(f"{color}{' ' * max(0, WIDTH - 2 - len(v))}{v}{N}")


def header(title):
    title = re.sub(r"^\d+\.\s*", "", title)
    REPORT.append("")
    REPORT.append(f"=== {title} ===")
    print()
    if STEP["total"] and title != "الخلاصة":
        STEP["i"] += 1
        i, t = STEP["i"], STEP["total"]
        bar_w = 12
        done = round(bar_w * i / t)
        bar = f"{G}{'▰' * done}{D}{'▱' * (bar_w - done)}{N}"
        label = f" {i}/{t}"
    else:
        bar, label = "", ""
    inner = WIDTH - 3
    print(f"{B}╭{'─' * inner}╮{N}")
    v = _ar(title)
    print(f"{B}│{N}{' ' * max(1, inner - 1 - len(v))}{BOLD}{W}{v}{N} {B}│{N}")
    if bar:
        print(f"{B}│{N} {bar}{D}{label}{N}{' ' * max(0, inner - 13 - len(label))}{B}│{N}")
    print(f"{B}╰{'─' * inner}╯{N}")


# ───────────────────────── أدوات ─────────────────────────
def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout.strip()
    except Exception:
        return ""


ADB = None  # serial ديال الجهاز إلا كان ADB متصل


def detect_adb():
    """كنقلبو على ADB متصل بالتيليفون راسو (localhost)."""
    global ADB
    if "--no-adb" in sys.argv or not shutil.which("adb"):
        return
    out = run("adb devices 2>/dev/null", 10)
    devs = [l.split()[0] for l in out.splitlines()[1:]
            if l.strip().endswith("device")]
    local = [d for d in devs if d.startswith(("localhost", "127.0.0.1"))]
    pick = (local or [d for d in devs if d.startswith("emulator-")] or devs[:1])
    if pick:
        test = run(f"adb -s {pick[0]} shell echo ok 2>/dev/null", 10)
        if test == "ok":
            ADB = pick[0]


def sh(cmd, timeout=20):
    """كنشغلو الأمر عبر ADB (صلاحيات أكبر) إلا كان متصل، ولا عادي."""
    if ADB:
        return run(f"adb -s {ADB} shell {shlex.quote(cmd)}", timeout + 10)
    return run(cmd, timeout)


def prop(name):
    return sh(f"getprop {name}", 5)


_settings_ok = None


def setting(ns, key):
    """كنقراو إعدادات Android. كترجع None إلا ما قدرناش."""
    global _settings_ok
    if _settings_ok is False:
        return None
    v = sh(f"settings get {ns} {key} 2>/dev/null", 10)
    low = v.lower()
    if (not v or "xception" in v or "not found" in low or "failure" in low
            or "failed" in low or low.startswith("cmd:") or "error" in low):
        if _settings_ok is None:
            _settings_ok = False
        return None
    _settings_ok = True
    return None if v == "null" else v


def read_net(path):
    """/proc/net عبر ADB كيبين الاتصالات ديال كاع التطبيقات."""
    if ADB:
        out = sh(f"cat {path} 2>/dev/null", 10)
        if out:
            return out
    return read(path)


def read(path):
    try:
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


HOME = os.path.expanduser("~")
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
MY_UID = os.getuid()

# ───────────────────────── قوائم ─────────────────────────
# تطبيقات خبيثة معروفة بالاسم بالضبط
KNOWN_BAD = {
    "com.metasploit.stage": "Metasploit (باب خلفي للتحكم فالتيليفون)",
    "ahmyth.mine.king.ahmyth": "AhMyth RAT (برنامج تجسس)",
    "com.etechd.l3mon": "L3MON RAT (برنامج تجسس)",
}
# أسماء شركات تطبيقات التجسس المعروفة (stalkerware)
STALKER_WORDS = [
    "mspy", "flexispy", "hoverwatch", "truthspy", "cocospy", "spyic",
    "xnspy", "spyzie", "ikeymonitor", "spyhuman", "highster", "mobistealth",
    "ispyoo", "spyera", "fonemonitor", "minspy", "neatspy", "clevguard",
    "kidsguard", "spybubble", "copy9", "talklog", "thetruthspy", "mobiletracker",
    "spymaster", "eyezy", "umobix", "spapp", "androrat", "spynote", "cellspy",
]
# كلمات عامة كتستاهل نراجعوها
SUSPECT_WORDS = ["spy", "keylog", "stalk", "monitor", "hidden", "tracker",
                 "rat.", ".rat", "backdoor", "payload"]
# تطبيقات مخدّمة بالمودات / مخترقة — غالباً فيهم برامج خبيثة
MOD_STORES = {"com.happymod.apk": "HappyMod", "com.apkpure.aegon": "APKPure",
              "com.lulubox": "LuluBox", "com.blackmod": "BlackMod",
              "com.ac.market.store": "AC Market", "com.mobilism": "Mobilism"}
# تطبيقات الشركة لي صنعات التيليفون (ماشي خطيرين)
OEM_PREFIXES = ("com.coloros.", "com.oplus.", "com.heytap.", "andes.oplus.",
                "com.realme.", "com.oppo.", "com.nearme.", "com.miui.",
                "com.xiaomi.", "com.mi.", "com.samsung.", "com.sec.",
                "com.huawei.", "com.hihonor.", "com.vivo.", "com.bbk.",
                "com.transsion.", "com.android.", "com.google.android.",
                "org.chromium.webapk.", "com.facebook.aura",
                "com.facebook.appmanager", "com.facebook.system",
                "com.facebook.services", "com.amazon.appmanager")


def is_oem(p):
    return p.startswith(OEM_PREFIXES)
# تطبيقات root
ROOT_APPS = {
    "com.topjohnwu.magisk": "Magisk",
    "eu.chainfire.supersu": "SuperSU",
    "me.weishu.kernelsu": "KernelSU",
    "io.github.huskydg.magisk": "Magisk Delta",
    "com.kingroot.kinguser": "KingRoot",
    "com.kingo.root": "KingoRoot",
    "com.noshufou.android.su": "Superuser",
    "io.github.vvb2060.magisk": "Magisk Alpha",
}
# المتاجر الموثوقة
TRUSTED_INSTALLERS = {
    "com.android.vending", "com.google.android.feedback",
    "com.sec.android.app.samsungapps", "com.huawei.appmarket",
    "com.xiaomi.market", "com.xiaomi.mipicks", "com.heytap.market",
    "com.oppo.market", "com.bbk.appstore", "com.amazon.venezia",
    "org.fdroid.fdroid", "com.aurora.store", "com.transsion.appstore",
    "com.android.chrome", "com.google.android.packageinstaller.preload",
    "com.oneplus.market", "com.vivo.appstore", "com.hihonor.appmarket",
}

# ───────────────────────── 1. معلومات الجهاز ─────────────────────────
DEVICE = {}


def check_device():
    header("1. معلومات الجهاز")
    brand = prop("ro.product.brand")
    model = prop("ro.product.model")
    release = prop("ro.build.version.release")
    patch = prop("ro.build.version.security_patch")
    DEVICE.update(brand=brand, model=model, release=release)

    if not model and not release:
        warn("ما قدرتش نقرا معلومات الجهاز. واش كتخدم من Termux على Android؟")
        return

    info(f"الجهاز: {brand} {model}")
    info(f"نسخة Android: {release}")

    if patch:
        try:
            d = datetime.date.fromisoformat(patch)
            months = (datetime.date.today() - d).days // 30
            if months > 12:
                bad(f"آخر تحديث أمني: {patch} (قديم بزاف، {months} شهر)",
                    "دير تحديث للنظام من الإعدادات. التيليفون بلا تحديثات أمنية سهل يتهكر.")
            elif months > 6:
                warn(f"آخر تحديث أمني: {patch} ({months} شهر)",
                     "شوف واش كاين تحديث فالإعدادات ← تحديث النظام.")
            else:
                ok(f"آخر تحديث أمني: {patch}")
        except ValueError:
            info(f"آخر تحديث أمني: {patch}")

    up = read("/proc/uptime")
    if up:
        hours = int(float(up.split()[0]) // 3600)
        info(f"التيليفون شاعل هادي {hours // 24} يوم و {hours % 24} ساعة")


# ───────────────────────── 2. root والنظام ─────────────────────────
PACKAGES = {}  # name -> {"uid": .., "installer": ..}


def load_packages():
    out = sh("pm list packages -3 -i -U 2>/dev/null", 40)
    for line in out.splitlines():
        m = re.search(r"package:(\S+)", line)
        if not m:
            continue
        name = m.group(1)
        inst = re.search(r"installer=(\S+)", line)
        uid = re.search(r"uid:(\d+)", line)
        PACKAGES[name] = {
            "installer": inst.group(1) if inst else "null",
            "uid": int(uid.group(1)) if uid else None,
        }


UID_MAP = {}


def load_uid_map():
    out = sh("pm list packages -U 2>/dev/null", 40)
    for line in out.splitlines():
        m = re.search(r"package:(\S+)\s+uid:(\d+)", line)
        if m:
            UID_MAP.setdefault(int(m.group(2)), []).append(m.group(1))


def check_root():
    header("2. Root والحماية ديال النظام")
    found = False

    su_paths = ["/system/bin/su", "/system/xbin/su", "/sbin/su",
                "/system/sbin/su", "/vendor/bin/su", "/su/bin/su",
                "/data/local/su", "/data/local/bin/su", "/data/local/xbin/su",
                "/system/app/Superuser.apk", "/sbin/.magisk", "/debug_ramdisk/su"]
    hits = [p for p in su_paths if os.path.exists(p)]
    if hits:
        found = True
        bad("لقيت ملفات ديال root فالنظام:",
            "إلا ما درتيش root بيدك، شي حد آخر دارو. خصك تدير Factory Reset.")
        for h in hits:
            sub(h)

    root_apps = [f"{ROOT_APPS[p]} ({p})" for p in PACKAGES if p in ROOT_APPS]
    if root_apps:
        found = True
        bad("لقيت تطبيقات ديال root:",
            "إلا ما نتا لي نصبتيهم، هادا مؤشر خطير.")
        for a in root_apps:
            sub(a)

    tags = prop("ro.build.tags")
    if "test-keys" in tags:
        found = True
        warn("النظام موقّع بمفاتيح تجريبية (test-keys) — غالباً ROM معدّل",
             "النظام الرسمي كيكون release-keys. إلا شريتيه هكا، سول البائع.")
    if prop("ro.debuggable") == "1":
        found = True
        warn("النظام فيه وضع debuggable شاعل (ro.debuggable=1)",
             "هادشي ما كيكونش فالنظام الرسمي العادي.")
    if prop("ro.secure") == "0":
        found = True
        bad("الحماية ديال النظام طافية (ro.secure=0)",
            "هادشي خطير بزاف. ردّ النظام الرسمي.")

    if not found:
        ok("ما لقيت حتى علامة ديال root")

    vb = prop("ro.boot.verifiedbootstate")
    locked = prop("ro.boot.flash.locked")
    if vb == "green":
        ok("الـ Bootloader مسدود والنظام أصلي (Verified Boot)")
    elif vb == "orange" or locked == "0":
        bad("الـ Bootloader محلول (unlocked)",
            "أي واحد شد التيليفون يقدر يبدل النظام. إلا ما نتا لي حليتيه، خطير.")
    elif vb == "yellow":
        warn("الـ Verified Boot فحالة yellow (نظام بمفتاح خاص)",
             "تأكد أن النظام لي فالتيليفون رسمي.")
    elif vb:
        info(f"حالة Verified Boot: {vb}")

    se = sh("getenforce 2>/dev/null", 5)
    if se == "Enforcing":
        ok("SELinux خدام (Enforcing)")
    elif se == "Permissive":
        bad("SELinux طافي (Permissive) — النظام بلا حماية",
            "هادشي كيوقع غير فالـ ROM المعدّلة ولا ملي يكون الجهاز مخترق.")


# ───────────────────────── 3. ADB ─────────────────────────
def listening_ports():
    """البورتات لي فحالة LISTEN، ولا None إلا ما قدرناش نقراو."""
    ports, ok_read = set(), False
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        data = read_net(f)
        if not data:
            continue
        ok_read = True
        for line in data.splitlines()[1:]:
            parts = line.split()
            if len(parts) > 3 and parts[3] == "0A":
                ports.add(int(parts[1].split(":")[1], 16))
    return ports if ok_read else None


def check_adb():
    header("3. وضع المطور و ADB")
    any_read = False

    dev = setting("global", "development_settings_enabled")
    adb = setting("global", "adb_enabled")
    adb_wifi = setting("global", "adb_wifi_enabled")
    tcp = prop("service.adb.tcp.port") or prop("persist.adb.tcp.port")
    adbd = prop("init.svc.adbd")

    if dev is not None or adb is not None:
        any_read = True

    if tcp and tcp not in ("-1", "0"):
        ports = listening_ports()
        try:
            tport = int(tcp)
        except ValueError:
            tport = -1
        if ports is not None and tport in ports:
            (warn if ADB else bad)(
                f"ADB عبر الشبكة شاعل ومفتوح دابا على البورت {tcp}!",
                "أي واحد معاك فنفس الويفي يقدر يتحكم فالتيليفون. ملي تسالي الفحص طفي «تصحيح الأخطاء اللاسلكي»، ولا طفي التيليفون وشعلو باش يتسد.")
        elif ports is not None:
            info(f"ADB عبر الشبكة مضبوط على البورت {tcp} ولكن ما مفتوحش دابا")
        else:
            warn(f"ADB عبر الشبكة مضبوط على البورت {tcp}",
                 "إلا ما نتا لي شعلتيه، طفي التيليفون وشعلو باش يتسد.")
    if adb_wifi == "1":
        warn("Wireless Debugging شاعل",
             "طفيه من خيارات المطور إلا ما كتستعملوش.")
    if adb == "1" or adbd == "running":
        warn("USB Debugging شاعل",
             "طفيه من الإعدادات ← خيارات المطور. إلا تشرّج التيليفون فشي بلاصة عامة يقدر يتخترق.")
    elif adb == "0":
        ok("USB Debugging طافي")

    if dev == "1":
        info("خيارات المطور (Developer options) مفعلة")
    elif dev == "0":
        ok("خيارات المطور طافية")

    if not any_read and not adbd:
        info("ما قدرتش نقرا إعدادات ADB من Termux فهاد الجهاز")


# ───────────────────────── 4. التطبيقات ─────────────────────────
def check_apps():
    header("4. التطبيقات")
    if not PACKAGES:
        warn("ما قدرتش نقرا لائحة التطبيقات (الأمر pm ما خدمش)",
             "شوف التطبيقات يدوياً فالإعدادات ← التطبيقات.")
        return

    info(f"عدد التطبيقات لي نصبتي: {len(PACKAGES)}")

    clean = True
    for p in PACKAGES:
        if p in KNOWN_BAD:
            clean = False
            flag(p, KNOWN_BAD[p])
            bad(f"تطبيق خبيث معروف: {p}",
                f"{KNOWN_BAD[p]}. مسحو دابا، وبدّل كلمات السر من جهاز آخر.")

    stalk = [p for p in PACKAGES if p not in KNOWN_BAD
             and any(w in p.lower() for w in STALKER_WORDS)]
    if stalk:
        clean = False
        bad("لقيت تطبيقات تجسس معروفة (Stalkerware):",
            "هاد التطبيقات كيقراو الرسائل والمكالمات والموقع. مسحهم وبدّل كلمات السر.")
        for p in stalk:
            flag(p, "تطبيق تجسس")
            sub(p)

    sus = [p for p in PACKAGES if p not in stalk and p not in KNOWN_BAD
           and any(w in p.lower() for w in SUSPECT_WORDS)]
    if sus:
        clean = False
        warn("تطبيقات سميتهم مشبوهة — راجعهم:",
             "يقدر يكونو عاديين (بحال تطبيق مراقبة البطارية)، ولكن تأكد منهم.")
        for p in sus:
            flag(p, "سمية مشبوهة")
            sub(p)

    mods = [f"{MOD_STORES[p]} ({p})" for p in PACKAGES if p in MOD_STORES]
    for p in PACKAGES:
        if p in MOD_STORES:
            flag(p, "متجر تطبيقات مهكرة")
    if mods:
        clean = False
        warn("عندك متجر ديال التطبيقات المهكرة (مودات):",
             "التطبيقات المهكرة من هاد المتاجر بزاف منهم فيهم برامج خبيثة. "
             "مسح المتجر، والتطبيقات لي نصبتي منو إلا ما محتاجهمش.")
        for m in mods:
            sub(m)

    side = [p for p, d in PACKAGES.items()
            if d["installer"] not in TRUSTED_INSTALLERS
            and not p.startswith("com.termux") and not is_oem(p)]
    if side:
        warn(f"{len(side)} تطبيق منصّب من برا المتجر (APK):",
             "التطبيقات من برا Play Store هوما الطريق الأول للاختراق. مسح لي ما عارفوش.")
        for p in sorted(side)[:20]:
            sub(p)
        if len(side) > 20:
            print(f"{D}{_ar(f'... و {len(side) - 20} آخرين (شوف التقرير)')}{N}")
            for p in sorted(side)[20:]:
                REPORT.append(f"  • {p}")
    else:
        ok("كاع التطبيقات جاية من متجر موثوق")

    if clean:
        ok("ما لقيت حتى تطبيق تجسس معروف")

    # Accessibility — أخطر صلاحية
    acc = setting("secure", "enabled_accessibility_services")
    if acc:
        pkgs = sorted({c.split("/")[0] for c in acc.split(":") if c})
        third = [p for p in pkgs if p in PACKAGES]
        if third:
            warn("تطبيقات عندهم صلاحية «إمكانية الوصول» (Accessibility):",
                 "هاد الصلاحية كتخلي التطبيق يشوف كلشي فالشاشة ويكتب بلاصتك. "
                 "إلا ما عارفش علاش محتاجها، حيدها من الإعدادات ← إمكانية الوصول.")
            for p in third:
                sub(p)
        else:
            ok("حتى تطبيق خارجي ما عندو صلاحية Accessibility")
    elif acc is None and _settings_ok:
        ok("حتى تطبيق ما عندو صلاحية Accessibility")

    notif = setting("secure", "enabled_notification_listeners")
    if notif:
        pkgs = sorted({c.split("/")[0] for c in notif.split(":") if c})
        third = [p for p in pkgs if p in PACKAGES]
        if third:
            info("تطبيقات كيقراو الإشعارات ديالك (فيهم الرسائل والأكواد):")
            for p in third:
                sub(p)
            for p in third:
                if p in side:
                    warn(f"{p} منصّب من برا وكيقرا الإشعارات",
                         "هادا يقدر يسرق أكواد التحقق (OTP). تأكد منو.")

    admin = sh("dumpsys device_policy 2>/dev/null", 20)
    if admin and "Permission Denial" not in admin:
        admins = sorted(set(re.findall(r"ComponentInfo\{([^/}]+)/", admin)))
        third = [a for a in admins if a in PACKAGES]
        if third:
            warn("تطبيقات عندهم صلاحية «مسؤول الجهاز» (Device admin):",
                 "هاد الصلاحية كتمنع مسح التطبيق. حيدها من الإعدادات ← الأمان.")
            for a in third:
                sub(a)


# ───────────────────────── الصلاحيات والتطبيقات المخبية ─────────────────────────
PERMS = {
    "android.permission.READ_SMS": "الرسائل",
    "android.permission.RECEIVE_SMS": "الرسائل",
    "android.permission.SEND_SMS": "صيفط رسائل",
    "android.permission.READ_CALL_LOG": "سجل المكالمات",
    "android.permission.RECORD_AUDIO": "الميكرو",
    "android.permission.CAMERA": "الكاميرا",
    "android.permission.ACCESS_FINE_LOCATION": "الموقع",
    "android.permission.ACCESS_BACKGROUND_LOCATION": "الموقع فالخلفية",
    "android.permission.READ_CONTACTS": "جهات الاتصال",
}
SENSITIVE = {"الرسائل", "صيفط رسائل", "سجل المكالمات", "الموقع فالخلفية"}


def parse_dumpsys_packages():
    """كنقراو الصلاحيات وتاريخ التنصيب ديال كاع التطبيقات فمرة وحدة."""
    out = sh("dumpsys package packages 2>/dev/null", 90)
    data, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"\s*Package \[([^\]]+)\]", line)
        if m:
            cur = data.setdefault(m.group(1), {"perms": set(), "installed": None})
            continue
        if not cur:
            continue
        m = re.search(r"firstInstallTime=(\d{4}-\d\d-\d\d)", line)
        if m and not cur["installed"]:
            cur["installed"] = m.group(1)
            continue
        m = re.match(r"\s*(android\.permission\.[A-Z_]+): granted=true", line)
        if m and m.group(1) in PERMS:
            cur["perms"].add(PERMS[m.group(1)])
    return data


def third_party_user_apps():
    return [p for p in PACKAGES if not is_oem(p) and not p.startswith("com.termux")]


def check_permissions():
    header("الصلاحيات الخطيرة")
    if not ADB:
        info("هاد الفحص محتاج وضع ADB (شوف: fahs --help)")
        return
    data = parse_dumpsys_packages()
    if not data:
        info("ما قدرتش نقرا الصلاحيات")
        return
    PKG_INFO.update(data)
    apps = third_party_user_apps()
    side = {p for p in apps if PACKAGES[p]["installer"] not in TRUSTED_INSTALLERS}

    rows = []
    for p in apps:
        perms = data.get(p, {}).get("perms", set())
        if not perms:
            continue
        risk = len(perms) + 3 * len(perms & SENSITIVE) + (3 if p in side else 0)
        rows.append((risk, p, perms))
    rows.sort(reverse=True)

    danger = [(p, perms) for r, p, perms in rows
              if p in side and (perms & SENSITIVE
                                or {"الميكرو", "الكاميرا", "الموقع"} <= perms)]
    if danger:
        warn("تطبيقات من برا المتجر وعندهم صلاحيات خطيرة:",
             "تطبيق APK عندو الرسائل ولا الميكرو والكاميرا والموقع بجوج يقدر يتجسس عليك. "
             "إلا ما محتاجش الصلاحية، حيدها: الإعدادات ← التطبيقات ← الصلاحيات.")
        for p, perms in danger:
            flag(p, "صلاحيات خطيرة")
            sub(f"{p}: {'، '.join(sorted(perms))}")
    else:
        ok("حتى تطبيق من برا المتجر ما عندو صلاحيات خطيرة")

    top = rows[:6]
    if top:
        info("التطبيقات لي عندهم أكثر صلاحيات:")
        for r, p, perms in top:
            sub(f"{p}: {'، '.join(sorted(perms))}")

    # التطبيقات المخبية (بلا أيقونة)
    out = sh("cmd package query-activities --brief -a android.intent.action.MAIN "
             "-c android.intent.category.LAUNCHER 2>/dev/null", 30)
    launch = set(re.findall(r"^\s*([a-zA-Z0-9_.]+)/", out, re.M))
    if launch:
        hidden = [p for p in apps if p not in launch]
        if hidden:
            warn(f"{len(hidden)} تطبيق ما عندهمش أيقونة (مخبيين):",
                 "تطبيقات التجسس كتخبي الأيقونة ديالها. شي وحدين عاديين (كيبورد، إضافات)، "
                 "ولكن إلا لقيتي شي واحد ما عارفوش، مسحو.")
            for p in hidden:
                flag(p, "تطبيق مخبي")
                sub(p)
        else:
            ok("كاع التطبيقات عندهم أيقونة (حتى واحد ما مخبي)")

    # التطبيقات الجداد
    week = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    new = sorted((data[p]["installed"], p) for p in apps
                 if data.get(p, {}).get("installed") and data[p]["installed"] >= week)
    if new:
        info("تطبيقات تنصبو فهاد السيمانة:")
        for d, p in new:
            sub(f"{p} ({d})")


PKG_INFO = {}
STATE_DIR = os.path.join(HOME, ".fahs")
STATE = os.path.join(STATE_DIR, "last.json")


def check_changes():
    header("شنو تبدل من الفحص لي فات")
    if not PACKAGES:
        info("ما كايناش لائحة التطبيقات باش نقارنو")
        return
    now = sorted(PACKAGES)
    old = None
    try:
        with open(STATE, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        pass
    if not old:
        info("هادا أول فحص. المرة الجاية غادي نقولك شنو تزاد ولا تمسح.")
    else:
        added = sorted(set(now) - set(old.get("packages", [])))
        removed = sorted(set(old.get("packages", [])) - set(now))
        info(f"الفحص لي فات: {old.get('date', '?')} (النقطة: {old.get('score', '?')})")
        if added:
            warn(f"{len(added)} تطبيق جديد من الفحص لي فات:",
                 "إلا شي واحد منهم ما نتا لي نصبتيه، هادي علامة خطيرة.")
            for p in added:
                sub(p)
        if removed:
            info(f"{len(removed)} تطبيق تمسح:")
            for p in removed[:10]:
                sub(p)
        if not added and not removed:
            ok("حتى تطبيق ما تزاد ولا تمسح")
    STATE_NEW.update(packages=now)


STATE_NEW = {}


def save_state(score):
    if not STATE_NEW:
        return
    STATE_NEW.update(date=f"{datetime.datetime.now():%Y-%m-%d %H:%M}", score=score)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(STATE_NEW, f)
    except Exception:
        pass


# ───────────────────────── 5. الشبكة ─────────────────────────
def hex_ip(h):
    if len(h) == 8:
        return ".".join(str(int(h[i:i + 2], 16)) for i in (6, 4, 2, 0))
    if h.upper() == "0" * 32:
        return "::"
    if h.upper().startswith("0000000000000000FFFF0000"):
        return hex_ip(h[24:])
    if h.upper() == "00000000000000000000000001000000":
        return "::1"
    return "IPv6"


def owner(uid):
    if uid == MY_UID:
        return "Termux"
    if uid in UID_MAP:
        return ", ".join(UID_MAP[uid][:2])
    if uid < 10000:
        return "النظام"
    return f"uid {uid}"


def check_network():
    header("5. الشبكة والانترنت")
    listen, estab = [], {}
    readable = False
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        data = read_net(f)
        if not data:
            continue
        readable = True
        for line in data.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 8:
                continue
            ip, port = parts[1].split(":")
            state, uid = parts[3], int(parts[7])
            if state == "0A":
                listen.append((hex_ip(ip), int(port, 16), uid))
            elif state == "01":
                o = owner(uid)
                estab[o] = estab.get(o, 0) + 1

    if not readable:
        info("Android ما خلانيش نقرا الاتصالات ديال الشبكة")
    else:
        seen = set()
        open_ext = []
        for ip, port, uid in listen:
            if (port, uid) in seen:
                continue
            seen.add((port, uid))
            public = ip in ("0.0.0.0", "::")
            o = owner(uid)
            if public and uid >= 10000 and not all(
                    is_oem(x.strip()) for x in o.split(",")):
                open_ext.append((port, o))
        if open_ext:
            warn("تطبيقات حالّين بورت مفتوح للشبكة:",
                 "أي جهاز معاك فالويفي يقدر يتصل بيهم. إلا ما عارفش هاد التطبيق، مسحو.")
            for port, o in open_ext:
                sub(f"البورت {port} ← {o}")
        else:
            ok("ما كاين حتى بورت مفتوح للشبكة من شي تطبيق")
        if estab:
            info("التطبيقات لي متصلين بالانترنت دابا:")
            for o, n in sorted(estab.items(), key=lambda x: -x[1])[:8]:
                sub(f"{o}: {n} اتصال")

    proxy = setting("global", "http_proxy")
    if proxy and proxy not in (":0", ""):
        bad(f"كاين Proxy مفعّل: {proxy}",
            "الانترنت ديالك كيدوز من سيرفر آخر ويقدر يتشاف. إلا ما نتا لي حطيتيه، حيدو من إعدادات الويفي.")
    elif _settings_ok:
        ok("ما كاين حتى Proxy")
    envp = {os.environ[v] for v in ("http_proxy", "https_proxy", "HTTP_PROXY",
            "HTTPS_PROXY", "all_proxy", "ALL_PROXY") if os.environ.get(v)}
    for val in envp:
        warn(f"Termux فيه Proxy: {val}",
             "شوف ملف ~/.bashrc وحيدو إلا ما نتا لي حطيتيه.")

    mode = setting("global", "private_dns_mode")
    if mode == "hostname":
        spec = setting("global", "private_dns_specifier")
        info(f"DNS خاص مفعّل: {spec}")
    elif mode in ("off", "opportunistic"):
        info("نصيحة: فعّل Private DNS (مثلاً dns.adguard-dns.com) باش تتحمى من المواقع الخبيثة")

    try:
        ifaces = os.listdir("/sys/class/net")
        vpn = [i for i in ifaces if i.startswith(("tun", "ppp", "wg"))]
        if vpn:
            info(f"كاين VPN شاعل ({', '.join(vpn)}) — تأكد أنك نتا لي شعلتيه")
    except Exception:
        pass


# ───────────────────────── 6. الملفات ─────────────────────────
def check_files():
    header("6. الملفات المشبوهة")
    bases = ["/storage/emulated/0", os.path.join(HOME, "storage", "shared")]
    root = next((b for b in bases if os.path.isdir(b) and os.access(b, os.R_OK)), None)
    if not root:
        warn("Termux ما عندوش صلاحية يدخل للذاكرة",
             "كتب termux-setup-storage ووافق على الصلاحية، ومن بعد عاود الفحص.")
        return

    dirs = ["Download", "Bluetooth", "Documents", "Telegram",
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents",
            "WhatsApp/Media/WhatsApp Documents",
            "Android/media/org.telegram.messenger"]
    apks, double = [], []
    for d in dirs:
        top = os.path.join(root, d)
        if not os.path.isdir(top):
            continue
        for cur, subdirs, files in os.walk(top):
            if cur[len(top):].count(os.sep) >= 4:
                subdirs[:] = []
            for f in files:
                low = f.lower()
                if low.endswith((".apk", ".apks", ".xapk", ".apkm")):
                    path = os.path.join(cur, f)[len(root) + 1:]
                    if re.search(r"\.(pdf|jpg|jpeg|png|mp4|mp3|doc|docx|txt)\.apk$", low):
                        double.append(path)
                    else:
                        apks.append(path)

    if double:
        bad("ملفات متنكرة (كتبان صورة ولا PDF ولكن هي تطبيق):",
            "هادي حيلة معروفة ديال الهاكرز. مسحهم وما تحلهمش أبداً.")
        for p in double:
            sub(p)
    if apks:
        warn(f"لقيت {len(apks)} ملف APK فالتيليفون:",
             "ما تنصب حتى APK جاك فواتساب ولا تيليغرام من عند شي حد ما عارفوش.")
        for p in apks[:15]:
            sub(p)
    if not apks and not double:
        ok("ما لقيت حتى ملف APK مشبوه فالتحميلات والواتساب والتيليغرام")


# ───────────────────────── 7. Termux ─────────────────────────
def check_termux():
    header("7. Termux راسو")
    files = [os.path.join(HOME, f) for f in (".bashrc", ".zshrc", ".profile", ".bash_profile")]
    files += [os.path.join(PREFIX, "etc", f) for f in ("bash.bashrc", "profile")]
    patterns = [
        (r"(curl|wget)[^\n|]*\|\s*(ba|z)?sh", "كيحمل وكيشغل سكريبت من الانترنت"),
        (r"\bnc\b[^\n]*-e\b|/dev/tcp/", "Reverse shell (باب خلفي)"),
        (r"base64\s+(-d|--decode)", "كود مخبّي بـ base64"),
        (r"ngrok|cloudflared|serveo|localhost\.run", "نفق للانترنت (tunnel)"),
        (r"rm\s+-rf\s+(/|~|\$HOME|/sdcard)", "أمر كيمسح الملفات"),
    ]
    hits = []
    for f in files:
        txt = read(f)
        if not txt:
            continue
        for n, line in enumerate(txt.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            for pat, why in patterns:
                if re.search(pat, line):
                    hits.append(f"{os.path.basename(f)} سطر {n}: {why}")
    if hits:
        bad("لقيت أوامر خطيرة كتشتغل أوتوماتيكياً ملي كتحل Termux:",
            "هادشي كيوقع ملي كتنصب أدوات «هاك» من يوتيوب. افتح الملف وحيد السطر.")
        for h in hits:
            sub(h)
    else:
        ok("ملفات التشغيل ديال Termux نقية")

    ak = read(os.path.join(HOME, ".ssh", "authorized_keys"))
    if ak and ak.strip():
        n = len([l for l in ak.splitlines() if l.strip() and not l.startswith("#")])
        warn(f"كاين {n} مفتاح SSH يقدر يدخل للـ Termux ديالك",
             "إلا ما نتا لي زدتيهم، مسح الملف: rm ~/.ssh/authorized_keys")

    ps = run("ps -A -o NAME 2>/dev/null || ps -e -o comm 2>/dev/null", 10)
    watch = {"sshd", "nc", "ncat", "netcat", "ngrok", "cloudflared", "dropbear",
             "telnetd", "msfconsole", "msfvenom", "socat", "busybox"}
    running = sorted({l.strip() for l in ps.splitlines()} & watch)
    if running:
        warn("برامج شبكة خدامين فـ Termux دابا:",
             "إلا ما نتا لي شعلتيهم، سد Termux كامل (exit) وعاود حلو.")
        for r in running:
            sub(r)
    else:
        ok("ما كاين حتى برنامج شبكة مشبوه خدام فـ Termux")

    cron = run("crontab -l 2>/dev/null", 5)
    cron = "\n".join(l for l in cron.splitlines() if l.strip() and not l.startswith("#"))
    if cron:
        warn("كاين مهام أوتوماتيكية (crontab) فـ Termux:",
             "تأكد منهم بـ crontab -l ومسحهم بـ crontab -r إلا ما عارفهمش.")
        for l in cron.splitlines()[:5]:
            sub(l)


# ───────────────────────── 8. صحة الجهاز ─────────────────────────
def check_health():
    header("8. صحة الجهاز")
    mem = read("/proc/meminfo")
    if mem:
        vals = dict(re.findall(r"(\w+):\s+(\d+)", mem))
        total = int(vals.get("MemTotal", 0))
        avail = int(vals.get("MemAvailable", 0))
        if total:
            used = 100 - avail * 100 // total
            txt = f"الرام: {used}% مستعملة من {total / 1048576:.1f} GB"
            if used >= 90:
                warn(txt, "سد التطبيقات لي ما كتستعملهمش. إلا بقات عامرة ديما، شي تطبيق كيخدم فالخفا.")
            else:
                ok(txt)

    for label, path in (("الذاكرة الداخلية", "/storage/emulated/0"), ("ذاكرة النظام", "/data")):
        try:
            u = shutil.disk_usage(path)
            free = u.free * 100 // u.total
            txt = f"{label}: باقي {u.free / 1e9:.1f} GB ({free}%)"
            if free < 10:
                warn(txt, "التيليفون كيتقل ملي الذاكرة كتعمر. مسح الفيديوهات والملفات لي ما محتاجهمش.")
            else:
                ok(txt)
            break
        except Exception:
            continue

    if shutil.which("termux-battery-status"):
        out = run("termux-battery-status", 8)
        try:
            bat = json.loads(out)
            pct, temp = bat.get("percentage"), bat.get("temperature")
            health = bat.get("health", "")
            info(f"البطارية: {pct}%")
            if temp is not None:
                if temp > 42:
                    warn(f"حرارة البطارية: {temp:.0f}°C (سخونة)",
                         "السخونة بلا سبب يقدر يكون من تطبيق خبيث كيخدم فالخفا.")
                else:
                    ok(f"حرارة البطارية: {temp:.0f}°C")
            if health and health != "GOOD":
                warn(f"حالة البطارية: {health}", "البطارية ممكن تحتاج تتبدل.")
        except Exception:
            info("ما قدرتش نقرا البطارية (نصب تطبيق Termux:API من F-Droid)")
    else:
        info("باش نفحص البطارية: pkg install termux-api + تطبيق Termux:API")


# ───────────────────────── الخلاصة ─────────────────────────
def score():
    return max(0, 100 - 25 * COUNTS["bad"] - 5 * COUNTS["warn"])


def summary():
    header("الخلاصة")
    sc = score()
    col = G if sc >= 80 else Y if sc >= 50 else R
    bar_w = WIDTH - 14
    done = round(bar_w * sc / 100)
    print()
    rline("نقطة الأمان", BOLD + W)
    print(f"  {col}{'█' * done}{D}{'░' * (bar_w - done)}{N} {BOLD}{col}{sc}/100{N}")
    print()
    chips = (f"{G}🟢 {COUNTS['ok']}{N}   {Y}🟡 {COUNTS['warn']}{N}   {R}🔴 {COUNTS['bad']}{N}")
    print(f"  {chips}")
    REPORT.append(f"نقطة الأمان: {sc}/100 — 🟢 {COUNTS['ok']}  🟡 {COUNTS['warn']}  🔴 {COUNTS['bad']}")
    print()
    if COUNTS["bad"]:
        show(f"كاينين {COUNTS['bad']} مشاكل خطيرة و {COUNTS['warn']} تنبيهات — خصك تشوفهم دابا", "bad")
    elif COUNTS["warn"]:
        show(f"الجهاز غالباً سالم، ولكن كاين {COUNTS['warn']} حوايج خصك تراجعهم", "warn")
    else:
        show("الجهاز ديالك باين سالم ✨", "ok")
    print()

    if FINDINGS:
        info("شنو خصك دير:")
        print()
        order = sorted(FINDINGS, key=lambda x: 0 if x[0] == "bad" else 1)
        for i, (lvl, text, advice) in enumerate(order, 1):
            show(f"{i}. {text}", lvl)
            if advice:
                sub(f"← {advice}")
        print()

    info("ملاحظة: بلا root، حتى أداة ما تقدر تضمن 100%. "
         "إلا شكيتي بزاف، دير Factory Reset وبدّل كلمات السر من جهاز آخر.")


def save_report():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    head = [f"تقرير فحص الجهاز — {datetime.datetime.now():%Y-%m-%d %H:%M}",
            f"{DEVICE.get('brand', '')} {DEVICE.get('model', '')} — Android {DEVICE.get('release', '')}"]
    text = "\n".join(head + REPORT) + "\n"
    targets = [os.path.join(HOME, "storage", "downloads"), HOME]
    for t in targets:
        if os.path.isdir(t):
            path = os.path.join(t, f"fahs_{stamp}.txt")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                print()
                show("التقرير تحفظ هنا:", "info")
                print(f"{W}  {path}{N}")
                return
            except Exception:
                continue


def ask(prompt):
    rline(prompt, C)
    try:
        ans = input(f"{BOLD}{W}  › {N}").strip()
        return ans.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    except EOFError:
        return ""


def uninstall_menu():
    """كنحلو نافذة المسح ديال Android — نتا لي كتأكد."""
    if not RISKY:
        return
    print()
    rline("بغيتي تمسح شي تطبيق من هادو؟", BOLD + W)
    items = sorted(RISKY.items())
    for i, (p, why) in enumerate(items, 1):
        print(f"  {Y}{i:>2}{N}  {p}  {D}{_ar(why)}{N}")
    ans = ask("كتب الأرقام مفروقين بفاصلة (مثلاً 1,3) ولا Enter باش تخرج")
    for part in re.split(r"[,\s،]+", ans):
        if part.isdigit() and 1 <= int(part) <= len(items):
            pkg = items[int(part) - 1][0]
            sh(f"am start -a android.intent.action.DELETE -d package:{pkg}", 10)
            rline(f"تحلات نافذة المسح ديال {pkg} — أكد فالتيليفون", G)
            ask("ضغط Enter ملي تسالي")


def adb_off_menu():
    if not ADB:
        return
    print()
    ans = ask("بغيتي نطفي ADB وتصحيح الأخطاء دابا؟ (y/n)")
    if ans.lower() in ("y", "yes", "اه", "ه", "نعم", "1"):
        sh("settings put global adb_wifi_enabled 0", 5)
        sh("settings put global adb_enabled 0", 5)
        rline("تطفى ADB ✅ (الاتصال غادي يتقطع، هادشي عادي)", G)


def banner():
    w = WIDTH - 3
    print()
    print(f"{C}╭{'─' * w}╮{N}")
    logo = ["╔═╗╔═╗╦ ╦╔═╗", "╠╣ ╠═╣╠═╣╚═╗", "╩  ╩ ╩╩ ╩╚═╝"]
    for l in logo:
        pad = (w - len(l)) // 2
        print(f"{C}│{N}{' ' * pad}{BOLD}{C}{l}{N}{' ' * (w - pad - len(l))}{C}│{N}")
    t = _ar("أداة فحص أمان التيليفون")
    pad = (w - len(t)) // 2
    print(f"{C}│{N}{' ' * pad}{W}{t}{N}{' ' * (w - pad - len(t))}{C}│{N}")
    v = f"v{VERSION}"
    pad = (w - len(v)) // 2
    print(f"{C}│{N}{' ' * pad}{D}{v}{N}{' ' * (w - pad - len(v))}{C}│{N}")
    print(f"{C}╰{'─' * w}╯{N}")


MENU = [
    ("1", "فحص كامل", "full"),
    ("2", "فحص سريع (بلا الملفات)", "quick"),
    ("3", "التطبيقات والصلاحيات بوحدهم", "apps"),
    ("4", "مسح تطبيق", "uninstall"),
    ("5", "طفي ADB وتصحيح الأخطاء", "adboff"),
    ("0", "خروج", "exit"),
]


def menu():
    print()
    for key, label, _ in MENU:
        v = _ar(label)
        print(f"{' ' * max(0, WIDTH - 8 - len(v))}{W}{v}{N}  {BOLD}{C}[{key}]{N}")
    ans = ask("ختار رقم")
    for key, _, mode in MENU:
        if ans == key:
            return mode
    return "full" if ans == "" else "exit"


HELP = """fahs — فحص أمان التيليفون

  fahs            القائمة
  fahs --full     فحص كامل مباشرة
  fahs --quick    فحص سريع
  fahs --apps     التطبيقات والصلاحيات
  --no-color      بلا ألوان
  --no-adb        ما تستعملش ADB

وضع ADB (فحص كامل للتطبيقات والصلاحيات):
  pkg install android-tools
  خيارات المطور ← تصحيح الأخطاء اللاسلكي ← إقران بالرمز
  adb pair localhost:PORT     ثم    adb connect localhost:PORT
"""


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        for line in HELP.splitlines():
            print(_ar(line) if re.search(r"[\u0600-\u06FF]", line) else line)
        return
    banner()
    detect_adb()
    if ADB:
        show(f"وضع ADB خدام ({ADB}) — الفحص غادي يكون كامل", "ok")
    else:
        show("وضع عادي (بلا ADB) — شي فحوصات ناقصين. شوف fahs --help", "info")

    mode = next((m for f, m in (("--full", "full"), ("--quick", "quick"),
                                ("--apps", "apps")) if f in sys.argv), None)
    interactive = sys.stdin.isatty() and mode is None
    if mode is None:
        mode = menu() if interactive else "full"
    if mode == "exit":
        return

    rline("كنقرا لائحة التطبيقات...", D)
    load_packages()
    load_uid_map()

    if mode == "uninstall":
        for p in third_party_user_apps():
            flag(p, "")
        uninstall_menu()
        return
    if mode == "adboff":
        adb_off_menu()
        return

    steps = {
        "full": (check_device, check_root, check_adb, check_apps, check_permissions,
                 check_changes, check_network, check_files, check_termux, check_health),
        "quick": (check_device, check_root, check_adb, check_apps,
                  check_changes, check_network, check_termux),
        "apps": (check_apps, check_permissions, check_changes),
    }[mode]
    STEP["total"] = len(steps)
    for step in steps:
        try:
            step()
        except KeyboardInterrupt:
            raise
        except Exception as e:  # حتى فحص ما يطيّح الأداة كاملة
            info(f"وقع مشكل فهاد الفحص: {e}")
    summary()
    save_report()
    save_state(score())
    if interactive:
        uninstall_menu()
        adb_off_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Y}{_ar('توقف الفحص.')}{N}")
