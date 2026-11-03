/**
 * Component renderers for RAG Document Q&A
 */

const Components = (() => {
  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatBytes(bytes, decimals = 1) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  }

  function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoStr;
    }
  }

  function renderStatusBadge(status) {
    const s = (status || "unknown").toLowerCase();
    switch (s) {
      case "ready":
        return `<span class="badge-ready inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold">
          <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span> Ready
        </span>`;
      case "processing":
        return `<span class="badge-processing inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold animate-pulse-subtle">
          <svg class="animate-spin -ml-0.5 mr-1 h-3 w-3 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Processing
        </span>`;
      case "pending":
        return `<span class="badge-pending inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold">
          <span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span> In Queue
        </span>`;
      case "failed":
        return `<span class="badge-failed inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold">
          <span class="w-1.5 h-1.5 rounded-full bg-red-500"></span> Failed
        </span>`;
      default:
        return `<span class="bg-gray-100 text-gray-700 px-2.5 py-0.5 rounded-full text-xs font-medium">${escapeHtml(status)}</span>`;
    }
  }

  /**
   * Lightweight, robust Markdown to HTML converter
   * Converts citations [1], [2] to clickable badges!
   */
  function renderMarkdown(text) {
    if (!text) return "";

    let html = escapeHtml(text);

    // Code blocks ```code```
    html = html.replace(/```([\s\S]*?)```/g, (match, code) => {
      return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Inline code `code`
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Bold **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    // Italic *text*
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Headings ### Header
    html = html.replace(/^### (.*$)/gim, '<h3 class="text-base font-bold mt-3 mb-1">$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2 class="text-lg font-bold mt-4 mb-2">$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>');

    // Unordered lists (- or *)
    html = html.replace(/^\s*[-*]\s+(.+)$/gim, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>)/gms, "<ul>$1</ul>");

    // Blockquotes > quote
    html = html.replace(/^\> (.*$)/gim, "<blockquote>$1</blockquote>");

    // Convert double line breaks to paragraphs
    const paragraphs = html.split(/\n{2,}/);
    html = paragraphs
      .map((p) => {
        p = p.trim();
        if (!p) return "";
        if (p.startsWith("<pre>") || p.startsWith("<ul>") || p.startsWith("<h")) {
          return p;
        }
        return `<p>${p.replace(/\n/g, "<br/>")}</p>`;
      })
      .join("");

    // Convert citations like [1], [2], [1][2] into interactive badges
    html = html.replace(/\[(\d+)\]/g, (match, num) => {
      return `<button type="button" class="citation-badge" onclick="App.scrollToSource(${num})" title="View source evidence #${num}">[${num}]</button>`;
    });

    return html;
  }

  /**
   * Render source cards for Q&A answer evidence
   */
  function renderSourcesList(sources, messageId) {
    if (!sources || sources.length === 0) return "";

    return `
      <div class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800">
        <details class="group">
          <summary class="flex items-center justify-between cursor-pointer text-xs font-semibold text-indigo-600 dark:text-indigo-400 select-none">
            <span class="flex items-center gap-1.5">
              <svg class="w-4 h-4 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
              Grounded Sources &amp; Evidence (${sources.length})
              Grounded Document Sources (${sources.length})
            </span>
            <span class="text-[11px] text-slate-400 font-normal">Click to expand chunks</span>
          </summary>
          
          <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2.5">
            ${sources
        .map(
          (src) => `
              <div id="src-${messageId}-${src.number}" class="source-card p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/60 text-xs text-slate-700 dark:text-slate-300 transition-all">
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-bold text-indigo-600 dark:text-indigo-400 flex items-center gap-1">
                    <span class="px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-950 text-[10px]">#${src.number}</span>
                    Chunk ${src.chunk_index}
                  </span>
                  <span class="text-[11px] font-medium px-2 py-0.5 rounded-full ${src.score >= 0.7
              ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
              : "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
            }">
                    Score: ${(src.score * 100).toFixed(1)}%
                  </span>
                </div>
                <p class="font-mono text-[11px] leading-relaxed line-clamp-4 hover:line-clamp-none transition-all cursor-text select-all bg-white dark:bg-slate-950 p-2 rounded border border-slate-100 dark:border-slate-800/80">
                  ${escapeHtml(src.content)}
                </p>
              </div>
            `
        )
        .join("")}
          </div>
        </details>
      </div>
    `;
  }

  /**
   * Render web search sources when falling back to the general model
   */
  function renderWebSourcesList(webSources, messageId) {
    if (!webSources || webSources.length === 0) return "";

    return `
      <div class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800">
        <details class="group" open>
          <summary class="flex items-center justify-between cursor-pointer text-xs font-semibold text-blue-600 dark:text-blue-400 select-none">
            <span class="flex items-center gap-1.5">
              <svg class="w-4 h-4 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
              </svg>
              Referenced Web Sources (${webSources.length})
            </span>
            <span class="text-[11px] text-slate-400 font-normal">Live search results</span>
          </summary>
          
          <div class="mt-2.5 space-y-2">
            ${webSources
        .map(
          (src, i) => `
              <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="flex items-center justify-between p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/60 hover:bg-blue-50/60 dark:hover:bg-blue-950/30 hover:border-blue-300 dark:hover:border-blue-800 text-xs transition-colors group/link">
                <div class="flex items-center gap-2 overflow-hidden">
                  <span class="w-5 h-5 rounded bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 flex items-center justify-center text-[10px] font-bold shrink-0">
                    ${i + 1}
                  </span>
                  <div class="truncate">
                    <span class="font-medium text-slate-800 dark:text-slate-200 group-hover/link:text-blue-600 dark:group-hover/link:text-blue-400 transition-colors block truncate">
                      ${escapeHtml(src.title || src.url)}
                    </span>
                    <span class="text-[10px] text-slate-400 truncate block font-mono">
                      ${escapeHtml(src.url)}
                    </span>
                  </div>
                </div>
                <svg class="w-3.5 h-3.5 text-slate-400 group-hover/link:text-blue-500 shrink-0 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
                </svg>
              </a>
            `
        )
        .join("")}
          </div>
        </details>
      </div>
    `;
  }

  /**
   * Render individual chat message
   */
  function renderChatMessage(msg) {
    const isUser = msg.sender === "user";
    const timeFormatted = formatDate(msg.timestamp);

    if (isUser) {
      return `
        <div class="flex items-start gap-3 justify-end mb-5">
          <div class="max-w-[85%] md:max-w-[70%]">
            <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm text-sm">
              ${escapeHtml(msg.text)}
            </div>
            <div class="text-[10px] text-slate-400 text-right mt-1 px-1">
              ${timeFormatted}
            </div>
          </div>
          <div class="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/70 text-indigo-600 dark:text-indigo-300 flex items-center justify-center font-bold text-xs shrink-0 shadow-sm">
            You
          </div>
        </div>
      `;
    }

    // Determine answer origin badge
    let sourceBadge = "";
    if (msg.answer_source === "document") {
      sourceBadge = `
        <div class="mb-2.5">
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60">
            <svg class="w-3 h-3 text-emerald-600 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
            Grounded in Document
          </span>
        </div>
      `;
    } else if (msg.answer_source === "web") {
      sourceBadge = `
        <div class="mb-2.5">
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-800 dark:bg-blue-950/70 dark:text-blue-300 border border-blue-200 dark:border-blue-800/60" title="Not found in document; answered via live Web Search">
            <svg class="w-3 h-3 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/>
            </svg>
            Web Search Fallback
          </span>
          <span class="text-[10px] text-slate-400 ml-1.5">Not found in document</span>
        </div>
      `;
    } else if (msg.answer_source === "llm") {
      sourceBadge = `
        <div class="mb-2.5">
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-purple-100 text-purple-800 dark:bg-purple-950/70 dark:text-purple-300 border border-purple-200 dark:border-purple-800/60" title="Not found in document; answered from general AI knowledge">
            <svg class="w-3 h-3 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
            </svg>
            General AI Knowledge
          </span>
          <span class="text-[10px] text-slate-400 ml-1.5">Not found in document</span>
        </div>
      `;
    } else if (msg.answer_source === "none") {
      sourceBadge = `
        <div class="mb-2.5">
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950/70 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60">
            <svg class="w-3 h-3 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            Web Search Unavailable
          </span>
        </div>
      `;
    }

    // Assistant message
    return `
      <div class="flex items-start gap-3 mb-6">
        <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-500 text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-sm">
          AI
        </div>
        <div class="max-w-[90%] md:max-w-[80%] flex-1">
          <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-sm p-4 shadow-sm text-sm text-slate-800 dark:text-slate-100">
            ${sourceBadge}
            <div class="prose-answer">
              ${renderMarkdown(msg.text)}
            </div>
            ${renderSourcesList(msg.sources, msg.id)}
            ${renderWebSourcesList(msg.web_sources, msg.id)}
          </div>
          <div class="flex items-center justify-between text-[10px] text-slate-400 mt-1 px-1">
            <span>${timeFormatted}</span>
            ${msg.telemetry
        ? `<span class="font-mono text-slate-500 dark:text-slate-400">⚡ ${msg.telemetry}</span>`
        : ""
      }
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Render a file card in the Document Manager
   */
  function renderFileCard(file, isActive) {
    const isReady = file.status === "ready";
    const ext = file.file_extension ? file.file_extension.toUpperCase() : "DOC";

    return `
      <div class="p-4 rounded-xl border transition-all ${isActive
        ? "border-indigo-500 bg-indigo-50/40 dark:bg-indigo-950/20 shadow-sm"
        : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700"
      }">
        <div class="flex items-start justify-between gap-3 mb-2">
          <div class="flex items-center gap-2.5 overflow-hidden">
            <span class="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-[11px] font-bold shrink-0">
              ${escapeHtml(ext)}
            </span>
            <h4 class="font-semibold text-sm text-slate-900 dark:text-slate-100 truncate title="${escapeHtml(file.original_filename)}">
              ${escapeHtml(file.original_filename)}
            </h4>
          </div>
          <div>${renderStatusBadge(file.status)}</div>
        </div>

        <div class="grid grid-cols-3 gap-2 py-2 text-xs text-slate-500 dark:text-slate-400 border-y border-slate-100 dark:border-slate-800/80 my-2">
          <div>
            <span class="block text-[10px] uppercase text-slate-400">Size</span>
            <span class="font-medium text-slate-700 dark:text-slate-300">${formatBytes(file.size_bytes)}</span>
          </div>
          <div>
            <span class="block text-[10px] uppercase text-slate-400">Pages</span>
            <span class="font-medium text-slate-700 dark:text-slate-300">${file.page_count ?? "-"}</span>
          </div>
          <div>
            <span class="block text-[10px] uppercase text-slate-400">Chunks</span>
            <span class="font-medium text-slate-700 dark:text-slate-300">${file.chunk_count ?? 0}</span>
          </div>
        </div>

        ${file.error_message
        ? `<div class="p-2 mb-2 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded text-red-600 dark:text-red-400 text-xs">
                ${escapeHtml(file.error_message)}
               </div>`
        : ""
      }

        <div class="flex items-center justify-between pt-1 gap-2">
          <button 
            type="button" 
            onclick="App.selectFile('${file.id}')"
            class="flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 ${isActive
        ? "bg-indigo-600 text-white shadow-sm"
        : isReady
          ? "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-indigo-600 hover:text-white"
          : "bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed"
      }"
            ${!isReady && !isActive ? 'disabled title="Document must be ready before querying"' : ""}
          >
            ${isActive ? "Active in Chat ✓" : "Chat with this File"}
          </button>

          <button 
            type="button" 
            onclick="App.downloadFile('${file.id}', '${escapeHtml(file.original_filename)}')"
            class="p-1.5 text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Download original file"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
          </button>

          <button 
            type="button" 
            onclick="App.deleteFile('${file.id}')"
            class="p-1.5 text-slate-400 hover:text-red-600 dark:hover:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
            title="Delete file"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
          </button>
        </div>
      </div>
    `;
  }

  /**
   * Render Performance Summary KPIs
   */
  function renderPerformanceSummary(summary) {
    if (!summary) return '<div class="text-slate-400 text-sm">No performance data recorded yet.</div>';

    const q = summary.query || {};
    const ing = summary.ingestion || {};

    return `
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <!-- Queries Count -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span class="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Total Queries</span>
          <div class="text-2xl font-black text-slate-900 dark:text-slate-100 mt-1">${q.runs ?? 0}</div>
          <span class="text-[11px] text-green-600 dark:text-green-400 font-medium">
            ${q.success_rate != null ? (q.success_rate * 100).toFixed(0) + "% success" : "-"}
          </span>
        </div>

        <!-- Latency p50 / p95 -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span class="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Median Latency</span>
          <div class="text-2xl font-black text-slate-900 dark:text-slate-100 mt-1">${q.p50_total_ms ? Math.round(q.p50_total_ms) + " ms" : "-"}</div>
          <span class="text-[11px] text-slate-400 font-medium">p95: ${q.p95_total_ms ? Math.round(q.p95_total_ms) + " ms" : "-"}</span>
        </div>

        <!-- Retrieval Latency -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span class="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Avg Retrieval</span>
          <div class="text-2xl font-black text-indigo-600 dark:text-indigo-400 mt-1">${q.avg_retrieval_ms ? Math.round(q.avg_retrieval_ms) + " ms" : "-"}</div>
          <span class="text-[11px] text-slate-400 font-medium">Vector similarity search</span>
        </div>

        <!-- Generation Latency -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span class="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Avg LLM Time</span>
          <div class="text-2xl font-black text-violet-600 dark:text-violet-400 mt-1">${q.avg_generation_ms ? Math.round(q.avg_generation_ms) + " ms" : "-"}</div>
          <span class="text-[11px] text-slate-400 font-medium">Groq Cloud inference</span>
        </div>

        <!-- Answer Found Rate -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span class="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Grounded Rate</span>
          <div class="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1">${q.answer_found_rate != null ? (q.answer_found_rate * 100).toFixed(0) + "%" : "-"}</div>
          <span class="text-[11px] text-slate-400 font-medium">Answers grounded in doc</span>
        </div>

        <!-- Ingestions -->
        <div class="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <span class="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Files Ingested</span>
          <div class="text-2xl font-black text-slate-900 dark:text-slate-100 mt-1">${ing.runs ?? 0}</div>
          <span class="text-[11px] text-slate-400 font-medium">Avg ${ing.avg_total_ms ? (ing.avg_total_ms / 1000).toFixed(1) + "s" : "-"}</span>
        </div>
      </div>
    `;
  }

  /**
   * Render Recent Performance Runs Table
   */
  function renderPerformanceRunsTable(runs) {
    if (!runs || runs.length === 0) {
      return `
        <div class="p-8 text-center text-slate-400 border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900">
          No performance runs logged yet. Query a document or upload a file to record metrics.
        </div>
      `;
    }

    return `
      <div class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-500 font-bold uppercase text-[10px] tracking-wider">
              <th class="py-3 px-4">Time</th>
              <th class="py-3 px-4">Operation</th>
              <th class="py-3 px-4">Status</th>
              <th class="py-3 px-4">Detail / Question</th>
              <th class="py-3 px-4">Total Time</th>
              <th class="py-3 px-4">Breakdown (Retrieval / LLM)</th>
              <th class="py-3 px-4">Tokens / Chunks</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800/60 font-mono text-slate-700 dark:text-slate-300">
            ${runs
        .map((r) => {
          const isQuery = r.operation === "query";
          const isSuccess = r.success;

          return `
                <tr class="hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
                  <td class="py-2.5 px-4 font-sans text-slate-400 text-[11px] whitespace-nowrap">
                    ${formatDate(r.created_at)}
                  </td>
                  <td class="py-2.5 px-4 whitespace-nowrap">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${isQuery
              ? "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300"
              : "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
            }">
                      ${r.operation}
                    </span>
                  </td>
                  <td class="py-2.5 px-4 whitespace-nowrap">
                    ${isSuccess
              ? '<span class="text-green-600 dark:text-green-400 font-bold">✓ OK</span>'
              : '<span class="text-red-500 font-bold">✗ ERR</span>'
            }
                  </td>
                  <td class="py-2.5 px-4 font-sans text-xs max-w-xs truncate" title="${escapeHtml(r.question || r.error_message || "")}">
                    ${isQuery
              ? escapeHtml(r.question || "-")
              : `Ingested ${r.chunks_processed ?? "-"} chunks`
            }
                    ${r.error_message ? `<div class="text-red-500 text-[10px] font-mono">${escapeHtml(r.error_message)}</div>` : ""}
                  </td>
                  <td class="py-2.5 px-4 font-bold text-slate-900 dark:text-slate-100 whitespace-nowrap">
                    ${r.total_ms} ms
                  </td>
                  <td class="py-2.5 px-4 text-[11px] text-slate-500 whitespace-nowrap">
                    ${isQuery
              ? `Retr: <span class="text-indigo-600 dark:text-indigo-400">${r.retrieval_ms ?? "-"}ms</span> · LLM: <span class="text-violet-600 dark:text-violet-400">${r.generation_ms ?? "-"}ms</span>`
              : `Extr: ${r.extraction_ms ?? "-"}ms · Embed: ${r.embedding_ms ?? "-"}ms`
            }
                  </td>
                  <td class="py-2.5 px-4 text-[11px] whitespace-nowrap">
                    ${isQuery
              ? `${r.input_tokens ? r.input_tokens + " in / " + (r.output_tokens || 0) + " out" : r.chunks_retrieved ? r.chunks_retrieved + " chunks" : "-"}`
              : `${r.chunks_processed ? r.chunks_processed + " chunks" : "-"}`
            }
                  </td>
                </tr>
              `;
        })
        .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  return {
    escapeHtml,
    formatBytes,
    formatDate,
    renderStatusBadge,
    renderMarkdown,
    renderSourcesList,
    renderWebSourcesList,
    renderChatMessage,
    renderFileCard,
    renderPerformanceSummary,
    renderPerformanceRunsTable,
  };
})();

