"""
database.py - Database Management & Connection Module for SmartPark
====================================================================
Designed for 3rd-Year B.Tech CSE Project:
"Smart Parking Management System using Operating Systems & DBMS Concepts"

Database Schema:
- users: Drivers and Parking Space Providers (with werkzeug hashed passwords)
- spaces: Parking facilities/lots (matching the frontend: Clock Tower, Parade Ground, etc.)
- parking_slots: Physical individual parking slots per facility
- vehicles: Registered vehicles per driver
- bookings: Confirmed/cancelled reservations
- entry_exit_logs: Audit logging for entry and exit timestamps
"""

import sqlite3
import os

DB_NAME = "smartpark.db"

def get_db_connection():
    """
    Returns a thread-safe connection to SQLite with row_factory enabled
    and Foreign Key constraints enforced.
    """
    conn = sqlite3.connect(DB_NAME, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """
    Creates tables and seeds initial parking facilities and slots.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users / Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        role TEXT CHECK(role IN ('driver', 'provider')) DEFAULT 'driver',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Spaces / Facilities Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS spaces (
        space_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        address TEXT NOT NULL,
        area TEXT NOT NULL,
        price REAL NOT NULL,
        capacity INTEGER NOT NULL,
        kind TEXT DEFAULT 'Covered',
        hours TEXT DEFAULT 'Open 24 hours',
        rating TEXT DEFAULT '4.8',
        owner_id INTEGER NULL,
        FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE SET NULL
    );
    """)

    # 3. Physical Parking Slots Table (For OS FAS Allocation)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_slots (
        slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        space_id TEXT NOT NULL,
        slot_number TEXT NOT NULL,
        status TEXT CHECK(status IN ('Available', 'Occupied', 'Reserved')) DEFAULT 'Available',
        FOREIGN KEY (space_id) REFERENCES spaces(space_id) ON DELETE CASCADE,
        UNIQUE (space_id, slot_number)
    );
    """)

    # 4. Vehicles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plate TEXT NOT NULL,
        model TEXT NOT NULL,
        type TEXT DEFAULT 'Car',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    );
    """)

    # 5. Bookings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        booking_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        space_id TEXT NOT NULL,
        slot_id INTEGER NOT NULL,
        slot_number TEXT NOT NULL,
        driver_name TEXT NOT NULL,
        plate TEXT NOT NULL,
        vehicle_model TEXT DEFAULT '',
        booking_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        hours INTEGER DEFAULT 1,
        amount REAL NOT NULL,
        payment_method TEXT DEFAULT 'UPI',
        status TEXT CHECK(status IN ('Confirmed', 'Cancelled', 'Completed')) DEFAULT 'Confirmed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (space_id) REFERENCES spaces(space_id) ON DELETE CASCADE,
        FOREIGN KEY (slot_id) REFERENCES parking_slots(slot_id) ON DELETE CASCADE
    );
    """)

    # 6. Entry / Exit Logs Table (Audit logging for DBMS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS entry_exit_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id TEXT NOT NULL,
        entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        exit_time TIMESTAMP NULL,
        FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE
    );
    """)

    conn.commit()

    # Seed initial spaces and physical slots if empty
    cursor.execute("SELECT COUNT(*) AS count FROM spaces;")
    if cursor.fetchone()["count"] == 0:
        seed_spaces = [
            ('SP-101', 'Clock Tower Smart Parking', 'MDDA Complex, Rajpur Road, Dehradun', 'Clock Tower', 30, 20, 'Covered', 'Open 24 hours', '4.8'),
            ('SP-102', 'Parade Ground Parking', 'Parade Ground, Dehradun', 'Parade Ground', 25, 16, 'Open air', '6:00 AM – 10:00 PM', '4.7'),
            ('SP-103', 'Railway Station Parking', 'Dehradun Railway Station, Haridwar Road', 'Railway Station', 30, 18, 'Covered', 'Open 24 hours', '4.6'),
            ('SP-104', 'Rajpur Road Central Parking', 'Rajpur Road, near Clock Tower, Dehradun', 'Rajpur Road', 35, 15, 'Covered', '5:00 AM – 12:00 AM', '4.9'),
            ('SP-105', 'Pacific Mall Parking', 'Pacific Mall, Rajpur Road, Dehradun', 'Jakhan', 20, 25, 'Covered', '10:00 AM – 10:00 PM', '4.5'),
            ('SP-106', 'ISBT Dehradun Parking', 'Inter State Bus Terminal, Shimla Bypass Road', 'ISBT', 20, 15, 'Open air', 'Open 24 hours', '4.8'),
            ('SP-107', 'Paltan Bazaar Parking', 'Paltan Bazaar, near Clock Tower, Dehradun', 'Paltan Bazaar', 25, 10, 'Open air', '8:00 AM – 9:00 PM', '4.6'),
            ('SP-108', 'Dilaram Bazaar Parking', 'Rajpur Road, Dilaram Bazaar, Dehradun', 'Dilaram Bazaar', 25, 12, 'Open air', '6:00 AM – 11:00 PM', '4.7'),
            ('MY-201', 'Doon Campus Parking', 'Graphic Era Road, Clement Town, Dehradun', 'Clement Town', 25, 12, 'Open air', '8:00 AM – 8:00 PM', '4.8'),
            ('MY-202', 'Rajpur Road Parking', 'Rajpur Road, Dehradun', 'Rajpur Road', 30, 10, 'Covered', 'Open 24 hours', '4.7')
        ]

        cursor.executemany("""
            INSERT INTO spaces (space_id, name, address, area, price, capacity, kind, hours, rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, seed_spaces)
        conn.commit()

        # Seed physical slots for each space
        slots_to_seed = []
        for space in seed_spaces:
            space_id = space[0]
            capacity = space[5]
            for i in range(1, capacity + 1):
                slots_to_seed.append((space_id, f"SLOT-{i:02d}", "Available"))

        cursor.executemany("""
            INSERT INTO parking_slots (space_id, slot_number, status)
            VALUES (?, ?, ?);
        """, slots_to_seed)
        conn.commit()
        print(f"[DB] Initialized database '{DB_NAME}' with {len(seed_spaces)} spaces and {len(slots_to_seed)} physical slots.")
    else:
        print(f"[DB] Database '{DB_NAME}' verified.")

    conn.close()

if __name__ == "__main__":
    init_db()
