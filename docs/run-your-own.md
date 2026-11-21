# Run your own

You can run the same connector the public service runs. You need Docker (or Python 3.11) and a
data folder.

## 1. Get the code

```bash
git clone https://github.com/fuzzzy-bot/fuzzzy-law.git
cd fuzzzy-law/backend
```

## 2. A data folder

The data files are not in the repository. For a first run, write a small sample from the test
fixtures (a few real articles of three laws, their earlier wordings and a few court decisions):

```bash
python3.11 -m venv .venv
.venv/bin/pip install --no-deps -r requirements-connector.txt -r requirements-dev.txt
.venv/bin/python scripts/make_sample_data.py sample-data
```

The full data is built by the pipeline in `law_corpus/` from the official sites, slowly and
politely (one request at a time, at least 10 seconds apart, so a full build takes many hours):
`law_history.py fetch` and `build` for earlier wordings, `daily_refresh.py --add-law <law>` to add a
law to the store, and the court collection scripts with `build_court_store.py`. See the docstring at
the top of each script and [architecture](architecture.md).

## 3. Build and run the image

```bash
docker build -f Dockerfile.connector -t fuzzzy-law-connector:local .
docker run --rm -p 127.0.0.1:8050:8000 \
  -e CONNECTOR_DATA_DIR=/data -v "$PWD/sample-data:/data:ro" \
  fuzzzy-law-connector:local
```

Check it:

```bash
curl -s localhost:8050/healthz
curl -s 'localhost:8050/api/v1/connector/articles?code=labour_code&article=48' | head -c 300
npx @modelcontextprotocol/inspector --cli http://localhost:8050/mcp --transport http --method tools/list
```

The tools list should be the same 12 tools the public service lists.

Without Docker: `CONNECTOR_DATA_DIR=sample-data .venv/bin/uvicorn app.connector_main:app --port 8050`.

## 4. Like the public service

`docker-compose.connector.yml` runs the connector read-only with a memory limit on a local port, and
the daily refresh as a one-shot job:

```bash
# connector.env holds CONNECTOR_DATA_PATH, CONNECTOR_WORK_PATH and the public URL
docker compose --env-file connector.env -f docker-compose.connector.yml up -d connector
docker compose --env-file connector.env -f docker-compose.connector.yml --profile refresh run --rm refresh
```

Put nginx in front for HTTPS (`scripts/nginx.connector.conf.example`, log rotation in
`scripts/logrotate.connector.example`) and start the refresh from cron once a day. All settings are
listed in the [technical reference](../connector/README.md#settings-environment).

## Tests

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check .
cd ../law_corpus && python3.11 -m venv .venv \
  && .venv/bin/pip install --no-deps -r requirements-refresh.txt -r requirements-dev.txt \
  && .venv/bin/pytest && .venv/bin/ruff check .
```
