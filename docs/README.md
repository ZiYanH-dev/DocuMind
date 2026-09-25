# 文档导航

本目录收录 DocuMind 的设计与开发文档，按"需求 → 数据库 → 接口 → 架构 → 前端"流程组织。

| 文档 | 内容 |
| --- | --- |
| [requirements.md](./requirements.md) | 需求文档：产品定位、目标用户、用户故事、功能清单、非功能性需求、范围边界 |
| [database-design.md](./database-design.md) | 数据库表设计：ER 关系、五张表字段/约束/索引、pgvector 向量检索与级联删除 |
| [api-reference.md](./api-reference.md) | 接口一览（总表）：按模块分类的全部接口速查表 |
| [api-spec.md](./api-spec.md) | API 接口规范：通用约定（鉴权 / 统一响应 / 错误）、全部接口请求响应、SSE 事件格式、状态码 |
| [architecture.md](./architecture.md) | 架构与分层规范：五层调用、目录结构、调用链、编码规范 Checklist、关键技术点 |
| [frontend-design.md](./frontend-design.md) | 前端 UI 设计：页面路由、核心交互、SSE 消费、原型线框、目录建议、对接要点 |
| [getting-started.md](./getting-started.md) | 环境准备与开发启动：Makefile 一键命令、配置分组（.env 接入 / app.yaml 超参）、手动分步 |
| [deployment.md](./deployment.md) | 生产部署：Dockerfile + compose.prod + nginx，一条命令起全栈 |

> 说明：根目录 `README.md`（项目级总览）计划在项目完成后统一编写，开发启动见 [`getting-started.md`](./getting-started.md)，生产部署见 [`deployment.md`](./deployment.md)。

## 阅读顺序建议

1. 先看 `requirements.md` 了解要做什么；
2. 再看 `architecture.md` 理解分层与规范约束；
3. 联调 / 接前端时查 `api-spec.md` 与 `database-design.md`；
4. 前端开发阶段参考 `frontend-design.md`。
