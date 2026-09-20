"""统一异常处理。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


class AppError(Exception):
    """应用自定义异常。"""

    def __init__(self, code: int, message: str, status_code: int = 400) -> None:
        self.code: int = code
        self.message: str = message
        self.status_code: int = status_code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(AppError)
    async def handle_app_error(_, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(_, exc: RequestValidationError) -> JSONResponse:
        errors: list[dict] = []
        for error in exc.errors():
            errors.append(
                {
                    "field": ".".join(str(loc) for loc in error["loc"]),
                    "message": error["msg"],
                }
            )
        return JSONResponse(
            status_code=422,
            content={
                "code": 1001,
                "message": "请求参数校验失败",
                "data": errors,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_exception(_, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": 2001,
                "message": f"数据库操作异常: {str(exc)}",
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": 9999,
                "message": f"服务器内部错误: {str(exc)}",
                "data": None,
            },
        )
