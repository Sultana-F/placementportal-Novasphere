from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import db, User, Role, LoginDetail, Student, JobPosting, Application, Announcement, ValidateStudent, ApprovedStaff
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity,
    get_jti, JWTManager, set_access_cookies, unset_jwt_cookies, decode_token,get_jwt,verify_jwt_in_request
)


from functools import wraps
# pyrefly: ignore [missing-import]
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
load_dotenv()
from logicemail import  mail,send_email
import os
from datetime import datetime, timezone, timedelta
import re
import pandas as pd
from io import BytesIO
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import send_file
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from google import genai
import json
import PyPDF2
from werkzeug.utils import secure_filename
import requests
import os



app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {"ssl_disabled": False}
}
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False  # For simplicity in this dev environment

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = os.getenv('MAIL_PORT')
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'False') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('EMAIL_USER')

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

@app.template_filter('gravatar')
def gravatar_filter(email):
    return f"https://ui-avatars.com/api/?name={email.split('@')[0].replace('.',' ')}&size=100&background=512da8&color=fff"

# Configure Upload Folder
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Token revocation blacklist
blacklist = set()

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    return jwt_payload['jti'] in blacklist

#initialize mail,db
mail.init_app(app)
db.init_app(app)

# GROQ Client Initialization
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
model = "gemini-1.5-flash"



# ─── Role → Dashboard mapping ───────────────────────────────────────────────

ROLE_DASHBOARD = {
    'principal': 'admin',        # existing admin_dashboard.html
    'hod':       'hod_dashboard',
    'tpo':       'tpo_dashboard',
    'student':   'student_dashboard',
}


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    token = request.cookies.get('access_token_cookie')
    user = None
    if token:
        try:
            payload = decode_token(token)
            user = payload['sub']
        except Exception:
            pass
    return render_template('home.html', user=user)


@app.route('/user')
def loginpage():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('studentReg.html')






# ── Student Login ────────────────────────────────────────────────────────────
@app.route('/login/student', methods=['POST'])
def login_student():
    regno    = request.form.get('regno', '').strip()
    password = request.form.get('password', '').strip()

    if not regno or not password:
        flash('Please enter registration number and password.', 'danger')
        return redirect(url_for('loginpage'))

    # Look up by regno in Student table
    student = Student.query.filter_by(regno=regno).first()
    if not student:
        flash('Invalid registration number.', 'danger')
        return redirect(url_for('loginpage'))

    # Fetch the corresponding User record via email
    user = User.query.filter_by(email=student.email, role='student').first()
   #verify password
    if not user or not bcrypt.check_password_hash(user.password, password):
        flash('Invalid registration number or password.', 'danger')
        return redirect(url_for('loginpage'))
    # Issue JWT and redirect to student dashboard
    access_token = create_access_token(
        identity=str(user.email),
        additional_claims={'role': 'student', 'regno': regno}
    )
    record_login_details(user, access_token)
    response = redirect(url_for('student_dashboard'))
    set_access_cookies(response, access_token)
    return response


# ── Admin / Staff Login ──────────────────────────────────────────────────────
@app.route('/login/admin', methods=['POST'])
def login_admin():
    email    = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    if not email or not password:
        flash('Please enter email and password.', 'danger')
        return redirect(url_for('loginpage') + '?tab=admin')

    user = User.query.filter_by(email=email).first()
    # Verify user exists and password matches
    if not user or not bcrypt.check_password_hash(user.password, password):
        flash('Invalid email or password.', 'danger')
        return redirect(url_for('loginpage') + '?tab=admin')
    if user.role == 'student':
        flash('Students must use the Student Login tab.', 'danger')
        return redirect(url_for('loginpage'))

    # Issue JWT with role claim
    access_token = create_access_token(
        identity=str(user.email),
        additional_claims={'role': user.role}
    )
    record_login_details(user, access_token)

    # Redirect to the appropriate role dashboard
    dashboard_route = ROLE_DASHBOARD.get(user.role, 'index')
    response = redirect(url_for(dashboard_route))
    set_access_cookies(response, access_token)
    return response


# ── Auth helper decorator ────────────────────────────────────────────────────
def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
           
            try:
                verify_jwt_in_request()
                claims = get_jwt()
                if roles and claims.get('role') not in roles:
                    flash('You are not authorized to access that page.', 'danger')
                    return redirect(url_for('loginpage'))
            except Exception:
                flash('Please log in to continue.', 'danger')
                return redirect(url_for('loginpage'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def record_login_details(user, access_token):
    """Record login audit details using the actual login token's JTI."""
    try:
        jti = get_jti(access_token)
        audit = LoginDetail(
            user_id=user.id,
            username=user.email,
            password=user.password,
            accessToken=str(jti),
        )
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error recording login details: {e}")







#reset password with token based email
@app.route('/reset_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot password.html')
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if user:
            # Generate a password reset token (JWT with short expiry)
            reset_token = create_access_token(
                identity=str(user.email),
                additional_claims={'role': user.role},
                expires_delta=timedelta(minutes=30)  # Token valid for 30 minutes
            )
            reset_link = url_for('reset_password', token=reset_token, _external=True) #
            send_email(
                subject='Password Reset Request',
                recipients=[user.email],
                body=f'Click the link to reset your password: {reset_link}'
            )
            flash('A password reset link has been sent to your email.', 'info')
        else:
            flash('No account found with that email address.', 'danger')
        return redirect(url_for('loginpage') + '?tab=admin')
    return render_template('forgot password.html')


#on click rest link, verify token and allow password reset
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        payload = decode_token(token)
        email = payload['sub']
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Invalid or expired token.', 'danger')
            return redirect(url_for('loginpage') + '?tab=admin')
    except Exception as e:
        print(f"Token decode error: {e}")
        flash('Invalid or expired reset token.', 'danger')
        return redirect(url_for('loginpage') + '?tab=admin')
    if request.method == 'GET':
        return render_template('reset_password.html', token=token)

    if request.method == 'POST':
        new_password = request.form.get('newpassword', '').strip()
        if new_password:
            user.password = bcrypt.generate_password_hash(new_password).decode('utf-8') 
            db.session.commit()
            flash('Your password has been reset successfully. Please log in.', 'success')
            return redirect(url_for('loginpage') + '?tab=admin')
        else:
            flash('Please enter a new password.', 'danger')

    return render_template('reset_password.html', token=token)
# Note: The reset_password.html template should include a form that submits the new password to the same URL (including the token).

#student registration
@app.route('/register/student', methods=['POST'])
def register_student():    
    name= request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone=request.form.get('phone', '').strip()
    regno=request.form.get('regno','').strip()
    department=request.form.get('department','').strip()
    sem=request.form.get('sem','').strip()
    gender=request.form.get('gender','').strip()
    dob=request.form.get('dob','').strip()
    batch=request.form.get('batch','').strip()
    cgpa=request.form.get('cgpa','').strip()
    backlogs=request.form.get('backlogs','').strip()
    address=request.form.get('address','').strip()
    tenth_percent=request.form.get('tenth_percent','').strip()
    twelfth_percent=request.form.get('twelfth_percent','').strip()
    password = request.form.get('password', '').strip() # Get password from form input

    #vaildate regno from vaildatestudent table
    validate_student = ValidateStudent.query.filter_by(regno=regno).first()
    if validate_student:
        regno_in_validate = validate_student.regno
        if regno != regno_in_validate:
            flash('Registration number does not match our records. Please contact administration.', 'danger')
            return redirect(url_for('register'))
    
    
    #validate registration number format  using regex where U is fixed, 16 is year of admission, NB is department code, 23 is batch year, S  is fixed and 0120 is unique number
    #validate the batch year based on the batch entered by student taking in consideration the last two digits for eg if batch is 2022-25 then it will take 25 and compare with regno[3:5] which is 23 in this case and it will show error because batch year and regno year should match
    batch_year_pattern = r'^\d{4}-\d{2}$'
    if not re.fullmatch(batch_year_pattern, batch):
        flash('Invalid batch format. Please follow the format: 2022-25', 'danger')
    #validate batch year matches regno year
    batch_year = batch[2:4]           # Get the last two digits of the batch year
    regno_year = regno[5:7]           # Get the year part from the registration number
    if batch_year != regno_year:    
        flash('Batch year does not match registration number year.', 'danger')
        return redirect(url_for('register'))
    
    regno_pattern = r'^U16NB\d{2}[S]\d{4}$'
    if not re.fullmatch(regno_pattern, regno):
        flash('Invalid registration number format. Please follow the format: U16NB23S0120', 'danger')
        return redirect(url_for('register'))
   
    #validate phone number format   
    phone_pattern = r'^\d{10}$'
    if not re.fullmatch(phone_pattern, phone):
        flash('Invalid phone number format. Please enter a 10-digit phone number.', 'danger')
        return redirect(url_for('register'))

    try:
        # 1. First create the User record for authentication
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        new_user = User(
            full_name=name,
            email=email,
            password=bcrypt.generate_password_hash(password).decode('utf-8'),
            role='student',
            phone=phone
        )
        db.session.add(new_user)
        db.session.flush() # Flush to generate new_user.id for the foreign key

        # 2. Create the Student record linked to the new user
        new_student = Student(
            student_id=new_user.id, # Foreign key to User
            name=name,
            email=email,
            phone=phone,
            regno=regno,
            department=department,
            sem=int(sem),
            gender=gender,
            dob=datetime.strptime(dob, '%Y-%m-%d').date() if dob else None,
            batch=batch,
            cgpa=float(cgpa) if cgpa else 0.0,
            backlogs=int(backlogs) if backlogs else 0,
            address=address,
            tenth_percent=float(tenth_percent) if tenth_percent else None,
            twelfth_percent=float(twelfth_percent) if twelfth_percent else None
        )
        db.session.add(new_student)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('loginpage'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating student record: {e}', 'danger')
        return redirect(url_for('register'))






# ─── API Endpoints ───────────────────────────────────────────────────────────

@app.route('/api/department_stats')
@login_required(roles=['principal'])
def get_department_stats():
    dept = request.args.get('dept')
    batch = request.args.get('batch')
    
    if not dept or not batch:
        return jsonify([])

    # Query students matching dept and batch (batch check uses contains for flexibility)
    students = Student.query.filter(Student.department == dept, Student.batch.contains(batch)).all()
    
    data = []
    for s in students:
        # Check if student is placed (has a 'selected' application)
        placement = Application.query.filter_by(student_id=s.id, status='selected').first()
        
        status = "Placed" if placement else "Not Placed"
        company = placement.job.company_name if placement else "N/A"
        package = placement.job.salary_package if placement else "N/A"
        
        data.append({
            'name': s.name,
            'regno': s.regno,
            'status': status,
            'company': company,
            'package': package
        })
        
    return jsonify(data)


# ─── Logout ──────────────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    response = redirect(url_for('home'))
    unset_jwt_cookies(response)
    return response


# ─── Dashboards ──────────────────────────────────────────────────────────────
#28-04-2026
@app.route('/admin_dashboard')
@login_required(roles=['principal'])
def admin():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    
    # 0. Filter Parameters
    selected_batch = request.args.get('batch', 'All')
    selected_dept = request.args.get('dept', 'All')
    
    # Get distinct batches and departments for filters
    batches = db.session.query(Student.batch).distinct().all()
    batch_list = sorted([b[0] for b in batches if b[0]])
    
    departments = db.session.query(Student.department).distinct().all()
    dept_list = sorted([d[0] for d in departments if d[0]])
    
    # Base queries for filtering
    student_query = Student.query
    application_query = db.session.query(Application).join(Student, Application.student_id == Student.id)
    
    if selected_batch != 'All':
        student_query = student_query.filter(Student.batch == selected_batch)
        application_query = application_query.filter(Student.batch == selected_batch)
        
    if selected_dept != 'All':
        student_query = student_query.filter(Student.department == selected_dept)
        application_query = application_query.filter(Student.department == selected_dept)
    
    # 1. Dashboard Stats
    total_students = student_query.count()
    placed_students = application_query.filter(Application.status == 'selected').distinct(Application.student_id).count()
    
    # Calculate Average Package for the filtered selection
    selected_apps = application_query.filter(Application.status == 'selected').all()
    total_package = 0
    count_package = 0
    for app in selected_apps:
        if app.job.salary_package:
            match = re.search(r'(\d+\.?\d*)', app.job.salary_package)
            if match:
                total_package += float(match.group(1))
                count_package += 1
    
    avg_package = round(total_package / count_package, 2) if count_package > 0 else 0
    
    # 2. Student Directory (Filtered by Dept/Batch)
    recent_placed_query = db.session.query(Student, Application, JobPosting).\
        join(Application, Student.id == Application.student_id).\
        join(JobPosting, Application.job_id == JobPosting.id).\
        filter(Application.status == 'selected')
    
    if selected_batch != 'All':
        recent_placed_query = recent_placed_query.filter(Student.batch == selected_batch)
    if selected_dept != 'All':
        recent_placed_query = recent_placed_query.filter(Student.department == selected_dept)
        
    recent_placed = recent_placed_query.order_by(Application.applied_at.desc()).limit(20).all()
    
    placed_data = []
    for s, a, j in recent_placed:
        placed_data.append({
            'app_id': a.id,
            'name': s.name,
            'reg_no': s.regno,
            'department': s.department,
            'company': j.company_name,
            'package': j.salary_package,
            'placed_date': a.applied_at.strftime('%d %b, %Y')
        })

    # 3. Department Specific Student Data (for the new table)
    dept_students = []
    if selected_dept != 'All':
        raw_students = student_query.all()
        for s in raw_students:
            # Check if this student is placed
            placed_app = Application.query.filter_by(student_id=s.id, status='selected').first()
            dept_students.append({
                'app_id': placed_app.id if placed_app else None,
                'name': s.name,
                'regno': s.regno,
                'batch': s.batch,
                'is_placed': True if placed_app else False,
                'package': placed_app.job.salary_package if placed_app and placed_app.job else None
            })

    # 4. TPO Management
    tpos = ApprovedStaff.query.filter_by(role='tpo').all()
    
    # 5. HOD Management
    hods = ApprovedStaff.query.filter_by(role='hod').all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()

    # 6. Advanced Analytics
    analytics = get_tpo_analytics(selected_batch, selected_dept)

    return render_template('admin_dashboard.html', 
                         user=user, 
                         total_students=total_students,
                         placed_count=placed_students,
                         avg_package=avg_package,
                         students=placed_data,
                         dept_students=dept_students,
                         announcements=announcements,
                         tpos=tpos,
                         hods=hods,
                         batches=batch_list,
                         selected_batch=selected_batch,
                         departments=dept_list,
                         selected_dept=selected_dept,
                         analytics=analytics)


@app.route('/delete_application/<int:app_id>')
@login_required(roles=['principal', 'tpo'])
def delete_application(app_id):
    try:
        application = Application.query.get_or_404(app_id)
        db.session.delete(application)
        db.session.commit()
        flash('Placement record deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting record: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('admin'))


@app.route('/add_staff', methods=['POST'])
@login_required(roles=['principal'])
def add_staff():
    name = request.form.get('fullname')
    email = request.form.get('email')
    phone = request.form.get('phone')
    role = request.form.get('role') # 'tpo' or 'hod'
   
    
    if User.query.filter_by(email=email).first():
        flash('Email already exists.', 'danger')
        return redirect(url_for('admin'))
        
    try:
        # 1. Create User with default password
        default_password = bcrypt.generate_password_hash('admin123').decode('utf-8')
        new_user = User(
            full_name=name,
            email=email,
            password=default_password,
            role=role,
            phone=phone
        )
        db.session.add(new_user)
        db.session.flush() # Get ID
        
        # 2. Create ApprovedStaff
        new_staff = ApprovedStaff(
            user_id=new_user.id,
            name=name,
            email=email,
            phone=phone,
            role=role
        )
        db.session.add(new_staff)
        db.session.commit()
        flash(f'{role.upper()} added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding staff: {str(e)}', 'danger')
        
    return redirect(url_for('admin'))


@app.route('/edit_staff/<int:id>', methods=['POST'])
@login_required(roles=['principal'])
def edit_staff(id):
    # 'id' here refers to the User ID (passed from the updated frontend)
    user = User.query.get_or_404(id)
    user.full_name = request.form.get('fullname')
    user.email = request.form.get('email')
    user.phone = request.form.get('phone')
    
    # Sync with ApprovedStaff record if it exists
    if user.approved_staff_profile:
        user.approved_staff_profile.name = user.full_name
        user.approved_staff_profile.email = user.email
        user.approved_staff_profile.phone = user.phone
    
    try:
        # Update User
        user.full_name = request.form.get('fullname')
        user.email = request.form.get('email')
        user.phone = request.form.get('phone')
        
        # Update ApprovedStaff
        staff = ApprovedStaff.query.filter_by(user_id=id).first()
        if staff:
            staff.name = user.full_name
            staff.email = user.email
            staff.phone = user.phone
            
        db.session.commit()
        flash('Staff details updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating staff: {str(e)}', 'danger')
        
    return redirect(url_for('admin'))


@app.route('/delete_staff/<int:id>')
@login_required(roles=['principal'])
def delete_staff(id):
    user = User.query.get_or_404(id)
    try:
        db.session.delete(user)
        db.session.commit()
        flash('Staff removed successfully.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting staff: {str(e)}', 'danger')
        
    return redirect(url_for('admin'))


@app.route('/update_profile', methods=['POST'])
@login_required(roles=['principal', 'tpo', 'hod'])
def update_profile():
    email_identity = get_jwt_identity()
    user = User.query.filter_by(email=email_identity).first()
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('home'))

    user.full_name = request.form.get('fullname')
    user.email = request.form.get('email')
    user.phone = request.form.get('phone')
    
    # Handle Profile Photo Removal
    if request.form.get('remove_photo') == 'true':
        user.avatar = None
        
    # Handle Profile Photo Upload
    if 'profile_photo' in request.files:
        file = request.files['profile_photo']
        if file and file.filename != '' and allowed_file(file.filename):
            # Use a consistent filename based on user ID to overwrite instead of creating new paths
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"profile_{user.id}.{ext}"
            
            # Ensure subfolder exists
            profile_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')
            os.makedirs(profile_folder, exist_ok=True)
            
            # Save and update path
            file.save(os.path.join(profile_folder, filename))
            user.avatar = f"uploads/profiles/{filename}" 
    
    try:
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'danger')
        
    return redirect(request.referrer or url_for('home'))


# ------------------------- preethi 
# ATS ENGINE
# -------------------------
def extract_resume_text(file):
    try:
        reader = PyPDF2.PdfReader(file)
        text = ""

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        text = text.strip()
        print(f"DEBUG: Extracted {len(text)} characters from resume")

        # Prevent overload / prompt injection risk
        return text[:5000] # Increased slightly to 5000

    except Exception as e:
        print(f"PDF EXTRACTION ERROR: {str(e)}")
        return ""

def analyze_resume_with_groq(resume_text, job_desc):
    import os
    from groq import Groq
    import json
    
    # Initialize Groq client
    # You must set the GROQ_API_KEY environment variable.
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("WARNING: GROQ_API_KEY not found in environment variables.")
        # Fallback for testing, but recommend setting env variable
        api_key = "gsk_..." # User should configure this
        
    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        print(f"Failed to initialize Groq client: {e}")
        return {
            "score": 0, "remark": "Analysis Failed", "skills_score": 0,
            "experience_score": 0, "formatting_score": 0,
            "matched_keywords": [], "missing_keywords": [],
            "strengths": [], "weaknesses": [],
            "suggestions": ["Failed to initialize Groq client. Check API key."]
        }

    # Prepare the prompt
    prompt = f"""
You are a strict ATS (Applicant Tracking System) Specialist.
Analyze the provided RESUME against the JOB DESCRIPTION.

JOB DESCRIPTION:
{job_desc}

RESUME:
{resume_text}

Provide your analysis in the following JSON format ONLY, do not output any markdown or conversational text:
{{
  "score": 0,
  "remark": "Excellent | Good | Average | Poor",
  "skills_score": 0,
  "experience_score": 0,
  "formatting_score": 0,
  "matched_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["keyword1", "keyword2"],
  "strengths": ["point1", "point2"],
  "weaknesses": ["point1", "point2"],
  "suggestions": ["tip1", "tip2"]
}}
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.2
        )

        data = json.loads(response.choices[0].message.content)

        # SAFE SCORE HANDLING
        def safe_int(val):
            try:
                if isinstance(val, str):
                    val = val.replace('%', '')
                return max(0, min(10, int(float(val))))
            except:
                return 0

        processed_data = {
            "score": safe_int(data.get("score")),
            "remark": str(data.get("remark", "Analysis Complete")),
            "skills_score": safe_int(data.get("skills_score")),
            "experience_score": safe_int(data.get("experience_score")),
            "formatting_score": safe_int(data.get("formatting_score")),
            "matched_keywords": data.get("matched_keywords", []),
            "missing_keywords": data.get("missing_keywords", []),
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "suggestions": data.get("suggestions", [])
        }

        # Ensure lists are actually lists
        for key in ["matched_keywords", "missing_keywords", "strengths", "weaknesses", "suggestions"]:
            if not isinstance(processed_data[key], list):
                processed_data[key] = []

        return processed_data

    except Exception as e:
        print(f"GROQ ANALYSIS ERROR: {str(e)}")
        return {
            "score": 0,
            "remark": "Analysis Failed",
            "skills_score": 0,
            "experience_score": 0,
            "formatting_score": 0,
            "matched_keywords": [],
            "missing_keywords": [],
            "strengths": [],
            "weaknesses": [],
            "suggestions": [f"Error during analysis: {str(e)}", "Please try again."]
        }


#---------- ats analyzer preethi 
@app.route('/ats_analyzer', methods=['GET', 'POST'])
@login_required(roles=['student'])
def ats_analyzer():
   
    try:
        file = request.files.get('resume')
        job_desc = request.form.get('job_desc', '').strip()

        if not file or not job_desc:
            flash("All fields required", "danger")
            return redirect(url_for('student_dashboard'))  

        if not file.filename.endswith('.pdf'):
            flash("Only PDF files allowed", "danger")
            return redirect(url_for('student_dashboard'))  

        file.seek(0, 2)
        size = file.tell()
        file.seek(0)

        if size > 5 * 1024 * 1024:
            flash("File must be under 5MB", "danger")
            return redirect(url_for('student_dashboard'))  

        if len(job_desc) < 50:
            flash("Job description too short", "danger")
            return redirect(url_for('student_dashboard'))  

        resume_text = extract_resume_text(file)

        if not resume_text:
            flash("Could not read resume PDF", "danger")
            return redirect(url_for('student_dashboard'))

        result = analyze_resume_with_groq(resume_text, job_desc)
        claims  = get_jwt()
        regno   = claims.get('regno')

        student = Student.query.filter_by(regno=regno).first()
        user = User.query.filter_by(email=student.email).first()
        applications = Application.query.filter_by(student_id=student.id).all()

        stats = {
          'total_applied': len(applications),
          'shortlisted': len([a for a in applications if a.status == 'shortlisted']),
          'interviews': len([a for a in applications if a.status == 'interviewed']),
          'rejected': len([a for a in applications if a.status == 'rejected'])
        }

        applied_job_ids = [a.job_id for a in applications]

        now = datetime.now()
        jobs = JobPosting.query.filter(
         db.or_(JobPosting.status == 'open', JobPosting.status == None),
         JobPosting.deadline > now
        ).all()

        email_identity = get_jwt_identity()
        user = User.query.filter_by(email=student.email).first()

        announcements = Announcement.query.order_by(
        Announcement.created_at.desc()
        ).limit(10).all()
        return render_template(
      'student_dashboard.html',
      student=student,
      user=user,
      stats=stats,
      applications=applications,
      jobs=jobs,
      applied_job_ids=applied_job_ids,
      announcements=announcements,
      deadlines=[],
      skills=[],
      result=result,
      filename=file.filename,
      job_desc=job_desc,
      active_tab='ats')


    except Exception as e:
       print("ERROR:", str(e))   # shows real error in terminal
       flash(f"Error: {str(e)}", "danger")
       return redirect(url_for('student_dashboard'))


#------------------ends preethi ats analyzer and student updates


#--------------------ends ats engine preethi

@app.route('/student_profile', methods=['POST'])
@login_required(roles=['student'])
def student_update_profile():
    


    # -------------------------------
    # GET CURRENT USER
    # -------------------------------
    email_identity = get_jwt_identity()
    user = User.query.filter_by(email=email_identity).first()

    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('home'))

    # -------------------------------
    # BASIC USER DATA
    # -------------------------------
    user.phone = request.form.get('phone')

    # -------------------------------
    # PROFILE PHOTO UPLOAD / REMOVE
    # -------------------------------
    if request.form.get('remove_photo') == 'true':
        user.avatar = None

    if 'profile_photo' in request.files:
        file = request.files['profile_photo']

        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"profile_{user.id}.{ext}"

            profile_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')
            os.makedirs(profile_folder, exist_ok=True)

            file.save(os.path.join(profile_folder, filename))
            user.avatar = f"uploads/profiles/{filename}"

    # -------------------------------
    # STUDENT DATA (FIXED)
    # -------------------------------
    student = Student.query.filter_by(email=user.email).first()

    #  Create if not exists
    if not student:
        student = Student(student_id=user.id)
        db.session.add(student)

    # ALWAYS update (for both new + existing)
    student.address = request.form.get('address')
    student.skills = request.form.get('skills')

    sem = request.form.get('sem')
    if sem and sem.isdigit() and 1 <= int(sem) <= 6:
        student.sem = int(sem)

    # -------------------------------
    # RESUME UPLOAD (REPLACE + SAME NAME)
    # -------------------------------
    if 'resume' in request.files:
        resume_file = request.files['resume']

        if resume_file and resume_file.filename != '':
            if resume_file.filename.lower().endswith('.pdf'):

                resume_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'resumes')
                os.makedirs(resume_folder, exist_ok=True)

                # Same filename → overwrite
                filename = f"resume_{user.id}.pdf"
                file_path = os.path.join(resume_folder, filename)

                resume_file.save(file_path)

                #  Save path in DB
                student.resume = f"uploads/resumes/{filename}"

            else:
                flash('Only PDF files allowed!', 'danger')

    # -------------------------------
    # SAVE TO DB
    # -------------------------------
    try:
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        print("DB ERROR:", e)
        flash(f'Error: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('home'))



@app.route('/student_dashboard')
@login_required(roles=['student'])
def student_dashboard():
    claims  = get_jwt()
    regno   = claims.get('regno')
    student = Student.query.filter_by(regno=regno).first()

    # Guard: if student profile not found, show helpful error
    if not student:
        flash(f'Student profile not found for regno "{regno}". Please contact administration.', 'danger')
        return redirect(url_for('loginpage'))

    # Fetch stats for overview cards
    applications = Application.query.filter_by(student_id=student.id).all()
    stats = {
        'total_applied': len(applications),
        'shortlisted': len([a for a in applications if a.status == 'shortlisted']),
        'interviews': len([a for a in applications if a.status == 'interviewed']),
        'rejected': len([a for a in applications if a.status == 'rejected'])
    }
    
    # Store applied job IDs for UI status updates
    applied_job_ids = [a.job_id for a in applications]
    
    # Fetch active job postings with open status and future deadlines
    now = datetime.now()
    jobs = JobPosting.query.filter(
        db.or_(JobPosting.status == 'open', JobPosting.status == None),
        JobPosting.deadline > now
    ).order_by(JobPosting.deadline.asc()).all()
    
    # Fetch Announcements for the notice board
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(10).all()
    
    deadlines = []
    skills = []
    
    return render_template('student_dashboard.html', 
                         student=student,
                         stats=stats,
                         applications=applications,
                         jobs=jobs,
                         applied_job_ids=applied_job_ids,
                         announcements=announcements,
                         deadlines=deadlines,
                         skills=skills,
                         user=User.query.filter_by(email=student.email).first()
                         )



@app.route('/apply_job/<int:job_id>', methods=['POST'])
@login_required(roles=['student'])
def apply_job(job_id):
    claims = get_jwt()
    regno = claims.get('regno')
    student = Student.query.filter_by(regno=regno).first()
    

    if not student:
        flash('Student record not found.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Get job posting
    job = JobPosting.query.filter_by(id=job_id).first()
    if not job:
        flash('Job posting not found.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Check if job is still open
    if job.status != 'open':
        flash('This job posting is no longer open for applications.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Check if deadline has passed
    if job.deadline < datetime.now():
        flash('The application deadline for this position has passed.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Check if student meets CGPA requirement
    if student.cgpa < job.min_cgpa:
        flash(f'Automated Verification Failed: Your CGPA ({student.cgpa}) does not meet the minimum requirement ({job.min_cgpa}) for this drive.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Check if student exceeds backlogs limit
    if student.backlogs > job.max_backlogs:
        flash(f'Automated Verification Failed: Your backlogs ({student.backlogs}) exceed the maximum allowed ({job.max_backlogs}) for this position.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Check if student profile is complete (Removed as per request)
    # if not student.resume:
    #     flash('Please upload your resume before applying. Go to your profile to upload.', 'info')
    #     return redirect(url_for('student_dashboard'))
    
    # if not student.skills:
    #     flash('Please add your skills to your profile before applying.', 'info')
    #     return redirect(url_for('student_dashboard'))
    
    # Check if already applied (Disabled to allow repeated redirection to external links)
    # existing = Application.query.filter_by(job_id=job_id, student_id=student.id).first()
    # if existing:
    #     flash('You have already applied for this position.', 'warning')
    #     return redirect(url_for('student_dashboard'))
    
    # Check if already applied (Done silently to allow redirection)
    existing = Application.query.filter_by(job_id=job_id, student_id=student.id).first()
    
    if not existing:
        try:
            new_app = Application(job_id=job_id, student_id=student.id)
            db.session.add(new_app)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error saving application: {e}")

    # Process external redirection if a link exists
    clean_link = job.form_link.strip() if job.form_link else "" # Remove leading/trailing whitespace
    
    if clean_link:
        flash('Redirecting to the official registration form...', 'success')
        target_url = clean_link if clean_link.startswith(('http://', 'https://')) else 'https://' + clean_link
        return  redirect(target_url)
    else:
        if not existing:
            flash('Application submitted successfully! (No external form required for this drive)', 'success')
        else:
             flash('You have already applied for this position.', 'info')
            
    return redirect(url_for('student_dashboard'))



@app.route('/hod_dashboard')
@login_required(roles=['hod'])
def hod_dashboard():
    from flask_jwt_extended import get_jwt_identity
    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    active_tab = request.args.get('tab', 'dashboard')

    # 1. Total students (from ValidateStudent table)
    total_students = ValidateStudent.query.count()

    # 2. Registered students (from Student table)
    registered_students = Student.query.count()

    # 3. Unregistered students
    unregistered_students = total_students - registered_students
    
    students = Student.query.all() 

    return render_template('hod_dashboard.html',
                           user=user,
                           total_students=total_students,
                           registered_students=registered_students,
                           unregistered_students=unregistered_students,
                           students=students,
                           applications=Application.query.all(),
                           announcements=Announcement.query.order_by(Announcement.created_at.desc()).all(),
                           active_tab=active_tab)

# =========================
#  UPLOAD + PREVIEW
# =========================
@app.route('/upload_students', methods=['POST'])
@login_required(roles=['hod'])
def upload_students():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()

    file = request.files.get('file')

    if not file or file.filename == '':
        flash("Please upload a file ", "danger")
        return redirect(url_for('hod_dashboard'))

    ext = file.filename.split('.')[-1].lower()

    if ext not in {'csv', 'xls', 'xlsx'}:
        flash("Only CSV or Excel files allowed ", "danger")
        return redirect(url_for('hod_dashboard'))

    try:
        df = pd.read_csv(file, dtype=str) if ext == 'csv' else pd.read_excel(file, dtype=str)

        df.columns = df.columns.str.lower().str.strip()

        if not {'regno', 'phone'}.issubset(df.columns):
            flash("File must contain 'regno' and 'phone' ", "danger")
            return redirect(url_for('hod_dashboard'))

        df = df[['regno', 'phone']].fillna("")

        phone_pattern = re.compile(r'^\d{10}$')
        regno_pattern = re.compile(r'^U16NB\d{2}S\d{4}$')

        seen = set()   # FILE DUPLICATE TRACKER
        preview_data = []
        existing_regnos = set(
            s.regno.upper() for s in Student.query.with_entities(Student.regno).all())

        for _, row in df.iterrows():

            regno = str(row['regno']).strip().upper()
            phone = str(row['phone']).strip()

            is_valid = True
            errors = []

            # --------------------
            # REGNO VALIDATION
            # --------------------
            if not regno:
                is_valid = False
                errors.append("RegNo required")
            elif not regno_pattern.match(regno):
                is_valid = False
                errors.append("Invalid RegNo")

            #  FILE DUPLICATE
            if regno in seen:
                 is_valid = False
                 errors.append("Duplicate RegNo in uploaded file")
            else:
                seen.add(regno)

            #  DATABASE DUPLICATE
            if regno in existing_regnos:
                is_valid = False
                errors.append("RegNo already exists in database")

            # --------------------
            # PHONE VALIDATION
            # --------------------
            if not phone:
                is_valid = False
                errors.append("Phone required")
            elif not phone_pattern.match(phone):
                is_valid = False
                errors.append("Invalid Phone")
           
            preview_data.append({
              "regno": regno,
               "phone": phone,
              "valid": is_valid,
              "errors": errors,
              "error_text": ", ".join(errors),
              "type": "valid" if is_valid else "error"
            })
          

        validated_students  = ValidateStudent.query.all()
        # Fetch dashboard stats and student list to maintain view data during preview
        total_students = ValidateStudent.query.count()
        registered_students = Student.query.count()
        unregistered_students = total_students - registered_students
        students = Student.query.all()
        
        existing_regnos = list(existing_regnos)

        return render_template(
            "hod_dashboard.html",
            validated_students=validated_students,
            total_students=total_students,
            registered_students=registered_students,
            unregistered_students=unregistered_students,
            students=students,
            students_preview=preview_data,
            user=user,
            existing_regnos=existing_regnos,
            active_tab="students" 
        )

    except Exception as e:
        flash(f"Error: {str(e)} ", "danger")
        return redirect(url_for('hod_dashboard'))


# =========================
#  CONFIRM + SAVE
# =========================
@app.route('/confirm_upload_students', methods=['POST'])
@login_required(roles=['hod'])
def confirm_upload_students():

    from flask_jwt_extended import get_jwt_identity
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()

    phone_pattern = re.compile(r'^\d{10}$')
    regno_pattern = re.compile(r'^U16NB\d{2}S\d{4}$')

    total_rows = int(request.form.get('total_rows', 0))

    preview_data = []
    all_valid = True

    seen = set()  # duplicate detection inside form

    for i in range(total_rows):

        regno = request.form.get(f'regno_{i}', '').strip().upper()
        phone = request.form.get(f'phone_{i}', '').strip()

        is_valid = True
        errors = []

        # --------------------
        # REGNO CHECK
        # --------------------
        if not regno:
            is_valid = False
            errors.append("RegNo required")
        elif not regno_pattern.match(regno):
            is_valid = False
            errors.append("Invalid RegNo")

        #  duplicate inside form
        if regno in seen:
            is_valid = False
            errors.append("Duplicate RegNo found in file")
        else:
            seen.add(regno)

        # --------------------
        # PHONE CHECK
        # --------------------
        if not phone:
            is_valid = False
            errors.append("Phone required")
        elif not phone_pattern.match(phone):
            is_valid = False
            errors.append("Invalid Phone")

        if not is_valid:
            all_valid = False

        preview_data.append({
            "regno": regno,
            "phone": phone,
            "valid": is_valid,
            "errors": errors,
            "error_text": ", ".join(errors)
        })

    #return if invalid
    if not all_valid:
        flash("Fix invalid rows", "danger")

        validated_students  = ValidateStudent.query.all()
        # Fetch stats and student data to prevent "No students found" message
        total_students = ValidateStudent.query.count()
        registered_students = Student.query.count()
        unregistered_students = total_students - registered_students
        students = Student.query.all()
        existing_regnos = list(set(s.regno.upper() for s in Student.query.with_entities(Student.regno).all()))

        return render_template(
            "hod_dashboard.html",
            validated_students=validated_students,
            total_students=total_students,
            registered_students=registered_students,
            unregistered_students=unregistered_students,
            students=students,
            students_preview=preview_data,
            user=user,
            existing_regnos=existing_regnos,
            active_tab="students" 
        )

    # =========================
    # DATABASE SAVE
    # =========================

    existing_students = {s.regno: s for s in ValidateStudent.query.all()}

    inserted = 0
    updated = 0

    for row in preview_data:

        regno = row['regno']
        phone = row['phone']

        #  DB duplicate handling
        if regno in existing_students:
            if existing_students[regno].phone != phone:
                existing_students[regno].phone = phone
                updated += 1
        else:
            db.session.add(ValidateStudent(regno=regno, phone=phone))
            inserted += 1

    db.session.commit()

    flash(f"{inserted} added, {updated} updated ", "success")

    return redirect(url_for('hod_dashboard', tab='students'))



@app.route('/tpo_dashboard')
@login_required(roles=['tpo'])
def tpo_dashboard():
    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    jobs  = JobPosting.query.order_by(JobPosting.created_at.desc()).all()
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    
    return render_template('tpo_dashboard.html', 
                         user=user, 
                         jobs=jobs, 
                         announcements=announcements, 
                         now=datetime.now())


def get_tpo_analytics(selected_batch='All', selected_dept='All'):
    """Generates analytics charts using Matplotlib and returns them as base64 strings."""
    charts = {}
    
    try:
        # Data preparation
        student_query = Student.query
        application_query = Application.query.join(Student)
        
        if selected_batch != 'All':
            student_query = student_query.filter(Student.batch == selected_batch)
            application_query = application_query.filter(Student.batch == selected_batch)
            
        if selected_dept != 'All':
            student_query = student_query.filter(Student.department == selected_dept)
            application_query = application_query.filter(Student.department == selected_dept)
            
        students = student_query.all()
        applications = application_query.all()
            
        jobs = JobPosting.query.all()

        # Current Academic Year Tracking logic (e.g., 2025)
        # This identifies batches that are currently in the system regardless of placement status
        current_year = datetime.now().year
        active_academic_cycle = f"{current_year-3}-{str(current_year)[2:]}" # e.g., 2022-25

        # 1. Placement Trends (By Graduating Year)
        # Ensure 2025-28 and others reflect by initializing them even if 0 placements exist
        trend_query = Student.query
        if selected_dept != 'All':
            trend_query = trend_query.filter(Student.department == selected_dept)
        trend_students = trend_query.all()
        batch_counts = {}
        
        # Get all unique batches from the Student table
        unique_batches = db.session.query(Student.batch).distinct().all()
        for b in unique_batches:
            if b[0]:
                batch_counts[b[0]] = 0
        
        # Count selected students per batch
        for s in trend_students:
            if s.batch and s.job_applications:
                # Check if this student has ANY successful application
                is_placed = any(app.status.lower() in ['selected', 'placed', 'offered'] for app in s.job_applications)
                if is_placed:
                    batch_counts[s.batch] = batch_counts.get(s.batch, 0) + 1
        
        if batch_counts:
            # Sort batches naturally (e.g., 2022-25, 2023-26...)
            batches_sorted = sorted([b for b in batch_counts.keys() if b])
            counts = [batch_counts[b] for b in batches_sorted]
            
            plt.figure(figsize=(7, 4))
            plt.plot(batches_sorted, counts, marker='o', color='#4f46e5', linewidth=3, markersize=8, markerfacecolor='white', markeredgewidth=2)
            plt.title('Placement Success by Batch', fontweight='bold', fontsize=14, pad=15)
            plt.xlabel('Batch Duration', fontweight='bold')
            plt.ylabel('Placed Students', fontweight='bold')
            plt.grid(True, linestyle=':', alpha=0.6)
            plt.fill_between(batches_sorted, counts, color='#4f46e5', alpha=0.1)
            plt.xticks(rotation=15)
            plt.tight_layout()
            charts['trend'] = fig_to_base64(plt.gcf())
            plt.close()

        # 2. Salary Package Distribution (Filtered by Batch)
        salaries = []
        for app in applications:
            if app.status.lower() in ['selected', 'placed', 'offered'] and app.job.salary_package:
                # Extract numeric value from salary string (e.g., "12 LPA" -> 12.0)
                match = re.search(r'(\d+\.?\d*)', app.job.salary_package)
                if match:
                    salaries.append(float(match.group(1)))
        
        if salaries:
            plt.figure(figsize=(6, 4))
            plt.hist(salaries, bins=8, color='#00c853', alpha=0.7, edgecolor='black')
            plt.title(f'Salary Distribution (Batch: {selected_batch})', fontweight='bold')
            plt.xlabel('CTC in LPA')
            plt.ylabel('No. of Students')
            plt.tight_layout()
            charts['salary'] = fig_to_base64(plt.gcf())
            plt.close()

        # 3. Department Performance (Filtered by Batch)
        dept_placed = {}
        dept_total = {}
        for s in students:
            dept = s.department or "General"
            dept_total[dept] = dept_total.get(dept, 0) + 1
            if any(app.status == 'selected' for app in s.job_applications):
                dept_placed[dept] = dept_placed.get(dept, 0) + 1
        
        if dept_placed:
            labels = list(dept_placed.keys())
            percentages = [(dept_placed[d] / dept_total[d]) * 100 for d in labels]
            plt.figure(figsize=(6, 4))
            plt.bar(labels, percentages, color='#2196f3', alpha=0.8)
            plt.title(f'Dept Performance % (Batch: {selected_batch})', fontweight='bold')
            plt.ylabel('Placement %')
            plt.xticks(rotation=45)
            plt.tight_layout()
            charts['dept'] = fig_to_base64(plt.gcf())
            plt.close()

        # 4. Real-time ROI (Conversion Rate) - Top 5 recent drives (Filtered by Batch)
        roi_data = []
        for j in sorted(jobs, key=lambda x: x.created_at, reverse=True)[:5]:
            # Filter applications for this job by the selected batch
            if selected_batch == 'All':
                apps_in_job = j.applications
            else:
                apps_in_job = [a for a in j.applications if a.student.batch == selected_batch]
                
            applied = len(apps_in_job)
            hired = len([a for a in apps_in_job if a.status == 'selected'])
            if applied > 0:
                roi_data.append({
                    'name': j.company_name[:10],
                    'conversion': (hired / applied) * 100
                })
        
        if roi_data:
            names = [d['name'] for d in roi_data]
            conv = [d['conversion'] for d in roi_data]
            plt.figure(figsize=(6, 4))
            plt.barh(names, conv, color='#ff9800', alpha=0.8)
            plt.title(f'Drive ROI % (Batch: {selected_batch})', fontweight='bold')
            plt.xlabel('Conversion Rate (%)')
            plt.tight_layout()
            charts['roi'] = fig_to_base64(plt.gcf())
            plt.close()

    except Exception as e:
        print(f"Analytics Error: {str(e)}")
    
    return charts

def fig_to_base64(fig):
    """Converts a Matplotlib figure to a base64 encoded string."""
    img = BytesIO()
    fig.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode('utf8')


@app.route('/track_registrations')
@login_required(roles=['tpo'])
def track_registrations():
    from flask_jwt_extended import get_jwt_identity
    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    jobs  = JobPosting.query.order_by(JobPosting.created_at.desc()).all()
    return render_template('track_registrations.html', user=user, jobs=jobs, now=datetime.now())


@app.route('/post_job', methods=['POST'])
@login_required(roles=['tpo'])
def post_job():
    from flask_jwt_extended import get_jwt_identity
    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()

    company_name = request.form.get('company_name')
    job_role = request.form.get('job_role')
    job_description = request.form.get('job_description')
    eligibility_criteria = request.form.get('eligibility_criteria')
    salary_package = request.form.get('salary_package')
    location = request.form.get('location')
    deadline_str = request.form.get('deadline')
    form_link = request.form.get('form_link')
    secondary_form_link = request.form.get('secondary_form_link')
    min_cgpa = request.form.get('min_cgpa', 0.0, type=float)
    max_backlogs = request.form.get('max_backlogs', 0, type=int)

    try:
        deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
        new_job = JobPosting(
            company_name=company_name,
            job_role=job_role,
            job_description=job_description,
            eligibility_criteria=eligibility_criteria,
            salary_package=salary_package,
            location=location,
            deadline=deadline,
            form_link=form_link,
            secondary_form_link=secondary_form_link,
            min_cgpa=min_cgpa,
            max_backlogs=max_backlogs,
            status='open',
            posted_by=user.id
        )
        db.session.add(new_job)
        db.session.commit()
        
        # Automated Notification: Alert all students about the new drive
        students = Student.query.all()
        student_emails = [s.email for s in students]
        if student_emails:
            send_email(
                subject=f'New Recruitment Drive: {company_name} - {job_role}',
                recipients=student_emails,
                body=f"Hello Students,\n\nA new recruitment drive has been posted for {company_name} for the role of {job_role}.\n\nCriteria:\n- Min CGPA: {min_cgpa}\n- Max Backlogs: {max_backlogs}\n- Salary: {salary_package}\n- Deadline: {deadline_str}\n\nPlease check your dashboard to apply.\n\nBest Regards,\nTraining & Placement Cell"
            )
        
        flash('Job posting published successfully and students notified!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error publishing job: {str(e)}', 'danger')
        return redirect(url_for('tpo_dashboard'))

    # Instead of just flashing success, we show the WhatsApp Preview
    # as per user's "Best Practice" requirement.
    return render_template('preview.html', 
                           dept=request.form.get('department'), 
                           company=company_name, 
                           details=f"{job_role} - {salary_package}. {job_description}...",
                           form_link=form_link,
                           deadline=deadline,
                           now=datetime.now())

@app.route('/preview-update', methods=['POST'])
@login_required(roles=['tpo'])
def preview_update():
    # This route can be used if we want to preview WITHOUT saving first, 
    # but the user requested saving first in the workflow.
    dept = request.form.get('department')
    company = request.form.get('company_name')
    job_role = request.form.get('job_role')
    salary = request.form.get('salary_package')
    form_link=request.form.get('form-link')
    details = f"Role: {job_role} | Package: {salary}"
    
    return render_template('preview.html', dept=dept, company=company, details=details,form_link=form_link ,now=datetime.now())

@app.route('/send-actual-message', methods=['POST'])
@login_required(roles=['tpo'])
def send_actual_message():
    dept = request.form.get('dept')
    company = request.form.get('company')
    details = request.form.get('details')
    form_link=request.form.get('form_link')


    # WHAPI Logic - User should replace with their real token and group IDs
    token = os.getenv('WHAPI_TOKEN', 'YOUR_WHAPI_TOKEN')
    
    # Mapping departments to Whapi Group IDs
    group_map = {
        "BCA": os.getenv('WHAPI_GROUP_BCA'),
        "BBA": os.getenv('WHAPI_GROUP_BBA'),
        "B.Tech": os.getenv('WHAPI_GROUP_BTECH')
    }
    
    target_group = group_map.get(dept)
    
    if not target_group:
        flash(f"No WhatsApp Group ID configured for department: {dept}", "warning")
        return redirect(url_for('tpo_dashboard'))

    payload = {
        "to": target_group,
        "body": f"📢 *Placement Alert: {dept}*\n\n🏢 Company: *{company}*\n📝 Details: {details} \n Link To Apply: {form_link}\n\n_Sent via Novasphere Portal_"
    }
    
    headers = {
        "Authorization": f"Bearer {token}", 
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post("https://gate.whapi.cloud/messages/text", json=payload, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            flash(f"Success! Placement alert blasted to {dept} WhatsApp group.", "success")
        else:
            flash(f"Whapi Error: {response.text}", "danger")
    except Exception as e:
        flash(f"Connection Error: Could not reach Whapi servers. {str(e)}", "danger")
    
    return redirect(url_for('tpo_dashboard'))


@app.route('/job_applicants/<int:job_id>')
@login_required(roles=['tpo'])
def job_applicants(job_id):
    job = JobPosting.query.get_or_404(job_id)
    # Fetch applications with joined students
    applications = Application.query.filter_by(job_id=job_id).all()
    departments = sorted(list(set(app.student.department for app in applications if app.student.department)))
    return render_template('job_applicants.html', job=job, applications=applications, departments=departments)


@app.route('/update_application_status/<int:app_id>', methods=['POST'])
@login_required(roles=['tpo'])
def update_application_status(app_id):
    application = Application.query.get_or_404(app_id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'shortlisted', 'interviewed', 'rejected', 'selected']:
        application.status = new_status
        db.session.commit()
        
        # Automated Notification: Alert the student about status change
        status_colors = {'shortlisted': 'congratulations', 'rejected': 'update', 'selected': 'BIG NEW STORY'} # Internal mapping for wording
        send_email(
            subject=f'Placement Update: {application.job.company_name}',
            recipients=[application.student.email],
            body=f"Hello {application.student.name},\n\nYour application status for the position of {application.job.job_role} at {application.job.company_name} has been updated to: {new_status.upper()}.\n\nPlease log in to your dashboard for more details.\n\nBest Regards,\nTraining & Placement Cell"
        )
        
        flash(f'Status updated to {new_status} and student notified!', 'success')
    else:
        flash('Invalid status provided.', 'danger')
        
    return redirect(url_for('job_applicants', job_id=application.job_id))


@app.route('/update_job_form/<int:job_id>', methods=['GET', 'POST'])
@login_required(roles=['tpo'])
def update_job_form(job_id):
    job = JobPosting.query.get_or_404(job_id)
    
    if request.method == 'GET':
        # Return job details for the edit modal
        return {
            'id': job.id,
            'company_name': job.company_name,
            'job_role': job.job_role,
            'job_description': job.job_description,
            'eligibility_criteria': job.eligibility_criteria,
            'salary_package': job.salary_package,
            'location': job.location,
            'deadline': job.deadline.strftime('%Y-%m-%dT%H:%M'),
            'form_link': job.form_link,
            'secondary_form_link': job.secondary_form_link,
            'min_cgpa': job.min_cgpa,
            'max_backlogs': job.max_backlogs
        }

    # Extract all fields from the form
    company_name = request.form.get('company_name')
    job_role = request.form.get('job_role')
    job_description = request.form.get('job_description')
    eligibility_criteria = request.form.get('eligibility_criteria')
    department = request.form.get('department')
    location = request.form.get('location')
    deadline_str = request.form.get('deadline')
    form_link = request.form.get('form_link')
    secondary_form_link = request.form.get('secondary_form_link')
    min_cgpa = request.form.get('min_cgpa', 0.0, type=float)
    max_backlogs = request.form.get('max_backlogs', 0, type=int)
    
    try:
        job.company_name = company_name
        job.job_role = job_role
        job.job_description = job_description
        job.eligibility_criteria = eligibility_criteria
        job.location = location
        job.min_cgpa = min_cgpa
        job.max_backlogs = max_backlogs
        if deadline_str:
            job.deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
        job.form_link = form_link
        job.secondary_form_link = secondary_form_link
        
        db.session.commit()
        flash(f'Placement drive for {job.company_name} updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating drive: {str(e)}', 'danger')
        
    return redirect(url_for('tpo_dashboard'))
    
@app.route('/delete_job/<int:job_id>', methods=['POST'])
@login_required(roles=['tpo'])
def delete_job(job_id):
    job = JobPosting.query.get_or_404(job_id)
    try:
        db.session.delete(job)
        db.session.commit()
        flash(f'Placement drive for {job.company_name} deleted successfully!', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting drive: {str(e)}', 'danger')
        
    return redirect(url_for('tpo_dashboard'))


@app.route('/download_applicants_excel/<int:job_id>')
@login_required(roles=['tpo'])
def download_applicants_excel(job_id):
    job = JobPosting.query.get_or_404(job_id)
    applications = Application.query.filter_by(job_id=job_id).all()
    
    data = []
    for app in applications:
        data.append({
            'Student Name': app.student.name,
            'Reg No': app.student.regno,
            'Email': app.student.email,
            'Phone': app.student.phone,
            'Dept': app.student.department,
            'Sem': app.student.sem,
            'CGPA': app.student.cgpa,
            'Status': app.status.capitalize(),
            'Applied Date': app.applied_at.strftime('%Y-%m-%d %H:%M')
        })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Applicants')
    
    output.seek(0)
    filename = f"Applicants_{job.company_name}_{job.job_role}.xlsx".replace(' ', '_')
    
    return send_file(output, 
                     download_name=filename, 
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/download_applicants_pdf/<int:job_id>')
@login_required(roles=['tpo'])
def download_applicants_pdf(job_id):
    job = JobPosting.query.get_or_404(job_id)
    applications = Application.query.filter_by(job_id=job_id).all()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    
    styles = getSampleStyleSheet()
    title = Paragraph(f"<b>Applicant Report - {job.company_name}</b>", styles['Title'])
    subtitle = Paragraph(f"Role: {job.job_role} | Date: {datetime.now().strftime('%d %b, %Y')}", styles['Heading2'])
    elements.extend([title, subtitle, Spacer(1, 20)])
    
    # Table Header
    data = [['Student Name', 'Reg No', 'Email', 'Dept/Sem', 'CGPA', 'Status']]
    
    # Table Data
    for app in applications:
        data.append([
            app.student.name,
            app.student.regno,
            app.student.email,
            f"{app.student.department}/{app.student.sem}",
            str(app.student.cgpa),
            app.status.capitalize()
        ])
    
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    filename = f"Applicants_{job.company_name}_{job.job_role}.pdf".replace(' ', '_')
    
    return send_file(buffer, 
                     download_name=filename, 
                     as_attachment=True,
                     mimetype='application/pdf')


@app.route('/change_password', methods=['POST'])
@jwt_required()
def change_password():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not bcrypt.check_password_hash(user.password, current_password):
        flash('Current password incorrect.', 'danger')
    elif new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
    else:
        user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()
        flash('Password updated successfully!', 'success')
        
    # Redirect back to the referrer or dashboard
    return redirect(request.referrer or url_for('home'))


@app.route('/submit_secondary_data/<int:job_id>', methods=['POST'])
@login_required(roles=['student'])
def submit_secondary_data(job_id):
    claims = get_jwt()
    regno = claims.get('regno')
    student = Student.query.filter_by(regno=regno).first()
    
    if not student:
        flash('Student record not found.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    application = Application.query.filter_by(job_id=job_id, student_id=student.id).first()
    if not application:
        flash('You must apply to the primary link first.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    secondary_data = request.form.get('secondary_data')
    if secondary_data:
        application.secondary_data = secondary_data
        db.session.commit()
        
        # Check if there is a secondary link to redirect to
        job = JobPosting.query.get(job_id)
        if job and job.secondary_form_link:
            clean_link = job.secondary_form_link.strip()
            target_url = clean_link if clean_link.startswith(('http://', 'https://')) else 'https://' + clean_link
            flash('External application ID saved! Redirecting to the next procedure...', 'success')
            return redirect(target_url)
        
        flash('Secondary application data saved successfully!', 'success')
    else:
        flash('Please fill in the required details.', 'warning')
        
    return redirect(url_for('student_dashboard'))


# ─── Notice Board Routes ─────────────────────────────────────────────────────

@app.route('/post_announcement', methods=['POST'])
@login_required(roles=['tpo'])
def post_announcement():
    email = get_jwt_identity()
    user = User.query.filter_by(email=email).first()
    
    title = request.form.get('title')
    content = request.form.get('content')
    category = request.form.get('category', 'general')
    
    try:
        new_note = Announcement(
            title=title,
            content=content,
            category=category,
            posted_by=user.id
        )
        db.session.add(new_note)
        db.session.commit()
        flash('Announcement posted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error posting announcement: {str(e)}', 'danger')
        
    return redirect(url_for('tpo_dashboard'))


@app.route('/delete_announcement/<int:id>', methods=['POST'])
@login_required(roles=['tpo'])
def delete_announcement(id):
    note = Announcement.query.get_or_404(id)
    db.session.delete(note)
    db.session.commit()
    flash('Announcement removed.', 'info')
    return redirect(url_for('tpo_dashboard'))

#contact
@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')
    
    # For now, we just print the message to console. In production, this should send an email to TPO or save in DB.
    print(f"Contact Form Submission:\nName: {name}\nEmail: {email}\nMessage: {message}")
    
    flash('Thank you for reaching out! The TPO will contact you soon.', 'success')
    return redirect(url_for('home'))

# Handle Chrome DevTools noise to clean up logs
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def devtools_json():
    return jsonify({}), 200



# ─── Chatbot Route ────────────────────────────────────────────────────────────

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message') if data else None
    
    if not user_message or not os.getenv('GEMINI_API_KEY'):
        return jsonify({'reply': "I didn't catch that. Could you please repeat?"})

    try:
        system_prompt = """
        You are the Novasphere Placement Assistant, a professional AI guide for the Novasphere Placement Portal.
        Your goal is to assist Students, Training & Placement Officers (TPOs), and Heads of Departments (HODs).

        ### 1. Key User Features:
        - Students: Register (requires pre-verified RegNo and matching Batch/Phone), update profile (skills, address, resume), use the ATS Resume Analyzer (PDFs < 5MB), and apply to Job Drives.
        - TPOs: Publish Job Drives with eligibility (CGPA, backlogs), manage applicant status (Shortlisted, Interviewed, Selected, etc.), send WhatsApp alerts via Whapi, and post Announcements to the Notice Board.
        - HODs: Upload Excel/CSV lists of students for verification, track registration progress, and view departmental stats.
        - Admin/Principal: Manage staff roles, view overall placement analytics (Salary distribution, Dept performance), and manage application records.

        ### 2. Specific Technical Knowledge:
        - Registration: RegNos must follow the format 'U16NB[Year]S[UniqueNumber]' (e.g., U16NB23S0120). Students can only register if their RegNo and Phone were first uploaded by an HOD into the verification table.
        - ATS Analyzer: Uses Groq AI to score resumes against job descriptions (>50 chars). Only PDF files are supported.
        - Eligibility Checks: The portal automatically blocks applications if a student's CGPA is below the 'min_cgpa' or if backlogs exceed 'max_backlogs' defined by the TPO.

        ### 3. Guidelines:
        - Tone: Professional, encouraging, and helpful.
        - Privacy: Do not share specific user contact details.
        - Limitations: You cannot check real-time database records (e.g., "Has student X registered?"). Instead, guide users to the relevant dashboard tab (e.g., 'Registration Track' for TPOs).
        - If a student cannot apply, suggest checking their profile for missing CGPA/Resume or verifying they meet the job's criteria.
        - If you don't know an answer, politely suggest contacting the TPO Office or using the 'Contact' form.
        """
        
        response = client.models.generate_content(
            model=model,
            contents=[f"{system_prompt}\n\nUser: {user_message}\nAssistant:"]
        )
        
        reply = response.text.strip() if response.text else "I'm sorry, I couldn't generate a response."
        return jsonify({'reply': reply})
        
    except Exception as e:
        print(f"Chatbot Error: {str(e)}")
        return jsonify({'reply': "I'm having a bit of a technical glitch. Could you try asking again in a moment?"})
@app.route('/project-profile')
def project_showcase():
    return render_template('project_showcase.html')
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    



        
