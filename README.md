# Elite Estates — Luxury Real Estate Management System
## Setup Guide

### 1. Prerequisites
- Python 3.8+
- XAMPP (Apache + MySQL running)
- pip

---

### 2. Database Setup
1. Open **phpMyAdmin** → `http://localhost/phpmyadmin`
2. Click **Import** → Choose `schema.sql` → Click **Go**
3. Database `elite_estates` will be created with all tables + demo data

---

### 3. Install Python Dependencies
```bash
cd elite_estates
pip install -r requirements.txt
```

> On some systems (especially Ubuntu/Debian), you may need:
> ```bash
> sudo apt-get install python3-dev default-libmysqlclient-dev build-essential
> ```

---

### 4. Configure Database (if needed)
Open `app.py` and update if your XAMPP MySQL has a password:
```python
app.config['MYSQL_PASSWORD'] = 'your_password_here'
```

---

### 5. Run the App
```bash
python app.py
```
Visit: **http://localhost:5000**

---

### 6. Demo Credentials

| Role  | Email                        | Password    |
|-------|------------------------------|-------------|
| Admin | admin@eliteestates.com       | admin123    |
| User  | user@demo.com                | password123 |

---

### 7. Features

#### Users Can:
- Register / Login
- Browse all approved properties (sale, rent, auction)
- Search & filter properties
- Upload properties with photos (goes to admin for approval)
- Book appointments with 10% advance
- Bid on auction properties
- View their dashboard (listings + bookings)

#### Admins Can:
- Approve / Reject submitted properties
- View all users and delete accounts
- Monitor all bookings and listings
- Full dashboard with stats

---

### 8. Project Structure
```
elite_estates/
├── app.py                  # Flask application
├── schema.sql              # MySQL database schema
├── requirements.txt        # Python dependencies
├── templates/
│   ├── base.html           # Shared layout
│   ├── index.html          # Homepage
│   ├── login.html          # Login page
│   ├── register.html       # Registration page
│   ├── properties.html     # Property listings
│   ├── property_detail.html
│   ├── add_property.html   # List a property
│   ├── book_property.html  # Booking page
│   ├── auctions.html       # Live auctions
│   ├── user_dashboard.html
│   └── admin_dashboard.html
└── static/
    └── uploads/            # Property images stored here
```

---

### Design Theme
- **Black & Gold** luxury aesthetic (matching your uploaded template)
- Playfair Display + Poppins typography
- Responsive grid layouts
- Animated flash messages, countdown timers for auctions
