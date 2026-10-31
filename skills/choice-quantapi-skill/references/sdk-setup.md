# SDK 准备：安装与激活（Agent 执行剧本）

> 本文档是 Agent 完成 Choice 量化 API SDK 准备工作的完整剧本。所有步骤已固化为 Python 脚本，Agent 直接运行脚本、读输出、做分流，无需拼 bash 命令。

---

## 0. 总览

### 0.1 两步流程

| 步骤 | 命令 | 说明 |
| --- | --- | --- |
| ① 安装 | `python scripts/install.py` | Python 探测 + SDK 下载解压 + 环境注册；**已存在时备份 userInfo（及同目录 defineCode，若有）后覆盖安装，不再跳过** |
| ② 激活 | `python scripts/activate.py` | 探测环境 → 输出 `RESULT=NEED_GUI_TWO_STEP` / `NEED_SMS` / `ALREADY_ACTIVATED`，Agent 据此分流 |

### 0.2 输出契约（重要）

两个脚本的所有信号都是 **`KEY=VALUE` 行**，Agent 按 KEY 前缀抓即可。

- **决策行**（必读，每条命令最后一行）：`RESULT=`
  - install.py：`INSTALL_SUCCESS` / `INSTALL_FAILED`
  - activate.py：`ALREADY_ACTIVATED` / `NEED_GUI_TWO_STEP` / `NEED_SMS` / `GUI_LAUNCH_DONE` / `GUI_STOP_SIGNALLED` / `LOGIN_OK` / `LOGIN_FAILED` / `ACTIVATE_FAILED`
- **分流字段**（决策时用）：`ACTION=` / `NEXT_STEP=` / `ERROR=` / `DETAIL=`
- **数据字段**（特定分支需要时读）：`LOGIN_CHECK=` / `OVERWRITE=` / `attempt_N_output=` / `USERINFO=` / `ACTIVATED=` / `TIMEOUT=` / `GIVEUP_AFTER_RETRIES=` / `FG_RESULT=`
- **诊断字段**（一律忽略）：`STEP=` / `HINT=` / `NOTE=` / `WARNING=` / `SDK_BASE=` / `SDK_DIR=` / `PYVER=` / `VERSION=` / `PY=` / `PLATFORM=` / `HAS_GUI=` / `MXWORK_ENV=` / `MXCLAW_ENV=` / `MAC_GTK3=`

> ⚠ 一个特例：`RESULT=` 的 VALUE 里可能含空格 + 第二个等号（如 `RESULT=LOGIN_OK_NO_USERINFO PATH=/...`）。按"取等号后到行尾"解析即可。

### 0.3 Agent 决策树

```
install.py
  └─ RESULT=INSTALL_SUCCESS ──→ activate.py
  │   （若含 OVERWRITE=yes → 覆盖安装，告知用户凭据已保留）
       ├─ RESULT=ALREADY_ACTIVATED + RESULT=LOGIN_OK   → 完工，回原任务
       │    └─（若 LOGIN_FAILED 且 ErrorCode=10001020/10001019 → 自动删 stale userInfo
       │       后重新分发 NEED_GUI_TWO_STEP / NEED_SMS；非凭据失效类 → ACTIVATE_FAILED。见 §2.1）
       ├─ RESULT=NEED_GUI_TWO_STEP                     → §2.2（--gui-launch → 发指引 → --gui-poll）
       ├─ RESULT=NEED_SMS                              → §2.3（发指引拿手机号 → --sms <phone>）
       └─ RESULT=ACTIVATE_FAILED                       → 读 ERROR=/HINT=/DETAIL= 报用户
  └─ RESULT=INSTALL_FAILED ──→ 见 §1.2
```

---

## 1. 第一步：安装

```bash
python scripts/install.py
```

已存在时不再跳过——备份 userInfo（及同目录 defineCode，若有）到 `<SDK基目录>/`，删除旧 SDK 目录后重新下载解压；注册始终重新完成；完成后同步恢复 userInfo（及 defineCode）并输出 `OVERWRITE=yes`。若任一备份失败则保留旧目录不变、改为 zip 覆盖解压（userInfo/defineCode 不在 zip 中不会被覆盖）。

> 🔁 **版本升级**（由 [check_sdk_version.py](../scripts/check_sdk_version.py) 的 `RESULT=VERSION_TOO_LOW` 触发）：用上面的默认 `python scripts/install.py` 即可——已存在时自动备份 `userInfo` 后覆盖升级（下载固定 `SDK_ZIP_URL` 的最新 SDK）。**不要加 `--force-reinstall`**：那不是"升级"而是"清空重装"，会清掉 `userInfo`（详见下方 ⚠）。两种安装场景：
> - **安装 / 升级**：`python scripts/install.py`（默认；已存在时备份 `userInfo` 后覆盖）
> - **损坏排查**（解压 / 注册失败）：`python scripts/install.py --force-reinstall`（清空残留，**不备份 `userInfo`**，见 §1.2）

> ℹ **SDK 基目录由脚本自动判定**：存在 `/workspace/user_space/` 时认定为妙想 Work，优先使用持久目录 `/workspace/user_space/.choice/` 并输出 `MXWORK_ENV=yes`；否则，妙想Claw 使用 `~/.openclaw/.choice/` 并输出 `MXCLAW_ENV=yes`；其他环境使用 `~/.choice/`。下文 `<SDK基目录>` 均指此处判定的基目录。**不要手动指定路径或改路径常量**。

> ⚠ `--force-reinstall` 会**清掉整个** `<SDK基目录>/EMQuantAPI_Python/` **目录，包括 `userInfo` 及同目录 `defineCode`**，跑完必须重新激活。仅用于解压损坏 / 注册失败排查（见 §1.2）。

### 1.1 关键输出

| 输出 | 含义 | 下一步 |
| --- | --- | --- |
| `RESULT=INSTALL_SUCCESS` | 安装完成 | 进入 §2 |
| `RESULT=INSTALL_FAILED` | 安装失败 | 读 `ERROR=` 行，见 §1.2 |
| `OVERWRITE=yes` | 覆盖安装（SDK 已存在时备份 userInfo 及 defineCode 后重装） | Agent 应告知用户「SDK 已覆盖安装，原有激活凭据已保留」 |

> `defineCode` 是 userInfo 同目录下的伴随文件（妙想Claw下使用，不一定存在）；与 userInfo 同备份/同恢复：备份时任一存在的伴随文件拷失败 → 视为备份失败（保留旧目录不 rmtree）；恢复时任一失败 → 保留备份供重试（清理以全部成功为前提）。

其余字段（`PYVER=` / `VERSION=` / `PY=` / `SDK_BASE=` / `SDK_DIR=` / `NOTE=` / `STEP=` / `HINT=`）均为诊断信息可忽略。

**Agent 看到 `OVERWRITE=yes` 时应向用户发一条消息：**

> ✅ **Choice 量化 API SDK 已覆盖安装，原有激活凭据（userInfo）已自动保留并恢复。**

若后续 §2 activate.py 报 `LOGIN_FAILED`（凭据因 SDK 版本变化失效），按 §3 错误码表重新激活即可。

### 1.2 失败处理

- **下载失败**（`Download failed`）：脚本已自动 urllib → curl 双重试，仍失败即网络/代理问题，让用户检查网络或代理，**不要自行换镜像或备用 URL**。若输出含 `DETAIL=userInfo backup preserved` → userInfo（及 defineCode）备份保留在 `<SDK基目录>/`，重跑 `install.py` 会自动恢复；否则无备份，下次安装会重新备份。
- **解压失败**：先 `python scripts/install.py` 重跑一次（已有备份则自动恢复）；仍失败再 `python scripts/install.py --force-reinstall`（清掉残留并重新下载，**不备份 userInfo/defineCode**）；仍失败再让用户确认 zip 完整性或手动下载解压到 `<SDK基目录>`。若输出含 `DETAIL=userInfo backup preserved` → 备份保留在 `<SDK基目录>/`，重跑 `install.py` 会自动恢复。
- **注册失败**（`Registration verification failed`）：最常见原因是当前解释器与 `installEmQuantAPI.py` 写入的 site-packages 不一致。让用户确认目标 Python 环境，**不要再换一个 Python 试**。userInfo（及 defineCode）已恢复到原位置（保留激活状态），备份已清理。

---

## 2. 第二步：激活

```bash
python scripts/activate.py
```

脚本探测当前环境并告知下一步该跑什么——**不会自动阻塞做 GUI/SMS 激活**。Agent 根据最后一行 `RESULT=` 分流：

| 最终 RESULT= | 下一步 |
| --- | --- |
| `ALREADY_ACTIVATED` + `LOGIN_OK` | §2.1，已完工 |
| `NEED_GUI_TWO_STEP` | §2.2，跑两步 |
| `NEED_SMS` | §2.3，发指引拿手机号 |
| `ACTIVATE_FAILED` | 读 `ERROR=` / `HINT=` 报用户 |

### 2.1 已激活 → 直接可用

`RESULT=ALREADY_ACTIVATED` + `RESULT=LOGIN_OK` → userInfo 已存在且登录自检通过，**立即回到用户原任务**。

> ℹ **userInfo 存在但自检失败时**，脚本按 `ErrorCode` 分两类处理：
> - **凭据失效类**（`10001020` / `10001019`）：自动删 stale userInfo 并继续激活——默认模式重新分发 `NEED_GUI_TWO_STEP` / `NEED_SMS`，`--sms` / `--gui-*` 覆盖写新凭据。**「重跑 `activate.py`」即可修复，无需手动删 userInfo。**
> - **非凭据失效类**（网络 / 限频 / subprocess 异常等）：**不删** userInfo（避免误删仍有效的凭据），输出 `RESULT=ACTIVATE_FAILED` + `HINT=`，报用户排查后重跑。
>
> ⚠ `RESULT=LOGIN_FAILED` 在自愈路径里是**中间态**（最终决策行是后面的 `NEED_*` / `ACTIVATE_FAILED`）；**仅当它是输出最后一行**（激活写盘后最终自检失败）时，才看 `LOGIN_CHECK=` 的 `ErrorCode` 对照 §3 处理（§3 未列的去 [error-codes.md](help/error-codes.md) 查含义；激活相关错误码的处理仍以 §3 为准）。始终以最后一行 `RESULT=` 为准（§0.2）。

### 2.2 GUI 弹窗激活（两步走）

入口 `RESULT=NEED_GUI_TWO_STEP` → 当前是桌面环境，需要用户在弹出的窗口里手动输手机号 + 验证码。

```bash
python scripts/activate.py --gui-launch   # ① 弹窗即返回（最终 RESULT=GUI_LAUNCH_DONE / ALREADY_ACTIVATED / ACTIVATE_FAILED）
# ↑ 仅当 RESULT=GUI_LAUNCH_DONE 时才向用户发"操作指引"消息（见下方文案）；ACTIVATE_FAILED 则按 ERROR=/HINT= 处理，不发指引
python scripts/activate.py --gui-poll     # ② 轮询 userInfo，最长 300s
```

> **WorkBuddy on Windows 保活流程**：WorkBuddy 可能在命令结束时清理该命令创建的整棵进程树，导致 `LoginActivator.exe` 随即关闭。因此第一步改为在后台运行 `python scripts/activate.py --gui-launch --keepalive 1800`。该命令会先输出 `RESULT=GUI_LAUNCH_DONE`，再保活所属进程树；Agent 随后另行运行 `--gui-poll`。轮询得到最终登录结果后会自动通知保活命令退出；300 秒轮询超时不会停止保活，可再次运行 `--gui-poll`。若用户放弃，执行 `python scripts/activate.py --gui-stop` 收尾。普通环境仍使用上方原命令。

> 若 `--gui-launch` 输出 `RESULT=ALREADY_ACTIVATED` + `RESULT=LOGIN_OK` —— 已经激活过，**无需再跑 `--gui-poll`**，直接完工。

**Agent 发给用户的指引文案**（仅在 `RESULT=GUI_LAUNCH_DONE` 时发）：

> 🔔 **即将弹出 Choice 激活窗口，需要你手动操作，有2种可选方式：**
> ① 用户名密码激活：输入用户名密码并点击「激活」按钮。
> ② 手机号激活：输入绑定 Choice 账号的**手机号**，获取验证码并填入后，点击「激活」按钮。
>
> **窗口马上弹出**，激活完成后我会自动检测 `userInfo` 文件并继续后续查数，你不用回复这条消息。

如果输出含 `FG_RESULT=FG_NO_WINDOW`，追加一句：

> ✅ 激活窗口已弹出但未抢到前台焦点。请去任务栏（Windows）/ Dock（macOS）/ 任务栏（Linux）点一下 **LoginActivator** 图标。

**`--gui-poll` 最终结果**：

| 输出 | 含义 | 下一步 |
| --- | --- | --- |
| `ACTIVATED=after Ns` + `RESULT=LOGIN_OK` | 激活成功 + 登录自检通过 | **回到用户原任务** |
| `ACTIVATED=after Ns` + `RESULT=LOGIN_FAILED` | userInfo 已写盘但最终自检失败 | 看 `LOGIN_CHECK=` 的 `ErrorCode` 对照 §3 处理（见 §2.1 ⚠） |
| `TIMEOUT=300s` + `RESULT=ACTIVATE_FAILED` | 300 秒内 userInfo 未出现 | 先问用户「激活窗口是否还在桌面上？操作完成了吗？」<br>· 还开着 + 还没完成 → 再跑一次 `--gui-poll` 继续等<br>· 已关掉 / 操作中断 → 重跑 `--gui-launch` 再来一遍<br>· 用户放弃 → 停下让用户确认下一步 |

### 2.3 SMS 短信激活

入口 `RESULT=NEED_SMS` → 当前无桌面，需用户手动发短信，Agent 再用 `--sms <手机号>` 完成登录。

> **Agent 行为约束**：
> ① 一次性向用户发完整 3 步指引，**不要拆条**——拆开后用户容易把"发短信"当可选步骤。
> ② 手机号是自由文本，**不要用选项式询问**。

**Step 1：发给用户的指引（一条消息发完）**

> 📱 **当前是无图形界面环境，使用「上行短信验证」激活 Choice 量化 API（一次完成）：**
>
> 1. 确认手机号已**绑定 Choice 账号**（未绑定的，先到 Choice 客户端「我的-账号设置」里绑定）。
> 2. 用该手机号发送短信内容 `SXDL` 到 `9535711`（三网合一、10 分钟内有效、**无回执，不会收到任何确认短信**）。
> 3. 把发送时使用的 **11 位手机号**直接回复给我，我立刻用它完成登录，并继续后续查数。

**Step 2：提取手机号**

从用户回复里抽 11 位数字（去掉空格、`+86`、连字符）。如果不像合法手机号（不是 11 位 / 不以 1 开头），直接回 "这看起来不像 11 位手机号，能再确认一下吗？" 再等，**不要硬塞进脚本**。

**Step 3：运行激活脚本**

```bash
python scripts/activate.py --sms 13800138000   # ← 替换为实际手机号
```

脚本带 3 次重试容忍 SMS 投递延迟，间隔 20 秒。

**Step 4：关键输出**

| 输出 | 含义 | 下一步 |
| --- | --- | --- |
| `ACTIVATED=USERINFO=<path>` + `RESULT=LOGIN_OK` | 登录成功 + userInfo 写盘 + 自检通过 | **回到用户原任务** |
| `DETAIL=LOGIN_OK_NO_USERINFO PATH=<path>` + `RESULT=ACTIVATE_FAILED` | 登录返回 0 但凭据文件没出现 | 停下报错让用户检查路径权限 |
| `GIVEUP_AFTER_RETRIES=` + `RESULT=ACTIVATE_FAILED` | 3 次重试全失败 | 见下方失败分流 |

**Step 5：失败分流**

按最后一次 `attempt_N_output=ErrorCode=... ErrorMsg=...` 判断：

- `ErrorMsg` 提示「未收到短信」/「验证码失效」 → 让用户重发 `SXDL` 到 `9535711`，重新提供手机号，重跑 `--sms <手机号>`。
- `ErrorMsg` 提示「手机号未绑定」/「账号不存在」 → 让用户去 Choice 客户端绑定后重发短信、重跑脚本。
- `ErrorCode=10001009`（`EQERR_LOGIN_COUNT_LIMIT`） → **先问用户**「该账号已在其他设备登录，是否踢掉其它设备改在本机激活？」用户确认后再加 `--force-login`：`python scripts/activate.py --sms <手机号> --force-login`。**不要不问直接加。**
- 其它非 0 → 把 `ErrorCode + ErrorMsg` 原样报给用户，对照 [error-codes.md](help/error-codes.md) 查含义排查；**不要自行循环 SMS 流程**。

---

## 3. 常见激活错误码

| 错误码                                | 含义 | 处理 |
|------------------------------------| --- | --- |
| `10001020 EQERR_USERINFO_EXPIRED`  | userInfo 失效（通常是改了账号密码） | 重跑 `activate.py` |
| `10001019 EQERR_DIFFRENT_DEVICE`   | 激活设备与当前设备不一致 | 在当前设备重跑 `activate.py` |
| `10001009 EQERR_LOGIN_COUNT_LIMIT` | 账号已在其他设备登录 | **先问用户**是否踢掉其它设备，确认后重跑 `activate.py --force-login` |

> ⚠ `--force-login` 会踢掉该账号在其他设备的登录。**Agent 必须先向用户说明影响并取得确认**，不要不问直接加。

---

## 4. 禁区（Agent 必须遵守）

- **不要自动升级 / 替换已有的 Python 解释器**。探测出的 3.x 就用它，不要因为版本不够新换 Python。**仅当完全找不到任何 Python 时**才允许自主安装（版本要求见 §5.2）。
- **不要自动安装 / 升级 VC++ 运行库或其它系统级依赖**。
- **不要用 GUI 自动化（autohotkey、pyautogui、SendKeys 等）填手机号或验证码** —— 验证码必须人手输入，Agent 看不到短信。
- **不要用 SMS 转发服务、第三方网关、模拟器代用户发 `SXDL` 到 `9535711`** —— 必须由用户本人从绑定手机发送。
- **不要手动指定 SDK 安装路径或修改脚本中的路径常量** —— 路径由脚本管理（`<SDK基目录>/EMQuantAPI_Python/`）。
- **登录失败不要反复重试 `c.start()`** —— 脚本已内置重试，超过后必须停下来和用户对齐原因。

---

## 5. 附录

### 5.1 路径约定

所有 SDK 文件落到脚本自动判定的 SDK 基目录：妙想 Work 使用 `/workspace/user_space/.choice/`，妙想Claw 使用 `~/.openclaw/.choice/`，其他环境使用 `~/.choice/`。这些目录与项目仓库天然隔离，无需 `.gitignore` 排除。

| 项 | 值 |
| --- | --- |
| SDK 安装基目录 | `/workspace/user_space/.choice/`（妙想 Work）；`~/.openclaw/.choice/`（妙想Claw）；`~/.choice/`（其他环境） |
| SDK 工作目录 | `<SDK基目录>/EMQuantAPI_Python/<PYVER>/` |
| userInfo 凭据文件 | `<SDK基目录>/EMQuantAPI_Python/<PYVER>/libs/<PLATFORM>/userInfo` |
| defineCode 伴随文件（妙想Claw，可选） | 与 userInfo 同目录：`.../libs/<PLATFORM>/defineCode`；与 userInfo 同备份/同恢复 |

### 5.2 系统要求

- **OS**：Windows 32/64、CentOS / Ubuntu 32/64、macOS 64。
- **Python**：建议 ≥ 3.7。
- **Windows** 需先装 **Microsoft Visual C++ 2010 可再发行组件包**。
- **macOS GUI 激活** 需 **gtk+3.0**。

### 5.3 编码

脚本内部已处理（`PYTHONIOENCODING=utf-8` + `sys.stdout.reconfigure`），运行脚本无需额外加。

Agent 自行拼 `python -c` 查数时才需要：
- **单行 `-c`**：前缀 `PYTHONIOENCODING=utf-8`
- **多行 `-c`**：脚本开头加 `sys.stdout.reconfigure(encoding="utf-8")`

Linux/macOS 默认 UTF-8，加这两项无副作用，可无条件使用。

### 5.4 可选调试

`python scripts/activate.py --probe` 跟默认模式行为基本一样（探测后退出），但只输出探测信息（`PLATFORM=` / `USERINFO=` / `HAS_GUI=` / `ACTION=`），不输出 `RESULT=NEED_*`。**正常 Agent 流程用默认模式即可**，本 flag 仅环境探测异常排查用。
