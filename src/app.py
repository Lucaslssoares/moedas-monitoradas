import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import get_connection

THRESHOLD = float(os.getenv("ALERT_THRESHOLD_PCT", "-10.0"))


class MLItem(BaseModel):
    id: str
    title: str
    price: float
    original_price: Optional[float] = None
    currency_id: str = "BRL"
    permalink: str
    seller: dict


class AnalyzeRequest(BaseModel):
    items: List[MLItem]
    query: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(open("sql/schema.sql").read())
    conn.commit()
    conn.close()
    yield


app = FastAPI(title="Moedas Monitoradas — Crypto Price Hunter", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}


@app.post("/webhook/analyze")
def analyze(req: AnalyzeRequest):
    conn = get_connection()
    alerts = []

    for item in req.items:
        try:
            with conn.cursor() as cur:
                # Idempotência: busca o último preço já registrado
                cur.execute(
                    "SELECT price FROM price_history "
                    "WHERE product_id = %s ORDER BY searched_at DESC LIMIT 1",
                    (item.id,),
                )
                row = cur.fetchone()
                previous_price = float(row[0]) if row else None

                variation_pct = None
                should_alert = False

                if previous_price and previous_price > 0:
                    variation_pct = ((item.price - previous_price) / previous_price) * 100
                    should_alert = variation_pct <= THRESHOLD

                # Insere novo registro de preço
                cur.execute(
                    """
                    INSERT INTO price_history
                      (product_id, product_title, seller_id, seller_nickname,
                       price, original_price, currency_id, permalink, variation_pct, alerted)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item.id,
                        item.title,
                        item.seller.get("id"),
                        item.seller.get("nickname", ""),
                        item.price,
                        item.original_price,
                        item.currency_id,
                        item.permalink,
                        variation_pct,
                        should_alert,
                    ),
                )
            conn.commit()

            if should_alert:
                alerts.append(
                    {
                        "product_id": item.id,
                        "title": item.title,
                        "previous_price": previous_price,
                        "current_price": item.price,
                        "variation_pct": round(variation_pct, 2),
                        "permalink": item.permalink,
                    }
                )
        except Exception as exc:
            conn.rollback()
            print(f"[ERROR] produto {item.id}: {exc}")

    conn.close()
    return {"processed": len(req.items), "alerts": alerts, "has_alert": bool(alerts)}
