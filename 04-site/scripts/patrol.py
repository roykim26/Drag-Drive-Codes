#!/usr/bin/env python3
"""DragDriveCodes daily code patrol.

Fetches the public Roblox games API snapshot for the tracked experience, diffs it
against the previous snapshot, extracts code-like tokens and writes a
"needs human review" report. Standard library only, no third-party imports.

It NEVER edits data/codes.json or any page. It only reports.

Exit codes
    0   fetched, no code candidates
    10  fetched, candidate codes and/or possibly-missing codes found  -> needs a human
    30  fetch/parse failed (after 3 attempts)
    40  configuration error

Examples
    python patrol.py --dry-run                       # print only, write nothing, notify nothing
    python patrol.py --once                          # normal run
    python patrol.py --snapshot-file fake.json --base-dir /tmp/t   # offline / test run
    python patrol.py --alert "ddc-patrol.service failed"           # used by systemd OnFailure=
Webhook
    Read from $DDC_WEBHOOK_URL (never hard-coded, never committed). If unset the
    report is still written and the notification is skipped with a warning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from difflib import unified_diff
from pathlib import Path

UNIVERSE_ID = 7089588429  # verified 2026-11-15 against the official game page
API_URL = "https://games.roblox.com/v1/games?universeIds={uid}"
USER_AGENT = "DragDriveCodes-patrol/1.0 (+https://dragdrivecodes.space)"

# Codes in this game are long uppercase tokens, occasionally versioned with dots
# (e.g. DRAGDRIVESIMULATORV1.2.0). Min length 10 keeps BETA/UPDATE/RP out.
CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]{9,}(?:\.[0-9]+)*\b")
DENY = {
    "DRAGDRIVESIMULATOR", "DRAGDRIVESIMULATORCODES", "DRAGDRIVESIMULATORCODE",
    "BETAUPDATE", "ROLEPLAYGAME", "NEXTCODERELEASING",
}

MAX_BACKOFF = 8
ATTEMPTS = 3


# --------------------------------------------------------------------------- io
def log(msg: str) -> None:
    print(msg, flush=True)


def fetch(url: str, timeout: int = 25) -> str:
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - any transport error is retryable
            last = e
            if attempt < ATTEMPTS:
                wait = min(2 ** attempt, MAX_BACKOFF)
                log(f"  ! attempt {attempt}/{ATTEMPTS} failed: {type(e).__name__}: {e} (retry in {wait}s)")
                time.sleep(wait)
    raise RuntimeError(f"fetch failed after {ATTEMPTS} attempts: {type(last).__name__}: {last}")


def notify(text: str, dry_run: bool, no_notify: bool) -> bool:
    url = os.environ.get("DDC_WEBHOOK_URL", "").strip()
    if no_notify:
        log("  notify: skipped (--no-notify)")
        return False
    if not url:
        log("  notify: skipped (DDC_WEBHOOK_URL not set)")
        return False
    if dry_run:
        log(f"  notify: would POST {len(text)} chars to the configured webhook")
        return False
    host = url.split("/")[2] if url.count("/") >= 2 else ""
    if "discord" in host:
        body = {"content": text[:1900]}
    elif "feishu" in host or "larksuite" in host:
        body = {"msg_type": "text", "content": {"text": text[:1900]}}
    else:
        body = {"text": text[:1900]}
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            log(f"  notify: sent ({r.status})")
        return True
    except Exception as e:  # noqa: BLE001 - notification must never fail the run
        log(f"  notify: FAILED {type(e).__name__}: {e}")
        return False


# ------------------------------------------------------------------------ logic
def _codes(node) -> list[str]:
    """codes.json nests expired entries by year, so accept list-or-dict at any depth."""
    if isinstance(node, dict):
        return [c for v in node.values() for c in _codes(v)]
    if isinstance(node, list):
        out = []
        for item in node:
            if isinstance(item, dict) and item.get("code"):
                out.append(item["code"])
            elif isinstance(item, str):
                out.append(item)
        return out
    return []


def load_known(codes_file: Path) -> tuple[set[str], list[str]]:
    """Return (all known codes, currently active codes)."""
    try:
        data = json.loads(codes_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log(f"  ! codes file not found: {codes_file} (candidates will not be filtered)")
        return set(), []
    active = _codes(data.get("active"))
    known = set(active) | set(_codes(data.get("unconfirmed"))) | set(_codes(data.get("expired")))
    return known, active


def extract_candidates(description: str) -> list[str]:
    found = {m.group(0) for m in CODE_RE.finditer(description)}
    return sorted(c for c in found if c not in DENY)


def summarize(payload: dict) -> dict:
    data = payload.get("data") or []
    if not data:
        raise ValueError("payload has no data[] entry (bad universeId or API schema change)")
    g = data[0]
    return {
        "name": g.get("name", ""),
        "updated": g.get("updated", ""),
        "description": g.get("description", "") or "",
        "playing": g.get("playing"),
        "visits": g.get("visits"),
    }


def diff_desc(old: str, new: str, limit: int = 40) -> str:
    if old == new:
        return "（描述文本无变化）"
    lines = list(unified_diff(old.splitlines(), new.splitlines(), "previous", "current", lineterm="", n=1))
    if len(lines) > limit:
        lines = lines[:limit] + [f"... （还有 {len(lines) - limit} 行未显示）"]
    return "\n".join(lines)


def build_report(now: datetime, cur: dict, prev: dict | None, new_codes: list[str],
                 missing: list[str], diff_text: str, snapshot_name: str,
                 baseline: list[str] | None = None) -> str:
    changed = []
    if prev:
        if prev.get("updated") != cur["updated"]:
            changed.append(f"updated 变化：{prev.get('updated')} → {cur['updated']}")
        if prev.get("description") != cur["description"]:
            changed.append("description 文本变化：有")
        if not changed:
            changed.append("无变化（updated 与 description 都与上一版一致）")
    else:
        changed.append("首次运行：没有上一版快照，本次只建立基线，不做候选判定")

    lines = [
        f"# Patrol {now:%Y-%m-%d %H:%M} UTC",
        "",
        f"- 体验：{cur['name']}",
        f"- updated：{cur['updated'] or 'unknown'}",
        f"- description sha256：{hashlib.sha256(cur['description'].encode()).hexdigest()[:16]}",
        f"- 判定：{'有变化' if prev and prev.get('description') != cur['description'] else ('仅时间戳变化' if prev else '基线')}",
        "",
        "## 变化摘要",
        *[f"- {c}" for c in changed],
        "",
        *( ["## 基线候选（首次运行，仅供参考，未触发告警）",
            *([f"- `{c}`" for c in baseline] or ["（无）"]), ""] if baseline is not None else [] ),
        f"## 疑似新码（需人工确认，共 {len(new_codes)} 条）",
        *( [f"- `{c}` — 出现在 description，未在 codes.json 中" for c in new_codes] or ["（无）"] ),
        "",
        f"## 疑似失效（需人工确认，共 {len(missing)} 条）",
        *( [f"- `{c}` — 当前有效码，本次 description 中未出现；**消失不等于过期**，需人工核对游戏内与官方页" for c in missing] or ["（无）"] ),
        "",
        "## 描述 diff",
        "```diff",
        diff_text,
        "```",
        "",
        "## 原文快照",
        f"snapshots/{snapshot_name}",
        "",
        "> 本报告只做提示，不修改 codes.json，也不触发任何构建。确认后请手动改 `data/codes.json` → `python build.py` → 部署。",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------- main
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DragDriveCodes daily code patrol (report only).")
    p.add_argument("--once", action="store_true", help="run once (default action)")
    p.add_argument("--dry-run", action="store_true", help="print intent, write nothing, notify nothing")
    p.add_argument("--snapshot-file", type=Path, help="use this JSON instead of the network (offline/test)")
    p.add_argument("--base-dir", type=Path, help="state directory (default /var/lib/ddc-patrol)")
    p.add_argument("--codes-file", type=Path, help="path to data/codes.json for filtering")
    p.add_argument("--universe", type=int, default=UNIVERSE_ID)
    p.add_argument("--keep", type=int, default=90, help="keep snapshots for N days (default 90)")
    p.add_argument("--alert", metavar="MSG", help="send one alert message and exit (systemd OnFailure=)")
    p.add_argument("--no-notify", action="store_true", help="never call the webhook")
    p.add_argument("--exit-zero", action="store_true", help="always exit 0 on success paths")
    p.add_argument("--json", action="store_true", help="print a machine-readable summary")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H%MZ")

    if a.alert:
        msg = f"[DragDriveCodes patrol] {a.alert}"
        log(msg)
        notify(msg, a.dry_run, a.no_notify)
        return 0

    base = a.base_dir or Path(os.environ.get("DDC_STATE_DIR")
                              or ("/var/lib/ddc-patrol" if os.name != "nt"
                                  else Path.home() / ".ddc-patrol"))
    snap_dir, rep_dir = base / "snapshots", base / "reports"
    codes_file = a.codes_file or Path(__file__).resolve().parent.parent / "data" / "codes.json"

    log(f"patrol {stamp} · base={base} · dry_run={a.dry_run}")
    if a.dry_run:
        log(f"  would write: {snap_dir / (stamp + '.json')}")
        log(f"  would write: {rep_dir / (now.strftime('%Y-%m-%d') + '.md')}")
        log(f"  would read : {codes_file}")

    try:
        if a.snapshot_file:
            log(f"  source: local file {a.snapshot_file}")
            raw = a.snapshot_file.read_text(encoding="utf-8")
        else:
            url = API_URL.format(uid=a.universe)
            log(f"  source: {url}")
            raw = fetch(url)
        cur = summarize(json.loads(raw))
    except Exception as e:  # noqa: BLE001
        log(f"  FAILED: {type(e).__name__}: {e}")
        notify(f"[DragDriveCodes patrol] 拉取失败 {stamp}: {type(e).__name__}: {e}", a.dry_run, a.no_notify)
        return 30

    latest = base / "latest.json"
    prev = None
    prev_success = None
    state_file = base / "state.json"
    if state_file.exists():
        try:
            prev_success = datetime.fromisoformat(
                json.loads(state_file.read_text(encoding="utf-8"))["last_success"])
        except Exception:  # noqa: BLE001
            prev_success = None
    if latest.exists():
        try:
            prev = summarize(json.loads(latest.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            log(f"  ! previous snapshot unreadable ({e}); treating as first run")

    known, active = load_known(codes_file)
    tokens = extract_candidates(cur["description"])
    desc_changed = prev is not None and prev["description"] != cur["description"]
    if prev is None:
        # First run only establishes a baseline; do not alert on day one.
        new_codes, missing = [], []
    elif not desc_changed:
        # Only `updated` moved (e.g. a thumbnail or title change). The description is
        # identical, so every candidate would be a repeat of yesterday's report.
        new_codes, missing = [], []
    else:
        new_codes = [c for c in tokens if c not in known]
        missing = [c for c in active if c not in cur["description"]]

    diff_text = diff_desc(prev["description"], cur["description"]) if prev else "（首次运行，无上一版可比）"
    baseline = [c for c in tokens if c not in known] if prev is None else None
    report = build_report(now, cur, prev, new_codes, missing, diff_text, f"{stamp}.json", baseline)

    log(f"  updated={cur['updated']}  desc_sha={hashlib.sha256(cur['description'].encode()).hexdigest()[:12]}")
    log(f"  candidates={len(new_codes)} missing={len(missing)} tokens_seen={len(tokens)}")
    if baseline:
        log("  基线候选（未触发告警）: " + ", ".join(baseline))
    for c in new_codes:
        log(f"    + {c}")
    for c in missing:
        log(f"    - {c}")

    if a.json:
        log(json.dumps({"stamp": stamp, "updated": cur["updated"], "new": new_codes,
                        "missing": missing, "dry_run": a.dry_run}, ensure_ascii=False))

    if not a.dry_run:
        snap_dir.mkdir(parents=True, exist_ok=True)
        rep_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / f"{stamp}.json").write_text(raw, encoding="utf-8")
        shutil.copy2(snap_dir / f"{stamp}.json", latest)
        (rep_dir / f"{now:%Y-%m-%d}.md").write_text(report, encoding="utf-8")
        state = {"last_success": now.isoformat(timespec="seconds"),
                 "last_updated": cur["updated"],
                 "desc_sha256": hashlib.sha256(cur["description"].encode()).hexdigest(),
                 "new": new_codes, "missing": missing}
        (base / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        cutoff = now - timedelta(days=a.keep)
        for f in snap_dir.glob("*.json"):
            if f.name == "latest.json":
                continue
            try:
                if datetime.strptime(f.name[:15] + "Z", "%Y-%m-%dT%H%M%Z").replace(tzinfo=timezone.utc) < cutoff:
                    f.unlink()
            except ValueError:
                pass
        log(f"  wrote snapshots/{stamp}.json + reports/{now:%Y-%m-%d}.md + state.json")

    # silence check: compare against the last success recorded *before* this run
    if prev_success:
        gap = now - prev_success
        if gap > timedelta(hours=36):
            log(f"  ! 上次成功是 {gap.days} 天前，检查定时器是否在跑")
            notify(f"[DragDriveCodes patrol] 静默告警：上次成功在 {gap.days} 天前，今天的运行已恢复",
                   a.dry_run, a.no_notify)

    hit = bool(new_codes or missing)
    if hit:
        head = f"[DragDriveCodes patrol {now:%Y-%m-%d}] "
        parts = []
        if new_codes:
            parts.append(f"疑似新码 {len(new_codes)} 条：" + ", ".join(new_codes))
        if missing:
            parts.append(f"疑似失效 {len(missing)} 条：" + ", ".join(missing))
        notify(head + "；".join(parts) + f"（需人工确认，详见 reports/{now:%Y-%m-%d}.md）",
               a.dry_run, a.no_notify)
    if a.exit_zero:
        return 0
    return 10 if hit else 0


if __name__ == "__main__":
    sys.exit(main())
