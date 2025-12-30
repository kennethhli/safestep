import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("DATABASE_URL not found in .env")
    exit(1)

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("db connection ok")
        
        try:
            result = conn.execute(text("SELECT PostGIS_version()"))
            version = result.fetchone()[0]
            print(f"postgis enabled: {version}")
        except:
            print("postgis not enabled")
            
except Exception as e:
    print(f"connection failed: {e}")

