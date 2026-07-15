from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from app.core.exceptions import BadRequestException

OBJECT_TAGS = {"Image", "Text", "Audio", "Video", "HyperText", "PDF"}
CONTROL_TAGS = {
    "Choices",
    "RectangleLabels",
    "Rectangle",
    "PolygonLabels",
    "Polygon",
    "BrushLabels",
    "Brush",
    "KeyPointLabels",
    "KeyPoint",
    "EllipseLabels",
    "Ellipse",
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
    "Rectangle": "rectangle",
    "PolygonLabels": "polygonlabels",
    "Polygon": "polygon",
    "BrushLabels": "brushlabels",
    "Brush": "brush",
    "KeyPointLabels": "keypointlabels",
    "KeyPoint": "keypoint",
    "EllipseLabels": "ellipselabels",
    "Ellipse": "ellipse",
    "Labels": "labels",
    "TextArea": "textarea",
    "Rating": "rating",
    "Number": "number",
    "Taxonomy": "taxonomy",
}

# Spatial control tags that create geometry regions (no embedded labels)
SPATIAL_BARE_TAGS = {"Rectangle", "Polygon", "KeyPoint", "Ellipse", "Brush"}
# Spatial control tags that include embedded labels
SPATIAL_LABELED_TAGS = {"RectangleLabels", "PolygonLabels", "KeyPointLabels", "EllipseLabels", "BrushLabels"}
# Tags that support perRegion classification
PER_REGION_CAPABLE_TAGS = {"TextArea", "Choices", "Rating", "Number", "Taxonomy"}


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
    per_region: bool = False
    when_label_value: str | None = None
    display_mode: str | None = None


@dataclass(frozen=True)
class LabelConfigInfo:
    objects: list[LabelObject]
    controls: list[LabelControl]


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
                    per_region=elem.attrib.get("perRegion", "").lower() == "true",
                    when_label_value=elem.attrib.get("whenLabelValue"),
                    display_mode=elem.attrib.get("displayMode"),
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
    )


def get_primary_data_object(info: LabelConfigInfo) -> LabelObject:
    first_control = info.controls[0]
    for obj in info.objects:
        if obj.name == first_control.to_name:
            return obj
    return info.objects[0]
