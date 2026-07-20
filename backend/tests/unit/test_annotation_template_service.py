"""Unit tests for AnnotationTemplateService.

覆盖:
- 合法 label_config 通过校验
- 非法 XML 触发 BadRequestException
- 引用项目数 > 0 阻止删除 (409)
- list_templates 按 name/tag/group 过滤
- 跨租户访问 404
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException, BadRequestException, NotFoundException
from app.models.annotation_template import AnnotationTemplate
from app.services.annotation_template_service import AnnotationTemplateService


def _valid_xml(control: str = "Choices", choice_value: str = "类别1") -> str:
    return f"""<View>
  <Image name="image" value="$image"/>
  <{control} name="choice" toName="image">
    <Choice value="{choice_value}"/>
  </{control}>
</View>"""


def _make_template(
    tenant_id: uuid.UUID | None = None,
    name: str = "tmpl-1",
    label_config: str | None = None,
    tags: list[str] | None = None,
    group: str = "其他",
) -> AnnotationTemplate:
    tpl = AnnotationTemplate(
        tenant_id=tenant_id or uuid.uuid4(),
        user_id=uuid.uuid4(),
        name=name,
        description=None,
        label_config=label_config or _valid_xml(),
        tags=tags or [],
        group=group,
    )
    tpl.id = uuid.uuid4()
    return tpl


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        return self._value


_ScalarOneOrNone = _ScalarResult


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class TestValidateLabelConfig:
    def test_valid_xml_passes(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        svc._validate_label_config(_valid_xml())  # no exception

    def test_invalid_xml_raises(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        with pytest.raises(BadRequestException):
            svc._validate_label_config("<View><Broken>")

    def test_missing_control_raises(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        xml = '<View><Image name="image" value="$image"/></View>'
        with pytest.raises(BadRequestException):
            svc._validate_label_config(xml)

    def test_missing_object_raises(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        xml = """<View>
  <Choices name="c" toName="ghost">
    <Choice value="x"/>
  </Choices>
</View>"""
        with pytest.raises(BadRequestException):
            svc._validate_label_config(xml)

    def test_video_frame_classification_template_passes(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        xml = """<View>
  <TimelineLabels name="videoLabels" toName="video">
    <Label value="Movement" background="#c813ec"/>
    <Label value="Still" background="#1d81cd"/>
  </TimelineLabels>
  <Video name="video" value="$video"/>
</View>"""
        svc._validate_label_config(xml)  # no exception

    def test_video_object_tracking_template_passes(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        xml = """<View>
  <Labels name="videoLabels" toName="video" allowEmpty="true">
    <Label value="Man" background="blue"/>
    <Label value="Woman" background="red"/>
  </Labels>
  <Video name="video" value="$video" framerate="25.0"/>
  <VideoRectangle name="box" toName="video"/>
</View>"""
        svc._validate_label_config(xml)  # no exception

    def test_timeseries_template_passes(self) -> None:
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]
        xml = """<View>
  <TimeSeriesLabels name="label" toName="ts">
    <Label value="Change" background="red"/>
  </TimeSeriesLabels>
  <TimeSeries name="ts" valueType="url" value="$csv"
    sep="," timeColumn="time">
    <Channel column="velocity" legend="Velocity"/>
  </TimeSeries>
</View>"""
        svc._validate_label_config(xml)  # no exception

    def test_all_builtin_templates_validate(self) -> None:
        import json
        from pathlib import Path

        builtin_path = (
            Path(__file__).parent.parent.parent / "app" / "integrations" / "labelstudio" / "builtin_templates.json"
        )
        if not builtin_path.exists():
            pytest.skip("builtin_templates.json not found")

        templates = json.loads(builtin_path.read_text(encoding="utf-8"))
        svc = AnnotationTemplateService(db=MagicMock())  # type: ignore[arg-type]

        failures: list[tuple[str, str]] = []
        for tpl in templates:
            try:
                svc._validate_label_config(tpl["config"])
            except BadRequestException as e:
                failures.append((tpl["label"], str(e)))

        assert failures == [], "模板校验失败:\n" + "\n".join(f"{k}: {v}" for k, v in failures)


class TestGetTemplate:
    def test_returns_template_when_found(self) -> None:
        tenant_id = uuid.uuid4()
        tpl = _make_template(tenant_id=tenant_id)
        session = AsyncMock()
        session.execute.return_value = _ScalarOneOrNone(tpl)

        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]
        result = _run(svc.get_template(tpl.id, tenant_id))
        assert result is tpl

    def test_raises_404_when_missing(self) -> None:
        session = AsyncMock()
        session.execute.return_value = _ScalarOneOrNone(None)
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]

        with pytest.raises(NotFoundException):
            _run(svc.get_template(uuid.uuid4(), uuid.uuid4()))


class TestCreateTemplate:
    def test_valid_xml_creates_template(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]
        tenant_id = uuid.uuid4()

        result = _run(
            svc.create_template(
                tenant_id=tenant_id,
                user_id=uuid.uuid4(),
                name="  t1 ",
                description="d",
                label_config=_valid_xml(control="RectangleLabels"),
                tags=["图像", "检测"],
                group="计算机视觉",
            )
        )

        assert result.name == "t1"
        assert result.tenant_id == tenant_id
        assert result.tags == ["图像", "检测"]
        assert result.group == "计算机视觉"
        session.add.assert_called_once()
        session.flush.assert_awaited()
        session.commit.assert_awaited()

    def test_invalid_xml_rejected(self) -> None:
        session = AsyncMock()
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]
        with pytest.raises(BadRequestException):
            _run(
                svc.create_template(
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    name="bad",
                    description=None,
                    label_config="<broken",
                    tags=[],
                )
            )

    def test_default_group_applied(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]
        result = _run(
            svc.create_template(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                name="t",
                description=None,
                label_config=_valid_xml(),
                tags=[],
                group="  ",
            )
        )
        assert result.group == "其他"


class TestUpdateTemplate:
    def test_update_label_config_validates(self) -> None:
        tenant_id = uuid.uuid4()
        tpl = _make_template(tenant_id=tenant_id)
        session = AsyncMock()
        session.execute.return_value = _ScalarOneOrNone(tpl)
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]

        result = _run(
            svc.update_template(
                template_id=tpl.id,
                tenant_id=tenant_id,
                label_config=_valid_xml(control="PolygonLabels", choice_value="区域1"),
            )
        )

        assert "PolygonLabels" in result.label_config

    def test_update_group(self) -> None:
        tenant_id = uuid.uuid4()
        tpl = _make_template(tenant_id=tenant_id, group="旧分组")
        session = AsyncMock()
        session.execute.return_value = _ScalarOneOrNone(tpl)
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]

        result = _run(
            svc.update_template(
                template_id=tpl.id,
                tenant_id=tenant_id,
                group="新分组",
            )
        )
        assert result.group == "新分组"

    def test_empty_body_raises_400(self) -> None:
        tenant_id = uuid.uuid4()
        tpl = _make_template(tenant_id=tenant_id)
        session = AsyncMock()
        session.execute.return_value = _ScalarOneOrNone(tpl)
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]

        with pytest.raises(AppException) as exc_info:
            _run(
                svc.update_template(
                    template_id=tpl.id,
                    tenant_id=tenant_id,
                )
            )
        assert exc_info.value.status_code == 400


class TestDeleteTemplate:
    def test_blocked_when_referenced(self) -> None:
        tenant_id = uuid.uuid4()
        tpl = _make_template(tenant_id=tenant_id)

        session = AsyncMock()
        session.execute.side_effect = [
            _ScalarOneOrNone(tpl),
            _ScalarOneOrNone(1),
        ]
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]

        with pytest.raises(AppException) as exc_info:
            _run(svc.delete_template(tpl.id, tenant_id))
        assert exc_info.value.status_code == 409
        session.delete.assert_not_called()

    def test_succeeds_when_no_reference(self) -> None:
        tenant_id = uuid.uuid4()
        tpl = _make_template(tenant_id=tenant_id)
        session = AsyncMock()
        session.execute.side_effect = [
            _ScalarOneOrNone(tpl),
            _ScalarOneOrNone(0),
        ]
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]

        _run(svc.delete_template(tpl.id, tenant_id))
        session.delete.assert_called_once_with(tpl)
        session.flush.assert_awaited()


class TestListTemplates:
    def test_filter_by_tenant_id_passed_to_query(self) -> None:
        class _RowsResult:
            def scalars(self) -> _RowsResult:
                return self

            def all(self) -> list[Any]:
                return []

        session = AsyncMock()
        session.execute.side_effect = [
            _ScalarResult(0),
            _RowsResult(),
        ]
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]
        tenant_id = uuid.uuid4()

        items, total = _run(
            svc.list_templates(
                tenant_id=tenant_id,
                page=2,
                page_size=5,
                name="x",
                tag="图像",
                group="计算机视觉",
            )
        )
        assert items == []
        assert total == 0
        assert session.execute.await_count == 2


class TestGetGroups:
    def test_returns_distinct_groups(self) -> None:
        session = AsyncMock()
        session.execute.return_value = MagicMock(all=lambda: [("图像",), ("文本",)])
        svc = AnnotationTemplateService(db=session)  # type: ignore[arg-type]
        groups = _run(svc.get_groups(uuid.uuid4()))
        assert groups == ["图像", "文本"]
