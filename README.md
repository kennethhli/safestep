# SafeStep

- SafeStep is a San Francisco walking route app that ranks route options by safety risk, not just ETA.
- It pulls walking alternatives from Mapbox, scores them with city open data, and shows the results on an interactive map.
- Most map apps optimize for speed. I wanted to try a version that also surfaces safety context, especially for night walks or scary/unfamiliar neighborhoods.

## Current features

- Search start/destination with address autocomplete
- Get real walking alternatives from Mapbox Directions
- Score each route with a trained scikit-learn model
- Compare side-by-side options (`safest`, `fastest`, `balanced alternative`)
- Show hazard pins and risk-colored route segments

## Tech stack

- **Frontend:** React, Mapbox GL JS, react-map-gl, Tailwind CSS
- **Backend:** FastAPI, Pydantic, requests
- **ML:** scikit-learn (Random Forest), NumPy, joblib
- **Data:** San Francisco Open Data (Socrata), Mapbox APIs
- **DB layer:** PostgreSQL/PostGIS via SQLAlchemy + GeoAlchemy2

## Project structure

```text
frontend/                 React client
backend/                  FastAPI service
backend/app/services/     route scoring + data fetching + risk model
backend/train_model.py    offline training script
docker-compose.yml        local PostGIS database service
```

## Run locally

Run backend and frontend in separate terminals.

```bash
git clone <your-repo-url>
cd safestep
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Create `backend/.env` (or repo `.env`):

```bash
MAPBOX_ACCESS_TOKEN=your_mapbox_token
SF_DATA_API_KEY=your_socrata_app_token
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/safestep
MODEL_ARTIFACT_PATH=app/artifacts/risk_model.joblib
```

### Frontend

```bash
cd ../frontend
npm install
npm start
```

Create `frontend/.env`:

```bash
REACT_APP_MAPBOX_TOKEN=your_mapbox_token
```

App runs at `http://localhost:3000` and calls the API at `http://localhost:8000`.

If routes are not loading, first check:
- backend is running on port `8000`
- both Mapbox tokens are set (`backend/.env` and `frontend/.env`)

## Retrain model (optional)

If you want to regenerate the model artifact:

```bash
cd backend
source .venv/bin/activate
python train_model.py
```

This writes the `joblib` file used by the API at runtime.

## Notes

- Route options come from Mapbox; SafeStep ranks them by modeled risk.
- Some open-data sources can be noisy or temporarily incomplete, so feature coverage can vary by location/time.
- PostgreSQL/PostGIS is wired in the project setup; the core route-scoring flow mainly uses external APIs + model inference.

## Future implementations

- Better calibrated labels / confidence intervals for risk score
- More robust data source fallback and freshness tracking
- Route history and user feedback loop
- Lightweight deployment pipeline (frontend + API)

