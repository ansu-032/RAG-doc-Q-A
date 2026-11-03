/**
 * State Management for RAG Document Q&A
 * Handles files, active document, chat history, and auto-polling
 */

const State = (() => {
  const STORAGE_KEYS = {
    FILES: "rag_saved_files",
    ACTIVE_FILE: "rag_active_file_id",
    CHATS: "rag_chat_history",
    THEME: "rag_theme",
  };

  // State object
  const data = {
    files: [], // Array of FileOut objects
    activeFileId: null,
    chats: {}, // { [fileId]: [ { sender: 'user'|'assistant', text, sources, stats, timestamp } ] }
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

      const storedActive = localStorage.getItem(STORAGE_KEYS.ACTIVE_FILE);
      if (storedActive) data.activeFileId = storedActive;

      const storedChats = localStorage.getItem(STORAGE_KEYS.CHATS);
      if (storedChats) data.chats = JSON.parse(storedChats);

      const storedTheme = localStorage.getItem(STORAGE_KEYS.THEME);
      if (storedTheme) {
        data.isDark = storedTheme === "dark";
      } else {
        data.isDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      }
    } catch (e) {
      console.warn("Failed to load initial state from localStorage:", e);
    }

    // Ensure valid activeFileId
    if (data.activeFileId && !data.files.some((f) => f.id === data.activeFileId)) {
      data.activeFileId = data.files.length > 0 ? data.files[0].id : null;
    } else if (!data.activeFileId && data.files.length > 0) {
      data.activeFileId = data.files[0].id;
    }
  }

  function saveFiles() {
    localStorage.setItem(STORAGE_KEYS.FILES, JSON.stringify(data.files));
  }

  function saveChats() {
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(data.chats));
  }

  return {
    init,
    subscribe,

    // Getters
    get files() {
      return data.files;
    },
    get activeFileId() {
      return data.activeFileId;
    },
    get activeFile() {
      return data.files.find((f) => f.id === data.activeFileId) || null;
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
      if (!data.activeFileId) return [];
      return data.chats[data.activeFileId] || [];
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

    setActiveFile(fileId) {
      data.activeFileId = fileId;
      localStorage.setItem(STORAGE_KEYS.ACTIVE_FILE, fileId || "");
      notify("active_file_change", fileId);
    },

    addOrUpdateFile(fileRecord) {
      const idx = data.files.findIndex((f) => f.id === fileRecord.id);
      if (idx >= 0) {
        data.files[idx] = { ...data.files[idx], ...fileRecord };
      } else {
        data.files.unshift(fileRecord);
      }
      saveFiles();

      // If active file is updated or unset, set it
      if (!data.activeFileId) {
        data.activeFileId = fileRecord.id;
        localStorage.setItem(STORAGE_KEYS.ACTIVE_FILE, fileRecord.id);
      }

      notify("files_update", data.files);
    },

    removeFile(fileId) {
      data.files = data.files.filter((f) => f.id !== fileId);
      delete data.chats[fileId];
      saveFiles();
      saveChats();

      if (data.activeFileId === fileId) {
        data.activeFileId = data.files.length > 0 ? data.files[0].id : null;
        localStorage.setItem(STORAGE_KEYS.ACTIVE_FILE, data.activeFileId || "");
      }

      notify("files_update", data.files);
      notify("active_file_change", data.activeFileId);
    },

    addChatMessage(fileId, message) {
      if (!data.chats[fileId]) {
        data.chats[fileId] = [];
      }
      data.chats[fileId].push({
        ...message,
        id: "msg_" + Math.random().toString(36).substring(2, 9),
        timestamp: new Date().toISOString(),
      });
      saveChats();
      notify("chat_update", { fileId, messages: data.chats[fileId] });
    },

    clearChat(fileId) {
      if (!fileId) return;
      data.chats[fileId] = [];
      saveChats();
      notify("chat_update", { fileId, messages: [] });
    },

    // Check if any file is pending/processing to schedule background polling
    hasUnfinishedProcessing() {
      return data.files.some((f) => f.status === "pending" || f.status === "processing");
    },
  };
})();

