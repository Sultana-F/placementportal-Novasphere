from app import app
from models import db
from sqlalchemy import text, inspect

with app.app_context():
    students = db.session.execute(text(
        'SELECT s.id, s.regno, s.name, s.student_id FROM student s JOIN users u ON s.student_id = u.id'
    )).fetchall()

    orphans = db.session.execute(text(
        'SELECT COUNT(*) FROM student s LEFT JOIN users u ON s.student_id = u.id WHERE u.id IS NULL'
    )).scalar()

    apps = db.session.execute(text('SELECT COUNT(*) FROM applications')).scalar()

    all_tables = inspect(db.engine).get_table_names()
    legacy = 'job_postings' in all_tables

    print('=== CLEAN DB VERIFICATION ===')
    print('Orphaned student records :', orphans)
    print('Applications remaining   :', apps)
    print('Legacy job_postings table:', 'EXISTS (needs drop)' if legacy else 'GONE (clean)')
    print('All tables               :', all_tables)
    print()
    print('Valid student records:')
    for r in students:
        print('  Student.id:{} | regno:{} | name:{} | user_id:{}'.format(r[0], r[1], r[2], r[3]))
