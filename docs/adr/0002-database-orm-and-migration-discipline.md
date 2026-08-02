# 数据库与 ORM/迁移纪律

采用 SQLite 作为统一数据库,SQLAlchemy 2.0 作为 ORM,Alembic 作为迁移工具,sqlite-vec 作为向量检索扩展。所有 schema 变更必须经 Alembic 迁移,禁止手动改库,迁移脚本必须可回滚,向量库 schema 同步纳入 Alembic。

## Status

accepted

## Considered Options

**ORM:**

- **SQLAlchemy 2.0 + Alembic** — 选定。LangChain 生态原生支持(ChatMessageHistory 等),异步完善,电信复杂查询需直接控制 SQL。
- **Tortoise ORM + Aerich** — 否决。生态小,异步原生但 LangChain 兼容差。
- **SQLModel** — 否决。底层仍 SQLAlchemy,隐藏复杂度对电信场景不利。

**向量库:**

- **sqlite-vec** — 选定。与 SQLite 同进程,部署最简,LangChain 0.2+ 原生支持。
- **Chroma 嵌入式** — 否决。独立向量库,数据分离,部署成本高。
- **FAISS** — 否决。全内存,需自行持久化,不适合生产。

## Consequences

- v1 无独立向量服务,部署最简。
- SQLite 并发写受限,需开启 WAL 模式(见 ADR-0006 部署)。
- 迁移纪律强:每次 PR 含 schema 变更必须带可回滚迁移脚本。
