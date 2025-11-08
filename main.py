"""
FastAPI Backend for Calendar Sync System
Handles:
- Email webhook for booking confirmations
- Manual blocking via web interface
- Task queueing and status tracking
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
from pathlib import Path
import json

from email_parser import EmailParser, Booking
from platform_blocker import PlatformBlocker
from database import db


app = FastAPI(title="Calendar Sync API")

# Initialize database
db.init_db()


# Pydantic models
class ManualBlockRequest(BaseModel):
    checkin: datetime
    checkout: datetime
    property_id: Optional[str] = None
    block_airbnb: bool = True
    block_booking: bool = True


class EmailWebhookRequest(BaseModel):
    from_email: str
    subject: str
    body_text: str
    body_html: Optional[str] = None


class BlockingStatus(BaseModel):
    booking_id: int
    platform: str
    checkin: str
    checkout: str
    blocked_on_other: bool
    error: Optional[str] = None


# Background task processor
async def process_blocking(booking_id: int, source_platform: str,
                          checkin: datetime, checkout: datetime,
                          property_id: Optional[str] = None):
    """Background task to block dates on the other platform"""

    # Determine target platform
    target_platform = 'booking' if source_platform == 'airbnb' else 'airbnb'

    # Create task record
    with db.get_connection() as conn:
        c = db.get_cursor(conn)
        c.execute('''
            INSERT INTO block_tasks (booking_id, target_platform, status)
            VALUES (%s, %s, 'processing') RETURNING id
        ''' if db.use_postgres else '''
            INSERT INTO block_tasks (booking_id, target_platform, status)
            VALUES (?, ?, 'processing')
        ''', (booking_id, target_platform))

        if db.use_postgres:
            task_id = c.fetchone()['id']
        else:
            task_id = c.lastrowid
        conn.commit()

    try:
        # Execute blocking
        blocker = PlatformBlocker()
        success = await blocker.block_dates(target_platform, checkin, checkout, property_id)

        # Update database
        with db.get_connection() as conn:
            c = db.get_cursor(conn)

            if success:
                c.execute('''
                    UPDATE block_tasks
                    SET status='completed', completed_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                ''' if db.use_postgres else '''
                    UPDATE block_tasks
                    SET status='completed', completed_at=CURRENT_TIMESTAMP
                    WHERE id=?
                ''', (task_id,))

                c.execute('''
                    UPDATE bookings
                    SET blocked_on_other_platform=%s
                    WHERE id=%s
                ''' if db.use_postgres else '''
                    UPDATE bookings
                    SET blocked_on_other_platform=1
                    WHERE id=?
                ''', (True, booking_id) if db.use_postgres else (booking_id,))

                print(f"✓ Successfully blocked {target_platform} for booking {booking_id}")
            else:
                c.execute('''
                    UPDATE block_tasks
                    SET status='failed', error_message='Blocking failed'
                    WHERE id=%s
                ''' if db.use_postgres else '''
                    UPDATE block_tasks
                    SET status='failed', error_message='Blocking failed'
                    WHERE id=?
                ''', (task_id,))

                print(f"✗ Failed to block {target_platform} for booking {booking_id}")

            conn.commit()

    except Exception as e:
        # Log error
        with db.get_connection() as conn:
            c = db.get_cursor(conn)
            c.execute('''
                UPDATE block_tasks
                SET status='failed', error_message=%s
                WHERE id=%s
            ''' if db.use_postgres else '''
                UPDATE block_tasks
                SET status='failed', error_message=?
                WHERE id=?
            ''', (str(e), task_id))
            conn.commit()

        print(f"✗ Error blocking {target_platform}: {e}")


# API Endpoints

@app.post("/webhook/email")
async def email_webhook(request: EmailWebhookRequest, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for incoming booking confirmation emails
    Mailgun, SendGrid, or custom email forwarder hits this endpoint
    """

    parser = EmailParser()

    # Parse the email
    booking = parser.parse_email(request.body_text, request.subject)

    if not booking:
        raise HTTPException(status_code=400, detail="Could not parse booking from email")

    # Store in database
    with db.get_connection() as conn:
        c = db.get_cursor(conn)
        c.execute('''
            INSERT INTO bookings
            (platform, checkin, checkout, property_id, guest_name, confirmation_code)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''' if db.use_postgres else '''
            INSERT INTO bookings
            (platform, checkin, checkout, property_id, guest_name, confirmation_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            booking.platform,
            booking.checkin.isoformat(),
            booking.checkout.isoformat(),
            booking.property_id,
            booking.guest_name,
            booking.confirmation_code
        ))

        if db.use_postgres:
            booking_id = c.fetchone()['id']
        else:
            booking_id = c.lastrowid
        conn.commit()

    # Queue blocking task
    background_tasks.add_task(
        process_blocking,
        booking_id,
        booking.platform,
        booking.checkin,
        booking.checkout,
        booking.property_id
    )

    return {
        "status": "success",
        "booking_id": booking_id,
        "message": f"Booking detected on {booking.platform}, blocking on other platform..."
    }


@app.post("/api/block")
async def manual_block(request: ManualBlockRequest, background_tasks: BackgroundTasks):
    """
    Manual blocking endpoint for walk-ins
    Blocks dates on both platforms
    """

    tasks = []

    if request.block_airbnb:
        # Create dummy booking for Airbnb
        with db.get_connection() as conn:
            c = db.get_cursor(conn)
            c.execute('''
                INSERT INTO bookings
                (platform, checkin, checkout, property_id, guest_name, confirmation_code)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            ''' if db.use_postgres else '''
                INSERT INTO bookings
                (platform, checkin, checkout, property_id, guest_name, confirmation_code)
                VALUES (?, ?, ?, ?, 'Walk-in', 'MANUAL')
            ''', (
                'manual',
                request.checkin.isoformat(),
                request.checkout.isoformat(),
                request.property_id,
                'Walk-in',
                'MANUAL'
            ))

            if db.use_postgres:
                booking_id = c.fetchone()['id']
            else:
                booking_id = c.lastrowid
            conn.commit()

        background_tasks.add_task(
            process_blocking,
            booking_id,
            'manual',  # Will trigger blocking on both
            request.checkin,
            request.checkout,
            request.property_id
        )

        # Queue Airbnb blocking
        blocker = PlatformBlocker()
        background_tasks.add_task(
            blocker.block_dates,
            'airbnb',
            request.checkin,
            request.checkout,
            request.property_id
        )
        tasks.append('airbnb')

    if request.block_booking:
        # Queue Booking.com blocking
        blocker = PlatformBlocker()
        background_tasks.add_task(
            blocker.block_dates,
            'booking',
            request.checkin,
            request.checkout,
            request.property_id
        )
        tasks.append('booking')

    return {
        "status": "success",
        "message": f"Blocking dates on: {', '.join(tasks)}",
        "checkin": request.checkin.isoformat(),
        "checkout": request.checkout.isoformat()
    }


@app.get("/api/bookings")
async def list_bookings(limit: int = 50, offset: int = 0):
    """List recent bookings and their blocking status"""

    with db.get_connection() as conn:
        c = db.get_cursor(conn)
        c.execute('''
            SELECT
                id, platform, checkin, checkout,
                property_id, guest_name, confirmation_code,
                blocked_on_other_platform, error_message, created_at
            FROM bookings
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        ''' if db.use_postgres else '''
            SELECT
                id, platform, checkin, checkout,
                property_id, guest_name, confirmation_code,
                blocked_on_other_platform, error_message, created_at
            FROM bookings
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))

        bookings = []
        for row in c.fetchall():
            if db.use_postgres:
                bookings.append({
                    'id': row['id'],
                    'platform': row['platform'],
                    'checkin': row['checkin'],
                    'checkout': row['checkout'],
                    'property_id': row['property_id'],
                    'guest_name': row['guest_name'],
                    'confirmation_code': row['confirmation_code'],
                    'blocked_on_other': bool(row['blocked_on_other_platform']),
                    'error': row['error_message'],
                    'created_at': str(row['created_at'])
                })
            else:
                bookings.append({
                    'id': row[0],
                    'platform': row[1],
                    'checkin': row[2],
                    'checkout': row[3],
                    'property_id': row[4],
                    'guest_name': row[5],
                    'confirmation_code': row[6],
                    'blocked_on_other': bool(row[7]),
                    'error': row[8],
                    'created_at': row[9]
                })

    return {"bookings": bookings}


@app.get("/api/status/{booking_id}")
async def booking_status(booking_id: int):
    """Check blocking status for a specific booking"""

    with db.get_connection() as conn:
        c = db.get_cursor(conn)

        # Get booking
        c.execute('''
            SELECT * FROM bookings WHERE id=%s
        ''' if db.use_postgres else '''
            SELECT * FROM bookings WHERE id=?
        ''', (booking_id,))
        booking_row = c.fetchone()

        if not booking_row:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Get tasks
        c.execute('''
            SELECT * FROM block_tasks WHERE booking_id=%s
        ''' if db.use_postgres else '''
            SELECT * FROM block_tasks WHERE booking_id=?
        ''', (booking_id,))
        task_rows = c.fetchall()

    if db.use_postgres:
        return {
            'booking_id': booking_id,
            'platform': booking_row['platform'],
            'checkin': booking_row['checkin'],
            'checkout': booking_row['checkout'],
            'blocked_on_other': bool(booking_row['blocked_on_other_platform']),
            'tasks': [
                {
                    'id': row['id'],
                    'target_platform': row['target_platform'],
                    'status': row['status'],
                    'created_at': str(row['created_at']),
                    'completed_at': str(row['completed_at']) if row['completed_at'] else None,
                    'error': row['error_message']
                }
                for row in task_rows
            ]
        }
    else:
        return {
            'booking_id': booking_id,
            'platform': booking_row[1],
            'checkin': booking_row[2],
            'checkout': booking_row[3],
            'blocked_on_other': bool(booking_row[7]),
            'tasks': [
                {
                    'id': row[0],
                    'target_platform': row[2],
                    'status': row[3],
                    'created_at': row[4],
                    'completed_at': row[5],
                    'error': row[6]
                }
                for row in task_rows
            ]
        }


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the walk-in blocking dashboard"""
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Calendar Sync - Walk-in Blocker</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100">
        <div class="container mx-auto px-4 py-8 max-w-2xl">
            <h1 class="text-3xl font-bold mb-8 text-gray-800">📅 Calendar Sync</h1>
            
            <!-- Walk-in Blocking Form -->
            <div class="bg-white rounded-lg shadow-md p-6 mb-8">
                <h2 class="text-xl font-semibold mb-4">Block Walk-in Dates</h2>
                
                <form id="blockForm" class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">
                            Check-in Date
                        </label>
                        <input type="date" id="checkin" required
                               class="w-full px-3 py-2 border border-gray-300 rounded-md">
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">
                            Check-out Date
                        </label>
                        <input type="date" id="checkout" required
                               class="w-full px-3 py-2 border border-gray-300 rounded-md">
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">
                            Property ID (Optional)
                        </label>
                        <input type="text" id="property_id" placeholder="Leave blank for default"
                               class="w-full px-3 py-2 border border-gray-300 rounded-md">
                    </div>
                    
                    <div class="flex gap-4">
                        <label class="flex items-center">
                            <input type="checkbox" id="block_airbnb" checked
                                   class="mr-2 h-4 w-4">
                            <span class="text-sm">Block on Airbnb</span>
                        </label>
                        
                        <label class="flex items-center">
                            <input type="checkbox" id="block_booking" checked
                                   class="mr-2 h-4 w-4">
                            <span class="text-sm">Block on Booking.com</span>
                        </label>
                    </div>
                    
                    <button type="submit"
                            class="w-full bg-blue-600 text-white py-3 px-4 rounded-md hover:bg-blue-700 font-medium">
                        🔒 Block Dates
                    </button>
                </form>
                
                <div id="status" class="mt-4 hidden">
                    <div class="p-4 rounded-md" id="statusBox">
                        <p id="statusMessage"></p>
                    </div>
                </div>
            </div>
            
            <!-- Recent Bookings -->
            <div class="bg-white rounded-lg shadow-md p-6">
                <h2 class="text-xl font-semibold mb-4">Recent Bookings</h2>
                <div id="bookingsList" class="space-y-3">
                    <p class="text-gray-500 text-sm">Loading...</p>
                </div>
            </div>
        </div>
        
        <script>
            // Handle form submission
            document.getElementById('blockForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const checkin = document.getElementById('checkin').value;
                const checkout = document.getElementById('checkout').value;
                const property_id = document.getElementById('property_id').value;
                const block_airbnb = document.getElementById('block_airbnb').checked;
                const block_booking = document.getElementById('block_booking').checked;
                
                const statusBox = document.getElementById('statusBox');
                const statusMessage = document.getElementById('statusMessage');
                const status = document.getElementById('status');
                
                try {
                    const response = await fetch('/api/block', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            checkin: checkin + 'T00:00:00',
                            checkout: checkout + 'T00:00:00',
                            property_id: property_id || null,
                            block_airbnb,
                            block_booking
                        })
                    });
                    
                    const data = await response.json();
                    
                    status.classList.remove('hidden');
                    statusBox.className = 'p-4 rounded-md bg-green-100 border border-green-300';
                    statusMessage.textContent = '✓ ' + data.message;
                    
                    // Reload bookings list
                    loadBookings();
                    
                    // Clear form
                    e.target.reset();
                    
                } catch (error) {
                    status.classList.remove('hidden');
                    statusBox.className = 'p-4 rounded-md bg-red-100 border border-red-300';
                    statusMessage.textContent = '✗ Error: ' + error.message;
                }
            });
            
            // Load recent bookings
            async function loadBookings() {
                try {
                    const response = await fetch('/api/bookings?limit=10');
                    const data = await response.json();
                    
                    const list = document.getElementById('bookingsList');
                    
                    if (data.bookings.length === 0) {
                        list.innerHTML = '<p class="text-gray-500 text-sm">No bookings yet</p>';
                        return;
                    }
                    
                    list.innerHTML = data.bookings.map(b => `
                        <div class="border-l-4 ${b.blocked_on_other ? 'border-green-500' : 'border-yellow-500'} pl-4 py-2">
                            <div class="flex justify-between items-start">
                                <div>
                                    <span class="font-medium">${b.platform}</span>
                                    ${b.guest_name ? `<span class="text-gray-600"> - ${b.guest_name}</span>` : ''}
                                </div>
                                <span class="text-xs px-2 py-1 rounded ${b.blocked_on_other ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}">
                                    ${b.blocked_on_other ? '✓ Synced' : '⏳ Pending'}
                                </span>
                            </div>
                            <div class="text-sm text-gray-600 mt-1">
                                ${new Date(b.checkin).toLocaleDateString()} - ${new Date(b.checkout).toLocaleDateString()}
                            </div>
                        </div>
                    `).join('');
                    
                } catch (error) {
                    console.error('Error loading bookings:', error);
                }
            }
            
            // Load bookings on page load
            loadBookings();
            
            // Refresh every 10 seconds
            setInterval(loadBookings, 10000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
