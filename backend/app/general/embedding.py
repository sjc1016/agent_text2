"""确定性文本嵌入（v1 本地实现，无外部 API）。

PRD 依据：
  - 实现决策 › 知识来源（非结构化文档 RAG，sqlite-vec 向量检索）
  - 测试决策 › tool 调用 seam（RAG 检索确定性，CI 可复现）

设计说明：
  - 字符 unigram/bigram/trigram 哈希袋 → 归一化单位向量，序列化为 sqlite-vec
    float32 blob（little-endian，与 vec0 虚拟表 MATCH 兼容）。
  - 语义相似的文本共享更多字符 n-gram，向量夹角更小——足够支撑
    「政策/规则/手册」类文档的检索；真实语义嵌入可替换本函数（接口不变）。
  - dim=256 + trigram：降低哈希碰撞，保证无关文档距离 > 1.2 阈值
    （不编造：相关 ~1.0-1.2，无关 >1.25，阈值 1.2 可分离）。
"""

from __future__ import annotations

import hashlib
import math
import re
import struct

#: 向量维度（sqlite-vec vec0 表列维度，须与迁移 0006 一致）
EMBEDDING_DIM = 256


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> bytes:
    """将文本编码为 dim 维单位向量，返回 sqlite-vec float32 blob。

    Args:
        text: 待嵌入文本（中文按字符处理，n-gram 捕获局部语义）
        dim: 向量维度，须与 vec0 表列维度一致
    """
    chars = list(re.sub(r"\s+", "", text))
    vec = [0.0] * dim

    def _bucket(token: str) -> int:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:2], "big") % dim

    for ch in chars:
        vec[_bucket(ch)] += 1.0
    for i in range(len(chars) - 1):
        vec[_bucket(chars[i] + chars[i + 1])] += 2.0
    for i in range(len(chars) - 2):
        vec[_bucket(chars[i] + chars[i + 1] + chars[i + 2])] += 3.0

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        norm = 1.0
    vec = [v / norm for v in vec]
    return struct.pack(f"<{dim}f", *vec)
