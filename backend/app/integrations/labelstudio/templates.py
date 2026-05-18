LABELING_TEMPLATES: dict[str, dict[str, str]] = {
    "image_classification": {
        "key": "image_classification",
        "label": "图像分类",
        "description": "单选或多选标签对图像进行分类，适用于猫狗识别、情感分析等场景",  # noqa: RUF001
        "config": """<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image" choice="single-radio">
    <Choice value="类别1"/>
    <Choice value="类别2"/>
    <Choice value="类别3"/>
  </Choices>
</View>""",
    },
    "object_detection": {
        "key": "object_detection",
        "label": "目标检测",
        "description": "使用矩形框标注图像中的目标位置和类别，适用于车辆检测、行人检测等场景",  # noqa: RUF001
        "config": """<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="目标1" background="#FF0000"/>
    <Label value="目标2" background="#00FF00"/>
  </RectangleLabels>
</View>""",
    },
    "image_segmentation": {
        "key": "image_segmentation",
        "label": "图像分割",
        "description": "使用多边形精确标注图像中的目标区域边界，适用于医学影像、遥感分析等场景",  # noqa: RUF001
        "config": """<View>
  <Image name="image" value="$image"/>
  <PolygonLabels name="label" toName="image">
    <Label value="区域1" background="#FF0000"/>
    <Label value="区域2" background="#00FF00"/>
  </PolygonLabels>
</View>""",
    },
    "text_classification": {
        "key": "text_classification",
        "label": "文本分类",
        "description": "对文本内容进行分类或命名实体识别，适用于情感分析、意图识别、实体抽取等场景",  # noqa: RUF001
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
