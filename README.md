# Cold Chain — Cloud-Integrated Control & Self-Healing System

A dual-mode cold-chain monitoring system featuring:
- 🎮 **Simulation Mode**: Synthetic sandbox engine with fault injection scenarios.
- 📡 **Live Hardware Mode**: HTTP ingestion for physical ESP32-S3 microcontroller nodes.
- 🤖 **ML Predictive Anomaly Classifier**: XGBoost + Random Forest ensemble for early failure prediction.
- ↻ **Autonomous Self-Healing Loop**: Dual Peltier cooling switching with strict safety interlocks.
- ⌖ **GPS Geofencing & Rerouting**: Automatic facility selection on critical cooling failure.

---

## 🚀 Quick Start (Local)

### 1. Install dependencies & launch
```bat
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```
Open **http://127.0.0.1:8000** in your browser.

---

## 🌐 Deploy to Vercel (Frontend) & Render (Backend)

### Option A: Push to GitHub

1. Initialize Git repository and commit your files:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of Cold Chain project"
   ```
2. Create a new repository on GitHub (e.g. `cold-chain-project`).
3. Link and push to GitHub:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/cold-chain-project.git
   git branch -M main
   git push -u origin main
   ```

---

### Option B: Deploy Backend to Render

1. Log into [Render.com](https://render.com) and click **New +** → **Blueprint**.
2. Connect your GitHub repository `cold-chain-project`.
3. Render automatically detects `render.yaml` and sets up the Web Service:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.asgi:app --host 0.0.0.0 --port $PORT`
4. Once deployed, Render provides your backend URL (e.g., `https://cold-chain-backend.onrender.com`).

---

### Option C: Deploy Frontend to Vercel

1. Log into [Vercel.com](https://vercel.com) and click **Add New** → **Project**.
2. Import your GitHub repository `cold-chain-project`.
3. Select Framework Preset: **Other** or **Vite/Static**.
4. Set:
   - **Build Command:** `node dashboard/build.mjs`
   - **Output Directory:** `dashboard/dist`
5. Click **Deploy**. Vercel will build and launch your frontend URL (e.g. `https://cold-chain.vercel.app`).
6. Open the deployed Vercel frontend, enter your Render API URL (`https://cold-chain-backend.onrender.com`) and your Operator Token to connect!

---

## 📡 Live ESP32 Hardware Integration

In **Live Hardware Mode**:
1. Click **+ Register ESP32** in the dashboard to generate a unique `X-Device-Token`.
2. Configure your ESP32 firmware with the target endpoint:
   ```cpp
   const char* API_URL = "https://your-backend.onrender.com/api/v1/telemetry";
   const char* DEVICE_TOKEN = "YOUR_GENERATED_DEVICE_TOKEN";
   ```
3. Post telemetry JSON to `/api/v1/telemetry`. The dashboard automatically streams real-time physical readings.

---

## 🧪 Verification Commands

Run full test suite:
```bat
.venv\Scripts\python.exe -m pytest -q
```

Run integration test:
```bat
.venv\Scripts\python.exe tests\run_live_integration.py
```

Build dashboard static assets:
```bash
node dashboard/build.mjs
```

---

## 📂 Project Structure

| Directory | Purpose |
|---|---|
| `backend/` | FastAPI routes, CORS, control rules, routing, validation |
| `dashboard/` | Modern UI with Simulation Mode & Live Hardware Mode |
| `database/` | SQLAlchemy models and SQLite persistence |
| `simulator/` | Seeded plant simulation engine |
| `ml/` | Predictive anomaly detection models (XGBoost, Random Forest) |
| `firmware/` | ESP32-S3 C++ adapter and local interlock rules |
| `tests/` | 67 verified Python unit & integration tests |
