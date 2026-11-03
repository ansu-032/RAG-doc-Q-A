/**
 * Main Application Controller for RAG Document Q&A
 */

const App = (() => {
  let pollingInterval = null;
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
      if (payload === "performance") {
        loadPerformanceData();
      }
    } else if (event === "files_update") {
      renderFiles();
      renderActiveFileHeader();
      startPollingIfNeeded();
    } else if (event === "active_file_change") {
      renderFiles();
      renderActiveFileHeader();
      renderChatMessages();
    } else if (event === "chat_update") {
      if (payload.fileId === State.activeFileId) {
        renderChatMessages();
      }
    } else if (event === "filter_change") {
      loadPerformanceData();
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
                console.warn(`Could not poll file ${f.id}:`, e);
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
    for (const f of State.files) {
      try {
        const updated = await Api.getFile(f.id);
        State.addOrUpdateFile(updated);
      } catch (e) {
        // If file 404s, user might have deleted it outside or DB was wiped
        if (e.status === 404) {
          console.warn(`File ${f.id} no longer exists on server`);
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
    const activeFile = State.activeFile;

    if (!header) return;

    if (!activeFile) {
      header.innerHTML = `
        <div class="flex items-center justify-between p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-800 dark:text-amber-200 text-xs">
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            <span>No document selected. Upload or select a document in the <strong>Documents</strong> tab to begin asking questions.</span>
          </div>
          <button onclick="App.setTab('files')" class="px-3 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white font-medium text-xs shadow-sm transition-colors shrink-0">
            Select Document
          </button>
        </div>
      `;
      return;
    }

    const isReady = activeFile.status === "ready";
    header.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-2 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 text-xs">
        <div class="flex items-center gap-2.5 overflow-hidden">
          <span class="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 font-bold shrink-0">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
          </span>
          <div class="truncate">
            <div class="font-bold text-slate-800 dark:text-slate-100 truncate">${Components.escapeHtml(activeFile.original_filename)}</div>
            <div class="text-[11px] text-slate-400 flex items-center gap-2">
              <span>${Components.formatBytes(activeFile.size_bytes)}</span>
              <span>•</span>
              <span>${activeFile.chunk_count ?? 0} chunks</span>
              <span>•</span>
              <span>${activeFile.page_count ? activeFile.page_count + " pages" : "No page limit"}</span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          ${Components.renderStatusBadge(activeFile.status)}
          <button onclick="App.setTab('files')" class="py-1 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 font-medium transition-colors">
            Switch Document
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
        queryInput.placeholder = `Document is ${activeFile.status}... Please wait until it is Ready.`;
        sendBtn.disabled = true;
      } else {
        queryInput.disabled = false;
        queryInput.placeholder = `Ask anything about ${activeFile.original_filename}... (Shift+Enter for newline)`;
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

    container.innerHTML = files
      .map((f) => Components.renderFileCard(f, f.id === State.activeFileId))
      .join("");
  }

  // Render Chat Messages
  function renderChatMessages() {
    const container = document.getElementById("chat-messages");
    if (!container) return;

    const messages = State.getActiveChatHistory();
    const activeFile = State.activeFile;

    if (messages.length === 0) {
      container.innerHTML = `
        <div class="h-full flex flex-col items-center justify-center p-8 text-center text-slate-400">
          <div class="w-16 h-16 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mb-4 shadow-inner">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
            </svg>
          </div>
          <h3 class="text-base font-bold text-slate-700 dark:text-slate-200 mb-1">
            ${activeFile ? `Ask questions about ${activeFile.original_filename}` : "Start by selecting a document"}
          </h3>
          <p class="text-xs text-slate-400 max-w-sm mb-6">
            Answers are grounded directly in your document with exact source citations and zero hallucination.
          </p>

          ${
            activeFile && activeFile.status === "ready"
              ? `
            <div class="flex flex-wrap justify-center gap-2 max-w-lg">
              <button onclick="App.suggestQuestion('Summarize the main points of this document')" class="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-600 dark:text-slate-300 transition-colors shadow-sm">
                💡 "Summarize the main points"
              </button>
              <button onclick="App.suggestQuestion('What are the key conclusions and takeaways?')" class="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-600 dark:text-slate-300 transition-colors shadow-sm">
                💡 "What are the key conclusions?"
              </button>
              <button onclick="App.suggestQuestion('List all important figures, numbers and statistics mentioned')" class="text-xs px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-600 dark:text-slate-300 transition-colors shadow-sm">
                💡 "List important figures and numbers"
              </button>
            </div>
          `
              : ""
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
    const activeFile = State.activeFile;
    if (!activeFile) {
      alert("Please select a document first!");
      setTab("files");
      return;
    }
    if (activeFile.status !== "ready") {
      alert(`This document is ${activeFile.status}. Please wait until it is ready.`);
      return;
    }

    const input = document.getElementById("query-input");
    const question = (input.value || "").trim();
    if (!question) return;

    // Reset input
    input.value = "";
    input.style.height = "auto";

    // Add user message to state
    State.addChatMessage(activeFile.id, {
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
        <span>Searching document and generating grounded answer</span>
        <span class="inline-flex"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></span>
      </div>
    `;
    container.appendChild(loadingElem);
    container.scrollTop = container.scrollHeight;

    const startTime = performance.now();
    try {
      const result = await Api.askQuestion(activeFile.id, question);
      const durationMs = Math.round(performance.now() - startTime);

      let telemetry = `${durationMs}ms`;
      if (result.answer_source === "web") {
        const webCount = result.web_sources ? result.web_sources.length : 0;
        telemetry += ` · 🌐 Web Search (${webCount} link${webCount === 1 ? "" : "s"})`;
      } else if (result.answer_source === "llm") {
        telemetry += ` · 🤖 General AI Knowledge`;
      } else if (result.sources && result.sources.length > 0) {
        telemetry += ` · 📄 Document Grounded (${result.sources.length} sources, Top: ${(result.sources[0].score * 100).toFixed(0)}%)`;
      }

      // Remove loading indicator
      const loader = document.getElementById("chat-loading-indicator");
      if (loader) loader.remove();

      // Add assistant message to state
      State.addChatMessage(activeFile.id, {
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

      State.addChatMessage(activeFile.id, {
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
    const file = files[0];

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
          <span>Uploading and hashing ${Components.escapeHtml(file.name)}...</span>
        </div>
      `;
    }

    try {
      const record = await Api.uploadFile(file);
      State.addOrUpdateFile(record);
      State.setActiveFile(record.id);

      if (uploadStatus) {
        uploadStatus.innerHTML = `
          <div class="text-green-600 dark:text-green-400 text-xs font-semibold">
            ✓ Uploaded! Extraction &amp; embedding pipeline in progress...
          </div>
        `;
        setTimeout(() => uploadStatus.classList.add("hidden"), 3000);
      }
    } catch (err) {
      if (uploadStatus) {
        uploadStatus.innerHTML = `
          <div class="text-red-500 text-xs font-semibold">
            Failed to upload: ${Components.escapeHtml(err.message)}
          </div>
        `;
        setTimeout(() => uploadStatus.classList.add("hidden"), 5000);
      }
    }
  }

  // Select a file
  function selectFile(fileId) {
    State.setActiveFile(fileId);
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

  return {
    init,
    setTab,
    selectFile,
    downloadFile,
    deleteFile,
    suggestQuestion,
    submitQuery,
    handleFileUpload,
    scrollToSource,
    loadPerformanceData,
    openSettings,
    closeSettings,
    saveSettings,
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
      if (confirm("Clear chat history for this document?")) {
        State.clearChat(State.activeFileId);
      }
    });
  }

  // Theme toggle
  const themeToggleBtn = document.getElementById("theme-toggle-btn");
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => State.toggleTheme());
  }
});

