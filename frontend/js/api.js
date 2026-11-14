/**
 * API Service for Citely
 * Interacts with FastAPI backend endpoints:
 * - POST   /api/v1/file
 * - GET    /api/v1/file/{file_id}
 * - GET    /api/v1/file/{file_id}/download
 * - DELETE /api/v1/file/{file_id}
 * - POST   /api/v1/query?file_id={file_id}
 * - GET    /api/v1/performance
 * - GET    /api/v1/performance/summary
 */

const Api = (() => {
  const normalizeUrl = (url) => {
    if (!url) return "";
    let cleaned = url.trim().replace(/\/+$/, "");
    if ((cleaned.startsWith("http://") || cleaned.startsWith("https://")) && !cleaned.endsWith("/api/v1")) {
      cleaned = `${cleaned}/api/v1`;
    }
    return cleaned;
  };

  const getDefaultBaseUrl = () => {
    if (typeof window !== "undefined") {
      if (window.location.protocol === "file:") {
        return "http://localhost:8000/api/v1";
      }
      const port = window.location.port;
      // Port 8000 (FastAPI), Port 3000 (frontend proxy), or standard 80/443 (reverse proxy) use relative /api/v1
      if (port === "8000" || port === "3000" || port === "") {
        return "/api/v1";
      }
      // Any other port (e.g. Live Server on 5500, 8080, etc.) connects to FastAPI at port 8000
      return "http://localhost:8000/api/v1";
    }
    return "/api/v1";
  };

  let savedUrl = localStorage.getItem("rag_api_base_url");
  let baseUrl = savedUrl ? normalizeUrl(savedUrl) : getDefaultBaseUrl();

  const getBaseUrl = () => baseUrl;

  const setBaseUrl = (url) => {
    baseUrl = normalizeUrl(url) || getDefaultBaseUrl();
    localStorage.setItem("rag_api_base_url", baseUrl);
  };

  const resetBaseUrl = () => {
    localStorage.removeItem("rag_api_base_url");
    baseUrl = getDefaultBaseUrl();
    return baseUrl;
  };

  /**
   * Helper for fetch requests with standardized error handling
   */
  async function request(endpoint, options = {}) {
    const url = `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
    const headers = options.headers ? { ...options.headers } : {};

    // Don't set Content-Type if body is FormData (let browser set boundary)
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    // Always include credentials so the session cookie is preserved across ports/origins
    options.credentials = options.credentials || "include";

    try {
      const response = await fetch(url, { ...options, headers });

      if (response.status === 204) {
        return null;
      }

      const contentType = response.headers.get("content-type") || "";
      let data = null;

      if (contentType.includes("application/json")) {
        data = await response.json();
      } else if (response.ok) {
        // Blob or raw stream
        data = await response.blob();
      } else {
        const text = await response.text();
        throw new Error(text || `HTTP error ${response.status}: ${response.statusText}`);
      }

      if (!response.ok) {
        const message = data && (data.detail || data.message || data.error)
          ? (typeof data.detail === "object" ? JSON.stringify(data.detail) : data.detail)
          : `HTTP ${response.status}: ${response.statusText}`;
        const err = new Error(message);
        err.status = response.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      if (err.name === "TypeError" && err.message.includes("fetch")) {
        throw new Error(
          `Unable to connect to backend at ${baseUrl}. Ensure the FastAPI server is running.`
        );
      }
      throw err;
    }
  }

  return {
    getBaseUrl,
    setBaseUrl,
    resetBaseUrl,

    /**
     * List all documents in the session
     */
    async getFiles() {
      return await request("/files");
    },

    /**
     * Upload multiple document files (PDF, DOCX, Markdown)
     */
    async uploadFiles(files) {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      return await request("/files", {
        method: "POST",
        body: formData,
      });
    },

    /**
     * Upload a document file (PDF, DOCX, Markdown)
     */
    async uploadFile(file) {
      const formData = new FormData();
      formData.append("file", file);
      return await request("/file", {
        method: "POST",
        body: formData,
      });
    },

    /**
     * Fetch document record and processing status
     */
    async getFile(fileId) {
      return await request(`/file/${fileId}`);
    },

    /**
     * Download document file
     */
    async downloadFile(fileId, filename) {
      const blob = await request(`/file/${fileId}/download`);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `document-${fileId}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },

    /**
     * Delete document and its chunks
     */
    async deleteFile(fileId) {
      return await request(`/file/${fileId}`, {
        method: "DELETE",
      });
    },

    /**
     * Query documents with natural language question (specific file or entire workspace)
     */
    async askQuestion(fileId, question, history = []) {
      const endpoint = fileId && fileId !== "all"
        ? `/query?file_id=${encodeURIComponent(fileId)}`
        : "/query";
      return await request(endpoint, {
        method: "POST",
        body: JSON.stringify({ question, history }),
      });
    },

    /**
     * List recent performance runs (query and/or ingestion)
     */
    async getPerformanceRuns({ operation = null, fileId = null, limit = 50 } = {}) {
      const params = new URLSearchParams();
      if (operation) params.append("operation", operation);
      if (fileId) params.append("file_id", fileId);
      if (limit) params.append("limit", limit.toString());
      const queryStr = params.toString() ? `?${params.toString()}` : "";
      return await request(`/performance${queryStr}`);
    },

    /**
     * Get aggregate performance summary (p50, p95, token averages)
     */
    async getPerformanceSummary(fileId = null) {
      const queryStr = fileId ? `?file_id=${encodeURIComponent(fileId)}` : "";
      return await request(`/performance/summary${queryStr}`);
    },

    /**
     * Check backend connectivity
     */
    async testConnection() {
      try {
        await request("/health");
        return { ok: true, message: "Backend is reachable and responding" };
      } catch (err) {
        try {
          await request("/files");
          return { ok: true, message: "Backend is reachable and responding" };
        } catch (e) {
          if (e.status && e.status !== 502) {
            return { ok: true, message: `Connected (HTTP ${e.status})` };
          }
          return { ok: false, message: e.message };
        }
      }
    },
  };
})();

