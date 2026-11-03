"""架构约束测试：用 AST 静态校验分层依赖方向。

不依赖数据库、网络与 LLM Key，可单独运行::

    uv run pytest tests/test_layering.py -v

这些用例守护的是「依赖方向」这条约定：一旦有人在 Service 层 import
FastAPI、或在 Repository 层 import Service，测试立即失败，
而不是等到代码 review 时靠人眼发现。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# 本文件位于 backend/tests/unit/ → 上三级为 backend/，其下的 app/ 才是源码根目录
APP_DIR: Path = Path(__file__).resolve().parents[2] / "app"

# 每层允许依赖的 app 内部层。key 为层名，value 为该层可以 import 的层集合。
# 依赖必须单向：api → service → repository → models。
ALLOWED_INTERNAL: dict[str, set[str]] = {
    "api": {"service", "schemas", "models", "core", "config", "api"},
    "service": {
        "repository",
        "models",
        "schemas",
        "core",
        "config",
        "agent",
        "retrieval",
        "utils",
        "service",
    },
    "repository": {"models", "core", "config", "repository"},
    "models": {"config", "core", "models"},
    "schemas": {"schemas"},
    "agent": {"agent", "schemas", "config", "core", "retrieval", "repository", "models"},
    "retrieval": {"retrieval", "config", "core", "repository", "models"},
    "core": {"core", "config", "models", "repository"},
    "config": {"config"},
    "utils": {"utils", "config", "schemas", "models"},
}

# 每层禁止直接 import 的第三方包。业务层不该知道 Web 框架的存在。
FORBIDDEN_EXTERNAL: dict[str, set[str]] = {
    "service": {"fastapi", "starlette"},
    "repository": {"fastapi", "starlette"},
    "models": {"fastapi", "starlette"},
    "schemas": {"fastapi", "starlette"},
    "retrieval": {"fastapi", "starlette"},
    "agent": {"fastapi", "starlette"},
}


def _iter_layer_modules(layer: str) -> list[tuple[Path, str]]:
    """收集某一层下所有 .py 文件的路径与源码。"""

    layer_dir: Path = APP_DIR / layer
    if not layer_dir.is_dir():
        return []
    return [(path, path.read_text(encoding="utf-8")) for path in sorted(layer_dir.rglob("*.py"))]


def _imported_roots(source: str) -> list[str]:
    """从源码中解析出所有 import 的顶层包名。"""

    tree: ast.Module = ast.parse(source)
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.append(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("layer", sorted(ALLOWED_INTERNAL))
def test_layer_internal_dependencies(layer: str) -> None:
    """每一层只能依赖白名单内的 app 内部层。"""

    allowed: set[str] = ALLOWED_INTERNAL[layer]
    violations: list[str] = []

    for path, source in _iter_layer_modules(layer):
        for root in _imported_roots(source):
            if root == "app":
                # from app.xxx import ... —— 取第二段作为层名
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        parts: list[str] = node.module.split(".")
                        if parts[0] == "app" and len(parts) > 1 and parts[1] not in allowed:
                            violations.append(f"{path.name}:{node.lineno} -> {node.module}")
            elif root in ALLOWED_INTERNAL and root != layer and root not in allowed:
                violations.append(f"{path.name} -> {root}")

    assert not violations, f"[{layer}] 层存在越层依赖:\n" + "\n".join(violations)


# 已知债务：Service 层目前 import 了 fastapi 并抛 HTTPException，
# 三条约束暂时用 xfail 登记。strict=True 意味着一旦修复导致用例意外通过，
# pytest 会报 XPASS 失败，提醒我们把 xfail 标记摘掉。
KNOWN_DEBT = pytest.mark.xfail(
    strict=True,
    reason="已知债务：Service 层依赖 fastapi（待改为抛 AppError 子类后摘除本标记）",
)


@pytest.mark.parametrize(
    "layer",
    [
        # 只有 service 层当前违规，其余层必须保持通过，不能一并标 xfail
        pytest.param(layer, marks=KNOWN_DEBT) if layer == "service" else layer
        for layer in sorted(FORBIDDEN_EXTERNAL)
    ],
)
def test_business_layers_do_not_import_web_framework(layer: str) -> None:
    """业务层不得 import Web 框架（fastapi / starlette）。"""

    forbidden: set[str] = FORBIDDEN_EXTERNAL[layer]
    violations: list[str] = []

    for path, source in _iter_layer_modules(layer):
        for node in ast.walk(ast.parse(source)):
            lineno: int = getattr(node, "lineno", 0)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden:
                        violations.append(f"{path.name}:{lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in forbidden:
                    violations.append(f"{path.name}:{lineno} from {node.module}")

    assert not violations, f"[{layer}] 层不应依赖 Web 框架，但发现:\n" + "\n".join(violations)


@KNOWN_DEBT
def test_raised_exceptions_are_domain_exceptions() -> None:
    """业务层抛出的应是领域异常，而不是 HTTPException。

    HTTPException 携带 status_code，属于 HTTP 协议语义。
    业务层一旦抛出它，该层就无法在非 HTTP 上下文（CLI、定时任务、
    未来的 worker）中复用。
    """

    violations: list[str] = []
    for path, source in _iter_layer_modules("service"):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                func = node.exc.func
                name: str = getattr(func, "id", None) or getattr(func, "attr", None) or ""
                if name == "HTTPException":
                    violations.append(f"{path.name}:{node.lineno} raise HTTPException(...)")

    assert not violations, "Service 层不应抛 HTTPException，应抛 AppError 子类:\n" + "\n".join(
        violations
    )


def _domain_exception_names() -> set[str]:
    """解析 app/core/exceptions.py 中定义的异常类名。"""

    source: str = (APP_DIR / "core" / "exceptions.py").read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef):
            bases: list[str] = [base.id for base in node.bases if isinstance(base, ast.Name)]
            if "Exception" in bases or "AppError" in bases:
                names.add(node.name)
    return names


@KNOWN_DEBT
def test_app_error_is_actually_used() -> None:
    """AppError 必须有业务代码真正抛出，否则注册了 handler 也是死代码。

    只认 core/exceptions.py 里定义的异常类，不能用 endswith("Error") 之类的
    模糊匹配 —— 那会把 ValueError 也算进来，导致假通过。
    """

    domain_names: set[str] = _domain_exception_names()
    raised: list[str] = []

    for layer in ALLOWED_INTERNAL:
        for path, source in _iter_layer_modules(layer):
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    func = node.exc.func
                    name: str = getattr(func, "id", None) or getattr(func, "attr", None) or ""
                    if name in domain_names:
                        raised.append(f"{layer}/{path.name}:{node.lineno} raise {name}")

    assert raised, (
        f"core/exceptions.py 定义了 {sorted(domain_names)} 并注册了 handler，"
        "但业务代码中没有任何地方 raise 它们 —— handler 是死代码。"
    )
