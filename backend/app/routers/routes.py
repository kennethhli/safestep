from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db

router = APIRouter()

class RouteRequest(BaseModel):
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float  # start and end coordinates

class RouteResponse(BaseModel):
    id: int
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    risk_score: Optional[float] = None
    distance: Optional[float] = None
    estimated_time: Optional[float] = None
    
    class Config:
        from_attributes = True  # allows orm to dict conversion

@router.post("/routes/calculate", response_model=RouteResponse)
async def calculate_route(
    route_request: RouteRequest,
    db: Session = Depends(get_db)
):
    # todo: add actual route calculation
    return {
        "id": 1,
        "start_lat": route_request.start_lat,
        "start_lng": route_request.start_lng,
        "end_lat": route_request.end_lat,
        "end_lng": route_request.end_lng,
        "risk_score": None,
        "distance": None,
        "estimated_time": None
    }

@router.get("/routes/{route_id}", response_model=RouteResponse)
async def get_route(route_id: int, db: Session = Depends(get_db)):
    raise HTTPException(status_code=404, detail="Route not found")

