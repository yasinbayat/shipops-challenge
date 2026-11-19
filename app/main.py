import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="ShipOps API")

APP_VERSION = os.getenv("APP_VERSION", "dev")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/shipops")

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
FAILED_REQUESTS = Counter("http_requests_failed_total", "Total failed HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])


class ItemCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=3)


def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL
                );
            """)
        conn.commit()
    finally:
        conn.close()


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    endpoint = request.url.path
    status = str(response.status_code)
    if endpoint != "/metrics":
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=status).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
        if response.status_code >= 400:
            FAILED_REQUESTS.labels(method=request.method, endpoint=endpoint, status=status).inc()
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"database not ready: {str(e)}")


@app.get("/version")
def version():
    return {"version": APP_VERSION}


@app.post("/items", status_code=201)
def create_item(item: ItemCreate):
    try:
        init_db()
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO items (name) VALUES (%s) RETURNING id, name;", (item.name,))
            row = cur.fetchone()
        conn.commit()
        conn.close()
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/items/{item_id}")
def get_item(item_id: int):
    try:
        init_db()
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM items WHERE id = %s;", (item_id,))
            row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
