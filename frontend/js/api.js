/**
 * API Service for RAG Document Q&A
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
  // If served through frontend server.py proxy, relative path "/api/v1" works directly.
  // Can be overridden by the user in Settings modal.
  let baseUrl = localStorage.getItem("rag_api_base_url") || "/api/v1";

  const getBaseUrl = () => baseUrl;

  const setBaseUrl = (url) => {
    baseUrl = url.replace(/\/+$/, "");
    localStorage.setItem("rag_api_base_url", baseUrl);
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
     * Query a specific document with natural language question
     */
    async askQuestion(fileId, question) {
      return await request(`/query?file_id=${encodeURIComponent(fileId)}`, {
        method: "POST",
        body: JSON.stringify({ question }),
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
        // Try performance endpoint or file probe
        const runs = await request("/performance?limit=1");
        return { ok: true, message: "Backend is reachable and responding" };
      } catch (err) {
        // Even if 404 or 422, the server might be reachable
        if (err.status && err.status !== 502) {
          return { ok: true, message: `Connected (HTTP ${err.status})` };
        }
        return { ok: false, message: err.message };
      }
    },
  };
})();

