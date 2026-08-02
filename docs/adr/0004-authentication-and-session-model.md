# 认证与会话模型

采用手机号 + 服务密码(单因素)认证,JWT 作为会话凭证(access token 2h + refresh token 7d),bcrypt 存储服务密码(成本 12)。办理类 Ticket 执行前必须二次输入服务密码复核(`Transaction Re-auth`),作为单因素认证的补偿控制。

## Status

accepted

## Considered Options

**认证因素:**

- **单因素(手机号 + 服务密码)** — 选定。开发简单,但合规风险。
- **双因素(手机号 + 短信验证码 + 服务密码)** — 否决。需引入短信通道,v1 不接入;但保留扩展位(密钥清单含 `SMS_API_KEY`)。

**会话凭证:**

- **JWT 无状态** — 选定。v1 无 Redis,JWT 不查库契合;WS 认证用 JWT 查询参数,REST 用 Authorization header。
- **服务端 Session + Cookie** — 否决。需 Redis 或 DB 存会话,v1 无 Redis。
- **长效 API Token** — 否决。无过期不安全。

**密码存储:**

- **bcrypt** — 选定。`passlib[bcrypt]` 是 FastAPI 标配,合规审计认可。
- **argon2** — 否决。Python 依赖较重,v1 不必要。
- **PBKDF2** — 否决。抗 GPU 攻击不如 bcrypt。

## Consequences

- **已知合规风险**:单因素认证不满足电信/金融业监管要求,服务密码泄露后攻击者可办业务。通过 `Transaction Re-auth` 补偿控制缓解,但 v2 应升级双因素。
- 办理类业务流程多一步:Ticket 入队 → 执行前复核服务密码 → 执行。
- JWT refresh token 需存储于前端 httpOnly cookie 或 localStorage,有 XSS 风险(v1 接受)。
