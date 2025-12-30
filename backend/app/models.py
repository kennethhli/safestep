from sqlalchemy import Column, Integer, Float, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from app.database import Base
from datetime import datetime

class Route(Base):
    __tablename__ = "routes"
    
    id = Column(Integer, primary_key=True, index=True)
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    geometry = Column(Geometry('LINESTRING'), nullable=True)  # postgis linestring for route path
    risk_score = Column(Float, nullable=True)  # lower = safer
    distance = Column(Float, nullable=True)  # meters
    estimated_time = Column(Float, nullable=True)  # seconds
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class CrimeData(Base):
    __tablename__ = "crime_data"
    
    id = Column(Integer, primary_key=True, index=True)
    location = Column(Geometry('POINT'), nullable=False)  # from sf open data
    incident_type = Column(String, nullable=False)
    incident_date = Column(DateTime, nullable=False)
    raw_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class StreetLight(Base):
    __tablename__ = "street_lights"
    
    id = Column(Integer, primary_key=True, index=True)
    location = Column(Geometry('POINT'), nullable=False)
    light_type = Column(String, nullable=True)
    metadata = Column(JSONB, nullable=True)

class AccidentData(Base):
    __tablename__ = "accident_data"
    
    id = Column(Integer, primary_key=True, index=True)
    location = Column(Geometry('POINT'), nullable=False)
    accident_date = Column(DateTime, nullable=False)
    severity = Column(String, nullable=True)
    raw_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

