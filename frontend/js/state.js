/**
 * State Management for Citely
 * Handles files, active document, chat history, and auto-polling
 */

const State = (() => {
  const STORAGE_KEYS = {
    FILES: "rag_saved_files",
    CHATS: "rag_unified_chat",
    THEME: "rag_theme",
  };

  // State object
  const data = {
    files: [], // Array of FileOut objects
    messages: [], // Unified chat message history across all documents
    isDark: false,
    activeTab: "chat", // 'chat' | 'files' | 'performance'
    isPolling: false,
    activeRunFilter: "all",
  };

  const subscribers = new Set();

  function notify(event, payload) {
    for (const cb of subscribers) {
      try {
        cb(event, payload, data);
      } catch (e) {
        console.error("State subscriber error:", e);
      }
    }
  }

  function subscribe(cb) {
    subscribers.add(cb);
    return () => subscribers.delete(cb);
  }

  // Load initial data from localStorage
  function init() {
    try {
      const storedFiles = localStorage.getItem(STORAGE_KEYS.FILES);
      if (storedFiles) data.files = JSON.parse(storedFiles);

      const storedChats = localStorage.getItem(STORAGE_KEYS.CHATS);
      if (storedChats) data.messages = JSON.parse(storedChats);

      const storedTheme = localStorage.getItem(STORAGE_KEYS.THEME);
      if (storedTheme) {
        data.isDark = storedTheme === "dark";
      } else {
        data.isDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      }
    } catch (e) {
      console.warn("Failed to load initial state from localStorage:", e);
    }
  }

  function saveFiles() {
    localStorage.setItem(STORAGE_KEYS.FILES, JSON.stringify(data.files));
  }

  function saveChats() {
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(data.messages));
  }

  return {
    init,
    subscribe,

    // Getters
    get files() {
      return data.files;
    },
    get readyFiles() {
      return data.files.filter((f) => f.status === "ready");
    },
    get isDark() {
      return data.isDark;
    },
    get activeTab() {
      return data.activeTab;
    },
    get activeRunFilter() {
      return data.activeRunFilter;
    },

    getActiveChatHistory() {
      return data.messages;
    },

    // Setters & Actions
    setActiveTab(tabName) {
      data.activeTab = tabName;
      notify("tab_change", tabName);
    },

    setActiveRunFilter(filter) {
      data.activeRunFilter = filter;
      notify("filter_change", filter);
    },

    toggleTheme() {
      data.isDark = !data.isDark;
      localStorage.setItem(STORAGE_KEYS.THEME, data.isDark ? "dark" : "light");
      notify("theme_change", data.isDark);
    },

    setFiles(fileList) {
      const existingMap = new Map((data.files || []).map((f) => [f.id, f]));
      data.files = (fileList || []).map((f) => {
        const existing = existingMap.get(f.id);
        return existing && existing.batch_id ? { ...f, batch_id: existing.batch_id } : f;
      });
      saveFiles();
      notify("files_update", data.files);
    },

    addOrUpdateFile(fileRecord) {
      const idx = data.files.findIndex((f) => f.id === fileRecord.id);
      if (idx >= 0) {
        data.files[idx] = { ...data.files[idx], ...fileRecord };
      } else {
        data.files.unshift(fileRecord);
      }
      saveFiles();
      notify("files_update", data.files);
    },

    removeFile(fileId) {
      data.files = data.files.filter((f) => f.id !== fileId);
      saveFiles();
      notify("files_update", data.files);
    },

    addChatMessage(message) {
      data.messages.push({
        ...message,
        id: "msg_" + Math.random().toString(36).substring(2, 9),
        timestamp: new Date().toISOString(),
      });
      saveChats();
      notify("chat_update", { messages: data.messages });
    },

    clearChat() {
      data.messages = [];
      saveChats();
      notify("chat_update", { messages: [] });
    },

    // Check if any file is pending/processing to schedule background polling
    hasUnfinishedProcessing() {
      return data.files.some((f) => f.status === "pending" || f.status === "processing");
    },
  };
})();

