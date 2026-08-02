"""F0 循环2：monorepo 结构成立 + 前端 pnpm workspace + 后端 uv 可装依赖。

验收标准（issue #2）：
  monorepo 结构成立（frontend/customer、frontend/agent、frontend/shared、backend、docs），
  前端 pnpm workspace + 后端 uv 可安装依赖
  （PRD 依据：实现决策 › 部署；用户故事 US-全）

结构性断言：目录树 + pnpm workspace 配置 + 各前端包 package.json。
「可装依赖」由 `uv sync`（后端）与 `pnpm install`（前端）成功执行验证，不在本测试内重复。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_monorepo_directories_exist():
    expected = [
        REPO_ROOT / "frontend" / "customer",
        REPO_ROOT / "frontend" / "agent",
        REPO_ROOT / "frontend" / "shared",
        REPO_ROOT / "backend",
        REPO_ROOT / "docs",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in expected if not p.is_dir()]
    assert not missing, f"missing monorepo dirs: {missing}"


def test_pnpm_workspace_config_exists():
    workspace = REPO_ROOT / "pnpm-workspace.yaml"
    assert workspace.is_file(), "pnpm-workspace.yaml missing at repo root"


def test_frontend_packages_have_manifests():
    for pkg in ("customer", "agent", "shared"):
        manifest = REPO_ROOT / "frontend" / pkg / "package.json"
        assert manifest.is_file(), f"frontend/{pkg}/package.json missing"
