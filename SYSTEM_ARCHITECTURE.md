# System Architecture — Novasphere Placement Portal

## 1. High-level Architecture (Component/DFD view)
The following 1-level data flow diagram describes how Students, TPO, HOD/Admin and the Email service interact with the portal’s backend processes and data stores.

> Source in repo: `placement/data_flow_diagrams.md`

```mermaid
flowchart LR
  %% External Entities
  ST[Students]
  TP[TPO]
  HA[HOD / Admin]
  ES[Email Service]

  %% Processes
  P1["1.0 Authentication"]
  P2["2.0 User Profile Management"]
  P3["3.0 Job Management"]
  P4["4.0 Application Management"]
  P5["5.0 Dashboards & Reports"]

  %% Data Stores
  D1[(D1 Users)]
  D2[(D2 Students)]
  D3[(D3 Jobs)]
  D4[(D4 Applications)]
  D5[(D5 Login Audit)]

  %% Student flows
  ST -->|login creds / reg details| P1
  ST -->|profile update / resume upload| P2
  ST -->|job search / apply request| P3
  ST -->|view status / dashboard| P5

  %% Staff flows
  TP -->|post jobs / review apps| P3
  HA -->|user mgmt / reports / announcements| P5
  HA -->|view reports / dashboards| P5

  %% Email flows
  ES -->|reset link / notification feedback| P1
  ES -->|send alerts| P5

  %% Process-store interactions
  P1 -->|user data| D1
  P1 -->|login audit| D5
  P1 -->|auth status / dashboard route| ST

  P2 -->|query student profile| D2
  P2 -->|query user info| D1
  P2 -->|update profile| D2
  P2 -->|return profile data| ST

  P3 -->|query job listings| D3
  P3 -->|store application| D4
  P3 -->|application status| ST
  P3 -->|posted jobs list| TP

  P4 -->|application details| D4
  P4 -->|app review results| HA
  P4 -->|application status| ST

  P5 -->|dashboard metrics| D1
  P5 -->|dashboard metrics| D2
  P5 -->|dashboard metrics| D3
  P5 -->|dashboard metrics| D4
  P5 -->|audit reports| D5
  P5 -->|report views| HA

  %% Cross-process connectors
  P1 -->|validated user / role| P5
  P2 -->|student status| P5
  P3 -->|application updates| P5
```

## 2. Backend Modules mapped to architecture processes
(derived from `placement/app.py`)

- **1.0 Authentication** (`/login/student`, `/login/admin`, `/logout`, `/reset_password`)
  - Issues JWT (stored in cookies) and applies role-based access checks.
  - Records login audit details into `LoginDetail`.

- **2.0 User Profile Management** (`/register/student`, `/student_profile`, avatar/resume uploads)
  - Stores Student profile data and resume path.

- **3.0 Job Management** (`/post_job`, `/update_job_form`, `/delete_job`, dashboard listing)
  - Creates and updates job drives with deadlines and eligibility constraints.

- **4.0 Application Management** (`/apply_job`, `/submit_secondary_data`, `/update_application_status`)
  - Creates Applications and updates statuses.
  - Triggers notifications (email) on status change.

- **5.0 Dashboards & Reports** (`/student_dashboard`, `/hod_dashboard`, `/tpo_dashboard`, `/admin_dashboard`, downloads)
  - Aggregates DB data into dashboards.
  - Generates Excel/PDF applicant reports.
  - Includes analytics charts (Matplotlib → base64).

## 3. External Integrations (as referenced in the system)
- **Email**: password reset + placement/ status update notifications.
- **ATS Analyzer**: resume PDF extraction (`PyPDF2`) and AI analysis (Gemini/Groq depending on flow).
- **Chatbot**: AI endpoint `/chat`.
- **WhatsApp (Whapi)**: `/send-actual-message` sends alerts to department groups.
- **ngrok (UAT)**: makes local Flask app accessible to students for acceptance testing.

