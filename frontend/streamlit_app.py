"""Streamlit Frontend for Citely.

Matches Step 12 of BUILD_GUIDE.md, upgraded to support:
- Multi-format uploads (PDF, DOCX, Markdown)
- Chat with citations [1], [2] and similarity score badges
- Live status polling for processing files
- Real-time Performance & Telemetry Dashboard

Run with:
    streamlit run frontend/streamlit_app.py
"""

import os
import time
import requests
import streamlit as st

API_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/v1").rstrip("/")

st.set_page_config(
    page_title="Citely",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# A requests.Session keeps the backend's session cookie; without it this user loses access to their files.
if "http" not in st.session_state:
    st.session_state["http"] = requests.Session()
http = st.session_state["http"]

st.title("⚡ Citely")
st.caption("Answers cited from your documents")

# Sidebar: Document Management & Upload
with st.sidebar:
    st.header("📂 Document Management")
    uploaded_files = st.file_uploader(
        "Upload documents",
        type=["pdf", "docx", "md"],
        accept_multiple_files=True,
        help="Upload PDF, DOCX, or Markdown files",
    )

    if uploaded_files and st.button("🚀 Upload & Ingest", use_container_width=True):
        if "saved_files" not in st.session_state:
            st.session_state["saved_files"] = []
        with st.spinner(f"Uploading {len(uploaded_files)} document(s)..."):
            for uf in uploaded_files:
                try:
                    files = {"file": (uf.name, uf.getvalue(), uf.type or "application/octet-stream")}
                    resp = http.post(f"{API_URL}/file", files=files, timeout=30)
                    if resp.status_code == 201:
                        file_record = resp.json()
                        if not any(f["id"] == file_record["id"] for f in st.session_state["saved_files"]):
                            st.session_state["saved_files"].insert(0, file_record)
                            if "active_file_id" not in st.session_state or not st.session_state["active_file_id"]:
                                st.session_state["active_file_id"] = file_record["id"]
                        st.success(f"Uploaded '{uf.name}'! Processing started.")
                    else:
                        st.error(f"Upload failed for '{uf.name}' ({resp.status_code}): {resp.text}")
                except Exception as e:
                    st.error(f"Cannot reach backend for '{uf.name}': {e}")

    st.divider()

    # Synchronize and refresh saved files from backend
    try:
        r = http.get(f"{API_URL}/files", timeout=5)
        if r.status_code == 200:
            st.session_state["saved_files"] = r.json()
    except Exception:
        pass

    if "saved_files" not in st.session_state:
        st.session_state["saved_files"] = []

    files_list = st.session_state["saved_files"]

    if files_list:
        ready_count = sum(1 for f in files_list if f.get("status") == "ready")
        st.subheader(f"📚 Documents in Workspace ({ready_count}/{len(files_list)} ready)")
        for f in files_list:
            col_info, col_act = st.columns([3, 1])
            with col_info:
                st.markdown(
                    f"📄 **{f['original_filename']}**\n\n"
                    f"<small>`{f['status']}` • {f.get('chunk_count', 0)} chunks • {f.get('page_count') or '-'} pages</small>",
                    unsafe_allow_html=True,
                )
            with col_act:
                if st.button("🗑️", key=f"del_{f['id']}", help=f"Delete {f['original_filename']}"):
                    try:
                        http.delete(f"{API_URL}/file/{f['id']}", timeout=10)
                        st.session_state["saved_files"] = [x for x in files_list if x["id"] != f["id"]]
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
            st.divider()
    else:
        st.write("No documents uploaded yet.")

# Main Tabs: Q&A Chat and Performance Analytics
tab_chat, tab_perf = st.tabs(["💬 Chat", "📊 Performance Analytics"])

# TAB 1: Chat (Single unified chat across all uploaded documents)
with tab_chat:
    files_list = st.session_state.get("saved_files", [])
    ready_files = [f for f in files_list if f.get("status") == "ready"]

    if not files_list:
        st.warning("👈 Please upload your documents in the sidebar to start asking questions.")
    elif not ready_files:
        st.warning(f"⏳ Uploaded documents are currently processing. Please wait a moment...")
        if st.button("🔄 Refresh Status"):
            st.rerun()
    else:
        # A single conversation thread that queries across all uploaded documents
        chat_key = "messages"
        if chat_key not in st.session_state:
            st.session_state[chat_key] = []

        doc_names = ", ".join(f"`{f['original_filename']}`" for f in ready_files)
        st.caption(f"📚 **Active Knowledge Base ({len(ready_files)} documents):** {doc_names}")

        # Display conversation
        for msg in st.session_state[chat_key]:
            with st.chat_message(msg["role"]):
                if msg.get("source_badge"):
                    st.caption(msg["source_badge"])
                st.markdown(msg["content"])
                if msg.get("sources"):
                    with st.expander(f"📚 Grounded Sources ({len(msg['sources'])})"):
                        for src in msg["sources"]:
                            src_name = src.get("filename") or "Document"
                            page_info = f", Page {src['page_number']}" if src.get("page_number") else ""
                            st.markdown(
                                f"**[#{src['number']}] 📄 {src_name}{page_info}** "
                                f"— *Chunk {src['chunk_index']} (Score: {round(src['score'] * 100, 1)}%)*\n\n"
                                f"```\n{src['content']}\n```"
                            )
                if msg.get("web_sources"):
                    with st.expander(f"🌐 Referenced Web Sources ({len(msg['web_sources'])})"):
                        for ws in msg["web_sources"]:
                            st.markdown(f"- [{ws['title']}]({ws['url']})")

        # Chat input: queries across all uploaded documents simultaneously
        placeholder = f"Ask anything across your {len(ready_files)} document(s) (compare, relate, synthesize)..."
        if prompt := st.chat_input(placeholder):
            st.session_state[chat_key].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Searching across documents and synthesizing answer..."):
                    start = time.perf_counter()
                    try:
                        history_payload = [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state[chat_key][-6:]
                            if m.get("content")
                        ]
                        # Query across all documents in this session (no single file_id restriction)
                        res = http.post(
                            f"{API_URL}/query",
                            json={"question": prompt, "history": history_payload},
                            timeout=60,
                        )
                        duration_ms = int((time.perf_counter() - start) * 1000)

                        if res.status_code == 200:
                            data = res.json()
                            answer = data.get("answer", "")
                            answer_source = data.get("answer_source", "document")
                            sources = data.get("sources", [])
                            web_sources = data.get("web_sources", [])

                            # Source badge
                            if answer_source == "web":
                                badge = "🌐 **Web Search Fallback** *(Not found in documents)*"
                            elif answer_source == "llm":
                                badge = "🤖 **General AI Knowledge** *(Not found in documents)*"
                            elif answer_source == "none":
                                badge = "⚠️ **Web Search Unavailable**"
                            else:
                                badge = f"📄 **Grounded across {len(set(s.get('filename') for s in sources if s.get('filename')))} Document(s)**"

                            st.caption(badge)
                            st.markdown(answer)

                            if sources:
                                with st.expander(f"📚 Grounded Sources ({len(sources)}) — ⚡ {duration_ms} ms"):
                                    for src in sources:
                                        src_name = src.get("filename") or "Document"
                                        page_info = f", Page {src['page_number']}" if src.get("page_number") else ""
                                        st.markdown(
                                            f"**[#{src['number']}] 📄 {src_name}{page_info}** "
                                            f"— *Chunk {src['chunk_index']} (Similarity: {round(src['score'] * 100, 1)}%)*\n\n"
                                            f"```\n{src['content']}\n```"
                                        )

                            if web_sources:
                                with st.expander(f"🌐 Referenced Web Sources ({len(web_sources)}) — ⚡ {duration_ms} ms"):
                                    for ws in web_sources:
                                        st.markdown(f"- [{ws['title']}]({ws['url']})")

                            st.session_state[chat_key].append({
                                "role": "assistant",
                                "content": answer,
                                "source_badge": badge,
                                "sources": sources,
                                "web_sources": web_sources,
                            })
                        else:
                            st.error(f"Error ({res.status_code}): {res.text}")
                    except Exception as e:
                        st.error(f"Failed to query documents: {e}")

# TAB 2: Performance Analytics
with tab_perf:
    st.subheader("Observability & Latency Metrics")

    try:
        summary_resp = http.get(f"{API_URL}/performance/summary", timeout=5)
        if summary_resp.status_code == 200:
            summary = summary_resp.json()
            q = summary.get("query", {})
            ing = summary.get("ingestion", {})

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Queries", q.get("runs") or 0)
            col2.metric("Median Total Latency", f"{round(q.get('p50_total_ms') or 0)} ms")
            col3.metric("Avg Retrieval (Vector)", f"{round(q.get('avg_retrieval_ms') or 0)} ms")
            col4.metric("Avg LLM Generation", f"{round(q.get('avg_generation_ms') or 0)} ms")
            col5.metric("Files Ingested", ing.get("runs") or 0)
        else:
            st.info("Performance summary not available yet.")
    except Exception:
        st.info("Ensure the FastAPI backend is running.")

    # List recent performance runs
    try:
        runs_resp = http.get(f"{API_URL}/performance?limit=25", timeout=5)
        if runs_resp.status_code == 200:
            runs = runs_resp.json()
            if runs:
                st.dataframe(
                    [
                        {
                            "Time": r.get("created_at"),
                            "Operation": r.get("operation"),
                            "Success": r.get("success"),
                            "Total (ms)": r.get("total_ms"),
                            "Retrieval (ms)": r.get("retrieval_ms"),
                            "LLM (ms)": r.get("generation_ms"),
                            "Tokens In": r.get("input_tokens"),
                            "Tokens Out": r.get("output_tokens"),
                            "Question / Status": r.get("question") or r.get("error_message") or "Ingestion",
                        }
                        for r in runs
                    ],
                    use_container_width=True,
                )
    except Exception:
        pass

