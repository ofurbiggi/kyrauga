# Kýrauga Architecture Overview

## 1. Project Overview

Kýrauga is currently a personal photography platform built as a Django and Wagtail monolith.

The project combines:

- A Wagtail CMS backend
- Server-rendered frontend templates
- A custom Dropbox-to-Wagtail media import workflow
- A simple deployment model aimed at Heroku-style hosting

The current implementation favors:

- Editorial control through Wagtail
- A single deployable application
- Incremental experimentation without introducing extra services too early

---

## 2. High-Level Architecture

Current production-oriented architecture:

            ┌──────────────────────┐
            │   Django / Wagtail   │
            │   App + Frontend UI  │
            └─────────┬────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
┌─────────▼──────────┐   ┌────────▼─────────┐
│  PostgreSQL        │   │ Static + Media   │
│  (via DATABASE_URL)│   │ Static: WhiteNoise│
│  in production     │   │ Media: local file │
└────────────────────┘   │ storage           │
                         └───────────────────┘

Current local development architecture:

- SQLite by default
- Local filesystem for uploaded media
- Django development server for app, static files, and media files

---

## 3. Core Stack

### Backend + Frontend

- **Framework:** Django 6.0.3
- **CMS:** Wagtail 7.3rc1
- **Language:** Python
- **Templating:** Django Templates
- **Styling:** Tailwind CSS plus legacy custom CSS/Sass
- **JavaScript:** Small amounts of vanilla JavaScript

The frontend is rendered directly by Django and Wagtail. There is no separate frontend application.

### Supporting Dependencies

- **Database URL parsing:** `dj-database-url`
- **Static file serving:** WhiteNoise
- **Image handling:** Pillow, pillow-heif, Willow
- **Filtering:** `django-filter`
- **API library present but not yet used:** Django REST Framework

---

## 4. Repository Structure

Current top-level app structure:

```text
config/
  settings/
    base.py
    dev.py
    production.py
home/
search/
media_importer/
docs/
```

### App Responsibilities

- `config`: project settings, URL routing, shared templates, and shared static assets
- `home`: homepage page model, homepage templates, and site-specific frontend assets
- `search`: Wagtail page search view and template
- `media_importer`: Dropbox import UI, Dropbox integration, and import tracking models

---

## 5. Backend Architecture

Wagtail currently handles:

- Page routing and page serving
- Admin/editor interface
- Built-in image and document management
- Search through Wagtail's database search backend

### Current Content Model

The current content model is still minimal:

- `HomePage` exists as a Wagtail `Page`
- No StreamField-based flexible block system is implemented yet
- No public API or GraphQL layer is implemented

This means the architecture is ready for richer editorial modeling, but the codebase is still in an early content-model phase.

---

## 6. Frontend Architecture

### Rendering

- Server-side rendering through Django templates
- Wagtail page models map to templates
- Shared layout is defined in the project templates

### Styling

The frontend currently uses a mixed styling setup:

- Tailwind CSS compiled through PostCSS
- Existing custom CSS
- Existing Sass-based stylesheet assets

This is best described as a transition toward Tailwind rather than a fully Tailwind-only frontend.

### JavaScript

- Vanilla JavaScript for lightweight behavior
- No separate SPA frontend or heavy client-side framework

---

## 7. Media and Asset Workflow

### Current Storage Strategy

| Type   | Current storage                    | Delivery |
| ------ | ---------------------------------- | -------- |
| Media  | Django local filesystem storage    | Django   |
| Static | WhiteNoise static file storage     | Django   |

### Current Media Workflow

1. Photos are prepared outside the application.
2. Files are placed in a Dropbox "to publish" folder.
3. Editors use a custom Wagtail admin screen to browse Dropbox files.
4. Selected files are downloaded into Wagtail as image objects.
5. Imported files are tracked in the database to avoid duplicate imports.
6. Imported Dropbox files are moved to a published folder in Dropbox.

### Media Importer Details

The `media_importer` app currently provides:

- A custom Wagtail admin menu item
- A Dropbox-backed import screen
- OAuth helper flow support
- Import history tracking through the `ImportedDropboxAsset` model

This Dropbox integration is one of the most concrete custom architecture pieces in the repository today.

---

## 8. Infrastructure and Deployment

### Current Deployment Shape

- **Hosting target:** Heroku-style deployment
- **Web server:** Gunicorn
- **Release phase:** database migrations via Procfile
- **Static files:** WhiteNoise in production

### Runtime Configuration

- Base settings default to SQLite
- Production switches to `DATABASE_URL` when present
- Production enables WhiteNoise middleware and manifest static storage

### Container Support

The repository also includes a Dockerfile for containerized runs, currently based on Python 3.12.

---

## 9. Environment Variables

Current environment variables used by the codebase include:

- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `DEBUG`
- `DROPBOX_APP_KEY`
- `DROPBOX_APP_SECRET`
- `DROPBOX_REDIRECT_URI`
- `DROPBOX_TO_PUBLISH_FOLDER`
- `DROPBOX_PUBLISHED_FOLDER`

The project also loads `.env.local` from the repository root for local development.

---

## 10. Search and Routing

### Routing

The project routes:

- Django admin under `django-admin/`
- Wagtail admin under `admin/`
- Wagtail documents under `documents/`
- Search under `search/`
- Dropbox importer views under custom admin URLs
- All remaining page routes through Wagtail page serving

### Search

Search is currently implemented with:

- A custom `search` app view
- Wagtail's database search backend
- Standard paginated search results

---

## 11. Testing and Delivery State

### Current Testing

- Homepage tests exist
- The media importer app has only placeholder tests at the moment

### CI/CD

- A GitHub Actions workflow is not currently present in the repository
- Deployment automation may exist outside the repo, but it is not represented in the checked-in code

---

## 12. Design and Engineering Direction

The current implementation reflects these priorities:

- Keep the system simple and monolithic
- Build editorial features directly inside Wagtail
- Support a photography-centered workflow first
- Leave room for richer content modeling later

---

## 13. Planned or Possible Future Work

These ideas are not implemented in the current codebase, but they fit the project direction:

- Cloudflare CDN integration
- Cloudflare R2 or another remote media storage backend
- Richer page models and StreamField-based editorial blocks
- More advanced homepage editing tools
- Public API layer
- Decoupled frontend experiments
- More interactive map and multimedia experiences

These should be treated as roadmap possibilities, not current architecture.
