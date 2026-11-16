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

The property identifier is read from `gsc_property` in data/site.json. Two forms:
  - domain property:       sc-domain:dragdrivecodes.space
  - URL-prefix property:   https://dragdrivecodes.space/
The sitemap feed path is always the full URL, independent of the property form.
If `gsc_property` is absent, the script falls back to the URL-prefix form.

Usage:
    python scripts/gsc_submit.py --check      # preconditions only, sends nothing
    python scripts/gsc_submit.py --dry-run    # formats the request, sends nothing
    python scripts/gsc_submit.py --status     # read-only: sitemaps list + counts
    python scripts/gsc_submit.py --inspect    # read-only: URL Inspection for every sitemap URL
    python scripts/gsc_submit.py              # actually submits the sitemap

Exit codes: 0 = submitted or all preconditions met, 1 = blocked / not verified,
2 = usage or dependency error.
"""

from __future__ import annotations

import json
import os
import sys
import time
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
SITEMAPS_API = "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps"
INSPECT_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

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

def site_property(site: dict) -> str:
    """Return the Search Console property identifier.

    Configured once in data/site.json (`gsc_property`). Both forms are valid:
      - "sc-domain:dragdrivecodes.space"  (domain property, DNS-verified)
      - "https://dragdrivecodes.space/"   (URL-prefix property)

    To switch forms, edit only `gsc_property` in data/site.json.
    """
    configured = str(site.get("gsc_property") or "").strip()
    if configured:
        return configured
    # Legacy fallback when the key is absent: URL-prefix form.
    base = site["base_url"].rstrip("/")
    return base + "/"


def property_problems(prop: str, base_url: str) -> list[str]:
    """Catch the mistake that produces a confusing 403/404 later."""
    host = urllib.parse.urlparse(base_url).hostname or ""
    if prop.startswith("sc-domain:"):
        domain = prop[len("sc-domain:"):].strip("/")
        if domain != host:
            return [f"gsc_property '{prop}' does not match base_url host '{host}'"]
        return []
    if not prop.startswith(("http://", "https://")):
        return [f"gsc_property '{prop}' must be 'sc-domain:<host>' or an http(s) URL"]
    if not prop.endswith("/"):
        return [f"gsc_property '{prop}' must end with '/' for a URL-prefix property"]
    if urllib.parse.urlparse(prop).hostname != host:
        return [f"gsc_property '{prop}' does not match base_url host '{host}'"]
    return []


def property_kind(prop: str) -> str:
    return "domain property" if prop.startswith("sc-domain:") else "URL-prefix property"


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

    prop = site_property(site)
    prop_issues = property_problems(prop, base)
    if prop_issues:
        blocked += prop_issues
    else:
        ok(f"Search Console property: {prop} ({property_kind(prop)})")
    ok(f"sitemap feed: {sitemap_url(base)}")

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
    print("  2. The property above has to exist in Search Console and be verified.")
    print("     This script cannot confirm that without credentials; domain properties use DNS TXT.")
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
    property_url = site_property(site)
    feed = sitemap_url(base)
    issues = property_problems(property_url, base)
    if issues:
        print("Invalid Search Console property configuration:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    endpoint = API.format(site=urllib.parse.quote(property_url, safe=""),
                          feed=urllib.parse.quote(feed, safe=""))

    print("Request")
    print(f"  PUT {endpoint}")
    print(f"  property: {property_url} ({property_kind(property_url)})")
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


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------

def api_json(url: str, token: str, method: str = "GET",
             body: dict | None = None) -> tuple[int, dict | None]:
    """Return (status, parsed JSON). Prints the raw error body on failure."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace") or "{}"
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        print(f"  HTTP {e.code} {url}")
        print(f"  {raw[:700]}")
        return e.code, None
    except Exception as e:  # noqa: BLE001 — network failures are reported, not retried
        print(f"  request failed: {type(e).__name__}: {e}")
        return 0, None


def require_token(site: dict) -> tuple[str | None, str | None]:
    prop = site_property(site)
    issues = property_problems(prop, site["base_url"].rstrip("/"))
    if issues:
        print("Invalid Search Console property configuration:")
        for issue in issues:
            print(f"  - {issue}")
        return None, None
    info, source = find_credentials()
    if info is None:
        print("NOT VERIFIED: no credentials.")
        return None, None
    print(f"  property: {prop} ({property_kind(prop)})")
    print(f"  credentials: {source}")
    return access_token(info), prop


def sitemap_status(site: dict) -> int:
    """GET the sitemaps list: counts, errors, last read time."""
    print("Sitemaps (read-only)")
    token, prop = require_token(site)
    if token is None:
        return 1
    url = SITEMAPS_API.format(site=urllib.parse.quote(prop, safe=""))
    code, payload = api_json(url, token)
    if code != 200 or payload is None:
        return 1
    entries = payload.get("sitemap", [])
    if not entries:
        print("  (no sitemaps submitted for this property)")
        return 0
    for sm in entries:
        print(f"\n  {sm.get('path')}")
        print(f"    lastSubmitted:  {sm.get('lastSubmitted', 'n/a')}")
        print(f"    lastDownloaded: {sm.get('lastDownloaded', 'n/a')}")
        print(f"    pending: {sm.get('isPending')}   sitemapIndex: {sm.get('isSitemapsIndex')}")
        print(f"    errors: {sm.get('errors', '0')}   warnings: {sm.get('warnings', '0')}")
        for content in sm.get("contents", []):
            print(f"    {content.get('type')}: submitted={content.get('submitted')} "
                  f"indexed={content.get('indexed')}")
    print("\n  note: the API has no 'Discovered URLs' field; 'submitted' is the URL count")
    print("  inside the sitemap, 'indexed' is what Google reports as indexed.")
    return 0


def sitemap_urls() -> list[str]:
    sm = SITE_ROOT / "dist" / "sitemap.xml"
    if not sm.exists():
        return []
    text = sm.read_text(encoding="utf-8")
    return [line.strip().removeprefix("<loc>").removesuffix("</loc>")
            for line in text.splitlines() if "<loc>" in line]


def classify(result: dict) -> str:
    verdict = result.get("verdict", "")
    coverage = result.get("coverageState", "") or ""
    if verdict in {"PASS", "PARTIAL"}:
        return "已收录"
    if "excluded" in coverage.lower():
        return "已排除"
    return "未收录"


def inspect_urls(site: dict) -> int:
    """URL Inspection for every URL in dist/sitemap.xml, strictly serial."""
    urls = sitemap_urls()
    if not urls:
        print("dist/sitemap.xml missing or empty — run: python build.py")
        return 1
    print(f"URL Inspection (read-only, {len(urls)} URLs, serial)")
    token, prop = require_token(site)
    if token is None:
        return 1
    rows = []
    for index, url in enumerate(urls, 1):
        code, payload = api_json(
            INSPECT_API, token, method="POST",
            body={"inspectionUrl": url, "siteUrl": prop, "languageCode": "en-US"},
        )
        if code != 200 or payload is None:
            print(f"  stopped at {index}/{len(urls)}: {url}")
            return 1
        result = payload.get("inspectionResult", {}).get("indexStatusResult", {})
        rows.append((url, classify(result), result))
        time.sleep(0.5)

    for url, category, result in rows:
        print(f"\n  [{category}] {url}")
        print(f"    verdict={result.get('verdict', 'n/a')}  "
              f"coverage={result.get('coverageState', 'n/a')}")
        print(f"    fetch={result.get('pageFetchState', 'n/a')}  "
              f"robots={result.get('robotsTxtState', 'n/a')}  "
              f"lastCrawl={result.get('lastCrawlTime', 'n/a')}")
        google_c = result.get("googleCanonical", "")
        user_c = result.get("userCanonical", "")
        if google_c and user_c and google_c != user_c:
            print(f"    canonical mismatch: google={google_c} user={user_c}")

    print("\nSummary")
    for category in ("已收录", "未收录", "已排除"):
        print(f"  {category}: {sum(1 for r in rows if r[1] == category)}")
    return 0


def main(argv: list[str]) -> int:
    args = set(argv[1:])
    unknown = args - {"--check", "--dry-run", "--status", "--inspect", "-h", "--help"}
    if unknown:
        print(f"unknown argument(s): {', '.join(sorted(unknown))}")
        return 2
    if args & {"-h", "--help"}:
        print(__doc__)
        return 0

    site = load_site()
    if "--check" in args:
        return run_check(site)
    if "--status" in args:
        return sitemap_status(site)
    if "--inspect" in args:
        return inspect_urls(site)
    return submit(site, dry_run="--dry-run" in args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
