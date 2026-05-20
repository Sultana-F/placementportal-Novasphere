from app import app, bcrypt
from models import db, User, Student

def test_student_login_logic(regno, password):
    print(f"\n--- Testing Student Login Logic for {regno} ---")
    with app.app_context():
        # Step 1: Look up by regno in Student table
        student = Student.query.filter_by(regno=regno).first()
        if not student:
            print(f"FAILED: No student found with regno {regno}")
            return False
        
        print(f"SUCCESS: Found student {student.name} with email {student.email}")

        # Step 2: Fetch the corresponding User record via email
        user = User.query.filter_by(email=student.email, role='student').first()
        if not user:
            print(f"FAILED: No user record found for email {student.email} with role 'student'")
            return False
        
        # Step 3: Verify password
        if bcrypt.check_password_hash(user.password, password):
            print("SUCCESS: Password verified!")
            return True
        else:
            print("FAILED: Password hash mismatch")
            return False

def test_admin_login_logic(email, password):
    print(f"\n--- Testing Admin Login Logic for {email} ---")
    with app.app_context():
        # Step 1: Look up by email
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"FAILED: No user found with email {email}")
            return False
        
        if user.role == 'student':
            print("FAILED: User is a student, not admin/staff")
            return False
            
        # Step 2: Verify password
        if bcrypt.check_password_hash(user.password, password):
            print(f"SUCCESS: Password verified for {user.role} {user.full_name}!")
            return True
        else:
            print("FAILED: Password hash mismatch")
            return False

if __name__ == "__main__":
    # Test cases based on seed data
    test_student_login_logic('20221001', 'Student@123')
    test_admin_login_logic('rohanv@gmail.com', 'Rverma123principal')
