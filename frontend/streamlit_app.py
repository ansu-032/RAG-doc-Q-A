"""Streamlit Frontend for RAG Document Q&A.

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
    page_title="RAG Document Q&A",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚡ RAG Document Q&A")
st.caption("Grounded Semantic Search with FastEmbed (384-dim) & Groq LLM Inference")

# Sidebar: Document Management & Upload
with st.sidebar:
    st.header("📂 Document Management")
    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "docx", "md"],
        help="Upload PDF, DOCX, or Markdown files",
    )

    if uploaded_file and st.button("🚀 Upload & Ingest", use_container_width=True):
        with st.spinner(f"Uploading {uploaded_file.name}..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")}
                resp = requests.post(f"{API_URL}/file", files=files, timeout=30)
                if resp.status_code == 201:
                    st.success(f"Uploaded! Processing pipeline started.")
                    file_record = resp.json()
                    if "saved_files" not in st.session_state:
                        st.session_state["saved_files"] = []
                    # Append if not exists
                    if not any(f["id"] == file_record["id"] for f in st.session_state["saved_files"]):
                        st.session_state["saved_files"].insert(0, file_record)
                        st.session_state["active_file_id"] = file_record["id"]
                else:
                    st.error(f"Upload failed ({resp.status_code}): {resp.text}")
            except Exception as e:
                st.error(f"Cannot reach backend: {e}")

    st.divider()

    # Retrieve and refresh saved files from session
    if "saved_files" not in st.session_state:
        st.session_state["saved_files"] = []

    # Update statuses of files
    updated_files = []
    for f in st.session_state["saved_files"]:
        try:
            r = requests.get(f"{API_URL}/file/{f['id']}", timeout=5)
            if r.status_code == 200:
                updated_files.append(r.json())
            else:
                updated_files.append(f)
        except Exception:
            updated_files.append(f)
    st.session_state["saved_files"] = updated_files

    files_list = st.session_state["saved_files"]

    if files_list:
        st.subheader("Your Documents")
        file_options = {f["id"]: f"{f['original_filename']} ({f['status']})" for f in files_list}
        selected_file_id = st.selectbox(
            "Select active document for Q&A:",
            options=list(file_options.keys()),
            format_func=lambda fid: file_options[fid],
            index=0 if "active_file_id" not in st.session_state or st.session_state["active_file_id"] not in file_options else list(file_options.keys()).index(st.session_state["active_file_id"]),
        )
        st.session_state["active_file_id"] = selected_file_id

        active_file = next((f for f in files_list if f["id"] == selected_file_id), None)
        if active_file:
            st.info(
                f"**Status:** `{active_file['status']}`\n\n"
                f"**Chunks:** {active_file.get('chunk_count', 0)} | "
                f"**Pages:** {active_file.get('page_count') or '-'}"
            )
            col_d, col_x = st.columns(2)
            with col_d:
                # Download original
                try:
                    dl_resp = requests.get(f"{API_URL}/file/{selected_file_id}/download", timeout=10)
                    if dl_resp.status_code == 200:
                        st.download_button(
                            "📥 Download",
                            data=dl_resp.content,
                            file_name=active_file["original_filename"],
                            mime=active_file.get("mime_type", "application/octet-stream"),
                            use_container_width=True,
                        )
                except Exception:
                    pass
            with col_x:
                if st.button("🗑️ Delete", use_container_width=True):
                    try:
                        requests.delete(f"{API_URL}/file/{selected_file_id}", timeout=10)
                        st.session_state["saved_files"] = [f for f in files_list if f["id"] != selected_file_id]
                        st.session_state["active_file_id"] = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
    else:
        st.write("No documents uploaded yet.")

# Main Tabs: Q&A Chat and Performance Analytics
tab_chat, tab_perf = st.tabs(["💬 Q&A Chat", "📊 Performance Analytics"])

# TAB 1: Chat
with tab_chat:
    active_file_id = st.session_state.get("active_file_id")
    active_file = next((f for f in st.session_state.get("saved_files", []) if f["id"] == active_file_id), None)

    if not active_file:
        st.warning("👈 Please upload and select a document in the sidebar to start asking questions.")
    elif active_file.get("status") != "ready":
        st.warning(f"⏳ Document '{active_file['original_filename']}' is currently **{active_file.get('status')}**. Please wait for processing to finish.")
        if st.button("🔄 Refresh Status"):
            st.rerun()
    else:
        # Chat history per file
        chat_key = f"messages_{active_file_id}"
        if chat_key not in st.session_state:
            st.session_state[chat_key] = []

        # Display conversation
        for msg in st.session_state[chat_key]:
            with st.chat_message(msg["role"]):
                if msg.get("source_badge"):
                    st.caption(msg["source_badge"])
                st.markdown(msg["content"])
                if msg.get("sources"):
                    with st.expander(f"📚 Grounded Sources ({len(msg['sources'])})"):
                        for src in msg["sources"]:
                            st.markdown(
                                f"**[#{src['number']}] Chunk {src['chunk_index']}** "
                                f"— *Score: {round(src['score'] * 100, 1)}%*\n\n"
                                f"```\n{src['content']}\n```"
                            )
                if msg.get("web_sources"):
                    with st.expander(f"🌐 Referenced Web Sources ({len(msg['web_sources'])})"):
                        for ws in msg["web_sources"]:
                            st.markdown(f"- [{ws['title']}]({ws['url']})")

        # Chat input
        if prompt := st.chat_input(f"Ask anything about {active_file['original_filename']}..."):
            st.session_state[chat_key].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Searching passages and generating answer..."):
                    start = time.perf_counter()
                    try:
                        res = requests.post(
                            f"{API_URL}/query",
                            params={"file_id": active_file_id},
                            json={"question": prompt},
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
                                badge = "🌐 **Web Search Fallback** *(Not found in document)*"
                            elif answer_source == "llm":
                                badge = "🤖 **General AI Knowledge** *(Not found in document)*"
                            elif answer_source == "none":
                                badge = "⚠️ **Web Search Unavailable**"
                            else:
                                badge = "📄 **Grounded in Document**"

                            st.caption(badge)
                            st.markdown(answer)

                            if sources:
                                with st.expander(f"📚 Grounded Sources ({len(sources)}) — ⚡ {duration_ms} ms"):
                                    for src in sources:
                                        st.markdown(
                                            f"**[#{src['number']}] Chunk {src['chunk_index']}** "
                                            f"— *Similarity: {round(src['score'] * 100, 1)}%*\n\n"
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
                        st.error(f"Failed to query document: {e}")

# TAB 2: Performance Analytics
with tab_perf:
    st.subheader("Observability & Latency Metrics")

    try:
        summary_resp = requests.get(f"{API_URL}/performance/summary", timeout=5)
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
        runs_resp = requests.get(f"{API_URL}/performance?limit=25", timeout=5)
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

