# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
# pylint: disable=broad-exception-caught,line-too-long
# pylint: disable=consider-using-with,too-many-locals

from __future__ import annotations

import argparse
import os
import json
import shutil
import socket
import subprocess
import tempfile
import time
import webbrowser
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence
from urllib.request import urlopen

import requests
from websocket import create_connection

# 与 app/notion_client.py 一致：支持区域镜像 / 反代，默认官方站点
NOTION_URL = os.getenv("NOTION_URL", "https://www.notion.so").rstrip("/")
NOTION_DOMAIN = os.getenv("NOTION_DOMAIN", "www.notion.so").lstrip(".")
BASE_URL = NOTION_URL
AI_URL = f"{NOTION_URL}/ai"
# CDP 页面识别用的主机名片段（Notion 有多个官方域名，自定义域名时填 NOTION_DOMAIN 即可）
_NOTION_HOST_HINTS = tuple(
    dict.fromkeys(
        hint
        for hint in (
            NOTION_DOMAIN.removeprefix("www.") if NOTION_DOMAIN.startswith("www.") else NOTION_DOMAIN,
            "notion.so",
            "notion.com",
            "notion.site",
        )
        if hint
    )
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
ACCOUNTS_FILE = Path(__file__).resolve().parent / "accounts.json"
ENV_FILE = Path(__file__).resolve().parent / ".env"
DEFAULT_PROFILE = "default"
DEFAULT_DEBUG_PORT = 9222
DEFAULT_LOGIN_TIMEOUT = 300


@dataclass(frozen=True)
class NotionAccount:
    profile_name: str
    token_v2: str
    space_id: str
    user_id: str
    space_view_id: str
    user_name: str
    user_email: str
    cookies: dict[str, str]

    def with_profile(self, profile_name: str) -> "NotionAccount":
        return replace(self, profile_name=profile_name or DEFAULT_PROFILE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name or DEFAULT_PROFILE,
            "token_v2": self.token_v2,
            "space_id": self.space_id,
            "user_id": self.user_id,
            "space_view_id": self.space_view_id,
            "user_name": self.user_name,
            "user_email": self.user_email,
            "cookies": self.cookies,
        }


def _print_header() -> None:
    print("=" * 60)
    print("Notion2API Login")
    print("=" * 60)
    print("This helper saves named Notion profiles into accounts.json.")
    print("Default flow: launch a local Chrome window, wait for sign-in, and extract token_v2.")
    print("Use --manual to paste token_v2 if Chrome is unavailable.")


def _open_login_page() -> None:
    try:
        webbrowser.open(AI_URL, new=2)
        print(f"Opened {AI_URL} in your browser.")
    except Exception:
        print(f"Open this page manually: {AI_URL}")


def _prompt_token() -> str:
    print()
    print("Step 1: Sign in to Notion in the browser window.")
    print("Step 2: Copy your token_v2 value from the Notion cookie store.")
    print("Step 3: Paste it below.")
    token = input("\nPaste token_v2: ").strip()
    if not token:
        raise ValueError("token_v2 is required")
    return token


def _find_free_port(start: int = DEFAULT_DEBUG_PORT, end: int = DEFAULT_DEBUG_PORT + 20) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free debugging port found")


def _get_json(url: str, timeout: int = 2) -> Any:
    with urlopen(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def _find_chrome_executable() -> str | None:
    env_path = os.getenv("CHROME_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists():
            return str(candidate)

    candidates = [
        "chrome.exe",
        "chrome",
        "google-chrome",
        "google-chrome-stable",
        "msedge.exe",
        "msedge",
    ]
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    program_files = [
        os.getenv("PROGRAMFILES"),
        os.getenv("PROGRAMFILES(X86)"),
        os.getenv("LOCALAPPDATA"),
    ]
    suffixes = [
        r"Google\Chrome\Application\chrome.exe",
        r"Google\Chrome Beta\Application\chrome.exe",
        r"Google\Chrome Canary\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
    ]
    for root in program_files:
        if not root:
            continue
        for suffix in suffixes:
            candidate = Path(root) / suffix
            if candidate.exists():
                return str(candidate)

    # macOS / Linux 默认安装位置
    posix_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for path in posix_paths:
        candidate = Path(path)
        if candidate.exists():
            return str(candidate)
    return None


def _start_chrome_debug_session(port: int) -> tuple[subprocess.Popen[bytes], Path]:
    chrome = _find_chrome_executable()
    if not chrome:
        raise FileNotFoundError("Chrome or Edge executable not found")

    profile_dir = Path(tempfile.mkdtemp(prefix="notion2api-chrome-profile-"))
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        "--new-window",
        AI_URL,
    ]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return process, profile_dir


class _CDPClient:
    def __init__(self, ws_url: str) -> None:
        self._ws = create_connection(ws_url, timeout=5)
        self._next_id = 1

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = self._next_id
        self._next_id += 1
        self._ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            response = json.loads(self._ws.recv())
            if response.get("id") == message_id:
                if response.get("error"):
                    raise RuntimeError(str(response["error"]))
                result = response.get("result", {})
                return result if isinstance(result, dict) else {}

    def call_raw(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.call(method, params)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


def _looks_like_notion_url(url: str) -> bool:
    text = str(url or "")
    return any(hint in text for hint in _NOTION_HOST_HINTS)


def _find_debug_target(port: int) -> dict[str, Any] | None:
    try:
        targets = _get_json(f"http://127.0.0.1:{port}/json/list")
    except Exception:
        return None

    items = targets if isinstance(targets, list) else targets.get("result")
    if not isinstance(items, list):
        return None

    # 优先返回真正的页面（page），避免命中 chrome:// 的 browser_ui 目标
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "page":
            continue
        url = str(item.get("url") or "")
        if _looks_like_notion_url(url) or "accounts.google.com" in url:
            return item
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if _looks_like_notion_url(url) or "accounts.google.com" in url:
            return item
    return next((item for item in items if isinstance(item, dict) and item.get("type") == "page"), None)


def _parse_cookie_string(cookie_string: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in cookie_string.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            name = name.strip()
            value = value.strip()
            if name:
                cookies[name] = value
    return cookies


def _extract_cookies_from_cdp(port: int) -> dict[str, str]:
    target = _find_debug_target(port)
    if not target:
        raise RuntimeError("Chrome debugging target not available yet")

    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("Chrome debugging target missing websocket URL")

    client = _CDPClient(str(ws_url))
    try:
        client.call("Page.enable")
        client.call("Network.enable")

        try:
            current_url = client.call("Runtime.evaluate", {"expression": "location.href", "returnByValue": True})
            current_href = str(current_url.get("result", {}).get("value") or "") if isinstance(current_url, dict) else ""
            if not _looks_like_notion_url(current_href):
                client.call("Page.navigate", {"url": AI_URL})
                time.sleep(2)
        except Exception:
            pass

        cookies: dict[str, str] = {}

        try:
            cookie_eval = client.call(
                "Runtime.evaluate",
                {"expression": "document.cookie", "returnByValue": True},
            )
            cookie_string = ""
            if isinstance(cookie_eval, dict):
                cookie_string = str(cookie_eval.get("result", {}).get("value") or "")
            cookies.update(_parse_cookie_string(cookie_string))
        except Exception:
            pass

        def _collect(cookie_items: Any) -> None:
            if not isinstance(cookie_items, list):
                return
            for item in cookie_items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                value = str(item.get("value") or "").strip()
                if name:
                    cookies[name] = value

        cookie_result = client.call("Network.getCookies", {"urls": [BASE_URL, AI_URL]})
        _collect(cookie_result.get("cookies", []))

        # Notion 已迁移到 app.notion.com：只按 BASE_URL 取会漏掉 .notion.com 的 cookie，兜底读全量
        if not cookies.get("token_v2"):
            try:
                _collect(client.call("Network.getAllCookies").get("cookies", []))
            except Exception:
                pass
        return cookies
    finally:
        client.close()


def _wait_for_browser_cookies(port: int, timeout_seconds: int = DEFAULT_LOGIN_TIMEOUT) -> dict[str, str]:
    started = time.time()
    last_error = ""
    while time.time() - started < timeout_seconds:
        try:
            cookies = _extract_cookies_from_cdp(port)
        except Exception as exc:
            cookies = {}
            message = str(exc)
            if message and message != last_error:
                print(f"Chrome DevTools not ready yet: {message}")
                last_error = message

        token_v2 = cookies.get("token_v2", "").strip()
        if token_v2:
            return cookies

        print("Waiting for token_v2... sign in to the opened Chrome window.")
        time.sleep(5)

    raise TimeoutError("Timed out waiting for token_v2 in Chrome")


def _launch_and_extract_cookies(timeout_seconds: int = DEFAULT_LOGIN_TIMEOUT) -> dict[str, str]:
    port = _find_free_port()
    process, profile_dir = _start_chrome_debug_session(port)
    try:
        try:
            _get_json(f"http://127.0.0.1:{port}/json/version", timeout=2)
        except Exception:
            pass
        return _wait_for_browser_cookies(port, timeout_seconds=timeout_seconds)
    finally:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass


def _launch_and_extract_token(timeout_seconds: int = DEFAULT_LOGIN_TIMEOUT) -> str:
    return _launch_and_extract_cookies(timeout_seconds=timeout_seconds).get("token_v2", "")


def _session_for_token(token_v2: str, cookies: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    cookie_values = dict(cookies or {})
    cookie_values["token_v2"] = token_v2
    session.headers.update(
        {
            "Origin": BASE_URL,
            "Referer": AI_URL,
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Cookie": "; ".join(f"{name}={value}" for name, value in cookie_values.items() if value),
        }
    )
    for name, value in cookie_values.items():
        if not value:
            continue
        session.cookies.set(name, value, domain=NOTION_DOMAIN, path="/")
    return session


def _safe_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, dict):
            return inner
        if inner is not None:
            return {"value": inner}
        return value
    return {}


def _load_json_response(session: requests.Session, path: str) -> dict[str, Any]:
    response = session.post(f"{BASE_URL}{path}", json={}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _extract_candidates(token_v2: str, cookies: dict[str, str] | None = None) -> list[NotionAccount]:
    cookies = cookies or {}
    active_user_id = str(cookies.get("notion_user_id") or "").strip()
    session = _session_for_token(token_v2, cookies)

    try:
        get_spaces = _load_json_response(session, "/api/v3/getSpaces")
    except Exception:
        get_spaces = {}

    load_user_content = _load_json_response(session, "/api/v3/loadUserContent").get("recordMap", {})

    users: dict[str, dict[str, str]] = {}
    spaces: dict[str, dict[str, str]] = {}
    space_views: dict[str, str] = {}

    def add_users(source: dict[str, Any], target: dict[str, dict[str, str]]) -> None:
        for user_id, raw in source.items():
            v = _safe_value(raw)
            target[user_id] = {
                "name": str(v.get("given_name") or v.get("name") or v.get("family_name") or "").strip(),
                "email": str(v.get("email") or "").strip(),
            }

    def add_spaces(source: dict[str, Any], target: dict[str, dict[str, str]]) -> None:
        for space_id, raw in source.items():
            v = _safe_value(raw)
            target[space_id] = {
                "name": str(v.get("name") or "").strip(),
                "plan": str(v.get("plan_type") or v.get("subscription_tier") or "").strip(),
            }

    def add_space_views(source: dict[str, Any], target: dict[str, str]) -> None:
        for space_view_id, raw in source.items():
            v = _safe_value(raw)
            space_id = str(v.get("space_id") or "").strip()
            if space_id:
                target.setdefault(space_id, space_view_id)

    def accounts_from_maps(
        account_users: dict[str, dict[str, str]],
        account_spaces: dict[str, dict[str, str]],
        account_space_views: dict[str, str],
    ) -> list[NotionAccount]:
        accounts: list[NotionAccount] = []
        for user_id, user_data in account_users.items():
            for space_id in account_spaces:
                accounts.append(
                    NotionAccount(
                        profile_name=DEFAULT_PROFILE,
                        token_v2=token_v2,
                        space_id=space_id,
                        user_id=user_id,
                        space_view_id=account_space_views.get(space_id, ""),
                        user_name=user_data["name"] or "user",
                        user_email=user_data["email"],
                        cookies=cookies,
                    )
                )
        return accounts

    candidates: list[NotionAccount] = []
    for raw_user_data in get_spaces.values():
        if not isinstance(raw_user_data, dict):
            continue
        grouped_users: dict[str, dict[str, str]] = {}
        grouped_spaces: dict[str, dict[str, str]] = {}
        grouped_space_views: dict[str, str] = {}
        add_users(raw_user_data.get("notion_user", {}), grouped_users)
        add_spaces(raw_user_data.get("space", {}), grouped_spaces)
        add_space_views(raw_user_data.get("space_view", {}), grouped_space_views)
        users.update(grouped_users)
        spaces.update(grouped_spaces)
        space_views.update(grouped_space_views)
        candidates.extend(accounts_from_maps(grouped_users, grouped_spaces, grouped_space_views))

    add_users(load_user_content.get("notion_user", {}), users)
    add_spaces(load_user_content.get("space", {}), spaces)
    add_space_views(load_user_content.get("space_view", {}), space_views)

    if not users:
        raise ValueError("No Notion users were returned. The token may be invalid or expired.")
    if not spaces:
        raise ValueError("No Notion workspaces were returned. The token may be invalid or expired.")

    if not candidates:
        candidates = accounts_from_maps(users, spaces, space_views)

    if active_user_id:
        active_candidates = [account for account in candidates if account.user_id == active_user_id]
        if active_candidates:
            candidates = active_candidates

    candidates.sort(
        key=lambda account: (
            1 if account.user_id == active_user_id else 0,
            1 if account.user_email else 0,
            1 if account.space_view_id else 0,
            1 if account.user_name else 0,
        ),
        reverse=True,
    )
    return candidates


def _choose_account(candidates: list[NotionAccount]) -> NotionAccount:
    if len(candidates) == 1:
        chosen = candidates[0]
        print(f"Auto-selected: {chosen.user_name} {f'({chosen.user_email})' if chosen.user_email else ''}")
        return chosen

    print()
    print("Multiple account combinations were detected. Choose one:")
    for index, account in enumerate(candidates, start=1):
        label = account.user_name or "(unknown)"
        if account.user_email:
            label += f" <{account.user_email}>"
        if account.space_view_id:
            label += f" | space_view_id={account.space_view_id}"
        print(f"  [{index}] {label}")

    while True:
        choice = input(f"Select 1-{len(candidates)}: ").strip()
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(candidates):
                return candidates[index - 1]
        print("Invalid selection. Try again.")


def _read_accounts_file() -> list[dict[str, Any]]:
    if not ACCOUNTS_FILE.exists():
        return []
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _account_identity(item: dict[str, Any]) -> tuple[str, ...]:
    profile_name = str(item.get("profile_name") or "").strip().lower()
    if profile_name:
        return ("profile", profile_name)

    user_id = str(item.get("user_id") or "").strip()
    space_id = str(item.get("space_id") or "").strip()
    if user_id and space_id:
        return ("account", user_id, space_id)

    return ("raw", json.dumps(item, sort_keys=True, ensure_ascii=False))


def _write_accounts(account: NotionAccount) -> list[dict[str, Any]]:
    existing = _read_accounts_file()
    merged: list[dict[str, Any]] = []
    identity = _account_identity(account.to_dict())

    for item in existing:
        if _account_identity(item) == identity:
            continue
        merged.append(item)

    merged.insert(0, account.to_dict())
    ACCOUNTS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged


def _sync_env_file(accounts: list[dict[str, Any]]) -> None:
    env_line = f"NOTION_ACCOUNTS={json.dumps(accounts, ensure_ascii=False)}"

    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        updated = False
        new_lines: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("NOTION_ACCOUNTS="):
                new_lines.append(env_line)
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(env_line)
        ENV_FILE.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    else:
        ENV_FILE.write_text(env_line + "\n", encoding="utf-8")


def _validate_account(account: dict[str, Any]) -> tuple[bool, str]:
    token_v2 = str(account.get("token_v2") or "").strip()
    space_id = str(account.get("space_id") or "").strip()
    user_id = str(account.get("user_id") or "").strip()
    if not token_v2 or not space_id or not user_id:
        return False, "missing required fields"

    account_cookies = account.get("cookies")
    if not isinstance(account_cookies, dict):
        account_cookies = {}
    session = _session_for_token(token_v2, account_cookies)
    try:
        response = session.post(f"{BASE_URL}/api/v3/loadUserContent", json={}, timeout=30)
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"
        payload = response.json()
        record_map = payload.get("recordMap") if isinstance(payload, dict) else None
        if not isinstance(record_map, dict):
            return False, "unexpected response"
        return True, "token appears valid"
    except Exception as exc:
        return False, str(exc)


def _readable_account_summary(account: NotionAccount) -> str:
    user = account.user_name or "user"
    if account.user_email:
        user = f"{user} ({account.user_email})"
    return f"profile={account.profile_name}, user={user}, space_id={account.space_id}"


def _find_account(accounts: list[dict[str, Any]], profile_name: str | None) -> dict[str, Any] | None:
    if not accounts:
        return None

    if profile_name:
        target = profile_name.strip().lower()
        for item in accounts:
            item_profile = str(item.get("profile_name") or "").strip().lower()
            if item_profile == target:
                return item
        return None

    return accounts[0]


def _format_account_label(account: dict[str, Any]) -> str:
    profile_name = str(account.get("profile_name") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    user_name = str(account.get("user_name") or "").strip()
    user_email = str(account.get("user_email") or "").strip()
    label = f"profile: {profile_name}"
    if user_name:
        label += f", user: {user_name}"
    if user_email:
        label += f" ({user_email})"
    return label


def _print_account_status(account: dict[str, Any]) -> int:
    ok, status = _validate_account(account)
    print("Saved account:")
    print(f"  {_format_account_label(account)}")
    print(f"  space_id: {account.get('space_id', '')}")
    print(f"  user_id: {account.get('user_id', '')}")
    print(f"  status: {status}")
    return 0 if ok else 1


def _list_accounts(accounts: list[dict[str, Any]]) -> int:
    if not accounts:
        print("No saved accounts found in accounts.json")
        return 1

    print("Saved profiles:")
    for index, account in enumerate(accounts, start=1):
        ok, status = _validate_account(account)
        marker = "ok" if ok else "invalid"
        print(f"  [{index}] {_format_account_label(account)} | {marker} | {status}")
    return 0


def _check_existing_login(profile_name: str | None = None) -> int:
    accounts = _read_accounts_file()
    if not accounts:
        print("No saved accounts found in accounts.json")
        return 1

    account = _find_account(accounts, profile_name)
    if account is None:
        available = ", ".join(str(item.get("profile_name") or DEFAULT_PROFILE) for item in accounts)
        print(f"Profile not found: {profile_name}")
        print(f"Available profiles: {available}")
        return 1

    return _print_account_status(account)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive Notion2API login helper")
    parser.add_argument("--check", action="store_true", help="Check a saved profile without prompting")
    parser.add_argument("--list", action="store_true", help="List saved profiles and validation state")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Profile name to check or save")
    parser.add_argument("--manual", action="store_true", help="Paste token_v2 manually instead of launching Chrome")
    parser.add_argument("--timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT, help="Seconds to wait for browser sign-in")
    parser.add_argument("--no-env", action="store_true", help="Do not update .env automatically")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check and args.list:
        parser.error("--check and --list cannot be used together")

    if args.list:
        return _list_accounts(_read_accounts_file())

    if args.check:
        return _check_existing_login(args.profile)

    _print_header()

    try:
        if args.manual:
            _open_login_page()
            token_v2 = _prompt_token()
            cookies = {"token_v2": token_v2}
        else:
            print(f"Launching Chrome for {AI_URL}...")
            print(f"Chrome will wait up to {args.timeout} seconds for token_v2 to appear.")
            cookies = _launch_and_extract_cookies(timeout_seconds=args.timeout)
            token_v2 = str(cookies.get("token_v2") or "").strip()
            print("token_v2 captured from Chrome.")

        candidates = _extract_candidates(token_v2, cookies)
        chosen = _choose_account(candidates).with_profile(args.profile)
        merged_accounts = _write_accounts(chosen)
        if not args.no_env:
            _sync_env_file(merged_accounts)
        print()
        print("Login complete.")
        print(f"Saved: {ACCOUNTS_FILE}")
        if not args.no_env:
            print(f"Updated: {ENV_FILE}")
        print(f"Profile: {chosen.profile_name}")
        print(f"User: {chosen.user_name} {f'({chosen.user_email})' if chosen.user_email else ''}")
        print(f"Workspace: {chosen.space_id}")
        if chosen.space_view_id:
            print(f"Space view: {chosen.space_view_id}")
        print(f"Summary: {_readable_account_summary(chosen)}")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1
    except TimeoutError as exc:
        print(f"\nLogin timed out: {exc}")
        print("Try --manual if you want to paste token_v2 instead.")
        return 1
    except Exception as exc:
        print(f"\nLogin failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
