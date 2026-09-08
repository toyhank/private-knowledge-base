import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  FileText,
  FolderOpen,
  Layers,
  LoaderCircle,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import "./styles.css";

const statuses = {
  uploaded: "等待处理",
  parsing: "解析中",
  indexing: "建立索引",
  ready: "已就绪",
  failed: "导入失败",
  deleting: "删除中",
};
const prompts = [
  "北京出差的住宿标准是多少？",
  "总结文档中的关键规定",
  "不同文档之间有哪些冲突？",
];

async function api(path, options) {
  const response = await fetch(`/api${path}`, options);
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : `请求失败（${response.status}）`,
    );
  return payload;
}

function App() {
  const [docs, setDocs] = useState([]),
    [selected, setSelected] = useState([]);
  const [messages, setMessages] = useState([]),
    [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false);
  const [health, setHealth] = useState(null),
    [error, setError] = useState("");
  const [filter, setFilter] = useState(""),
    [source, setSource] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null),
    [action, setAction] = useState("");
  const [dragging, setDragging] = useState(false),
    [help, setHelp] = useState(false);
  const fileInput = useRef(null),
    bottom = useRef(null),
    input = useRef(null),
    sourceDialog = useRef(null);
  const ready = docs.filter((doc) => doc.status === "ready");
  const active = docs.filter((doc) =>
    ["uploaded", "parsing", "indexing"].includes(doc.status),
  ).length;

  async function refresh() {
    const items = await api("/documents");
    setDocs(items);
    setSelected((current) =>
      current.filter((id) =>
        items.some((doc) => doc.document_id === id && doc.status === "ready"),
      ),
    );
  }
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        if (alive) await refresh();
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    poll();
    const healthPoll = async () => {
      try {
        const status = await api("/health");
        if (alive) setHealth(status);
      } catch {
        if (alive) setHealth(null);
      }
    };
    healthPoll();
    const timer = setInterval(poll, 3000),
      healthTimer = setInterval(healthPoll, 15000);
    return () => {
      alive = false;
      clearInterval(timer);
      clearInterval(healthTimer);
    };
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);
  useEffect(() => {
    if (source && sourceDialog.current) sourceDialog.current.showModal();
  }, [source]);

  async function upload(files) {
    if (!files?.length || uploading) return;
    setUploading(true);
    setError("");
    const errors = [];
    for (const file of Array.from(files)) {
      try {
        const form = new FormData();
        form.append("file", file);
        await api("/documents/upload", { method: "POST", body: form });
      } catch (e) {
        errors.push(`${file.name}：${e.message}`);
      }
    }
    setUploading(false);
    if (fileInput.current) fileInput.current.value = "";
    try {
      await refresh();
    } catch (e) {
      errors.push(e.message);
    }
    setError(errors.join("；"));
  }
  async function remove() {
    const id = deleteTarget.document_id;
    setAction(id);
    setError("");
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      setDeleteTarget(null);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setAction("");
    }
  }
  async function retry(id) {
    setAction(id);
    setError("");
    try {
      await api(`/documents/${id}/retry`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setAction("");
    }
  }
  async function submit(event) {
    event?.preventDefault();
    const text = question.trim();
    if (!text || busy || !ready.length) return;
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setQuestion("");
    setBusy(true);
    setError("");
    setMessages((current) => [
      ...current,
      { role: "user", text, time: timeStr },
    ]);
    const t0 = performance.now();
    try {
      const reply = await api("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, document_ids: selected }),
      });
      const replyDate = new Date();
      const replyTimeStr = replyDate.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      const latencySec =
        typeof reply.latency_ms === "number"
          ? (reply.latency_ms / 1000).toFixed(1)
          : ((performance.now() - t0) / 1000).toFixed(1);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: reply.answer,
          citations: reply.citations,
          time: replyTimeStr,
          latency: `${latencySec}s`,
        },
      ]);
    } catch (e) {
      setMessages((current) => [
        ...current,
        {
          role: "error",
          text: e.message,
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
        },
      ]);
      setQuestion(text);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }
  function toggle(id) {
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );
  }
  function answerText(message) {
    return message.text.split(/(\[\d+\])/g).map((part, i) => {
      const citation = message.citations?.find((c) => `[${c.id}]` === part);
      return citation ? (
        <button
          className="inline-citation"
          key={i}
          onClick={() => setSource(citation)}
          aria-label={`查看引用 ${citation.id}`}
        >
          {part}
        </button>
      ) : (
        part
      );
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-mark">
            <Layers size={23} />
          </span>
          <span>
            知屿<span className="brand-en">LOCAL KNOWLEDGE</span>
          </span>
        </a>
        <div className="workspace-label">
          个人工作空间 <span>本地</span>
        </div>
        <button className="nav-active" onClick={() => input.current?.focus()}>
          <BookOpen size={18} /> 我的知识库 <ChevronRight size={15} />
        </button>
        <div className="library-heading">
          <span>
            文档库 <b>{docs.length}</b>
          </span>
          <button
            className="icon-button"
            aria-label="上传文档"
            onClick={() => fileInput.current.click()}
            disabled={uploading}
          >
            <Plus size={18} />
          </button>
        </div>
        <label className="search">
          <Search size={15} />
          <input
            aria-label="搜索文档"
            placeholder="搜索文档…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </label>
        <button
          className={`all-docs ${!selected.length ? "chosen" : ""}`}
          onClick={() => setSelected([])}
        >
          <FolderOpen size={17} />
          <span>全部文档</span>
          <span>{ready.length}</span>
        </button>
        <div className="document-list">
          {docs
            .filter((doc) =>
              doc.filename.toLowerCase().includes(filter.toLowerCase()),
            )
            .map((doc) => (
              <div
                key={doc.document_id}
                className={`document-row ${selected.includes(doc.document_id) ? "selected" : ""}`}
              >
                <button
                  className="document-select"
                  disabled={doc.status !== "ready"}
                  onClick={() => toggle(doc.document_id)}
                  aria-pressed={selected.includes(doc.document_id)}
                >
                  <span className="file-icon">
                    <FileText size={18} />
                  </span>
                  <span className="document-info">
                    <strong title={doc.filename}>{doc.filename}</strong>
                    <span className={`doc-status ${doc.status}`}>
                      {["uploaded", "parsing", "indexing"].includes(
                        doc.status,
                      ) && <LoaderCircle size={11} className="spin" />}
                      {statuses[doc.status]}
                      {doc.status === "ready" && ` · ${doc.chunk_count} 个片段`}
                    </span>
                  </span>
                  {selected.includes(doc.document_id) && <Check size={14} />}
                </button>
                <button
                  className="icon-button doc-delete"
                  title="删除文档"
                  aria-label={`删除 ${doc.filename}`}
                  disabled={!!action}
                  onClick={() => setDeleteTarget(doc)}
                >
                  <Trash2 size={13} />
                </button>
                {doc.error && (
                  <div className="doc-error">
                    {doc.error}
                    <button
                      onClick={() => retry(doc.document_id)}
                      disabled={!!action}
                    >
                      <RefreshCw size={11} />
                      重试
                    </button>
                  </div>
                )}
              </div>
            ))}
          {!docs.length && (
            <div className="library-empty">
              <FileText size={28} strokeWidth={1.3} />
              <p>还没有文档</p>
              <span>添加资料，开始积累你的知识</span>
            </div>
          )}
          {!!docs.length &&
            !docs.some((doc) =>
              doc.filename.toLowerCase().includes(filter.toLowerCase()),
            ) && <p className="no-match">没有匹配的文档</p>}
        </div>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx,.md,.txt"
          multiple
          hidden
          onChange={(e) => upload(e.target.files)}
        />
        <button
          className={`upload-box ${dragging ? "dragging" : ""}`}
          disabled={uploading}
          onClick={() => fileInput.current.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            upload(e.dataTransfer.files);
          }}
        >
          {uploading ? (
            <LoaderCircle className="spin" size={21} />
          ) : (
            <Upload size={21} />
          )}
          <strong>{uploading ? "正在上传文档…" : "点击上传或拖入文档"}</strong>
          <span>PDF · Word · Markdown · TXT</span>
        </button>
        <div className="privacy">
          <ShieldCheck size={17} />
          <div>
            <strong>知识留在你的设备</strong>
            <span>本地存储 · 本地检索 · 本地回答</span>
          </div>
        </div>
        <div className="sidebar-bottom">
          <span className="avatar">我</span>
          <span>本地工作空间</span>
          <button
            className="icon-button"
            aria-label="使用帮助"
            onClick={() => setHelp(true)}
          >
            <CircleHelp size={17} />
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <span className="breadcrumb">工作空间</span>
            <ChevronRight size={13} />
            <strong>知识问答</strong>
          </div>
          <span
            className={`connection ${health?.llm?.available ? "connected" : ""}`}
          >
            <i />
            {health?.llm?.available
              ? "本地模型已连接"
              : health?.llm?.reachable
                ? "请配置问答模型"
                : "等待本地模型连接"}
          </span>
        </header>
        <div className="chat-toolbar">
          <div>
            <MessageSquare size={19} />
            <h1>与知识对话</h1>
            <span className="small-tag">RAG</span>
          </div>
          <button
            className="text-button"
            onClick={() => setMessages([])}
            disabled={busy || !messages.length}
          >
            <Plus size={16} />
            新对话
          </button>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button aria-label="关闭错误提示" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        <section
          className="chat-content"
          aria-label="聊天记录"
          aria-live="polite"
        >
          {!messages.length ? (
            <div className="welcome">
              <div className="welcome-emblem">
                <BookOpen size={32} strokeWidth={1.45} />
                <span>
                  <Sparkles size={13} />
                </span>
              </div>
              <div className="eyebrow">YOUR KNOWLEDGE, CONNECTED</div>
              <h2>让资料，成为答案。</h2>
              <p>
                从你的文档中找到线索，得到有据可查的回答。
                <br />
                每一处引用，都能回到知识的源头。
              </p>
              <div className="steps">
                <div>
                  <span>01</span>
                  <strong>添加资料</strong>
                  <small>上传你的文档</small>
                </div>
                <ChevronRight size={16} />
                <div>
                  <span>02</span>
                  <strong>提出问题</strong>
                  <small>用自然语言探索</small>
                </div>
                <ChevronRight size={16} />
                <div>
                  <span>03</span>
                  <strong>追溯来源</strong>
                  <small>查看引用与原文</small>
                </div>
              </div>
              <div className="suggestion-heading">可以从这些问题开始</div>
              <div className="suggestions">
                {prompts.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => {
                      setQuestion(prompt);
                      input.current?.focus();
                    }}
                  >
                    {prompt}
                    <ArrowUpRight size={16} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages">
              {messages.map((message, index) => (
                <article key={index} className={`message ${message.role}`}>
                  <div className="message-avatar">
                    {message.role === "user" ? "我" : <Layers size={17} />}
                  </div>
                  <div className="message-body">
                    <div className="message-label">
                      {message.role === "user" ? "你" : "知屿"}
                      {message.role === "assistant" && <span>基于知识库</span>}
                      {message.time && (
                        <span className="message-time">{message.time}</span>
                      )}
                      {message.latency && (
                        <span className="message-latency">耗时 {message.latency}</span>
                      )}
                    </div>
                    <div className="message-text">{answerText(message)}</div>
                    {!!message.citations?.length && (
                      <div className="citations">
                        <div className="citations-label">
                          <BookOpen size={13} />
                          引用来源 · {message.citations.length}
                        </div>
                        {message.citations.map((c) => (
                          <button key={c.id} onClick={() => setSource(c)}>
                            <span className="citation-number">{c.id}</span>
                            <span>
                              <strong>{c.filename}</strong>
                              <small>
                                {[
                                  c.page ? `第 ${c.page} 页` : null,
                                  c.section || "正文片段",
                                ]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </small>
                            </span>
                            <ArrowUpRight size={15} />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
              ))}
              {busy && (
                <div className="thinking">
                  <LoaderCircle size={17} className="spin" />
                  正在检索资料并生成回答…
                  <small>CPU 重排或首次加载模型可能需要一些时间</small>
                </div>
              )}
            </div>
          )}
          <div ref={bottom} />
        </section>
        <footer className="composer-wrap">
          <div className="scope">
            <FolderOpen size={13} />
            {selected.length
              ? `已选择 ${selected.length} 份文档`
              : `检索范围：全部文档（${ready.length}）`}
            {active > 0 && (
              <span>
                <LoaderCircle size={12} className="spin" />
                {active} 份文档正在处理
              </span>
            )}
          </div>
          <form className="composer" onSubmit={submit}>
            <textarea
              ref={input}
              aria-label="输入问题"
              placeholder={
                ready.length
                  ? "向你的知识库提问…"
                  : "先在左侧上传一份文档，再开始提问…"
              }
              value={question}
              maxLength={1000}
              rows={2}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="composer-bottom">
              <span>
                <ShieldCheck size={13} />
                仅使用知识库资料回答
              </span>
              <button
                aria-label="发送问题"
                type="submit"
                disabled={busy || !question.trim() || !ready.length}
              >
                {busy ? (
                  <LoaderCircle size={19} className="spin" />
                ) : (
                  <ArrowUp size={20} />
                )}
              </button>
            </div>
          </form>
          <p className="footer-note">
            回答可能有误，请结合引用原文核实。每条问题独立检索，暂不关联历史对话。
            <span>Enter 发送 · Shift + Enter 换行</span>
          </p>
        </footer>
      </main>

      {source && (
        <dialog
          ref={sourceDialog}
          className="source-dialog"
          onClose={() => setSource(null)}
          onClick={(e) => {
            if (e.target === e.currentTarget) setSource(null);
          }}
        >
          <div className="dialog-header">
            <span>
              <BookOpen size={18} /> 引用原文
            </span>
            <button
              className="icon-button"
              aria-label="关闭引用"
              onClick={() => setSource(null)}
            >
              <X size={20} />
            </button>
          </div>
          <div className="source-body">
            <span className="eyebrow">
              SOURCE {String(source.id).padStart(2, "0")}
            </span>
            <h2>{source.filename}</h2>
            <p className="source-meta">
              {source.page ? `第 ${source.page} 页 · ` : ""}
              {source.section || "正文"} · 片段 {source.chunk_index + 1}
            </p>
            <blockquote>{source.text}</blockquote>
            <p className="source-note">
              <ShieldCheck size={14} />
              此原文片段来自本地检索，来源信息由系统提供。
            </p>
          </div>
        </dialog>
      )}
      {deleteTarget && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="删除文档"
          >
            <h2>删除这份文档？</h2>
            <p>{deleteTarget.filename}</p>
            <p>本地上传副本与检索索引将一并删除。你的原始文件不受影响。</p>
            <div className="modal-actions">
              <button onClick={() => setDeleteTarget(null)} disabled={!!action}>
                取消
              </button>
              <button className="danger" onClick={remove} disabled={!!action}>
                {action ? "正在删除…" : "删除文档"}
              </button>
            </div>
          </section>
        </div>
      )}
      {help && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="使用帮助"
          >
            <h2>开始使用知屿</h2>
            <p>
              上传 PDF、DOCX、Markdown 或
              TXT，等待状态变为「已就绪」，然后在右侧提问。点击文档可限定检索范围，点击引用可核对原文。
            </p>
            <p>
              扫描 PDF 需要先做 OCR。首次导入会加载本地 BGE
              模型，请耐心等待；导入失败可查看原因并重试。
            </p>
            <p>
              问答模型：{health?.llm?.model || "未连接"}
              <br />
              Embedding / Reranker：{health?.devices?.embedding || "cpu"} /{" "}
              {health?.devices?.reranker || "cpu"}
            </p>
            <div className="modal-actions">
              <button onClick={() => setHelp(false)}>知道了</button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
