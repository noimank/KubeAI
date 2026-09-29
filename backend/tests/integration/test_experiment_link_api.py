"""实验追踪与训练任务/超参调优的关联暴露验证.

实验追踪已并入训练任务(详情 Tab)与超参调优(trial 对比), 不再有独立页面,
但两个列表接口必须携带 experiment_id 供前端入口判断:
  - GET /api/training-jobs           → 每个任务的 experiment_id
  - GET /api/tuning/studies/{id}/trials → 每个 trial 的 experiment_id
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.enums import TenantStatus, UserRole
from app.models.experiment import Experiment
from app.models.image import Image
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.models.tuning import TuningStudy, TuningTrial
from app.models.user import User


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _get_admin_token(client: AsyncClient) -> str:
    username = _unique("admin")
    email = f"{username}@example.com"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Passw0rd", "confirm_password": "Passw0rd"},
    )
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one()
        user.role = UserRole.ADMIN
        await db.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "Passw0rd"},
    )
    return resp.json()["data"]["access_token"]


@pytest.fixture
def admin_headers(client):
    import asyncio

    token = asyncio.get_event_loop().run_until_complete(_get_admin_token(client))
    return {"Authorization": f"Bearer {token}"}


async def _seed_experiment_scene(client: AsyncClient, admin_headers: dict) -> dict:
    """直建 tenant/用户/镜像/两个训练任务(一个带实验)/调优 study 与 trial, 返回关键 ID."""
    username = _unique("user")
    email = f"{username}@example.com"
    await client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "Passw0rd", "confirm_password": "Passw0rd"},
    )

    async with async_session_factory() as db:
        tenant = Tenant(name=_unique("tenant"), display_name="实验关联测试租户", status=TenantStatus.ACTIVE)
        db.add(tenant)
        await db.flush()

        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one()
        user.role = UserRole.ENGINEER
        user.tenant_id = tenant.id

        image = Image(name=_unique("image"), tag="v1", image_ref="harbor.local/test:v1")
        db.add(image)
        await db.flush()

        def _job(name: str) -> TrainingJob:
            return TrainingJob(
                tenant_id=tenant.id,
                created_by=user.id,
                name=name,
                image_id=image.id,
                command="python train.py",
                gpu_count=1,
                gpu_mode="exclusive",
                cpu="4",
                memory="8Gi",
                priority="normal",
                worker_count=1,
                status="succeeded",
                mlflow_enabled=True,
            )

        job_with_exp = _job(_unique("job"))
        job_plain = _job(_unique("job"))
        db.add_all([job_with_exp, job_plain])
        await db.flush()

        experiment = Experiment(
            tenant_id=tenant.id,
            training_job_id=job_with_exp.id,
            status="completed",
        )
        db.add(experiment)

        study = TuningStudy(
            tenant_id=tenant.id,
            created_by=user.id,
            name=_unique("study"),
            status="completed",
            direction="maximize",
            metric_name="accuracy",
            n_trials=2,
            n_jobs=1,
            search_space={"lr": {"type": "float", "low": 0.01, "high": 0.1}},
            image_id=image.id,
            command="python train.py",
            optuna_study_name=_unique("optuna-study"),
        )
        db.add(study)
        await db.flush()

        db.add_all(
            [
                TuningTrial(
                    study_id=study.id,
                    trial_number=0,
                    training_job_id=job_with_exp.id,
                    params={"lr": 0.1},
                    state="complete",
                    value=0.9,
                ),
                TuningTrial(
                    study_id=study.id,
                    trial_number=1,
                    training_job_id=job_plain.id,
                    params={"lr": 0.2},
                    state="complete",
                    value=0.8,
                ),
            ]
        )
        await db.commit()

        resp = await client.post(
            "/api/auth/login",
            json={"username": username, "password": "Passw0rd"},
        )
        return {
            "token": resp.json()["data"]["access_token"],
            "job_with_exp_id": str(job_with_exp.id),
            "job_plain_id": str(job_plain.id),
            "experiment_id": str(experiment.id),
            "study_id": str(study.id),
        }


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_training_job_list_carries_experiment_id(mock_enforce, client, admin_headers):
    scene = await _seed_experiment_scene(client, admin_headers)
    headers = {"Authorization": f"Bearer {scene['token']}"}

    resp = await client.get("/api/training-jobs", headers=headers)
    assert resp.status_code == 200
    items = {item["id"]: item for item in resp.json()["data"]["items"]}

    assert items[scene["job_with_exp_id"]]["experiment_id"] == scene["experiment_id"]
    assert items[scene["job_plain_id"]]["experiment_id"] is None


@pytest.mark.asyncio(loop_scope="session")
@patch("app.api.deps.CasbinEnforcer.enforce", return_value=True)
async def test_tuning_trials_carry_experiment_id(mock_enforce, client, admin_headers):
    scene = await _seed_experiment_scene(client, admin_headers)
    headers = {"Authorization": f"Bearer {scene['token']}"}

    resp = await client.get(f"/api/tuning/studies/{scene['study_id']}/trials", headers=headers)
    assert resp.status_code == 200
    trials = sorted(resp.json()["data"], key=lambda t: t["trial_number"])

    assert len(trials) == 2
    assert trials[0]["experiment_id"] == scene["experiment_id"]
    assert trials[1]["experiment_id"] is None
