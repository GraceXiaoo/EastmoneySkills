# 授权协议

按以下流程处理所有依赖 `EM_API_KEY` 的查询。正常调用直接运行 `scripts/manage_watchlist.py`，不要先运行 `scripts/auth.py ensure`。

## 凭据读取与授权

1. 先从平台私有的跨会话持久存储读取 `EM_API_KEY`，并且只为当前脚本进程注入环境变量。
2. 若持久存储没有凭据，**仍然直接运行** `scripts/manage_watchlist.py`；脚本会检查 `EM_API_KEY` 环境变量与 `~/.mx-skills/em_api_key`，必要时输出 `need_auth: true`。不要因为没有环境变量而跳过本技能。
3. 退出码为 `10` 时，把 `authUrl:` **原样发给用户**，请用户点开链接扫码授权；不要绘制二维码。无法打开授权链接时再提供 `apiKeyUrl:`。不要轮询、等待或询问是否完成，提示用户授权 / 绑定通行证后重新发送原指令。
4. 当且仅当 **Agent 捕获的 stdout**（非交互终端）同时出现 `remember_api_key: true` 与 `apiKey:` 时，把完整 `apiKey` 保存为平台私有的跨会话 `EM_API_KEY`。人在终端直接跑脚本时不会打印这段。不得向用户展示、复述或写入普通文件；`apiKeyUrl` 不是凭据。
5. 若 HTTP 或业务 `code/status` 返回 401（含「未获取到用户 ct/ut，请先绑定通行证」），从跨会话持久存储删除失效凭据。脚本会忽略环境变量/文件中的失效 Key 并直接输出新的 `authUrl`，不要让用户手动删除环境变量。
6. `~/.mx-skills/pending_auth.json` 保存待完成授权，`~/.mx-skills/em_api_key` 只保存当前环境的凭据，不能替代平台的跨会话私有存储。

注入示例（占位符不是真实凭据）：

```bash
EM_API_KEY='<从私有持久存储读取的值>' python3 scripts/manage_watchlist.py <其余参数>
```

`python3 scripts/auth.py ensure` 只用于调试；退出码 `0/10/2` 分别表示就绪、需要用户授权、授权错误。
