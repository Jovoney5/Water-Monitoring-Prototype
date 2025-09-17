# Water Quality Monitoring System

A complete web-based water quality monitoring system with real-time data entry, admin monitoring, and monthly report generation.

## Project Structure

```
Water Monitoring Prototype/
├── app.py              # Flask backend with SQLite database
├── requirements.txt    # Python dependencies
├── index.html         # Inspector data entry page
├── admin.html         # Admin real-time monitoring dashboard
├── report.html        # Monthly report generator
└── README.md          # This file
```

## Features

### 🔐 **Authentication System**
- **Inspector Login:** inspector / inspector123
- **Admin Login:** admin / admin123
- Role-based access control

### 📝 **Inspector Dashboard (index.html)**
- Dropdown with all 41 pre-loaded water supplies
- Grouped by Treated (19) and Untreated (22) supplies
- Color-coded form fields:
  - 🟢 **Positive tests** (green background)
  - 🔴 **Negative tests** (red background)
  - 🟡 **Pending tests** (yellow background)
- **Smart Forms:**
  - Chlorine tests only for treated supplies
  - Auto-calculation of chlorine totals
  - +1 Visit quick button
  - Real-time data persistence

### 📊 **Admin Dashboard (admin.html)**
- Real-time grid of all water supplies
- Live statistics and updates
- Color-coded supply cards
- Filter by type (treated/untreated) and agency
- WebSocket notifications for new data

### 📋 **Monthly Reports (report.html)**
- Exact format matching monthly report structure
- **Two separate tables:**
  - Treated Supplies (with chlorine data)
  - Untreated Supplies (bacteriological only)
- Color-coded cells for easy reading
- Print/PDF ready format
- Monthly summary statistics

### ⚡ **Real-time Features**
- WebSocket updates between inspector and admin
- Live notifications
- Automatic data synchronization
- Online/offline status indicators

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the server:**
   ```bash
   python app.py
   ```

3. **Access the system:**
   - Open: http://localhost:5003
   - Login with demo credentials

## Pre-loaded Water Supplies

### Treated Supplies (19)
- Roaring River 1, Roaring River 2, Bluemede, Dantrout
- Bluefield's, Negril/Logwood, Bethel Town/Cambridge
- Venture-Williamsfield, Shettlewood, Cave, Carawina
- Dean's Valley, New Works, New Works-Steward Lands
- Castle Mountain, Berkshire Shane, Army Mountains
- Beeston Spring, Spring Gardens

### Untreated Supplies (22)
- Content, Holly Hill, Bunion (Bunyan), Lundi
- Pinnock Shafton, Orange Hill, Cairn Curran, Cedar Valley
- Leamington, Charlie Mount, New Roads, Belvedere
- York Mountain, Ashton, Kilmarnock, Bronti
- Argyle Mountain, Bog, Porters Mountain, Ketto
- Lambs River, Bath Mtns.

## Database Schema

- **users:** Authentication and roles
- **water_supplies:** All water supply locations
- **monthly_supply_data:** Accumulative monthly data

## API Endpoints

- `GET /api/supplies` - Get all water supplies
- `GET /api/monthly-data` - Get current month data
- `POST /api/update-supply-data` - Update supply data
- `GET /api/report/{year}/{month}` - Generate monthly report

## Technology Stack

- **Backend:** Python Flask + SQLite
- **Frontend:** HTML5 + CSS3 + Vanilla JavaScript
- **Real-time:** Flask-SocketIO
- **Styling:** Embedded CSS with modern design
- **Database:** SQLite with automatic initialization

## Key Features

✅ **Accumulative Data:** Updates existing monthly data instead of creating separate records
✅ **Smart UI:** Chlorine fields disabled for untreated supplies
✅ **Color Coding:** Consistent green/red/yellow throughout system
✅ **Real-time Sync:** Admin sees updates instantly
✅ **Print Ready:** Professional report formatting
✅ **Mobile Friendly:** Responsive design
✅ **Data Validation:** Form validation and error handling

## Usage

1. **Inspectors:** Use index.html to enter daily water quality data
2. **Admins:** Monitor real-time updates on admin.html dashboard
3. **Reports:** Generate and print monthly reports from report.html

The system generates exactly the monthly report format described, with proper color coding and all required water supplies pre-loaded!