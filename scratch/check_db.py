import sqlite3
import os

DATABASE = 'elite_estates.db'

def check_db():
    if not os.path.exists(DATABASE):
        print(f"Database {DATABASE} not found.")
        return

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("--- Property Images ---")
    rows = cur.execute("SELECT * FROM property_images").fetchall()
    for row in rows:
        print(dict(row))

    print("\n--- Properties ---")
    rows = cur.execute("SELECT id, title, latitude, longitude FROM properties").fetchall()
    for row in rows:
        print(dict(row))

    conn.close()

if __name__ == "__main__":
    check_db()
