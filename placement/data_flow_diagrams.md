# 1-Level Data Flow Diagram

This 1-level DFD is styled to match the provided image design, with numbered processes, external entities, and data stores.

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

## Notes

- `1.0 Authentication` handles login, registration, and password reset routing.
- `2.0 User Profile Management` manages student profile details and resume uploads.
- `3.0 Job Management` stores job posts in `D3 Jobs` and sends applications to `4.0 Application Management`.
- `4.0 Application Management` tracks application status and updates staff reviewers.
- `5.0 Dashboards & Reports` aggregates data from the core stores for HOD/Admin/TPO and students.
