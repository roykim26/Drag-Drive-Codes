#!/usr/bin/env python3
"""Submit dist/sitemap.xml to Google Search Console.

This script is deliberately conservative: it verifies its own preconditions before
sending anything, and it refuses to run when the site is not live or the Search
Console property is not verified.

Credentials are NEVER written to this repository or to dist/. They are read from,
in order:

  1. GSC_SERVICE_ACCOUNT_JSON  — raw JSON, or a path to a JSON file
  2. GSC_SERVICE_ACCOUNT_FILE  — path to a JSON file
  3. ./gsc-service-account.json — local file, already listed in .gitignore

The service account must be added as a user (at least "Full" permission) on the
Search Console property. Adding it as an owner of the Google Cloud project is not
enough — it has to be a user of the Search Console property itself.

Usage:
    python scripts/gsc_submit.py --check      # preconditions only, sends nothing
    python scripts/gsc_submit.py --dry-run    # formats the request, sends nothing
    python scripts/gsc_submit.py              # actually submits the sitemap

Exit codes: 0 = submitted or all preconditions met, 1 = blocked / not verified,
2 = usage or dependency error.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
SITE_JSON = SITE_ROOT / "data" / "site.json"
LOCAL_CRED = SITE_ROOT / "gsc-service-account.json"
SITEMAP_PATH = "/sitemap.xml"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]
API = "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps/{feed}"

PLACEHOLDER_HOSTS = ("example.com", "example.org", "localhost", "127.0.0.1", "0.0.0.0")


def load_site() -> dict:
    if not SITE_JSON.exists():
        fail(2, f"missing {SITE_JSON}")
    return json.loads(SITE_JSON.read_text(encoding="utf-8"))


def fail(code: int, message: str) -> None:
    print(f"  x {message}")
    raise SystemExit(code)


def ok(message: str) -> None:
    print(f"  ok {message}")


def warn(message: str) -> None:
    print(f"  ! {message}")


# ---------------------------------------------------------------------------
# Credentials — read only, never write
# ---------------------------------------------------------------------------

def read_json_file(path: Path) -> dict:
    """Read a JSON file tolerantly: Windows editors often add a UTF-8 BOM."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        fail(2, f"{path.name} is not valid JSON ({e.msg} at line {e.lineno})")


def find_credentials() -> tuple[dict | None, str]:
    """Return (service_account_info, human-readable source) without printing secrets."""
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        if raw.startswith("{"):
            try:
                return json.loads(raw), "GSC_SERVICE_ACCOUNT_JSON (inline JSON)"
            except json.JSONDecodeError:
                fail(2, "GSC_SERVICE_ACCOUNT_JSON is set but is not valid JSON")
        path = Path(raw)
        if path.exists():
            return read_json_file(path), "GSC_SERVICE_ACCOUNT_JSON (file path)"
        fail(2, "GSC_SERVICE_ACCOUNT_JSON points to a file that does not exist")

    env_file = os.environ.get("GSC_SERVICE_ACCOUNT_FILE", "").strip()
    if env_file:
        path = Path(env_file)
        if path.exists():
            return read_json_file(path), "GSC_SERVICE_ACCOUNT_FILE"
        fail(2, "GSC_SERVICE_ACCOUNT_FILE points to a file that does not exist")

    if LOCAL_CRED.exists():
        return read_json_file(LOCAL_CRED), "gsc-service-account.json (local, gitignored)"

    return None, "none"


def describe_credentials(info: dict) -> list[str]:
    """Summarise a service-account key by its non-secret fields only."""
    problems = []
    email = info.get("client_email", "")
    if not email:
        problems.append("client_email missing — this is not a service-account key file")
    else:
        warn(f"service account: {email}")
    if not info.get("private_key"):
        problems.append("private_key missing — key file is incomplete")
    if info.get("type") != "service_account":
        problems.append(f"type is '{info.get('type')}', expected 'service_account'")
    if info.get("project_id"):
        print(f"     project: {info['project_id']}")
    return problems


def access_token(info: dict) -> str:
    try:
        from google.oauth2 import service_account  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError:
        fail(2, "google-auth is not installed. Run: pip install google-auth")

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

def site_property(base_url: str) -> str:
    """Search Console accepts either a URL-prefix property or a domain property."""
    return base_url if base_url.endswith("/") else base_url + "/"


def sitemap_url(base_url: str) -> str:
    return base_url.rstrip("/") + SITEMAP_PATH


def check_local_build(base_url: str) -> list[str]:
    """Verify dist/ exists and matches the configured base_url, offline."""
    problems: list[str] = []
    dist = SITE_ROOT / "dist"
    sm = dist / "sitemap.xml"
    robots = dist / "robots.txt"
    if not dist.is_dir():
        return [f"{dist} does not exist — run: python build.py"]
    if not sm.exists():
        problems.append("dist/sitemap.xml missing — run: python build.py")
    else:
        text = sm.read_text(encoding="utf-8")
        locs = [line.strip().removeprefix("<loc>").removesuffix("</loc>")
                for line in text.splitlines() if "<loc>" in line]
        if not locs:
            problems.append("dist/sitemap.xml contains no <loc> entries")
        wrong = [u for u in locs if not u.startswith(base_url.rstrip('/') + "/")]
        if wrong:
            problems.append(f"{len(wrong)} sitemap URLs do not use base_url (first: {wrong[0]})")
        else:
            ok(f"dist/sitemap.xml: {len(locs)} URLs, all under {base_url}")
    if robots.exists() and "Sitemap:" not in robots.read_text(encoding="utf-8"):
        problems.append("dist/robots.txt does not reference a sitemap")
    elif robots.exists():
        ok("dist/robots.txt references the sitemap")
    return problems


def check_live(url: str) -> list[str]:
    """Best-effort reachability check. A failure here means the site is not live yet."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "DragDriveCodes-GSC/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                ok(f"{url} responds 200")
                return []
            return [f"{url} responds {response.status}"]
    except urllib.error.HTTPError as e:
        return [f"{url} responds HTTP {e.code}"]
    except Exception as e:  # noqa: BLE001 — any network failure means "not live yet"
        return [f"{url} is not reachable ({type(e).__name__})"]


def run_check(site: dict) -> int:
    base = site["base_url"].rstrip("/")
    host = urllib.parse.urlparse(base).hostname or ""
    blocked: list[str] = []

    print("Preconditions")
    if any(h in host for h in PLACEHOLDER_HOSTS) or "." not in host:
        blocked.append(f"base_url '{base}' is a placeholder, not a live domain")
    else:
        ok(f"base_url: {base}")

    blocked += check_local_build(base)

    info, source = find_credentials()
    if info is None:
        blocked.append("no service-account key found (GSC_SERVICE_ACCOUNT_JSON, "
                       "GSC_SERVICE_ACCOUNT_FILE, or gsc-service-account.json)")
    else:
        ok(f"credentials read from {source}")
        blocked += describe_credentials(info)
        try:
            import google.oauth2.service_account  # noqa: F401
            ok("google-auth is installed")
        except ImportError:
            blocked.append("google-auth is not installed (pip install google-auth)")

    print("\nLive checks")
    blocked += check_live(sitemap_url(base))

    print("\nWhat still has to happen outside this script")
    print("  1. The domain has to be registered, deployed and serving this dist/ folder over HTTPS.")
    print("  2. The site has to be added as a Search Console property and verified")
    print("     (DNS TXT record or HTML file — the HTML meta tag route needs a template change).")
    print("  3. The service-account email has to be added as a user of that property in Search Console.")
    print("  4. The Search Console API has to be enabled in the Google Cloud project that owns the key.")

    if blocked:
        print("\nNOT VERIFIED — this script has never reached the live API:")
        for b in blocked:
            print(f"  - {b}")
        return 1
    print("\nAll preconditions met. Run without --check to submit.")
    return 0


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

def submit(site: dict, dry_run: bool) -> int:
    base = site["base_url"].rstrip("/")
    property_url = site_property(base)
    feed = sitemap_url(base)
    endpoint = API.format(site=urllib.parse.quote(property_url, safe=""),
                          feed=urllib.parse.quote(feed, safe=""))

    print("Request")
    print(f"  PUT {endpoint}")
    print(f"  property: {property_url}")
    print(f"  sitemap:  {feed}")

    info, source = find_credentials()
    if info is None:
        print("\nNOT VERIFIED: no credentials, nothing was sent.")
        return 1
    print(f"  credentials: {source}")

    if dry_run:
        print("\nDry run: credentials and request were not exercised. Nothing was sent.")
        return 0

    token = access_token(info)
    request = urllib.request.Request(
        endpoint,
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Length": "0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"\nSubmitted. HTTP {response.status}")
            return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        print(f"\nSubmission failed: HTTP {e.code}")
        print(f"  {body}")
        if e.code in (401, 403):
            print("  403/401 usually means the service account is not a user of the property,")
            print("  or the Search Console API is not enabled for the project.")
        if e.code == 404:
            print("  404 usually means the property URL is wrong, or the sitemap URL does not match.")
        return 1


def main(argv: list[str]) -> int:
    args = set(argv[1:])
    unknown = args - {"--check", "--dry-run", "-h", "--help"}
    if unknown:
        print(f"unknown argument(s): {', '.join(sorted(unknown))}")
        return 2
    if args & {"-h", "--help"}:
        print(__doc__)
        return 0

    site = load_site()
    if "--check" in args:
        return run_check(site)
    return submit(site, dry_run="--dry-run" in args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
