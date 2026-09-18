import React, { useEffect, useMemo, useState } from 'react';
import Map, { Marker, NavigationControl, Source, Layer } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import './App.css';

const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN || '';
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const SF_BOUNDS = [-122.55, 37.68, -122.35, 37.84];
const INITIAL_VIEW = {
  longitude: -122.4194,
  latitude: 37.7749,
  zoom: 12,
};

function App() {
  const [startQuery, setStartQuery] = useState('');
  const [endQuery, setEndQuery] = useState('');
  const [startResults, setStartResults] = useState([]);
  const [endResults, setEndResults] = useState([]);
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [activeClickMode, setActiveClickMode] = useState('start');
  const [loading, setLoading] = useState(false);
  const [searchingStart, setSearchingStart] = useState(false);
  const [searchingEnd, setSearchingEnd] = useState(false);
  const [error, setError] = useState('');
  const [routeResult, setRouteResult] = useState(null);
  const [selectedOptionId, setSelectedOptionId] = useState(null);

  const routeOptions = routeResult?.route_options?.length
    ? routeResult.route_options
    : (routeResult ? [{
      option_id: 1,
      label: 'safest',
      risk_score: routeResult.risk_score,
      distance: routeResult.distance,
      estimated_time: routeResult.estimated_time,
      route_geometry: routeResult.route_geometry,
      waypoints: routeResult.waypoints,
      danger_summary: routeResult.danger_summary,
      hazards: routeResult.hazards || [],
      risk_segments: routeResult.risk_segments || [],
    }] : []);

  const selectedRoute = routeOptions.find((route) => route.option_id === selectedOptionId) || routeOptions[0] || null;
  const hazardSummary = useMemo(() => {
    const hazards = selectedRoute?.hazards || [];
    return {
      high: hazards.filter((h) => ['collision_hotspot', 'high_incident_density'].includes(h.type)).length,
      medium: hazards.filter((h) => ['collision_risk', 'incident_density'].includes(h.type)).length,
      lowLighting: hazards.filter((h) => h.type === 'low_lighting').length,
    };
  }, [selectedRoute]);
  const riskHeatGeoJson = useMemo(() => {
    const segments = selectedRoute?.risk_segments;
    if (!segments?.length) return null;
    return {
      type: 'FeatureCollection',
      features: segments.map((seg, idx) => ({
        type: 'Feature',
        id: idx,
        properties: { risk: seg.risk_display ?? seg.risk },
        geometry: {
          type: 'LineString',
          coordinates: seg.coordinates,
        },
      })),
    };
  }, [selectedRoute]);

  const routeFallbackGeoJson = useMemo(() => {
    if (riskHeatGeoJson) return null;
    const geometryPoints = selectedRoute?.route_geometry?.length
      ? selectedRoute.route_geometry
      : selectedRoute?.waypoints;
    if (!geometryPoints?.length) return null;
    return {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: geometryPoints.map(([lat, lng]) => [lng, lat]),
      },
      properties: {},
    };
  }, [selectedRoute, riskHeatGeoJson]);

  const hazardIconForType = (type) => {
    if (type === 'low_lighting') return { icon: '💡', bg: '#eab308', label: 'low lighting' };
    if (type === 'collision_hotspot' || type === 'collision_risk') {
      return { icon: '⚠', bg: type === 'collision_hotspot' ? '#dc2626' : '#f59e0b', label: 'collision' };
    }
    // crime / incident density
    return {
      icon: '!',
      bg: type === 'high_incident_density' ? '#dc2626' : '#f59e0b',
      label: 'crime',
    };
  };

  const routeFallbackLayer = {
    id: 'route-line-fallback',
    type: 'line',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': '#2563eb',
      'line-width': 5,
      'line-opacity': 0.85,
    },
  };

  const routeHeatLayer = {
    id: 'route-risk-heat',
    type: 'line',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-width': 9,
      'line-opacity': 0.92,
      'line-color': [
        'interpolate',
        ['linear'],
        ['get', 'risk'],
        0,
        '#15803d',
        0.35,
        '#84cc16',
        0.55,
        '#eab308',
        0.75,
        '#f97316',
        1,
        '#991b1b',
      ],
    },
  };

  const searchAddress = async (query, target) => {
    if (!MAPBOX_TOKEN) {
      setError('missing mapbox token. set REACT_APP_MAPBOX_TOKEN in frontend/.env');
      return;
    }
    if (!query.trim()) return;

    const encoded = encodeURIComponent(query.trim());
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encoded}.json?access_token=${MAPBOX_TOKEN}&autocomplete=true&limit=5&bbox=${SF_BOUNDS.join(',')}&proximity=-122.4194,37.7749`;
    if (target === 'start') setSearchingStart(true);
    if (target === 'end') setSearchingEnd(true);

    try {
      const response = await fetch(url);
      if (!response.ok) {
        setError('could not search address right now');
        return;
      }
      const data = await response.json();
      const features = data.features || [];
      if (target === 'start') setStartResults(features);
      if (target === 'end') setEndResults(features);
    } catch (err) {
      setError('network error while searching addresses');
    } finally {
      if (target === 'start') setSearchingStart(false);
      if (target === 'end') setSearchingEnd(false);
    }
  };

  useEffect(() => {
    if (!startQuery.trim()) {
      setStartResults([]);
      return undefined;
    }
    // don't re-open dropdown after a place is already selected
    if (startPoint?.label === startQuery) {
      setStartResults([]);
      return undefined;
    }

    const timer = setTimeout(() => {
      searchAddress(startQuery, 'start');
    }, 250);

    return () => clearTimeout(timer);
  }, [startQuery, startPoint]);

  useEffect(() => {
    if (!endQuery.trim()) {
      setEndResults([]);
      return undefined;
    }
    // don't re-open dropdown after a place is already selected
    if (endPoint?.label === endQuery) {
      setEndResults([]);
      return undefined;
    }

    const timer = setTimeout(() => {
      searchAddress(endQuery, 'end');
    }, 250);

    return () => clearTimeout(timer);
  }, [endQuery, endPoint]);

  const selectPlace = (feature, target) => {
    const [lng, lat] = feature.center;
    const selected = {
      lat,
      lng,
      label: feature.place_name,
    };
    if (target === 'start') {
      setStartPoint(selected);
      setStartQuery(feature.place_name);
      setStartResults([]);
      setEndResults([]);
      setActiveClickMode('end');
    } else {
      setEndPoint(selected);
      setEndQuery(feature.place_name);
      setEndResults([]);
      setStartResults([]);
    }
  };

  const onMapClick = (event) => {
    const { lat, lng } = event.lngLat;
    const point = { lat, lng, label: `${lat.toFixed(5)}, ${lng.toFixed(5)}` };
    if (activeClickMode === 'start') {
      setStartPoint(point);
      setStartQuery(point.label);
      setStartResults([]);
      setActiveClickMode('end');
    } else {
      setEndPoint(point);
      setEndQuery(point.label);
      setEndResults([]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setRouteResult(null);

    if (!startPoint || !endPoint) {
      setError('pick both start and destination first');
      return;
    }

    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/routes/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_lat: startPoint.lat,
          start_lng: startPoint.lng,
          end_lat: endPoint.lat,
          end_lng: endPoint.lng,
        }),
      });
      if (!response.ok) {
        setError('could not calculate route, please try again');
        return;
      }
      const data = await response.json();
      setRouteResult(data);
      setSelectedOptionId(data?.route_options?.[0]?.option_id || 1);
    } catch (err) {
      setError('network error while calling the api');
    } finally {
      setLoading(false);
    }
  };

  const clearRoute = () => {
    setRouteResult(null);
    setSelectedOptionId(null);
    setError('');
  };

  const formatMetersToMiles = (meters) => {
    if (!meters && meters !== 0) return '';
    const miles = meters / 1609.344;
    return `${miles.toFixed(2)} mi`;
  };

  const formatSecondsToMinutes = (seconds) => {
    if (!seconds && seconds !== 0) return '';
    const minutes = seconds / 60;
    if (minutes < 1) return `${seconds.toFixed(0)} s`;
    return `${minutes.toFixed(1)} min`;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        {/* header with app title */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-3xl font-bold text-gray-900">
            SafeStep
          </h1>
          <p className="text-gray-600 mt-1">
            AI Safety Route Navigator for San Francisco
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-1 bg-white rounded-lg shadow p-5">
          <h2 className="text-xl font-semibold text-gray-800 mb-3">
            Route Planner
          </h2>
          <p className="text-sm text-gray-600 mb-4">
            search for places like google maps, or click the map to set points.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">start</label>
              <div className="relative">
                <input
                  type="text"
                  value={startQuery}
                  onChange={(e) => {
                    setStartQuery(e.target.value);
                    setStartPoint(null);
                  }}
                  placeholder="e.g. Ferry Building, San Francisco"
                  className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm p-2"
                />
                {searchingStart && (
                  <span className="absolute right-3 top-2 text-xs text-gray-400">searching...</span>
                )}
              </div>
              {startResults.length > 0 && (
                <div className="mt-2 border rounded-md max-h-36 overflow-y-auto">
                  {startResults.map((place) => (
                    <button
                      key={place.id}
                      type="button"
                      onClick={() => selectPlace(place, 'start')}
                      className="w-full text-left text-sm px-3 py-2 hover:bg-gray-50 border-b last:border-b-0"
                    >
                      {place.place_name}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">destination</label>
              <div className="relative">
                <input
                  type="text"
                  value={endQuery}
                  onChange={(e) => {
                    setEndQuery(e.target.value);
                    setEndPoint(null);
                  }}
                  placeholder="e.g. Dolores Park, San Francisco"
                  className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm p-2"
                />
                {searchingEnd && (
                  <span className="absolute right-3 top-2 text-xs text-gray-400">searching...</span>
                )}
              </div>
              {endResults.length > 0 && (
                <div className="mt-2 border rounded-md max-h-36 overflow-y-auto">
                  {endResults.map((place) => (
                    <button
                      key={place.id}
                      type="button"
                      onClick={() => selectPlace(place, 'end')}
                      className="w-full text-left text-sm px-3 py-2 hover:bg-gray-50 border-b last:border-b-0"
                    >
                      {place.place_name}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="text-xs text-gray-500">
              click mode: <span className="font-medium">{activeClickMode}</span>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setActiveClickMode('start')}
                className="px-3 py-2 text-sm rounded-md bg-gray-100 hover:bg-gray-200"
              >
                set start by click
              </button>
              <button
                type="button"
                onClick={() => setActiveClickMode('end')}
                className="px-3 py-2 text-sm rounded-md bg-gray-100 hover:bg-gray-200"
              >
                set destination by click
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {loading ? 'calculating...' : 'calculate safest route'}
              </button>
              <button
                type="button"
                onClick={clearRoute}
                className="px-3 py-2 text-sm rounded-md bg-gray-100 hover:bg-gray-200"
              >
                clear
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {routeResult && !error && (
            <div className="mt-6 border-t pt-4 grid grid-cols-1 gap-3 text-sm">
              {routeOptions.length > 0 && (
                <div className="bg-gray-50 rounded-md p-3">
                  <p className="text-gray-500 mb-2">Route Options</p>
                  <div className="grid grid-cols-1 gap-2">
                    {routeOptions.map((option) => {
                      const isSelected = selectedRoute?.option_id === option.option_id;
                      return (
                        <button
                          key={option.option_id}
                          type="button"
                          onClick={() => setSelectedOptionId(option.option_id)}
                          className={`text-left rounded-md border px-3 py-2 ${isSelected ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:bg-gray-50'}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-medium capitalize">{option.label}</span>
                            <span className="text-xs text-gray-500">
                              {(option.risk_score * 100).toFixed(0)}% risk
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-gray-600">
                            {formatMetersToMiles(option.distance)} • {formatSecondsToMinutes(option.estimated_time)}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              <div className="bg-gray-50 rounded-md p-3">
                <p className="text-gray-500">distance</p>
                <p className="mt-1 text-lg font-semibold text-gray-900">
                  {selectedRoute?.distance != null ? formatMetersToMiles(selectedRoute.distance) : 'n/a'}
                </p>
              </div>
              <div className="bg-gray-50 rounded-md p-3">
                <p className="text-gray-500">estimated walk time</p>
                <p className="mt-1 text-lg font-semibold text-gray-900">
                  {selectedRoute?.estimated_time != null
                    ? formatSecondsToMinutes(selectedRoute.estimated_time)
                    : 'n/a'}
                </p>
              </div>
              <div className="bg-gray-50 rounded-md p-3">
                <p className="text-gray-500">Hazard Breakdown</p>
                <div className="mt-2 space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-gray-700">
                      <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-600" />
                      <span>high-risk clusters</span>
                    </div>
                    <span className="font-medium text-gray-900">{hazardSummary.high}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-gray-700">
                      <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-500" />
                      <span>moderate caution spots</span>
                    </div>
                    <span className="font-medium text-gray-900">{hazardSummary.medium}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-gray-700">
                      <span className="inline-block w-2.5 h-2.5 rounded-full bg-yellow-400" />
                      <span>low-light segments</span>
                    </div>
                    <span className="font-medium text-gray-900">{hazardSummary.lowLighting}</span>
                  </div>
                </div>
                {(selectedRoute?.hazards?.length || 0) === 0 && (
                  <p className="mt-2 text-xs text-gray-500">no major hazard clusters detected on sampled segments</p>
                )}
              </div>
            </div>
          )}
        </section>

        <section className="lg:col-span-2 bg-white rounded-lg shadow overflow-hidden">
          {!MAPBOX_TOKEN && (
            <div className="p-4 bg-amber-50 text-amber-700 text-sm border-b">
              add `REACT_APP_MAPBOX_TOKEN=your_token` to `frontend/.env` to load the map.
            </div>
          )}
          <div className="h-[620px] relative">
            <Map
              mapboxAccessToken={MAPBOX_TOKEN}
              initialViewState={INITIAL_VIEW}
              mapStyle="mapbox://styles/mapbox/streets-v12"
              onClick={onMapClick}
              maxBounds={SF_BOUNDS}
            >
              <NavigationControl position="top-right" />
              {startPoint && (
                <Marker longitude={startPoint.lng} latitude={startPoint.lat} color="#16a34a" />
              )}
              {endPoint && (
                <Marker longitude={endPoint.lng} latitude={endPoint.lat} color="#dc2626" />
              )}
              {riskHeatGeoJson && (
                <Source id="route-risk-heat" type="geojson" data={riskHeatGeoJson}>
                  <Layer {...routeHeatLayer} />
                </Source>
              )}
              {routeFallbackGeoJson && (
                <Source id="route-fallback" type="geojson" data={routeFallbackGeoJson}>
                  <Layer {...routeFallbackLayer} />
                </Source>
              )}
              {(selectedRoute?.hazards || []).map((hazard, idx) => {
                const style = hazardIconForType(hazard.type);
                return (
                  <Marker
                    key={`${hazard.type}-${hazard.lat}-${hazard.lng}-${idx}`}
                    longitude={hazard.lng}
                    latitude={hazard.lat}
                    anchor="center"
                  >
                    <div
                      title={hazard.message || style.label}
                      className="flex items-center justify-center rounded-full border-2 border-white shadow-md"
                      style={{
                        width: 24,
                        height: 24,
                        backgroundColor: style.bg,
                        color: '#fff',
                        fontSize: style.icon === '!' ? 14 : 12,
                        fontWeight: 700,
                        lineHeight: 1,
                      }}
                    >
                      {style.icon}
                    </div>
                  </Marker>
                );
              })}
            </Map>
            {riskHeatGeoJson && (
              <div className="absolute bottom-8 left-4 w-72 rounded-md bg-white/95 px-3 py-2 text-xs text-gray-700 shadow border border-gray-200">
                <p className="font-medium text-gray-800">Route Legend</p>
                <div className="mt-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Path risk</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-[11px] text-gray-500">lower</span>
                    <div className="flex-1 flex items-center gap-1">
                      <span className="inline-block h-1.5 flex-1 bg-green-700 rounded-sm" />
                      <span className="inline-block h-1.5 flex-1 bg-lime-500 rounded-sm" />
                      <span className="inline-block h-1.5 flex-1 bg-yellow-500 rounded-sm" />
                      <span className="inline-block h-1.5 flex-1 bg-orange-500 rounded-sm" />
                      <span className="inline-block h-1.5 flex-1 bg-red-800 rounded-sm" />
                    </div>
                    <span className="text-[11px] text-gray-500">higher</span>
                  </div>
                </div>
                <div className="mt-2 border-t border-gray-200 pt-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500">Hazard pins</p>
                  <div className="mt-1 space-y-1 text-gray-600">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-600 text-white text-[11px] font-bold border border-white shadow-sm">!</span>
                      <span>crime / incidents</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-500 text-white text-[10px] border border-white shadow-sm">⚠</span>
                      <span>collisions</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-yellow-400 text-[11px] border border-white shadow-sm">💡</span>
                      <span>low lighting</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;

