from fastapi import FastAPI

from middleware import log_requests

app = FastAPI(title="RAG Document Q&A")
app.middleware("http")(log_requests)
