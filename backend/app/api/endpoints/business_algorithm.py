"""业务算法库代理端点 — 将请求转发到 balibrary 独立服务.

返回格式与 cube-studio 代理层保持一致: 直接透传 balibrary 解包后的 data,
不使用 BaseResponse 包装, 以兼容前端现有代码.
"""

from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Body

from app.api.deps import CurrentUser
from app.core.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/algorithm_api", tags=["business-algorithm"])

BALIBRARY_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


async def _proxy_to_balibrary(path: str, payload: dict[str, Any]) -> Any:
    """将请求转发到 balibrary 服务并解包 {code, msg, data} 结构."""
    base_url = getattr(settings, "BALIBRARY_URL", "http://balibrary.kubeai.svc:8800").rstrip("/")
    target_url = f"{base_url}/businessAlgorithm/{path}"

    async with httpx.AsyncClient(timeout=BALIBRARY_TIMEOUT) as client:
        resp = await client.post(target_url, json=payload)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()

    # balibrary 返回 {code, msg, data} 包装, 取出 data 直接透传
    if isinstance(result, dict) and "data" in result:
        return result["data"]
    return result


@router.post("/heuristicAlgorithms/optimize")
async def optimize_metaheuristic(
    _: CurrentUser,
    payload: Annotated[dict[str, Any], Body(...)],
) -> Any:
    """元启发算法优化 — 遗传算法、粒子群、免疫遗传等."""
    return await _proxy_to_balibrary("heuristicAlgorithms/optimize", payload)


@router.post("/dataPlanning/optimize")
async def optimize_data_planning(
    _: CurrentUser,
    payload: Annotated[dict[str, Any], Body(...)],
) -> Any:
    """数据规划算法优化 — 混合整数规划、约束规划、拉格朗日松弛."""
    return await _proxy_to_balibrary("dataPlanning/optimize", payload)


@router.post("/heuristicRules/optimize")
async def optimize_heuristic_rules(
    _: CurrentUser,
    payload: Annotated[dict[str, Any], Body(...)],
) -> Any:
    """启发式规则算法优化 — 转移瓶颈、插入规则、优先分派."""
    return await _proxy_to_balibrary("heuristicRules/optimize", payload)
