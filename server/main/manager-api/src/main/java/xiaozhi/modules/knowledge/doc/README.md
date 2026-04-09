# RAGFlow API 接口文档索引 (Unofficial Detailed Guide)

本文档汇集了 RAGFlow 核心模块的 API 详解。所有文档均遵循 **Zero Omissions (无省略)** 原则，全字段展开并包含中文注释。

## 📚 1. 知识库与文档管理 (Knowledge & Documents)
核心的数据管理模块，负责上传文件、解析文档与建立索引。

- **[知识库管理 (Dataset)](./RAGFlow_Dataset接口详解.md)**
  - 涵盖知识库的创建、列表查询、更新、删除等接口。
- **[文档处理 (Document)](./RAGFlow_Document接口详解.md)**
  - 涵盖文档的上传 (Upload)、解析配置更新 (Update)、解析状态查询 (Run Status)。
  - **切片管理**: 解析后的 Chunk 列表查询、增删改查。
  - **检索测试**: 直接对知识库进行召回测试 (Retrieval Test)。
- **[文件管理 (File)](./RAGFlow_File接口详解.md)**
  - 类似网盘的文件操作体系。
  - **CRUD**: 上传、下载、列表。
  - **目录**: 文件夹创建、面包屑导航 (`get_all_parent_folders`)。
  - **操作**: 移动、重命名、删除、导入知识库 (`convert`).

## 💬 2. 聊天助手 (Chat Assistant)
RAGFlow 原生的对话助手体系，基于 Assistant (Dialog) 模型。

- **[会话管理 (Chat Session)](./RAGFlow_Chat_Session接口详解.md)**
  - 管理 `/chats/` 下的会话生命周期。
  - 创建会话、获取历史记录、重命名、批量删除。
- **[对话交互 (Chat Completion)](./RAGFlow_Chat_Completion接口详解.md)**
  - **Core Chat**: 原生流式对话 (`/chats/<id>/completions`), 支持引用 (`quote`)。
  - **OpenAI Compatible**: 完美兼容 OpenAI `/v1/chat/completions` 协议。
  - **Embedded Bot**: 面向 C 端嵌入窗口的对话接口 (`/chatbots/`).

## 🤖 3. Agent 与 机器人 (Agent & Bots)
基于 Graph (DAG) 编排的复杂应用与各类机器人扩展。

- **[Agent 与 Dify 兼容 (Agent & Dify)](./RAGFlow_Agent_Dify接口详解.md)**
  - **Agent Session**: Agent 的会话管理与流式对话 (`agent_completions`)。
  - **Dify Adapter**: 兼容 Dify 协议的检索接口 (`retrieval`).
- **[SearchBot 与 AgentBot](./RAGFlow_SearchBot_AgentBot接口详解.md)**
  - **SearchBot**: 纯搜索机器人，支持思维导图 (`mindmap`)、相关问题 (`related_questions`).
  - **AgentBot**: 嵌入式 Agent，支持前置表单 (`begin_inputs`).
  - **Agent OpenAI**: Agent 的 OpenAI 兼容接口。

## 🛠️ 4. 其他 (Extras)
- **[通用与补充接口 (Session Extras)](./RAGFlow_Session_Extra接口详解.md)**
  - **引用详情**: 获取 SearchBot 引用来源 (`detail_share_embedded`).
  - **通用问答**: 内部调试用的直接问答 (`ask_about`).
