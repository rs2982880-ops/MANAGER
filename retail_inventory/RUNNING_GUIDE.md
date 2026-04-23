# 🚀 Running Guide — ShelfAI Retail Inventory System

A step-by-step guide to get the new **FastAPI + React** system up and running on your machine.

---

## 📋 Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Python | 3.9+ | 3.10 or 3.11 recommended |
| Node.js | v20+ | Required for the React frontend |
| Webcam (optional) | any | only needed for live camera mode |
| GPU (optional) | CUDA-capable | speeds up YOLO detection, not required |

---

## 1️⃣ Open the Project

Open a terminal and navigate to the project directory:

```powershell
cd "c:\Users\lonew\OneDrive\Documents\.vscode\retail_inventory"
```

---

## 2️⃣ Start the Backend (FastAPI)

Open **Terminal 1** and run:

```powershell
cd backend
pip install -r requirements.txt  # Only needed the first time
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

This starts the Python server that handles the YOLO model, WebSocket streaming, and SQLite database.
You should see it running at `http://localhost:8000`.

> **First-time note:** `ultralytics` will automatically download the YOLOv8 model if not already present.

---

## 3️⃣ Start the Frontend (React + Vite)

Open **Terminal 2** (keep the backend running in Terminal 1) and run:

```powershell
cd frontend
npm install   # Only needed the first time
npm run dev
```

This starts the premium React dashboard.
Streamlit is no longer used, so you won't experience any UI flickering.

---

## 4️⃣ Launch the Dashboard

Open your browser and navigate to:
**http://localhost:5173** (or whatever URL Vite gives you in Terminal 2).

### 🎮 How to use the Dashboard:

1. **Select Source**: In the left Camera panel, choose "Device Camera" (Index 0 is usually your laptop webcam, 1 or 2 for USB cameras) or "IP Camera" (enter the URL from DroidCam or similar).
2. **Start Camera**: Click the **Start** button. The dashboard will connect to the backend, stream the live video, and draw the grid overlay.
3. **Settings**: Adjust the Confidence slider, detection toggle, and Grid dimensions (Rows/Cols) on the left panel. These update the backend instantly.
4. **Insights**: The right panel shows real-time Stock Summaries, Alerts (when stock is low), and AI Recommendations.

---

## 🗂️ Project Structure

The project has been rebuilt into two clean directories:

- `/backend` — FastAPI server, YOLO detection, camera streaming, and SQLite data persistence.
- `/frontend` — React 18, Vite, Tailwind CSS, Zustand state management.

## ⚠️ Common Issues

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: fastapi` | Make sure you ran `pip install -r requirements.txt` inside the `backend` folder. |
| Cannot connect to WebSocket | Ensure the FastAPI backend is running on port 8000 before clicking "Start Camera" in the frontend. |
| Node/npm errors | Make sure you are using Node v20+ for Vite compatibility. |
