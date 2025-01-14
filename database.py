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

    def upsert_event(self, event):
        """Insert or update a calendar event."""
        try:
            with connection.cursor() as cursor:
                # Check if event exists
                cursor.execute("""
                    SELECT COUNT(*) FROM calendar_event WHERE event_id = %s
                """, [event['event_id']])
                
                exists = cursor.fetchone()[0] > 0
                
                if exists:
                    # Update existing event
                    cursor.execute("""
                        UPDATE calendar_event
                        SET user_email = %s,
                            user_name = %s,
                            subject = %s,
                            description = %s,
                            start_date = %s,
                            end_date = %s,
                            last_modified = %s,
                            is_deleted = %s,
                            updated_at = GETDATE()
                        WHERE event_id = %s
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
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                
                connection.commit()
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
                        WHERE start_date <= %s 
                        AND end_date >= %s
                        AND user_email = %s
                        AND is_deleted = 0
                    """, [end_date, start_date, user_email])
                else:
                    cursor.execute("""
                        SELECT * FROM calendar_event 
                        WHERE start_date <= %s 
                        AND end_date >= %s
                        AND is_deleted = 0
                    """, [end_date, start_date])
                
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Database error while getting events: {str(e)}")
            raise

    def mark_event_deleted(self, event_id):
        """Mark an event as deleted."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE calendar_event
                    SET is_deleted = 1,
                        updated_at = GETDATE()
                    WHERE event_id = %s
                """, [event_id])
                connection.commit()
                logger.info(f"Marked event as deleted: {event_id}")
        except Exception as e:
            logger.error(f"Database error while marking event as deleted: {str(e)}")
            raise

    def create_tables(self):
        """Create the necessary tables if they don't exist."""
        try:
            with connection.cursor() as cursor:
                # Create calendar_event table
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[calendar_event]') AND type in (N'U'))
                    BEGIN
                        CREATE TABLE [dbo].[calendar_event] (
                            [event_id] NVARCHAR(255) PRIMARY KEY,
                            [user_email] NVARCHAR(255) NOT NULL,
                            [user_name] NVARCHAR(255),
                            [subject] NVARCHAR(255),
                            [description] NVARCHAR(1000),
                            [start_date] DATETIME NOT NULL,
                            [end_date] DATETIME NOT NULL,
                            [last_modified] DATETIME NOT NULL,
                            [is_deleted] BIT NOT NULL DEFAULT 0,
                            [created_at] DATETIME NOT NULL DEFAULT GETDATE(),
                            [updated_at] DATETIME NOT NULL DEFAULT GETDATE()
                        )
                    END

                    -- Create calendar_category table if it doesn't exist
                    IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[calendar_category]') AND type in (N'U'))
                    BEGIN
                        CREATE TABLE [dbo].[calendar_category] (
                            [category_id] INT IDENTITY(1,1) PRIMARY KEY,
                            [name] NVARCHAR(255) NOT NULL UNIQUE,
                            [is_project] AS CASE WHEN name LIKE '%[[]PROJECT]%' THEN 1 ELSE 0 END PERSISTED,
                            [is_activity] AS CASE WHEN name LIKE '%[[]ACTIVITY]%' THEN 1 ELSE 0 END PERSISTED,
                            [created_at] DATETIME NOT NULL DEFAULT GETDATE(),
                            [updated_at] DATETIME NOT NULL DEFAULT GETDATE()
                        )
                    END

                    -- Create calendar_event_calendar_category junction table if it doesn't exist
                    IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[calendar_event_calendar_category]') AND type in (N'U'))
                    BEGIN
                        CREATE TABLE [dbo].[calendar_event_calendar_category] (
                            [event_id] NVARCHAR(255) NOT NULL,
                            [category_id] INT NOT NULL,
                            [created_at] DATETIME NOT NULL DEFAULT GETDATE(),
                            [updated_at] DATETIME NOT NULL DEFAULT GETDATE(),
                            CONSTRAINT [PK_calendar_event_calendar_category] PRIMARY KEY ([event_id], [category_id]),
                            CONSTRAINT [FK_calendar_event_calendar_category_event] FOREIGN KEY ([event_id]) REFERENCES [calendar_event]([event_id]),
                            CONSTRAINT [FK_calendar_event_calendar_category_category] FOREIGN KEY ([category_id]) REFERENCES [calendar_category]([category_id])
                        )

                        -- Add indexes for better query performance
                        CREATE INDEX [IX_calendar_category_name] ON [calendar_category]([name])
                        CREATE INDEX [IX_calendar_event_calendar_category_event_id] ON [calendar_event_calendar_category]([event_id])
                        CREATE INDEX [IX_calendar_event_calendar_category_category_id] ON [calendar_event_calendar_category]([category_id])
                    END
                """)
                connection.commit()
                logger.info("Tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise

    def initialize_table(self):
        """Initialize the database tables if they don't exist."""
        try:
            with connection.cursor() as cursor:
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
                    CREATE TABLE calendar_event_calendar_category (
                        event_id NVARCHAR(255) NOT NULL,
                        category_id INT NOT NULL,
                        created_at DATETIME NOT NULL DEFAULT GETDATE(),
                        updated_at DATETIME NOT NULL DEFAULT GETDATE(),
                        CONSTRAINT PK_calendar_event_calendar_category PRIMARY KEY (event_id, category_id),
                        CONSTRAINT FK_calendar_event_calendar_category_event FOREIGN KEY (event_id) REFERENCES calendar_event(event_id),
                        CONSTRAINT FK_calendar_event_calendar_category_category FOREIGN KEY (category_id) REFERENCES calendar_category(category_id)
                    )
                """)

                # Create indexes if they don't exist
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_calendar_category_name')
                    CREATE INDEX IX_calendar_category_name ON calendar_category(name)
                """)

                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_calendar_event_calendar_category_event_id')
                    CREATE INDEX IX_calendar_event_calendar_category_event_id ON calendar_event_calendar_category(event_id)
                """)

                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_calendar_event_calendar_category_category_id')
                    CREATE INDEX IX_calendar_event_calendar_category_category_id ON calendar_event_calendar_category(category_id)
                """)

                logger.info("Calendar events table initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database table: {str(e)}")
            raise

    def get_or_create_category(self, category_name):
        """Get or create a category by name."""
        with connection.cursor() as cursor:
            # Try to get existing category
            cursor.execute("""
                SELECT category_id, name, is_project, is_activity 
                FROM calendar_category 
                WHERE name = %s
            """, [category_name])
            
            row = cursor.fetchone()
            if row:
                return row[0]  # Return existing category_id
            
            # Create new category if it doesn't exist
            cursor.execute("""
                INSERT INTO calendar_category (name)
                VALUES (%s);
                SELECT SCOPE_IDENTITY();
            """, [category_name])
            
            category_id = cursor.fetchone()[0]
            connection.commit()
            return category_id

    def link_event_categories(self, event_id, category_names):
        """Link an event to its categories."""
        if not category_names:
            return
        
        with connection.cursor() as cursor:
            # First remove existing category links
            cursor.execute("""
                DELETE FROM calendar_event_calendar_category 
                WHERE event_id = %s
            """, [event_id])
            
            # Add new category links
            for name in category_names:
                category_id = self.get_or_create_category(name)
                cursor.execute("""
                    INSERT INTO calendar_event_calendar_category (event_id, category_id)
                    VALUES (%s, %s)
                """, [event_id, category_id])

    def get_event_categories(self, event_id):
        """Get all categories for an event."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.name
                FROM calendar_event_calendar_category ec
                JOIN calendar_category c ON ec.category_id = c.category_id
                WHERE ec.event_id = %s
            """, [event_id])
            
            return [row[0] for row in cursor.fetchall()] 