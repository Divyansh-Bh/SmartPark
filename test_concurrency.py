"""
test_concurrency.py - Automated Concurrency & Race Condition Verification
========================================================================
Course: Operating Systems & DBMS Lab (3rd-Year B.Tech CSE)
Topic: Concurrency Control, Mutual Exclusion, and Database Race Conditions

Scenario:
Clock Tower Smart Parking (SP-101) has only 1 remaining free parking slot.
10 concurrent users simultaneously submit booking requests to the server
at the exact same microsecond using threading.Barrier.

Expected Outcome:
- The OS FCFS Queue receives and sequences the requests.
- The First Available Slot (FAS) algorithm assigns the slot to the first request.
- The SQLite conditional transaction locks the slot atomically.
- Exactly 1 user succeeds.
- The remaining 9 competing users fail safely with "No slots available".
- ZERO double bookings occur in the database.
"""

import threading
import time
from database import get_db_connection, init_db
from booking_manager import booking_manager

NUM_CONCURRENT_USERS = 10
TARGET_SPACE_ID = "SP-101"

def setup_test_environment():
    """Prepares the database: leaves exactly ONE available slot in SP-101."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Reset all slots for SP-101 to Occupied except the very first one
    cursor.execute("UPDATE parking_slots SET status = 'Occupied' WHERE space_id = ?;", (TARGET_SPACE_ID,))
    
    # Pick the first slot of SP-101 and set it to Available
    cursor.execute("""
        SELECT slot_id, slot_number 
        FROM parking_slots 
        WHERE space_id = ? 
        ORDER BY slot_id ASC 
        LIMIT 1;
    """, (TARGET_SPACE_ID,))
    single_free_slot = cursor.fetchone()
    
    cursor.execute("UPDATE parking_slots SET status = 'Available' WHERE slot_id = ?;", (single_free_slot["slot_id"],))

    # 2. Register 10 test driver accounts if not present
    for i in range(1, NUM_CONCURRENT_USERS + 1):
        email = f"driver_{i}@smartpark.edu"
        cursor.execute("SELECT user_id FROM users WHERE email = ?;", (email,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES (?, ?, '9876543210', 'dummy_hash', 'driver');
            """, (f"Driver-{i}", email))
    conn.commit()

    cursor.execute("SELECT user_id, name, email FROM users WHERE email LIKE 'driver_%@smartpark.edu' ORDER BY user_id ASC LIMIT ?;", (NUM_CONCURRENT_USERS,))
    users = cursor.fetchall()
    conn.close()

    return single_free_slot, [dict(u) for u in users]

def submit_concurrent_booking(user, slot_info, barrier, results_list, lock):
    """Worker thread: waits at the barrier and fires request concurrently."""
    user_id = user["user_id"]
    driver_name = user["name"]
    plate = f"UK-07-TEST-{user_id:02d}"

    # Synchronize all 10 threads to release at the exact same instant
    barrier.wait()
    t_start = time.time()

    # Enqueue into OS FCFS Queue
    response = booking_manager.enqueue_booking(
        user_id=user_id,
        space_id=TARGET_SPACE_ID,
        driver_name=driver_name,
        plate=plate,
        vehicle_model="Test Car",
        booking_date="2026-10-15",
        start_time="10:00",
        end_time="11:00",
        hours=1,
        amount=30.0,
        payment_method="UPI"
    )

    with lock:
        results_list.append({
            "user_id": user_id,
            "name": driver_name,
            "plate": plate,
            "time": t_start,
            "response": response
        })

def run_concurrency_test():
    print("\n" + "=" * 75)
    print(" OPERATING SYSTEMS LAB: CONCURRENT BOOKING SAFETY & MUTEX TEST")
    print(f" Target Facility: {TARGET_SPACE_ID} | Competing Threads: {NUM_CONCURRENT_USERS}")
    print("=" * 75)

    free_slot, users = setup_test_environment()
    print(f"[Setup] Target Space '{TARGET_SPACE_ID}' configured with ONLY 1 free slot: {free_slot['slot_number']} (ID: {free_slot['slot_id']})")
    print(f"[Setup] Initialized {len(users)} distinct concurrent driver threads.")

    barrier = threading.Barrier(NUM_CONCURRENT_USERS)
    results = []
    lock = threading.Lock()
    threads = []

    print(f"[Test] Synchronizing {NUM_CONCURRENT_USERS} threads with threading.Barrier...")
    for u in users:
        t = threading.Thread(target=submit_concurrent_booking, args=(u, free_slot, barrier, results, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("[Test] All threads finished. Evaluating concurrency logs...\n")

    success_count = 0
    failure_count = 0
    winner = None

    print(f"{'Driver':<12} | {'Vehicle':<14} | {'Status':<10} | {'Server Response'}")
    print("-" * 75)
    for r in results:
        is_ok = r["response"]["success"]
        status = "SUCCESS" if is_ok else "FAILED"
        msg = r["response"].get("message", "")
        if is_ok:
            success_count += 1
            winner = r["name"]
            slot_booked = r["response"]["booking"]["slotNumber"]
            print(f"{r['name']:<12} | {r['plate']:<14} | {status:<10} | Allocated: {slot_booked}")
        else:
            failure_count += 1
            print(f"{r['name']:<12} | {r['plate']:<14} | {status:<10} | {msg}")

    print("-" * 75)
    print(f"Summary: Successful = {success_count} | Safely Rejected = {failure_count}")

    # Database Verification
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM parking_slots WHERE slot_id = ?;", (free_slot["slot_id"],))
    final_slot_status = cursor.fetchone()["status"]

    cursor.execute("""
        SELECT COUNT(*) AS active_count 
        FROM bookings 
        WHERE slot_id = ? AND status = 'Confirmed';
    """, (free_slot["slot_id"],))
    db_bookings_count = cursor.fetchone()["active_count"]
    conn.close()

    print("\n--- DBMS Verification ---")
    print(f"Physical Slot {free_slot['slot_number']} DB Status   : {final_slot_status}")
    print(f"Total Confirmed Records in Bookings Table : {db_bookings_count}")

    print("\n" + "=" * 75)
    if success_count == 1 and failure_count == (NUM_CONCURRENT_USERS - 1) and db_bookings_count == 1:
        print("[PASS] TEST PASSED: Concurrency safeguard verified!")
        print(f"       Slot awarded to: {winner}")
        print(f"       Zero double bookings. Exactly {failure_count} competing requests rejected cleanly.")
    else:
        print("[FAIL] TEST FAILED: Concurrency violation detected.")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    run_concurrency_test()
