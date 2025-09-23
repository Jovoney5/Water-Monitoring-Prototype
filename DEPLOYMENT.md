# PostgreSQL Migration & Deployment Guide

This guide will help you migrate your Flask water monitoring application from SQLite to PostgreSQL for production deployment on Render.

## What's Been Updated

✅ **Dependencies Added**:
- `psycopg2-binary==2.9.7` - PostgreSQL adapter
- `SQLAlchemy==2.0.21` - Database toolkit
- `python-dotenv==1.0.0` - Environment variable management

✅ **Database Support**:
- Dual database support (PostgreSQL for production, SQLite for development)
- Environment variable configuration
- PostgreSQL-compatible SQL queries

## Quick Setup

### 1. Local Development (SQLite)
```bash
# Install new dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Your app will automatically use SQLite locally
python app.py
```

### 2. Production Deployment on Render

#### Step 1: Create PostgreSQL Database on Render
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "PostgreSQL"
3. Configure your database:
   - Name: `water-monitoring-db`
   - Database: `water_monitoring`
   - User: `water_monitoring_user`
   - Region: Choose closest to your users
   - Plan: Choose based on your needs (Free tier available)
4. Click "Create Database"
5. **Save the connection details** - you'll need the `External Database URL`

#### Step 2: Deploy Web Service on Render
1. Click "New" → "Web Service"
2. Connect your GitHub repository
3. Configure your service:
   - Name: `water-monitoring-app`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`
4. **Add Environment Variables**:
   - `DATABASE_URL`: Paste your PostgreSQL External Database URL
   - `FLASK_ENV`: `production`
   - `SECRET_KEY`: `water-monitoring-secret-key-2024`

#### Step 3: Deploy
1. Click "Create Web Service"
2. Render will automatically build and deploy your app
3. Your app will be available at `https://your-app-name.onrender.com`

## Environment Variables

### Required for Production:
- `DATABASE_URL`: PostgreSQL connection string from Render
- `FLASK_ENV`: Set to `production`
- `SECRET_KEY`: Your app secret key

### Optional:
- `PORT`: Render sets this automatically

## Database Migration

Your app will automatically:
- Create all necessary tables on first run
- Populate initial data (users, water supplies)
- Handle both SQLite (development) and PostgreSQL (production)

## Troubleshooting

### Common Issues:

1. **Database Connection Errors**
   - Verify your `DATABASE_URL` is correct
   - Check if PostgreSQL database is running on Render

2. **Module Import Errors**
   - Ensure all dependencies are in `requirements.txt`
   - Run `pip install -r requirements.txt`

3. **Application Startup Issues**
   - Check Render logs for specific error messages
   - Verify environment variables are set correctly

### Debug Mode:
- Set `FLASK_ENV=development` for detailed error messages
- Check application logs in Render dashboard

## Testing the Migration

### Local Testing with PostgreSQL:
1. Install PostgreSQL locally
2. Create a test database
3. Set `DATABASE_URL` in your `.env` file
4. Run the application

### Verify Production Deployment:
1. Check that your app loads at the Render URL
2. Test login functionality
3. Verify water supplies are loading
4. Test form submissions

## Database Schema

The app automatically creates these tables:
- `users` - Inspector and admin accounts
- `water_supplies` - Water supply locations by parish
- `inspection_submissions` - Individual inspection reports
- `monthly_supply_data` - Aggregated monthly data
- `sampling_points` - Sample collection points
- `inspector_tasks` - Task assignments

## Data Migration

If you have existing SQLite data you want to migrate:
1. Export data from SQLite using the admin dashboard
2. Import data through the PostgreSQL admin interface
3. Or contact support for migration assistance

## Support

For deployment issues:
- Check Render documentation: https://render.com/docs
- Review application logs in Render dashboard
- Verify database connectivity in Render PostgreSQL dashboard

Your water monitoring application is now ready for production deployment with persistent PostgreSQL storage! 🚀