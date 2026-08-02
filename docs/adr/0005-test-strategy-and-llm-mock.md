# 测试策略与 LLM Mock

采用三层测试:单元测试(业务逻辑)+ 集成测试(API + DB)+ 冒烟测试(关键路径端到端)。后端用 pytest + pytest-asyncio + httpx + factory-boy;LLM 测试用 Mock LLM(`FakeListLLM` 返回固定响应)验证对话流与 tool 调用逻辑,不验证 LLM 质量。前端用 Vitest + Vue Test Utils + Playwright。

## Status

accepted

## Considered Options

**LLM 测试策略:**

- **Mock LLM** — 选定。CI 必须确定性,真实 LLM 输出不稳定;业务逻辑用 Mock,LLM 质量评估单独走评估集(线下)。
- **真实 LLM 集成测试** — 否决。成本高、不稳定、CI 不可控。
- **LLM-as-judge** — 否决。适合评估但不适合 CI。

## Consequences

- CI 不烧 token,运行快且稳定。
- LLM 输出质量无自动化保障,需线下维护评估集人工 review。
- LangChain tool 调用逻辑必须可独立测试(纯函数 + Mock),不能与 LLM 调用耦合。
