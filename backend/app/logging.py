"""structlog 配置：JSON 输出 + correlation ID（经 contextvars 注入）。

PRD 依据：实现决策 › 模块划分（structlog JSON 日志 + correlation ID 请求追踪）。
configure_logging 接受可选 stream 便于测试捕获，默认输出到 sys.stderr。
"""

from __future__ import annotations

import sys
from typing import TextIO

import structlog


def configure_logging(stream: TextIO | None = None) -> None:
    """配置 structlog 输出 JSON 日志到 stream（默认 stderr）。

    每条日志经 merge_contextvars 合入 correlation_id 等上下文变量，
    由 JSONRenderer 序列化为单行 JSON。cache_logger_on_first_use=False
    以便运行期重新指向不同 stream（测试场景）。
    """
    stream = stream if stream is not None else sys.stderr
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO 及以上
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )
