from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import optuna
from optuna.distributions import (
    BaseDistribution,
    CategoricalDistribution,
    FloatDistribution,
    IntDistribution,
)
from optuna.importance import PedAnovaImportanceEvaluator
from optuna.storages import RDBStorage

from app.core.config import settings

if TYPE_CHECKING:
    from optuna.study import Study
    from optuna.trial import Trial, TrialState

# 平台 search_space 支持的参数类型
SEARCH_SPACE_TYPES = ("float", "int", "categorical", "fixed")


def _dbname_of(url: str) -> str:
    """从连接 URL 取数据库名 (路径末段, 去 query), 粗粒度用于区分两库是否同名."""
    return url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]


def sync_db_url() -> str:
    """Optuna RDBStorage 用的同步 URL (asyncpg → psycopg2).

    Optuna 是同步 SQLAlchemy 库, 无法用 asyncpg 方言; OPTUNA_DATABASE_URL 须指向独立数据库,
    Optuna 在其上自建 version_info/studies/trials/... 表 (与平台库物理隔离, 见 get_optuna_storage 校验).
    """
    return settings.OPTUNA_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


@lru_cache(maxsize=1)
def get_optuna_storage() -> RDBStorage:
    """RDBStorage 单例 (惰性首次访问时建表).

    Optuna 必须使用独立数据库, 不得复用平台 DATABASE_URL: 两者各自走 Alembic 管理 schema,
    共库会共用同一张 alembic_version, 导致 Optuna 误判已初始化而跳过建表, 或污染平台迁移状态.
    """
    if not settings.OPTUNA_DATABASE_URL:
        raise RuntimeError("OPTUNA_DATABASE_URL 未配置; Optuna 必须使用独立数据库 (与平台 DATABASE_URL 不同库)")
    if _dbname_of(settings.OPTUNA_DATABASE_URL) == _dbname_of(settings.DATABASE_URL):
        raise RuntimeError(
            f"OPTUNA_DATABASE_URL 与平台 DATABASE_URL 指向同一数据库 "
            f"({_dbname_of(settings.DATABASE_URL)}); Optuna 须用独立数据库以避免 alembic_version 冲突"
        )
    return RDBStorage(
        url=sync_db_url(),
        heartbeat_interval=settings.OPTUNA_STORAGE_HEARTBEAT_SECONDS,
    )


def json_search_space_to_distributions(
    search_space: dict[str, dict[str, Any]],
) -> tuple[dict[str, BaseDistribution], dict[str, Any]]:
    """把平台 search_space JSON 转成 optuna distributions 与固定参数.

    JSON 格式: {name: {type: "float"|"int"|"categorical"|"fixed", ...}}
      - float: {type, low, high, log?, step?}       → FloatDistribution
      - int:   {type, low, high, log?, step?}       → IntDistribution
      - categorical: {type, choices: [..]}          → CategoricalDistribution
      - fixed: {type, value}                        → 不入 distributions, 合并进每个 trial 的 params

    非法 type / 非法区间由 optuna 构造时抛 ValueError, 调用方 (create_study 校验) 负责转译.
    """
    distributions: dict[str, BaseDistribution] = {}
    fixed_params: dict[str, Any] = {}
    for name, item in search_space.items():
        param_type = item.get("type")
        if param_type == "float":
            distributions[name] = FloatDistribution(
                low=item["low"],
                high=item["high"],
                log=bool(item.get("log", False)),
                step=item.get("step"),
            )
        elif param_type == "int":
            step = item.get("step")
            distributions[name] = IntDistribution(
                low=item["low"],
                high=item["high"],
                log=bool(item.get("log", False)),
                step=int(step) if step is not None else 1,
            )
        elif param_type == "categorical":
            distributions[name] = CategoricalDistribution(choices=item["choices"])
        elif param_type == "fixed":
            fixed_params[name] = item["value"]
        else:
            raise ValueError(f"不支持的搜索空间类型: {param_type}")
    return distributions, fixed_params


async def create_study(study_name: str, direction: str) -> Study:
    """创建 (或 load_if_exists 复用) 一个 RDB 持久化的 optuna study."""
    return await asyncio.to_thread(
        optuna.create_study,
        study_name=study_name,
        storage=get_optuna_storage(),
        direction=direction,
        load_if_exists=True,
    )


async def load_study(study_name: str) -> Study:
    """按名称加载 RDB study (供调度器每次 tick 使用)."""
    return await asyncio.to_thread(optuna.load_study, study_name=study_name, storage=get_optuna_storage())


async def study_ask(study: Study, distributions: dict[str, BaseDistribution]) -> Trial:
    """采样一组超参, 返回已含 ``trial.params``/``trial.number`` 的 Trial."""
    return await asyncio.to_thread(study.ask, distributions)


async def study_trials(study: Study) -> list[Any]:
    """取 study 全部 trial (含运行中/失败/剪枝), to_thread 避免阻塞事件循环."""
    return await asyncio.to_thread(study.get_trials)


async def study_param_importances(study: Study) -> dict[str, float]:
    """超参重要性 (PED-ANOVA, 纯 optuna 无 sklearn 依赖). 完成 trial 不足时 optuna 抛 ValueError → 返回空 dict."""
    try:
        return await asyncio.to_thread(
            optuna.importance.get_param_importances,
            study,
            evaluator=PedAnovaImportanceEvaluator(),
        )
    except ValueError:
        return {}


async def study_tell(
    study: Study,
    trial_number: int,
    value: float | None = None,
    state: TrialState | None = None,
) -> None:
    """回报 trial 结果. 默认 value 非空 → COMPLETE, value=None → FAIL; 传 state 可显式覆盖 (如 PRUNED).

    幂等以 Optuna trial state 为事实来源: reconcile 只对 RUNNING/WAITING 的 trial 调本函数,
    已终态 trial 不进入此路径. 极端竞态下重复 tell 抛 ValueError 由调用方 per-trial 隔离吞掉.
    """
    await asyncio.to_thread(study.tell, trial_number, value, state=state)


async def best_trial(study_name: str) -> dict[str, Any] | None:
    """返回最优 trial {trial_number, value, params}; 尚无完成 trial 时返回 None."""
    study = await load_study(study_name)
    try:
        best = await asyncio.to_thread(lambda: study.best_trial)
    except ValueError:
        return None
    return {"trial_number": best.number, "value": best.value, "params": best.params}


async def delete_study(study_name: str) -> None:
    """删除 RDB 中的 study (连同其 trials)."""
    await asyncio.to_thread(lambda: optuna.delete_study(study_name=study_name, storage=get_optuna_storage()))
