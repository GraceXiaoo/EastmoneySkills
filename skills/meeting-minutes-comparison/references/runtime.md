# Python 运行时

## 当前策略：系统 Python 3

**使用系统 `python3`，不在 skill 目录创建 `.venv`。**

宿主机预装依赖（一次性，已安装可跳过）：

```bash
pip3 install httpx jinja2 requests python-docx urllib3 \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

- `run_py.sh` / `run_py.cmd`：直接调用 `python3`
- `ensure_env.py --check`：校验 `requirements.txt` 中的包是否可 import
- `ensure_env.py --ensure`：缺包时尝试 `pip3 install -r requirements.txt`

**禁止** bare `python`。**不要**在 skill 源目录保留 `.venv`（会随 `add_skill` 拷进用户 session）。

## 门禁（任何 `scripts/*.py` 之前）

Linux（在 workspace 根目录执行时，**脚本参数**用 `scripts/...`，不要带 `skills/policy-comparison/` 前缀）：

```bash
bash skills/policy-comparison/scripts/run_py.sh scripts/ensure_env.py --check
```

或在 skill 目录内：

```bash
cd skills/policy-comparison && bash scripts/run_py.sh scripts/ensure_env.py --check
```

Windows：

```text
skills\policy-comparison\scripts\run_py.cmd scripts\ensure_env.py --check
```

- exit `0` 且 JSON `"ok": true` → 继续
- 否则 → 停止生成，回复环境不满足（附 JSON `message`）

## 日常命令（Linux）

```bash
scripts/run_py.sh scripts/generate_policy_document.py \
  --conference "2025年中央经济工作会议" \
  --output-dir skills/policy-comparison/output/2026-07-13/reports

scripts/run_py.sh scripts/read_docx.py --path skills/policy-comparison/output/2026-07-13/reports/xxx.docx

scripts/run_py.sh scripts/validate.py --date 2026-07-13
```

`run_py` 会自动选择解释器，Agent **不要**手写 `python` / `python3` / `uv run`。

## 文档生成认证

`generate_policy_document.py` 通过 `mx-saas-platform` 聚合接口生成单场会议报告，需要配置 `EM_API_KEY`。

调用流程：

```text
research -> 聚合接口完成多步骤大纲和正文生成 -> 保存 Word
```

多个会议由 Agent 调度时，同时运行的文档生成任务最多为 **2**。该限制由调度层保证；单会议脚本不再派生子进程。

优先级：**环境变量 > 打包占位符**

| 来源 | 变量 |
|------|------|
| 环境变量 | `EM_API_KEY` |
| 打包占位符 | `{em_api_key}` |

脚本不再使用 `CTOKEN`、`UTOKEN`、`UID`。

## 环境不满足时的回复模板

```markdown
## 无法生成报告：Python 环境不满足

- **错误码**：ENV_UNSATISFIED
- **说明**：{ensure_env 输出的 message}
- **建议**：pip3 install httpx jinja2 requests python-docx urllib3 -i https://pypi.tuna.tsinghua.edu.cn/simple
```
