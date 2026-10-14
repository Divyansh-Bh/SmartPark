"""
app.py - Flask Backend for Smart Parking Management System
==========================================================
Course: Operating Systems & DBMS Lab (3rd-Year B.Tech CSE)

Features:
- Full connectivity with GitHub Frontend (https://github.com/Divyansh-Bh/SmartPark)
- SQLite Database Management with ACID transactions
- OS FCFS Booking Request Queue & First Available Slot (FAS) Allocation
- Concurrency Control preventing double bookings
- Educational FCFS CPU Scheduling Simulation
"""

from flask import Flask, request, jsonify, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash
import time

from database import init_db, get_db_connection
from booking_manager import booking_manager
from os_concepts import simulate_fcfs, Process

app = Flask(__name__, template_folder="templates")
app.secret_key = "smartpark-3rd-year-cse-secure-key"

# Ensure tables and initial records exist
with app.app_context():
    init_db()

# -----------------------------------------------------------------------------
# Frontend Route
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """Serves the complete SmartPark frontend interface."""
    return render_template("frontend.html")

# -----------------------------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------------------------
@app.route("/api/register", methods=["POST"])
def register():
    """Registers a driver or provider with secure password hashing."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    phone = data.get("phone", "").strip()
    password = data.get("password", "")
    role = data.get("role", "driver").strip().lower()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400

    password_hash = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (name, email, phone, password_hash, role)
            VALUES (?, ?, ?, ?, ?);
        """, (name or email.split("@")[0], email, phone, password_hash, role))
        conn.commit()
        user_id = cursor.lastrowid
        return jsonify({
            "success": True,
            "message": "Account created successfully.",
            "user": {
                "id": f"AC-{user_id}",
                "userId": user_id,
                "name": name,
                "email": email,
                "role": role
            }
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "An account with this email already exists."}), 409
    finally:
        conn.close()

@app.route("/api/login", methods=["POST"])
def login():
    """Authenticates user and returns profile."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "driver").strip().lower()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? AND role = ?;", (email, role))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({"success": False, "message": f"No {role} account found with this email."}), 404

    if not check_password_hash(user["password_hash"], password):
        return jsonify({"success": False, "message": "Incorrect password."}), 401

    session["user_id"] = user["user_id"]
    session["role"] = user["role"]
    session["name"] = user["name"]

    return jsonify({
        "success": True,
        "message": "Signed in successfully.",
        "user": {
            "id": f"AC-{user['user_id']}",
            "userId": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "role": user["role"]
        }
    }), 200

# -----------------------------------------------------------------------------
# Parking Spaces & Slot Endpoints
# -----------------------------------------------------------------------------
@app.route("/api/spaces", methods=["GET"])
def get_spaces():
    """
    Returns all parking spaces with real-time slot availability
    computed directly from SQLite physical slot records.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            s.space_id,
            s.name,
            s.address,
            s.area,
            s.price,
            s.capacity,
            s.kind,
            s.hours,
            s.rating,
            s.owner_id,
            COUNT(p.slot_id) AS total_slots,
            SUM(CASE WHEN p.status = 'Available' THEN 1 ELSE 0 END) AS available_slots
        FROM spaces s
        LEFT JOIN parking_slots p ON s.space_id = p.space_id
        GROUP BY s.space_id
        ORDER BY s.space_id ASC;
    """)
    rows = cursor.fetchall()
    conn.close()

    spaces = []
    provider_spaces = []

    for r in rows:
        item = {
            "id": r["space_id"],
            "name": r["name"],
            "address": r["address"],
            "area": r["area"],
            "price": float(r["price"]),
            "capacity": int(r["capacity"]),
            "available": int(r["available_slots"] or 0),
            "kind": r["kind"],
            "hours": r["hours"],
            "rating": r["rating"] or "4.7",
            "ownerId": r["owner_id"]
        }
        if str(r["space_id"]).startswith("MY-") or r["owner_id"]:
            provider_spaces.append(item)
        else:
            spaces.append(item)

    return jsonify({
        "success": True,
        "spaces": spaces,
        "providerSpaces": provider_spaces
    }), 200

@app.route("/api/spaces", methods=["POST"])
def add_space():
    """Allows a provider to list a new parking space and creates its physical slots."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    address = data.get("address", "").strip()
    area = data.get("area", "").strip()
    price = float(data.get("price", 30))
    capacity = int(data.get("capacity", 5))
    kind = data.get("kind", "Covered")
    hours = data.get("hours", "Open 24 hours").strip()
    owner_id = session.get("user_id")

    if not name or not address or not area:
        return jsonify({"success": False, "message": "Missing required facility details."}), 400

    space_id = f"MY-{int(time.time()) % 1000000:06d}"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        cursor.execute("""
            INSERT INTO spaces (space_id, name, address, area, price, capacity, kind, hours, rating, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '4.8', ?);
        """, (space_id, name, address, area, price, capacity, kind, hours, owner_id))

        # Create physical slots
        slots = [(space_id, f"SLOT-{i:02d}", "Available") for i in range(1, capacity + 1)]
        cursor.executemany("INSERT INTO parking_slots (space_id, slot_number, status) VALUES (?, ?, ?);", slots)

        conn.commit()
        return jsonify({
            "success": True,
            "message": "Parking space listed successfully.",
            "space": {
                "id": space_id,
                "name": name,
                "address": address,
                "area": area,
                "price": price,
                "capacity": capacity,
                "available": capacity,
                "kind": kind,
                "hours": hours,
                "rating": "4.8"
            }
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/spaces/<space_id>/adjust", methods=["POST"])
def adjust_space_availability(space_id):
    """
    Allows provider to manually adjust availability (+1 or -1) atomically.
    """
    data = request.get_json() or {}
    delta = int(data.get("delta", 0))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        if delta < 0:
            # Mark one available slot as Occupied
            cursor.execute("""
                UPDATE parking_slots 
                SET status = 'Occupied' 
                WHERE slot_id = (
                    SELECT slot_id FROM parking_slots 
                    WHERE space_id = ? AND status = 'Available' 
                    LIMIT 1
                );
            """, (space_id,))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"success": False, "message": "No free slots left to mark occupied."}), 400
        elif delta > 0:
            # Mark one occupied slot as Available
            cursor.execute("""
                UPDATE parking_slots 
                SET status = 'Available' 
                WHERE slot_id = (
                    SELECT slot_id FROM parking_slots 
                    WHERE space_id = ? AND status = 'Occupied' 
                    LIMIT 1
                );
            """, (space_id,))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"success": False, "message": "All slots are already available."}), 400

        conn.commit()
        return jsonify({"success": True, "message": "Availability updated successfully."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# Vehicles Endpoints
# -----------------------------------------------------------------------------
@app.route("/api/vehicles", methods=["GET"])
def get_vehicles():
    """Retrieves vehicles for current driver."""
    user_id = session.get("user_id") or request.args.get("user_id")
    conn = get_db_connection()
    cursor = conn.cursor()

    if user_id:
        cursor.execute("SELECT vehicle_id, user_id, plate, model, type FROM vehicles WHERE user_id = ?;", (user_id,))
    else:
        cursor.execute("SELECT vehicle_id, user_id, plate, model, type FROM vehicles LIMIT 20;")

    rows = cursor.fetchall()
    conn.close()

    vehicles = [
        {
            "id": f"VH-{r['vehicle_id']}",
            "dbId": r["vehicle_id"],
            "plate": r["plate"],
            "model": r["model"],
            "type": r["type"]
        }
        for r in rows
    ]

    # If new user has no vehicles yet, provide default fallback
    if not vehicles:
        vehicles = [
            {"id": "VH-01", "plate": "KA 03 MN 4821", "model": "Hyundai i20", "type": "Car"}
        ]

    return jsonify({"success": True, "vehicles": vehicles}), 200

@app.route("/api/vehicles", methods=["POST"])
def add_vehicle():
    """Adds a new registered vehicle for the user."""
    data = request.get_json() or {}
    plate = data.get("plate", "").strip().upper()
    model = data.get("model", "").strip()
    v_type = data.get("type", "Car").strip()
    user_id = session.get("user_id") or data.get("user_id", 1)

    if not plate or not model:
        return jsonify({"success": False, "message": "Registration plate and model are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO vehicles (user_id, plate, model, type)
            VALUES (?, ?, ?, ?);
        """, (user_id, plate, model, v_type))
        conn.commit()
        v_id = cursor.lastrowid
        return jsonify({
            "success": True,
            "message": "Vehicle registered successfully.",
            "vehicle": {
                "id": f"VH-{v_id}",
                "dbId": v_id,
                "plate": plate,
                "model": model,
                "type": v_type
            }
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/vehicles/<v_id>", methods=["DELETE"])
def remove_vehicle(v_id):
    """Deletes a vehicle."""
    raw_id = v_id.replace("VH-", "")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vehicles WHERE vehicle_id = ?;", (raw_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Vehicle removed."}), 200

# -----------------------------------------------------------------------------
# Booking Route (OS FCFS Queue + FAS Allocation)
# -----------------------------------------------------------------------------
@app.route("/api/book", methods=["POST"])
def book_parking_spot():
    """
    Submits a booking request into the OS FCFS Queue.
    Allocates physical parking slot using the First Available Slot (FAS) algorithm.
    """
    data = request.get_json() or {}
    user_id = session.get("user_id") or data.get("user_id", 1)
    space_id = data.get("space_id") or data.get("spaceId")
    driver_name = data.get("driver_name") or data.get("driverName") or session.get("name", "Student Driver")
    plate = data.get("plate", "").strip().upper()
    vehicle_model = data.get("vehicle_model") or data.get("vehicleModel", "")
    booking_date = data.get("date") or time.strftime("%Y-%m-%d")
    start_time = data.get("start", "10:00")
    end_time = data.get("end", "11:00")
    hours = int(data.get("hours", 1))
    amount = float(data.get("amount", 30.0))
    payment_method = data.get("method") or data.get("paymentMethod", "UPI")

    if not space_id or not plate:
        return jsonify({"success": False, "message": "Missing space_id or vehicle plate."}), 400

    # Submit to thread-safe FCFS queue
    result = booking_manager.enqueue_booking(
        user_id=user_id,
        space_id=space_id,
        driver_name=driver_name,
        plate=plate,
        vehicle_model=vehicle_model,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        hours=hours,
        amount=amount,
        payment_method=payment_method
    )

    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

# -----------------------------------------------------------------------------
# Bookings Retrieval & Cancellation
# -----------------------------------------------------------------------------
@app.route("/api/bookings", methods=["GET"])
def get_bookings():
    """Retrieves all confirmed and past bookings from SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            b.booking_id,
            b.user_id,
            b.space_id,
            b.slot_number,
            b.driver_name,
            b.plate,
            b.vehicle_model,
            b.booking_date,
            b.start_time,
            b.end_time,
            b.hours,
            b.amount,
            b.payment_method,
            b.status,
            b.created_at,
            s.name AS space_name,
            s.address
        FROM bookings b
        JOIN spaces s ON b.space_id = s.space_id
        ORDER BY b.created_at DESC;
    """)
    rows = cursor.fetchall()
    conn.close()

    bookings = []
    for r in rows:
        bookings.append({
            "id": r["booking_id"],
            "spaceId": r["space_id"],
            "spaceName": r["space_name"],
            "address": r["address"],
            "slotNumber": r["slot_number"],
            "driverName": r["driver_name"],
            "plate": r["plate"],
            "vehicleModel": r["vehicle_model"],
            "date": r["booking_date"],
            "start": r["start_time"],
            "end": r["end_time"],
            "hours": r["hours"],
            "amount": r["amount"],
            "method": r["payment_method"],
            "status": r["status"],
            "created": r["created_at"]
        })

    return jsonify({"success": True, "bookings": bookings}), 200

@app.route("/api/cancel/<booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    """
    Cancels a booking and resets its physical slot status to 'Available' atomically.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        cursor.execute("SELECT slot_id, status FROM bookings WHERE booking_id = ?;", (booking_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "message": "Booking not found."}), 404

        slot_id = row["slot_id"]

        # 1. Update booking
        cursor.execute("UPDATE bookings SET status = 'Cancelled' WHERE booking_id = ?;", (booking_id,))

        # 2. Release physical slot
        cursor.execute("UPDATE parking_slots SET status = 'Available' WHERE slot_id = ?;", (slot_id,))

        # 3. Update exit log
        cursor.execute("UPDATE entry_exit_logs SET exit_time = CURRENT_TIMESTAMP WHERE booking_id = ?;", (booking_id,))

        conn.commit()
        return jsonify({"success": True, "message": f"Booking {booking_id} cancelled and slot released."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# OS Educational Simulation
# -----------------------------------------------------------------------------
@app.route("/api/simulate-fcfs", methods=["GET"])
def simulate_cpu():
    """FCFS CPU process scheduling simulation endpoint."""
    sample = [
        Process(pid="P1", burst_time=5, arrival_time=0),
        Process(pid="P2", burst_time=3, arrival_time=0),
        Process(pid="P3", burst_time=2, arrival_time=0),
        Process(pid="P4", burst_time=4, arrival_time=0)
    ]
    res = simulate_fcfs(sample)
    formatted = [
        {
            "pid": p.pid,
            "arrival_time": p.arrival_time,
            "burst_time": p.burst_time,
            "completion_time": p.completion_time,
            "turnaround_time": p.turnaround_time,
            "waiting_time": p.waiting_time
        }
        for p in res["processes"]
    ]
    return jsonify({
        "success": True,
        "processes": formatted,
        "avg_waiting_time": res["avg_waiting_time"],
        "avg_turnaround_time": res["avg_turnaround_time"]
    }), 200

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print(" SmartPark: OS & DBMS Integrated Backend Server")
    print(" Running on http://127.0.0.1:5000")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
