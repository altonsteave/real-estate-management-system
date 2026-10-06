"""
Elite Estates — Database Initialization Script
Run this once to create the SQLite database with schema and sample data.
Usage: python init_db.py
"""
import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'elite_estates.db')

def init_db():
    # Remove old DB if exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed old database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # Read and execute schema
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_path, 'r') as f:
        cur.executescript(f.read())
    print("Schema created successfully.")

    # Insert default admin (password: ADMIN123, SHA256 hashed)
    admin_pwd = hashlib.sha256('ADMIN123'.encode()).hexdigest()
    cur.execute(
        "INSERT INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)",
        ('Administrator', 'admin@eliteestates.com', '9876543210', admin_pwd, 'admin')
    )

    # Insert demo user (password: password123)
    demo_pwd = hashlib.sha256('password123'.encode()).hexdigest()
    cur.execute(
        "INSERT INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)",
        ('Demo User', 'user@demo.com', '9999999999', demo_pwd, 'user')
    )

    # Insert sample properties
    sample_props = [
        (2, 'Elegant Sea-View Villa',
         'Breathtaking ocean views, private pool, modern architecture with heritage touches.',
         25000000, 'Kovalam, Kerala', 8.3812, 76.9787, 3, '{"hospital":2,"supermarket":1,"bus_stop":5,"metro_station":0,"school":3}',
         'sale', 4, 3, 3500, None, 'approved'),
        (2, 'Heritage Bungalow',
         'Colonial-era bungalow lovingly restored with all modern amenities.',
         18000000, 'Fort Kochi, Kerala', 9.9658, 76.2421, 4, '{"hospital":3,"supermarket":4,"bus_stop":8,"metro_station":0,"school":5}',
         'sale', 5, 4, 4200, None, 'approved'),
        (2, 'Penthouse Suite',
         'Ultra-luxury penthouse on the 32nd floor with panoramic city skyline views.',
         85000, 'Thiruvananthapuram', 8.5241, 76.9366, 5, '{"hospital":5,"supermarket":6,"bus_stop":12,"metro_station":2,"school":7}',
         'rent', 3, 3, 2800, None, 'approved'),
        (2, 'Backwater Estate',
         'Exclusive estate on the banks of Ashtamudi Lake. Private boat jetty.',
         45000000, 'Kollam, Kerala', 8.8932, 76.6141, 3, '{"hospital":2,"supermarket":3,"bus_stop":4,"metro_station":0,"school":2}',
         'auction', 6, 5, 6000, None, 'approved'),
        (2, 'Luxury Penthouse (Closed)',
         'A premium penthouse that was recently auctioned.',
         12000000, 'Kochi, Kerala', 9.9312, 76.2673, 5, '{"hospital":5,"supermarket":5,"bus_stop":10,"metro_station":1,"school":5}',
         'auction', 4, 4, 3200, '2026-05-01 10:00:00', 'approved'),
    ]

    # Insert sample properties and get their IDs
    property_ids = []
    for prop in sample_props:
        cur.execute(
            """INSERT INTO properties 
            (user_id, title, description, price, location, latitude, longitude, 
             locality_score, locality_details, type, bedrooms, bathrooms, area, auction_end, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            prop
        )
        property_ids.append(cur.lastrowid)

    # Insert sample images (using files found in static/uploads)
    sample_images = [
        (property_ids[0], '20260413122156_seaface.jpg', 1),
        (property_ids[0], '20260413130237_seaface.jpg', 0),
        (property_ids[1], '20260413122520_palace.jpg', 1),
        (property_ids[2], '20260413121812_penthouse.webp', 1),
        (property_ids[3], '20260331090958_backgrond.jpg', 1),
    ]
    for img in sample_images:
        cur.execute(
            "INSERT INTO property_images (property_id, filename, is_primary) VALUES (?, ?, ?)",
            img
        )

    # Set auction end for auction properties
    cur.execute(
        "UPDATE properties SET auction_end = datetime('now', '+7 days') WHERE type='auction'"
    )

    # Insert sample bookings
    sample_bookings = [
        (2, property_ids[0], '2026-05-10', '10:00 AM', 'pending'),
        (2, property_ids[1], '2026-05-11', '02:00 PM', 'approved'),
    ]
    for b in sample_bookings:
        cur.execute(
            "INSERT INTO bookings (user_id, property_id, appointment_date, time_slot, status) VALUES (?, ?, ?, ?, ?)",
            b
        )
    
    # Add winning bid for the closed auction (property_ids[4])
    cur.execute(
        "INSERT INTO bids (user_id, property_id, amount) VALUES (?, ?, ?)",
        (2, property_ids[4], 15000000)
    )

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at: {DB_PATH}")
    print("Default accounts:")
    print("  Admin: admin@eliteestates.com / ADMIN123")
    print("  User:  user@demo.com / password123")

if __name__ == '__main__':
    init_db()
