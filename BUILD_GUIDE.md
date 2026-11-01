# RAG Document Q&A: Step-by-Step Build Guide

Stack: FastAPI (async) · LangChain · PostgreSQL + pgvector · MinIO · Ollama (local LLM) · HuggingFace embeddings · Streamlit

**What you are building:** a web app where a user uploads a PDF, asks questions about it, and gets answers grounded in the PDF's content, with page-number sources.

**Where data lives**

| Data | Stored in |
|---|---|
| The PDF file itself | **MinIO** |
| File details + MinIO path | table **`uploaded_files`** |
| Extracted text chunks + embeddings | table **`document_chunks`** (linked to `uploaded_files`, `ON DELETE CASCADE`) |
| Timing and score of every ingestion / query | table **`model_performance`** |

All primary keys are **UUID**.

---

## Step 0: Prerequisites (one-time)

- Install **Docker Desktop** and **Ollama** (https://ollama.com), then `ollama pull llama3.1:8b` (any model works; you set it in `.env`).
- Python 3.10+ for local development.

Minimal `docker-compose.yml` to start with:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: rag
      POSTGRES_DB: ragdb
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]
    volumes: [miniodata:/data]
volumes: { pgdata: {}, miniodata: {} }
```

```powershell
docker compose up -d
```

---

## Step 1: Create the tables

Connect: `docker exec -it <postgres-container> psql -U rag -d ragdb`, then run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE file_status AS ENUM ('pending', 'processing', 'ready', 'failed');

-- 1) Uploaded file: file details + where it lives in MinIO
CREATE TABLE uploaded_files (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename TEXT        NOT NULL,
    mime_type         TEXT        NOT NULL,              -- e.g. application/pdf
    file_extension    TEXT,                              -- e.g. pdf
    size_bytes        BIGINT      NOT NULL,
    sha256_checksum   CHAR(64)    NOT NULL,              -- detect duplicate uploads
    minio_bucket      TEXT        NOT NULL,
    minio_object_key  TEXT        NOT NULL,              -- storage path inside the bucket
    minio_etag        TEXT,
    page_count        INT,
    chunk_count       INT         NOT NULL DEFAULT 0,    -- total chunks created for this file
    status            file_status NOT NULL DEFAULT 'pending',
    error_message     TEXT,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at      TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (minio_bucket, minio_object_key)
);
CREATE INDEX uploaded_files_checksum_idx ON uploaded_files (sha256_checksum);

-- 2) Document content split into chunks, linked to the file
CREATE TABLE document_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id      UUID NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    chunk_index  INT  NOT NULL,                          -- order inside the file
    page_number  INT  NOT NULL,                          -- used in answer citations
    content      TEXT NOT NULL,                          -- the chunk text
    char_count   INT  NOT NULL,
    word_count   INT  NOT NULL,
    embedding    vector(384) NOT NULL,                   -- must match embedding model dimension
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (file_id, chunk_index)
);
CREATE INDEX document_chunks_file_id_idx ON document_chunks (file_id);
CREATE INDEX document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- 3) Model performance: one row per ingestion run or per question asked
CREATE TABLE model_performance (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id           UUID REFERENCES uploaded_files(id) ON DELETE SET NULL,  -- NULL for questions across many files
    operation         TEXT NOT NULL CHECK (operation IN ('ingestion', 'query')),
    success           BOOLEAN NOT NULL,
    error_message     TEXT,

    embedding_model   TEXT NOT NULL,
    llm_model         TEXT,                              -- NULL for ingestion
    chunk_size        INT,
    chunk_overlap     INT,
    top_k             INT,
    question          TEXT,                              -- query rows only

    -- time taken (milliseconds)
    extraction_ms     INT,
    chunking_ms       INT,
    embedding_ms      INT,
    retrieval_ms      INT,
    generation_ms     INT,
    total_ms          INT NOT NULL,

    -- scores / counts
    chunks_processed  INT,                               -- ingestion: chunks created
    chunks_retrieved  INT,                               -- query: chunks found
    top_similarity    REAL,                              -- best cosine similarity (0..1)
    avg_similarity    REAL,
    answer_found      BOOLEAN,                           -- false = "not found in documents"

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX model_performance_file_id_idx ON model_performance (file_id);
CREATE INDEX model_performance_created_at_idx ON model_performance (created_at DESC);
```

Notes:
- `vector(384)` matches `BAAI/bge-small-en-v1.5`. If you change the embedding model, change this number.
- Deleting a row in `uploaded_files` automatically deletes all its `document_chunks` (`ON DELETE CASCADE`).
- `model_performance.file_id` uses `ON DELETE SET NULL`, so your timing history survives after a file is deleted. A question asked across all files has no single file, so `file_id` is NULL for it. If you would rather delete the metrics together with the file, change it to `ON DELETE CASCADE` (the column would then need to be `NOT NULL`, so cross-file questions couldn't be logged).
- `gen_random_uuid()` is built into PostgreSQL 13+ (no extension needed).
- Later you can move this SQL into an Alembic migration. Running it by hand first shows you what the app needs.

Handy queries once data exists:

```sql
-- average ingestion time per embedding model
SELECT embedding_model, avg(total_ms) FROM model_performance WHERE operation='ingestion' GROUP BY 1;
-- slowest questions and how well they matched
SELECT question, total_ms, top_similarity FROM model_performance WHERE operation='query' ORDER BY total_ms DESC LIMIT 10;
```

---

## Step 2: Project skeleton and config

```
api/
  app/
    main.py  config.py  deps.py
    db/{session.py, models.py}
    schemas/{file.py, query.py}
    api/routes/{files.py, query.py, health.py}
    services/{storage.py, chunking.py, embeddings.py, ingestion.py, retrieval.py, generation.py, metrics.py}
  tests/
ui/app.py
.env
```

```powershell
cd api
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" sqlalchemy[asyncio] asyncpg pgvector pydantic-settings python-multipart `
  minio pypdf langchain langchain-community langchain-huggingface langchain-ollama sentence-transformers `
  pytest pytest-asyncio httpx
```

`.env`:

```
API_KEY=change-me
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=documents
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K=5
MIN_SCORE=0.3
MAX_UPLOAD_MB=25
```

`config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    api_key: str
    database_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "documents"
    ollama_base_url: str
    ollama_model: str
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    min_score: float = 0.3
    max_upload_mb: int = 25

settings = Settings()
```

---

## Step 3: Database layer (SQLAlchemy async models)

`db/session.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

`db/models.py` mirrors the three tables from Step 1:

```python
import uuid, datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text, Enum, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    file_extension: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int]
    sha256_checksum: Mapped[str]
    minio_bucket: Mapped[str] = mapped_column(Text)
    minio_object_key: Mapped[str] = mapped_column(Text)
    minio_etag: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    chunk_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(
        Enum("pending", "processing", "ready", "failed", name="file_status", create_type=False),
        default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime.datetime | None]
    updated_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    page_number: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int]
    word_count: Mapped[int]
    embedding = mapped_column(Vector(384))
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

class ModelPerformance(Base):
    __tablename__ = "model_performance"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("uploaded_files.id", ondelete="SET NULL"))
    operation: Mapped[str]                      # 'ingestion' | 'query'
    success: Mapped[bool]
    error_message: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    chunk_size: Mapped[int | None]
    chunk_overlap: Mapped[int | None]
    top_k: Mapped[int | None]
    question: Mapped[str | None] = mapped_column(Text)
    extraction_ms: Mapped[int | None]
    chunking_ms: Mapped[int | None]
    embedding_ms: Mapped[int | None]
    retrieval_ms: Mapped[int | None]
    generation_ms: Mapped[int | None]
    total_ms: Mapped[int]
    chunks_processed: Mapped[int | None]
    chunks_retrieved: Mapped[int | None]
    top_similarity: Mapped[float | None]
    avg_similarity: Mapped[float | None]
    answer_found: Mapped[bool | None]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
```

`deps.py` provides a DB session dependency and the API-key check:

```python
from fastapi import Header, HTTPException

async def get_db():
    async with SessionLocal() as session:
        yield session

async def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(401, "Invalid API key")
```

---

## Step 4: MinIO storage service

`services/storage.py`. The `minio` client is synchronous, so call it with `asyncio.to_thread` from async code.

```python
from minio import Minio
import io

client = Minio(settings.minio_endpoint, settings.minio_access_key,
               settings.minio_secret_key, secure=False)

def ensure_bucket():
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)

def put_pdf(key: str, data: bytes) -> str:
    result = client.put_object(settings.minio_bucket, key, io.BytesIO(data), len(data),
                               content_type="application/pdf")
    return result.etag                       # saved in uploaded_files.minio_etag

def get_pdf(key: str) -> bytes:
    r = client.get_object(settings.minio_bucket, key)
    try: return r.read()
    finally: r.close(); r.release_conn()

def delete_pdf(key: str):
    client.remove_object(settings.minio_bucket, key)
```

Call `ensure_bucket()` in the FastAPI lifespan at startup.

---

## Step 5: Upload, list, get and delete endpoints

`api/routes/files.py`. Upload flow:

1. Validate that the file is a PDF (content type and the `%PDF` magic bytes) and under `MAX_UPLOAD_MB`.
2. Compute the SHA-256 checksum and generate the id.
3. Store the file in MinIO at `files/{id}.pdf`.
4. Insert an `uploaded_files` row with status `pending`, saving mime type, size, checksum, bucket, key and etag.
5. Schedule ingestion with `BackgroundTasks` and return **202** immediately.

```python
@router.post("/files", status_code=202, dependencies=[Depends(require_api_key)])
async def upload(file: UploadFile, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    data = await file.read()
    if not data.startswith(b"%PDF") or len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(400, "Invalid or too large PDF")
    file_id = uuid.uuid4()
    key = f"files/{file_id}.pdf"
    etag = await asyncio.to_thread(storage.put_pdf, key, data)
    db.add(UploadedFile(
        id=file_id, original_filename=file.filename, mime_type="application/pdf",
        file_extension="pdf", size_bytes=len(data),
        sha256_checksum=hashlib.sha256(data).hexdigest(),
        minio_bucket=settings.minio_bucket, minio_object_key=key, minio_etag=etag))
    await db.commit()
    bg.add_task(ingestion.ingest_file, file_id)
    return {"id": file_id, "status": "pending"}
```

Also add `GET /files`, `GET /files/{id}` (the UI polls this for status) and `DELETE /files/{id}`. Delete removes the MinIO object, then the `uploaded_files` row, and the chunks go with it through the cascade.

Run and test: `uvicorn app.main:app --reload`, then open http://localhost:8000/docs.

---

## Step 6: Chunking with overlap

`services/chunking.py`. Overlap keeps a sentence that straddles a boundary present in both neighbouring chunks, so retrieval doesn't lose context.

```python
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def pdf_to_chunks(path: str):
    pages = PyPDFLoader(path).load()          # one Document per page, metadata["page"] is 0-based
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = splitter.split_documents(pages)  # page metadata is carried over
    return len(pages), chunks
```

`PyPDFLoader` needs a file path, so write the bytes from MinIO to a temp file first, or use `pypdf.PdfReader(io.BytesIO(data))` and build the `Document` objects yourself. For timing in Step 8, keep text extraction and splitting as two separate calls.

Test it early: a unit test that checks consecutive chunks share about `chunk_overlap` characters of text.

---

## Step 7: Embeddings

`services/embeddings.py`. Load the model **once** (it is slow and memory-heavy) and reuse it.

```python
from langchain_huggingface import HuggingFaceEmbeddings
from functools import lru_cache

@lru_cache
def get_embedder():
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        encode_kwargs={"normalize_embeddings": True},  # cosine similarity works best normalized
    )
```

Embedding is CPU-bound, so run it with `await asyncio.to_thread(embedder.embed_documents, texts)` to keep the event loop free.

---

## Step 8: Ingestion pipeline with performance logging

`services/metrics.py` is a small timer helper plus a function that writes a `model_performance` row:

```python
import time

class Timer:
    def __init__(self): self.t = {}; self._start = time.perf_counter()
    async def step(self, name, fn, *args):
        s = time.perf_counter()
        result = await asyncio.to_thread(fn, *args)
        self.t[name] = int((time.perf_counter() - s) * 1000)
        return result
    def total(self): return int((time.perf_counter() - self._start) * 1000)

async def log_metrics(**fields):
    async with SessionLocal() as db:           # own session, so it is saved even if the main work failed
        db.add(ModelPerformance(**fields)); await db.commit()
```

`services/ingestion.py` ties Steps 4 to 7 together, keeps `uploaded_files.status` current, and records one `ingestion` metrics row:

```python
async def ingest_file(file_id):
    timer = Timer()
    async with SessionLocal() as db:
        f = await db.get(UploadedFile, file_id)
        try:
            f.status = "processing"; await db.commit()

            data = await asyncio.to_thread(storage.get_pdf, f.minio_object_key)
            pages = await timer.step("extraction_ms", extract_pages, data)
            chunks = await timer.step("chunking_ms", split_pages, pages)
            texts = [c.page_content for c in chunks]
            vectors = await timer.step("embedding_ms", get_embedder().embed_documents, texts)

            db.add_all(DocumentChunk(
                file_id=file_id, chunk_index=i, page_number=c.metadata["page"] + 1,
                content=c.page_content, char_count=len(c.page_content),
                word_count=len(c.page_content.split()), embedding=v)
                for i, (c, v) in enumerate(zip(chunks, vectors)))
            f.status, f.chunk_count, f.page_count = "ready", len(chunks), len(pages)
            f.processed_at = datetime.datetime.now(datetime.timezone.utc)
            await db.commit()
            ok, err = True, None
        except Exception as e:
            await db.rollback()
            f = await db.get(UploadedFile, file_id)
            f.status, f.error_message = "failed", str(e)
            await db.commit()
            ok, err = False, str(e)

    await log_metrics(file_id=file_id, operation="ingestion", success=ok, error_message=err,
        embedding_model=settings.embedding_model, chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap, total_ms=timer.total(),
        chunks_processed=len(chunks) if ok else None, **timer.t)
```

Embed in batches (for example 64 texts at a time) for large PDFs to limit memory.

Test: upload a PDF, poll `GET /files/{id}` until `ready`, then run:

```sql
SELECT count(*) FROM document_chunks;
SELECT operation, total_ms, embedding_ms, chunks_processed FROM model_performance;
```

---

## Step 9: Retrieval (pgvector similarity search)

`services/retrieval.py`. `<=>` is cosine distance, so `similarity = 1 - distance`.

```python
async def search(db, question: str, top_k: int, file_ids: list[UUID] | None):
    qvec = await asyncio.to_thread(get_embedder().embed_query, question)
    distance = DocumentChunk.embedding.cosine_distance(qvec)
    stmt = (select(DocumentChunk, UploadedFile.original_filename, (1 - distance).label("score"))
            .join(UploadedFile, UploadedFile.id == DocumentChunk.file_id)
            .where(UploadedFile.status == "ready")
            .order_by(distance).limit(top_k))
    if file_ids:
        stmt = stmt.where(DocumentChunk.file_id.in_(file_ids))
    rows = (await db.execute(stmt)).all()
    return [r for r in rows if r.score >= settings.min_score]
```

---

## Step 10: Grounded answer generation and query logging

`services/generation.py`:

```python
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Answer ONLY from the context below. Cite sources like [1], [2]. "
     "If the answer is not in the context, say you don't know.\n\nContext:\n{context}"),
    ("human", "{question}"),
])

async def answer(question, hits):
    context = "\n\n".join(
        f"[{i+1}] ({h.original_filename}, p.{h.DocumentChunk.page_number}) {h.DocumentChunk.content}"
        for i, h in enumerate(hits))
    msg = await (prompt | llm).ainvoke({"context": context, "question": question})
    return msg.content
```

`routes/query.py`: `POST /api/v1/query` with `{question, file_ids?, top_k?}`. Time retrieval and generation separately and log a `query` row:

```python
timer = Timer()
hits = await timed_async(timer, "retrieval_ms", search(db, q.question, k, q.file_ids))
if not hits:
    answer_text, found = "Not found in the documents.", False       # skip the LLM entirely
else:
    answer_text = await timed_async(timer, "generation_ms", answer(q.question, hits)); found = True

scores = [h.score for h in hits]
await log_metrics(
    file_id=q.file_ids[0] if q.file_ids and len(q.file_ids) == 1 else None,
    operation="query", success=True, question=q.question,
    embedding_model=settings.embedding_model, llm_model=settings.ollama_model, top_k=k,
    chunks_retrieved=len(hits), top_similarity=max(scores, default=None),
    avg_similarity=(sum(scores) / len(scores)) if scores else None,
    answer_found=found, total_ms=timer.total(), **timer.t)
return {"answer": answer_text, "sources": [...]}   # file, page, snippet, score
```

`file_id` is stored only when the question targeted exactly one file; otherwise it is NULL.

---

## Step 11: Health check and wiring

- `GET /health` pings Postgres (`SELECT 1`), MinIO (`bucket_exists`) and Ollama (`GET {OLLAMA_BASE_URL}/api/tags`).
- In `main.py` use a lifespan handler to call `ensure_bucket()` and warm up `get_embedder()` so the first request isn't slow.
- Include the routers under `/api/v1`.
- Optional: `GET /api/v1/metrics?file_id=...` returning rows from `model_performance`, so the UI can show a performance table.

---

## Step 12: Streamlit UI

`ui/app.py` calls the API with the `X-API-Key` header:

```python
import streamlit as st, requests
API, H = "http://localhost:8000/api/v1", {"X-API-Key": "change-me"}

up = st.file_uploader("Upload a PDF", type="pdf")
if up and st.button("Ingest"):
    requests.post(f"{API}/files", headers=H, files={"file": (up.name, up.getvalue())})

files = requests.get(f"{API}/files", headers=H).json()
st.dataframe([{"name": f["original_filename"], "status": f["status"], "chunks": f["chunk_count"]} for f in files])
selected = st.multiselect("Search in", [f["id"] for f in files],
                          format_func=lambda i: next(f["original_filename"] for f in files if f["id"] == i))

q = st.text_input("Ask a question")
if q:
    res = requests.post(f"{API}/query", headers=H, json={"question": q, "file_ids": selected or None}).json()
    st.write(res["answer"])
    for s in res["sources"]:
        st.caption(f'{s["filename"]} p.{s["page"]}: {s["snippet"]}')
```

Show each file's status (`pending`, `processing`, `ready`, `failed`) and refresh it so users know when a PDF is ready. Add a "Performance" tab that lists recent `model_performance` rows.

Run: `streamlit run ui/app.py`

---

## Step 13: Tests

Use pytest with `httpx.AsyncClient`. Fake the embedder (deterministic vectors), the LLM and MinIO so tests need no external services.

- `test_chunking.py`: overlap works, page numbers are preserved.
- `test_files_api.py`: upload accepts a PDF, rejects non-PDFs and oversized files, returns 401 without the API key, and saves mime type, checksum and MinIO path.
- `test_cascade.py`: deleting an `uploaded_files` row removes its `document_chunks`.
- `test_retrieval.py`: the file filter works and results are ordered by similarity.
- `test_query_api.py`: returns an answer with sources; the "not found" path doesn't call the LLM; a `model_performance` row is written for ingestion and for queries.

---

## Step 14: Containerize everything

Add `api` and `ui` services to `docker-compose.yml`, each with its own `Dockerfile` (`python:3.11-slim`, `pip install -r requirements.txt`).

- Inside the containers use `DATABASE_URL=...@postgres:5432/...` and `MINIO_ENDPOINT=minio:9000`, not `localhost`.
- Ollama runs on the host, so set `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
- Add a `depends_on` with a Postgres healthcheck, and mount a volume for the HuggingFace model cache so the embedding model isn't re-downloaded every time.
- Mount the Step 1 SQL into `/docker-entrypoint-initdb.d/` so the tables are created automatically on first start.

Run the whole stack: `docker compose up --build`

---

## Step 15: Try it end to end

1. Open http://localhost:8501 (UI), upload a PDF, wait for status `ready`.
2. Ask a question and check that the answer cites sources with page numbers.
3. Ask something that is not in the document and confirm you get "not found".
4. Check the data: `SELECT * FROM uploaded_files;`, `SELECT count(*) FROM document_chunks;`, `SELECT * FROM model_performance ORDER BY created_at DESC;`.
5. Delete the file and confirm its chunks are gone, while its `model_performance` rows remain with `file_id` NULL.
6. Browse the stored PDFs in the MinIO console at http://localhost:9001.

## Common problems

| Symptom | Likely cause |
|---|---|
| `type "vector" does not exist` | `CREATE EXTENSION vector;` was not run, or the image isn't `pgvector/pgvector` |
| Dimension mismatch error on insert | `vector(N)` doesn't match the embedding model's output size |
| API can't reach Ollama from Docker | Use `host.docker.internal`, and make sure Ollama is running |
| First query/upload is very slow | The embedding model is downloading or loading; warm it up at startup |
| Scanned PDF gives 0 chunks | No text layer; OCR is not included in this design |
