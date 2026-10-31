#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Choice 量化 API SDK 安装脚本（install.py）

功能：Python 解释器探测 → SDK 下载与解压 → 环境注册
已存在时备份 userInfo 后覆盖安装（不再跳过），注册始终重新完成。
--force-reinstall 会清掉整个目录且不备份 userInfo，需重新激活。

用法：
    python scripts/install.py                  # 正常安装（已存在时覆盖安装，保留 userInfo）
    python scripts/install.py --force-reinstall  # 强制重装（会清掉 <SDK基目录>/EMQuantAPI_Python/
                                                 # 整个目录，不备份 userInfo，需重新激活。
                                                 # 基目录：妙想 Work 用 /workspace/user_space/.choice，
                                                 # 妙想Claw 用 ~/.openclaw/.choice，其他环境用 ~/.choice

输出契约：所有信号均为 KEY=VALUE 行。
决策行：RESULT=INSTALL_SUCCESS / INSTALL_FAILED（决策只看这行）。
数据行：OVERWRITE=yes（覆盖安装时出现，Agent 应告知用户）。
失败时回头看 ERROR= / DETAIL=（DETAIL 含 userInfo 备份保留信息）。
其余字段（PYVER/VERSION/PY/SDK_BASE/SDK_DIR/STEP/HINT/NOTE）为诊断信息可忽略。
"""

from __future__ import print_function
import sys
import os
import subprocess
import argparse
import shutil

# ─── 常量 ────────────────────────────────────────────────────────────────────
SDK_ZIP_URL = "https://cftdlcdn.eastmoney.com/Choice/EMQuantAPI/EMQuantAPI_Python.zip"
SDK_DIRNAME = "EMQuantAPI_Python"  # zip 解压后的顶层目录名
INSTALL_SCRIPT = "installEmQuantAPI.py"  # SDK 内的注册脚本
CHOICE_BASEDIR = ".choice"  # SDK 安装目录名
MIAOXIANG_WORK_ROOT = "/workspace/user_space"

# userInfo 同目录下需同步备份/恢复的伴随文件:有则备份,无则跳过。
# 覆盖安装的 rmtree 会删整个 SDK 目录,这些伴随文件与 userInfo 同目录,需一并保住。
USERINFO_SIBLING_FILES = ("defineCode",)


# ─── 辅助 ────────────────────────────────────────────────────────────────────
def _print_kv(key, value):
    """输出 KEY=VALUE 行"""
    print("{}={}".format(key, value))
    sys.stdout.flush()


def _oneline(s):
    """把多行文本压成单行(用 ` | ` 串行),避免塞进 KEY=VALUE 时换行破契约。

    SDK installer / 子进程输出经常多行(pip 日志、site-packages 路径等),
    直接灌进 _print_kv 会让 Agent 的逐行 KEY= 解析把后续行当成游离日志或误识 KV。
    """
    if not s:
        return ""
    return " | ".join(line.strip() for line in s.splitlines() if line.strip())


def _is_miaoxiang_claw():
    """检测是否运行在妙想Claw(项目内部 Web IDE / 云端开发容器)中。

    满足任一组合即认定(共同前提:~/.openclaw/extensions/mx-claw 标记目录存在):
    1. INGRESS_URL + KUBERNETES_PORT 环境变量同时存在(K8s 部署模式)
    2. WUYING_INSTANCE_ID 环境变量存在

    与 activate.py 中同名函数保持一致;两脚本是独立可移植单元,故各自维护一份。
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


def _get_sdk_base():
    """获取 SDK 安装基目录。

    妙想 Work 环境下优先使用 /workspace/user_space/.choice，保证跨容器持久化；
    妙想Claw 环境下用 $HOME/.openclaw/.choice；其他环境仍用 $HOME/.choice。
    路径决策的唯一入口,下游所有路径(SDK 工作目录/userInfo/备份)均派生自此处。
    """
    home = os.path.expanduser("~")
    if _is_miaoxiang_work():
        base = os.path.join(MIAOXIANG_WORK_ROOT, CHOICE_BASEDIR)
    elif _is_miaoxiang_claw():
        base = os.path.join(home, ".openclaw", CHOICE_BASEDIR)
    else:
        base = os.path.join(home, CHOICE_BASEDIR)
    try:
        os.makedirs(base)  # exist_ok 是 Py3.2+ 才有,Py2 用 try/except 兜底
    except OSError:
        if not os.path.isdir(base):
            raise
    return base


def _run_cmd(cmd, cwd=None, timeout=120):
    """运行外部命令,返回 (returncode, stdout, stderr) —— 跨 Py2/Py3 兼容。

    - stdout/stderr 始终为 str(utf-8 解码,errors='replace')。
    - Py2 下 Popen.communicate() 不支持 timeout 参数,会被忽略(timeout 是 Py3.3+);
      Py2 上如果子进程卡死只能 Ctrl+C 兜底。
    - 异常区分:`subprocess.TimeoutExpired` → err="timeout";其他 → err=str(e)。
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # Py2/3 兼容(替代 {**os.environ, ...})
    try:
        p = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
    except Exception as e:
        return -1, "", str(e)

    kwargs = {"timeout": timeout} if timeout is not None and sys.version_info >= (3, 3) else {}
    try:
        out, err = p.communicate(**kwargs)
    except Exception as e:
        try:
            p.kill()
            p.communicate()
        except Exception:
            pass
        is_timeout = hasattr(subprocess, "TimeoutExpired") and isinstance(e, subprocess.TimeoutExpired)
        return -1, "", "timeout" if is_timeout else str(e)

    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    if isinstance(err, bytes):
        err = err.decode("utf-8", errors="replace")
    return p.returncode, out or "", err or ""


def _download_sdk(sdk_base, zip_path):
    """下载 SDK zip。Py2 用 urllib.urlretrieve,Py3 用 urllib.request.urlretrieve,均自动跟随重定向。"""
    try:
        from urllib.request import urlretrieve  # Py3
    except ImportError:
        from urllib import urlretrieve  # Py2

    _print_kv("STEP", "Downloading SDK zip...")
    try:
        urlretrieve(SDK_ZIP_URL, zip_path)
        _print_kv("STEP", "Download complete: {}".format(zip_path))
        return True
    except Exception as e:
        _print_kv("STEP", "Download failed: {}".format(e))

    # Fallback: curl(若可用)—— _run_cmd 自己吞所有异常,curl 不存在时 rc=-1 + err=系统报错
    rc, _, err = _run_cmd(
        ["curl", "-fL", "--retry", "3", "-o", zip_path, SDK_ZIP_URL],
        cwd=sdk_base, timeout=300
    )
    if rc == 0:
        _print_kv("STEP", "Download via curl complete")
        return True
    _print_kv("STEP", "Download via curl failed: {}".format(err.strip() or "curl unavailable"))
    return False


def _unzip_sdk(sdk_base, zip_path):
    """解压 SDK zip"""
    import zipfile

    _print_kv("STEP", "Unzipping SDK...")
    try:
        # 优先用 Python zipfile（跨平台）
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(sdk_base)
        _print_kv("STEP", "Unzip complete (Python zipfile)")
        return True
    except Exception as e:
        _print_kv("STEP", "Python zipfile failed: {}".format(e))
        # Fallback: unzip 命令
        rc, out, err = _run_cmd(
            ["unzip", "-oq", zip_path, "-d", sdk_base],
            cwd=sdk_base, timeout=120
        )
        if rc == 0:
            _print_kv("STEP", "Unzip via unzip command complete")
            return True
        else:
            _print_kv("STEP", "unzip command also failed: {}".format(err))
            return False


# ─── userInfo 备份 / 恢复 ────────────────────────────────────────────────────
def _find_userinfo(sdk_work_dir):
    """在 SDK 工作目录的 libs/ 下搜索 userInfo 文件。

    返回 (绝对路径, 相对路径) 或 None。
    相对路径用于覆盖安装后恢复到同一位置。
    """
    libs_dir = os.path.join(sdk_work_dir, "libs")
    if not os.path.isdir(libs_dir):
        return None
    for root, dirs, files in os.walk(libs_dir):
        if "userInfo" in files:
            abs_path = os.path.join(root, "userInfo")
            rel_path = os.path.relpath(abs_path, sdk_work_dir)
            return abs_path, rel_path
    return None


def _find_active_sdk_userinfo(py_info):
    """默认 SDK 目录下没有 userInfo 时,通过 site-packages/EmQuantAPI.pth 反查
    当前生效的 SDK 位置,再在其 libs/ 下找 userInfo。

    参考 installEmQuantAPI.py / EmQuantAPI.py 的 .pth 定位逻辑:
    扫 sys.path 中以 site-packages / dist-packages 结尾的目录,读其中的
    EmQuantAPI.pth 首行(= SDK 根目录),进 libs/ 搜 userInfo。

    用子进程跑(对 py_info['py']),保证读到的是目标解释器真正生效的 .pth,
    而非 install.py 自身进程可能不一致的 sys.path。

    返回 (userInfo_abs_path, rel_path相对该SDK根) 或 None。
    rel_path 相对 SDK 根,与默认 SDK 同构(libs/<os>/userInfo),故可直接用于
    恢复到新解压的 sdk_work_dir。
    """
    # Py2/3 兼容的探测片段:逐行打印所有 .pth 指向的去重 SDK 根目录
    snippet = (
        "import sys, os\n"
        "seen = set()\n"
        "for sp in sys.path:\n"
        "    if not sp:\n"
        "        continue\n"
        "    if not (sp.endswith('site-packages') or sp.endswith('dist-packages')):\n"
        "        continue\n"
        "    pth = os.path.join(sp, 'EmQuantAPI.pth')\n"
        "    if not os.path.exists(pth):\n"
        "        continue\n"
        "    try:\n"
        "        with open(pth) as f:\n"
        "            line = f.readline().strip()\n"
        "    except Exception:\n"
        "        continue\n"
        "    if line and line not in seen:\n"
        "        seen.add(line)\n"
        "        print(line)\n"
    )
    rc, out, _ = _run_cmd([py_info["py"], "-c", snippet], timeout=15)
    if rc != 0:
        return None

    for line in out.splitlines():
        base_dir = line.strip()
        if not base_dir:
            continue
        # base_dir 即 .pth 指向的生效 SDK 根,结构与默认 SDK 一致,直接复用 _find_userinfo
        result = _find_userinfo(base_dir)
        if result is not None:
            _print_kv("STEP", "userInfo located via active EmQuantAPI.pth -> {}".format(base_dir))
            return result
    return None


def _backup_userinfo(sdk_work_dir, py_info):
    """备份 userInfo 到 <SDK基目录>/userInfo（基目录由 _get_sdk_base 判定）。

    查找顺序:
    1. 默认 SDK 工作目录(sdk_work_dir/libs/...)—— 常规覆盖安装场景
    2. 若默认目录没有,通过 site-packages/EmQuantAPI.pth 反查当前生效的 SDK 位置,
       在其 libs/ 下找 userInfo —— 处理 SDK 被装到非默认路径的情况

    返回 userInfo 相对 SDK 根的相对路径(用于后续恢复到新解压目录),或 None。
    """
    result = _find_userinfo(sdk_work_dir)
    source = "default SDK dir"
    if result is None:
        result = _find_active_sdk_userinfo(py_info)
        source = "active EmQuantAPI.pth"
    if result is None:
        _print_kv("STEP", "No userInfo found (default nor active .pth), skipping backup")
        return None

    abs_path, rel_path = result
    sdk_base = _get_sdk_base()
    backup_path = os.path.join(sdk_base, "userInfo")
    sibling_dir = os.path.dirname(abs_path)
    try:
        shutil.copy2(abs_path, backup_path)
        # 同目录伴随文件(defineCode 等)有则同步备份;任一失败 → 整体回退(清掉半备份,
        # 返回 None 让上层走"备份失败保留旧目录不 rmtree",避免丢了伴随文件)
        backed = []
        for sib in USERINFO_SIBLING_FILES:
            sib_src = os.path.join(sibling_dir, sib)
            if os.path.isfile(sib_src):
                shutil.copy2(sib_src, os.path.join(sdk_base, sib))
                backed.append(sib)
        # 持久化恢复路径到 sidecar,供重试场景(本次未备份但存在遗留备份)定位恢复目标
        try:
            with open(backup_path + ".restorepath", "w") as f:
                f.write(rel_path)
        except (OSError, IOError):
            pass  # 非关键:写失败时重试只能依赖本次 userinfo_rel_path
        _print_kv("STEP", "userInfo backed up (from {}): {} -> {}{}".format(
            source, abs_path, backup_path, " + " + ",".join(backed) if backed else ""))
        return rel_path
    except (OSError, IOError) as e:
        _print_kv("WARNING", "userInfo/sibling backup failed: {}".format(e))
        _cleanup_userinfo_backup()  # 清掉本次写了一半的文件,避免半备份/孤儿
        return None


def _restore_userinfo(sdk_work_dir, userinfo_rel_path):
    """从 <SDK基目录>/userInfo 备份恢复 userInfo 到 SDK 工作目录的指定位置,
    并同步恢复同目录伴随文件(defineCode 等,有备份才恢复)。

    返回 True(userInfo 及所有存在的伴随备份均恢复成功)/ False(恢复失败或无备份)。
    伴随文件恢复失败也返 False,让上层(_restore_userinfo_from_backup)不清理备份、
    保留供重试(清理以全部成功为前提)。
    """
    backup_path = os.path.join(_get_sdk_base(), "userInfo")
    if not os.path.isfile(backup_path):
        _print_kv("STEP", "No userInfo backup to restore")
        return False

    if userinfo_rel_path is None:
        _print_kv("WARNING", "userInfo backup exists but original location unknown, skipping restore")
        return False

    dest = os.path.join(sdk_work_dir, userinfo_rel_path)
    dest_dir = os.path.dirname(dest)
    try:
        os.makedirs(dest_dir)  # Py2 没有 exist_ok,try/except 兜底
    except OSError:
        if not os.path.isdir(dest_dir):
            _print_kv("WARNING", "Cannot create userInfo directory: {}".format(dest_dir))
            return False

    try:
        shutil.copy2(backup_path, dest)
    except (OSError, IOError) as e:
        _print_kv("WARNING", "userInfo restoration failed: {}".format(e))
        return False
    _print_kv("STEP", "userInfo restored: {} -> {}".format(backup_path, dest))

    # 同步恢复伴随文件:有备份才恢复,落到 userInfo 同目录;任一失败 → 返 False 保留备份
    for sib in USERINFO_SIBLING_FILES:
        sib_backup = os.path.join(_get_sdk_base(), sib)
        if not os.path.isfile(sib_backup):
            continue
        sib_dest = os.path.join(dest_dir, sib)
        try:
            shutil.copy2(sib_backup, sib_dest)
            _print_kv("STEP", "{} restored: {} -> {}".format(sib, sib_backup, sib_dest))
        except (OSError, IOError) as e:
            _print_kv("WARNING", "{} restoration failed: {}".format(sib, e))
            return False
    return True


def _cleanup_userinfo_backup():
    """清理 <SDK基目录>/userInfo 备份、sidecar(.restorepath)及伴随文件(defineCode 等)。"""
    sdk_base = _get_sdk_base()
    targets = [os.path.join(sdk_base, "userInfo"),
               os.path.join(sdk_base, "userInfo") + ".restorepath"]
    targets += [os.path.join(sdk_base, sib) for sib in USERINFO_SIBLING_FILES]
    removed = False
    for p in targets:
        try:
            os.remove(p)
            removed = True
        except OSError:
            pass  # 文件可能不存在，非关键
    if removed:
        _print_kv("STEP", "userInfo backup cleaned up")


def _mark_mxclaw_device(sdk_work_dir):
    """妙想Claw 环境下,在 libs/ 中每个含 ServerList.json.e 的目录放置 mxClawDevice 标记
    """
    libs_dir = os.path.join(sdk_work_dir, "libs")
    if not os.path.isdir(libs_dir):
        _print_kv("STEP", "mxClawDevice: libs dir not found, skip")
        return

    marked = 0
    for root, dirs, files in os.walk(libs_dir):
        if "ServerList.json.e" not in files:
            continue
        marker = os.path.join(root, "mxClawDevice")
        try:
            with open(marker, "w") as f:
                f.write("1")
            marked += 1
        except (OSError, IOError) as e:
            _print_kv("WARNING", "mxClawDevice write failed at {}: {}".format(root, e))
    _print_kv("STEP", "mxClawDevice marked {} dir(s) under {}".format(marked, libs_dir))


def _restore_userinfo_from_backup(sdk_work_dir, userinfo_rel_path):
    """有备份则恢复 userInfo 到新 SDK 目录。

    恢复目标优先用本次备份记录的 userinfo_rel_path;若为 None(重试场景:本次未
    备份但存在上次失败遗留的备份),则读 sidecar(.restorepath) 拿到上次的恢复路径。
    恢复成功 → 清理备份+sidecar,返回 True;失败或无法定位目标 → 保留备份,返回 False。

    与 main 各失败路径配合:只要备份存在就尝试恢复,清理以恢复成功为前提,
    避免"重试时遗留备份被删却未恢复"。
    """
    backup_path = os.path.join(_get_sdk_base(), "userInfo")
    if not os.path.isfile(backup_path):
        return False

    rel = userinfo_rel_path
    if rel is None:
        sidecar = backup_path + ".restorepath"
        try:
            with open(sidecar) as f:
                rel = f.read().strip() or None
        except (OSError, IOError):
            rel = None
        if rel is None:
            _print_kv("DETAIL", "userInfo backup exists at {} but restore target unknown; preserving backup".format(backup_path))
            return False

    if _restore_userinfo(sdk_work_dir, rel):
        _cleanup_userinfo_backup()
        return True
    _print_kv("DETAIL", "userInfo backup preserved at {} - restore failed; retry install.py to auto-restore".format(backup_path))
    return False


# ─── 第一步：Python 探测 ──────────────────────────────────────────────────
def probe_python():
    """
    探测当前 Python 解释器版本。
    直接用 sys.version_info（脚本已在 Python 下运行，无需再试 launcher）。

    返回 dict:
        py:       sys.executable 绝对路径
        pyver:    "python3" / "python2"
        version:  "3.12" / "2.7"
        major:    3 / 2
    """
    vi = sys.version_info
    major = vi[0]
    minor = vi[1]
    version_str = "{}.{}".format(major, minor)
    pyver = "python3" if major >= 3 else "python2"

    result = {
        "py": sys.executable,
        "pyver": pyver,
        "version": version_str,
        "major": major,
    }

    if major < 3:
        _print_kv("NOTE", "downgraded_to_python2")
        print("⚠ Python 2 已停止官方维护，后续示例代码可能需要手工降级。")

    _print_kv("PYVER", pyver)
    _print_kv("VERSION", version_str)
    _print_kv("PY", sys.executable)

    return result


# ─── 第二步：SDK 下载与解压 ────────────────────────────────────────────────
def download_and_extract(py_info, force=False):
    """
    下载并解压 SDK。已存在时备份 userInfo 后覆盖安装（不再跳过）。
    --force-reinstall 时清掉整个目录（不备份 userInfo）后重新下载。

    返回 (sdk_work_dir, userinfo_rel_path) 或 (None, userinfo_rel_path) 表示失败。
    userinfo_rel_path 为 None 表示首次安装或 userInfo 未找到；
    非 None 表示覆盖安装且 userInfo 已备份（即使下载/解压失败，备份仍保留供重试恢复）。
    """
    pyver = py_info["pyver"]
    sdk_base = _get_sdk_base()
    sdk_root = os.path.join(sdk_base, SDK_DIRNAME)
    install_marker = os.path.join(sdk_root, pyver, INSTALL_SCRIPT)
    sdk_work_dir = os.path.join(sdk_root, pyver)

    userinfo_rel_path = None

    # 非强制重装时备份 userInfo:默认目录优先,没有则回退到 .pth 指向的生效 SDK。
    # 即使默认目录无旧 SDK(如环境迁移),也可能存在装在他处的活跃 SDK 需保住。
    if not force:
        default_present = os.path.isfile(install_marker)
        if default_present:
            # 修复短路:SDK 本体在但当前 import 失败(妙想Claw 闲置清理删了 site-packages 的
            # .pth,本体与 userInfo 在持久卷未丢)→ 先 try_register_and_check_version 重注册 .pth
            # 并验版本:版本够 → 跳过重下(交 main 幂等再 register 一次);版本低或任何失败 →
            # 回退完整重下(低版本即在本次 install.py 内自动升级)。与升级路径(本体能 import)
            # 互不冲突:升级时 import 正常,走下方覆盖重下。
            if not _verify_import(py_info):
                _print_kv("STEP", "SDK body present but import fails; try register + version check")
                if try_register_and_check_version(py_info, sdk_work_dir):
                    return sdk_work_dir, None
                _print_kv("STEP", "register/version check failed or version too low; fall through to re-download")
            _print_kv("STEP", "SDK already present at default dir, backing up userInfo and overwriting")
        else:
            _print_kv("STEP", "Default SDK dir empty; probing active EmQuantAPI.pth for userInfo to back up")
        userinfo_rel_path = _backup_userinfo(sdk_work_dir, py_info)
        # 备份失败但 userInfo 仍存在于默认目录 → 不删默认目录(保留 userInfo),改为覆盖解压
        userinfo_still_exists = _find_userinfo(sdk_work_dir) is not None
        if userinfo_rel_path is None and userinfo_still_exists:
            _print_kv("WARNING", "userInfo backup failed; keeping existing SDK directory to preserve userInfo")
        else:
            if default_present and os.path.isdir(sdk_root):
                _print_kv("STEP", "Removing existing SDK directory for overwrite install...")
                shutil.rmtree(sdk_root, ignore_errors=True)

    # 强制重装时清理旧目录（不备份 userInfo——从头开始）
    if force and os.path.isdir(sdk_root):
        _print_kv("STEP", "Removing existing SDK directory for reinstall...")
        shutil.rmtree(sdk_root, ignore_errors=True)

    zip_path = os.path.join(sdk_base, SDK_DIRNAME + ".zip")

    # 下载
    if not _download_sdk(sdk_base, zip_path):
        return None, userinfo_rel_path

    # 解压
    if not _unzip_sdk(sdk_base, zip_path):
        return None, userinfo_rel_path

    # 验证关键文件
    if not os.path.isfile(install_marker):
        _print_kv("STEP", "Verification failed: {} not found after unzip".format(install_marker))
        return None, userinfo_rel_path

    _print_kv("STEP", "SDK verified: {} present".format(install_marker))

    # 妙想Claw 专属:在 libs/ 下每个含 ServerList.json.e 的目录落 mxClawDevice 标记
    if _is_miaoxiang_claw():
        _mark_mxclaw_device(sdk_work_dir)

    # 清理 zip 文件
    try:
        os.remove(zip_path)
    except OSError:
        pass  # 非关键

    return sdk_work_dir, userinfo_rel_path


def _write_user_pth(sdk_work_dir, py_info):
    """Fallback: 手动往用户级 site-packages 写 EmQuantAPI.pth,绕开系统级目录权限不足。

    .pth 文件内容是 SDK 工作目录的绝对路径,Python 启动时会扫描所有 .pth 并将
    每行路径加入 sys.path,效果等同于 installEmQuantAPI.py 往系统级 site-packages
    写的那份,只是位置在用户空间,无需 root。

    返回 True(写成功 + import 验证通过) / False(仍然失败)。
    """
    _print_kv("STEP", "Fallback: writing user-level .pth file...")

    # 拿用户级 site-packages 路径(site.getusersitepackages())
    # 用子进程取,避免 import site 影响父进程状态;也兼容 Py2
    _, out, _ = _run_cmd(
        [py_info["py"], "-c",
         "try:\n"
         "    import site\n"
         "    print(site.getusersitepackages())\n"
         "except AttributeError:\n"
         "    # Py2 旧版本可能没有这个方法,用 site.USER_SITE\n"
         "    print(site.USER_SITE if hasattr(site, 'USER_SITE') else '')\n"],
        timeout=10,
    )
    user_site = out.strip()
    if not user_site:
        _print_kv("ERROR", "Cannot determine user site-packages path")
        return False

    _print_kv("STEP", "User site-packages: {}".format(user_site))

    # 创建目录(可能不存在)
    try:
        os.makedirs(user_site)  # Py2 没有 exist_ok,try/except 兜底
    except OSError:
        if not os.path.isdir(user_site):
            _print_kv("ERROR", "Cannot create user site-packages dir: {}".format(user_site))
            return False

    # 写 .pth 文件
    pth_path = os.path.join(user_site, "EmQuantAPI.pth")
    pth_content = sdk_work_dir  # .pth 每行就是一个路径
    try:
        with open(pth_path, "w") as f:
            f.write(pth_content + "\n")
    except (OSError, IOError) as e:
        _print_kv("ERROR", "Cannot write .pth file {}: {}".format(pth_path, e))
        return False

    _print_kv("STEP", "Written {} -> {}".format(pth_path, pth_content))

    # 验证: 从非 SDK 目录 import EmQuantAPI(用 home 目录作为 cwd 防假阳性)
    verify_cmd = [
        py_info["py"], "-c",
        "from EmQuantAPI import c; print('REGISTERED')"
    ]
    rc, out, err = _run_cmd(verify_cmd, cwd=os.path.expanduser("~"), timeout=30)

    if rc == 0 and "REGISTERED" in out:
        _print_kv("STEP", "Registration verified via user-level .pth")
        return True
    else:
        _print_kv("ERROR", "User-level .pth verification failed: rc={}, out={}, err={}".format(
            rc, _oneline(out), _oneline(err)))
        _print_kv("HINT", "可能需要确认 EmQuantAPI.pth 指向的路径是否正确")
        return False


def _verify_import(py_info):
    """验证当前解释器能否 import EmQuantAPI —— 从 home 目录跑子进程,避开 cwd 下
    可能存在的同名 EmQuantAPI.py 抢 import(与 activate.py verify_login 同款防假阳性)。

    返回 True(子进程输出含 'REGISTERED') / False。供 register_sdk 注册后验证、以及
    download_and_extract 的修复短路(本体在但 import 失败 → 跳过重下只重注册)复用。
    """
    verify_cmd = [
        py_info["py"], "-c",
        "from EmQuantAPI import c; print('REGISTERED')"
    ]
    rc, out, _ = _run_cmd(verify_cmd, cwd=os.path.expanduser("~"), timeout=30)
    return rc == 0 and "REGISTERED" in out


# ─── 第三步：环境注册 ──────────────────────────────────────────────────────
def register_sdk(py_info, sdk_work_dir):
    """
    注册 SDK 到当前 Python 环境,优先系统级,权限不足时 fallback 到用户级 .pth。

    流程:
    1. 跑 installEmQuantAPI.py(官方注册脚本,写系统级 site-packages)—— 有权限则一步到位
    2. 如果失败且是权限问题(PermissionError / rc!=0),自动 fallback 到用户级 .pth

    返回 True/False。
    """
    _print_kv("STEP", "Registering SDK...")

    install_script_path = os.path.join(sdk_work_dir, INSTALL_SCRIPT)

    # ① 尝试系统级注册(官方 installEmQuantAPI.py)
    rc, out, err = _run_cmd(
        [py_info["py"], install_script_path],
        cwd=sdk_work_dir,
        timeout=60
    )

    if rc == 0:
        _print_kv("STEP", "installEmQuantAPI.py succeeded: {}".format(_oneline(out)))
        # 验证: 从非 SDK 目录 import(用 home 目录作为 cwd,避免假阳性)
        if _verify_import(py_info):
            _print_kv("STEP", "Registration verified (system-level)")
            return True
        # 系统级注册成功但 import 验证失败(罕见:不同 Python 版本等)
        _print_kv("STEP", "System-level .pth written but import verification failed, trying user-level fallback")

    else:
        # 系统级注册失败 —— 检查是否是权限问题
        is_perm_error = (
            "PermissionError" in err
            or "Permission denied" in err
            or "Errno 13" in err
        )
        _print_kv("STEP", "installEmQuantAPI.py failed (permission={})".format(
            "yes" if is_perm_error else "no"))
        if not is_perm_error:
            # 非权限问题(如 Python 版本不兼容等),不走 fallback,直接报错
            _print_kv("ERROR", "installEmQuantAPI.py failed: rc={}, stdout={}, stderr={}".format(
                rc, _oneline(out), _oneline(err)))
            _print_kv("HINT", "可能原因: Python 版本不兼容或 SDK 内部错误")
            return False

    # ② Fallback: 用户级 .pth
    _print_kv("NOTE", "System-level registration unavailable, using user-level .pth fallback")
    return _write_user_pth(sdk_work_dir, py_info)


def try_register_and_check_version(py_info, sdk_work_dir):
    """修复快路径:重注册 .pth 后用 check_sdk_version.py 验版本。

    register_sdk 重写 .pth(使 import 恢复),再子进程跑同目录的 check_sdk_version.py
    (其内部 c.start() 登录拿版本横幅;THRESHOLD 仍以该脚本为唯一来源,本处不复制)。
    成功(register 通过 + 版本≥阈值)→ True,调用方跳过重下,交 main 幂等再 register
    一次即可;任何失败(register 失败 / 版本过低 / 版本未知 / 登录或子进程异常)→
    False,调用方回退完整重下(升级),低版本即在本次 install.py 内自动升级。

    仅在修复分支(import 已断、本体在)调用;此刻 userInfo 在持久卷未丢,登录可成功。
    """
    if not register_sdk(py_info, sdk_work_dir):
        _print_kv("STEP", "repair: register_sdk failed; fall through to re-download")
        return False
    check_script = os.path.join(os.path.dirname(os.path.realpath(__file__)), "check_sdk_version.py")
    rc, out, _ = _run_cmd([py_info["py"], check_script],
                          cwd=os.path.expanduser("~"), timeout=60)
    _print_kv("STEP", "version check rc={} out={}".format(rc, _oneline(out)))
    # check_sdk_version.py 退出码: 0=VERSION_OK / 1=VERSION_TOO_LOW / 2=VERSION_UNKNOWN
    return rc == 0 and "VERSION_OK" in out


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Choice 量化 API SDK 安装脚本")
    parser.add_argument("--force-reinstall", action="store_true",
                        help="强制重新下载并安装（即使 SDK 已存在）")
    args = parser.parse_args()

    sdk_base = _get_sdk_base()
    _print_kv("SDK_BASE", sdk_base)
    if _is_miaoxiang_work():
        _print_kv("MXWORK_ENV", "yes")
    elif _is_miaoxiang_claw():
        _print_kv("MXCLAW_ENV", "yes")

    # Step 1: Python 探测
    _print_kv("STEP", "=== Step 1: Python probe ===")
    py_info = probe_python()

    # Step 2: SDK 下载与解压
    _print_kv("STEP", "=== Step 2: SDK download & extract ===")
    sdk_work_dir, userinfo_rel_path = download_and_extract(py_info, force=args.force_reinstall)
    backup_path = os.path.join(_get_sdk_base(), "userInfo")
    if sdk_work_dir is None:
        # 下载/解压失败:非强制且存在备份(本次或上次遗留)→保留供重试自动恢复;否则清理
        if not args.force_reinstall and os.path.isfile(backup_path):
            _print_kv("DETAIL", "userInfo backup preserved at {} - retry install.py to auto-restore".format(backup_path))
        else:
            _cleanup_userinfo_backup()
        _print_kv("RESULT", "INSTALL_FAILED")
        _print_kv("ERROR", "SDK download or extraction failed")
        sys.exit(1)

    _print_kv("SDK_DIR", sdk_work_dir)

    # Step 3: 环境注册
    _print_kv("STEP", "=== Step 3: Environment registration ===")
    if not register_sdk(py_info, sdk_work_dir):
        # 注册失败:非强制则尝试恢复 userInfo 保留激活态(成功清理,失败保留供重试);
        # 强制重装=干净起点,丢弃任何遗留备份,不恢复 userInfo
        if args.force_reinstall:
            _cleanup_userinfo_backup()
        else:
            _restore_userinfo_from_backup(sdk_work_dir, userinfo_rel_path)
        _print_kv("RESULT", "INSTALL_FAILED")
        _print_kv("ERROR", "SDK registration failed")
        sys.exit(1)

    # Step 4: userInfo 恢复
    if args.force_reinstall:
        # 强制重装=干净起点:丢弃任何遗留备份(sdk_base/userInfo 在 sdk_root 之外,rmtree 不会动它),需重新激活
        _cleanup_userinfo_backup()
    elif os.path.isfile(backup_path):
        # 有备份就恢复:本次备份或上次失败遗留(经 sidecar 定位目标)
        _print_kv("STEP", "=== Step 4: userInfo restoration ===")
        if _restore_userinfo_from_backup(sdk_work_dir, userinfo_rel_path):
            _print_kv("OVERWRITE", "yes")

    # 成功
    _print_kv("RESULT", "INSTALL_SUCCESS")
    sys.exit(0)


if __name__ == "__main__":
    main()
