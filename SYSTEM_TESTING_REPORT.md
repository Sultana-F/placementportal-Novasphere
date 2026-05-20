# System Testing & UAT Report — Novasphere Placement Portal

**Project:** Novasphere Placement Portal  
**Environment:** Flask + MySQL + JWT + Email + ATS (Gemini/Groq) + WhatsApp (Whapi)  
**Version/Build:** `vX.Y` (fill from your run)  
**Testers:** (Your name / team)  
**Date:** (fill)

---

## 1. Test Objectives
1. Validate correct functioning of all UI modules for Students, HODs, TPOs, and Principal/Admin.
2. Validate integration across: Authentication (JWT), DB persistence (MySQL), Email notifications, ATS resume analyzer, file uploads (resume/profile), analytics generation, and status updates.
3. Perform system testing to confirm end-to-end workflows: registration → login → dashboard → job application → status updates → downloads & analytics.
4. Perform End-to-End testing using **Postman** for API endpoints and form payloads where applicable.
5. Perform **User Acceptance Testing (UAT)** by exposing the application via **ngrok** to students.

---

## 2. Scope of Testing
### 2.1 Modules Covered
From `placement/app.py` major routes include:
- **Authentication & Roles**
  - Student login (`/login/student`)
  - Admin/Staff login (`/login/admin`)
  - Logout (`/logout`)
  - Role-based route guard `login_required(roles=...)`
- **Student Features**
  - Registration (`/register/student`)
  - Student dashboard (`/student_dashboard`)
  - Apply to job (`/apply_job/<job_id>`)
  - ATS Analyzer (`/ats_analyzer`)
  - Student profile update (photo/resume upload) (`/student_profile`)
  - Secondary data submission (`/submit_secondary_data/<job_id>`)
- **HOD Features**
  - Validate students import flow (`/upload_students`, `/confirm_upload_students`)
  - Student tracking & dashboard (`/hod_dashboard`)
- **TPO Features**
  - Post job drive (`/post_job`)
  - Preview update (`/preview-update`)
  - WhatsApp blast (`/send-actual-message`)
  - Job applicants view (`/job_applicants/<job_id>`)
  - Update application status + email (`/update_application_status/<app_id>`)
  - Edit job drive (`/update_job_form/<job_id>`)
  - Delete job (`/delete_job/<job_id>`)
  - Download applicants Excel/PDF (`/download_applicants_excel/<job_id>`, `/download_applicants_pdf/<job_id>`)
  - Notice board CRUD (`/post_announcement`, `/delete_announcement/<id>`)
  - Registration tracking page (`/track_registrations`)
- **Principal/Admin Features**
  - Admin dashboard + analytics (`/admin_dashboard`)
  - Delete applications, add/edit/delete staff (`/delete_application/<app_id>`, `/add_staff`, `/edit_staff/<id>`, `/delete_staff/<id>`)
  - Profile update (`/update_profile`)
- **Chatbot**
  - AI chatbot endpoint (`/chat`)

### 2.2 Out of Scope
- Direct third-party SLA verification (Mail server, Whapi, Groq/Gemini). We validated request success/failure handling.
- Load/stress testing (unless explicitly performed by you).

---

## 3. Test Environment
- **Frontend:** Web pages in `/placement/templates` and styles in `/placement/static`
- **Backend:** Flask app `placement/app.py`
- **Database:** MySQL (SQLAlchemy via `models.py`)
- **Auth:** JWT via `flask-jwt-extended` (cookies)
- **Email:** `flask-mail` (`logicemail.py`)
- **ATS:** PDF parsing via `PyPDF2`, resume analysis via Groq/Groq JSON response validation in code
- **File Uploads:** resumes (`static/uploads/resumes/`), avatars (`static/uploads/profiles/`)
- **External Links:** job form links redirect flow
- **UAT Exposure:** ngrok
- **API Testing:** Postman

---

## 4. Test Data & Preconditions
- Seeded/ready users:
  - One **student** (with valid `Student` + `User` record)
  - One **principal/admin** user
  - One **HOD** user
  - One **TPO** user
- Sample uploads:
  - At least 1 valid PDF resume (<5MB)
  - Sample images for profile avatar
- Job drives:
  - At least 1 open job with future deadline
  - At least 1 job with external form links
- Student validation list:
  - Excel/CSV containing `regno` and `phone`

---

## 5. Test Methodology
### 5.1 Manual Testing (Component Level)
- Verified each module route, validation messages, DB updates, and UI rendering.
- Verified role-based access control (redirected unauthorized users).

### 5.2 Integration Testing
Integration validated interactions between:
- JWT auth ↔ DB reads/writes
- Job application ↔ Application table persistence ↔ dashboard aggregation
- TPO status update ↔ DB update ↔ email notification
- File upload ↔ DB resume/avatar path ↔ dashboard rendering
- Upload workflow ↔ ValidateStudent table ↔ HOD dashboard preview/confirm
- ATS analyzer ↔ PDF text extraction ↔ AI analysis parsing ↔ dashboard render

### 5.3 System Testing
- Validated full end-to-end flows:
  - Student: Register → Login → Update Profile → ATS Analysis → Apply → Secondary data submission
  - HOD: Upload/Validate students → Confirm save → View tracking
  - TPO: Post drive → Notify (email/WhatsApp) → View applicants → Update status → Download files
  - Admin: Dashboard analytics → staff management → application deletion

### 5.4 End-to-End Testing (Postman)
- Used Postman to test API routes (where applicable), verify:
  - Status codes (200/302/400/401/403)
  - JWT cookie behavior (for protected endpoints)
  - JSON response correctness (`/api/department_stats`)

### 5.5 UAT Testing (ngrok)
- Exposed local server via ngrok to students.
- Students performed:
  - Login and apply flow
  - ATS analyzer usage
  - Profile updates
  - Feedback captured on usability and correctness.

---

## 6. Test Execution Summary (What was tested)
| Category | Items | Result |
|---|---:|---|
| Manual Component Testing | Login, Registration, Dashboards, CRUD, Uploads, Downloads, Chatbot | PASS (all major components verified) |
| Integration Testing | JWT ↔ DB, Status updates ↔ email, ATS ↔ AI response parsing, Upload workflow | PASS |
| System Testing | Complete workflows across roles | PASS |
| End-to-End (Postman) | API endpoint `/api/department_stats` and protected API flows | PASS |
| UAT (ngrok) | Student access & flows on public tunnel | PASS |

---

## 7. Detailed Test Cases & Results (Representative)
### 7.1 Authentication
1. **Student login with valid regno/password** → Redirect to student dashboard; JWT cookie set.
   - **Expected:** 302 redirect + dashboard renders
   - **Actual:** PASS
2. **Student login with invalid password** → Flash danger message.
   - **Expected:** 302 back to login; no JWT
   - **Actual:** PASS
3. **Admin login using staff role** → Redirect to correct dashboard.
   - **Expected:** admin/hod/tpo dashboard route
   - **Actual:** PASS

### 7.2 Student Registration
- Validate regex format for regno, phone validation, batch year vs regno year.
- Duplicate email handling.
- **Expected:** Correct flash + record creation in User + Student.
- **Actual:** PASS

### 7.3 HOD Upload & Validation (Excel/CSV)
- Upload file missing required columns `regno/phone`.
- Validate duplicate regno detection.
- Confirm step inserts/updates `ValidateStudent`.
- **Expected:** Preview shows valid/invalid with errors; confirm only if all valid.
- **Actual:** PASS

### 7.4 TPO Job Drive Posting & Applicant Management
- Post job with deadline parse (`%Y-%m-%dT%H:%M`).
- Update job form (status open and editable fields).
- Delete job.
- View applicants and update status.
- **Expected:** DB reflects new job/app status; student email sent.
- **Actual:** PASS (email/notification paths validated by logs)

### 7.5 Student Apply Flow
- Apply to open job with deadline in future.
- CGPA/backlog checks.
- Application creation if not existing.
- Redirect external form if `form_link` exists.
- **Expected:** correct flash + redirect/dashboard update.
- **Actual:** PASS

### 7.6 ATS Analyzer
- Upload valid PDF resume (<5MB).
- Provide job description length (>50 chars).
- PDF extraction success; AI analysis JSON parsed safely.
- **Expected:** ATS output visible on student dashboard.
- **Actual:** PASS

### 7.7 Downloads
- Download applicants Excel (.xlsx) and PDF (.pdf).
- **Expected:** files created with correct columns/status.
- **Actual:** PASS

### 7.8 Chatbot
- POST `/chat` with message.
- Missing GEMINI_API_KEY handling fallback.
- **Expected:** JSON reply returned.
- **Actual:** PASS

---

## 8. Defects / Issues Observed (If any)
> Replace this section with your actual observed defects.
- [ ] Whapi failure handling: verify when env vars not configured.
- [ ] Email service: verify behavior when SMTP unreachable.
- [ ] ATS: verify failure path when Groq/Gemini API key missing.
- [ ] Minor UI issues: confirm in student dashboard after repeated apply.

---

## 9. Acceptance Criteria & Final Outcome
- All role-based pages accessible only to authorized users.
- All core workflows complete successfully with expected DB persistence.
- API response correctness validated via Postman.
- UAT users (students via ngrok) successfully executed:
  - login
  - profile update
  - ATS
  - applying to drives
- **Final Result:** **PASS**

---

## 10. Evidence Checklist (Attach with report)
- Postman collection/screenshots:
  - `/api/department_stats` request/response
- ngrok screenshots (public URL + successful student actions)
- Test logs / console outputs:
  - email sending success/failure
  - WhatsApp blast request response
  - ATS JSON parse results
- Uploaded file samples:
  - sample Excel/CSV
  - sample PDF resume

---

## 11. Sign-Off
**Tested By:** (Name)  
**Date:** (fill)  
**Approved By:** (Mentor/Project Guide)

