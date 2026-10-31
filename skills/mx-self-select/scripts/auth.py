
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

AUTH_BASE = os.environ.get("EM_AUTH_BASE", "https://ai-saas.eastmoney.com").rstrip("/")
EM_API_KEY = os.environ.get("EM_API_KEY", "").strip()
CLIENT_ID = "mx-self-select"
DEFAULT_EXPIRES_IN = 30 * 24 * 60 * 60
TIMEOUT_SECONDS = 30

EXIT_OK = 0
EXIT_NEED_USER = 10
EXIT_ERROR = 2

AUTH_OK = "ok"
AUTH_NEED_USER = "need_user"
AUTH_ERROR = "error"


def _mx_dir() -> Path:
    return Path.home() / ".mx-skills"


def _key_path() -> Path:
    return _mx_dir() / "em_api_key"


def _pending_path() -> Path:
    return _mx_dir() / "pending_auth.json"


def _revoked_path() -> Path:
    return _mx_dir() / "revoked_em_api_key.json"


def _key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass


def _read_revoked_fingerprints() -> List[str]:
    p = _revoked_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        keys = data.get("keys")
        if isinstance(keys, list):
            return [str(item) for item in keys if item]
    if isinstance(data, list):
        return [str(item) for item in data if item]
    return []


def _write_revoked_fingerprints(keys: List[str]) -> None:
    p = _revoked_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    unique = []
    seen = set()
    for item in keys:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    p.write_text(
        json.dumps({"keys": unique}, ensure_ascii=False),
        encoding="utf-8",
    )
    _chmod_private(p)


def _is_key_revoked(api_key: str) -> bool:
    value = (api_key or "").strip()
    if not value:
        return False
    return _key_fingerprint(value) in set(_read_revoked_fingerprints())


def mark_api_key_revoked(api_key: str) -> None:
    """记住服务端已判定失效的 Key，后续读取时跳过（含环境变量里的旧值）。"""
    value = (api_key or "").strip()
    if not value:
        return
    fingerprint = _key_fingerprint(value)
    keys = _read_revoked_fingerprints()
    if fingerprint not in keys:
        keys.append(fingerprint)
        _write_revoked_fingerprints(keys)


def _unrevoke_key(api_key: str) -> None:
    value = (api_key or "").strip()
    if not value:
        return
    fingerprint = _key_fingerprint(value)
    keys = [item for item in _read_revoked_fingerprints() if item != fingerprint]
    if keys:
        _write_revoked_fingerprints(keys)
        return
    p = _revoked_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def load_em_api_key() -> str:
    """读取可用 Key：环境变量优先，其次落盘文件；已吊销的值一律跳过。"""
    env_value = (os.environ.get("EM_API_KEY") or "").strip()
    if env_value and not _is_key_revoked(env_value):
        return env_value
    p = _key_path()
    if p.exists():
        file_value = p.read_text(encoding="utf-8").strip()
        if file_value and not _is_key_revoked(file_value):
            return file_value
    return ""


def clear_em_api_key_file() -> None:
    p = _key_path()
    try:
        p.unlink(missing_ok=True)
    except TypeError:
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _has_valid_key() -> bool:
    return bool(load_em_api_key())


def _write_api_key(api_key: str) -> Path:
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(api_key.strip() + "\n", encoding="utf-8")
    _chmod_private(path)
    _unrevoke_key(api_key)
    return path


def _read_pending() -> Optional[Dict[str, Any]]:
    p = _pending_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        _clear_pending()
        return None
    if not isinstance(data, dict) or not data.get("token"):
        _clear_pending()
        return None
    if int(data.get("expiresAt", 0)) <= int(time.time()):
        _clear_pending()
        return None
    return data


def _write_pending(token: str, auth_url: str, api_key_url: str, expires_in: int) -> None:
    p = _pending_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "token": token,
        "authUrl": auth_url,
        "apiKeyUrl": api_key_url,
        "expiresAt": int(time.time()) + int(expires_in) - 5,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass


def _clear_pending() -> None:
    p = _pending_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def _http_json_post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib_request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError("http status {0}: {1}".format(exc.code, err_body[:200]))
    except urllib_error.URLError as exc:
        raise RuntimeError(str(exc.reason))
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        raise RuntimeError("接口返回不是 JSON")
    if not isinstance(parsed, dict):
        raise RuntimeError("接口返回不是 JSON 对象: {0!r}".format(parsed))
    return parsed


def _unwrap(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    code = resp_json.get("code")
    if code not in (0, "0", 200, "200", None):
        msg = resp_json.get("message") or resp_json.get("msg") or ""
        raise RuntimeError("接口业务错误 code={0} message={1}".format(code, msg))
    data = resp_json.get("data")
    if data is None:
        raise RuntimeError("接口返回缺少 data: {0!r}".format(resp_json))
    return data


def _api_create() -> Tuple[str, str, str, int]:
    resp = _http_json_post(
        "{0}/api/auth/token/create".format(AUTH_BASE),
        {"clientId": CLIENT_ID},
    )
    data = _unwrap(resp)
    token = data.get("token")
    auth_url = data.get("authUrl")
    if not token or not auth_url:
        raise RuntimeError("接口未返回 token 或 authUrl: {0}".format(data))
    api_key_url = data.get("apiKeyUrl")
    return token, auth_url, api_key_url, int(data.get("expiresIn", DEFAULT_EXPIRES_IN))


def _api_result(token: str) -> Tuple[str, Optional[str]]:
    resp = _http_json_post(
        "{0}/api/auth/token/result".format(AUTH_BASE),
        {"token": token},
    )
    data = _unwrap(resp)
    state = data.get("state") or "invalid"
    api_key = data.get("apiKey")
    return state, api_key


def _print_pending_hint(auth_url: str, api_key_url: str) -> None:
    print("尚未完成授权，请打开下面的链接，用东方财富/妙想 App 扫码绑定：")
    print("授权链接: {0}".format(auth_url))
    print("无法打开授权链接时，可访问: {0}".format(api_key_url))
    print("完成后重新发送指令即可，Skill 会在下次调用时自动检测并落盘 EM_API_KEY。")


def ensure_auth(*, force_refresh: bool = False) -> Dict[str, Any]:
    """
    幂等授权检查：不打印、不 sys.exit，返回结构化结果。

    force_refresh=True：忽略本地已有 Key（用于 401 后强制重新扫码）。

    {"status": AUTH_OK}
    {"status": AUTH_OK, "api_key": str, "newly_obtained": True}
    {"status": AUTH_NEED_USER, "auth_url": str, "api_key_url": str}
    {"status": AUTH_ERROR, "message": str}
    """
    if not force_refresh and _has_valid_key():
        return {"status": AUTH_OK}

    pending = _read_pending()
    if pending is not None:
        try:
            state, api_key = _api_result(pending["token"])
        except Exception as exc:
            return {"status": AUTH_ERROR, "message": "查询授权结果失败: {0}".format(exc)}

        if state == "done" and api_key:
            _write_api_key(api_key)
            _clear_pending()
            return {
                "status": AUTH_OK,
                "api_key": api_key,
                "newly_obtained": True,
            }
        if state == "pending":
            return {
                "status": AUTH_NEED_USER,
                "auth_url": pending.get("authUrl") or pending.get("qrUrl"),
                "api_key_url": pending.get("apiKeyUrl"),
            }
        _clear_pending()

    try:
        token, auth_url, api_key_url, expires_in = _api_create()
    except Exception as exc:
        return {"status": AUTH_ERROR, "message": "创建授权 token 失败: {0}".format(exc)}

    _write_pending(token, auth_url, api_key_url, expires_in)
    return {
        "status": AUTH_NEED_USER,
        "auth_url": auth_url,
        "api_key_url": api_key_url,
    }


def ensure() -> int:
    r = ensure_auth()
    status = r.get("status")
    if status == AUTH_OK:
        return EXIT_OK
    if status == AUTH_NEED_USER:
        _print_pending_hint(r["auth_url"], r["api_key_url"])
        return EXIT_NEED_USER
    print("错误: {0}".format(r.get("message", "授权流程出错")), file=sys.stderr)
    return EXIT_ERROR


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    if len(sys.argv) >= 2 and sys.argv[1] not in ("ensure", "-h", "--help"):
        print("未知命令: {0}。仅支持 `ensure`。".format(sys.argv[1]), file=sys.stderr)
        return EXIT_ERROR
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return EXIT_OK
    return ensure()


if __name__ == "__main__":
    sys.exit(main())
