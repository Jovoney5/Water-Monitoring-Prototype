#!/usr/bin/env python3
"""
Database migration script to add new columns to inspection_submissions table
"""
import sqlite3
import sys

def migrate_database():
    try:
        conn = sqlite3.connect('water_monitoring.db')
        cursor = conn.cursor()

        print("Starting database migration on water_monitoring.db...")

        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspection_submissions'")
        if not cursor.fetchone():
            print("Table inspection_submissions does not exist. Run the main app to create it first.")
            return

        # Get existing columns
        cursor.execute("PRAGMA table_info(inspection_submissions)")
        existing_columns = {col[1] for col in cursor.fetchall()}
        print(f"Found {len(existing_columns)} existing columns")

        # Define new columns to add
        new_columns = [
            ("bacteriological_positive_status", "VARCHAR(50)"),
            ("bacteriological_negative_status", "VARCHAR(50)"),
            ("chemical_satisfactory", "INTEGER DEFAULT 0"),
            ("chemical_non_satisfactory", "INTEGER DEFAULT 0"),
            ("chemical_non_satisfactory_params", "TEXT"),
            ("turbidity_satisfactory", "INTEGER DEFAULT 0"),
            ("turbidity_non_satisfactory", "INTEGER DEFAULT 0"),
            ("temperature_satisfactory", "INTEGER DEFAULT 0"),
            ("temperature_non_satisfactory", "INTEGER DEFAULT 0"),
            ("ph_non_satisfactory_params", "TEXT"),
        ]

        # Add missing columns
        added_count = 0
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE inspection_submissions ADD COLUMN {col_name} {col_type}")
                    print(f"✓ Added column: {col_name}")
                    added_count += 1
                except sqlite3.OperationalError as e:
                    print(f"✗ Could not add {col_name}: {e}")
            else:
                print(f"○ Column already exists: {col_name}")

        conn.commit()
        print(f"\nMigration complete! Added {added_count} new columns.")

        # Verify final schema
        cursor.execute("PRAGMA table_info(inspection_submissions)")
        all_columns = cursor.fetchall()
        print(f"\nFinal schema has {len(all_columns)} columns:")
        for col in all_columns:
            print(f"  - {col[1]}: {col[2]}")

        conn.close()

    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate_database()
