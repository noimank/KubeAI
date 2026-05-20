from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import BadRequestException

COMMUNITY_LABEL_CONFIG_PRESETS: dict[str, dict[str, str]] = {
    "image_choices": {
        "key": "image_choices",
        "label": "图像分类",
        "description": "基于 Label Studio Choices 控件的图像分类配置，可按业务类别修改 Choice。",  # noqa: RUF001
        "config": """<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image" choice="single-radio">
    <Choice value="类别1"/>
    <Choice value="类别2"/>
  </Choices>
</View>""",
    },
    "object_detection": {
        "key": "object_detection",
        "label": "目标检测",
        "description": "基于 Label Studio RectangleLabels 控件的图像矩形框标注配置。",
        "config": """<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="目标1" background="#1677FF"/>
    <Label value="目标2" background="#52C41A"/>
  </RectangleLabels>
</View>""",
    },
    "image_segmentation": {
        "key": "image_segmentation",
        "label": "图像分割",
        "description": "基于 Label Studio PolygonLabels 控件的图像多边形标注配置。",
        "config": """<View>
  <Image name="image" value="$image"/>
  <PolygonLabels name="label" toName="image">
    <Label value="区域1" background="#1677FF"/>
    <Label value="区域2" background="#52C41A"/>
  </PolygonLabels>
</View>""",
    },
    "text_choices": {
        "key": "text_choices",
        "label": "文本分类",
        "description": "基于 Label Studio Text + Choices 控件的文本分类配置。",
        "config": """<View>
  <Text name="text" value="$text"/>
  <Choices name="sentiment" toName="text" choice="single-radio">
    <Choice value="正面"/>
    <Choice value="负面"/>
    <Choice value="中性"/>
  </Choices>
</View>""",
    },
}

LABELING_TEMPLATES = COMMUNITY_LABEL_CONFIG_PRESETS

OBJECT_TAGS = {"Image", "Text", "Audio", "Video", "HyperText", "PDF"}
CONTROL_TAGS = {
    "Choices",
    "RectangleLabels",
    "PolygonLabels",
    "BrushLabels",
    "KeyPointLabels",
    "Labels",
    "TextArea",
    "Rating",
    "Number",
    "Taxonomy",
}
URL_OBJECT_TAGS = {"Image", "Audio", "Video", "PDF"}
TEXT_OBJECT_TAGS = {"Text", "HyperText"}
CONTROL_TYPE_BY_TAG = {
    "Choices": "choices",
    "RectangleLabels": "rectanglelabels",
    "PolygonLabels": "polygonlabels",
    "BrushLabels": "brushlabels",
    "KeyPointLabels": "keypointlabels",
    "Labels": "labels",
    "TextArea": "textarea",
    "Rating": "rating",
    "Number": "number",
    "Taxonomy": "taxonomy",
}


@dataclass(frozen=True)
class LabelObject:
    tag: str
    name: str
    field: str


@dataclass(frozen=True)
class LabelChoice:
    value: str
    background: str | None = None


@dataclass(frozen=True)
class LabelControl:
    tag: str
    name: str
    to_name: str
    control_type: str
    choices: list[LabelChoice]
    choice_mode: str | None = None


@dataclass(frozen=True)
class LabelConfigInfo:
    objects: list[LabelObject]
    controls: list[LabelControl]
    annotation_type: str


def _field_from_value(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"\$([A-Za-z_][\w.-]*)", value.strip())
    return match.group(1) if match else None


def parse_label_config(label_config: str) -> LabelConfigInfo:
    try:
        root = ET.fromstring(label_config)
    except ET.ParseError as exc:
        raise BadRequestException(f"Label Studio 标注配置 XML 无效: {exc}") from exc

    objects: list[LabelObject] = []
    object_names: set[str] = set()
    controls: list[LabelControl] = []

    for elem in root.iter():
        if elem.tag in OBJECT_TAGS:
            name = elem.attrib.get("name", "").strip()
            field = _field_from_value(elem.attrib.get("value"))
            if name and field:
                objects.append(LabelObject(tag=elem.tag, name=name, field=field))
                object_names.add(name)
        if elem.tag in CONTROL_TAGS:
            name = elem.attrib.get("name", "").strip()
            to_name = elem.attrib.get("toName", "").strip()
            if not name or not to_name:
                continue
            choices = [
                LabelChoice(value=child.attrib["value"], background=child.attrib.get("background"))
                for child in elem
                if child.tag in {"Choice", "Label"} and child.attrib.get("value")
            ]
            controls.append(
                LabelControl(
                    tag=elem.tag,
                    name=name,
                    to_name=to_name,
                    control_type=CONTROL_TYPE_BY_TAG[elem.tag],
                    choices=choices,
                    choice_mode=elem.attrib.get("choice"),
                )
            )

    if not objects:
        raise BadRequestException("Label Studio 配置必须包含 Image/Text/Audio/Video/HyperText/PDF 数据标签")
    if not controls:
        raise BadRequestException("Label Studio 配置必须包含至少一个标注控件")

    unsupported_targets = [control.to_name for control in controls if control.to_name not in object_names]
    if unsupported_targets:
        raise BadRequestException(f"标注控件引用的数据标签不存在: {', '.join(unsupported_targets)}")

    return LabelConfigInfo(
        objects=objects,
        controls=controls,
        annotation_type=controls[0].control_type,
    )


def get_primary_data_object(info: LabelConfigInfo) -> LabelObject:
    first_control = info.controls[0]
    for obj in info.objects:
        if obj.name == first_control.to_name:
            return obj
    return info.objects[0]


def get_annotation_result_template(annotation_type: str) -> dict[str, Any]:
    templates: dict[str, dict[str, Any]] = {
        "image_classification": {
            "from_name": "choice",
            "to_name": "image",
            "type": "choices",
            "value_key": "choices",
        },
        "text_classification": {
            "from_name": "sentiment",
            "to_name": "text",
            "type": "choices",
            "value_key": "choices",
        },
        "object_detection": {
            "type": "rectanglelabels",
            "value_keys": ["x", "y", "width", "height", "rectanglelabels"],
        },
        "image_segmentation": {"type": "polygonlabels", "value_keys": ["points", "polygonlabels"]},
        "choices": {"type": "choices", "value_key": "choices"},
        "rectanglelabels": {"type": "rectanglelabels", "value_keys": ["x", "y", "width", "height", "rectanglelabels"]},
        "polygonlabels": {"type": "polygonlabels", "value_keys": ["points", "polygonlabels"]},
        "textarea": {"type": "textarea", "value_key": "text"},
        "rating": {"type": "rating", "value_key": "rating"},
        "number": {"type": "number", "value_key": "number"},
        "taxonomy": {"type": "taxonomy", "value_key": "taxonomy"},
    }
    return templates.get(annotation_type, {})
