# 文档导航

本目录按「流程骨架 + 子系统纵深」两层组织。
根层放贯穿全流程的文档，子目录放单个子系统的实现细节。

## 1. 流程骨架

| 文档 | 内容 |
| --- | --- |
| [01-requirements.md](./01-requirements.md) | 需求：产品定位、目标用户、用户故事、功能清单、非功能性需求、范围边界 |
| [02-architecture.md](./02-architecture.md) | 架构总览：五层与旁挂模块、目录结构、两条主调用链、质量门禁、已知债务、技术选型 |
| [03-database-design.md](./03-database-design.md) | 数据库：ER 关系、五张表字段与索引、pgvector 约束、级联删除 |
| [04-api.md](./04-api.md) | 接口：总表速查、通用约定、错误码映射、全部接口出入参、SSE 事件格式 |

## 2. 后端纵深

| 文档 | 内容 |
| --- | --- |
| [backend/layering.md](./backend/layering.md) | 每层允许依赖谁、禁止做什么、事务边界、命名与格式、分层债务的摘除条件 |
| [backend/config.md](./backend/config.md) | `.env` 与 `app.yaml` 的三段式分工、加载顺序、分字段推导连接串、缺省复用规则 |
| [backend/testing.md](./backend/testing.md) | 四层测试与 marker、九类替身、关键夹具、环境变量先于导入的约束 |

## 3. AI 纵深

| 文档 | 内容 |
| --- | --- |
| [ai/agent.md](./ai/agent.md) | LangGraph `create_agent` 组装、System Prompt 五条准则、两个工具、按节点过滤 token |
| [ai/retrieval.md](./ai/retrieval.md) | 查询改写 → 双路召回 → RRF 融合 → 百炼重排，开关与退化链、缓存、失败降级 |
| [ai/indexing.md](./ai/indexing.md) | 解析与分块、向量化与入库、三级缓存与失效、换 embedding 模型的代价 |

## 4. 前端与运维

| 文档 | 内容 |
| --- | --- |
| [frontend/design.md](./frontend/design.md) | 技术栈与路由、目录职责、请求层拦截、SSE 原生 fetch 消费、对接要点 |
| [ops/getting-started.md](./ops/getting-started.md) | 环境准备与开发启动：Makefile 一键命令、配置分组、手动分步 |
| [ops/deployment.md](./ops/deployment.md) | 生产部署：Dockerfile + compose.prod + nginx，一条命令起全栈 |

## 5. 阅读顺序

| 目的 | 读什么 |
| --- | --- |
| 了解要做什么 | `01-requirements.md` |
| 理解分层与边界 | `02-architecture.md` → `backend/layering.md` |
| 看 AI 链路怎么跑通 | `ai/agent.md` → `ai/retrieval.md` → `ai/indexing.md` |
| 联调或接前端 | `04-api.md` 与 `03-database-design.md` |
| 改配置或排查启动问题 | `backend/config.md` → `ops/getting-started.md` |
| 写测试或加门禁 | `backend/testing.md` |

## 6. 维护约定

| 约定 | 说明 |
| --- | --- |
| 事实以代码为准 | 文档与代码不一致时改文档，改代码要同步改文档 |
| 一篇一个主题 | 增补内容先找已有文档的对应小节，不另起新文件 |
| 路径写全 | 引用源码写相对 `backend/` 的路径，避免文档搬家后失效 |
| 接口只留一份 | 接口清单与字段定义合并维护在 `04-api.md`，不再拆总表与详情 |
