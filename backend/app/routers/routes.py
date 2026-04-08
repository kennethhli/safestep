from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict
from app.database import get_db
from app.services.route_calculator import RouteCalculator

router = APIRouter()
route_calculator = RouteCalculator()

def build_danger_summary(risk_score: float, feature_summary: Dict[str, float]) -> str:
    avg_violent = feature_summary.get("avg_violent_crimes", 0.0)
    avg_lights = feature_summary.get("avg_street_lights", 0.0)
    avg_accidents = feature_summary.get("avg_accidents", 0.0)
    avg_ped = feature_summary.get("avg_pedestrian_activity", 0.0)

    notes: List[str] = []
    if risk_score >= 0.7:
        notes.append("high overall risk for walking right now")
    elif risk_score >= 0.45:
        notes.append("moderate risk with a few caution points")
    else:
        notes.append("relatively safer option compared with alternatives")

    if avg_violent >= 4:
        notes.append("elevated violent incident density along sections of this route")
    if avg_accidents >= 4:
        notes.append("higher collision activity near parts of this path")
    if avg_lights < 3:
        notes.append("limited street lighting in parts of the route")
    if avg_ped < 8:
        notes.append("lower pedestrian activity can reduce natural visibility")
    if avg_lights >= 8 and avg_ped >= 15:
        notes.append("good lighting and foot traffic improve perceived safety")

    return ". ".join(notes) + "."

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
    route_geometry: Optional[List[List[float]]] = None
    waypoints: Optional[List[List[float]]] = None
    feature_summary: Optional[Dict[str, float]] = None
    danger_summary: Optional[str] = None
    
    class Config:
        from_attributes = True  # allows orm to dict conversion

@router.post("/routes/calculate", response_model=RouteResponse)
async def calculate_route(
    route_request: RouteRequest,
    db: Session = Depends(get_db)
):
    # calculate route with risk scoring
    result = route_calculator.calculate_route(
        route_request.start_lat,
        route_request.start_lng,
        route_request.end_lat,
        route_request.end_lng
    )
    
    summary = build_danger_summary(result["risk_score"], result["feature_summary"])
    return {
        "id": 1,
        "start_lat": route_request.start_lat,
        "start_lng": route_request.start_lng,
        "end_lat": route_request.end_lat,
        "end_lng": route_request.end_lng,
        "risk_score": result["risk_score"],
        "distance": result["distance"],
        "estimated_time": result["estimated_time"],
        "route_geometry": [[lat, lng] for lat, lng in result.get("route_geometry", [])],
        "waypoints": [[lat, lng] for lat, lng in result["waypoints"]],
        "feature_summary": result["feature_summary"],
        "danger_summary": summary
    }

@router.get("/routes/{route_id}", response_model=RouteResponse)
async def get_route(route_id: int, db: Session = Depends(get_db)):
    raise HTTPException(status_code=404, detail="Route not found")

