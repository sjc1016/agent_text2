"""Alembic 迁移环境。

复用 app.db.create_engine 以确保迁移过程启用 SQLite WAL/外键。
target_metadata 暂为 None（F0 无业务模型）；B-slice 接入 Base.metadata 后可启用 autogenerate。
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# 让 env.py 可 import app.*（兼容从任意 CWD 调用）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import create_engine as app_create_engine  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # F0 baseline；B-slice 接入 Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    connectable = app_create_engine(url)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
