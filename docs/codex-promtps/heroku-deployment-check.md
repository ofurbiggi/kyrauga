Please run a full deployment-readiness sweep for this Wagtail/Django project before deploying to Heroku.

Context:
This is the Kýrauga project, a pure Wagtail/Django site deployed on Heroku, using:

- Python 3.13
- Heroku Postgres
- WhiteNoise for static files
- Tailwind CSS v3
- Cloudflare/custom domain setup
- Django settings split into base/dev/production where applicable

Goal:
Check whether the project is ready to deploy safely to Heroku.

Please inspect and verify:

1. Django/Wagtail config

- Correct DJANGO_SETTINGS_MODULE for production
- ALLOWED_HOSTS includes production domains
- CSRF_TRUSTED_ORIGINS is correctly configured
- DEBUG is false in production
- SECRET_KEY is environment-based
- database config works with Heroku Postgres
- static/media settings are production-safe
- Wagtail admin and site settings look sane

2. Heroku deployment files

- Procfile exists and points to the correct WSGI app
- runtime.txt or .python-version is correct if used
- requirements / pyproject / uv setup is consistent
- release phase is correct if migrations are run there
- no missing production dependencies

3. Static files and frontend

- Tailwind build works
- CSS output is committed or generated correctly for Heroku
- collectstatic works
- WhiteNoise config is correct
- no references to missing static files

4. Migrations and database

- makemigrations reports no unexpected changes
- migrations apply cleanly
- no migration conflicts
- Wagtail system checks pass

5. Environment variables

- List required env vars without exposing secrets
- Identify missing or suspicious env vars
- Check that local examples/documentation match production needs

6. Tests and checks
   Run the relevant commands, for example:

- python manage.py check
- python manage.py check --deploy
- python manage.py makemigrations --check --dry-run
- python manage.py migrate
- python manage.py test
- npm install if needed
- npm run build:css or the project’s actual CSS build command
- python manage.py collectstatic --noinput

7. Code quality / obvious risks

- Look for hardcoded local paths
- Look for DEBUG-only assumptions
- Look for references to missing templates/static files
- Look for import errors
- Look for settings that will fail on Heroku’s ephemeral filesystem
- Look for accidentally committed secrets

8. Output format
   Please return:

- ✅ Ready to deploy / ⚠️ Not ready
- A short summary
- A checklist of passed checks
- A list of blockers
- A list of warnings or follow-up improvements
- Exact file changes made, if any
- Exact commands run and their results

Important:
Do not deploy.
Do not change secrets.
Do not remove existing functionality unless clearly broken.
If you make fixes, keep them minimal and explain why.
