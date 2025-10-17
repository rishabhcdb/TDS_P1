# ⚙️ AI App Builder Backend

This project is a **Flask-based backend** designed to handle the core functionality of the **AI App Builder**, allowing users to submit requests for app generation, process builds, and interact with the deployed endpoints.

---

## 🚀 Features

- **REST API Endpoints**
  - `GET /` — Health check route to confirm the server is running.
  - `POST /build-app` — Handles app creation requests from the frontend.  
    Accepts JSON payloads containing configuration parameters and triggers app-building logic.
- **Automatic Logging** — Logs all incoming requests for debugging and visibility.
- **Render Deployment Ready** — Fully configured to run on HuggingFace Spaces or any modern cloud hosting service.
- **CORS Enabled** — Allows secure communication with the frontend application.
- **Environment Variables Support** — Easily manage secrets and environment-specific configurations.

---

## 🧠 Tech Stack

- **Backend and API:** Flask (Python)
- **Deployment:** HuggingFace spaces
- **LLM:** Gemini 2.0Flash API
- **Utilities:** Python-dotenv, requests, json, logging

---

## ⚡ Getting Started

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/rishabhcdb/TDS_P1.git
cd TDS_P1
