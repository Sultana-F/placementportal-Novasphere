from app import app
from models import db
from sqlalchemy import text

def run_migrations():
    with app.app_context():
        print("Starting migrations...")
        try:
            # 1. Update User role enum in MySQL
            print("Altering users.role enum...")
            db.session.execute(text(
                "ALTER TABLE users MODIFY COLUMN role ENUM('principal', 'hod', 'student', 'tpo', 'recruiter') NOT NULL;"
            ))
            db.session.commit()
            print("users.role altered successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"Error altering users.role enum: {e}")

        try:
            # 2. Add recruiter_id column to job_post table
            print("Ensuring recruiter_id column and foreign key exist on job_post...")
            # Check if the column already exists
            col_exists = db.session.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_post' AND COLUMN_NAME = 'recruiter_id'"
            )).scalar()

            if not col_exists:
                db.session.execute(text(
                    "ALTER TABLE job_post ADD COLUMN recruiter_id INT NULL;"
                ))
                db.session.commit()
                print("recruiter_id column added.")
            else:
                print("recruiter_id column already exists, skipping column add.")

            # Check if a foreign-key exists for recruiter_id referencing users.id
            fk_exists = db.session.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_post' AND COLUMN_NAME = 'recruiter_id' AND REFERENCED_TABLE_NAME = 'users' AND REFERENCED_COLUMN_NAME = 'id'"
            )).scalar()

            if not fk_exists:
                try:
                    db.session.execute(text(
                        "ALTER TABLE job_post ADD CONSTRAINT fk_jobpost_recruiter FOREIGN KEY (recruiter_id) REFERENCES users(id) ON DELETE SET NULL;"
                    ))
                    db.session.commit()
                    print("Foreign key for recruiter_id added.")
                except Exception as fk_e:
                    db.session.rollback()
                    print(f"Warning: failed to add foreign key for recruiter_id: {fk_e}")
            else:
                print("Foreign key for recruiter_id already exists, skipping fk add.")
        except Exception as e:
            db.session.rollback()
            print(f"Error/Warning adding recruiter_id to job_post (might already exist): {e}")

        try:
            # 3. Create recruiter_profiles table
            print("Creating recruiter_profiles table...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS recruiter_profiles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL UNIQUE,
                    company_name VARCHAR(100) NOT NULL,
                    company_website VARCHAR(255) NULL,
                    company_logo VARCHAR(255) NULL,
                    designation VARCHAR(50) NULL,
                    is_approved BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB;
            """))
            db.session.commit()
            print("recruiter_profiles table verified/created successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating recruiter_profiles table: {e}")

        print("Migration process finished.")

if __name__ == '__main__':
    run_migrations()
