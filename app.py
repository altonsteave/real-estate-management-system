from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
import sqlite3
import os
import json
import hashlib
import requests
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'elite_estates_secret_key_2026'

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'elite_estates.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB total

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── DATABASE HELPERS ────────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_primary_image(property_id):
    """Get the primary image filename for a property."""
    db = get_db()
    img = db.execute(
        "SELECT filename FROM property_images WHERE property_id=? ORDER BY is_primary DESC, id ASC LIMIT 1",
        (property_id,)
    ).fetchone()
    return img['filename'] if img else None

def get_property_images(property_id):
    """Get all images for a property."""
    db = get_db()
    return db.execute(
        "SELECT * FROM property_images WHERE property_id=? ORDER BY is_primary DESC, id ASC",
        (property_id,)
    ).fetchall()

def get_image_count(property_id):
    """Get the count of images for a property."""
    db = get_db()
    return db.execute("SELECT COUNT(*) as c FROM property_images WHERE property_id=?", (property_id,)).fetchone()['c']

def delete_property_files(property_id):
    """Delete all image files associated with a property from the filesystem."""
    db = get_db()
    images = db.execute("SELECT filename FROM property_images WHERE property_id=?", (property_id,)).fetchall()
    for img in images:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], img['filename'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file {filepath}: {e}")

# ─── LOCALITY SCORE ──────────────────────────────────────────────────────────
def calculate_locality_score(lat, lng):
    """
    Query OpenStreetMap Overpass API to count nearby facilities within 2km.
    Returns (score_out_of_5, details_dict).
    """
    radius = 2000  # 2km as requested

    # Use nwr but focus on distinct features to avoid over-counting
    overpass_query = f"""
    [out:json][timeout:60];
    (
      nwr["amenity"~"hospital|clinic"](around:{radius},{lat},{lng});
      nwr["shop"~"supermarket|mall"](around:{radius},{lat},{lng});
      node["highway"="bus_stop"](around:{radius},{lat},{lng});
      nwr["railway"~"station|subway_entrance"](around:{radius},{lat},{lng});
      nwr["amenity"~"school|university|college"](around:{radius},{lat},{lng});
    );
    out tags;
    """

    details = {
        'hospital': 0,
        'supermarket': 0,
        'bus_stop': 0,
        'metro_station': 0,
        'school': 0,
    }

    try:
        headers = {'User-Agent': 'EliteEstates/1.0 (RealEstateApp; contact: admin@eliteestates.com)'}
        resp = requests.post(
            'https://overpass-api.de/api/interpreter',
            data={'data': overpass_query},
            timeout=40,
            headers=headers
        )
        if resp.status_code == 200:
            data = resp.json()
            elements = data.get('elements', [])
            
            # Use sets to avoid double counting the same name/location
            found_names = {
                'hospital': set(),
                'supermarket': set(),
                'bus_stop': set(),
                'metro_station': set(),
                'school': set()
            }

            for el in elements:
                tags = el.get('tags', {})
                name = tags.get('name', f"unnamed_{el.get('id')}")
                amenity = tags.get('amenity', '').lower()
                shop = tags.get('shop', '').lower()
                highway = tags.get('highway', '').lower()
                railway = tags.get('railway', '').lower()

                if any(x in amenity for x in ['hospital', 'clinic']):
                    found_names['hospital'].add(name)
                elif any(x in shop for x in ['supermarket', 'mall']):
                    found_names['supermarket'].add(name)
                elif any(x in amenity for x in ['school', 'university', 'college']):
                    found_names['school'].add(name)
                elif any(x in railway for x in ['station', 'subway_entrance']):
                    found_names['metro_station'].add(name)
                elif highway == 'bus_stop':
                    found_names['bus_stop'].add(name)

            # Update details with counts from sets
            for key in details:
                details[key] = len(found_names[key])

    except Exception as e:
        print(f"Overpass API error: {e}")

    # Diversity score (max 5)
    score = sum(1 for v in details.values() if v > 0)
    return score, details

# ─── HOME ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    featured = db.execute(
        "SELECT * FROM properties WHERE status='approved' ORDER BY created_at DESC LIMIT 6"
    ).fetchall()
    # Attach primary image to each property
    featured_list = []
    for p in featured:
        p_dict = dict(p)
        p_dict['image'] = get_primary_image(p['id'])
        p_dict['image_count'] = get_image_count(p['id'])
        featured_list.append(p_dict)
    return render_template('index.html', featured=featured_list)

# ─── AUTH ────────────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = hash_password(request.form['password'])
        role = request.form.get('role', 'user')

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))

        db.execute(
            "INSERT INTO users (name, email, phone, password, role) VALUES (?,?,?,?,?)",
            (name, email, phone, password, role)
        )
        db.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hash_password(request.form['password'])
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password)).fetchone()
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ─── USER DASHBOARD ──────────────────────────────────────────────────────────
@app.route('/dashboard')
def user_dashboard():
    if 'user_id' not in session or session['user_role'] != 'user':
        return redirect(url_for('login'))
    db = get_db()
    my_props = db.execute(
        "SELECT * FROM properties WHERE user_id=? ORDER BY created_at DESC", (session['user_id'],)
    ).fetchall()
    # Attach primary images
    props_list = []
    for p in my_props:
        p_dict = dict(p)
        p_dict['image'] = get_primary_image(p['id'])
        p_dict['image_count'] = get_image_count(p['id'])
        props_list.append(p_dict)

    my_bookings = db.execute(
        """SELECT b.*, p.title, p.price FROM bookings b 
           JOIN properties p ON b.property_id=p.id 
           WHERE b.user_id=? ORDER BY b.created_at DESC""",
        (session['user_id'],)
    ).fetchall()

    # Won Auctions that need appointment booking
    won_auctions = db.execute(
        """SELECT p.*, (SELECT MAX(amount) FROM bids WHERE property_id=p.id) as final_price
           FROM properties p 
           WHERE p.type='auction' AND p.status='approved' 
           AND p.auction_end < datetime('now')
           AND (SELECT user_id FROM bids WHERE property_id=p.id ORDER BY amount DESC LIMIT 1) = ?
           AND NOT EXISTS (SELECT 1 FROM bookings WHERE property_id=p.id AND user_id=?)""",
        (session['user_id'], session['user_id'])
    ).fetchall()
    
    won_list = []
    for w in won_auctions:
        w_dict = dict(w)
        w_dict['image'] = get_primary_image(w['id'])
        won_list.append(w_dict)

    return render_template('user_dashboard.html', properties=props_list, bookings=my_bookings, won_auctions=won_list, now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

# ─── PROPERTIES ──────────────────────────────────────────────────────────────
@app.route('/properties')
def properties():
    prop_type = request.args.get('type', '')
    search = request.args.get('search', '')
    db = get_db()
    query = """SELECT p.*, u.name as owner_name FROM properties p 
               JOIN users u ON p.user_id=u.id WHERE p.status='approved'"""
    params = []
    if prop_type:
        query += " AND p.type=?"
        params.append(prop_type)
    if search:
        query += " AND (p.title LIKE ? OR p.location LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    query += " ORDER BY p.created_at DESC"
    props = db.execute(query, params).fetchall()
    # Attach primary images
    props_list = []
    for p in props:
        p_dict = dict(p)
        p_dict['image'] = get_primary_image(p['id'])
        p_dict['image_count'] = get_image_count(p['id'])
        props_list.append(p_dict)
    return render_template('properties.html', properties=props_list, prop_type=prop_type, search=search)

@app.route('/property/<int:pid>')
def property_detail(pid):
    db = get_db()
    prop = db.execute(
        """SELECT p.*, u.name as owner_name, u.phone as owner_phone 
           FROM properties p JOIN users u ON p.user_id=u.id WHERE p.id=?""", (pid,)
    ).fetchone()
    if not prop:
        flash('Property not found.', 'error')
        return redirect(url_for('properties'))
    prop_dict = dict(prop)
    prop_dict['images'] = get_property_images(pid)
    prop_dict['image'] = get_primary_image(pid)
    
    # Identify if current user is the winner of this auction
    is_winner = False
    if session.get('user_id') and prop_dict['type'] == 'auction':
        winner = db.execute(
            "SELECT user_id FROM bids WHERE property_id=? ORDER BY amount DESC LIMIT 1", (pid,)
        ).fetchone()
        if winner and winner['user_id'] == session['user_id']:
            is_winner = True
    
    # Parse locality details
    if prop_dict.get('locality_details'):
        try:
            prop_dict['locality_details'] = json.loads(prop_dict['locality_details'])
        except (json.JSONDecodeError, TypeError):
            prop_dict['locality_details'] = {}
    else:
        prop_dict['locality_details'] = {}
    return render_template('property_detail.html', prop=prop_dict, now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), is_winner=is_winner)

@app.route('/add-property', methods=['GET', 'POST'])
def add_property():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        location = request.form['location']
        latitude = request.form.get('latitude', None)
        longitude = request.form.get('longitude', None)
        prop_type = request.form['type']
        bedrooms = request.form.get('bedrooms', 0)
        bathrooms = request.form.get('bathrooms', 0)
        area = request.form.get('area', 0)
        auction_end = request.form.get('auction_end', None)

        # Calculate locality score if coordinates provided
        locality_score = 0
        locality_details = '{}'
        if latitude and longitude and str(latitude).strip() != '' and str(longitude).strip() != '':
            try:
                lat = float(latitude)
                lng = float(longitude)
                locality_score, details = calculate_locality_score(lat, lng)
                locality_details = json.dumps(details)
            except (ValueError, TypeError):
                latitude = None
                longitude = None

        db = get_db()
        cur = db.execute(
            """INSERT INTO properties 
            (user_id, title, description, price, location, latitude, longitude,
             locality_score, locality_details, type, bedrooms, bathrooms, area, auction_end, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session['user_id'], title, description, price, location,
             latitude, longitude, locality_score, locality_details,
             prop_type, bedrooms, bathrooms, area,
             auction_end if auction_end else None, 'pending')
        )
        property_id = cur.lastrowid

        # Handle multiple image uploads (max 4)
        files = request.files.getlist('images')
        saved_count = 0
        for i, file in enumerate(files):
            if saved_count >= 4:
                break
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                if not filename:
                    filename = f"image_{i}.jpg"
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                image_filename = f"{timestamp}_{i}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                db.execute(
                    "INSERT INTO property_images (property_id, filename, is_primary) VALUES (?,?,?)",
                    (property_id, image_filename, 1 if saved_count == 0 else 0)
                )
                saved_count += 1

        db.commit()
        flash('Property submitted for approval!', 'success')
        return redirect(url_for('user_dashboard'))
    return render_template('add_property.html')

# ─── EDIT PROPERTY ───────────────────────────────────────────────────────────
@app.route('/edit-property/<int:pid>', methods=['GET', 'POST'])
def edit_property(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id=? AND user_id=?", (pid, session['user_id'])).fetchone()
    if not prop:
        flash('Property not found or you do not have permission.', 'error')
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        location = request.form['location']
        latitude = request.form.get('latitude', prop['latitude'])
        longitude = request.form.get('longitude', prop['longitude'])
        prop_type = request.form['type']
        bedrooms = request.form.get('bedrooms', 0)
        bathrooms = request.form.get('bathrooms', 0)
        area = request.form.get('area', 0)
        auction_end = request.form.get('auction_end', None)

        # Recalculate locality score if coordinates changed
        locality_score = prop['locality_score']
        locality_details = prop['locality_details']
        if latitude and longitude and str(latitude).strip() != '' and str(longitude).strip() != '':
            try:
                lat = float(latitude)
                lng = float(longitude)
                old_lat = float(prop['latitude']) if prop['latitude'] else None
                old_lng = float(prop['longitude']) if prop['longitude'] else None
                if old_lat != lat or old_lng != lng:
                    locality_score, details = calculate_locality_score(lat, lng)
                    locality_details = json.dumps(details)
            except (ValueError, TypeError):
                pass

        db.execute(
            """UPDATE properties SET title=?, description=?, price=?, location=?,
               latitude=?, longitude=?, locality_score=?, locality_details=?,
               type=?, bedrooms=?, bathrooms=?, area=?, auction_end=?, status='pending'
               WHERE id=? AND user_id=?""",
            (title, description, price, location, latitude, longitude,
             locality_score, locality_details, prop_type, bedrooms, bathrooms, area,
             auction_end if auction_end else None, pid, session['user_id'])
        )

        # Handle image deletions
        delete_images = request.form.getlist('delete_images')
        for img_id in delete_images:
            img = db.execute("SELECT filename FROM property_images WHERE id=? AND property_id=?", (img_id, pid)).fetchone()
            if img:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], img['filename'])
                if os.path.exists(filepath):
                    os.remove(filepath)
                db.execute("DELETE FROM property_images WHERE id=?", (img_id,))

        # Handle new image uploads
        existing_count = db.execute("SELECT COUNT(*) as c FROM property_images WHERE property_id=?", (pid,)).fetchone()['c']
        files = request.files.getlist('images')
        for i, file in enumerate(files):
            if existing_count >= 4:
                break
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                image_filename = f"{timestamp}_{i}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                is_primary = 1 if existing_count == 0 else 0
                db.execute(
                    "INSERT INTO property_images (property_id, filename, is_primary) VALUES (?,?,?)",
                    (pid, image_filename, is_primary)
                )
                existing_count += 1

        # Ensure there's a primary image
        primary = db.execute("SELECT id FROM property_images WHERE property_id=? AND is_primary=1", (pid,)).fetchone()
        if not primary:
            first = db.execute("SELECT id FROM property_images WHERE property_id=? ORDER BY id ASC LIMIT 1", (pid,)).fetchone()
            if first:
                db.execute("UPDATE property_images SET is_primary=1 WHERE id=?", (first['id'],))

        db.commit()
        flash('Property updated successfully! Resubmitted for approval.', 'success')
        return redirect(url_for('user_dashboard'))

    prop_dict = dict(prop)
    prop_dict['images'] = get_property_images(pid)
    return render_template('edit_property.html', prop=prop_dict)

# ─── DELETE PROPERTY ─────────────────────────────────────────────────────────
@app.route('/delete-property/<int:pid>', methods=['POST'])
def delete_property(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id=? AND user_id=?", (pid, session['user_id'])).fetchone()
    if not prop:
        flash('Property not found or you do not have permission.', 'error')
        return redirect(url_for('user_dashboard'))

    # Delete image files from disk
    delete_property_files(pid)

    # Delete property records (cascading will remove images, bids, bookings in DB)
    db.execute("DELETE FROM property_images WHERE property_id=?", (pid,))
    db.execute("DELETE FROM bids WHERE property_id=?", (pid,))
    db.execute("DELETE FROM bookings WHERE property_id=?", (pid,))
    db.execute("DELETE FROM properties WHERE id=?", (pid,))
    db.commit()
    flash('Property deleted successfully.', 'success')
    return redirect(url_for('user_dashboard'))

# ─── BOOKING / APPOINTMENT ───────────────────────────────────────────────────
@app.route('/book/<int:pid>', methods=['GET', 'POST'])
def book_property(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id=? AND status='approved'", (pid,)).fetchone()
    if not prop:
        flash('Property not available for appointment.', 'error')
        return redirect(url_for('properties'))
    
    # Restrict auction bookings to winners
    if prop['type'] == 'auction':
        # Check if auction ended
        if not prop['auction_end'] or datetime.strptime(prop['auction_end'], '%Y-%m-%d %H:%M:%S' if ' ' in prop['auction_end'] else '%Y-%m-%dT%H:%M') > datetime.now():
            flash('Auction is still active. Appointments can only be booked by the winner after it ends.', 'error')
            return redirect(url_for('property_detail', pid=pid))
        
        # Check if user is the winner
        winner = db.execute(
            "SELECT user_id FROM bids WHERE property_id=? ORDER BY amount DESC LIMIT 1", (pid,)
        ).fetchone()
        
        if not winner or winner['user_id'] != session['user_id']:
            flash('Only the auction winner can book an appointment for this property.', 'error')
            return redirect(url_for('property_detail', pid=pid))
    
    if request.method == 'POST':
        date = request.form.get('appointment_date')
        slot = request.form.get('time_slot')
        
        if not date or not slot:
            flash('Please select both a date and a time slot.', 'error')
            return redirect(url_for('book_property', pid=pid))

        # Double check availability
        existing = db.execute(
            "SELECT id FROM bookings WHERE property_id=? AND appointment_date=? AND time_slot=? AND status != 'cancelled'",
            (pid, date, slot)
        ).fetchone()
        
        if existing:
            flash('This time slot has just been taken. Please choose another.', 'error')
            return redirect(url_for('book_property', pid=pid))

        db.execute(
            "INSERT INTO bookings (user_id, property_id, appointment_date, time_slot, status) VALUES (?,?,?,?,'pending')",
            (session['user_id'], pid, date, slot)
        )
        db.commit()
        flash('Appointment request submitted! Waiting for owner/admin approval.', 'success')
        return redirect(url_for('user_dashboard'))
    
    return render_template('book_property.html', prop=prop)

@app.route('/api/booked-slots/<int:pid>')
def get_booked_slots(pid):
    date = request.args.get('date')
    if not date:
        return jsonify([])
    db = get_db()
    booked = db.execute(
        "SELECT time_slot FROM bookings WHERE property_id=? AND appointment_date=? AND status IN ('pending', 'approved')",
        (pid, date)
    ).fetchall()
    return jsonify([b['time_slot'] for b in booked])

@app.route('/stop-auction/<int:pid>')
def stop_auction(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    # Ensure user owns the property
    prop = db.execute("SELECT * FROM properties WHERE id=? AND user_id=?", (pid, session['user_id'])).fetchone()
    if not prop:
        flash('Property not found or access denied.', 'error')
        return redirect(url_for('user_dashboard'))
    
    if prop['type'] != 'auction':
        flash('This property is not an auction.', 'error')
        return redirect(url_for('user_dashboard'))

    # Set auction_end to now
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute("UPDATE properties SET auction_end=? WHERE id=?", (now_str, pid))
    db.commit()
    flash('Auction stopped successfully. The highest bidder can now book an appointment.', 'success')
    return redirect(url_for('user_dashboard'))

# ─── AUCTIONS ────────────────────────────────────────────────────────────────
@app.route('/auctions')
def auctions():
    db = get_db()
    auction_list = db.execute(
        """SELECT p.*, u.name as owner_name, 
           (SELECT MAX(b.amount) FROM bids b WHERE b.property_id=p.id) as current_bid
           FROM properties p JOIN users u ON p.user_id=u.id 
           WHERE p.type='auction' AND p.status='approved' 
           ORDER BY p.auction_end ASC"""
    ).fetchall()
    # Attach primary images and winner info
    auctions_list = []
    current_user_id = session.get('user_id')
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    for a in auction_list:
        a_dict = dict(a)
        a_dict['image'] = get_primary_image(a['id'])
        
        # Check if current user is winner
        is_winner = False
        has_ended = False
        if a['auction_end']:
            auction_end_dt = datetime.strptime(a['auction_end'], '%Y-%m-%d %H:%M:%S' if ' ' in a['auction_end'] else '%Y-%m-%dT%H:%M')
            if auction_end_dt <= now:
                has_ended = True
                winner = db.execute(
                    "SELECT user_id FROM bids WHERE property_id=? ORDER BY amount DESC LIMIT 1", (a['id'],)
                ).fetchone()
                if winner and winner['user_id'] == current_user_id:
                    is_winner = True
        
        a_dict['is_winner'] = is_winner
        a_dict['has_ended'] = has_ended
        auctions_list.append(a_dict)
        
    return render_template('auctions.html', auctions=auctions_list, now_str=now_str)

@app.route('/bid/<int:pid>', methods=['POST'])
def place_bid(pid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        amount = float(request.form['amount'])
    except (ValueError, KeyError):
        flash('Invalid bid amount.', 'error')
        return redirect(url_for('auctions'))

    db = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id=? AND type='auction' AND status='approved'", (pid,)).fetchone()
    
    if not prop:
        flash('Auction not found or not active.', 'error')
        return redirect(url_for('auctions'))
        
    # Check if auction has ended
    if prop['auction_end'] and datetime.strptime(prop['auction_end'], '%Y-%m-%d %H:%M:%S' if ' ' in prop['auction_end'] else '%Y-%m-%dT%H:%M') < datetime.now():
        flash('Auction has already ended.', 'error')
        return redirect(url_for('auctions'))

    top = db.execute("SELECT MAX(amount) as top FROM bids WHERE property_id=?", (pid,)).fetchone()
    min_bid = float(top['top']) if top['top'] else float(prop['price'])
    
    if amount <= min_bid:
        flash(f'Bid must be higher than current top bid (₹{min_bid:,.0f})', 'error')
        return redirect(url_for('auctions'))
        
    db.execute("INSERT INTO bids (user_id, property_id, amount) VALUES (?,?,?)", (session['user_id'], pid, amount))
    db.commit()
    flash('Bid placed successfully!', 'success')
    return redirect(url_for('auctions'))

# ─── ADMIN ───────────────────────────────────────────────────────────────────
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session['user_role'] != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    users_count = db.execute("SELECT COUNT(*) as c FROM users WHERE role='user'").fetchone()['c']
    props_count = db.execute("SELECT COUNT(*) as c FROM properties").fetchone()['c']
    pending_count = db.execute("SELECT COUNT(*) as c FROM properties WHERE status='pending'").fetchone()['c']
    bookings_count = db.execute("SELECT COUNT(*) as c FROM bookings").fetchone()['c']

    pending_props = db.execute(
        """SELECT p.*, u.name as owner_name FROM properties p 
           JOIN users u ON p.user_id=u.id WHERE p.status='pending' 
           ORDER BY p.created_at DESC"""
    ).fetchall()
    # Attach images to pending
    pending_list = []
    for p in pending_props:
        p_dict = dict(p)
        p_dict['image'] = get_primary_image(p['id'])
        p_dict['image_count'] = get_image_count(p['id'])
        pending_list.append(p_dict)

    all_users = db.execute("SELECT * FROM users WHERE role='user' ORDER BY created_at DESC").fetchall()

    all_props_raw = db.execute(
        """SELECT p.*, u.name as owner_name FROM properties p 
           JOIN users u ON p.user_id=u.id ORDER BY p.created_at DESC"""
    ).fetchall()
    all_props = []
    for p in all_props_raw:
        p_dict = dict(p)
        p_dict['image'] = get_primary_image(p['id'])
        p_dict['image_count'] = get_image_count(p['id'])
        all_props.append(p_dict)

    all_bookings = db.execute(
        """SELECT b.*, u.name as user_name, p.title as property_title 
           FROM bookings b JOIN users u ON b.user_id=u.id 
           JOIN properties p ON b.property_id=p.id 
           ORDER BY b.created_at DESC"""
    ).fetchall()

    return render_template('admin_dashboard.html',
        users_count=users_count, props_count=props_count,
        pending_count=pending_count, bookings_count=bookings_count,
        pending_props=pending_list, all_users=all_users,
        all_props=all_props, all_bookings=all_bookings)

@app.route('/admin/approve/<int:pid>')
def approve_property(pid):
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    db.execute("UPDATE properties SET status='approved' WHERE id=?", (pid,))
    db.commit()
    flash('Property approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:pid>')
def reject_property(pid):
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    db.execute("UPDATE properties SET status='rejected' WHERE id=?", (pid,))
    db.commit()
    flash('Property rejected.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-user/<int:uid>')
def delete_user(uid):
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    
    # Fetch all properties belonging to this user to delete their images from disk
    user_props = db.execute("SELECT id FROM properties WHERE user_id=?", (uid,)).fetchall()
    for p in user_props:
        delete_property_files(p['id'])
        
    db.execute("DELETE FROM users WHERE id=? AND role='user'", (uid,))
    db.commit()
    flash('User and all their property listings deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-property/<int:pid>')
def admin_delete_property(pid):
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    
    # Delete image files from disk
    delete_property_files(pid)
            
    # Delete property record (DB cascade handles related records)
    db.execute("DELETE FROM properties WHERE id=?", (pid,))
    db.commit()
    flash('Property deleted by admin.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/booking/approve/<int:bid>')
def approve_booking(bid):
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    db.execute("UPDATE bookings SET status='approved' WHERE id=?", (bid,))
    db.commit()
    flash('Booking approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/booking/reject/<int:bid>')
def reject_booking(bid):
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    db.execute("UPDATE bookings SET status='rejected' WHERE id=?", (bid,))
    db.commit()
    flash('Booking rejected.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/auctions')
def admin_auctions():
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
    db = get_db()
    
    # Get all auction properties
    auctions = db.execute(
        """SELECT p.*, u.name as owner_name 
           FROM properties p JOIN users u ON p.user_id=u.id 
           WHERE p.type='auction' ORDER BY p.created_at DESC"""
    ).fetchall()
    
    auction_data = []
    for a in auctions:
        a_dict = dict(a)
        # Get all bids for this auction
        bids = db.execute(
            """SELECT b.*, u.name as bidder_name, u.email as bidder_email 
               FROM bids b JOIN users u ON b.user_id=u.id 
               WHERE b.property_id=? ORDER BY b.amount DESC""", (a['id'],)
        ).fetchall()
        a_dict['bids'] = bids
        a_dict['top_bid'] = bids[0] if bids else None
        auction_data.append(a_dict)
        
    return render_template('admin_auctions.html', auctions=auction_data, now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

if __name__ == '__main__':
    app.run(debug=True)
