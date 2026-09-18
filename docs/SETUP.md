# Setup and Daily Use

Use Python 3.12 and a virtual environment. This project does not require MySQL, XAMPP, Docker, a GPU, or purchased hardware for simulation. The saved dataset contains 10,800 simulated records and is small enough for a normal laptop.

## Windows Command Prompt

```bat
cd /d E:\cold_chain_project_complete
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

On later runs, only the final command is needed. The launcher creates `runtime/operator.json` containing the local operator token and `runtime/cold_chain.db` containing data. Keep those files private. They are excluded from the deliverable archive and version control. The database persists across normal application restarts.

## Linux or macOS

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

The launcher builds the static asset directory by copying the source files. For a separate JavaScript syntax/build check, run `npm run build` in `dashboard/`. No npm dependencies are needed for the dashboard itself.

## Independent HTTP simulator

The original entry point and scenario names work with the replacement client:

```bat
.venv\Scripts\python.exe simulator\simulator.py --register --scenario primary_fault --interval 2
```

Start `run.py` first. `--register` uses the locally created operator credential once, stores a separate simulator token privately under `runtime/`, and reuses it on later runs. `primary_fault` maps to `primary_failure`; `critical_fault` maps to the primary-plus-backup failure scenario. Both now use the same local interlocks as firmware. The client runs until Ctrl+C unless `--samples` is set.

For explicit device registration instead:

Keep the backend running, then open another terminal:

```bat
.venv\Scripts\python.exe scripts\register_device.py --id CCU-SIM-EXTERNAL --mode SIMULATION
```

Enter the operator token at the hidden prompt. Registration returns a separate device token once. Set it in this terminal only:

```bat
set CC_DEVICE_TOKEN=PASTE_THE_RETURNED_DEVICE_TOKEN
.venv\Scripts\python.exe -m simulator.client --device-id CCU-SIM-EXTERNAL --scenario backup_failure --samples 120
```

The independent client defaults to a real five-second sampling interval. The dashboard's built-in demonstration instead runs at 5 times speed. Both use the same Pydantic wire schema and ingestion endpoint.

## Trained model artifacts

`ml/trained_models` includes both trained estimators, a feature schema, a manifest, held-out metrics, and the labelled simulated dataset. To regenerate them:

```bat
.venv\Scripts\python.exe -m ml.train
```

Stop and restart the backend after retraining. The predictor checks schema identity and artifact hashes before loading. Do not load a Random Forest pickle/joblib file from an untrusted source.

## Connecting hardware later

First follow `HARDWARE_INTEGRATION.md`. Register a new HARDWARE device rather than reusing a SIMULATION identity. Bind the backend to a LAN interface only when necessary:

```bat
.venv\Scripts\python.exe run.py --host 0.0.0.0 --no-simulator
```

The ESP32 uses the laptop's LAN IP, not `127.0.0.1`. Use a TLS endpoint with a valid root CA for deployment. Firmware HTTP is disabled by default and has an explicit isolated-LAN laboratory option. Opening the local listener is not a cloud deployment, and firewall/TLS setup has not been performed for the user's laptop.

## Database portability

SQLite is the tested default. SQLAlchemy mappings use portable types. For an independently provisioned PostgreSQL database, install `psycopg[binary]` and set `CC_DATABASE_URL` to a `postgresql+psycopg://...` URL. PostgreSQL operation, concurrent workers, and deployment are not validated. The older project SQLite import is implemented and tested; it archives old rows without changing their source. Run one backend worker; its transaction lock is process-local.

Back up a stopped SQLite database or use SQLite's backup API. Do not copy only the `.db` file during active writes without accounting for its WAL files.

## Direct Uvicorn entry point

Set a random `CC_ADMIN_TOKEN` of at least 16 characters, then use `python -m uvicorn backend.asgi:app --host 127.0.0.1 --port 8000`. The uploaded `backend.main:app` command has been replaced by an application factory and this explicit ASGI entry point. `python run.py` is the recommended beginner path and also enables the dashboard simulator.

Set `CC_MODEL_DIR` to a separate trained-artifact directory to evaluate an operator-trained model. The default remains the supplied simulation model.
