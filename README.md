# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route. It generates three routes, checks the forecast at each checkpoint **at the time the truck will actually be there**, scores the risk with the load rules, and recommends the best route.

## Features

- Inputs: origin, destination, departure date/time, load weight (lb), checkpoint spacing (10 / 25 / 50 miles).
- 3 route options (OSRM). Each shows distance, travel time, arrival time, road summary and a risk bar.
- Weather checkpoints with per-checkpoint ETA, wind, rain, snow and risk level.
- Recommendation with a plain-English reason.
- Map with all routes, risk-coloured checkpoints and popups.
- Weather heatmap along the corridor with a 0-48 hour forecast slider (and a play button).

## How it works

```
React (Vite, react-leaflet)  --POST /api/plan-->  Django
                                                   |- Nominatim   geocoding
                                                   |- OSRM        3 routes + per-segment time
                                                   '- Open-Meteo  hourly wind / rain / snow
```

One request does everything:

1. Geocode origin and destination.
2. Get routes from OSRM. If it returns fewer than 3 distinct routes, extra ones are requested through a via-point on each side of the main route (rejecting duplicates and detours over 30% longer).
3. Place checkpoints every N miles along each route (always including start and end).
4. ETA at each checkpoint = departure + cumulative driving time up to that point (OSRM per-segment durations x 1.10 truck factor).
5. Fetch the hourly forecast for all points in **batched, parallel, cached** Open-Meteo calls, and read the hour closest to each ETA.
6. Classify each checkpoint, aggregate per route, rank routes.

### Code map

| File | Purpose |
| --- | --- |
| `backend/routing/risk.py` | Risk thresholds and load rules (pure functions) |
| `backend/routing/planner.py` | Checkpoints, ETAs, route stats, ranking and recommendation |
| `backend/routing/providers.py` | Geocoding, routing and weather API clients, caching |
| `backend/routing/geo.py` | Polyline helpers |
| `backend/routing/views.py` | `POST /api/plan`, validation |
| `backend/routing/tests/` | Unit tests for rules, ETA timing and ranking |
| `frontend/src/components/` | Form, route cards, checkpoint table, map, heat slider |
| `frontend/src/lib/corridor.js` | Pre-computes the heatmap corridor so the slider is instant |

## Risk rules

Levels: Low 0, Moderate 1, High 2, Severe 3, No Travel 4. A checkpoint's level is the worst of wind, rain and snow.

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | <25 | 25-34 | 35-44 | 45-54 | >=55 |
| Rain (in/hr) | <0.10 | 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5-1.0 | 1.0-2.0 | 2.0-3.0 | >3.0 |

Load rules (applied to wind): >=55 mph is No Travel for any load; 45-54 mph with a load over 30,000 lb is No Travel; 35-44 mph with a load over 40,000 lb is Severe.

Edge values: wind bands are exclusive on the upper side (35 mph is High). For rain and snow, a value exactly on a shared edge (for example 0.25) goes to the lower band, because the table shows it as the end of that band.

## Recommendation

Each checkpoint "owns" the miles halfway to its neighbours, so risk is measured in **miles** per level. Routes are ranked by:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk (mile-weighted)
4. Shortest travel time

Two practical choices on top of the brief:

- **No Travel miles are checked first.** A route you are not allowed to drive should never win.
- **Small gaps count as ties** (under 1 mile, or 0.05 average risk). Otherwise a 0.3-mile difference in weather would beat a route that is hours faster.

If every route has No Travel weather, the least bad route is shown with a warning to consider changing the departure time.

## Heatmap

The backend returns, for samples every ~10+ miles along each route, the risk level for each of the 49 hours (0-48) after departure. The browser cuts each route into short chunks and blends the two nearest samples, so dragging the slider only changes colours (no network calls, no geometry rebuild). Chunks are drawn on a dedicated canvas pane with a CSS blur to make a smooth corridor.

## Assumptions and limits

- Free APIs, no keys needed. The public OSRM and Nominatim servers are for light use; for heavy traffic use your own instances (`OSRM_URL`, `NOMINATIM_URL` env vars).
- OSRM times are for cars, so a 1.10 factor is applied for trucks. It does not know about truck restrictions (height, weight, hazmat).
- Weather uses sustained 10 m wind speed (not gusts), hourly rain, and snowfall depth converted to in/hr.
- Open-Meteo forecasts reach 16 days. Checkpoints beyond the data are clamped and flagged "forecast not available".
- Times in the UI use your browser's time zone.
- The first request for a long trip can take 10-20 s; repeats are served from a 30-minute weather cache.

## Run locally

Requires Python 3.10+ and Node 18+.

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py test          # 21 tests
python manage.py runserver     # http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                    # http://localhost:5173 (proxies /api to Django)
```

### API

`POST /api/plan`

```json
{ "origin": "Chicago, IL", "destination": "Dallas, TX", "departure": "2026-01-10T14:00:00Z", "load_lb": 35000, "interval_miles": 25 }
```

Returns `routes[]` (geometry, stats, checkpoints, heat), `recommended_index` and `recommendation_reason`.

## Deploy

One Docker image serves both the API and the built React app.

**Render (free):** push this repo to GitHub, create a new Blueprint on Render and select the repo. `render.yaml` does the rest.

**Any Docker host:** `docker build -t truck-routing . && docker run -p 8000:8000 truck-routing`

Env vars: `DJANGO_SECRET_KEY` (set in production), `DJANGO_ALLOWED_HOSTS` (default `*`).
