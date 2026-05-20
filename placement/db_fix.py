"""
db_fix.py — One-shot database cleanup script for NovaSphere placement app.

Fixes:
  1. Deletes applications linked to orphaned students (no matching user)
  2. Deletes orphaned student records (student_id points to non-existent users)
  3. Drops the legacy 'job_postings' table (duplicate of 'job_post')

Run once:  python db_fix.py
"""
from app import app
from models import db
from sqlalchemy import text


def fix_orphaned_data():
    print("\n=== Step 1: Finding Orphaned Student IDs ===")

    # Find student IDs where no matching user exists (raw SQL to avoid ORM cascade issues)
    result = db.session.execute(text("""
        SELECT s.id, s.student_id, s.name, s.regno
        FROM student s
        LEFT JOIN users u ON s.student_id = u.id
        WHERE u.id IS NULL
    """))
    orphaned = result.fetchall()

    if not orphaned:
        print("  ✅ No orphaned student records found.")
        return

    orphaned_student_ids = [row[0] for row in orphaned]
    print(f"  Found {len(orphaned_student_ids)} orphaned student records.")
    for row in orphaned[:5]:
        print(f"    Student ID:{row[0]} | student_id:{row[1]} | name:{row[2]} | regno:{row[3]}")
    if len(orphaned) > 5:
        print(f"    ... and {len(orphaned) - 5} more")

    # Step 1a: Delete applications linked to orphaned students first
    print("\n=== Step 2: Deleting Applications Linked to Orphaned Students ===")
    if orphaned_student_ids:
        id_list = ",".join(str(i) for i in orphaned_student_ids)
        app_result = db.session.execute(
            text(f"DELETE FROM applications WHERE student_id IN ({id_list})")
        )
        print(f"  Deleted {app_result.rowcount} linked application(s).")
    else:
        print("  No applications to delete.")

    # Step 1b: Delete orphaned student records
    print("\n=== Step 3: Deleting Orphaned Student Records ===")
    if orphaned_student_ids:
        id_list = ",".join(str(i) for i in orphaned_student_ids)
        stu_result = db.session.execute(
            text(f"DELETE FROM student WHERE id IN ({id_list})")
        )
        print(f"  Deleted {stu_result.rowcount} orphaned student record(s).")
    else:
        print("  No orphaned students to delete.")

    db.session.commit()
    print("  ✅ Committed successfully.")


def drop_legacy_table():
    print("\n=== Step 4: Dropping Legacy 'job_postings' Table ===")
    try:
        inspector_result = db.session.execute(
            text("SHOW TABLES LIKE 'job_postings'")
        ).fetchone()

        if inspector_result:
            db.session.execute(text("DROP TABLE IF EXISTS job_postings"))
            db.session.commit()
            print("  ✅ Dropped legacy 'job_postings' table.")
        else:
            print("  [.] 'job_postings' table not found, nothing to drop.")
    except Exception as e:
        db.session.rollback()
        print(f"  ❌ Error dropping legacy table: {e}")


def verify():
    print("\n=== Step 5: Final Verification ===")

    user_count = db.session.execute(text("SELECT COUNT(*) FROM users")).scalar()
    student_user_count = db.session.execute(text("SELECT COUNT(*) FROM users WHERE role='student'")).scalar()
    student_record_count = db.session.execute(text("SELECT COUNT(*) FROM student")).scalar()

    orphan_check = db.session.execute(text("""
        SELECT COUNT(*) FROM student s
        LEFT JOIN users u ON s.student_id = u.id
        WHERE u.id IS NULL
    """)).scalar()

    print(f"  Total users             : {user_count}")
    print(f"  Student-role users      : {student_user_count}")
    print(f"  Student profile records : {student_record_count}")
    print(f"  Remaining orphans       : {orphan_check}")

    if orphan_check == 0:
        print("\n  ✅ All clean! No orphaned records remain.")
    else:
        print(f"\n  ⚠️  {orphan_check} orphaned records still exist — check manually.")

    print("\n  Remaining valid student records:")
    rows = db.session.execute(text("""
        SELECT s.id, s.regno, s.name, s.student_id
        FROM student s
        JOIN users u ON s.student_id = u.id
    """)).fetchall()
    for row in rows:
        print(f"    ✅ Student.id:{row[0]} | regno:{row[1]} | name:{row[2]} | user_id:{row[3]}")


if __name__ == '__main__':
    with app.app_context():
        try:
            fix_orphaned_data()
            drop_legacy_table()
            verify()
            print("\n=== All done! The database is clean. You can now login. ===\n")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Fatal error: {e}")
