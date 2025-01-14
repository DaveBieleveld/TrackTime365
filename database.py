import django.db
from django.db import connection
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, logger
import os
from datetime import timezone

# Configure Django database settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
if not os.environ.get('DJANGO_SETTINGS_CONFIGURED'):
    from django.conf import settings
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'mssql',
                'NAME': DB_NAME,
                'HOST': DB_SERVER,
                'USER': DB_USER,
                'PASSWORD': DB_PASSWORD,
                'OPTIONS': {
                    'driver': 'ODBC Driver 18 for SQL Server',
                    'TrustServerCertificate': 'yes',
                    'Encrypt': 'no',
                    'Trusted_Connection': 'no',
                    'trust_server_certificate': 'yes',
                    'connection_timeout': 30,
                    'extra_params': 'TrustServerCertificate=yes;Encrypt=no;',
                    'unicode_results': True,
                },
            }
        },
        INSTALLED_APPS=[],
        DATABASE_ROUTERS=[],
    )
    django.setup()

class DatabaseManager:
    def __init__(self):
        self.initialize_table()

    def initialize_table(self):
        """Create all necessary tables if they don't exist."""
        try:
            with connection.cursor() as cursor:
                # Create calendar_event table if it doesn't exist
                cursor.execute("""
                    IF NOT EXISTS (
                        SELECT * FROM sys.tables 
                        WHERE name = 'calendar_event'
                    )
                    BEGIN
                        CREATE TABLE calendar_event (
                            event_id NVARCHAR(255) PRIMARY KEY,
                            user_email NVARCHAR(255) NOT NULL,
                            user_name NVARCHAR(255),
                            subject NVARCHAR(255),
                            start_date DATETIME,
                            end_date DATETIME,
                            start_date_utc DATETIME,
                            end_date_utc DATETIME,
                            description NVARCHAR(MAX),
                            last_modified DATETIME,
                            is_deleted BIT DEFAULT 0,
                            created_at DATETIME DEFAULT GETDATE(),
                            updated_at DATETIME DEFAULT GETDATE()
                        );
                        CREATE INDEX IX_calendar_event_user_email ON calendar_event(user_email);
                        CREATE INDEX IX_calendar_event_dates ON calendar_event(start_date, end_date);
                    END;

                    -- Create calendar_category table if it doesn't exist
                    IF NOT EXISTS (
                        SELECT * FROM sys.tables 
                        WHERE name = 'calendar_category'
                    )
                    BEGIN
                        CREATE TABLE calendar_category (
                            category_id INT IDENTITY(1,1) PRIMARY KEY,
                            name NVARCHAR(255) UNIQUE NOT NULL,
                            is_project AS CAST(CASE WHEN name LIKE '[[]PROJECT]%' THEN 1 ELSE 0 END AS BIT) PERSISTED,
                            is_activity AS CAST(CASE WHEN name LIKE '[[]ACTIVITY]%' THEN 1 ELSE 0 END AS BIT) PERSISTED,
                            created_at DATETIME DEFAULT GETDATE(),
                            updated_at DATETIME DEFAULT GETDATE()
                        );
                    END;

                    -- Create junction table calendar_event_calendar_category if it doesn't exist
                    IF NOT EXISTS (
                        SELECT * FROM sys.tables 
                        WHERE name = 'calendar_event_calendar_category'
                    )
                    BEGIN
                        CREATE TABLE calendar_event_calendar_category (
                            event_id NVARCHAR(255),
                            category_id INT,
                            PRIMARY KEY (event_id, category_id),
                            FOREIGN KEY (event_id) REFERENCES calendar_event(event_id),
                            FOREIGN KEY (category_id) REFERENCES calendar_category(category_id)
                        );
                    END;

                    -- Drop category column from calendar_event if it exists
                    IF EXISTS (
                        SELECT * FROM sys.columns 
                        WHERE object_id = OBJECT_ID('calendar_event') 
                        AND name = 'category'
                    )
                    BEGIN
                        ALTER TABLE calendar_event DROP COLUMN category;
                    END;
                """)
                logger.info("All database tables initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {str(e)}")
            raise

    def upsert_event(self, event):
        """Insert or update a calendar event."""
        try:
            with connection.cursor() as cursor:
                # Check if event exists
                cursor.execute("""
                    SELECT event_id FROM calendar_event 
                    WHERE event_id = %s
                """, [event['event_id']])
                
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update existing event
                    cursor.execute("""
                        UPDATE calendar_event 
                        SET subject = %s,
                            user_email = %s,
                            user_name = %s,
                            start_date = %s,
                            end_date = %s,
                            start_date_utc = %s,
                            end_date_utc = %s,
                            description = %s,
                            last_modified = %s,
                            is_deleted = %s,
                            updated_at = GETDATE()
                        WHERE event_id = %s
                    """, [
                        event['subject'],
                        event['user_email'],
                        event['user_name'],
                        event['start_date'],
                        event['end_date'],
                        event['start_date_utc'],
                        event['end_date_utc'],
                        event['description'],
                        event['last_modified'],
                        event['is_deleted'],
                        event['event_id']
                    ])
                    logger.info(f"Updated event: {event['subject']} for user {event['user_email']}")
                else:
                    # Insert new event
                    cursor.execute("""
                        INSERT INTO calendar_event (
                            event_id, user_email, user_name, subject,
                            start_date, end_date, start_date_utc, end_date_utc,
                            description, last_modified, is_deleted
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, [
                        event['event_id'],
                        event['user_email'],
                        event['user_name'],
                        event['subject'],
                        event['start_date'],
                        event['end_date'],
                        event['start_date_utc'],
                        event['end_date_utc'],
                        event['description'],
                        event['last_modified'],
                        event['is_deleted']
                    ])
                    logger.info(f"Inserted new event: {event['subject']} for user {event['user_email']}")
                
        except Exception as e:
            logger.error(f"Database error while upserting event: {str(e)}")
            raise

    def get_events_by_date_range(self, start_date, end_date, user_email=None):
        """Retrieve events within a date range."""
        try:
            with connection.cursor() as cursor:
                if user_email:
                    cursor.execute("""
                        SELECT * FROM calendar_event 
                        WHERE start_date_utc >= %s 
                        AND end_date_utc <= %s
                        AND user_email = %s
                        AND is_deleted = 0
                        ORDER BY start_date_utc
                    """, [start_date, end_date, user_email])
                else:
                    cursor.execute("""
                        SELECT * FROM calendar_event 
                        WHERE start_date_utc >= %s 
                        AND end_date_utc <= %s
                        AND is_deleted = 0
                        ORDER BY start_date_utc
                    """, [start_date, end_date])
                
                columns = [col[0] for col in cursor.description]
                events = []
                for row in cursor.fetchall():
                    event_dict = dict(zip(columns, row))
                    # Convert UTC datetime fields to timezone-aware
                    if event_dict['start_date_utc']:
                        event_dict['start_date_utc'] = event_dict['start_date_utc'].replace(tzinfo=timezone.utc)
                    if event_dict['end_date_utc']:
                        event_dict['end_date_utc'] = event_dict['end_date_utc'].replace(tzinfo=timezone.utc)
                    # Get categories for this event
                    event_dict['categories'] = self.get_event_categories(event_dict['event_id'])
                    events.append(event_dict)
                return events
                
        except Exception as e:
            logger.error(f"Database error while retrieving events: {str(e)}")
            raise

    def get_events_by_category(self, category, user_email=None):
        """Retrieve events by category."""
        try:
            with connection.cursor() as cursor:
                if user_email:
                    cursor.execute("""
                        SELECT e.* 
                        FROM calendar_event e
                        JOIN calendar_event_calendar_category ec ON e.event_id = ec.event_id
                        JOIN calendar_category c ON ec.category_id = c.category_id
                        WHERE c.name = %s
                        AND e.user_email = %s
                        AND e.is_deleted = 0
                        ORDER BY e.start_date
                    """, [category, user_email])
                else:
                    cursor.execute("""
                        SELECT e.* 
                        FROM calendar_event e
                        JOIN calendar_event_calendar_category ec ON e.event_id = ec.event_id
                        JOIN calendar_category c ON ec.category_id = c.category_id
                        WHERE c.name = %s
                        AND e.is_deleted = 0
                        ORDER BY e.start_date
                    """, [category])
                
                columns = [col[0] for col in cursor.description]
                events = []
                for row in cursor.fetchall():
                    event_dict = dict(zip(columns, row))
                    # Convert UTC datetime fields to timezone-aware
                    if event_dict['start_date_utc']:
                        event_dict['start_date_utc'] = event_dict['start_date_utc'].replace(tzinfo=timezone.utc)
                    if event_dict['end_date_utc']:
                        event_dict['end_date_utc'] = event_dict['end_date_utc'].replace(tzinfo=timezone.utc)
                    # Get categories for this event
                    event_dict['categories'] = self.get_event_categories(event_dict['event_id'])
                    events.append(event_dict)
                return events
                
        except Exception as e:
            logger.error(f"Database error while retrieving events by category: {str(e)}")
            raise

    def mark_event_deleted(self, event_id):
        """Mark an event as deleted and clean up category relationships."""
        try:
            with connection.cursor() as cursor:
                # First remove all category relationships
                cursor.execute("""
                    DELETE FROM calendar_event_calendar_category
                    WHERE event_id = %s;
                """, [event_id])
                
                # Then mark the event as deleted
                cursor.execute("""
                    UPDATE calendar_event 
                    SET is_deleted = 1,
                        updated_at = GETDATE()
                    WHERE event_id = %s
                """, [event_id])
                logger.info(f"Marked event as deleted and removed category relationships: {event_id}")
                
                # Cleanup any orphaned categories
                self.cleanup_orphaned_categories()
                
        except Exception as e:
            logger.error(f"Database error while marking event as deleted: {str(e)}")
            raise

    def delete_category(self, category_name):
        """Delete a category and clean up event relationships."""
        try:
            with connection.cursor() as cursor:
                # First get the category ID
                cursor.execute("""
                    SELECT category_id 
                    FROM calendar_category 
                    WHERE name = %s
                """, [category_name])
                
                result = cursor.fetchone()
                if not result:
                    logger.warning(f"Category not found for deletion: {category_name}")
                    return False
                
                category_id = result[0]
                
                # Remove all relationships for this category
                cursor.execute("""
                    DELETE FROM calendar_event_calendar_category
                    WHERE category_id = %s;
                """, [category_id])
                
                # Delete the category
                cursor.execute("""
                    DELETE FROM calendar_category
                    WHERE category_id = %s;
                """, [category_id])
                
                logger.info(f"Deleted category and removed event relationships: {category_name}")
                return True
                
        except Exception as e:
            logger.error(f"Database error while deleting category: {str(e)}")
            raise

    def upsert_category(self, name):
        """Insert or update a category and return its ID."""
        try:
            with connection.cursor() as cursor:
                # Check if category exists
                cursor.execute("""
                    SELECT category_id FROM calendar_category 
                    WHERE name = %s
                """, [name])
                
                result = cursor.fetchone()
                if result:
                    category_id = result[0]
                    # Update timestamp
                    cursor.execute("""
                        UPDATE calendar_category 
                        SET updated_at = GETDATE()
                        WHERE category_id = %s
                    """, [category_id])
                else:
                    # Insert new category
                    cursor.execute("""
                        INSERT INTO calendar_category (name)
                        OUTPUT INSERTED.category_id
                        VALUES (%s)
                    """, [name])
                    category_id = cursor.fetchone()[0]
                
                return category_id
        except Exception as e:
            logger.error(f"Database error while upserting category: {str(e)}")
            raise

    def get_event_categories_set(self, event_id):
        """Get all categories for an event as a set for easy comparison."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT c.name
                    FROM calendar_category c
                    JOIN calendar_event_calendar_category ec ON c.category_id = ec.category_id
                    WHERE ec.event_id = %s
                    ORDER BY c.name
                """, [event_id])
                
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Database error while getting event categories set: {str(e)}")
            raise

    def link_event_categories(self, event_id, category_names):
        """Link an event to its categories and track changes."""
        try:
            # Get existing categories before making changes
            existing_categories = self.get_event_categories_set(event_id)
            new_categories = {name.strip() for name in category_names if name.strip()}

            # Calculate differences
            categories_added = new_categories - existing_categories
            categories_removed = existing_categories - new_categories

            with connection.cursor() as cursor:
                # First, remove existing category links
                if categories_removed:
                    cursor.execute("""
                        DELETE FROM calendar_event_calendar_category 
                        WHERE event_id = %s
                        AND category_id IN (
                            SELECT category_id 
                            FROM calendar_category 
                            WHERE name IN %s
                        )
                    """, [event_id, tuple(categories_removed)])
                    logger.info(f"Removed categories for event {event_id}: {', '.join(categories_removed)}")

                # Add new categories
                for name in categories_added:
                    category_id = self.upsert_category(name)
                    
                    # Create link
                    cursor.execute("""
                        INSERT INTO calendar_event_calendar_category (event_id, category_id)
                        VALUES (%s, %s)
                    """, [event_id, category_id])
                
                if categories_added:
                    logger.info(f"Added categories for event {event_id}: {', '.join(categories_added)}")

                # Log if categories were unchanged
                if not categories_added and not categories_removed:
                    logger.debug(f"No category changes for event {event_id}")

                # Cleanup any orphaned categories
                self.cleanup_orphaned_categories()

        except Exception as e:
            logger.error(f"Database error while linking event categories: {str(e)}")
            raise

    def get_event_categories(self, event_id):
        """Get all categories for an event."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT c.name
                    FROM calendar_category c
                    JOIN calendar_event_calendar_category ec ON c.category_id = ec.category_id
                    WHERE ec.event_id = %s
                    ORDER BY c.name
                """, [event_id])
                
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Database error while getting event categories: {str(e)}")
            raise

    def cleanup_orphaned_categories(self):
        """Remove categories that aren't linked to any events."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM calendar_category
                    OUTPUT DELETED.name
                    WHERE category_id NOT IN (
                        SELECT DISTINCT category_id 
                        FROM calendar_event_calendar_category
                    )
                """)
                deleted_categories = cursor.fetchall()
                if deleted_categories:
                    logger.info(f"Cleaned up orphaned categories: {', '.join(row[0] for row in deleted_categories)}")
        except Exception as e:
            logger.error(f"Database error while cleaning up categories: {str(e)}")
            raise 