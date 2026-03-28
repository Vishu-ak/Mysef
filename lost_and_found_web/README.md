# Lost & Found Connect (Map-based Website)

A standalone Flask website for reporting lost and found items (like **e-scooters, cycles, and mobiles**) and connecting people by **location proximity**.

## Features

- Post **lost** or **found** items with:
  - category
  - title and description
  - contact details
  - optional location label
  - exact map coordinates
- Interactive **map pinning**:
  - click map to place pin
  - use browser geolocation
- Search and filter:
  - by type (lost/found)
  - by category
  - by text
  - by radius near a center point
- Match engine:
  - compares opposite type (lost vs found)
  - same category
  - within configurable distance/time windows

## Tech stack

- Python 3.10+
- Flask
- SQLite
- Leaflet + OpenStreetMap tiles

## Run locally

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r lost_and_found_web/requirements.txt
python -m lost_and_found_web.app
```

Then open:

`http://127.0.0.1:5000`

## API endpoints

- `GET /api/items`
  - Query params (optional): `type`, `category`, `q`, `lat`, `lon`, `radius_km`
- `POST /api/items`
  - JSON body:
    - `item_type` (`lost` or `found`)
    - `category`
    - `title`
    - `description`
    - `contact_name`
    - `contact_phone`
    - `lat`
    - `lon`
    - `location_label` (optional)
    - `reward_note` (optional)
- `GET /api/items/<item_id>/matches`
  - Query params (optional): `distance_km` (default 8), `time_days` (default 14)

## Notes

- Data is stored in `lost_and_found_web/data/lost_and_found.db`.
- This app is intentionally isolated from the existing coding-showcase modules in this repository.
