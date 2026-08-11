# Implementation Plan: Mobile-Ready & Database-Portable Architecture

If you want to transition this system into a **mobile application** in the future, the desktop app should not talk directly to the database. Instead, we should use a standard **API-First Architecture** with a database abstraction layer.

---

## 🏗️ Future-Proof Mobile & Database Architecture

To ensure you don't have to rewrite or change your database code in the future when moving to a mobile app or a different database, we will use two standard software design patterns:

```mermaid
graph TD
    subgraph Frontend Clients
        A[Desktop GUI App] -->|HTTP JSON Requests| C[FastAPI Backend Server]
        B[Future Mobile App] -->|HTTP JSON Requests| C
    end
    subgraph Backend Layer
        C -->|SQLAlchemy ORM| D[Database Connection Layer]
    end
    subgraph Storage Layer
        D -->|Development| E[(SQLite Local File)]
        D -->|Production / Cloud| F[(PostgreSQL Server)]
    end
```

### 1. The API Backend (Mobile Ready)
A mobile application cannot access a local database file on your laptop. Instead, it must communicate with a web server over the internet.
- We will put your database queries, resume downloading, and Gemini scoring logic inside a lightweight **FastAPI** local web server.
- The desktop app will talk to this local server via standard HTTP requests (e.g., `http://127.0.0.1:8000/jobs`).
- **Future Mobile App Migration:** When you build your mobile app in the future, it will connect to this exact same FastAPI server. You will **not** have to change a single line of backend database or Gemini code.

### 2. SQLAlchemy ORM (Database Portable)
To prevent having to rewrite SQL queries when migrating databases:
- We will use **SQLAlchemy**, Python's industry-standard Object-Relational Mapper (ORM).
- SQLAlchemy lets us interact with the database using Python objects instead of raw SQL strings.
- **Future Database Migration:** If you migrate from a local SQLite file to a cloud PostgreSQL server in the future, you change **nothing** in your code. You simply swap the connection URL in your `.env` file (e.g. from `sqlite:///recruiting.db` to `postgresql://user:pass@host/db`).

---

## Proposed Database Schema (SQLAlchemy Models)

We will define two database tables:

1. **`Job` Model**:
   - `job_id` (String, Primary Key)
   - `title` (String)
   - `description` (String)
   - `created_at` (DateTime)

2. **`Candidate` Model**:
   - `candidate_id` (Integer, Primary Key)
   - `job_id` (String, Foreign Key)
   - `name` (String)
   - `email` (String)
   - `resume_path` (String)
   - `relevance_score` (Integer, 0-100)
   - `summary` (String)
   - `status` (String, e.g. `"Applied"`, `"Scored"`)
   - `applied_at` (DateTime)

---

## Proposed Changes

### [Component: API & Database Layer]

#### [NEW] [models.py](file:///c:/Test%20linkedin%20posting/models.py)
- Defines the SQLAlchemy database schemas for `Job` and `Candidate` objects.

#### [NEW] [database.py](file:///c:/Test%20linkedin%20posting/database.py)
- Sets up database session management, tables initialization, and handles connection swapping between SQLite and PostgreSQL based on environmental variables.

#### [NEW] [server.py](file:///c:/Test%20linkedin%20posting/server.py)
- A local **FastAPI** backend server exposing REST endpoints (e.g., `/api/jobs`, `/api/download-resumes`, `/api/score-candidates`).
- Integrates the Gemini API calls and coordinates `download_resumes.py` logic.

#### [MODIFY] [app.py](file:///c:/Test%20linkedin%20posting/app.py)
- Update the GUI commands to query the local FastAPI server endpoints instead of calling local functions directly, making it fully decoupled and mobile-ready.

---

## Verification Plan

1. Install FastAPI and SQLAlchemy (`pip install fastapi uvicorn sqlalchemy`).
2. Launch the FastAPI server in the background: `uvicorn server:app --reload`.
3. Run `app.py` and test the generation, downloading, and resume listing functions to verify they communicate with the server successfully.
