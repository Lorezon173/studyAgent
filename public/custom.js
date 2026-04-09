(() => {
  const CONFIG = {
    uploadEndpoint:
      window.localStorage.getItem("LA_KB_UPLOAD_ENDPOINT") ||
      "http://127.0.0.1:1900/api/knowledge_base/upload",
    tokenStorageKeys: ["LA_ADMIN_JWT", "access_token", "token", "jwt", "Authorization"],
  };

  const STATE = {
    modalOpen: false,
    mounted: false,
    sidebarOpen: true,
    sessionItems: [],
    selectedSessionId: "",
    topic: "",
  };

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const parseSessionLine = (line) => {
    const match = line.match(/^-\s+`([^`]+)`\s+stage=(.+)$/);
    if (!match) return null;
    return { session_id: match[1].trim(), stage: match[2].trim() };
  };

  const parseSessionLabel = (line) => {
    // e.g. "线代 [summary] (web-123abc)"
    const idxL = line.lastIndexOf("(");
    const idxR = line.lastIndexOf(")");
    if (idxL < 0 || idxR <= idxL) return null;
    const sid = line.slice(idxL + 1, idxR).trim();
    const text = line.slice(0, idxL).trim();
    const stageL = text.lastIndexOf("[");
    const stageR = text.lastIndexOf("]");
    if (stageL < 0 || stageR <= stageL) {
      return { session_id: sid, topic: text || "未命名主题", stage: "unknown" };
    }
    return {
      session_id: sid,
      topic: text.slice(0, stageL).trim() || "未命名主题",
      stage: text.slice(stageL + 1, stageR).trim() || "unknown",
    };
  };

  const getCurrentTopicFromSettings = () => {
    const input = document.querySelector('input[placeholder="输入主题并保存"]');
    if (!input) return "";
    return (input.value || "").trim();
  };

  const sendCommand = (command) => {
    const composer = document.querySelector("textarea");
    if (!composer) return false;
    composer.value = command;
    composer.dispatchEvent(new Event("input", { bubbles: true }));
    const submit =
      document.querySelector('button[data-testid="send-button"]') ||
      Array.from(document.querySelectorAll("button")).find(
        (el) =>
          el.getAttribute("aria-label")?.includes("Send") ||
          el.getAttribute("aria-label")?.includes("发送")
      );
    if (!submit) return false;
    submit.click();
    return true;
  };

  const readSessionsFromDom = () => {
    // 优先从会话下拉读取（由后端 _sync_sidebar_settings 注入）
    const select = document.querySelector('select[id="active_session_id"]');
    if (select?.options?.length) {
      const list = Array.from(select.options)
        .map((opt) => {
          const parsed = parseSessionLabel(opt.textContent || "");
          if (!parsed) return null;
          return { ...parsed, session_id: opt.value || parsed.session_id };
        })
        .filter(Boolean);
      STATE.sessionItems = list;
      STATE.selectedSessionId = select.value || STATE.selectedSessionId;
      return;
    }

    // 兜底：解析最近一条 “会话列表” 助手消息
    const messages = Array.from(document.querySelectorAll('[data-testid="message-content"]'));
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const text = messages[i].innerText || "";
      if (!text.includes("会话列表：")) continue;
      const lines = text.split("\n");
      const start = lines.findIndex((x) => x.includes("会话列表："));
      const items = lines.slice(start + 1).map(parseSessionLine).filter(Boolean);
      if (items.length) {
        STATE.sessionItems = items.map((x) => ({ ...x, topic: x.session_id }));
        return;
      }
    }
  };

  const applySidebarVisibility = () => {
    const panel = document.getElementById("la-left-sidebar");
    const toggle = document.getElementById("la-left-sidebar-toggle");
    if (!panel || !toggle) return;
    panel.style.transform = STATE.sidebarOpen ? "translateX(0)" : "translateX(-268px)";
    toggle.style.left = STATE.sidebarOpen ? "272px" : "8px";
    toggle.textContent = STATE.sidebarOpen ? "隐藏" : "显示";
  };

  const renderSessionList = () => {
    const box = document.getElementById("la-session-list");
    if (!box) return;
    const items = STATE.sessionItems || [];
    if (!items.length) {
      box.innerHTML = '<div style="padding:8px;color:#6b7280;font-size:12px;">暂无历史会话</div>';
      return;
    }
    box.innerHTML = items
      .map((s) => {
        const sid = escapeHtml(s.session_id);
        const topic = escapeHtml(s.topic || s.session_id);
        const stage = escapeHtml(s.stage || "unknown");
        const active = s.session_id === STATE.selectedSessionId;
        return `<button type="button" data-session-id="${sid}" style="width:100%;text-align:left;padding:8px 10px;border:1px solid ${
          active ? "#2563eb" : "#e5e7eb"
        };border-radius:8px;background:${active ? "#eff6ff" : "#fff"};cursor:pointer;margin-bottom:8px;">
            <div style="font-size:13px;color:#111827;line-height:1.3;">${topic}</div>
            <div style="font-size:11px;color:#6b7280;line-height:1.3;margin-top:2px;">${stage} · ${sid}</div>
          </button>`;
      })
      .join("");

    box.querySelectorAll("button[data-session-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sid = btn.getAttribute("data-session-id");
        if (!sid) return;
        STATE.selectedSessionId = sid;
        renderSessionList();
        sendCommand(`/use ${sid}`);
      });
    });
  };

  const refreshSidebarState = () => {
    STATE.topic = getCurrentTopicFromSettings();
    readSessionsFromDom();
    renderSessionList();
  };

  const ensureLeftSidebar = () => {
    if (document.getElementById("la-left-sidebar")) return;

    const panel = document.createElement("aside");
    panel.id = "la-left-sidebar";
    panel.style.cssText =
      "position:fixed;left:0;top:0;bottom:0;width:260px;z-index:9999;background:#ffffff;border-right:1px solid #e5e7eb;padding:12px;box-sizing:border-box;overflow:auto;transition:transform .2s ease;";

    panel.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
        <div style="font-size:14px;font-weight:600;color:#111827;">会话管理</div>
      </div>
      <button id="la-new-session-btn" type="button" style="width:100%;padding:8px 10px;border:1px solid #2563eb;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer;font-size:13px;">新建会话</button>
      <button id="la-kb-create-btn-left" type="button" style="width:100%;padding:8px 10px;border:1px solid #3b82f6;border-radius:8px;background:#fff;color:#2563eb;cursor:pointer;font-size:13px;margin-top:8px;">知识库创建</button>
      <div style="margin-top:12px;font-size:12px;color:#6b7280;">历史会话</div>
      <div id="la-session-list" style="margin-top:8px;"></div>
    `;
    document.body.appendChild(panel);

    const toggle = document.createElement("button");
    toggle.id = "la-left-sidebar-toggle";
    toggle.type = "button";
    toggle.style.cssText =
      "position:fixed;top:14px;left:272px;z-index:10000;padding:6px 10px;border:1px solid #d1d5db;border-radius:8px;background:#fff;color:#111827;cursor:pointer;font-size:12px;transition:left .2s ease;";
    toggle.textContent = "隐藏";
    toggle.addEventListener("click", () => {
      STATE.sidebarOpen = !STATE.sidebarOpen;
      applySidebarVisibility();
    });
    document.body.appendChild(toggle);

    const newSessionBtn = document.getElementById("la-new-session-btn");
    if (newSessionBtn) {
      newSessionBtn.addEventListener("click", () => {
        sendCommand("/newsession");
      });
    }

    const kbBtn = document.getElementById("la-kb-create-btn-left");
    if (kbBtn) {
      kbBtn.addEventListener("click", openUploadModal);
    }

    applySidebarVisibility();
    refreshSidebarState();
  };

  const getToken = () => {
    for (const key of CONFIG.tokenStorageKeys) {
      const value = window.localStorage.getItem(key);
      if (value && value.trim()) {
        return value.replace(/^Bearer\s+/i, "").trim();
      }
    }
    return "";
  };

  const bindComposerBehavior = () => {
    const composer = document.querySelector("textarea");
    if (!composer) return;
    if (composer.dataset.learningAgentBound === "1") return;
    composer.dataset.learningAgentBound = "1";
    composer.setAttribute("placeholder", "回车发送，Alt+Enter 换行");

    composer.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || !event.altKey) return;
      event.preventDefault();

      const start = composer.selectionStart ?? composer.value.length;
      const end = composer.selectionEnd ?? composer.value.length;
      const next = `${composer.value.slice(0, start)}\n${composer.value.slice(end)}`;
      composer.value = next;
      composer.selectionStart = composer.selectionEnd = start + 1;
      composer.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };

  const ensureUploadButton = () => {
    // 兼容旧逻辑：已迁移到左侧栏，保留函数避免调用链报错
  };

  const closeModal = () => {
    const modal = document.getElementById("la-kb-upload-modal");
    if (modal) modal.remove();
    STATE.modalOpen = false;
  };

  const makeRow = (labelText, inputEl) => {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;flex-direction:column;gap:6px;margin-bottom:10px;";
    const label = document.createElement("label");
    label.textContent = labelText;
    label.style.cssText = "font-size:13px;color:#111827;";
    row.appendChild(label);
    row.appendChild(inputEl);
    return row;
  };

  const renderResult = (container, result) => {
    const line = document.createElement("div");
    line.style.cssText =
      "padding:8px 10px;border-radius:6px;font-size:12px;margin-top:6px;background:#f3f4f6;color:#111827;word-break:break-word;";
    line.textContent = result;
    container.appendChild(line);
  };

  const openUploadModal = () => {
    if (STATE.modalOpen) return;
    STATE.modalOpen = true;

    const overlay = document.createElement("div");
    overlay.id = "la-kb-upload-modal";
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;";

    const panel = document.createElement("div");
    panel.style.cssText =
      "width:min(680px,94vw);max-height:86vh;overflow:auto;background:#fff;border-radius:12px;padding:16px 16px 14px;box-shadow:0 10px 30px rgba(0,0,0,.2);";

    const title = document.createElement("div");
    title.textContent = "创建本地知识库（直连 FastAPI）";
    title.style.cssText = "font-size:16px;font-weight:600;margin-bottom:10px;";
    panel.appendChild(title);

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    fileInput.style.cssText = "padding:6px;";
    panel.appendChild(makeRow("选择文件（支持多文件）", fileInput));

    const topicInput = document.createElement("input");
    topicInput.type = "text";
    topicInput.placeholder = "如：图论基础";
    topicInput.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    panel.appendChild(makeRow("主题 Topic", topicInput));

    const scopeSelect = document.createElement("select");
    scopeSelect.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    scopeSelect.innerHTML = `<option value="personal">personal</option><option value="global">global</option>`;
    panel.appendChild(makeRow("Scope", scopeSelect));

    const titleInput = document.createElement("input");
    titleInput.type = "text";
    titleInput.placeholder = "可选，不填默认文件名";
    titleInput.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    panel.appendChild(makeRow("标题 Title（可选）", titleInput));

    const userIdInput = document.createElement("input");
    userIdInput.type = "number";
    userIdInput.placeholder = "personal 时建议填写";
    userIdInput.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    panel.appendChild(makeRow("User ID（可选）", userIdInput));

    const chunkSizeInput = document.createElement("input");
    chunkSizeInput.type = "number";
    chunkSizeInput.placeholder = "500";
    chunkSizeInput.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    panel.appendChild(makeRow("Chunk Size（可选）", chunkSizeInput));

    const chunkOverlapInput = document.createElement("input");
    chunkOverlapInput.type = "number";
    chunkOverlapInput.placeholder = "100";
    chunkOverlapInput.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    panel.appendChild(makeRow("Chunk Overlap（可选）", chunkOverlapInput));

    const endpointInput = document.createElement("input");
    endpointInput.type = "text";
    endpointInput.value = CONFIG.uploadEndpoint;
    endpointInput.style.cssText = "padding:8px;border:1px solid #d1d5db;border-radius:8px;";
    panel.appendChild(makeRow("上传接口 Endpoint", endpointInput));

    const resultBox = document.createElement("div");
    resultBox.style.cssText =
      "margin-top:10px;border:1px dashed #d1d5db;border-radius:8px;padding:10px;min-height:40px;background:#fafafa;";
    resultBox.textContent = "等待上传...";
    panel.appendChild(resultBox);

    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:12px;";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "关闭";
    cancelBtn.style.cssText =
      "padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;background:#fff;cursor:pointer;";
    cancelBtn.addEventListener("click", closeModal);

    const submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.textContent = "开始上传";
    submitBtn.style.cssText =
      "padding:8px 12px;border:1px solid #2563eb;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer;";
    submitBtn.addEventListener("click", async () => {
      const files = Array.from(fileInput.files || []);
      if (!files.length) {
        resultBox.textContent = "请先选择至少一个文件。";
        return;
      }

      CONFIG.uploadEndpoint = endpointInput.value.trim() || CONFIG.uploadEndpoint;
      window.localStorage.setItem("LA_KB_UPLOAD_ENDPOINT", CONFIG.uploadEndpoint);
      resultBox.innerHTML = "";
      submitBtn.disabled = true;
      submitBtn.textContent = "上传中...";

      const token = getToken();
      let success = 0;
      let failed = 0;

      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        form.append("scope", scopeSelect.value);
        if (topicInput.value.trim()) form.append("topic", topicInput.value.trim());
        if (titleInput.value.trim()) form.append("title", titleInput.value.trim());
        if (userIdInput.value.trim()) form.append("user_id", userIdInput.value.trim());
        if (chunkSizeInput.value.trim()) form.append("chunk_size", chunkSizeInput.value.trim());
        if (chunkOverlapInput.value.trim()) form.append("chunk_overlap", chunkOverlapInput.value.trim());

        const headers = {};
        if (token) headers.Authorization = `Bearer ${token}`;

        try {
          const resp = await fetch(CONFIG.uploadEndpoint, {
            method: "POST",
            headers,
            body: form,
            credentials: "include",
          });
          const text = await resp.text();
          let body = null;
          try {
            body = text ? JSON.parse(text) : null;
          } catch (_) {
            body = { raw: text };
          }

          if (!resp.ok) {
            failed += 1;
            renderResult(
              resultBox,
              `❌ ${file.name} 上传失败 [${resp.status}] ${
                (body && (body.message || body.detail || body.error)) || "未知错误"
              }`
            );
            continue;
          }

          success += 1;
          renderResult(
            resultBox,
            `✅ ${file.name} 上传成功 | item_id=${body?.item_id || "-"} | inserted_chunks=${
              body?.inserted_chunks ?? "-"
            }`
          );
        } catch (error) {
          failed += 1;
          renderResult(resultBox, `❌ ${file.name} 上传异常: ${error?.message || error}`);
        }
      }

      renderResult(resultBox, `完成：成功 ${success}，失败 ${failed}`);
      submitBtn.disabled = false;
      submitBtn.textContent = "开始上传";
    });

    actions.appendChild(cancelBtn);
    actions.appendChild(submitBtn);
    panel.appendChild(actions);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
  };

  const mount = () => {
    if (STATE.mounted) return;
    STATE.mounted = true;
    bindComposerBehavior();
    ensureLeftSidebar();
    ensureUploadButton();
    refreshSidebarState();
  };

  const observer = new MutationObserver(() => {
    bindComposerBehavior();
    ensureLeftSidebar();
    ensureUploadButton();
    refreshSidebarState();
  });
  observer.observe(document.body, { childList: true, subtree: true });
  mount();
})();
