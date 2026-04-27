from app.schemas.base import BaseResponse, PageData, PageRequest, PageResponse


def test_base_response_success():
    resp = BaseResponse(data={"key": "value"})
    assert resp.success is True
    assert resp.message == "操作成功"
    assert resp.data == {"key": "value"}


def test_base_response_error():
    resp = BaseResponse(success=False, message="失败", data=None)
    assert resp.success is False
    assert resp.message == "失败"
    assert resp.data is None


def test_page_data():
    pd = PageData(items=[1, 2, 3], total=10, page=1, page_size=3)
    assert len(pd.items) == 3
    assert pd.total == 10


def test_page_response():
    pd = PageData(items=["a", "b"], total=5, page=1, page_size=2)
    resp = PageResponse(data=pd)
    assert resp.success is True
    assert resp.data is not None
    assert resp.data.total == 5


def test_page_request_defaults():
    pr = PageRequest()
    assert pr.page == 1
    assert pr.page_size == 20


def test_page_request_custom():
    pr = PageRequest(page=3, page_size=50)
    assert pr.page == 3
    assert pr.page_size == 50
