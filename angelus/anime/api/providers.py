"""/api/anime/providers/* 路由：Provider 能力查询（不含密钥）。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter

from ..providers.registry import build_router

router = APIRouter()

_router = None


def set_router(router_instance: Any) -> None:
    """注入共享 ProviderRouter（webapp 挂载时调用）。"""
    global _router
    _router = router_instance


def _get_router() -> Any:
    if _router is None:
        return build_router()
    return _router


@router.get("/api/anime/providers")
def list_providers() -> dict[str, Any]:
    """列出已注册 provider 及其能力（不暴露任何密钥）。"""
    router = _get_router()
    providers: list[dict[str, Any]] = []
    for name in router.names():
        try:
            provider = router.get(name)
            capabilities = provider.capabilities() if hasattr(provider, "capabilities") else {}
        except Exception:  # noqa: BLE001 - 单个 provider 失败不影响列表
            capabilities = {}
        providers.append({"name": name, "capabilities": capabilities})
    return {"providers": providers}
