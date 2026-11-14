/**
 * Main Application Controller for Citely
 */

const App = (() => {
  let pollingInterval = null;
  // How often to check that this browser's files still exist on the server.
  const FILE_SYNC_INTERVAL_MS = 5 * 60 * 1000;
  let isSendingQuery = false;

  function init() {
    State.init();
    applyTheme(State.isDark);

    // Subscribe to state updates
    State.subscribe(onStateChange);

    // Initial renders
    renderCurrentTab();
    renderFiles();
    renderActiveFileHeader();
    renderChatMessages();

    // Setup polling for pending/processing files
    startPollingIfNeeded();

    // Synchronize known files from backend (refresh live statuses)
    refreshFilesFromBackend();
    setInterval(refreshFilesFromBackend, FILE_SYNC_INTERVAL_MS);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refreshFilesFromBackend();
    });

    // Check backend connection
    checkBackendHealth();
  }

  function applyTheme(isDark) {
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }

  function onStateChange(event, payload, data) {
    if (event === "theme_change") {
      applyTheme(payload);
    } else if (event === "tab_change") {
      renderCurrentTab();
    } else if (event === "files_update") {
      renderFiles();
      renderActiveFileHeader();
      startPollingIfNeeded();
    } else if (event === "chat_update") {
      renderChatMessages();
    }
  }

  // Polling mechanism to track document processing status until ready/failed
  function startPollingIfNeeded() {
    if (State.hasUnfinishedProcessing()) {
      if (!pollingInterval) {
        pollingInterval = setInterval(async () => {
          let hasPending = false;
          for (const f of State.files) {
            if (f.status === "pending" || f.status === "processing") {
              hasPending = true;
              try {
                const updated = await Api.getFile(f.id);
                State.addOrUpdateFile(updated);
              } catch (e) {
                if (e.status === 404) State.removeFile(f.id);
                else console.warn(`Could not poll file ${f.id}:`, e);
              }
            }
          }
          if (!hasPending && pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
          }
        }, 2000);
      }
    } else if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  }

  async function refreshFilesFromBackend() {
    try {
      const files = await Api.getFiles();
      if (Array.isArray(files)) {
        State.setFiles(files);
      }
    } catch (e) {
      for (const f of State.files) {
        try {
          const updated = await Api.getFile(f.id);
          State.addOrUpdateFile(updated);
        } catch (err) {
          if (err.status === 404) {
            State.removeFile(f.id);
          }
        }
      }
    }
  }

  async function checkBackendHealth() {
    const pill = document.getElementById("backend-status-pill");
    if (!pill) return;
    const res = await Api.testConnection();
    if (res.ok) {
      pill.innerHTML = `<span class="w-2 h-2 rounded-full bg-green-500"></span><span class="text-xs font-medium text-slate-600 dark:text-slate-300">API Connected</span>`;
    } else {
      pill.innerHTML = `<span class="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span><span class="text-xs font-medium text-red-600 dark:text-red-400">API Offline</span>`;
    }
  }

  // Tab navigation
  function setTab(tabName) {
    State.setActiveTab(tabName);
  }

  function renderCurrentTab() {
    const activeTab = State.activeTab;
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      const tab = btn.dataset.tab;
      if (tab === activeTab) {
        btn.classList.add("active", "border-indigo-600", "text-indigo-600", "dark:text-indigo-400");
        btn.classList.remove("border-transparent", "text-slate-500", "dark:text-slate-400");
      } else {
        btn.classList.remove("active", "border-indigo-600", "text-indigo-600", "dark:text-indigo-400");
        btn.classList.add("border-transparent", "text-slate-500", "dark:text-slate-400");
      }
    });

    document.querySelectorAll(".tab-pane").forEach((pane) => {
      if (pane.id === `tab-pane-${activeTab}`) {
        pane.classList.remove("hidden");
      } else {
        pane.classList.add("hidden");
      }
    });
  }

  // Active File Header for Chat
  function renderActiveFileHeader() {
    const header = document.getElementById("active-file-banner");
    if (!header) return;

    const files = State.files;
    const readyFiles = State.readyFiles;

    if (files.length === 0) {
      header.innerHTML = `
        <div class="flex items-center justify-between p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-800 dark:text-amber-200 text-xs">
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            <span>No documents uploaded yet. Upload your PDF documents in the <strong>Documents</strong> tab to begin multi-document chat.</span>
          </div>
          <button onclick="App.setTab('files')" class="px-3 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white font-medium text-xs shadow-sm transition-colors shrink-0">
            Upload Documents
          </button>
        </div>
      `;
      const queryInput = document.getElementById("query-input");
      const sendBtn = document.getElementById("send-btn");
      if (queryInput && sendBtn) {
        queryInput.disabled = true;
        queryInput.placeholder = "Upload documents to begin asking questions...";
        sendBtn.disabled = true;
      }
      return;
    }

    const isReady = readyFiles.length > 0;
    const filePills = files
      .map(
        (f) =>
          `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-medium text-[11px] ${f.status === "ready"
            ? "bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
            : "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
          }">
            📄 ${Components.escapeHtml(f.original_filename)}
            <span class="text-[9px] opacity-75">(${f.status})</span>
          </span>`
      )
      .join("");

    header.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-2 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 text-xs">
        <div class="flex items-center gap-2.5 overflow-hidden flex-1 min-w-[240px]">
          <span class="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 font-bold shrink-0">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>
            </svg>
          </span>
          <div class="truncate flex-1">
            <div class="font-bold text-slate-800 dark:text-slate-100 mb-1">
              Multi-Document Knowledge Base (${readyFiles.length}/${files.length} ready)
            </div>
            <div class="flex flex-wrap gap-1">
              ${filePills}
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <button onclick="App.setTab('files')" class="py-1 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 font-medium transition-colors">
            Manage Documents
          </button>
        </div>
      </div>
    `;

    // Enable/disable query input based on readiness
    const queryInput = document.getElementById("query-input");
    const sendBtn = document.getElementById("send-btn");
    if (queryInput && sendBtn) {
      if (!isReady) {
        queryInput.disabled = true;
        queryInput.placeholder = `Documents are processing... Please wait until at least one document is Ready.`;
        sendBtn.disabled = true;
      } else {
        queryInput.disabled = false;
        queryInput.placeholder = `Ask anything across your ${readyFiles.length} document(s) (relational concepts, comparisons, synthesis)...`;
        sendBtn.disabled = false;
      }
    }
  }

  // Render Documents List
  function renderFiles() {
    const container = document.getElementById("files-grid");
    const countBadge = document.getElementById("file-count-badge");
    const files = State.files;

    if (countBadge) countBadge.textContent = files.length.toString();
    if (!container) return;

    if (files.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-slate-400 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-2xl bg-white/50 dark:bg-slate-900/30">
          <svg class="mx-auto h-12 w-12 text-slate-300 dark:text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
          </svg>
          <p class="mt-2 text-sm font-semibold text-slate-700 dark:text-slate-300">No documents uploaded yet</p>
          <p class="text-xs text-slate-400 mt-0.5">Drag and drop a PDF, DOCX, or Markdown file above</p>
        </div>
      `;
      return;
    }

    const batches = Components.groupFilesIntoBatches(files);
    container.innerHTML = batches
      .map((batch) => Components.renderBatchCard(batch, false))
      .join("");
  }

  // Render Chat Messages
  function renderChatMessages() {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    const messages = State.getActiveChatHistory();
    const readyFiles = State.readyFiles;

    if (messages.length === 0) {
      container.innerHTML = `
        <div class="h-full flex flex-col items-center justify-center p-8 text-center text-slate-400">
          <div class="w-16 h-16 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mb-4 shadow-inner">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
            </svg>
          </div>
          <h3 class="text-base font-bold text-slate-700 dark:text-slate-200 mb-1">
            ${readyFiles.length > 0 ? `Multi-Document Q&A Chat (${readyFiles.length} document${readyFiles.length > 1 ? "s" : ""} ready)` : "Start by uploading documents"}
          </h3>
          <p class="text-xs text-slate-400 max-w-sm mb-6">
            Answers are synthesized across all your uploaded documents with exact citations, filename, and page numbers.
          </p>

          ${readyFiles.length > 0
          ? `
            <div class="flex flex-wrap justify-center gap-2 max-w-lg">
              <button onclick="App.suggestQuestion('Summarize the key points across the documents')" class="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-600 dark:text-slate-300 transition-colors shadow-sm">
                💡 "Summarize key points across documents"
              </button>
              <button onclick="App.suggestQuestion('Compare and contrast the findings between the documents')" class="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-600 dark:text-slate-300 transition-colors shadow-sm">
                💡 "Compare and contrast findings"
              </button>
              <button onclick="App.suggestQuestion('What are the common themes or differences discussed?')" class="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-600 dark:text-slate-300 transition-colors shadow-sm">
                💡 "Common themes or differences"
              </button>
            </div>
          `
          : `
            <button onclick="App.setTab('files')" class="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-sm transition-colors">
              Upload Documents Now
            </button>
          `
        }
        </div>
      `;
      return;
    }

    container.innerHTML = messages.map(Components.renderChatMessage).join("");
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
  }

  // Suggest Question click handler
  function suggestQuestion(text) {
    const input = document.getElementById("query-input");
    if (input) {
      input.value = text;
      input.focus();
    }
  }

  // Handle Asking a Question
  async function submitQuery() {
    if (isSendingQuery) return;
    const readyFiles = State.readyFiles;
    if (readyFiles.length === 0) {
      alert("Please upload documents and wait until at least one document is ready!");
      setTab("files");
      return;
    }

    const input = document.getElementById("query-input");
    const question = (input.value || "").trim();
    if (!question) return;

    // Reset input
    input.value = "";
    input.style.height = "auto";

    // Last 3 question/answer turns, taken before this question is added, so the
    // backend can understand follow-ups like "how do they compare?". Error
    // messages are skipped; long answers are cut (the backend cuts them again).
    const history = State.getActiveChatHistory()
      .filter((m) => !(m.sender === "assistant" && (m.text || "").startsWith("**Error:**")))
      .slice(-6)
      .map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: (m.text || "").slice(0, 300),
      }));

    // Add user message to state
    State.addChatMessage({
      sender: "user",
      text: question,
    });

    isSendingQuery = true;
    const sendBtn = document.getElementById("send-btn");
    if (sendBtn) sendBtn.disabled = true;

    // Render loading indicator in chat
    const container = document.getElementById("chat-messages");
    const loadingElem = document.createElement("div");
    loadingElem.id = "chat-loading-indicator";
    loadingElem.className = "flex items-start gap-3 mb-6 animate-pulse-subtle";
    loadingElem.innerHTML = `
      <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-500 text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-sm">
        AI
      </div>
      <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-4 shadow-sm text-sm text-slate-500 dark:text-slate-400 flex items-center gap-2">
        <span>Searching across ${readyFiles.length} document(s) and synthesizing answer</span>
        <span class="inline-flex"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></span>
      </div>
    `;
    container.appendChild(loadingElem);
    container.scrollTop = container.scrollHeight;

    const startTime = performance.now();
    try {
      // Query across all uploaded documents in the workspace (fileId = null)
      const result = await Api.askQuestion(null, question, history);
      const durationMs = Math.round(performance.now() - startTime);

      let telemetry = `${durationMs}ms`;
      if (result.answer_source === "web") {
        const webCount = result.web_sources ? result.web_sources.length : 0;
        telemetry += ` · 🌐 Web Search (${webCount} link${webCount === 1 ? "" : "s"})`;
      } else if (result.answer_source === "llm") {
        telemetry += ` · 🤖 General AI Knowledge`;
      } else if (result.sources && result.sources.length > 0) {
        telemetry += ` · 📄 Multi-Document Grounded (${result.sources.length} sources, Top: ${(result.sources[0].score * 100).toFixed(0)}%)`;
      }

      // Remove loading indicator
      const loader = document.getElementById("chat-loading-indicator");
      if (loader) loader.remove();

      // Add assistant message to state
      State.addChatMessage({
        sender: "assistant",
        text: result.answer,
        answer_source: result.answer_source || "document",
        sources: result.sources || [],
        web_sources: result.web_sources || [],
        telemetry,
      });
    } catch (err) {
      const loader = document.getElementById("chat-loading-indicator");
      if (loader) loader.remove();

      State.addChatMessage({
        sender: "assistant",
        text: `**Error:** ${err.message}`,
        sources: [],
      });
    } finally {
      isSendingQuery = false;
      if (sendBtn) sendBtn.disabled = false;
      if (input) input.focus();
    }
  }

  // Upload file handler
  async function handleFileUpload(files) {
    if (!files || files.length === 0) return;
    const fileList = Array.from(files);

    // Show progress modal or banner
    const uploadStatus = document.getElementById("upload-status");
    if (uploadStatus) {
      uploadStatus.classList.remove("hidden");
      uploadStatus.innerHTML = `
        <div class="flex items-center gap-2 text-indigo-600 dark:text-indigo-400 text-xs font-semibold">
          <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span>Uploading ${fileList.length} document(s)...</span>
        </div>
      `;
    }

    let successCount = 0;
    let lastError = null;
    const batchId = "batch_" + Date.now();

    try {
      const records = await Api.uploadFiles(fileList);
      for (const record of records) {
        State.addOrUpdateFile({ ...record, batch_id: batchId });
        successCount++;
      }
    } catch (err) {
      // Fallback to uploading individually if bulk fails
      for (const file of fileList) {
        try {
          const record = await Api.uploadFile(file);
          State.addOrUpdateFile({ ...record, batch_id: batchId });
          successCount++;
        } catch (individualErr) {
          lastError = individualErr;
        }
      }
    }

    if (uploadStatus) {
      if (successCount > 0) {
        uploadStatus.innerHTML = `
          <div class="text-green-600 dark:text-green-400 text-xs font-semibold">
            ✓ Uploaded ${successCount} document(s)! Ingestion in progress...
          </div>
        `;
        setTimeout(() => uploadStatus.classList.add("hidden"), 3000);
      } else if (lastError) {
        uploadStatus.innerHTML = `
          <div class="text-red-500 text-xs font-semibold">
            Failed to upload: ${Components.escapeHtml(lastError.message)}
          </div>
        `;
        setTimeout(() => uploadStatus.classList.add("hidden"), 5000);
      }
    }
  }

  // Go to chat
  function selectFile(fileId) {
    setTab("chat");
  }

  // Download file
  async function downloadFile(fileId, filename) {
    try {
      await Api.downloadFile(fileId, filename);
    } catch (err) {
      alert("Could not download file: " + err.message);
    }
  }

  // Delete file
  async function deleteFile(fileId) {
    const file = State.files.find((f) => f.id === fileId);
    const filename = file ? file.original_filename : "this file";
    if (!confirm(`Are you sure you want to delete "${filename}" and all its vector chunks?`)) {
      return;
    }

    try {
      await Api.deleteFile(fileId);
      State.removeFile(fileId);
    } catch (err) {
      alert("Could not delete file: " + err.message);
    }
  }

  // Delete all files in a batch
  async function deleteBatch(fileIds) {
    if (!Array.isArray(fileIds) || fileIds.length === 0) return;
    if (!confirm(`Are you sure you want to delete these ${fileIds.length} documents and all their vector chunks?`)) {
      return;
    }

    for (const fileId of fileIds) {
      try {
        await Api.deleteFile(fileId);
        State.removeFile(fileId);
      } catch (err) {
        console.warn(`Could not delete file ${fileId}:`, err);
      }
    }
  }

  // Scroll to source card and highlight
  function scrollToSource(number) {
    const details = document.querySelectorAll(".source-card");
    // Ensure parent details tag is opened
    document.querySelectorAll("details").forEach((d) => (d.open = true));

    for (const card of details) {
      if (card.id.endsWith(`-${number}`)) {
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.add("source-highlight");
        setTimeout(() => card.classList.remove("source-highlight"), 2500);
        break;
      }
    }
  }

  // Load Performance Data
  async function loadPerformanceData() {
    const summaryContainer = document.getElementById("performance-summary-container");
    const runsContainer = document.getElementById("performance-runs-container");

    if (summaryContainer) {
      summaryContainer.innerHTML = '<div class="py-4 text-xs text-slate-400">Loading KPI metrics...</div>';
    }
    if (runsContainer) {
      runsContainer.innerHTML = '<div class="py-8 text-xs text-slate-400 text-center">Loading run telemetry...</div>';
    }

    try {
      const summary = await Api.getPerformanceSummary();
      if (summaryContainer) {
        summaryContainer.innerHTML = Components.renderPerformanceSummary(summary);
      }

      const operation = State.activeRunFilter === "all" ? null : State.activeRunFilter;
      const runs = await Api.getPerformanceRuns({ operation, limit: 50 });
      if (runsContainer) {
        runsContainer.innerHTML = Components.renderPerformanceRunsTable(runs);
      }
    } catch (err) {
      if (summaryContainer) {
        summaryContainer.innerHTML = `<div class="p-4 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 rounded-lg text-xs">
          Performance metrics route not yet reachable. Make sure the database migration 0002 has been applied.
        </div>`;
      }
      if (runsContainer) runsContainer.innerHTML = "";
    }
  }

  // Settings modal
  function openSettings() {
    const modal = document.getElementById("settings-modal");
    const input = document.getElementById("settings-base-url");
    if (input) input.value = Api.getBaseUrl();
    if (modal) modal.classList.remove("hidden");
  }

  function closeSettings() {
    const modal = document.getElementById("settings-modal");
    if (modal) modal.classList.add("hidden");
  }

  function saveSettings() {
    const input = document.getElementById("settings-base-url");
    if (input) {
      Api.setBaseUrl(input.value.trim());
      checkBackendHealth();
    }
    closeSettings();
  }

  function resetSettings() {
    const input = document.getElementById("settings-base-url");
    const defaultUrl = Api.resetBaseUrl();
    if (input) input.value = defaultUrl;
    checkBackendHealth();
    closeSettings();
  }

  return {
    init,
    setTab,
    selectFile,
    downloadFile,
    deleteFile,
    deleteBatch,
    suggestQuestion,
    submitQuery,
    handleFileUpload,
    scrollToSource,
    loadPerformanceData,
    openSettings,
    closeSettings,
    saveSettings,
    resetSettings,
  };
})();

// Initialize on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  App.init();

  // Drag and drop file listeners
  const dropzone = document.getElementById("file-dropzone");
  const fileInput = document.getElementById("file-input");

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
      App.handleFileUpload(e.target.files);
      fileInput.value = "";
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add("border-indigo-500", "bg-indigo-50/50", "dark:bg-indigo-950/30");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove("border-indigo-500", "bg-indigo-50/50", "dark:bg-indigo-950/30");
      });
    });

    dropzone.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files) {
        App.handleFileUpload(e.dataTransfer.files);
      }
    });
  }

  // Auto-resize textarea for query input
  const queryInput = document.getElementById("query-input");
  if (queryInput) {
    queryInput.addEventListener("input", function () {
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 180) + "px";
    });

    queryInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        App.submitQuery();
      }
    });
  }

  // Send button listener
  const sendBtn = document.getElementById("send-btn");
  if (sendBtn) {
    sendBtn.addEventListener("click", () => App.submitQuery());
  }

  // Clear chat listener
  const clearChatBtn = document.getElementById("clear-chat-btn");
  if (clearChatBtn) {
    clearChatBtn.addEventListener("click", () => {
      if (confirm("Clear conversation history?")) {
        State.clearChat();
      }
    });
  }

  // Theme toggle
  const themeToggleBtn = document.getElementById("theme-toggle-btn");
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => State.toggleTheme());
  }
});

