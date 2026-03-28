# Lost & Found Connect (Map-based Website)

A standalone Flask website for reporting lost and found items (like **e-scooters, cycles, and mobiles**) and connecting people by **location proximity**.

## New features added

- **User authentication**
  - local register/login/logout
  - Google OAuth Sign-In (ID token flow)
  - session token via cookie and bearer token
  - posting items and uploading images require login
- **Image uploads with pluggable storage**
  - local filesystem storage (default)
  - Cloudinary storage
  - Amazon S3 storage
  - upload item photos (`jpg`, `jpeg`, `png`, `webp`, `gif`)
- **Quick contact actions**
  - WhatsApp chat button (`wa.me`)
  - Email button (`mailto`) if owner email is available
- **Deploy support**
  - Render config (`render.yaml`)
  - Railway-friendly `Procfile`
  - Vercel serverless adapter (`vercel.json`, `vercel_api/index.py`)
  - backend host/public URL support via environment variables

## Existing core features

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
python3 -m venv .venv
source .venv/bin/activate
pip install -r lost_and_found_web/requirements.txt
python3 -m lost_and_found_web.app
```

Then open:

`http://127.0.0.1:5000`

## Environment variables

Copy and edit:

```bash
cp lost_and_found_web/.env.example lost_and_found_web/.env
```

Supported variables:

- `SECRET_KEY` - Flask secret for sessions/cookies
- `BACKEND_PUBLIC_URL` - optional absolute backend base URL (used in generated local file URLs)
- `DATABASE_PATH` - optional override for sqlite path
- `UPLOAD_FOLDER` - optional override for upload storage path
- `MAX_UPLOAD_MB` - optional upload size limit in MB (default: 8)
- `GOOGLE_CLIENT_ID` - required for Google Sign-In
- `STORAGE_PROVIDER` - `local` (default), `cloudinary`, or `s3`
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_FOLDER` (Cloudinary mode)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`, `S3_KEY_PREFIX` (S3 mode)

## API endpoints

### Auth

- `POST /api/auth/register`
  - JSON: `name`, `email`, `password`
- `POST /api/auth/login`
  - JSON: `email`, `password`
- `POST /api/auth/google`
  - JSON: `credential` (Google ID token)
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/config`

### Uploads

- `POST /api/uploads`
  - multipart form-data key: `image`
  - requires authenticated session

### Items

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
    - `image_filename` (optional, returned by `/api/uploads`)
    - `image_url` (optional, returned by `/api/uploads`)
  - requires authenticated session
- `GET /api/items/<item_id>/matches`
  - Query params (optional): `distance_km` (default 8), `time_days` (default 14)

## Deploy options

### Render

- `render.yaml` is included.
- Service root is `lost_and_found_web`.

### Railway

- `Procfile` is included:
  - `web: gunicorn -b 0.0.0.0:$PORT lost_and_found_web.wsgi:app`

### Vercel

- `vercel.json` and `vercel_api/index.py` are included.
- For production, prefer external object storage for uploads because serverless file systems are ephemeral.

## Google OAuth setup

1. Create OAuth client in Google Cloud Console for your app origin.
2. Add your app URL to authorized JavaScript origins.
3. Set `GOOGLE_CLIENT_ID` in environment.
4. Reload app and use **Continue with Google**.

## Cloud image storage setup

### Cloudinary

Set:

- `STORAGE_PROVIDER=cloudinary`
- `CLOUDINARY_CLOUD_NAME=...`
- `CLOUDINARY_API_KEY=...`
- `CLOUDINARY_API_SECRET=...`

### S3

Set:

- `STORAGE_PROVIDER=s3`
- `AWS_ACCESS_KEY_ID=...`
- `AWS_SECRET_ACCESS_KEY=...`
- `AWS_REGION=...`
- `S3_BUCKET_NAME=...`

Keep `STORAGE_PROVIDER=local` for development.

## Notes

- Data is stored in `lost_and_found_web/data/lost_and_found.db` by default.
- Uploaded images are stored in `lost_and_found_web/uploads/`.
- This app is intentionally isolated from the existing coding-showcase modules in this repository.
