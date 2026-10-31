# AgentLoop 标准 scripts 套件

## Python 运行时（当前策略）

**使用系统 `python3`，不在 skill 目录创建 `.venv`。**

宿主机需预装依赖（一次性）：

```bash
pip3 install httpx jinja2 requests python-docx urllib3 \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

各 skill 的 `requirements.txt` 仍保留，用于 `ensure_env.py` 校验缺包。

| 脚本 | 说明 |
|------|------|
| `ensure_env.py` | 检查系统 python3 + requirements 导入 |
| `run_py.sh` / `run_py.cmd` | 直接 `exec python3` |
| `validate.py` | 本 skill 交付物校验 |
| 其他 | 见各 skill 业务脚本 |

## 调用示例（workspace 根目录）

```bash
bash skills/{skill-name}/scripts/run_py.sh scripts/ensure_env.py --check
```

## 注意

- **不要**在 `applications/skills/*/` 下保留 `.venv`（会随 `add_skill` 拷进用户 session，拖慢加载）
- `.gitignore` 已忽略 `.venv/`，开发时若误建请手动删除
