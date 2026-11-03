# 后端分层落地细则

> 分层总览与调用链见 [../02-architecture.md](../02-architecture.md)。
> 本文只讲每层的落笔约束，以及违反约束时哪条测试会失败。

## 1. 五个层的落笔约束

| 层 | 允许 import 的层 | 允许 import 的第三方 | 典型错误 |
| --- | --- | --- | --- |
| `api` | service、schemas、models、core、config | fastapi | 在路由里直接查库 |
| `service` | repository、models、schemas、core、config、agent、retrieval、utils | 不应有 fastapi | 在 service 里写 `raise HTTPException` |
| `repository` | models、core、config | 不应有 fastapi | 在 repository 里判断业务状态 |
| `models` | config、core | sqlalchemy、pgvector | 在实体里写业务方法 |
| `schemas` | 仅自身 | pydantic | 让 schema 依赖 repository |
| `agent` | agent、schemas、config、core、retrieval、repository、models | langchain、langgraph | 在 tool 里直接抛异常中断图 |
| `retrieval` | retrieval、config、core、repository、models | httpx、jieba、rank-bm25 | 让 retrieval 直接持 Session 参数以外的状态 |
| `core` | core、config、models、repository | redis、fastapi | 在 core 里放业务规则 |
| `config` | 仅自身 | pydantic-settings、pyyaml | 在 config 里写业务逻辑 |
| `utils` | utils、config、schemas、models | pypdf、python-docx、langchain-text-splitters | 在工具函数里查库 |

上表就是 `tests/unit/test_layering.py` 里 `ALLOWED_INTERNAL` 与 `FORBIDDEN_EXTERNAL` 的取值来源。
改分层规则要同时改文档与那张表，两边不一致时以测试为准。

## 2. 一次请求里各层各做什么

以删除文档为例，看职责如何切分：

| 动作 | 所在层 | 具体位置 |
| --- | --- | --- |
| 解析路径参数、注入当前用户 | API | `api/v1/documents.py` `delete_document` |
| 校验文档归属、删文件、删记录、清缓存 | Service | `service/document_service.py` `delete_document` |
| 按用户与 ID 查记录、执行 delete | Repository | `document_repository` |
| 分块随外键级联删除 | Model | `document.py` 的 `ondelete="CASCADE"` |
| 返回 `DeleteOut` | Schema | `schemas/response.py` |

Service 不出现 `select()`，Repository 不出现 `if status == "failed"` 这类判断。

## 3. 事务边界

事务边界固定在 Service。
Repository 的方法各自 `commit()`，Service 在需要跨多次写入时用 `self._db.commit()` 收口。

`chat_service` 是一个典型用例：
- 先取历史再落库提问，避免历史里出现重复的当前提问；
- 保存提问后立刻 `commit()` 并刷新 `updated_at`，让会话置顶生效；
- 回答与引用最后一次性落库。

## 4. 命名与格式

| 项 | 规则 | 例子 |
| --- | --- | --- |
| 类 | PascalCase | `DocumentService`、`ChunkRepository` |
| 函数 / 变量 / 文件 | snake_case | `vector_search`、`chat_service.py` |
| 常量 | UPPER_SNAKE | `HISTORY_LIMIT`、`ALLOWED_FILE_TYPES` |
| 私有成员 | 单下划线 | `self._db`、`_record_hits` |

格式约束：

| 位置 | 空行数 |
| --- | --- |
| 顶层类与类、函数与函数之间 | 2 |
| 类内部方法与方法之间 | 1 |
| docstring 与首行代码之间 | 1 |
| import 块与下方代码之间 | 2 |

## 5. 类型与导入

类型注解：
- 函数参数与返回值必须标注，返回 `None` 也写 `-> None`；
- 空容器、嵌套结构、自定义模型实例必须显式标注；
- 类属性写在类体，实例属性在 `__init__` 里用 `self.xxx` 赋值。

导入：
- 业务代码用绝对导入 `from app.xxx import yyy`；
- 分组顺序为标准库 → 第三方库 → 项目内部，组间空行、组内字母序；
- 仅 `__init__.py` 做导出时允许相对导入。

分组顺序由 `ruff` 的 `I` 规则强制，类型由 `mypy --strict` 强制。

## 6. 已知债务与摘除条件

`test_layering.py` 用 `xfail(strict=True)` 登记两条债务，`strict` 的含义是修好之后测试会报 XPASS 失败，逼着人把标记摘掉。

| 债务 | 现状 | 摘除条件 |
| --- | --- | --- |
| Service 层 import fastapi | `auth`、`document`、`conversation`、`chat` 四个 service 抛 `HTTPException` | 改为抛 `AppError` 子类，并让 `core/exceptions.py` 的 handler 映射状态码 |
| `AppError` 是死代码 | handler 已注册，业务代码无 `raise` | 上一条完成后自然满足，`test_app_error_is_actually_used` 会自动通过 |

改完必须同时把 `KNOWN_DEBT` 标记删掉，否则测试从 xfail 变 XPASS 而失败。
