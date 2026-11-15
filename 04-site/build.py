#!/usr/bin/env python3
"""Static site builder for DragDriveCodes.

Single source of truth: data/site.json + data/codes.json.
Every page, the sitemap, dateModified, and code tables are generated from those files,
so refreshing codes only requires editing JSON and re-running this script.

Usage:  python build.py
Output: ./dist  (pure static HTML, no external requests)
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DIST = ROOT / "dist"
LOCAL_DIST = ROOT / "dist-local"

# Local-preview tree: same pages, flat filenames, relative hrefs. See build_local().
LOCAL_NAMES = {
    "/": "index.html",
    "/how-to-redeem/": "how-to-redeem.html",
    "/expired-codes/": "expired-codes.html",
    "/rp-guide/": "rp-guide.html",
    "/updates/": "updates.html",
    "/about/": "about.html",
    "/privacy/": "privacy.html",
    "/contact/": "contact.html",
}
_LOCAL_HREF = re.compile(r'(<(?:a|link)\b[^>]*?\bhref=")([^"]+)(")')


def localize_html(html: str) -> str:
    """Rewrite only <a>/<link> hrefs; canonical, og:*, JSON-LD keep absolute URLs."""
    def repl(m):
        url = m.group(2)
        path, sep, frag = url.partition("#")
        if path in LOCAL_NAMES:
            return m.group(1) + LOCAL_NAMES[path] + (sep + frag if sep else "") + m.group(3)
        if path.startswith("/") and not path.startswith("//"):
            return m.group(1) + path.lstrip("/") + m.group(3)
        return m.group(0)
    return _LOCAL_HREF.sub(repl, html)


SITE = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
CODES = json.loads((DATA / "codes.json").read_text(encoding="utf-8"))

BRAND = SITE["brand"]
BASE = SITE["base_url"].rstrip("/")
EMAIL = SITE["contact_email"]
CHECKED = SITE["last_checked"]
GAME = SITE["game"]

ADS = SITE.get("ads") or {}
ADS_ON = bool(ADS.get("enabled"))
ADS_CLIENT = str(ADS.get("client") or "").strip()
ADS_SLOTS = {str(k): str(v or "").strip() for k, v in (ADS.get("slots") or {}).items()}
ADS_POSITIONS = ("home-after-codes", "home-end", "redeem-mid",
                 "expired-after-tables", "rp-mid", "updates-mid")
ADS_CLIENT_RE = re.compile(r"ca-pub-\d{16}")
ADS_SLOT_RE = re.compile(r"\d{6,20}")

ADS_CSS = "" if not ADS_ON else (
    ".ad-slot{margin:28px 0;padding:0;overflow:hidden;border-radius:var(--radius)}"
    ".ad-slot::before{content:'';display:block;min-height:200px}"
    "@media(min-width:640px){.ad-slot::before{min-height:250px}}"
    ".ad-slot ins{display:block}"
)
ADS_HEAD = "" if not ADS_ON else (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    f'?client={ADS_CLIENT}" crossorigin="anonymous"></script>'
)


def validate_ads() -> None:
    if not ADS_ON:
        return
    errors = []
    if not ADS_CLIENT_RE.fullmatch(ADS_CLIENT):
        errors.append(f"ads.client={ADS_CLIENT!r} 不是 AdSense 客户端 ID（应为 ca-pub- 加 16 位数字）")
    for pos in ADS_POSITIONS:
        slot = ADS_SLOTS.get(pos, "")
        if not slot:
            errors.append(f"ads.slots.{pos} 为空（ads.enabled=true 时每个位置都必须有 slot ID）")
        elif not ADS_SLOT_RE.fullmatch(slot):
            errors.append(f"ads.slots.{pos}={slot!r} 不是合法 slot ID（应为纯数字）")
    if errors:
        print("\nBUILD FAILED — ads config is not publishable:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print(f"  ads validation OK ({len(ADS_POSITIONS)} slots, client {ADS_CLIENT})")


def ad_unit(position: str) -> str:
    """Emit one ad slot. Returns '' when ads are off -- no wrapper, no height."""
    if not ADS_ON:
        return ""
    slot = ADS_SLOTS.get(position, "")
    return (
        f'<div class="ad-slot" data-slot="{position}">'
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADS_CLIENT}" '
        f'data-ad-slot="{slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
        '</div>'
    )


MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}


def human(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return f"{dd} {MONTHS[m]} {y}"


CHECKED_HUMAN = human(CHECKED)
TITLE_MONTH = MONTHS[int(CHECKED[5:7])]

ACTIVE = CODES["active"]
UNCONFIRMED = CODES["unconfirmed"]
EXPIRED_2026 = CODES["expired"]["2026"]
EXPIRED_2025 = CODES["expired"]["2025"]
TOTAL_EXPIRED = len(EXPIRED_2026) + len(EXPIRED_2025)
RP_MIN = sum(c["reward_min"] for c in ACTIVE)
RP_MAX = sum(c["reward_max"] for c in ACTIVE)
SINGLE_MIN = min((c["reward_min"] for c in ACTIVE), default=0)
SINGLE_MAX = max((c["reward_max"] for c in ACTIVE), default=0)

# Number words are derived, never hardcoded: the code count changes every few weeks.
WORD_NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def count_word(n: int, capital: bool = False) -> str:
    w = WORD_NUMBERS.get(n, str(n))
    return w.capitalize() if capital else w


def name_list(items: list[dict]) -> str:
    names = [c["code"] for c in items]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def report_href(code: str) -> str:
    subject = quote(f"Code report: {code}", safe="")
    body = quote(
        f"Code: {code}\n"
        f"What happened (invalid / no RP / wrong amount / already used):\n"
        f"Platform (phone, tablet, PC, console):\n"
        f"Approximate time tried (UTC):\n"
        f"Anything else that helps:\n",
        safe="")
    return f"mailto:{EMAIL}?subject={subject}&body={body}"


def validate_data() -> None:
    """Fail the build instead of publishing data that contradicts the pages."""
    errors: list[str] = []
    seen: dict[str, str] = {}

    groups = [("active", ACTIVE), ("unconfirmed", UNCONFIRMED)]
    for year, items in CODES["expired"].items():
        groups.append((f"expired.{year}", items))

    for name, items in groups:
        for c in items:
            code = c.get("code", "").strip()
            if not code:
                errors.append(f"{name}: entry without a code")
                continue
            if code != code.upper():
                errors.append(f"{code}: codes must be uppercase")
            if code in seen:
                errors.append(f"{code}: duplicate, appears in both {seen[code]} and {name}")
            else:
                seen[code] = name

    for c in ACTIVE + UNCONFIRMED:
        code = c["code"]
        srcs = [s for s in c.get("sources", []) if s]
        if not srcs:
            errors.append(f"{code}: no sources listed")
        if c.get("status") == "confirmed" and len(set(srcs)) < 2:
            errors.append(f"{code}: confirmed needs >=2 independent sources, has {len(set(srcs))}")
        lo, hi = c.get("reward_min", 0), c.get("reward_max", 0)
        if not isinstance(lo, int) or not isinstance(hi, int) or lo <= 0:
            errors.append(f"{code}: reward_min must be a positive integer")
        if hi < lo:
            errors.append(f"{code}: reward_max ({hi}) is lower than reward_min ({lo})")
        if c.get("last_verified", "") > CHECKED:
            errors.append(f"{code}: last_verified {c['last_verified']} is in the future (site last_checked {CHECKED})")
        if c.get("expired_on"):
            errors.append(f"{code}: has an expired_on date but is listed as active")
        tested = c.get("in_game_verified")
        if tested:
            if tested > CHECKED:
                errors.append(f"{code}: in_game_verified {tested} is later than last_checked {CHECKED}")
            if tested > c.get("last_verified", ""):
                errors.append(f"{code}: in_game_verified {tested} is later than last_verified {c.get('last_verified')}")
            if c.get("status") != "confirmed":
                errors.append(f"{code}: in_game_verified is set but status is not 'confirmed'")

    # The templates branch on the list an entry sits in, the card branches on its status.
    for c in ACTIVE:
        if c.get("status") != "confirmed":
            errors.append(f"{c['code']}: listed as active but status is '{c.get('status')}'")
    for c in UNCONFIRMED:
        if c.get("status") != "reported":
            errors.append(f"{c['code']}: listed as reported but status is '{c.get('status')}'")

    for year, items in CODES["expired"].items():
        for c in items:
            if c.get("expired_on") and c["expired_on"] > CHECKED:
                errors.append(f"{c['code']}: expired_on is in the future")

    if ACTIVE and RP_MAX <= 0:
        errors.append("active codes produce a zero RP total")

    if errors:
        print("\nBUILD FAILED — data is not publishable:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print(f"  data validation OK ({len(seen)} unique codes, {len(ACTIVE)} active)")


COUNT_PATTERNS = [
    re.compile(r"\b(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve)\s+codes are confirmed\b"),
    re.compile(r"\b(?:the|all)\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+confirmed codes\b", re.I),
]


def validate_copy(pages: list[dict]) -> None:
    """Catch a stale number word left behind after the code count changes."""
    expected = count_word(len(ACTIVE))
    problems: list[str] = []
    for p in pages:
        for pat in COUNT_PATTERNS:
            for m in pat.finditer(p["body"]):
                found = m.group(1).lower()
                if found != expected:
                    problems.append(f"{p['slug']}: text says '{m.group(0)}' but there are {len(ACTIVE)} active codes")
    if problems:
        print("\nBUILD FAILED — copy contradicts the data:")
        for e in problems:
            print(f"  - {e}")
        raise SystemExit(1)
    print(f"  copy validation OK (number words match {len(ACTIVE)} active codes)")



def rp_full(n: int) -> str:
    return f"{n:,} RP"


def rp_short(n: int) -> str:
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.0f}M RP" if v == int(v) else f"{v:.1f}M RP"
    if n >= 1_000:
        return f"{n // 1000}K RP"
    return f"{n:,} RP"


def reward_text(c: dict) -> str:
    lo, hi = c["reward_min"], c["reward_max"]
    if lo == hi:
        return rp_full(lo)
    return f"{rp_short(lo)} – {rp_short(hi)}"


def reward_text_table(c: dict) -> str:
    lo, hi = c["reward_min"], c["reward_max"]
    if lo == hi:
        return f"{lo:,}"
    return f"{rp_short(lo)}–{rp_short(hi)}"


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#0A0D12;--bg-elev:#11161F;--bg-elev-2:#161E2A;
  --line:#232C3A;--line-strong:#344054;
  --text:#E8EDF5;--text-dim:#98A4B7;--text-mute:#6E7B8F;
  --accent:#C8FF3D;--accent-ink:#0A0D12;
  --ok:#35D07F;--warn:#FFB020;--danger:#FF5C5C;--info:#5AA9FF;
  --font-sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --font-mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --radius-sm:8px;--radius:12px;
}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:400 16px/1.65 var(--font-sans);overflow-wrap:break-word}
a{color:var(--info);text-decoration:none}
a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.skip{position:absolute;left:-9999px;top:0;background:var(--accent);color:var(--accent-ink);padding:10px 16px;z-index:99;font-weight:700}
.skip:focus{left:8px;top:8px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.wrap{width:100%;max-width:1080px;margin:0 auto;padding:0 16px}
@media(min-width:640px){.wrap{padding:0 24px}}
@media(min-width:1024px){.wrap{padding:0 32px}}
.hdr{position:sticky;top:0;z-index:10;background:rgba(10,13,18,.94);border-bottom:1px solid var(--line)}
.hdr__in{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:56px}
.brand{display:inline-flex;align-items:center;gap:9px;font-weight:700;font-size:17px;color:var(--text);letter-spacing:-.01em;min-width:0;white-space:nowrap}
.brand:hover{text-decoration:none;color:var(--accent)}
.brand__mark{width:28px;height:28px;flex:0 0 auto;display:block}
@media(max-width:359px){.brand{font-size:16px;gap:7px}.brand__mark{width:24px;height:24px}}
.nav{display:none;gap:2px}
@media(min-width:900px){.nav{display:flex}}
.nav a{color:var(--text-dim);font-size:14px;padding:8px 10px;border-radius:var(--radius-sm)}
.nav a:hover{color:var(--text);background:var(--bg-elev-2);text-decoration:none}
.nav a[aria-current=page]{color:var(--accent)}
.pill{display:inline-flex;align-items:center;gap:7px;background:var(--bg-elev-2);border:1px solid var(--line);border-radius:999px;padding:5px 11px;font-size:12px;color:var(--text-dim);white-space:nowrap;flex:0 0 auto}
.pill__word{display:none}
@media(min-width:420px){.pill__word{display:inline}}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px rgba(53,208,127,.16);flex:0 0 auto}
main{padding-bottom:16px}
.hero{padding:30px 0 0}
.sec-label{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-size:clamp(26px,6vw,34px);line-height:1.18;letter-spacing:-.02em;margin:0 0 12px}
h2{font-size:clamp(19px,3.4vw,22px);line-height:1.3;margin:38px 0 10px;letter-spacing:-.01em}
h3{font-size:16px;line-height:1.4;margin:22px 0 6px}
p{margin:0 0 12px;max-width:68ch}
.lede{color:var(--text-dim);font-size:15px;max-width:70ch}
ul,ol{padding-left:20px}
li{margin:0 0 6px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin:24px 0 8px}
.stat{background:var(--bg-elev);padding:14px 10px;text-align:center;min-width:0}
.stat b{display:block;font-size:clamp(19px,4.6vw,26px);color:var(--accent);font-variant-numeric:tabular-nums;line-height:1.2;letter-spacing:-.01em}
.stat span{display:block;font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--text-mute);margin-top:2px}
.code-card{position:relative;background:var(--bg-elev);border:1px solid var(--line);border-radius:var(--radius);padding:15px 16px 14px;margin:0 0 12px}
.code-card::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:0 3px 3px 0;background:var(--line-strong)}
.code-card[data-status=confirmed]::before{background:var(--ok)}
.code-card[data-status=reported]::before{background:var(--warn)}
.code-card__top{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin-bottom:10px}
.badge{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:999px;border:1px solid}
.badge--ok{color:var(--ok);border-color:rgba(53,208,127,.42);background:rgba(53,208,127,.1)}
.badge--warn{color:var(--warn);border-color:rgba(255,176,32,.42);background:rgba(255,176,32,.1)}
.badge--dead{color:var(--text-mute);border-color:var(--line-strong);background:rgba(110,123,143,.08)}
.badge--tested{color:var(--info);border-color:rgba(90,169,255,.42);background:rgba(90,169,255,.1)}
.meta{font-size:12px;color:var(--text-mute)}
.code-card__row{display:flex;flex-direction:column;gap:12px}
@media(min-width:640px){.code-card__row{flex-direction:row;align-items:center;justify-content:space-between;gap:16px}}
.code-card__id{min-width:0}
.code{font-family:var(--font-mono);font-weight:700;font-size:16px;letter-spacing:.02em;word-break:break-all;user-select:all;line-height:1.35}
.reward{margin-top:7px;font-size:14px;color:var(--text-dim)}
.reward b{color:var(--text);font-size:17px;font-variant-numeric:tabular-nums}
.btn-copy{flex:0 0 auto;min-height:44px;padding:0 20px;border:0;border-radius:var(--radius-sm);background:var(--accent);color:var(--accent-ink);font:700 15px/1 var(--font-sans);cursor:pointer;transition:background .12s ease,transform .12s ease}
.btn-copy:hover{background:#d8ff6b}
.btn-copy:active{transform:scale(.985)}
.btn-copy.is-done{background:var(--ok)}
@media(max-width:639px){.btn-copy{width:100%}}
.note{font-size:13px;color:var(--text-mute);margin:12px 0 0;max-width:70ch}
.report{display:inline-flex;align-items:center;gap:6px;min-height:44px;margin:2px 0 -6px;font-size:13px;color:var(--text-mute);text-decoration:none}
.report:hover{color:var(--info)}
.report:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.steps{list-style:none;counter-reset:s;padding:0;margin:16px 0 0;display:grid;gap:10px}
.steps li{counter-increment:s;position:relative;padding:14px 16px 14px 54px;background:var(--bg-elev);border:1px solid var(--line);border-radius:var(--radius);margin:0}
.steps li::before{content:counter(s);position:absolute;left:14px;top:13px;width:24px;height:24px;border-radius:50%;background:var(--bg-elev-2);border:1px solid var(--line-strong);color:var(--accent);font-size:13px;font-weight:700;display:grid;place-items:center}
.steps b{display:block;font-size:15px;margin-bottom:2px}
.steps span{font-size:14px;color:var(--text-dim)}
.callout{background:var(--bg-elev);border:1px solid var(--line);border-left:3px solid var(--info);border-radius:10px;padding:13px 16px;font-size:14px;color:var(--text-dim);margin:18px 0;max-width:78ch}
.callout--warn{border-left-color:var(--warn)}
.callout--ok{border-left-color:var(--ok)}
.callout strong{color:var(--text)}
.callout p:last-child{margin-bottom:0}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:var(--radius);background:var(--bg-elev);margin:14px 0 8px}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:480px}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--text-mute);background:var(--bg-elev-2);font-weight:700;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--bg-elev-2)}
td.code-cell{font-family:var(--font-mono);font-size:12.5px;word-break:break-all;color:var(--text)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.faq details{background:var(--bg-elev);border:1px solid var(--line);border-radius:var(--radius);padding:0 16px;margin:0 0 9px}
.faq summary{cursor:pointer;list-style:none;padding:13px 0;font-weight:600;font-size:15px;display:flex;justify-content:space-between;align-items:center;gap:14px}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";color:var(--accent);font-size:20px;line-height:1;flex:0 0 auto}
.faq details[open] summary::after{content:"\\2212"}
.faq__body{padding:0 0 13px;font-size:14.5px;color:var(--text-dim);max-width:70ch}
.faq__body p{margin:0 0 8px}
.crumbs{font-size:12px;color:var(--text-mute);margin:18px 0 0;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.crumbs a{color:var(--text-dim)}
.crumbs span{color:var(--line-strong)}
.sources{font-size:12.5px;color:var(--text-mute);margin-top:8px}
.sources li{margin-bottom:5px}
.ftr{border-top:1px solid var(--line);margin-top:52px;padding:30px 0 44px;font-size:13px;color:var(--text-mute)}
.ftr__grid{display:grid;gap:22px}
@media(min-width:640px){.ftr__grid{grid-template-columns:1.15fr 1fr}}
.ftr p{max-width:52ch;margin:8px 0 0}
.ftr nav{display:flex;flex-wrap:wrap;gap:8px 18px;align-content:start}
.ftr a{color:var(--text-dim)}
.ftr__bottom{margin-top:22px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;display:flex;flex-wrap:wrap;gap:8px 16px;justify-content:space-between}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = """
(function(){
  var live=document.getElementById('copy-status');
  function fallback(text){
    var t=document.createElement('textarea');
    t.value=text;t.setAttribute('readonly','');
    t.style.position='fixed';t.style.top='-1000px';t.style.opacity='0';
    document.body.appendChild(t);t.select();
    try{document.execCommand('copy');}catch(e){}
    document.body.removeChild(t);
  }
  function announce(btn,text){
    var label=btn.getAttribute('data-label')||'Copy';
    btn.textContent='Copied';
    btn.classList.add('is-done');
    if(live){live.textContent='Copied '+text+' to the clipboard.';}
    window.setTimeout(function(){btn.textContent=label;btn.classList.remove('is-done');},1600);
  }
  document.addEventListener('click',function(e){
    var btn=e.target.closest('[data-copy]');
    if(!btn){return;}
    var text=btn.getAttribute('data-copy');
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(function(){announce(btn,text);},function(){fallback(text);announce(btn,text);});
    }else{fallback(text);announce(btn,text);}
  });
})();
"""

# --- Brand mark -------------------------------------------------------------
# One geometry, three consumers: the inline header/footer mark, the SVG favicon,
# and the raster fallback. Letters are drawn as paths so they never depend on a
# font being installed (system fonts differ per device; a wordmark must not).
#
# 40x40 grid: badge 0.8..39.2, letters 12..28 tall, stems 4 wide, bowls r=8,
# 2.4 gap between the two Ds, baseline rule at y=31. Each D carries an r=4.4
# counter drawn as a second subpath (fill-rule=evenodd), so the glyphs stay
# readable as letters at 44-120px instead of collapsing into solid blobs.
MARK_BADGE = "#10151D"
MARK_ACCENT = "#C8FF3D"
MARK_PATH = ("M6.8 12h4a8 8 0 0 1 0 16h-4zM10.8 15.6a4.4 4.4 0 0 1 0 8.8z"
             "M21.2 12h4a8 8 0 0 1 0 16h-4zM25.2 15.6a4.4 4.4 0 0 1 0 8.8z")


def mark_svg(size: int = 28, cls: str = "brand__mark") -> str:
    """Decorative brand mark. Text next to it carries the accessible name."""
    return (
        f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 40 40" '
        'aria-hidden="true" focusable="false">'
        f'<rect x="0.8" y="0.8" width="38.4" height="38.4" rx="10" fill="{MARK_BADGE}" '
        f'stroke="{MARK_ACCENT}" stroke-opacity=".38" stroke-width="1.6"/>'
        f'<path d="{MARK_PATH}" fill="{MARK_ACCENT}" fill-rule="evenodd"/>'
        f'<rect x="8.8" y="31" width="22.4" height="1.6" rx=".8" fill="{MARK_ACCENT}" fill-opacity=".55"/>'
        '</svg>'
    )


def mark_data_uri() -> str:
    """Same mark, URL-encoded for an inline SVG favicon (zero image requests)."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'>"
        f"<rect x='0.8' y='0.8' width='38.4' height='38.4' rx='10' fill='{MARK_BADGE}' "
        f"stroke='{MARK_ACCENT}' stroke-opacity='.38' stroke-width='1.6'/>"
        f"<path d='{MARK_PATH}' fill='{MARK_ACCENT}' fill-rule='evenodd'/>"
        f"<rect x='8.8' y='31' width='22.4' height='1.6' rx='.8' fill='{MARK_ACCENT}' fill-opacity='.55'/>"
        "</svg>"
    )
    return "data:image/svg+xml," + quote(svg, safe="")


FAVICON = mark_data_uri()

NAV = [
    ("/", "Codes"),
    ("/how-to-redeem/", "Redeem"),
    ("/expired-codes/", "Expired"),
    ("/rp-guide/", "RP guide"),
    ("/updates/", "Updates"),
]

FOOTER_LINKS = NAV + [("/about/", "About"), ("/privacy/", "Privacy"), ("/contact/", "Contact")]


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def head(title: str, desc: str, slug: str, jsonld: list[dict], noindex: bool = False) -> str:
    url = BASE + slug
    robots = "noindex,follow" if noindex else "index,follow,max-image-preview:large"
    graph = [{"@context": "https://schema.org", "@graph": jsonld}]
    ld = json.dumps(graph[0], ensure_ascii=False, separators=(",", ":"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#0A0D12">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{BRAND}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{BASE}/og.png">
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="icon" href="{FAVICON}" type="image/svg+xml" sizes="any">
<style>{CSS}{ADS_CSS}</style>
<script type="application/ld+json">{ld}</script>
{ADS_HEAD}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="hdr">
  <div class="wrap hdr__in">
    <a class="brand" href="/">{mark_svg(28)}{BRAND}</a>
    <nav class="nav" aria-label="Primary">
      {''.join(f'<a href="{u}"{" aria-current=page" if u == slug else ""}>{esc(t)}</a>' for u, t in NAV)}
    </nav>
    <span class="pill"><span class="dot" aria-hidden="true"></span><span class="pill__word">Checked&nbsp;</span>{CHECKED_HUMAN}</span>
  </div>
</header>
<main id="main" class="wrap">
"""


def footer() -> str:
    return f"""</main>
<footer class="ftr">
  <div class="wrap">
    <div class="ftr__grid">
      <div>
        <a class="brand" href="/">{mark_svg(28)}{BRAND}</a>
        <p>Unofficial fan site for {GAME['name']}. Not affiliated with Roblox Corporation or {GAME['developer']}. Codes are cross-checked against the official game page and independent trackers, and every entry shows the date we last confirmed it.</p>
      </div>
      <nav aria-label="Footer">
        {''.join(f'<a href="{u}">{esc(t)}</a>' for u, t in FOOTER_LINKS)}
      </nav>
    </div>
    <div class="ftr__bottom">
      <span>Last checked {CHECKED_HUMAN} · dates in UTC</span>
      <span>© {CHECKED[:4]} {BRAND}</span>
    </div>
  </div>
</footer>
<div class="sr-only" id="copy-status" role="status" aria-live="polite"></div>
<script>{JS}</script>
</body>
</html>
"""


def code_card(c: dict) -> str:
    status = c["status"]
    badge = ('<span class="badge badge--ok">Confirmed</span>' if status == "confirmed"
             else '<span class="badge badge--warn">Reported</span>')
    tested = c.get("in_game_verified")
    tested_badge = (f'<span class="badge badge--tested">In-game tested {human(tested)}</span>'
                    if tested else "")
    n = len(c["sources"])
    src_txt = f"{n} independent sources" if n > 1 else "1 tracker only"
    return f"""<article class="code-card" data-status="{status}">
  <div class="code-card__top">
    {badge}
    {tested_badge}
    <span class="meta">{src_txt}</span>
    <span class="meta" aria-hidden="true">·</span>
    <span class="meta">Checked {human(c['last_verified'])}</span>
  </div>
  <div class="code-card__row">
    <div class="code-card__id">
      <div class="code">{esc(c['code'])}</div>
      <div class="reward"><b>{reward_text(c)}</b> · one per account</div>
    </div>
    <button class="btn-copy" type="button" data-copy="{esc(c['code'])}" data-label="Copy code">Copy code</button>
  </div>
  <p class="note">{esc(c['note'])}</p>
  <a class="report" href="{esc(report_href(c['code']))}">Report a problem with this code</a>
</article>"""


def faq_block(faqs: list[tuple[str, str]]) -> str:
    items = "".join(
        f"""<details>
  <summary>{esc(q)}</summary>
  <div class="faq__body"><p>{esc(a)}</p></div>
</details>"""
        for q, a in faqs
    )
    return f'<div class="faq">{items}</div>'


def breadcrumbs(slug: str, label: str) -> str:
    if slug == "/":
        return ""
    return (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a>'
            f'<span aria-hidden="true">/</span><span aria-current="page">{esc(label)}</span></nav>')


def base_jsonld(slug: str, title: str, desc: str) -> list[dict]:
    url = BASE + slug
    node = {
        "@type": "WebPage",
        "@id": url + "#webpage",
        "url": url,
        "name": title,
        "description": desc,
        "inLanguage": "en",
        "datePublished": "2026-11-15",
        "dateModified": CHECKED,
        "isPartOf": {"@id": BASE + "/#website"},
        "publisher": {"@id": BASE + "/#org"},
    }
    return [node]


def crumb_jsonld(slug: str, label: str) -> dict:
    return {
        "@type": "BreadcrumbList",
        "@id": BASE + slug + "#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": label, "item": BASE + slug},
        ],
    }


def faq_jsonld(slug: str, faqs: list[tuple[str, str]]) -> dict:
    return {
        "@type": "FAQPage",
        "@id": BASE + slug + "#faq",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }


def org_jsonld() -> list[dict]:
    return [
        {
            "@type": "Organization",
            "@id": BASE + "/#org",
            "name": BRAND,
            "url": BASE + "/",
            "description": "Independent code tracker for the Roblox game Drag Drive Simulator.",
        },
        {
            "@type": "WebSite",
            "@id": BASE + "/#website",
            "url": BASE + "/",
            "name": BRAND,
            "inLanguage": "en",
            "publisher": {"@id": BASE + "/#org"},
        },
    ]


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def page_home() -> dict:
    slug = "/"
    title = f"Drag Drive Simulator Codes ({TITLE_MONTH} {CHECKED[:4]}) — All Working Codes"
    desc = (f"All working Drag Drive Simulator codes for {TITLE_MONTH} {CHECKED[:4]}, checked against the official "
            f"Roblox page and independent trackers. Copy a code and redeem RP in seconds.")
    reported_note = (
        f" {count_word(len(UNCONFIRMED), True)} further "
        f"{'code is' if len(UNCONFIRMED) == 1 else 'codes are'} only reported by one tracker "
        f"({name_list(UNCONFIRMED)}) and may already be expired." if UNCONFIRMED else "")
    faqs = [
        ("Are there any working Drag Drive Simulator codes right now?",
         f"Yes. {count_word(len(ACTIVE), True)} codes were confirmed on {CHECKED_HUMAN} by the official Roblox game "
         f"page and at least two independent trackers: {name_list(ACTIVE)}.{reported_note}"),
        ("How much RP do all the codes give together?",
         f"Between {RP_MIN // 1_000_000} million and {RP_MAX // 1_000_000} million RP, depending on which tracker's "
         f"reward amounts are correct. Individual codes pay out between {SINGLE_MIN // 1_000_000} million and "
         f"{SINGLE_MAX // 1_000_000} million RP, and each code can only be redeemed once per account."),
        ("Where do I enter a code in Drag Drive Simulator?",
         "Join any server, tap the Shop (shopping cart) icon along the bottom edge of the screen, open the Redeem tab "
         "at the top of the shop, paste the code into the text box, then press Redeem. The RP is credited immediately."),
        ("Why is my code not working?",
         "The four usual reasons are: the code has expired, it was typed with a missing or extra character, you already "
         "redeemed it on that account, or you are in an old server that started before the code went live. Rejoin a new "
         "server and try again before assuming the code is dead."),
        ("When do new Drag Drive Simulator codes come out?",
         "The developer releases codes in three waves: a monthly code, a batch with each big update, and milestone codes "
         "tied to likes. The official page currently says the next code arrives at 200,000 likes, and the game had "
         "already passed 209,000 likes on 11 November 2026, so a new code is likely soon."),
        ("Do Drag Drive Simulator codes expire?",
         f"Yes. Monthly and milestone codes usually last a few weeks to a few months. {len(EXPIRED_2026)} codes from "
         f"2026 and the entire 2025 archive are already dead, and we keep them on a separate expired page so this list "
         f"stays usable."),
        ("Is this an official Drag Drive Simulator website?",
         f"No. {BRAND} is an independent fan site. We are not affiliated with Roblox Corporation or "
         f"{GAME['developer']}, and we cannot restore accounts, grant RP, or provide free Robux."),
    ]

    cards = "\n".join(code_card(c) for c in ACTIVE)
    reported = "\n".join(code_card(c) for c in UNCONFIRMED)

    body = f"""
{breadcrumbs(slug, 'Codes')}
<section class="hero">
  <p class="sec-label">Roblox · {GAME['name']}</p>
  <h1>Drag Drive Simulator Codes ({TITLE_MONTH} {CHECKED[:4]})</h1>
  <p class="lede">{count_word(len(ACTIVE), True)} codes are confirmed by the official Roblox game page and at least two independent trackers. No account, no survey, no Robux — every code below pays out in RP.</p>
  <div class="stats">
    <div class="stat"><b>{len(ACTIVE)}</b><span>Confirmed codes</span></div>
    <div class="stat"><b>{RP_MIN // 1_000_000}–{RP_MAX // 1_000_000}M</b><span>RP available</span></div>
    <div class="stat"><b>{CHECKED_HUMAN.split(' ')[0]} {CHECKED_HUMAN.split(' ')[1]}</b><span>Last checked</span></div>
  </div>
</section>

<h2>Working Drag Drive Simulator codes</h2>
<p>Every code below was confirmed on {CHECKED_HUMAN}. Copy a code, then paste it into the Redeem tab inside the game.</p>
{cards}

<div class="callout">
  <p><strong>How much you can trust this list.</strong> A code is marked <em>Confirmed</em> when the official game page
  names it and at least two independent trackers list it as working. We are not a player account, so we do not run an
  in-game test on every code. When sources disagree about a code, or readers report that one is dead, we redeem it
  inside the game ourselves and the card shows the date that test passed. Roblox codes can die without notice, so each
  card also shows the date we last checked it. Found a dead code? Use the report link on the card.</p>
</div>

{ad_unit("home-after-codes")}

<h2>How to redeem codes in Drag Drive Simulator</h2>
<ol class="steps">
  <li><b>Join a server</b><span>Open {GAME['name']} on Roblox from any device — phone, tablet, PC or console.</span></li>
  <li><b>Open the Shop</b><span>Tap the shopping-cart icon along the bottom edge of the screen, then choose the Redeem tab at the top.</span></li>
  <li><b>Paste and confirm</b><span>Codes are case-sensitive, so copy rather than type. A success message means the RP is already in your balance.</span></li>
</ol>
<p><a href="/how-to-redeem/">Full redeem walkthrough, including fixes for “invalid code” errors →</a></p>

<h2>Codes that may still work</h2>
<p>This one is listed as active by a single tracker and as expired by another. It costs nothing to try.</p>
{reported}

<h2>Expired Drag Drive Simulator codes</h2>
<p>{TOTAL_EXPIRED} codes are already dead, including every 2025 code and {len(EXPIRED_2026)} from 2026. They are archived on a separate page with their original RP values, so you can check whether an old code is worth trying before you type it.</p>
<p><a href="/expired-codes/">See the full expired code archive →</a></p>

<h2>When do new codes come out?</h2>
<p>{GAME['developer']} releases codes in three patterns, and knowing them is the fastest way to catch a new one early:</p>
<ul>
  <li><b>Monthly codes.</b> Named after the month, for example DRAGDRIVESIMULATORSEPTEMBER26. No October or November 2026 monthly code had appeared when we last checked.</li>
  <li><b>Update codes.</b> Each big update ships a batch. BETA V1.1.9 added five codes in one go.</li>
  <li><b>Like milestones.</b> The official game page says the next code drops at 200,000 likes. It had already passed 209,000 likes on 11 November 2026, so that code could land any day.</li>
</ul>
<p>New codes appear first in the game description on the <a href="{GAME['roblox_url']}" rel="noopener noreferrer" target="_blank">official Roblox page</a>, in the <a href="{GAME['discord_url']}" rel="noopener noreferrer" target="_blank">official Discord</a> (about 310,000 members), and in the <a href="{GAME['group_url']}" rel="noopener noreferrer" target="_blank">ADV Gamers Team group</a>. We check all three every day, and again within a few hours of any game update.</p>

<h2>Frequently asked questions</h2>
{faq_block(faqs)}

{ad_unit("home-end")}

<h2>Sources and verification</h2>
<ul class="sources">
  <li><a href="{GAME['roblox_url']}" rel="noopener noreferrer" target="_blank">Official {GAME['name']} page on Roblox</a> — game description and version notes, checked {CHECKED_HUMAN}.</li>
  <li>timesaver.gg — code list and weekly re-check note, dated 11 Nov 2026.</li>
  <li>rocodes.gg — code list including the 2025 archive, dated 31 Oct 2026.</li>
  <li>urgametips.com — reward amounts and the one unconfirmed code, dated Nov 2026.</li>
</ul>
<p class="note">Reward amounts differ between trackers by up to 10 million RP for some codes, so we show a range rather than a single number. Last checked {CHECKED_HUMAN} (UTC).</p>
"""

    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [
        faq_jsonld(slug, faqs),
        {
            "@type": "ItemList",
            "@id": BASE + "/#codes",
            "name": f"Active {GAME['name']} codes",
            "numberOfItems": len(ACTIVE),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": c["code"],
                 "description": f"{reward_text(c)} in {GAME['name']}"}
                for i, c in enumerate(ACTIVE)
            ],
        },
    ]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld, "out": "index.html"}


def page_redeem() -> dict:
    slug = "/how-to-redeem/"
    title = "How to Redeem Drag Drive Simulator Codes (Step by Step)"
    desc = ("Step-by-step guide to redeeming Drag Drive Simulator codes on phone or PC, where the Redeem button is, "
            "and fixes for codes that say invalid.")
    faqs = [
        ("Where is the Redeem button in Drag Drive Simulator?",
         "Open the Shop with the shopping-cart icon along the bottom edge of the screen. The Redeem tab sits at the top "
         "of the shop window. Tracker guides disagree about whether the cart is bottom-left or bottom-right because the "
         "layout changed between versions, so scan the whole bottom edge."),
        ("Are Drag Drive Simulator codes case-sensitive?",
         "Yes. Codes are long strings of capital letters and must match exactly, with no spaces before or after. Copy and "
         "paste instead of typing, especially on mobile."),
        ("Can I redeem the same code twice?",
         "No. Each code can be redeemed once per Roblox account. A code that worked for a friend will still show as "
         "invalid for you if you have already claimed it."),
    ]
    body = f"""
{breadcrumbs(slug, 'How to redeem')}
<section class="hero">
  <p class="sec-label">Step by step</p>
  <h1>How to Redeem Drag Drive Simulator Codes</h1>
  <p class="lede">Redeeming a code takes about 30 seconds and works the same on phone, tablet, PC and console. You need an account that has joined the game at least once.</p>
</section>

<h2>The five steps</h2>
<ol class="steps">
  <li><b>Launch the game</b><span>Open {GAME['name']} on Roblox and wait until you spawn in a server. Codes cannot be redeemed from the Roblox website.</span></li>
  <li><b>Find the Shop icon</b><span>It is a shopping-cart button sitting along the bottom edge of the HUD. It is not the vehicle key, and it is not the in-game phone.</span></li>
  <li><b>Open the Redeem tab</b><span>The tab is at the top of the shop window, next to the normal vehicle and upgrade sections.</span></li>
  <li><b>Paste the code</b><span>Copy it from <a href="/">our working codes list</a> using the Copy button, then paste with Ctrl+V on PC or a long-press on mobile. Codes are case-sensitive and must not contain spaces.</span></li>
  <li><b>Press Redeem</b><span>A success toast confirms the RP was added. A failure toast usually means the code is invalid or already used.</span></li>
</ol>

<div class="callout callout--ok">
  <p><strong>Fastest path:</strong> copy the code, keep this tab open, switch to Roblox, open Shop → Redeem, paste, confirm. You can redeem all {count_word(len(ACTIVE))} confirmed codes one after another without leaving the server.</p>
</div>

{ad_unit("redeem-mid")}

<h2>Why does my code say invalid?</h2>
<p>Work through these in order — the first four are far more common than a genuinely dead code.</p>

<h3>1. A typo or stray space</h3>
<p>These codes are 20 to 33 characters of capital letters. One wrong character or a trailing space from a copied paragraph is enough to fail. Delete the field and paste again.</p>

<h3>2. You already claimed it</h3>
<p>Every code is limited to one redemption per account. If you redeemed it on the same account months ago, it will read as invalid even though it is still live for other players.</p>

<h3>3. You are in an old server</h3>
<p>A server that started before the code went live will not recognise it. Leave the game, join a fresh server, and try once more.</p>

<h3>4. Your client is out of date</h3>
<p>Close Roblox completely, reopen it, and rejoin. Update codes ship with a game version and older clients sometimes reject them.</p>

<h3>5. The code really has expired</h3>
<p>Monthly and milestone codes are retired without much warning. Check the <a href="/expired-codes/">expired archive</a> before spending more time on it, then go back to the <a href="/">active list</a>.</p>

<div class="callout callout--warn">
  <p><strong>Do not use “code generators”.</strong> Any site or app that asks for your Roblox login to generate RP or Robux is a scam. Real codes are posted publicly by the developer and are typed into the in-game Redeem tab — never into a third-party site.</p>
</div>

<h2>Related pages</h2>
<ul>
  <li><a href="/">All working Drag Drive Simulator codes</a></li>
  <li><a href="/expired-codes/">Expired codes archive (2025 and 2026)</a></li>
  <li><a href="/rp-guide/">What RP is and how to earn more of it</a></li>
  <li><a href="/updates/">Update history and which update added which code</a></li>
</ul>

<h2>Frequently asked questions</h2>
{faq_block(faqs)}

<h2>Sources</h2>
<ul class="sources">
  <li>Official {GAME['name']} page on Roblox — version and code announcements, checked {CHECKED_HUMAN}.</li>
  <li>timesaver.gg and rocodes.gg — redemption steps and failure reasons, November 2026.</li>
</ul>
<p class="note">Last checked {CHECKED_HUMAN} (UTC).</p>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [
        crumb_jsonld(slug, "How to redeem"), faq_jsonld(slug, faqs)]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "how-to-redeem/index.html"}


def page_expired() -> dict:
    slug = "/expired-codes/"
    title = "Expired Drag Drive Simulator Codes — Full 2025 & 2026 Archive"
    desc = ("The full archive of expired Drag Drive Simulator codes from 2025 and 2026, with their RP values, so you "
            "never waste time typing a dead code.")
    rows26 = "".join(
        f'<tr><td class="code-cell">{esc(c["code"])}</td><td class="num">{c["reward"]:,}</td>'
        f'<td>Reported expired</td></tr>' for c in EXPIRED_2026)
    def reward_cell(c: dict) -> str:
        return f"{c['reward']:,}" if c["reward"] else "Not recorded"

    rows25 = "".join(
        f'<tr><td class="code-cell">{esc(c["code"])}</td>'
        f'<td class="num">{reward_cell(c)}</td>'
        f'<td>{human(c["expired_on"])}</td></tr>' for c in EXPIRED_2025)

    faqs = [
        ("Can an expired Drag Drive Simulator code come back?",
         "Almost never. The developer retires codes permanently when the event they belong to ends, so a code marked "
         "expired by several trackers will not start working again. New codes are issued instead."),
        ("How do you decide a code is expired?",
         "We mark a code expired when at least two independent trackers list it as expired, or when the developer has "
         "already replaced it with a newer batch. Codes are never deleted from this page, so you can always check an old "
         "code you found in a video or comment."),
    ]
    body = f"""
{breadcrumbs(slug, 'Expired codes')}
<section class="hero">
  <p class="sec-label">Archive</p>
  <h1>Expired Drag Drive Simulator Codes</h1>
  <p class="lede">Every code below has stopped working. We keep them so you can check an old code before wasting time on it — and so the <a href="/">active list</a> stays short enough to use.</p>
</section>

<div class="stats">
  <div class="stat"><b>{len(EXPIRED_2026)}</b><span>Expired in 2026</span></div>
  <div class="stat"><b>{len(EXPIRED_2025)}</b><span>Archived from 2025</span></div>
  <div class="stat"><b>{len(ACTIVE)}</b><span>Still working</span></div>
</div>

<h2>2026 codes</h2>
<p>All of these were marked expired by at least two trackers when we checked on {CHECKED_HUMAN}. Our sources do not publish exact expiry dates for this batch, so we do not invent them.</p>
<div class="table-scroll">
<table>
  <caption class="sr-only">Expired Drag Drive Simulator codes from 2026</caption>
  <thead><tr><th scope="col">Code</th><th scope="col">Original reward (RP)</th><th scope="col">Status</th></tr></thead>
  <tbody>{rows26}</tbody>
</table>
</div>

<h2>2025 codes</h2>
<p>Expiry dates for this batch are recorded by rocodes.gg. Some very old codes never had their reward amount documented, and those are marked as not recorded rather than guessed.</p>
<div class="table-scroll">
<table>
  <caption class="sr-only">Expired Drag Drive Simulator codes from 2025</caption>
  <thead><tr><th scope="col">Code</th><th scope="col">Original reward (RP)</th><th scope="col">Expired on</th></tr></thead>
  <tbody>{rows25}</tbody>
</table>
</div>

{ad_unit("expired-after-tables")}

<h2>Why do these codes stop working?</h2>
<p>Drag Drive Simulator is still in beta, and its codes are tied to events rather than to permanent promotions:</p>
<ul>
  <li><b>Monthly codes</b> are retired when the next month's code replaces them.</li>
  <li><b>Update codes</b> usually survive one or two update cycles, then get swapped for the new batch.</li>
  <li><b>Milestone codes</b> are limited by design — they exist to reward players for hitting a like target.</li>
</ul>
<p>Each code is also capped at one redemption per account, which is why a code can be “working” for a friend and invalid for you.</p>

<h2>How to get RP without a working code</h2>
<p>Codes are the fastest boost — the current batch is worth {RP_MIN // 1_000_000}–{RP_MAX // 1_000_000} million RP — but you can still earn RP in game through jobs and races. Our <a href="/rp-guide/">RP guide</a> covers the job types, what to spend RP on after the V1.1.9 update, and why you should never buy “RP generators”.</p>

<div class="callout">
  <p><strong>Looking for the current batch?</strong> The {count_word(len(ACTIVE))} confirmed codes are on the <a href="/">Drag Drive Simulator codes page</a>, each with the date we last checked it.</p>
</div>

<h2>Frequently asked questions</h2>
{faq_block(faqs)}

<h2>Sources</h2>
<ul class="sources">
  <li>rocodes.gg — 2025 expiry dates, list checked 31 Oct 2026.</li>
  <li>timesaver.gg — 2026 expired batch and RP values, dated 11 Nov 2026.</li>
  <li>Official {GAME['name']} page on Roblox — current version, checked {CHECKED_HUMAN}.</li>
</ul>
<p class="note">Last checked {CHECKED_HUMAN} (UTC).</p>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [
        crumb_jsonld(slug, "Expired codes"), faq_jsonld(slug, faqs)]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "expired-codes/index.html"}


def page_rp() -> dict:
    slug = "/rp-guide/"
    title = "What Is RP in Drag Drive Simulator? Earn & Spend Guide"
    desc = ("What RP means in Drag Drive Simulator, how much the codes pay, the fastest ways to earn RP, and what to "
            "spend it on after the V1.1.9 update.")
    faqs = [
        ("What does RP stand for in Drag Drive Simulator?",
         "RP is the game's main soft currency, the cash you spend on cars, motorbikes, garage space and modifications. "
         "It is not Robux and cannot be converted into Robux."),
        ("Do codes give Robux or RP?",
         "RP only. No legitimate Drag Drive Simulator code grants Robux. Anything promising free Robux in exchange for "
         "your password or a survey is a scam."),
    ]
    body = f"""
{breadcrumbs(slug, 'RP guide')}
<section class="hero">
  <p class="sec-label">Currency guide</p>
  <h1>What Is RP in Drag Drive Simulator?</h1>
  <p class="lede">RP is the game's cash. Codes are the fastest way to get it, but knowing what to spend it on matters more than the number in your balance.</p>
</section>

<h2>RP in one paragraph</h2>
<p>RP is the main soft currency in {GAME['name']} ({GAME['aliases']}). You earn it by working jobs, racing and pulling stunts, then spend it on cars, motorbikes, garage slots and modifications. It is separate from Robux: RP is earned in game, Robux is bought with real money and only used for game passes.</p>

<h2>How much RP the current codes give</h2>
<p>The {count_word(len(ACTIVE))} confirmed codes are worth <b>{RP_MIN // 1_000_000}–{RP_MAX // 1_000_000} million RP</b> in total, depending on which tracker's reward amounts are accurate. That is enough to skip a large part of the early grind and buy a competitive car plus a first round of modifications.</p>
<p><a href="/">See the working codes and copy them →</a></p>

<h2>Other ways to earn RP</h2>
<p>Outside of codes, RP comes from in-game jobs. Tracker guides currently list courier, office worker, barista and police work, and the game's description emphasises roleplay alongside racing. Job payouts and the exact list change between updates, so treat that as a starting set rather than a fixed tier list.</p>
<p>RP is also earned from racing and stunt driving, which is where the V1.1.9 wheelie system comes in: five wheelie styles with speed and angle tuning, plus a dedicated wheelie camera.</p>

<h2>What to spend RP on</h2>
<ul>
  <li><b>A fast car or bike first.</b> Vehicles are the biggest single purchase and the main gate on earning speed.</li>
  <li><b>Garage slots.</b> More slots means you stop selling cars to make room for the next one.</li>
  <li><b>Modifications.</b> V1.1.9 reworked rims into wide rim types, materials and accessories, and added a new modification system. Cosmetic, but it is what most players spend on after the first car.</li>
  <li><b>Not on passes.</b> Game passes are bought with Robux, so RP does nothing for them.</li>
</ul>

<div class="callout callout--warn">
  <p><strong>RP cannot buy game passes.</strong> Passes such as 2x Paycheck, Police Pass or Luxury Pass are Robux purchases inside the Roblox store. If a site offers to sell you a pass for RP, it is not legitimate.</p>
</div>

{ad_unit("rp-mid")}

<h2>RP vs Robux: what each one buys</h2>
<div class="table-scroll">
<table>
  <caption class="sr-only">RP and Robux compared</caption>
  <thead><tr><th scope="col">Currency</th><th scope="col">How you get it</th><th scope="col">What it buys</th></tr></thead>
  <tbody>
    <tr><td>RP</td><td>Jobs, racing, codes</td><td>Cars, bikes, garage slots, modifications</td></tr>
    <tr><td>Robux</td><td>Purchased from Roblox</td><td>Game passes such as 2x Paycheck, Police Pass, Luxury Pass, DragSpec Pass</td></tr>
  </tbody>
</table>
</div>
<p class="note">Game pass prices change and are set by the developer. We do not list prices here because they are frequently rebalanced and a stale price is worse than none.</p>

<h2>Why there is no such thing as a free Robux code</h2>
<p>Drag Drive Simulator codes only ever pay RP. Any page, video or app claiming to generate Robux, asking for your Roblox password, or requesting a “verification” step is trying to take your account. The only safe place to enter a code is the Redeem tab inside the game.</p>

<h2>Related pages</h2>
<ul>
  <li><a href="/">Working codes, checked {CHECKED_HUMAN}</a></li>
  <li><a href="/how-to-redeem/">How to redeem a code without errors</a></li>
  <li><a href="/updates/">What changed in each update</a></li>
</ul>

<h2>Frequently asked questions</h2>
{faq_block(faqs)}

<h2>Sources</h2>
<ul class="sources">
  <li>Official {GAME['name']} page on Roblox — V1.1.9 feature list and version, checked {CHECKED_HUMAN}.</li>
  <li>timesaver.gg — RP uses, job types and game pass context, dated 11 Nov 2026.</li>
</ul>
<p class="note">Last checked {CHECKED_HUMAN} (UTC).</p>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [
        crumb_jsonld(slug, "RP guide"), faq_jsonld(slug, faqs)]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "rp-guide/index.html"}


def page_updates() -> dict:
    slug = "/updates/"
    title = "Drag Drive Simulator Update History & Codes (V1.1.6–V1.1.9)"
    desc = ("Drag Drive Simulator update history from V1.1.6 to V1.1.9, which codes each update added, and when the "
            "next code is expected.")
    faqs = [
        ("What is the latest Drag Drive Simulator update?",
         "BETA V1.1.9, the Wheelie Style x Big Update. It added a wheelie trick system with five styles, the Gatsu Street "
         "map expansion in Surakarta, six limited special vehicles, a reworked rim and modification system, a new vehicle "
         "camera and five redeem codes."),
        ("Did the October 2026 update add a code?",
         "No October code has appeared. The developer's event schedule lists updates at the end of June, July, August and "
         "September 2026, with no October entry, and no tracker lists a DRAGDRIVESIMULATOROCTOBER26 code."),
    ]
    body = f"""
{breadcrumbs(slug, 'Updates')}
<section class="hero">
  <p class="sec-label">Version log</p>
  <h1>Drag Drive Simulator Update History</h1>
  <p class="lede">Codes ship with updates. This page maps each version to the codes it introduced, so you can tell whether an old code you found is from a batch that has already been retired.</p>
</section>

<h2>Version timeline</h2>
<div class="table-scroll">
<table>
  <caption class="sr-only">Drag Drive Simulator update history</caption>
  <thead><tr><th scope="col">Version</th><th scope="col">Date</th><th scope="col">What changed</th><th scope="col">Codes</th></tr></thead>
  <tbody>
    <tr>
      <td><b>BETA V1.1.9</b><br><span class="meta">Wheelie Style x Big Update</span></td>
      <td>27 Sep 2026<br><span class="meta">page updated 9 Nov 2026</span></td>
      <td>Wheelie trick system with 5 styles, Gatsu Street map expansion, 6 limited special vehicles, new standard cars and bikes, reworked rims and modification system, first-person and 360 action camera, favourite vehicle spawner</td>
      <td>5 codes added — the five now confirmed: DRAGDRIVESIMULATORSEPTEMBER26, HBDADVGAMERSTEAM26, DDSWHEELIESTYLEUPDATE, NEWGATSUMAPNEWMODIFICATION, DELAYDIKITLAGIFREESTYLE</td>
    </tr>
    <tr>
      <td><b>V1.1.8</b></td><td>29 Aug 2026</td>
      <td>Not documented by our sources</td>
      <td>DRAGDRIVESIMULATORAUGUST26 (expired)</td>
    </tr>
    <tr>
      <td><b>V1.1.7</b></td><td>31 Jul 2026</td>
      <td>Not documented by our sources</td>
      <td>DRAGDRIVESIMULATORJULY26 (expired)</td>
    </tr>
    <tr>
      <td><b>V1.1.6</b></td><td>28 Jun 2026</td>
      <td>Not documented by our sources</td>
      <td>DRAGDRIVESIMULATORJUNE26 (expired)</td>
    </tr>
    <tr>
      <td><b>Launch</b></td><td>15 Jan 2025</td>
      <td>Game created by {GAME['developer']}</td>
      <td>Early 2025 codes, all expired</td>
    </tr>
  </tbody>
</table>
</div>
<p class="note">Update dates come from the developer's event schedule as reported by timesaver.gg. The monthly code attached to each version is inferred from the naming pattern, not from a per-update announcement, so treat that column as a guide rather than a record.</p>

{ad_unit("updates-mid")}

<h2>The October gap</h2>
<p>Updates landed at the end of June, July, August and September 2026. There is no October entry in the event schedule, and no tracker lists a DRAGDRIVESIMULATOROCTOBER26 code. That gap is one reason the September batch is still the current one — and why the next milestone code matters.</p>

<h2>What should arrive next</h2>
<p>The official game description says the next code is tied to <b>200,000 likes</b>. On 11 November 2026 the game already showed more than 209,000 likes, so the milestone has technically been passed and the code is overdue. When it lands it will appear first in three places:</p>
<ul>
  <li>The game description on the <a href="{GAME['roblox_url']}" rel="noopener noreferrer" target="_blank">official Roblox page</a>.</li>
  <li>The <a href="{GAME['discord_url']}" rel="noopener noreferrer" target="_blank">official Discord</a> announcements channel.</li>
  <li>The <a href="{GAME['group_url']}" rel="noopener noreferrer" target="_blank">ADV Gamers Team group</a> page.</li>
</ul>
<p>We check all three every day and again after each update, and update the <a href="/">active code list</a> with the date we confirmed it.</p>

<h2>How updates affect existing codes</h2>
<p>A new version usually retires the previous batch. Codes from V1.1.9 are the ones working now; anything named after an earlier month has already been moved to the <a href="/expired-codes/">expired archive</a>. If you find a code in an old video, check the archive before typing it.</p>

<h2>Frequently asked questions</h2>
{faq_block(faqs)}

<h2>Sources</h2>
<ul class="sources">
  <li>Official {GAME['name']} page on Roblox — version name, feature list and code announcement, checked {CHECKED_HUMAN}.</li>
  <li>timesaver.gg — update dates, likes count and code batches, dated 11 Nov 2026.</li>
  <li>rocodes.gg — historical code archive, checked 31 Oct 2026.</li>
</ul>
<p class="note">Last checked {CHECKED_HUMAN} (UTC).</p>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [
        crumb_jsonld(slug, "Updates"), faq_jsonld(slug, faqs)]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "updates/index.html"}


def page_about() -> dict:
    slug = "/about/"
    title = f"About {BRAND} — How We Verify Codes"
    desc = (f"How {BRAND} verifies Drag Drive Simulator codes, what our confirmation labels mean, what we do not do, "
            f"and how quickly a dead code report gets corrected.")
    body = f"""
{breadcrumbs(slug, 'About')}
<section class="hero">
  <p class="sec-label">About</p>
  <h1>How We Verify Drag Drive Simulator Codes</h1>
  <p class="lede">{BRAND} is an independent, single-purpose site: it tracks the codes for one Roblox game and nothing else. This page explains exactly what our labels mean, so you can judge the list yourself.</p>
</section>

<h2>What we do</h2>
<p>We read the official {GAME['name']} page on Roblox, the developer's Discord announcements and a small set of established code trackers, then reconcile them. When sources disagree — which they often do on reward amounts — we show a range instead of picking the most flattering number.</p>
<p>When a code is disputed, or a reader reports that one has stopped working, we redeem it inside the game ourselves and record the date. That in-game check is an extra piece of evidence, not a replacement for the source check — see the labels below.</p>

<h2>What the labels mean</h2>
<p>Every code on this site is in one of three states. The <span class="badge badge--tested">In-game tested</span> badge is not a fourth state: it is an extra marker that only appears on codes we have personally redeemed in the game.</p>
<div class="table-scroll">
<table>
  <caption class="sr-only">How codes are labelled</caption>
  <thead><tr><th scope="col">Label</th><th scope="col">Condition</th><th scope="col">What to expect</th></tr></thead>
  <tbody>
    <tr><td><span class="badge badge--ok">Confirmed</span></td><td>The official game page names the code and at least two independent trackers list it as working</td><td>Very likely to work. Each card shows the date we last checked it.</td></tr>
    <tr><td><span class="badge badge--tested">In-game tested</span></td><td>We redeemed the code on a real account inside {GAME['name']}, the RP balance rose by the stated amount, and we logged the date</td><td>Strongest evidence we can show. Only some codes carry it — we do not test every code on every check.</td></tr>
    <tr><td><span class="badge badge--warn">Reported</span></td><td>Only one tracker lists it, and the official page does not mention it</td><td>Might work. We keep it separate and label it clearly.</td></tr>
    <tr><td><span class="badge badge--dead">Expired</span></td><td>At least two trackers mark it expired, or the developer has replaced it</td><td>Will not work. Moved to the archive, never deleted.</td></tr>
  </tbody>
</table>
</div>
<p>A test only counts as passed when all three things happen: the code is accepted inside the game, the balance increases by the amount shown on the card, and the date is written to the card. If a code is rejected in game, we do not keep it at Confirmed just because the trackers still list it.</p>

<h2>What we do not do</h2>
<ul>
  <li>We do not claim that every code has been tested in game. Most entries are confirmed from official and tracker sources only, and the badge tells you which is which.</li>
  <li>We do not publish a reward amount we cannot trace to a source. Where sources disagree, you see a range.</li>
  <li>We do not offer free Robux, generators, or anything that asks for your Roblox password.</li>
  <li>We do not claim to be official. {BRAND} is not affiliated with Roblox Corporation or {GAME['developer']}.</li>
</ul>

<h2>Why other sites list 50+ “active” codes</h2>
<p>Some trackers keep a very long active list that mixes current codes with 2025 codes other sources mark as expired. A list of 50 codes looks generous, but it wastes the reader's time when most of them fail. We would rather show {count_word(len(ACTIVE))} codes that are confirmed than fifty that are not.</p>

<h2>How often this site is updated</h2>
<ul>
  <li><b>Every day.</b> One full pass over the official Roblox page, the developer's Discord announcements and the group page, plus every tracker we cite.</li>
  <li><b>Within a few hours of a game update or a new code announcement.</b> We do not wait for the next daily pass.</li>
  <li><b>Within 48 hours of a verified reader report.</b> Dead codes are demoted and moved rather than left up.</li>
</ul>
<p>That is the whole schedule — there is no quieter “weekly” mode. The date in the header of every page is the date of the last full pass, not the date the site was built.</p>

<h2>Corrections</h2>
<p>If a code fails for you, if a reward amount is wrong, or if you spot a new code before we do, email <a href="mailto:{EMAIL}">{EMAIL}</a> with the code and roughly when you tried it. Corrections are the fastest way to improve this site.</p>

<div class="callout">
  <p><strong>Editorial policy in one line:</strong> every claim about a code should be traceable to the official game page or to at least two named trackers, and every page should say when it was last checked.</p>
</div>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [crumb_jsonld(slug, "About")]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "about/index.html"}


def page_privacy() -> dict:
    slug = "/privacy/"
    title = f"Privacy Policy — {BRAND}"
    desc = (f"How {BRAND} handles data: no accounts, no tracking cookies today, what the host logs contain, and what "
            f"changes before any advertising is enabled.")
    body = f"""
{breadcrumbs(slug, 'Privacy')}
<section class="hero">
  <p class="sec-label">Legal</p>
  <h1>Privacy Policy</h1>
  <p class="lede">Effective {CHECKED_HUMAN}. This policy describes what this site does today, not what it might do later.</p>
</section>

<h2>What this site collects</h2>
<p>{BRAND} is a static website. It has no accounts, no comment system, no newsletter and no contact form. We do not ask for your name, email address, Roblox username or password, and we do not store any of them.</p>

<h2>Cookies and analytics</h2>
<p>This site sets no cookies of its own and currently runs no analytics or tracking scripts. The hosting provider may keep standard server logs, including IP address, browser type and requested URL, for security and abuse prevention. Those logs are controlled by the host, not by us.</p>

<h2>Advertising</h2>
<p>The page layout reserves space for advertising, but no ad code is installed right now. If third-party advertising such as Google AdSense is enabled in future, Google and its partners may use cookies or similar technologies to serve and measure ads, and this policy will be updated before that happens. You will then be able to opt out of personalised advertising through Google's Ads Settings and, where required, through a consent prompt.</p>

<h2>Children</h2>
<p>This site publishes general information about a game that is popular with younger players. It is written for a general audience and does not knowingly collect personal information from anyone, including children under 13. Because there is no account system and no form, there is no personal data to delete. If you believe a child has sent us personal information by email, contact us and we will delete it.</p>

<h2>External links</h2>
<p>Pages link to Roblox, Discord, the developer's group and other code trackers. Those sites have their own privacy policies, and we are not responsible for their content or data practices.</p>

<h2>Changes</h2>
<p>If this policy changes, the effective date at the top of this page will change with it. Material changes — such as enabling advertising or analytics — will be reflected here before they take effect.</p>

<h2>Contact</h2>
<p>Questions about this policy: <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [crumb_jsonld(slug, "Privacy")]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "privacy/index.html"}


def page_contact() -> dict:
    slug = "/contact/"
    title = f"Contact — {BRAND}"
    desc = ("Report a dead Drag Drive Simulator code, a wrong RP reward, or send a new code tip. One email address, "
            "read by a human, with code reports handled within 48 hours.")
    body = f"""
{breadcrumbs(slug, 'Contact')}
<section class="hero">
  <p class="sec-label">Contact</p>
  <h1>Report a Code or a Correction</h1>
  <p class="lede">One email address, read by a human. The most useful reports are the shortest ones.</p>
</section>

<h2>Email</h2>
<p><a href="mailto:{EMAIL}">{EMAIL}</a></p>

<h2>What to send</h2>
<p>The report link under each code opens a pre-filled email with the code already in the subject line, so you only need to add what went wrong. If you are writing from scratch, include the code in the subject.</p>
<ul>
  <li><b>A dead code.</b> Send the code and roughly when you tried it, plus your platform if you can.</li>
  <li><b>A wrong reward.</b> Send the code, the amount you actually received, and where you saw the other figure.</li>
  <li><b>A new code.</b> Send the code and a link to where the developer posted it. Screenshots of the game description work well.</li>
  <li><b>A correction to a page.</b> Send the URL and the sentence that is wrong.</li>
</ul>

<h2>What we cannot help with</h2>
<p>We are an independent fan site, not Roblox support and not the developer. We cannot restore a lost account, grant RP, unban you, or recover missing purchases. For account issues, use Roblox support or the {GAME['developer']} Discord.</p>

<h2>Response time</h2>
<p>Code reports are usually handled within 48 hours, and always before the next daily check. We do not send a reply to every report, but every one is read.</p>

<div class="callout callout--warn">
  <p><strong>Never send your Roblox password.</strong> No one from this site will ever ask for it, and no legitimate code requires it.</p>
</div>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc) + [crumb_jsonld(slug, "Contact")]
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "contact/index.html"}


def page_404() -> dict:
    slug = "/404.html"
    title = f"Page not found — {BRAND}"
    desc = (f"That page does not exist on {BRAND}. Jump back to the working Drag Drive Simulator codes, the expired "
            f"archive, or the step-by-step redeem guide.")
    body = f"""
<section class="hero">
  <p class="sec-label">404</p>
  <h1>That page does not exist</h1>
  <p class="lede">The link may be old, or the page may have been renamed. The working codes are one click away.</p>
  <div class="callout">
    <p><a href="/">Working Drag Drive Simulator codes</a> · <a href="/expired-codes/">Expired archive</a> · <a href="/how-to-redeem/">How to redeem</a> · <a href="/rp-guide/">RP guide</a></p>
  </div>
</section>
"""
    jsonld = org_jsonld() + base_jsonld(slug, title, desc)
    return {"slug": slug, "title": title, "desc": desc, "body": body, "jsonld": jsonld,
            "out": "404.html", "noindex": True}


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------

def _blend(base: str, top: str, alpha: float) -> str:
    """Flatten `top` over `base` at `alpha`, for Pillow (which has no fill-opacity)."""
    a = tuple(int(base[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(top[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(round(a[i] + (b[i] - a[i]) * alpha) for i in range(3))


def draw_mark(d, x: float, y: float, size: float) -> None:
    """Raster twin of mark_svg(), same 40x40 geometry (used by og.png and the .ico)."""
    s = size / 40.0
    d.rounded_rectangle([x + 0.8 * s, y + 0.8 * s, x + 39.2 * s, y + 39.2 * s],
                        radius=10 * s, fill=MARK_BADGE,
                        outline=_blend(MARK_BADGE, MARK_ACCENT, .38),
                        width=max(1, round(1.6 * s)))
    for ox in (6.8, 21.2):
        cx, cy, r = x + (ox + 4) * s, y + 20 * s, 8 * s
        d.rectangle([x + ox * s, y + 12 * s, cx, y + 28 * s], fill=MARK_ACCENT)
        d.pieslice([cx - r, cy - r, cx + r, cy + r], -90, 90, fill=MARK_ACCENT)
        ir = 4.4 * s
        d.pieslice([cx - ir, cy - ir, cx + ir, cy + ir], -90, 90, fill=MARK_BADGE)
    d.rounded_rectangle([x + 8.8 * s, y + 31 * s, x + 31.2 * s, y + 32.6 * s],
                        radius=max(1, round(.8 * s)),
                        fill=_blend(MARK_BADGE, MARK_ACCENT, .55))


def build_icon(path: Path) -> None:
    """Raster fallback for browsers without SVG favicon support."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("! Pillow not installed, skipping favicon.ico")
        return
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(img), 0, 0, 256)
    img.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])


def build_og_image(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("! Pillow not installed, skipping og.png")
        return

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#0A0D12")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 6], fill="#C8FF3D")
    draw_mark(d, 64, 68, 76)

    def font(names, size):
        for n in names:
            p = Path("C:/Windows/Fonts") / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
        return ImageFont.load_default()

    f_brand = font(["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"], 34)
    f_h1 = font(["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"], 66)
    f_sub = font(["segoeui.ttf", "arial.ttf"], 30)
    f_mono = font(["consolab.ttf", "consola.ttf", "courbd.ttf"], 28)

    d.text((156, 84), BRAND, font=f_brand, fill="#E8EDF5")
    d.text((64, 190), GAME["name"], font=f_h1, fill="#E8EDF5")
    d.text((64, 272), "Codes", font=f_h1, fill="#C8FF3D")
    d.text((66, 372), f"{len(ACTIVE)} confirmed codes  ·  checked {CHECKED_HUMAN}", font=f_sub, fill="#98A4B7")
    d.rounded_rectangle([64, 452, 1136, 542], radius=12, fill="#11161F", outline="#232C3A", width=2)
    d.text((88, 476), ACTIVE[0]["code"], font=f_mono, fill="#E8EDF5")
    d.text((64, 570), "Unofficial fan site · not affiliated with Roblox or ADV Gamers Team", font=font(["segoeui.ttf"], 20), fill="#6E7B8F")
    img.save(path, "PNG", optimize=True)


def build_local(pages: list, p404: dict) -> None:
    """Flat, relative-linked twin of dist/ so double-clicking index.html works.

    Why a second tree instead of changing dist/: under file:// a root-absolute link
    ("/about/") resolves against the drive root (file:///E:/about/), and a relative
    directory link ("about/") only shows Chrome's directory listing -- neither is
    fixable by link syntax alone. dist/ therefore keeps the absolute, trailing-slash
    URLs that canonical/OG/sitemap depend on; this tree exists only for local preview.
    """
    if LOCAL_DIST.exists():
        shutil.rmtree(LOCAL_DIST)
    LOCAL_DIST.mkdir(parents=True)
    written = []
    for p in pages + [p404]:
        name = LOCAL_NAMES.get(p["slug"], p["out"].replace("/", "-"))
        html = head(p["title"], p["desc"], p["slug"], p["jsonld"], p.get("noindex", False))
        html += p["body"] + footer()
        (LOCAL_DIST / name).write_text(localize_html(html), encoding="utf-8")
        written.append(name)
    for asset in ("favicon.ico", "og.png"):
        src = DIST / asset
        if src.exists():
            shutil.copy2(src, LOCAL_DIST / asset)
    print(f"  local preview: {len(written)} flat pages + favicon.ico/og.png -> {LOCAL_DIST.name}/")
    print(f"  double-click {LOCAL_DIST.name}\\index.html to browse offline")


def build() -> None:
    # Validate before touching dist/, so a failed build leaves the last good site in place.
    validate_data()
    validate_ads()

    pages = [page_home(), page_redeem(), page_expired(), page_rp(),
             page_updates(), page_about(), page_privacy(), page_contact()]
    validate_copy(pages)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    for p in pages:
        html = head(p["title"], p["desc"], p["slug"], p["jsonld"], p.get("noindex", False))
        html += p["body"] + footer()
        out = DIST / p["out"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"  wrote {p['out']:<32} {len(html.encode('utf-8')) / 1024:.1f} KB")

    p404 = page_404()
    html = head(p404["title"], p404["desc"], p404["slug"], p404["jsonld"], True)
    html += p404["body"] + footer()
    (DIST / "404.html").write_text(html, encoding="utf-8")
    print(f"  wrote {'404.html':<32} {len(html.encode('utf-8')) / 1024:.1f} KB")

    urls = [(p["slug"], p.get("out", "")) for p in pages if p["slug"] != "/"]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    entries = [("/", "1.0")] + [(s, "0.8" if s == "/how-to-redeem/" else "0.6") for s, _ in urls]
    priority = {"/": "1.0", "/how-to-redeem/": "0.8", "/expired-codes/": "0.7"}
    for slug, _ in entries:
        sitemap.append("  <url>")
        sitemap.append(f"    <loc>{BASE}{slug}</loc>")
        sitemap.append(f"    <lastmod>{CHECKED}</lastmod>")
        sitemap.append(f"    <priority>{priority.get(slug, '0.6')}</priority>")
        sitemap.append("  </url>")
    sitemap.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")
    print("  wrote sitemap.xml")

    (DIST / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        f"Sitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    print("  wrote robots.txt")

    if ADS_ON:
        # Publisher ID is only ever written when ads are actually enabled, and it
        # comes from data/site.json -- never a fabricated value.
        pub = ADS_CLIENT.removeprefix("ca-")
        (DIST / "ads.txt").write_text(
            f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
        print(f"  wrote ads.txt (authorised seller {pub})")
    else:
        (DIST / "ads.txt").write_text(
            "# ads.txt placeholder\n"
            "# Ads are disabled in data/site.json, so no seller is authorised yet.\n"
            "# Set ads.enabled=true with ads.client/ads.slots, then rebuild to publish a seller line.\n",
            encoding="utf-8")
        print("  wrote ads.txt (placeholder, no publisher ID)")

    build_og_image(DIST / "og.png")
    print("  wrote og.png")

    build_icon(DIST / "favicon.ico")
    if (DIST / "favicon.ico").exists():
        print("  wrote favicon.ico (16/32/48 raster fallback)")

    # Cloudflare Pages: _headers applies static response headers. CSP is deliberately
    # absent -- the site has inline <style>/<script> and a data: URI favicon, and a
    # wrong CSP silently breaks the copy buttons. Add it only after testing it.
    (DIST / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  X-Frame-Options: DENY\n"
        "  Permissions-Policy: geolocation=(), microphone=(), camera=(), interest-cohort=()\n"
        "\n"
        "/og.png\n"
        "  Cache-Control: public, max-age=86400\n"
        "\n"
        "/favicon.ico\n"
        "  Cache-Control: public, max-age=604800\n", encoding="utf-8")
    print("  wrote _headers")

    # www -> apex. Only fires once www.dragdrivecodes.space is added as a custom
    # domain on the same Pages project; until then the host does not resolve at all.
    (DIST / "_redirects").write_text(
        "# Force www to the apex domain. Prerequisite: add www.<domain> as a custom\n"
        "# domain on the same Pages project, otherwise this rule is never reached.\n"
        f"https://www.{BASE.split('//', 1)[1]}/*  {BASE}/:splat  301!\n", encoding="utf-8")
    print("  wrote _redirects")

    build_local(pages, p404)

    titles = [p["title"] for p in pages]
    assert len(titles) == len(set(titles)), "duplicate page titles"
    print(f"\nBuild OK · {len(pages) + 1} HTML pages · base URL {BASE}")
    print("Deploy: upload dist/ as-is (Cloudflare Pages, no build step needed on CI).")


if __name__ == "__main__":
    build()
