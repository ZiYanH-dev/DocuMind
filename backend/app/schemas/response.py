"""统一响应 Schema。"""

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    """统一 API 响应封装。

    Attributes:
        code: 业务状态码，0 表示成功，非 0 表示业务异常。
        message: 提示信息。
        data: 业务数据负载，类型由泛型参数决定。
    """

    code: int = 0
    message: str = "success"
    data: T | None = None


class DeleteOut(BaseModel):
    """删除操作响应。"""

    id: int
