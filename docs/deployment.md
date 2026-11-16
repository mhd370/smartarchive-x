# Deploying SmartArchive-X on a public server

The API runs in a Docker container on Railway (or Render). The web interface runs on Netlify, which forwards
`/api/*` to the API server-side, so the browser talks to one address and sessions stay first-party.

## API on Railway (Hobby plan)
1. New Project → Deploy from GitHub repo → this repository. Railway builds `Dockerfile` (`railway.toml`).
2. Volume: right-click the service → Attach Volume, mount path `/data`. Without it, documents and accounts are
   lost on every restart.
3. Variables:
   - `SMARTARCHIVE_CORS_ORIGINS` = the Netlify address, for example `https://smartarchive-x-kareem.netlify.app`;
   - `SMARTARCHIVE_SETUP_TOKEN` = a secret code you choose. The first-run page asks for it before anyone can
     create the first admin, so a stranger who opens the site first cannot take it over. You can remove the
     variable after the admin exists.
4. Settings → Networking → Generate Domain (port 10000). Wait until the deployment is Active.

Memory: OCR and the classifiers need about 1 GB. The image fetches the pinned Arabic Tesseract models at build
time (`tools/fetch_ocr_models.py`). The learned classifier starts untrained: train it from the System page after
people have confirmed some categories; until then keyword classification is used.

## Interface on Netlify
Run `results\claude_checks\s26_netlify.cmd` (or, in `frontend`, set `SMARTARCHIVE_API_ORIGIN` to the API
address and run `npx.cmd netlify-cli deploy --build --prod`). `SMARTARCHIVE_API_ORIGIN` is read at build time
by `next.config.ts`, so redeploy the interface when the API address changes.

## Checking
- `https://<api>/api/health` returns JSON with `status`.
- Open the Netlify address, enter the setup code, create the admin, upload a scanned page and search for a word.
