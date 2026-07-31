"""
FastAPI app entry point.

Run locally with:
    uvicorn api.main:app --reload
"""

from fastapi import FastAPI

from api.routes import customers, enquiries, quotations

app = FastAPI(title="Green Earth Quotation System API")

app.include_router(customers.router)
app.include_router(enquiries.router)
app.include_router(quotations.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
