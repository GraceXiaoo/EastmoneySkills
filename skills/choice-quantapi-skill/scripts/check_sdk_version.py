"""Choice 量化 API SDK 版本检查。

获取 SDK 版本号，与阈值 THRESHOLD 比较，按 RESULT= 契约输出分流信号：
- 低于阈值 → RESULT=VERSION_TOO_LOW（退出码 1）
- 否则     → RESULT=VERSION_OK（退出码 0）
- 取不到版本号 / c.start() 异常 → RESULT=VERSION_UNKNOWN（退出码 2）

退出码可区分三种状态，Agent 亦可按 RESULT= 行分流（与 sdk-setup.md §0.2 输出契约一致）。

版本号来源：c.start() 登录时打印的 "The current version is EmQuantAPI(Vx.x.x.x)." 行
（EmQuantAPI 是单文件模块，无 __version__ 属性、无包元数据，运行时打印行是唯一可靠来源）。
"""

from __future__ import annotations

import io
import re
import sys

# Windows 下中文输出防乱码（与 sdk-setup.md §5.3 约定一致）；RESULT= 行为 ASCII 不受影响。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass  # stdout 不支持 reconfigure（非 TextIOWrapper）时忽略

from EmQuantAPI import c

# 阈值取所有"版本门控函数"要求版本的最大值。当前由 secucode（需 V2.7.2.2+）决定。
# 新增此类函数时，若其要求更高，须同步抬高此阈值，否则该函数的 AttributeError 会被判 VERSION_OK。
THRESHOLD = "2.7.2.2"


def parse_version(text: str):
    # 精确：EmQuantAPI(Vx.x.x.x) —— 文档记载的标准横幅格式。
    m = re.search(r"EmQuantAPI\(V([\d.]+)\)", text)
    if not m:
        # 宽松回退：容忍 "EmQuantAPI V2.7.2.0" / 小写 v / 无括号等变体。
        # 故意只容忍空白与 '('，不放宽到任意非数字间隔——否则会误抓
        # "EmQuantAPI (c) 2024 ..." 里的 2024 当版本，导致 VERSION_OK 跳过升级。
        m = re.search(r"EmQuantAPI[\s(]*V?([\d.]+)", text, re.IGNORECASE)
    return m.group(1) if m else None


def compare(a: str, b: str) -> int:
    """按点号分段从左到右逐段比较。返回 -1/0/1。"""
    # 过滤空段，容忍 "2.7.2.0." 这类尾随点，避免 int('') 崩溃。
    pa = [int(x) for x in a.split(".") if x]
    pb = [int(x) for x in b.split(".") if x]
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    for x, y in zip(pa, pb):
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def get_sdk_version() -> str | None:
    # 同时重定向 stdout 与 stderr：版本横幅可能走任一流，正则只认版本行，无关噪音不影响解析。
    buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = buf
    sys.stderr = buf
    r = None
    try:
        r = c.start()
    except Exception:
        # c.start() 本身异常（SDK 损坏 / 注册异常等）→ 无法判定版本，交由 main() 走 VERSION_UNKNOWN
        return None
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    version = parse_version(buf.getvalue())
    if r is not None and r.ErrorCode == 0:
        c.stop()
    return version


def main() -> None:
    version = get_sdk_version()
    if version is None:
        print("RESULT=VERSION_UNKNOWN")
        print("未获取到版本号，无法判定是否需要升级；若因 AttributeError 触发本检查，请排查 SDK 安装是否异常或回退报用户对齐")
        sys.exit(2)
    if compare(version, THRESHOLD) < 0:
        print("RESULT=VERSION_TOO_LOW")
        print(f"当前版本过低，请运行 `python scripts/install.py`（默认参数，禁止加 --force-reinstall，否则会清掉 userInfo 凭据需重新激活）覆盖升级，再跑 activate.py（见 sdk-setup.md §2），完成后重跑原查询。当前版本：{version}，要求版本：{THRESHOLD}")
        sys.exit(1)
    else:
        print("RESULT=VERSION_OK")
        print(f"版本符合预期：{version}。若因 AttributeError 触发本检查，函数不存在另有原因（如函数名拼写），请排查他因，不要升级")
        sys.exit(0)


if __name__ == "__main__":
    main()
