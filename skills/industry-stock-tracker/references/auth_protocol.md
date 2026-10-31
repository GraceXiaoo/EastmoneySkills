# 授权协议

正常调用直接运行业务脚本，不要先运行 `scripts/auth.py ensure`。

1. 从平台私有跨会话存储读取 `EM_API_KEY`，仅为当前脚本进程注入环境变量。
2. 没有凭据时直接运行脚本；脚本依次检查环境变量和 `~/.mx-skills/em_api_key`。
3. 退出码 `10` 表示需要授权：优先把 `authUrl` 显示为二维码，无法扫码时提供 `apiKeyUrl`，提示用户授权后重新发送原指令，不要轮询等待。
4. stdout 同时出现 `remember_api_key: true` 与 `apiKey:` 时，将完整值保存为平台私有跨会话 `EM_API_KEY`，不得向用户展示或写入业务文件。
5. HTTP 或业务 `code/status` 返回 401/403 时，从私有存储删除失效凭据；脚本会清理文件凭据并创建新授权。
6. `~/.mx-skills/pending_auth.json` 保存待完成授权，`~/.mx-skills/em_api_key` 保存本地凭据。

`python3 scripts/auth.py ensure` 仅用于调试；退出码 `0/10/2` 分别表示就绪、需要用户授权、授权错误。
