# 知屿 · 本地私有知识库

[English](README.md) · [简体中文](README_zh-CN.md)

<p align="center">
  <img src="docs/assets/desktop.png" alt="知屿桌面界面" width="900">
</p>

一个可以上传 PDF / Word / Markdown / TXT 并基于来源问答的本地 RAG 应用。React 页面、FastAPI API、SQLite 文档元数据、Qdrant 向量索引、BGE-M3、BGE reranker 和本地 OpenAI-compatible LLM 各自独立。

## 对原方案的判断

原方案适合作为个人或小团队的 MVP。无需为了接几个组件先引入整套 Agent 框架，自己掌握检索、重排和引用有助于排错。但完整的可靠服务还需要持久化任务状态、错误恢复、上下文预算、并发限制和测试，这些已补上。

- **8GB 显存**：默认 embedding 和 reranker 放 CPU；GPU 留给量化问答模型。是否够用取决于量化、上下文及其他程序占用，不能只凭“8B”保证。当前机器已装 Qwen3.5 4B / 9B，实际 `.env` 复用 4B 做轻量本机配置；通用 `.env.example` 以 Qwen3 8B 为示例。改模型不需要修改 RAG 代码。
- **来源可信度**：引用元数据来自实际 chunk，并拦截缺失、越界引用编号。但编号正确不等于回答每句话都由原文支持，关键结果仍应核对原文。重排阈值需要在自己的资料上校准。
- **本地运行**：本机没有 Docker，因此先使用 Qdrant 官方客户端的本地持久化模式；Compose 提供独立 Qdrant 服务。两种模式的索引是独立的，切换后需重新导入；不要同时使用同一个 DATA_DIR。
- **第一版范围**：单机、单进程、单用户；扫描件不做 OCR；不做多轮上下文、权限系统、混合检索或复杂 Agent。

官方参考：[BGE-M3](https://huggingface.co/BAAI/bge-m3)、[BGE reranker](https://huggingface.co/BAAI/bge-reranker-v2-m3)、[Qdrant 本地模式](https://github.com/qdrant/qdrant-client)、[Ollama 兼容接口](https://docs.ollama.com/api/openai-compatibility)。

## 本机启动（Windows）

已经完成安装和模型下载的机器，只需要确保 Ollama 已运行，再执行：

```powershell
cd G:\AI\知识库
.\scripts\start.ps1
```

打开 **http://127.0.0.1:8000**，API 文档为 **http://127.0.0.1:8000/docs**。如果端口已被当前后台服务使用，直接打开页面即可，不要重复启动。

首次安装需要 Python 3.12、Node.js 22+、uv 和 Ollama。依赖安装在项目 `.venv` 中：

```powershell
uv sync --python 3.12 --cache-dir .cache/uv
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\download_models.py
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
```

BGE 模型初次下载约 4.5GB，下载器可能同时保留框架权重格式，因此实际空间可更多；中断后再次执行可复用下载缓存。`models/` 是独立模型目录。默认 `MODELS_LOCAL_ONLY=true`，业务运行时不会自动联网下载模型。模型下载访问公共模型仓库，不读取或上传知识库文档。

通用 Qwen3 8B 启动方法：

```powershell
ollama pull qwen3:8b
ollama create knowledge-qwen3:8b -f scripts/Modelfile
.\scripts\start.ps1
```

本机已存在 Qwen3.5 4B 时可复用：

```powershell
ollama create knowledge-qwen35:4b -f scripts/Modelfile.local
# .env: LLM_MODEL=knowledge-qwen35:4b
```

通用 Modelfile 设置 `num_ctx=8192`；本机 `Modelfile.local` 使用 4096、`num_batch=128`，对应 `.env` 设置 `LLM_CONTEXT_TOKENS=4096`、`CHUNK_SIZE=400`、`CHUNK_OVERLAP=60`、`LLM_TIMEOUT_SECONDS=600`，以适应当前机器的内存占用。**修改 `.env` 的 LLM_CONTEXT_TOKENS 只改变应用预算，不能增加模型服务实际的上下文容量**；两处需一致。切换到 9B 可复制 Modelfile，修改 FROM 为本机已有的 `qwen3.5:9b`，创建另一模型名称并更新 `.env`。

默认发送 `LLM_REASONING_EFFORT=none`，通过 Ollama 接口关闭思考输出，避免 Qwen3.5 把输出额度耗在思考过程而未返回答案。仅在 prompt 写 `/no_think` 对当前 Qwen3.5 不足以关闭该模式。其他兼容服务不支持此字段时把该配置留空，并在模型服务中控制思考模式。

Linux/macOS 安装过程相同，Python 路径改为 `.venv/bin/python`，启动执行 `sh scripts/start.sh`。

## CUDA 模式

仓库锁定 CPU PyTorch，适合 embedding/reranker 用 CPU、Ollama 自行使用 GPU 的配置。8GB 显存建议首先保持此配置。

若需要完全用 CPU 推理，可在另一份 Ollama Modelfile 中添加 `PARAMETER num_gpu 0`，创建独立模型名并更新 `LLM_MODEL`；embedding 和 reranker 保持 `cpu`。纯 CPU 的回答速度会明显较慢，需相应增加超时。

如果确实需要 GPU 加速 embedding/reranker，在独立虚拟环境中安装适配驱动的 CUDA PyTorch。当前固定版本可使用 cu126：

```powershell
uv pip install --python .venv\Scripts\python.exe --reinstall torch==2.8.0 --index-url https://download.pytorch.org/whl/cu126
# .env 中按需配置 EMBEDDING_DEVICE=cuda 或 RERANKER_DEVICE=cuda
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
.\scripts\start.ps1
```

CUDA 安装后直接用 `scripts/start.ps1`，避免再运行默认 `uv sync` 将 Torch 换回锁定的 CPU 包。显存不足时恢复 CPU、减小 batch，或卸载 Ollama 中正在运行的模型后建库。本版不提供自动模型卸载/显存调度。

## Docker Compose

需要 Docker Desktop / Docker Engine。前端作为静态资源打包到 backend 镜像，浏览器只访问一个端口。

```powershell
Copy-Item .env.example .env  # 首次创建；已有配置请勿覆盖
docker compose build
docker compose run --rm --no-deps backend .venv/bin/python scripts/download_models.py
docker compose up -d
```

Compose 启动 `backend` 和 `qdrant`，宿主机继续运行 Ollama。只向本机暴露 8000 和 6333 端口。Linux 宿主机上的 Ollama 需能接受 Docker 网桥访问；限制防火墙来源，不应直接把无认证的 Ollama 服务公开到互联网。容器到宿主机连接失败时优先采用本机运行方式。

Compose 默认 CPU embedding/reranker；GPU 示例以本机启动流程为准。当前环境无 Docker，Compose 配置未经过容器运行验收。

## 使用流程

1. 打开页面，上传 `samples/公司测试制度.md`。
2. 文档经过 `uploaded → parsing → indexing → ready`。第一次加载 BGE 模型需要等待。
3. 提问“北京出差的住宿标准是多少？”，应回答每人每晚 600 元，并有可点击的引用。
4. 点击引用，查看文件名、章节、PDF 页码（如有）及原始 chunk。
5. 询问“公司的火星基地地址是什么？”，应回答“知识库中没有找到足够信息”。
6. 左侧点击文档可限定范围；再次点击可取消；“全部文档”恢复搜索整个 ready 文档库。
7. 删除文档会删除上传副本、元数据和向量；不会修改用户最初上传的原始文件。

示例制度是人工测试数据，不代表真实公司政策。聊天记录只保存在当前页面内存中，刷新即清空；每个问题独立检索。

## 架构与文件

```text
上传 → 本地文件 + SQLite → 单个后台 worker
     → 解析段落/标题/页码 → BGE tokenizer 切分 → 分批 BGE-M3 → Qdrant

问题 → 只搜索 ready 文档 → BGE-M3 → Qdrant Top 30
     → BGE reranker → 阈值过滤、最多 Top 5
     → 上下文预算 → 本地 LLM → 引用编号校验 → 回答和真实 chunk 元数据
```

| 文件/目录 | 职责 |
|---|---|
| `backend/app/main.py` | API、生命周期、后台任务装配、静态页面 |
| `config.py` / `schemas.py` / `repository.py` | 配置校验、数据结构、SQLite |
| `parsers.py` / `chunking.py` | PDF/DOCX/MD/TXT 解析及有结构的 token 切分 |
| `services/document_service.py` | 导入队列、重启恢复、失败清理及删除 |
| `services/embedding_service.py` / `reranker_service.py` | 本地模型加载和分批推理 |
| `services/vector_store.py` / `retrieval_service.py` | Qdrant 操作、文档过滤，预留混合检索接口 |
| `services/llm_client.py` / `rag_service.py` | 本地兼容接口、提示词、拒答、来源校验 |
| `frontend/` | React 页面和响应式样式，依赖均打包本地 |
| `tests/` | 使用真实本地 Qdrant、确定性模型替身的自动测试 |
| `scripts/` | 启动、模型下载、真实模型及页面测试 |
| `samples/` | 可复现的测试资料 |

PDF 保留物理页码，DOCX 不编造页码；Word 表格按行解析。切分不跨页或章节，先合并段落，超长段落用 BGE tokenizer 的 offset 切分，默认 800 token / overlap 120。标题提取为启发式，不保证识别所有 PDF 排版。复杂跨页表格和多栏 PDF 需要后续专项优化。

## API

| 方法与路径 | 作用 |
|---|---|
| `POST /api/documents/upload` | multipart 字段 `file`，返回 202 和文档 ID |
| `GET /api/documents` | 文档列表和状态 |
| `GET /api/documents/{id}` | 文档详情、错误信息 |
| `GET /api/documents/{id}/chunks?offset=0&limit=50` | 按 chunk_index 分页查看原文 |
| `POST /api/documents/{id}/retry` | 重新导入失败文档 |
| `DELETE /api/documents/{id}` | 删除文件、元数据和索引 |
| `POST /api/chat` | `{"message":"问题","document_ids":[]}` |
| `GET /api/health` | 本地 LLM 连接、模型配置和 BGE 加载状态 |

空 `document_ids` 搜索所有 ready 文档；非空列表包含不存在的文档返回 404，包含未就绪文档返回 409。空库或没有足够相关内容时跳过 LLM。重排加载失败返回明确错误，不静默降级。

## 配置与运维边界

全部配置见 `.env.example`。模型名称、设备、batch、chunk、Top K、重排阈值、上下文、上传大小及调试开关均可配置。修改模型或切分策略后应创建新 collection 并重新导入，已有向量不会自动更新。

- 默认单 Uvicorn 进程，不要加 `--workers`；本地 Qdrant 路径不允许多进程共享。并发问答返回 429，导入、问答、删除串行使用推理资源，处理大型文档时问答可能排队。
- SQLite 保存状态，重启会重新处理未完成的导入；重复导入前清理该文档旧向量。删除先标记 deleting，清理失败时可重试，重启也会继续。
- 日志保存在 `data/rag.log`，最多 4 × 5MB，记录问题、chunk ID、检索/重排分数、选中 chunk 和耗时。日志包含用户问题，需要按本地私有数据管理。原文不写入普通请求日志。
- `RAG_DEBUG=false` 时 API 不返回 debug；开启后返回当前请求的调试信息。
- 默认仅允许本地/私网模型与向量地址。显式开启 `ALLOW_REMOTE_ENDPOINTS=true` 并配置外部 LLM 后，相关原文片段会发到该地址；此时不再是全本地系统。
- 文件、索引和 SQLite 在 `data/`，模型在 `models/`；备份前停止服务。上传限制默认 25MB，解析限制 200 万字符 / 500 页 PDF。
- 这是本机个人应用，没有登录和部门权限。默认监听 127.0.0.1；不要将此 MVP 直接作为多人公网服务。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend tests scripts
npm.cmd run build --prefix frontend
# 服务启动且模型下载完成后，使用真实 BGE + reranker + Ollama：
.\.venv\Scripts\python.exe scripts/smoke_test.py
```

真实模型测试会保留示例文档，结果保存到 `test-results/real-model-smoke.json`。重复执行会新建另一份示例文档，可在页面删除重复项。

可选页面测试：在已安装 Playwright 的 Python 环境运行 `python scripts/ui_smoke.py --chat`，需要本机 Chrome，验证桌面、手机宽度、聊天及引用弹窗，截图保存到 `test-results/`。

## 下一步最值得改进

1. 用实际文档建立评测集，测召回率、引用支持率、拒答误判率；据此调整阈值、chunk 和模型，避免凭感觉换大模型。
2. 加 BM25 / sparse 的混合召回，提高条款编号、缩写和专有词的命中率。
3. 针对真实 PDF 的多栏、表格和扫描件优化解析；多人使用前再加入身份认证、文档权限与独立任务队列。
