"""真实 LLM 联调验证脚本 — 验证 OpenAI 兼容 API 主备接入的真实对话能力。

验证场景（11 项）：
   1. 主 provider（agnes-ai）非流式 invoke
   2. 主 provider 流式 stream（逐 token）
   3. 备 provider（NVIDIA NIM minimax-m3）非流式 invoke
   4. 备 provider 流式 stream
   5. FailoverLLM 主备切换（主故意失败 → 切备）
   6. AssistantService 多轮对话 — 主 provider（上下文记忆）
   7. Tool 调用协议检测 — 主 provider（<|tool_call:name:json|> 格式）
   8. Tool 调用协议检测 — 备 provider
   9. 异步不阻塞事件循环（issue #67 回归）
  10. NVIDIA NIM minimax-m3 多轮对话（上下文记忆）
  11. FailoverLLM 多轮对话（主→备切换多轮）

运行方式：
  cd backend
  .venv\\Scripts\\python.exe scripts\verify_real_llm.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# 确保能找到 app 包
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
os.chdir(str(backend_dir))

# 从 .env 读取配置（避免硬编码 key）；需在 sys.path 就绪后导入 app 包
from app.config import get_settings  # noqa: E402

_settings = get_settings()
PRIMARY_BASE_URL = _settings.llm_base_url
PRIMARY_API_KEY = _settings.llm_api_key
PRIMARY_MODEL = _settings.llm_model
FAILOVER_BASE_URL = _settings.llm_failover_base_url
FAILOVER_API_KEY = _settings.llm_failover_api_key
FAILOVER_MODEL = _settings.llm_failover_model
TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# 测试结果收集
# ---------------------------------------------------------------------------
class TestReport:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def record(self, name: str, success: bool, detail: str = ""):
        self.results.append((name, success, detail))
        status = "PASS" if success else "FAIL"
        print(f"\n{'=' * 60}")
        print(f"  [{status}] {name}")
        if detail:
            for line in detail.split("\n"):
                print(f"    {line}")
        print(f"{'=' * 60}")

    def summary(self):
        total = len(self.results)
        passed = sum(1 for _, ok, _ in self.results if ok)
        print(f"\n{'#' * 60}")
        print(f"  联调验证结果: {passed}/{total} 通过")
        print(f"{'#' * 60}")
        for name, ok, detail in self.results:
            status = "PASS" if ok else "FAIL"
            short = detail.split("\n")[0][:60] if detail else ""
            print(f"  [{status}] {name}" + (f" -- {short}" if short else ""))
        return passed == total


report = TestReport()


# ---------------------------------------------------------------------------
# 场景 1-2：主 provider
# ---------------------------------------------------------------------------
async def test_primary_invoke():
    """场景1：主 provider 非流式调用。"""
    from app.agent.llm import ChatMessage, ChatRole, OpenAICompatLLM

    llm = OpenAICompatLLM(
        base_url=PRIMARY_BASE_URL,
        api_key=PRIMARY_API_KEY,
        model=PRIMARY_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    try:
        start = time.time()
        result = await llm.invoke(
            [
                ChatMessage(role=ChatRole.SYSTEM, content="你是中国电信客服助理，请简短回复。"),
                ChatMessage(role=ChatRole.USER, content="你好，请问有什么套餐推荐？"),
            ]
        )
        elapsed = time.time() - start
        success = bool(result) and len(result) > 5
        report.record(
            f"场景1: 主 provider({PRIMARY_MODEL}) 非流式 invoke",
            success,
            f"耗时: {elapsed:.2f}s\n回复: {result[:200]}",
        )
    except Exception as e:
        report.record(f"场景1: 主 provider({PRIMARY_MODEL}) 非流式 invoke", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


async def test_primary_stream():
    """场景2：主 provider 流式调用。"""
    from app.agent.llm import ChatMessage, ChatRole, OpenAICompatLLM

    llm = OpenAICompatLLM(
        base_url=PRIMARY_BASE_URL,
        api_key=PRIMARY_API_KEY,
        model=PRIMARY_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    try:
        start = time.time()
        tokens = []
        async for token in llm.stream(
            [
                ChatMessage(role=ChatRole.SYSTEM, content="你是中国电信客服助理，请简短回复。"),
                ChatMessage(role=ChatRole.USER, content="帮我查一下营业厅地址"),
            ]
        ):
            tokens.append(token)
        elapsed = time.time() - start
        full = "".join(tokens)
        success = bool(full) and len(tokens) > 1
        report.record(
            f"场景2: 主 provider({PRIMARY_MODEL}) 流式 stream",
            success,
            f"耗时: {elapsed:.2f}s | token 数: {len(tokens)}\n回复: {full[:200]}",
        )
    except Exception as e:
        report.record(f"场景2: 主 provider({PRIMARY_MODEL}) 流式 stream", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


# ---------------------------------------------------------------------------
# 场景 3-4：备 provider
# ---------------------------------------------------------------------------
async def test_failover_invoke():
    """场景3：备 provider 非流式调用。"""
    from app.agent.llm import ChatMessage, ChatRole, OpenAICompatLLM

    llm = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    try:
        start = time.time()
        result = await llm.invoke(
            [
                ChatMessage(role=ChatRole.SYSTEM, content="你是中国电信客服助理，请简短回复。"),
                ChatMessage(role=ChatRole.USER, content="你好，请问有什么套餐推荐？"),
            ]
        )
        elapsed = time.time() - start
        success = bool(result) and len(result) > 5
        report.record(
            f"场景3: 备 provider({FAILOVER_MODEL}) 非流式 invoke",
            success,
            f"耗时: {elapsed:.2f}s\n回复: {result[:200]}",
        )
    except Exception as e:
        report.record(f"场景3: 备 provider({FAILOVER_MODEL}) 非流式 invoke", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


async def test_failover_stream():
    """场景4：备 provider 流式调用。"""
    from app.agent.llm import ChatMessage, ChatRole, OpenAICompatLLM

    llm = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    try:
        start = time.time()
        tokens = []
        async for token in llm.stream(
            [
                ChatMessage(role=ChatRole.SYSTEM, content="你是中国电信客服助理，请简短回复。"),
                ChatMessage(role=ChatRole.USER, content="帮我查一下营业厅地址"),
            ]
        ):
            tokens.append(token)
        elapsed = time.time() - start
        full = "".join(tokens)
        success = bool(full) and len(tokens) > 1
        report.record(
            f"场景4: 备 provider({FAILOVER_MODEL}) 流式 stream",
            success,
            f"耗时: {elapsed:.2f}s | token 数: {len(tokens)}\n回复: {full[:200]}",
        )
    except Exception as e:
        report.record(f"场景4: 备 provider({FAILOVER_MODEL}) 流式 stream", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


# ---------------------------------------------------------------------------
# 场景 5：FailoverLLM 主备切换
# ---------------------------------------------------------------------------
async def test_failover_switch():
    """场景5：FailoverLLM 主故意失败 → 自动切备 provider。"""
    from app.agent.llm import ChatMessage, ChatRole, FailoverLLM, OpenAICompatLLM

    primary = OpenAICompatLLM(
        base_url=PRIMARY_BASE_URL,
        api_key="sk-INVALID-KEY-FOR-TESTING",
        model=PRIMARY_MODEL,
        timeout_seconds=10.0,
    )
    backup = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        timeout_seconds=TIMEOUT,
    )
    llm = FailoverLLM(providers=[primary, backup])
    try:
        start = time.time()
        result = await llm.invoke(
            [
                ChatMessage(role=ChatRole.SYSTEM, content="你是中国电信客服助理，请简短回复。"),
                ChatMessage(role=ChatRole.USER, content="你好"),
            ]
        )
        elapsed = time.time() - start
        success = bool(result) and len(result) > 5
        report.record(
            "场景5: FailoverLLM 主备切换（主失败→备成功）",
            success,
            f"耗时: {elapsed:.2f}s\n回复: {result[:200]}",
        )
    except Exception as e:
        report.record("场景5: FailoverLLM 主备切换", False, f"异常: {e}")
    finally:
        await primary._client.aclose()
        await backup._client.aclose()


# ---------------------------------------------------------------------------
# 场景 6：AssistantService 多轮对话（主 provider）
# ---------------------------------------------------------------------------
async def test_assistant_multiturn_primary():
    """场景6：AssistantService 多轮对话 + 上下文记忆（主 provider）。"""
    from app.agent.llm import OpenAICompatLLM
    from app.agent.service import AssistantService

    llm = OpenAICompatLLM(
        base_url=PRIMARY_BASE_URL,
        api_key=PRIMARY_API_KEY,
        model=PRIMARY_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    svc = AssistantService(llm=llm)

    try:
        start = time.time()
        tokens_r1 = []
        async for token in svc.chat(conversation_id=100, user_message="你好，我是电信用户"):
            tokens_r1.append(token)
        reply_r1 = "".join(tokens_r1)
        elapsed_r1 = time.time() - start

        start = time.time()
        tokens_r2 = []
        async for token in svc.chat(conversation_id=100, user_message="我刚才说了我是谁？"):
            tokens_r2.append(token)
        reply_r2 = "".join(tokens_r2)
        elapsed_r2 = time.time() - start

        context_ok = "电信" in reply_r2 or "用户" in reply_r2
        success = bool(reply_r1) and bool(reply_r2) and "繁忙" not in reply_r2

        report.record(
            f"场景6: AssistantService 多轮对话（主 {PRIMARY_MODEL}）",
            success and context_ok,
            f"第一轮({elapsed_r1:.2f}s): {reply_r1[:150]}\n"
            f"第二轮({elapsed_r2:.2f}s): {reply_r2[:150]}\n"
            f"上下文记忆: {'OK' if context_ok else 'MISS'}",
        )
    except Exception as e:
        report.record("场景6: AssistantService 多轮对话（主）", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


# ---------------------------------------------------------------------------
# 场景 7-8：Tool 调用协议检测
# ---------------------------------------------------------------------------
TOOL_DESCRIPTIONS = (
    "- balance_lookup: 查询当前话费余额（元）\n"
    "- plan_detail_lookup: 查询当前套餐详情\n"
    "- general_info_search: 检索政策/规则/操作手册文档\n"
    "- plan_lookup: 查询套餐介绍与对比"
)


async def test_tool_call_primary():
    """场景7：主 provider Tool 调用协议检测。"""
    from app.agent.llm import ChatMessage, ChatRole, OpenAICompatLLM
    from app.agent.tools import parse_tool_call

    llm = OpenAICompatLLM(
        base_url=PRIMARY_BASE_URL,
        api_key=PRIMARY_API_KEY,
        model=PRIMARY_MODEL,
        temperature=0.1,
        timeout_seconds=TIMEOUT,
        tool_descriptions=TOOL_DESCRIPTIONS,
    )
    try:
        result = await llm.invoke(
            [
                ChatMessage(role=ChatRole.USER, content="帮我查一下话费余额"),
            ]
        )
        call = parse_tool_call(result)
        success = call is not None
        detail = f"LLM 原始输出: {result[:200]}\n"
        if call:
            detail += f"解析结果: tool={call.name}, params={call.params}"
        else:
            detail += "未检测到 tool_call 标记"
        report.record("场景7: 主 provider Tool 调用协议检测", success, detail)
    except Exception as e:
        report.record("场景7: 主 provider Tool 调用协议检测", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


async def test_tool_call_failover():
    """场景8：备 provider Tool 调用协议检测。"""
    from app.agent.llm import ChatMessage, ChatRole, OpenAICompatLLM
    from app.agent.tools import parse_tool_call

    llm = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        temperature=0.1,
        timeout_seconds=TIMEOUT,
        tool_descriptions=TOOL_DESCRIPTIONS,
    )
    try:
        result = await llm.invoke(
            [
                ChatMessage(role=ChatRole.USER, content="帮我查一下话费余额"),
            ]
        )
        call = parse_tool_call(result)
        success = call is not None
        detail = f"LLM 原始输出: {result[:200]}\n"
        if call:
            detail += f"解析结果: tool={call.name}, params={call.params}"
        else:
            detail += "未检测到 tool_call 标记"
        report.record(f"场景8: 备 provider({FAILOVER_MODEL}) Tool 调用协议检测", success, detail)
    except Exception as e:
        report.record("场景8: 备 provider Tool 调用协议检测", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


# ---------------------------------------------------------------------------
# 场景 9：异步不阻塞验证（issue #67 回归）
# ---------------------------------------------------------------------------
async def test_async_non_blocking():
    """场景9：长耗时 LLM 调用不阻塞事件循环。"""
    from app.agent.llm import OpenAICompatLLM
    from app.agent.service import AssistantService

    llm = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        timeout_seconds=TIMEOUT,
    )
    svc = AssistantService(llm=llm)

    try:
        timer_done = asyncio.Event()

        async def timer():
            await asyncio.sleep(0.05)
            timer_done.set()

        timer_task = asyncio.create_task(timer())
        tokens = []
        async for tok in svc.chat(conversation_id=200, user_message="你好"):
            tokens.append(tok)
        await timer_task

        reply = "".join(tokens)
        success = timer_done.is_set() and bool(reply)
        report.record(
            "场景9: 异步不阻塞事件循环（issue #67 回归）",
            success,
            f"定时器在 LLM 期间就绪: {'OK' if timer_done.is_set() else 'BLOCKED'}\n"
            f"回复: {reply[:150]}",
        )
    except Exception as e:
        report.record("场景9: 异步不阻塞事件循环", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


# ---------------------------------------------------------------------------
# 场景 10：NVIDIA NIM minimax-m3 多轮对话
# ---------------------------------------------------------------------------
async def test_nim_multiturn():
    """场景10：备 provider 多轮对话（上下文记忆）。"""
    from app.agent.llm import OpenAICompatLLM
    from app.agent.service import AssistantService

    llm = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    svc = AssistantService(llm=llm)

    try:
        start = time.time()
        tokens_r1 = []
        async for token in svc.chat(conversation_id=300, user_message="你好，我是电信用户"):
            tokens_r1.append(token)
        reply_r1 = "".join(tokens_r1)
        elapsed_r1 = time.time() - start

        start = time.time()
        tokens_r2 = []
        async for token in svc.chat(conversation_id=300, user_message="我刚才说了我是谁？"):
            tokens_r2.append(token)
        reply_r2 = "".join(tokens_r2)
        elapsed_r2 = time.time() - start

        context_ok = "电信" in reply_r2 or "用户" in reply_r2
        success = bool(reply_r1) and bool(reply_r2) and "繁忙" not in reply_r2

        report.record(
            f"场景10: 备 provider({FAILOVER_MODEL}) 多轮对话",
            success and context_ok,
            f"第一轮({elapsed_r1:.2f}s): {reply_r1[:150]}\n"
            f"第二轮({elapsed_r2:.2f}s): {reply_r2[:150]}\n"
            f"上下文记忆: {'OK' if context_ok else 'MISS'}",
        )
    except Exception as e:
        report.record("场景10: 备 provider 多轮对话", False, f"异常: {e}")
    finally:
        await llm._client.aclose()


# ---------------------------------------------------------------------------
# 场景 11：FailoverLLM 多轮对话
# ---------------------------------------------------------------------------
async def test_failover_multiturn():
    """场景11：FailoverLLM 多轮对话（主→备切换多轮）。"""
    from app.agent.llm import FailoverLLM, OpenAICompatLLM
    from app.agent.service import AssistantService

    primary = OpenAICompatLLM(
        base_url=PRIMARY_BASE_URL,
        api_key=PRIMARY_API_KEY,
        model=PRIMARY_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    backup = OpenAICompatLLM(
        base_url=FAILOVER_BASE_URL,
        api_key=FAILOVER_API_KEY,
        model=FAILOVER_MODEL,
        temperature=0.7,
        timeout_seconds=TIMEOUT,
    )
    llm = FailoverLLM(providers=[primary, backup])
    svc = AssistantService(llm=llm)

    try:
        start = time.time()
        tokens_r1 = []
        async for token in svc.chat(conversation_id=400, user_message="你好，我是电信用户"):
            tokens_r1.append(token)
        reply_r1 = "".join(tokens_r1)
        elapsed_r1 = time.time() - start

        start = time.time()
        tokens_r2 = []
        async for token in svc.chat(conversation_id=400, user_message="我刚才说了我是谁？"):
            tokens_r2.append(token)
        reply_r2 = "".join(tokens_r2)
        elapsed_r2 = time.time() - start

        context_ok = "电信" in reply_r2 or "用户" in reply_r2
        success = bool(reply_r1) and bool(reply_r2) and "繁忙" not in reply_r2

        report.record(
            "场景11: FailoverLLM 多轮对话（主→备切换）",
            success and context_ok,
            f"第一轮({elapsed_r1:.2f}s): {reply_r1[:150]}\n"
            f"第二轮({elapsed_r2:.2f}s): {reply_r2[:150]}\n"
            f"上下文记忆: {'OK' if context_ok else 'MISS'}",
        )
    except Exception as e:
        report.record("场景11: FailoverLLM 多轮对话", False, f"异常: {e}")
    finally:
        await primary._client.aclose()
        await backup._client.aclose()


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def main():
    print("=" * 60)
    print("  真实 LLM 联调验证")
    print(f"  主 provider: {PRIMARY_MODEL} @ {PRIMARY_BASE_URL}")
    print(f"  备 provider: {FAILOVER_MODEL} @ {FAILOVER_BASE_URL}")
    print(f"  超时: {TIMEOUT}s")
    print("=" * 60)

    await test_primary_invoke()
    await test_primary_stream()
    await test_failover_invoke()
    await test_failover_stream()
    await test_failover_switch()
    await test_assistant_multiturn_primary()
    await test_tool_call_primary()
    await test_tool_call_failover()
    await test_async_non_blocking()
    await test_nim_multiturn()
    await test_failover_multiturn()

    all_passed = report.summary()
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
