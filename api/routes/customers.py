"""GET /customers and GET /customers/{id} -- read-only list/detail views for the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Customer
from database.session import get_db
from api.schemas import CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(search: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Customer).order_by(Customer.name)
    if search:
        stmt = stmt.where(Customer.name.ilike(f"%{search}%"))
    return db.execute(stmt).scalars().all()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
