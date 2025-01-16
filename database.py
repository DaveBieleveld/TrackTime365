import pyodbc
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, logger
import os
from datetime import timezone

class DatabaseManager:
    def __init__(self):
        self.connection_string = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD};"
            "TrustServerCertificate=yes;"
            "Encrypt=no"
        )
        self.initialize_table()

    def get_connection(self):
        """Get a new database connection."""
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logger.error(f"Error connecting to database: {str(e)}")
            raise

    def get_or_create_category(self, category_name):
        """Get or create a category by name."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Try to get existing category
                    cursor.execute("""
                        SELECT category_id 
                        FROM calendar_category 
                        WHERE name = ?
                    """, [category_name])
                    
                    row = cursor.fetchone()
                    if row:
                        return row[0]  # Return existing category_id
                    
                    # Create new category if it doesn't exist
                    cursor.execute("""
                        INSERT INTO calendar_category (name)
                        OUTPUT INSERTED.category_id
                        VALUES (?)
                    """, [category_name])
                    
                    row = cursor.fetchone()
                    category_id = row[0]
                    conn.commit()
                    return category_id
        except Exception as e:
            logger.error(f"Database error while getting/creating category: {str(e)}")
            raise

    def link_event_categories(self, event_id, category_names):
        """Link an event to its categories."""
        if not category_names:
            return
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # First remove existing category links
                    cursor.execute("""
                        DELETE FROM calendar_event_calendar_category 
                        WHERE event_id = ?
                    """, [event_id])
                    
                    # Add new category links
                    for name in category_names:
                        category_id = self.get_or_create_category(name)
                        cursor.execute("""
                            INSERT INTO calendar_event_calendar_category (event_id, category_id)
                            VALUES (?, ?)
                        """, [event_id, category_id])
                    conn.commit()
        except Exception as e:
            logger.error(f"Database error while linking categories: {str(e)}")
            raise

    def get_event_categories(self, event_id):
        """Get all categories for an event."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT c.category_id, c.name
                        FROM calendar_event_calendar_category ec
                        JOIN calendar_category c ON ec.category_id = c.category_id
                        WHERE ec.event_id = ?
                    """, [event_id])
                    
                    return [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Database error while getting event categories: {str(e)}")
            raise

    def upsert_event(self, event):
        """Insert or update a calendar event."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check if event exists
                    cursor.execute("""
                        SELECT COUNT(*) FROM calendar_event WHERE event_id = ?
                    """, [event['event_id']])
                    
                    exists = cursor.fetchone()[0] > 0
                    
                    if exists:
                        # Update existing event
                        cursor.execute("""
                            UPDATE calendar_event
                            SET user_email = ?,
                                user_name = ?,
                                subject = ?,
                                description = ?,
                                start_date = ?,
                                end_date = ?,
                                last_modified = ?,
                                is_deleted = ?,
                                updated_at = GETDATE()
                            WHERE event_id = ?
                        """, (
                            event['user_email'],
                            event['user_name'],
                            event['subject'],
                            event['description'],
                            event['start_date'],
                            event['end_date'],
                            event['last_modified'],
                            event['is_deleted'],
                            event['event_id']
                        ))
                        logger.info(f"Updated event: {event['subject']} for user {event['user_email']}")
                    else:
                        # Insert new event
                        cursor.execute("""
                            INSERT INTO calendar_event (
                                event_id, user_email, user_name, subject, description,
                                start_date, end_date, last_modified, is_deleted
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            event['event_id'],
                            event['user_email'],
                            event['user_name'],
                            event['subject'],
                            event['description'],
                            event['start_date'],
                            event['end_date'],
                            event['last_modified'],
                            event['is_deleted']
                        ))
                        logger.info(f"Inserted new event: {event['subject']} for user {event['user_email']}")
                    
                    conn.commit()
        except Exception as e:
            logger.error(f"Database error while upserting event: {str(e)}")
            raise

    def get_events_by_date_range(self, start_date, end_date, user_email=None):
        """Retrieve events within a date range."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if user_email:
                        cursor.execute("""
                            SELECT * FROM calendar_event 
                            WHERE start_date <= ? 
                            AND end_date >= ?
                            AND user_email = ?
                            AND is_deleted = 0
                        """, [end_date, start_date, user_email])
                    else:
                        cursor.execute("""
                            SELECT * FROM calendar_event 
                            WHERE start_date <= ? 
                            AND end_date >= ?
                            AND is_deleted = 0
                        """, [end_date, start_date])
                    
                    columns = [column[0] for column in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Database error while getting events: {str(e)}")
            raise

    def mark_event_deleted(self, event_id):
        """Mark an event as deleted."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE calendar_event
                        SET is_deleted = 1,
                            updated_at = GETDATE()
                        WHERE event_id = ?
                    """, [event_id])
                    conn.commit()
                    logger.info(f"Marked event as deleted: {event_id}")
        except Exception as e:
            logger.error(f"Database error while marking event as deleted: {str(e)}")
            raise

    def initialize_table(self):
        """Initialize the database tables if they don't exist."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Create calendar_event table if it doesn't exist
                    cursor.execute("""
                        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='calendar_event' and xtype='U')
                        CREATE TABLE calendar_event (
                            event_id NVARCHAR(255) PRIMARY KEY,
                            user_email NVARCHAR(255) NOT NULL,
                            user_name NVARCHAR(255),
                            subject NVARCHAR(255),
                            description NVARCHAR(1000),
                            start_date DATETIME NOT NULL,
                            end_date DATETIME NOT NULL,
                            last_modified DATETIME NOT NULL,
                            is_deleted BIT NOT NULL DEFAULT 0,
                            created_at DATETIME NOT NULL DEFAULT GETDATE(),
                            updated_at DATETIME NOT NULL DEFAULT GETDATE()
                        )
                    """)

                    # Create calendar_category table if it doesn't exist
                    cursor.execute("""
                        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='calendar_category' and xtype='U')
                        CREATE TABLE calendar_category (
                            category_id INT IDENTITY(1,1) PRIMARY KEY,
                            name NVARCHAR(255) NOT NULL UNIQUE,
                            is_project AS CASE WHEN name LIKE '%[[]PROJECT]%' THEN 1 ELSE 0 END PERSISTED,
                            is_activity AS CASE WHEN name LIKE '%[[]ACTIVITY]%' THEN 1 ELSE 0 END PERSISTED,
                            created_at DATETIME NOT NULL DEFAULT GETDATE(),
                            updated_at DATETIME NOT NULL DEFAULT GETDATE()
                        )
                    """)

                    # Create calendar_event_calendar_category table if it doesn't exist
                    cursor.execute("""
                        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='calendar_event_calendar_category' and xtype='U')
                        BEGIN
                            CREATE TABLE calendar_event_calendar_category (
                                event_id NVARCHAR(255) NOT NULL,
                                category_id INT NOT NULL,
                                created_at DATETIME NOT NULL DEFAULT GETDATE(),
                                updated_at DATETIME NOT NULL DEFAULT GETDATE(),
                                CONSTRAINT PK_calendar_event_calendar_category PRIMARY KEY (event_id, category_id),
                                CONSTRAINT FK_calendar_event_calendar_category_event FOREIGN KEY (event_id) REFERENCES calendar_event(event_id),
                                CONSTRAINT FK_calendar_event_calendar_category_category FOREIGN KEY (category_id) REFERENCES calendar_category(category_id)
                            )

                            -- Add indexes for better query performance
                            CREATE INDEX IX_calendar_category_name ON calendar_category(name)
                            CREATE INDEX IX_calendar_event_calendar_category_event_id ON calendar_event_calendar_category(event_id)
                            CREATE INDEX IX_calendar_event_calendar_category_category_id ON calendar_event_calendar_category(category_id)
                        END
                    """)
                    conn.commit()
                    logger.info("Tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise 