from app import app
from models import db
from sqlalchemy import text, inspect

with app.app_context():
    tables = inspect(db.engine).get_table_names()
    if 'job_postings' in tables:
        db.session.execute(text('DROP TABLE job_postings'))
        db.session.commit()
        print('Dropped legacy job_postings table.')
    else:
        print('job_postings table not found, nothing to do.')

    # Final state
    remaining = inspect(db.engine).get_table_names()
    print('Tables now:', remaining)
