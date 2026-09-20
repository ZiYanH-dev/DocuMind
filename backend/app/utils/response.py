"""统一响应工具。"""

from app.schemas.response import ApiResponse


def success(data: object = None, message: str = "success") -> ApiResponse:
    """构造统一成功响应。"""
    return ApiResponse(data=data, message=message)


def error(code: int = 1, message: str = "error", data: object = None) -> ApiResponse:
    """构造统一错误响应（供异常处理器包装为 JSONResponse 时使用）。"""
    return ApiResponse(code=code, message=message, data=data)
