"""
booking_manager.py - OS Scheduling & Resource Allocation Module
================================================================
Implements the core Operating Systems concepts for SmartPark:
1. FCFS Booking Request Queue (Non-preemptive process scheduling)
2. First Available Slot (FAS) Allocation (First-Fit resource allocation)
3. Concurrency Control & ACID Database Transactions
"""

import queue
import threading
import time
from datetime import datetime
from database import get_db_connection

class BookingRequest:
    """
    Represents an incoming booking request submitted to the FCFS Ready Queue.
    """
    def __init__(self, user_id, space_id, driver_name, plate, vehicle_model,
                 booking_date, start_time, end_time, hours, amount, payment_method):
        self.request_id = f"REQ-{int(time.time() * 1000)}"
        self.user_id = user_id
        self.space_id = space_id
        self.driver_name = driver_name
        self.plate = plate
        self.vehicle_model = vehicle_model
        self.booking_date = booking_date
        self.start_time = start_time
        self.end_time = end_time
        self.hours = hours
        self.amount = amount
        self.payment_method = payment_method
        self.arrival_time = datetime.now()

        # Threading event to signal completion to waiting HTTP worker
        self.completed_event = threading.Event()
        self.response = None

class BookingManager:
    """
    Manages the thread-safe FCFS Queue and executes First Available Slot (FAS) allocation.
    """
    def __init__(self):
        self.request_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        print("[OS Scheduler] FCFS Queue initialized. Worker dispatcher started.")

    def enqueue_booking(self, user_id, space_id, driver_name, plate, vehicle_model,
                        booking_date, start_time, end_time, hours, amount, payment_method, timeout=6.0):
        """
        Enqueues an incoming booking request into the FCFS queue and blocks
        until the worker thread processes it or timeout expires.
        """
        req = BookingRequest(
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
        self.request_queue.put(req)

        # Wait for the worker thread to service the request
        finished = req.completed_event.wait(timeout=timeout)
        if not finished:
            return {
                "success": False,
                "message": "Booking request timed out in the FCFS scheduling queue.",
                "request_id": req.request_id
            }
        return req.response

    def _process_queue(self):
        """
        Background worker thread: processes requests strictly in First-Come, First-Served order.
        """
        while True:
            request = self.request_queue.get()
            try:
                result = self._execute_fas_allocation(request)
                request.response = result
            except Exception as e:
                request.response = {
                    "success": False,
                    "message": f"Scheduling error: {str(e)}",
                    "request_id": request.request_id
                }
            finally:
                request.completed_event.set()
                self.request_queue.task_done()

    def _execute_fas_allocation(self, req):
        """
        Executes First Available Slot (FAS) allocation algorithm
        backed by atomic SQLite transaction and conditional update.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            conn.execute("BEGIN IMMEDIATE TRANSACTION;")

            # 1. Fetch space info
            cursor.execute("SELECT space_id, name, address, price FROM spaces WHERE space_id = ?;", (req.space_id,))
            space = cursor.fetchone()
            if not space:
                conn.rollback()
                return {"success": False, "message": "Selected parking facility does not exist."}

            # 2. OS FAS Algorithm: Scan physical slots in ascending order
            cursor.execute("""
                SELECT slot_id, slot_number 
                FROM parking_slots 
                WHERE space_id = ? AND status = 'Available' 
                ORDER BY slot_id ASC 
                LIMIT 1;
            """, (req.space_id,))
            target_slot = cursor.fetchone()

            if not target_slot:
                conn.rollback()
                return {
                    "success": False,
                    "message": f"Sorry, '{space['name']}' has no free slots available (Capacity Full).",
                    "request_id": req.request_id
                }

            target_slot_id = target_slot["slot_id"]
            target_slot_number = target_slot["slot_number"]

            # 3. Critical Section: Conditional Atomic Update
            cursor.execute("""
                UPDATE parking_slots
                SET status = 'Occupied'
                WHERE slot_id = ? AND status = 'Available';
            """, (target_slot_id,))

            if cursor.rowcount == 0:
                conn.rollback()
                return {
                    "success": False,
                    "message": "Race condition detected: The slot was claimed by a concurrent transaction.",
                    "request_id": req.request_id
                }

            # 4. Generate unique Booking ID (e.g. BK-xxxxxxx)
            booking_id = f"BK-{int(time.time() * 1000) % 10000000:07d}"

            cursor.execute("""
                INSERT INTO bookings (
                    booking_id, user_id, space_id, slot_id, slot_number,
                    driver_name, plate, vehicle_model, booking_date,
                    start_time, end_time, hours, amount, payment_method, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Confirmed');
            """, (
                booking_id, req.user_id, req.space_id, target_slot_id, target_slot_number,
                req.driver_name, req.plate, req.vehicle_model, req.booking_date,
                req.start_time, req.end_time, req.hours, req.amount, req.payment_method
            ))

            # 5. Insert Entry Log
            cursor.execute("INSERT INTO entry_exit_logs (booking_id) VALUES (?);", (booking_id,))

            # 6. Commit transaction atomically
            conn.commit()

            return {
                "success": True,
                "message": f"Slot '{target_slot_number}' successfully allocated via FAS.",
                "booking": {
                    "id": booking_id,
                    "spaceId": req.space_id,
                    "spaceName": space["name"],
                    "address": space["address"],
                    "slotNumber": target_slot_number,
                    "driverName": req.driver_name,
                    "plate": req.plate,
                    "vehicleModel": req.vehicle_model,
                    "date": req.booking_date,
                    "start": req.start_time,
                    "end": req.end_time,
                    "hours": req.hours,
                    "amount": req.amount,
                    "method": req.payment_method,
                    "status": "Confirmed",
                    "requestId": req.request_id
                }
            }

        except Exception as e:
            conn.rollback()
            return {
                "success": False,
                "message": f"Transaction rolled back due to error: {str(e)}",
                "request_id": req.request_id
            }
        finally:
            conn.close()

# Singleton manager
booking_manager = BookingManager()
