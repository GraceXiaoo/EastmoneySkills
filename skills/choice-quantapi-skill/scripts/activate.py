#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Choice 量化 API SDK 激活脚本（activate.py）

功能：探测环境 → GUI/SMS 路径激活 → 登录自检

用法：
    python scripts/activate.py                  # 默认：探测后输出 ACTION= + NEXT_STEP=，由 Agent 决定下一步
    python scripts/activate.py --probe          # 同默认，但只输出探测信息（PLATFORM/USERINFO/HAS_GUI/ACTION）
    python scripts/activate.py --gui-launch     # 启动 GUI 激活工具后立即返回（不轮询）
    python scripts/activate.py --gui-launch --keepalive 1800  # 启动 GUI 后保活父命令（仍不轮询）
    python scripts/activate.py --gui-poll       # 轮询 userInfo（gui-launch 之后调用），最长 300s
    python scripts/activate.py --gui-stop       # 用户放弃时通知 GUI 保活命令退出
    python scripts/activate.py --sms <PHONE>    # SMS 激活（用户先发 SXDL 到 9535711）
    python scripts/activate.py --force-login    # 所有 c.start() 加 ForceLogin=1（踢其他设备登录）

输出契约：所有信号均为 KEY=VALUE 行（Agent 按 KEY 前缀解析）。
决策依据：最后一行 RESULT=（ACTIVATE_FAILED / LOGIN_OK / LOGIN_FAILED / ALREADY_ACTIVATED / NEED_GUI_TWO_STEP / NEED_SMS / GUI_LAUNCH_DONE / GUI_STOP_SIGNALLED）。
失败时回头看 ERROR= / HINT= / DETAIL=。
"""

from __future__ import print_function
import sys
import os
import time
import re
import glob
import argparse
import subprocess
import platform
import tempfile
import hashlib

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    # EnumWindows 回调签名: BOOL CALLBACK(HWND, LPARAM)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    # 显式声明 argtypes/restype —— 缺省下 ctypes 把返回值/HWND 按 c_int(32-bit)处理,
    # 64-bit Windows 上会截断句柄。下面这些都是写给 64-bit 跑得稳的。
    _user32 = ctypes.windll.user32
    _user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    _user32.AllowSetForegroundWindow.restype = wintypes.BOOL
    _user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindowAsync.restype = wintypes.BOOL
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL

# ─── 常量 ────────────────────────────────────────────────────────────────────
SDK_DIRNAME = "EMQuantAPI_Python"
INSTALL_SCRIPT = "installEmQuantAPI.py"
CHOICE_BASEDIR = ".choice"  # SDK 安装目录名
MIAOXIANG_WORK_ROOT = "/workspace/user_space"

# SMS 重试参数
SMS_MAX_RETRIES = 3
SMS_RETRY_INTERVAL = 20  # seconds

# GUI userInfo 轮询参数
POLL_INTERVAL = 3  # seconds
POLL_MAX_WAIT = 300  # seconds (100 iterations)
KEEPALIVE_POLL_INTERVAL = 1  # seconds


# ─── 辅助 ────────────────────────────────────────────────────────────────────
def _print_kv(key, value):
    print("{}={}".format(key, value))
    sys.stdout.flush()


def _gui_keepalive_stop_file(userinfo_path):
    """按 userInfo 路径生成稳定的跨进程停止标记路径。"""
    normalized = os.path.normcase(os.path.abspath(userinfo_path or ""))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), "choice-quantapi-activate", digest + ".stop")


def _clear_gui_keepalive_stop(userinfo_path):
    stop_file = _gui_keepalive_stop_file(userinfo_path)
    try:
        if os.path.isfile(stop_file):
            os.remove(stop_file)
    except OSError as e:
        _print_kv("WARNING", "Cannot remove stale GUI stop marker: {}".format(e))
    return stop_file


def _signal_gui_keepalive_stop(userinfo_path):
    """通知独立的 GUI 保活进程退出；不存在保活进程时也可安全调用。"""
    stop_file = _gui_keepalive_stop_file(userinfo_path)
    stop_dir = os.path.dirname(stop_file)
    try:
        if not os.path.isdir(stop_dir):
            os.makedirs(stop_dir)
        with open(stop_file, "w") as f:
            f.write(str(os.getpid()))
        return stop_file
    except Exception as e:
        _print_kv("WARNING", "Cannot signal GUI keepalive stop: {}".format(e))
        return None


def _is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _keep_gui_process_alive(gui_pid, userinfo_path, seconds):
    """保持当前 Python 命令存活，直到收到停止标记或达到最长时间。"""
    stop_file = _clear_gui_keepalive_stop(userinfo_path)
    _print_kv("KEEPALIVE_SECONDS", seconds)
    _print_kv("KEEPALIVE_STOP_FILE", stop_file)
    _print_kv("HINT", "Run --gui-poll separately; it will stop keepalive after final login result")
    _print_kv("RESULT", "GUI_LAUNCH_DONE")

    deadline = time.time() + seconds
    while time.time() < deadline:
        if os.path.isfile(stop_file):
            try:
                os.remove(stop_file)
            except OSError:
                pass
            return
        if not _is_process_alive(gui_pid):
            return
        time.sleep(KEEPALIVE_POLL_INTERVAL)


def _try_remove_userinfo(userinfo_path):
    """best-effort 删除 userInfo（verify_login 失败后视为 stale，删掉让后续激活流程重跑）。

    删不掉不致命——SMS 的 c.start(SXDL) / GUI 激活工具成功都会覆盖写新凭据；
    默认模式 / --gui-launch / --gui-poll 依赖删除把 action 从 SKIP 变回 GUI/SMS 或避免轮询命中
    stale 文件（删失败由调用方兜底）。
    """
    try:
        os.remove(userinfo_path)
        _print_kv("STEP", "removed stale userInfo: {}".format(userinfo_path))
        return True
    except OSError as e:
        _print_kv("WARNING", "could not remove userInfo ({}); activation will try to overwrite".format(e))
        return False


# 凭据失效类错误码：userInfo 文件还在但内容失效，删 stale 后重新激活可恢复。
# 其它错误（网络/限频/subprocess 异常等）不在此列——不删 userInfo，避免误删仍有效的凭据。
STALE_CREDENTIAL_ERRORS = {"10001020", "10001019"}


def _parse_error_code(login_check_output):
    """从 LOGIN_CHECK 子进程输出里提取 ErrorCode 数字串（如 '10001020'）。"""
    m = re.search(r"ErrorCode=(\S+)", login_check_output)
    return m.group(1) if m else ""


def _abort_non_stale(err_code):
    """verify_login 失败但非凭据失效类：不删 userInfo，报失败退出（避免网络抖动等误删有效凭据）。

    10001009 单独处理：userInfo 仍有效，只是账号在他设备登录，需 --force-login（而非删凭据/排查网络）。
    """
    if err_code == "10001009":
        _print_kv("HINT", "账号已在其他设备登录（ErrorCode=10001009），userInfo 仍有效、无需重激活；"
                          "请**先问用户**是否踢掉其它设备，确认后用 `activate.py --force-login` 重跑")
    else:
        _print_kv("HINT", "登录自检失败且非凭据失效类（ErrorCode={}），未删除 userInfo；请排查网络/限频后重跑".format(err_code))
    _print_kv("RESULT", "ACTIVATE_FAILED")
    sys.exit(1)


def _run_capture(cmd, timeout=None, env=None, cwd=None):
    """跨 Py2/Py3 的 subprocess 调用,返回 (returncode, stdout, stderr)。

    - stdout/stderr 始终为 str(utf-8 解码,errors='replace'),适合做 ASCII 子串匹配。
    - Py2 下 Popen.communicate() 不支持 timeout 参数,会被忽略(timeout 是 Py3.3+)。
    - 调用方负责捕获 subprocess.TimeoutExpired / OSError 等异常。
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    kwargs = {}
    if timeout is not None and sys.version_info >= (3, 3):
        kwargs["timeout"] = timeout
    try:
        stdout, stderr = proc.communicate(**kwargs)
    except BaseException:
        try:
            proc.kill()
            proc.communicate()
        except Exception:
            pass
        raise
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return proc.returncode, stdout or "", stderr or ""


def _get_sdk_base():
    """获取 SDK 安装基目录。

    妙想 Work 环境下优先使用 /workspace/user_space/.choice，保证跨容器持久化；
    妙想Claw 环境下用 $HOME/.openclaw/.choice；其他环境仍用 $HOME/.choice。
    路径决策的唯一入口,下游所有路径(SDK 工作目录/userInfo/备份)均派生自此处。
    """
    home = os.path.expanduser("~")
    if _is_miaoxiang_work():
        return os.path.join(MIAOXIANG_WORK_ROOT, CHOICE_BASEDIR)
    if _is_miaoxiang_claw():
        return os.path.join(home, ".openclaw", CHOICE_BASEDIR)
    return os.path.join(home, CHOICE_BASEDIR)


def _detect_pyver():
    """根据当前 Python 版本返回 python3/python2"""
    return "python3" if sys.version_info[0] >= 3 else "python2"


def _detect_platform():
    """
    检测操作系统平台，返回 SDK libs/ 下的子目录名。

    返回 str: "windows" / "mac" / "linux/x64" / "linux/x86" / "linuxArm/x64"
    """
    s = platform.system()
    m = platform.machine()

    if s == "Windows":
        return "windows"
    elif s == "Darwin":
        return "mac"
    elif s == "Linux":
        if m in ("aarch64", "arm64"):
            return "linuxArm/x64"
        elif m == "x86_64":
            return "linux/x64"
        elif re.match(r"i\d86$", m):
            return "linux/x86"
        else:
            _print_kv("ACTION", "ABORT_ARCH={}".format(m))
            return None
    else:
        _print_kv("ACTION", "ABORT_OS={}".format(s))
        return None


def _find_sdk_work_dir(pyver):
    """找到 SDK 工作目录（<SDK基目录>/EMQuantAPI_Python/<PYVER>/，基目录见 _get_sdk_base）"""
    sdk_base = _get_sdk_base()
    sdk_work = os.path.join(sdk_base, SDK_DIRNAME, pyver)
    if os.path.isfile(os.path.join(sdk_work, INSTALL_SCRIPT)):
        return sdk_work
    # 也可能没按约定放——尝试另一个 PYVER
    alt_pyver = "python2" if pyver == "python3" else "python3"
    alt_work = os.path.join(sdk_base, SDK_DIRNAME, alt_pyver)
    if os.path.isfile(os.path.join(alt_work, INSTALL_SCRIPT)):
        _print_kv("WARNING", "PYVER={} but SDK found at {}; consider matching interpreter".format(
            pyver, alt_work))
        return alt_work
    return None


def _is_miaoxiang_claw():
    """检测是否运行在妙想Claw(项目内部 Web IDE / 云端开发容器)中。

    满足任一组合即认定(共同前提:~/.openclaw/extensions/mx-claw 标记目录存在):
    1. INGRESS_URL + KUBERNETES_PORT 环境变量同时存在(K8s 部署模式)
    2. WUYING_INSTANCE_ID 环境变量存在

    """
    claw_marker = os.path.join(os.path.expanduser("~"), ".openclaw", "extensions", "mx-claw")
    if not os.path.exists(claw_marker):
        return False
    if os.environ.get("INGRESS_URL") and os.environ.get("KUBERNETES_PORT"):
        return True
    if os.environ.get("WUYING_INSTANCE_ID"):
        return True
    return False


def _is_miaoxiang_work():
    """存在持久化目录 /workspace/user_space/ 时认定为妙想 Work 环境。"""
    return os.path.isdir(MIAOXIANG_WORK_ROOT)


def _linux_has_physical_display():
    """Linux: 当前用户是否真坐在物理显示器前(双层判定)。

    L1 — systemd-logind 的会话元数据(权威):
        loginctl show-user <uid> -p Display 拿到该用户的"主图形会话" ID,
        loginctl show-session <sid> 再要 Remote/Active/Seat/Type 四项。
        本地真桌面应满足:Remote=no、Active=yes、Seat 以 'seat' 开头、Type 是 x11/wayland。
        不依赖 $XDG_SESSION_ID(sudo/su/IDE 转发会丢),也不依赖 $SSH_CONNECTION
        (sudo 也会丢);VNC / xrdp 即使有真 X 会话也被 logind 标 Remote=yes,正确否决。

    L2 — DRM 层显示口物理 connected:
        /sys/class/drm/card*-*/status 至少一行内容是 "connected",证明真的有显示器
        插在 GPU 端口上。headless 云主机 / 容器 / Xvfb 这里会全部 disconnected 或读不到。

    任一层不满足 → False(严格默认非 GUI,宁可让用户走 SMS 也不弹到无人的会话)。
    """
    # L1: logind 会话信息
    try:
        uid = os.getuid()  # 仅 Unix 有,本函数本就只在 Linux 调用
        _, out, _ = _run_capture(
            ["loginctl", "show-user", str(uid), "-p", "Display"], timeout=5,
        )
        m = re.search(r"^Display=(.+)$", out, re.M)
        if not m or not m.group(1).strip():
            return False
        sid = m.group(1).strip()
        _, out, _ = _run_capture(
            ["loginctl", "show-session", sid,
             "-p", "Remote", "-p", "Active", "-p", "Seat", "-p", "Type"],
            timeout=5,
        )
        kv = dict(re.findall(r"^([A-Za-z]+)=(.*)$", out, re.M))
        if kv.get("Remote") != "no":
            return False
        if kv.get("Active") != "yes":
            return False
        if not kv.get("Seat", "").startswith("seat"):
            return False
        if kv.get("Type") not in ("x11", "wayland"):
            return False
    except Exception:
        return False

    # L2: 至少一个 DRM 显示口物理 connected
    try:
        for status_file in glob.glob("/sys/class/drm/card*-*/status"):
            try:
                with open(status_file) as f:
                    if f.read().strip() == "connected":
                        return True
            except (OSError, IOError):
                continue
    except Exception:
        pass
    return False


def _mac_has_gtk3():
    """macOS: loginactivator_mac 动态链接 libgtk-3.0.dylib,缺这个库进程会 dyld 加载失败立即崩溃。
    检查 dyld 在本机的标准搜索路径,任一命中即认为可用。

    候选路径来自 dyld 实测搜索顺序 + brew 两种前缀:
    - /opt/homebrew/opt/gtk+3/lib/  (Apple Silicon brew keg path)
    - /opt/homebrew/lib/            (Apple Silicon brew linked)
    - /usr/local/opt/gtk+3/lib/     (Intel brew keg path)
    - /usr/local/lib/               (Intel brew linked / 通用)
    - /usr/lib/                     (系统库,基本不会有)

    同时考虑无版本符号链接(libgtk-3.0.dylib)和带 ABI 版本号的实文件(libgtk-3.0.0.dylib)。
    任一命中返回命中路径,否则返回 None。
    """
    candidates = []
    for base in (
        "/opt/homebrew/opt/gtk+3/lib",
        "/opt/homebrew/lib",
        "/usr/local/opt/gtk+3/lib",
        "/usr/local/lib",
        "/usr/lib",
    ):
        for name in ("libgtk-3.0.dylib", "libgtk-3.0.0.dylib"):
            candidates.append(os.path.join(base, name))
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _detect_gui(platform_str):
    """
    检测当前环境是否有 GUI 桌面可用。默认非 GUI,只有正向证据齐了才返回 True。

    Windows: tasklist 看到 explorer.exe(Session 0 服务环境会误判,已知限制)
    macOS:   $SSH_TTY 未设置(launchd 后台环境会误判,已知限制) + libgtk-3.0.dylib 可加载
             (loginactivator_mac 链接 gtk+3,缺库会 dyld 失败崩溃,此时降级 SMS)
    Linux:   委托 _linux_has_physical_display() —— logind 会话(Remote=no/Active=yes/Seat=seat*/Type=x11|wayland)
             + /sys/class/drm 物理 connected,双层确认
    """
    if platform_str == "windows":
        # 检查 explorer.exe（桌面会话指标）
        try:
            _, stdout, _ = _run_capture(
                ["tasklist", "/FI", "IMAGENAME eq explorer.exe"],
                timeout=10,
            )
            if "explorer.exe" in stdout.lower():
                return True
        except Exception:
            pass
        return False

    elif platform_str == "mac":
        # macOS: 非 SSH 环境 + gtk+3 已装才算有 GUI;缺 gtk+3 时降级到 SMS 路径
        if os.environ.get("SSH_TTY") is not None:
            return False
        gtk_path = _mac_has_gtk3()
        if gtk_path:
            _print_kv("MAC_GTK3", "yes path={}".format(gtk_path))
            return True
        _print_kv("MAC_GTK3", "no")
        _print_kv("HINT", "libgtk-3.0.dylib 未在 dyld 标准路径找到,loginactivator_mac 会崩溃,降级 SMS。"
                          "如需 GUI 激活请先 `brew install gtk+3` 再重跑 activate.py")
        return False

    elif platform_str.startswith("linux/") or platform_str.startswith("linuxArm/"):
        # 妙想Claw 容器即使 logind/DRM 检查通过也强制走 SMS —— 弹窗会落到容器里用户看不见
        if _is_miaoxiang_claw():
            return False
        # 其他情况下检测是否真桌面
        return _linux_has_physical_display()

    return False


def _find_activator(platform_str, sdk_libs_dir):
    """
    在 SDK libs/<platform>/ 下找到激活工具可执行文件路径。

    返回 (path, name) 或 None。
    """
    act_dir = os.path.join(sdk_libs_dir, platform_str)

    if platform_str == "windows":
        exe = os.path.join(act_dir, "LoginActivator.exe")
        if os.path.isfile(exe):
            return exe, "LoginActivator.exe"

    elif platform_str == "mac":
        exe = os.path.join(act_dir, "loginactivator_mac")
        if os.path.isfile(exe):
            return exe, "loginactivator_mac"

    elif platform_str.startswith("linux/") or platform_str.startswith("linuxArm/"):
        # 优先 loginactivator_ubuntu，其次 loginactivator
        for name in ("loginactivator_ubuntu", "loginactivator"):
            exe = os.path.join(act_dir, name)
            if os.path.isfile(exe):
                return exe, name

    return None


# ─── Probe 模式 ──────────────────────────────────────────────────────────────
def probe(pyver):
    """
    探测环境：平台 + userInfo + GUI → 输出 ACTION=。

    返回 dict: platform, userinfo_path, has_gui, action
    """
    platform_str = _detect_platform()
    if platform_str is None:
        return {"action": "ABORT"}

    _print_kv("PLATFORM", platform_str)

    # 找 SDK 工作目录
    sdk_work_dir = _find_sdk_work_dir(pyver)
    if sdk_work_dir is None:
        _print_kv("ERROR", "SDK not found; run install.py first")
        _print_kv("ACTION", "ABORT_NO_SDK")
        return {"action": "ABORT_NO_SDK"}

    libs_dir = os.path.join(sdk_work_dir, "libs")
    userinfo_path = os.path.join(libs_dir, platform_str, "userInfo")

    _print_kv("USERINFO", userinfo_path)

    # userInfo 已存在 → 直接跳过激活
    if os.path.isfile(userinfo_path):
        _print_kv("ACTION", "SKIP_ALREADY_ACTIVATED")
        return {
            "platform": platform_str,
            "userinfo_path": userinfo_path,
            "has_gui": None,
            "action": "SKIP_ALREADY_ACTIVATED",
        }

    # 检测 GUI
    has_gui = _detect_gui(platform_str)
    _print_kv("HAS_GUI", "yes" if has_gui else "no")

    action = "GUI" if has_gui else "SMS"
    _print_kv("ACTION", action)

    return {
        "platform": platform_str,
        "userinfo_path": userinfo_path,
        "has_gui": has_gui,
        "action": action,
    }


# ─── GUI 激活路径 ────────────────────────────────────────────────────────────
def _launch_activator_windows(exe_path):
    """
    Windows: 启动 LoginActivator.exe 并用 ctypes SetForegroundWindow 抢前台焦点。
    纯 Python ctypes 实现，避免 PowerShell 编码地狱。

    返回 subprocess.Popen 对象的 pid。
    """
    # ① AllowSetForegroundWindow(ASFW_ANY=0xFFFFFFFF) —— 解锁前台锁定
    try:
        _user32.AllowSetForegroundWindow(0xFFFFFFFF)
    except Exception:
        pass  # 无权限 —— 不致命

    # ② 启动进程
    proc = subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
    pid = proc.pid
    _print_kv("STEP", "LoginActivator.exe launched, pid={}".format(pid))

    # ③ 等窗口句柄就绪（最多 5 秒），然后 SetForegroundWindow
    try:
        for _ in range(50):  # 5 秒 × 100ms
            hwnd_val = _find_window_by_pid(pid)
            if hwnd_val:
                _user32.ShowWindowAsync(hwnd_val, 9)  # SW_RESTORE=9
                _user32.SetForegroundWindow(hwnd_val)
                _print_kv("FG_RESULT", "FG_OK pid={}".format(pid))
                return pid
            time.sleep(0.1)

        _print_kv("FG_RESULT", "FG_NO_WINDOW pid={}".format(pid))
        _print_kv("HINT", "窗口可能在任务栏闪动，让用户手动点击 LoginActivator 图标")
    except Exception as e:
        _print_kv("FG_RESULT", "FG_ERROR: {}".format(e))

    return pid


def _find_window_by_pid(pid):
    """Windows: 用 EnumWindows 找到属于指定 PID 的主窗口句柄(可见且有标题)。"""
    try:
        result_hwnd = [0]  # list 借给闭包做可变容器

        def enum_callback(hwnd, lparam):
            proc_id = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid and _user32.IsWindowVisible(hwnd):
                if _user32.GetWindowTextLengthW(hwnd) > 0:
                    result_hwnd[0] = hwnd
                    return False  # 停止枚举
            return True  # 继续枚举

        _user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return result_hwnd[0]
    except Exception:
        return 0


def _mac_bring_to_front(pid):
    """macOS: 用 osascript 把指定 PID 的窗口拉到前台。

    gtk+3 窗口默认不抢焦点,用户可能看不到弹出的激活窗口。
    尝试通过进程名激活;如果失败则输出 FG_RESULT 供 Agent 追加提示。
    """
    _print_kv("STEP", "Attempting to bring activator to front on macOS")
    try:
        # 先从 ps 拿进程名
        _, ps_out, _ = _run_capture(["ps", "-p", str(pid), "-o", "comm="], timeout=5)
        proc_name = ps_out.strip()
        if not proc_name:
            _print_kv("FG_RESULT", "FG_NO_PROCNAME pid={}".format(pid))
            _print_kv("HINT", "激活窗口可能已弹出但未抢到前台焦点。请去 Dock 点一下激活工具图标")
            return

        # 尝试用 AppleScript 激活
        script = 'tell application "System Events" to set frontmost of process "{}" to true'.format(proc_name)
        rc, _, err = _run_capture(["osascript", "-e", script], timeout=5)
        if rc == 0:
            _print_kv("FG_RESULT", "FG_OK pid={}".format(pid))
        else:
            _print_kv("FG_RESULT", "FG_NO_WINDOW pid={}".format(pid))
            _print_kv("HINT", "激活窗口可能已弹出但未抢到前台焦点。请去 Dock 点一下 {} 图标".format(proc_name))
    except Exception as e:
        _print_kv("FG_RESULT", "FG_ERROR: {}".format(e))


def _launch_activator_unix(exe_path, platform_str):
    """
    macOS / Linux: 直接 exec 激活工具(chmod +x + subprocess),detach 到新会话避免随父退出连带。

    用 start_new_session(Py3.2+) 或 preexec_fn=os.setsid(Py2) 替代外部 nohup,
    免去 minimal 容器无 nohup 时的 FileNotFoundError。

    关键: cwd 必须设为可执行文件所在目录。loginactivator_mac / loginactivator_ubuntu
    是 C++ 程序,内部用相对路径读取同目录资源文件;若 cwd 不正确会因路径解析越界
    抛出 std::out_of_range 崩溃。Windows 版同理(已在 _launch_activator_windows 中处理)。

    返回 pid。
    """
    # chmod +x
    try:
        os.chmod(exe_path, 0o755)
    except OSError:
        pass  # 可能已经可执行

    # cwd 设为可执行文件所在目录,与 Windows 版保持一致
    activator_cwd = os.path.dirname(exe_path)

    devnull = open(os.devnull, "wb")  # subprocess.DEVNULL 是 Py3.3+,这样 Py2 也能用
    popen_kwargs = dict(stdout=devnull, stderr=devnull, cwd=activator_cwd)
    if sys.version_info >= (3, 2):
        popen_kwargs["start_new_session"] = True
    elif hasattr(os, "setsid"):
        popen_kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen([exe_path], **popen_kwargs)
    return proc.pid


# ─── SMS 激活路径 ────────────────────────────────────────────────────────────
def sms_activate(phone, userinfo_path, force_login=False):
    """
    SMS 激活路径：用户上行发 SXDL 到 9535711 → 脚本用 c.start(SXDL) 完成登录。

    带 3 次重试容忍 SMS 投递延迟，间隔 20 秒。
    登录成功后立即确认 userInfo 写盘。

    返回 True（激活成功）/ False（失败）。
    """
    # 验证手机号格式
    phone = re.sub(r"\D", "", phone)  # 只保留数字(吃掉空格、+、-、括号等)
    if len(phone) == 13 and phone.startswith("86"):
        phone = phone[2:]  # 剥掉 +86 国家码
    if not re.match(r"^1\d{10}$", phone):
        _print_kv("ERROR", "Invalid phone number: {} (expect 11-digit Chinese mobile)".format(phone))
        return False

    _print_kv("STEP", "SMS activation with phone={}".format(phone))

    # 构造 c.start() 登录参数
    login_options = "LoginMode=SXDL,PhoneNumber={}".format(phone)
    if force_login:
        login_options += ",ForceLogin=1"

    # 3 次重试
    for i in range(SMS_MAX_RETRIES):
        _print_kv("STEP", "attempt {} of {}".format(i + 1, SMS_MAX_RETRIES))

        # 用 subprocess 跑 c.start():① 避免父进程 import EmQuantAPI 后的状态污染;
        # ② cwd 设到 $HOME,避开调用方 cwd 下可能存在的同名 EmQuantAPI.py 抢 import。
        # 注意:userinfo_path 含反斜杠(Windows),必须用 repr() 序列化成合法 Python 字面量,
        # 否则 \U / \a / \b 会被 Python 解析成转义,子进程直接 SyntaxError。
        py = sys.executable
        script = (
            "from __future__ import print_function\n"
            "import os, sys\n"
            "if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')\n"
            "from EmQuantAPI import c\n"
            "r = c.start({login}, '')\n"
            "print('ErrorCode=%s ErrorMsg=%s' % (r.ErrorCode, r.ErrorMsg))\n"
            "sys.stdout.flush()\n"
            "c.stop()\n"
            "if r.ErrorCode == 0:\n"
            "    if os.path.isfile({path}):\n"
            "        print('ACTIVATED USERINFO=' + {path}); sys.exit(0)\n"
            "    print('LOGIN_OK_NO_USERINFO PATH=' + {path}); sys.exit(2)\n"
            "sys.exit(1)\n"
        ).format(login=repr(login_options), path=repr(userinfo_path))

        env = dict(os.environ, PYTHONIOENCODING="utf-8")  # Py2/3 兼容写法
        try:
            _, stdout, _ = _run_capture(
                [py, "-c", script],
                timeout=60,
                env=env,
                cwd=os.path.expanduser("~"),
            )
        except Exception as e:
            _print_kv("attempt_{}_error".format(i + 1), str(e))
            stdout = ""

        output = stdout.strip()
        _print_kv("attempt_{}_output".format(i + 1), output)

        # 解析输出
        if "ACTIVATED" in output:
            _print_kv("ACTIVATED", "USERINFO={}".format(userinfo_path))
            return True

        if "LOGIN_OK_NO_USERINFO" in output:
            _print_kv("DETAIL", "LOGIN_OK_NO_USERINFO PATH={}".format(userinfo_path))
            _print_kv("HINT", "登录成功但 userInfo 未写盘——可能是路径权限异常")
            return False

        # 失败 → 等待后重试
        if i < SMS_MAX_RETRIES - 1:
            _print_kv("STEP", "Waiting {}s before retry...".format(SMS_RETRY_INTERVAL))
            time.sleep(SMS_RETRY_INTERVAL)

    _print_kv("GIVEUP_AFTER_RETRIES", "")
    return False


# ─── 登录自检 ────────────────────────────────────────────────────────────────
def verify_login(force_login=False):
    """
    登录自检：c.start() → c.stop() → 输出 ErrorCode + ErrorMsg + RESULT=LOGIN_OK/LOGIN_FAILED。

    返回 (ok, error_code)：ok 为是否通过；error_code 是 ErrorCode 数字串（供调用方判断
    是否凭据失效类 STALE_CREDENTIAL_ERRORS，决定要不要删 stale userInfo）。**用返回值判断
    必须解包** `ok, err = verify_login(...)`——元组在 `if verify_login(...)` 里恒真，禁止直接当 bool。
    """
    _print_kv("STEP", "Login verification...")

    login_options = "ForceLogin=1" if force_login else ""
    py = sys.executable
    script = (
        "from __future__ import print_function\n"
        "import sys\n"
        "if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')\n"
        "from EmQuantAPI import c\n"
        "r = c.start({login}, '')\n"
        "c.stop()\n"
        "print('ErrorCode=%s ErrorMsg=%s' % (r.ErrorCode, r.ErrorMsg))\n"
        "sys.exit(0 if r.ErrorCode == 0 else 1)\n"
    ).format(login=repr(login_options))

    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # Py2/3 兼容
    try:
        rc, stdout, _ = _run_capture(
            [py, "-c", script],
            timeout=30,
            env=env,
            cwd=os.path.expanduser("~"),
        )
    except Exception as e:
        _print_kv("LOGIN_CHECK", "subprocess error: {}".format(e))
        _print_kv("RESULT", "LOGIN_FAILED")
        return False, ""

    output = stdout.strip()
    _print_kv("LOGIN_CHECK", output)
    err_code = _parse_error_code(output)

    if rc == 0:
        _print_kv("RESULT", "LOGIN_OK")
        return True, err_code
    else:
        _print_kv("RESULT", "LOGIN_FAILED")
        return False, err_code


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Choice 量化 API SDK 激活脚本")
    parser.add_argument("--probe", action="store_true",
                        help="仅探测环境，输出 ACTION= 后退出")
    parser.add_argument("--sms", metavar="PHONE", type=str,
                        help="SMS 激活模式，需提供 11 位手机号")
    parser.add_argument("--gui-launch", action="store_true",
                        help="仅启动 GUI 激活工具并输出 GUI_LAUNCHED，不轮询 userInfo（用于 Agent 先发用户指引再轮询）")
    parser.add_argument("--keepalive", metavar="SECONDS", type=int,
                        help="与 --gui-launch 同用：启动后保活当前命令指定秒数，不轮询 userInfo")
    parser.add_argument("--gui-poll", action="store_true",
                        help="仅轮询 userInfo 文件（用于 --gui-launch 之后）")
    parser.add_argument("--gui-stop", action="store_true",
                        help="通知当前 userInfo 对应的 GUI 保活命令退出")
    parser.add_argument("--force-login", action="store_true",
                        help="所有 c.start() 加 ForceLogin=1（踢掉其他设备）")
    args = parser.parse_args()

    if args.keepalive is not None and not args.gui_launch:
        parser.error("--keepalive must be used with --gui-launch")
    if args.keepalive is not None and args.keepalive <= 0:
        parser.error("--keepalive SECONDS must be greater than 0")
    if args.keepalive is not None and (args.probe or args.gui_poll or args.gui_stop or args.sms):
        parser.error("--keepalive cannot be combined with --probe, --gui-poll, --gui-stop, or --sms")
    if args.gui_stop and (args.gui_launch or args.gui_poll or args.sms):
        parser.error("--gui-stop cannot be combined with --gui-launch, --gui-poll, or --sms")

    pyver = _detect_pyver()
    sdk_base = _get_sdk_base()
    _print_kv("SDK_BASE", sdk_base)
    if _is_miaoxiang_work():
        _print_kv("MXWORK_ENV", "yes")
    elif _is_miaoxiang_claw():
        _print_kv("MXCLAW_ENV", "yes")
    _print_kv("PYVER", pyver)

    # ── --probe 模式 ──
    if args.probe:
        probe_result = probe(pyver)
        sys.exit(0 if probe_result["action"] not in ("ABORT", "ABORT_NO_SDK") else 1)

    # ── --gui-stop 模式：通知保活命令退出 ──
    if args.gui_stop:
        probe_result = probe(pyver)
        userinfo_path = probe_result.get("userinfo_path", "")
        if not userinfo_path:
            _print_kv("ERROR", "Cannot determine userinfo path")
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)
        stop_file = _signal_gui_keepalive_stop(userinfo_path)
        if stop_file is None:
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)
        _print_kv("KEEPALIVE_STOP_FILE", stop_file)
        _print_kv("RESULT", "GUI_STOP_SIGNALLED")
        sys.exit(0)

    # ── --gui-launch 模式：仅弹窗，不轮询 ──
    if args.gui_launch:
        probe_result = probe(pyver)
        if probe_result["action"] == "SKIP_ALREADY_ACTIVATED":
            ok, err_code = verify_login(args.force_login)
            if ok:
                _print_kv("RESULT", "ALREADY_ACTIVATED")
                sys.exit(0)
            if err_code not in STALE_CREDENTIAL_ERRORS:
                _abort_non_stale(err_code)  # 非凭据失效类 → 不删，报失败退出
            # 凭据失效类 → 删 stale userInfo 后重新探测走 GUI 激活
            _print_kv("STEP", "userInfo stale (ErrorCode={}); removing".format(err_code))
            _try_remove_userinfo(probe_result["userinfo_path"])
            probe_result = probe(pyver)
        if probe_result["action"] != "GUI":
            _print_kv("ERROR", "--gui-launch only valid when ACTION=GUI; current ACTION={}".format(probe_result["action"]))
            _print_kv("HINT", "若 stale userInfo 删不掉或环境无 GUI，请改用 --sms <phone>")
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)
        # 启动激活工具但不轮询
        _print_kv("STEP", "=== GUI launch only (no polling) ===")
        platform_str = probe_result["platform"]
        userinfo_path = probe_result["userinfo_path"]
        sdk_work_dir = _find_sdk_work_dir(pyver)
        libs_dir = os.path.join(sdk_work_dir, "libs")
        activator_info = _find_activator(platform_str, libs_dir)
        if activator_info is None:
            _print_kv("ERROR", "No activator binary found")
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)
        exe_path, exe_name = activator_info
        _print_kv("STEP", "Launching activator: {}".format(exe_name))
        if platform_str == "windows":
            pid = _launch_activator_windows(exe_path)
        else:
            pid = _launch_activator_unix(exe_path, platform_str)
        _print_kv("GUI_LAUNCHED", "pid={}".format(pid))

        # ── 进程存活性检查: 等待 2 秒,确认激活工具没有立即崩溃 ──
        time.sleep(2)
        try:
            os.kill(pid, 0)  # 发信号 0 不杀进程,仅检测存在性
        except OSError:
            _print_kv("ERROR", "Activator process (pid={}) exited immediately — likely a crash".format(pid))
            _print_kv("HINT", "C++ activator may need cwd = its own directory; "
                             "check that resource files exist alongside the binary")
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)

        # ── macOS: 尝试把激活窗口拉到前台 ──
        if platform_str == "mac":
            _mac_bring_to_front(pid)

        _print_kv("USERINFO_PATH", userinfo_path)
        if args.keepalive is not None:
            _keep_gui_process_alive(pid, userinfo_path, args.keepalive)
        else:
            _print_kv("RESULT", "GUI_LAUNCH_DONE")
        sys.exit(0)

    # ── --gui-poll 模式：仅轮询 userInfo ──
    if args.gui_poll:
        probe_result = probe(pyver)
        userinfo_path = probe_result.get("userinfo_path", "")
        if not userinfo_path:
            _print_kv("ERROR", "Cannot determine userinfo path; run --probe first")
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)
        # 如果已经激活了
        if probe_result["action"] == "SKIP_ALREADY_ACTIVATED":
            ok, err_code = verify_login(args.force_login)
            if ok:
                _signal_gui_keepalive_stop(userinfo_path)
                _print_kv("RESULT", "ALREADY_ACTIVATED")
                sys.exit(0)
            if err_code not in STALE_CREDENTIAL_ERRORS:
                _signal_gui_keepalive_stop(userinfo_path)
                _abort_non_stale(err_code)
            # 凭据失效类 → 删 stale userInfo 后继续轮询等 GUI 写新凭据
            _print_kv("STEP", "userInfo stale (ErrorCode={}); removing".format(err_code))
            if not _try_remove_userinfo(probe_result["userinfo_path"]):
                # 删失败 → 旧文件仍在，轮询会立刻命中 stale 文件打出假 ACTIVATED，直接报失败
                _print_kv("ERROR", "stale userInfo 删除失败，无法重新激活")
                _print_kv("HINT", "请手动删除 {} 后重跑，或用 --sms <phone>".format(probe_result["userinfo_path"]))
                _print_kv("RESULT", "ACTIVATE_FAILED")
                sys.exit(1)
        # 轮询
        _print_kv("STEP", "=== Polling userInfo (3s interval, max 300s) ===")
        for i in range(POLL_MAX_WAIT // POLL_INTERVAL):
            if os.path.isfile(userinfo_path):
                elapsed = (i + 1) * POLL_INTERVAL
                _print_kv("ACTIVATED", "after {}s".format(elapsed))
                ok, _ = verify_login(args.force_login)
                _signal_gui_keepalive_stop(userinfo_path)
                _print_kv("RESULT", "LOGIN_OK" if ok else "LOGIN_FAILED")
                sys.exit(0 if ok else 1)
            time.sleep(POLL_INTERVAL)
        _print_kv("TIMEOUT", "{}s".format(POLL_MAX_WAIT))
        _print_kv("RESULT", "ACTIVATE_FAILED")
        sys.exit(1)

    # ── --sms 模式 ──
    if args.sms:
        # 先 probe 找 userinfo 路径
        probe_result = probe(pyver)
        if probe_result["action"] in ("ABORT", "ABORT_NO_SDK"):
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)

        # userInfo 已存在 → 自检通过即完工；凭据失效类则继续 SMS 激活（c.start(SXDL) 覆盖旧凭据，无需删）
        if probe_result["action"] == "SKIP_ALREADY_ACTIVATED":
            ok, err_code = verify_login(args.force_login)
            if ok:
                _print_kv("RESULT", "ALREADY_ACTIVATED")
                sys.exit(0)
            if err_code not in STALE_CREDENTIAL_ERRORS:
                _abort_non_stale(err_code)
            _print_kv("STEP", "userInfo stale (ErrorCode={}); re-activating via SMS (c.start will overwrite)".format(err_code))

        userinfo_path = probe_result["userinfo_path"]
        success = sms_activate(args.sms, userinfo_path, force_login=args.force_login)

        if success:
            ok, _ = verify_login(args.force_login)
            sys.exit(0 if ok else 1)
        else:
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)

    # ── 自动模式（默认）──
    probe_result = probe(pyver)

    if probe_result["action"] == "SKIP_ALREADY_ACTIVATED":
        ok, err_code = verify_login(args.force_login)
        if ok:
            _print_kv("RESULT", "ALREADY_ACTIVATED")
            sys.exit(0)
        if err_code not in STALE_CREDENTIAL_ERRORS:
            _abort_non_stale(err_code)
        # 凭据失效类 → 删 stale userInfo 后重新探测分发 GUI/SMS
        _print_kv("STEP", "userInfo stale (ErrorCode={}); removing".format(err_code))
        _try_remove_userinfo(probe_result["userinfo_path"])
        probe_result = probe(pyver)
        if probe_result["action"] == "SKIP_ALREADY_ACTIVATED":
            # 删除失败 → userInfo 仍在，默认模式无法分发，避免死循环
            _print_kv("ERROR", "stale userInfo 删除失败，默认模式无法重新激活")
            _print_kv("HINT", "请手动删除 {} 后重跑，或用 --sms <phone> / --gui-launch".format(probe_result["userinfo_path"]))
            _print_kv("RESULT", "ACTIVATE_FAILED")
            sys.exit(1)

    if probe_result["action"] in ("ABORT", "ABORT_NO_SDK"):
        _print_kv("RESULT", "ACTIVATE_FAILED")
        sys.exit(1)

    if probe_result["action"] == "GUI":
        _print_kv("NEXT_STEP", "run --gui-launch then --gui-poll")
        _print_kv("HINT", "GUI 路径必须两步：先 `activate.py --gui-launch` 弹窗，Agent 向用户发指引，再 `activate.py --gui-poll` 轮询")
        _print_kv("RESULT", "NEED_GUI_TWO_STEP")
        sys.exit(0)

    if probe_result["action"] == "SMS":
        _print_kv("NEED_SMS", "Current environment has no GUI; SMS activation required.")
        _print_kv("NEXT_STEP", "run --sms <PHONE>")
        _print_kv("HINT", "用户需先发短信 SXDL 到 9535711，然后把 11 位手机号提供给 Agent")
        _print_kv("RESULT", "NEED_SMS")
        sys.exit(0)


if __name__ == "__main__":
    main()
