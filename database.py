import pyodbc
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, logger
import os
from datetime import timezone
from contextlib import contextmanager
from queue import Queue
from threading import Lock
import time

class DatabaseManager:
    def __init__(self, pool_size=5):
        self.connection_string = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD};"
            "TrustServerCertificate=yes;"
            "Encrypt=no"
        )
        self.pool_size = pool_size
        self.connection_pool = Queue(maxsize=pool_size)
        self.pool_lock = Lock()
        self._initialize_pool()
        self.initialize_table()

    def _initialize_pool(self):
        """Initialize the connection pool."""
        self.connection_pool = Queue(maxsize=self.pool_size)
        for _ in range(self.pool_size):
            try:
                conn = pyodbc.connect(self.connection_string, timeout=30)  # 30 second connection timeout
                conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.execute("SET LOCK_TIMEOUT 5000")  # 5 second lock timeout
                self.connection_pool.put(conn)
            except Exception as e:
                logger.error(f"Error initializing connection pool: {str(e)}")
                raise

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool with context management."""
        connection = None
        try:
            connection = self.connection_pool.get(timeout=30)  # Wait up to 30 seconds for a connection
            yield connection
        except Exception as e:
            logger.error(f"Error getting connection from pool: {str(e)}")
            if connection:
                try:
                    connection.rollback()
                except:
                    pass
            raise
        finally:
            if connection:
                try:
                    # Reset the connection state before returning to pool
                    connection.rollback()
                    self.connection_pool.put(connection)
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {str(e)}")
                    # If we can't return it to the pool, try to create a new one
                    try:
                        new_conn = pyodbc.connect(self.connection_string)
                        new_conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                        self.connection_pool.put(new_conn)
                    except:
                        logger.error("Failed to create replacement connection")

    def get_or_create_categories(self, category_names):
        """Get or create multiple categories in a single transaction."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("BEGIN TRANSACTION")
                    try:
                        # Sort category names to ensure consistent lock ordering
                        sorted_names = sorted(category_names)
                        values = []
                        params = []
                        for name in sorted_names:
                            values.append("(?)")
                            params.append(name)

                        # Single query to get existing categories and insert missing ones
                        query = f"""
                        WITH existing_categories AS (
                            SELECT category_id, name 
                            FROM calendar_category WITH (UPDLOCK, HOLDLOCK)
                            WHERE name IN ({','.join(['?' for _ in sorted_names])})
                        ),
                        new_categories AS (
                            INSERT INTO calendar_category (name)
                            OUTPUT 
                                INSERTED.category_id,
                                INSERTED.name
                            SELECT n.name
                            FROM (
                                VALUES {','.join(values)}
                            ) n(name)
                            WHERE NOT EXISTS (
                                SELECT 1 FROM existing_categories e 
                                WHERE e.name = n.name
                            )
                        )
                        SELECT category_id, name FROM existing_categories
                        UNION ALL
                        SELECT category_id, name FROM new_categories
                        ORDER BY name;
                        """
                        
                        cursor.execute(query, params + params)  # params twice: once for EXISTS check, once for VALUES
                        
                        # Store categories - name as key, id as value
                        category_ids = {row[1]: row[0] for row in cursor.fetchall()}  # row[0] is id, row[1] is name

                        conn.commit()
                        return category_ids
                    except Exception:
                        conn.rollback()
                        raise
        except Exception as e:
            logger.error(f"Database error while getting/creating categories: {str(e)}")
            raise

    def upsert_events_batch(self, events):
        """Insert or update multiple calendar events and their categories in a single transaction."""
        try:
            logger.debug(f"Processing batch upsert of {len(events)} events")

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET LOCK_TIMEOUT 5000")  # Reset lock timeout for this transaction
                    cursor.execute("BEGIN TRANSACTION")
                    try:
                        # Create temp tables
                        cursor.execute("""
                            CREATE TABLE #temp_events (
                                event_id NVARCHAR(255) PRIMARY KEY,
                                user_email NVARCHAR(255) NOT NULL,
                                user_name NVARCHAR(255),
                                subject NVARCHAR(255),
                                description NVARCHAR(MAX),
                                start_date DATETIME NOT NULL,
                                end_date DATETIME NOT NULL,
                                last_modified DATETIME NOT NULL,
                                is_deleted BIT NOT NULL
                            );

                            CREATE TABLE #temp_categories (
                                name NVARCHAR(255) PRIMARY KEY
                            );

                            CREATE TABLE #temp_event_categories (
                                event_id NVARCHAR(255),
                                category_name NVARCHAR(255),
                                PRIMARY KEY (event_id, category_name)
                            );
                        """)

                        # Insert into temp_events
                        event_values = []
                        event_params = []
                        for event in events:
                            event_values.append("(?, ?, ?, ?, ?, ?, ?, ?, ?)")
                            event_params.extend([
                                event['event_id'],
                                event['user_email'],
                                event['user_name'],
                                event['subject'],
                                event['description'],
                                event['start_date'],
                                event['end_date'],
                                event['last_modified'],
                                event['is_deleted']
                            ])

                        if event_values:
                            cursor.execute(f"""
                                INSERT INTO #temp_events 
                                VALUES {','.join(event_values)}
                            """, event_params)

                        # Insert into temp_categories and temp_event_categories
                        category_values = []
                        category_params = []
                        event_category_values = []
                        event_category_params = []

                        for event in events:
                            if 'categories' in event and event['categories']:
                                for category in event['categories']:
                                    category_values.append("(?)")
                                    category_params.append(category)
                                    event_category_values.append("(?, ?)")
                                    event_category_params.extend([event['event_id'], category])

                        if category_values:
                            cursor.execute(f"""
                                INSERT INTO #temp_categories 
                                SELECT DISTINCT t.name
                                FROM (VALUES {','.join(category_values)}) AS t(name)
                            """, category_params)

                        if event_category_values:
                            cursor.execute(f"""
                                INSERT INTO #temp_event_categories 
                                VALUES {','.join(event_category_values)}
                            """, event_category_params)

                        # Merge events
                        cursor.execute("""
                            MERGE calendar_event AS target
                            USING #temp_events AS source
                            ON target.event_id = source.event_id
                            WHEN MATCHED THEN
                                UPDATE SET
                                    user_email = source.user_email,
                                    user_name = source.user_name,
                                    subject = source.subject,
                                    description = source.description,
                                    start_date = source.start_date,
                                    end_date = source.end_date,
                                    last_modified = source.last_modified,
                                    is_deleted = source.is_deleted,
                                    updated_at = GETDATE()
                            WHEN NOT MATCHED THEN
                                INSERT (
                                    event_id, user_email, user_name, subject, description,
                                    start_date, end_date, last_modified, is_deleted
                                )
                                VALUES (
                                    source.event_id, source.user_email, source.user_name,
                                    source.subject, source.description, source.start_date,
                                    source.end_date, source.last_modified, source.is_deleted
                                );
                        """)

                        # Merge categories
                        cursor.execute("""
                            MERGE calendar_category AS target
                            USING #temp_categories AS source
                            ON target.name = source.name
                            WHEN NOT MATCHED THEN
                                INSERT (name)
                                VALUES (source.name);
                        """)

                        # Update event-category relationships
                        cursor.execute("""
                            -- First, delete any existing relationships that aren't in the temp table
                            DELETE ec
                            FROM calendar_event_calendar_category ec
                            INNER JOIN #temp_events te ON ec.event_id = te.event_id
                            WHERE NOT EXISTS (
                                SELECT 1 
                                FROM #temp_event_categories tec
                                INNER JOIN calendar_category cc ON cc.name = tec.category_name
                                WHERE tec.event_id = ec.event_id 
                                AND cc.category_id = ec.category_id
                            );

                            -- Then insert new relationships
                            INSERT INTO calendar_event_calendar_category (event_id, category_id)
                            SELECT DISTINCT tec.event_id, cc.category_id
                            FROM #temp_event_categories tec
                            INNER JOIN calendar_category cc ON cc.name = tec.category_name
                            WHERE NOT EXISTS (
                                SELECT 1 
                                FROM calendar_event_calendar_category ec
                                WHERE ec.event_id = tec.event_id 
                                AND ec.category_id = cc.category_id
                            );
                        """)

                        conn.commit()
                        logger.debug(f"Successfully upserted {len(events)} events")
                        return True

                    except Exception as e:
                        conn.rollback()
                        logger.error(f"Error during batch upsert: {str(e)}")
                        raise
                    finally:
                        # Cleanup temp tables
                        try:
                            cursor.execute("""
                                DROP TABLE IF EXISTS #temp_event_categories;
                                DROP TABLE IF EXISTS #temp_categories;
                                DROP TABLE IF EXISTS #temp_events;
                            """)
                        except:
                            pass  # Ignore cleanup errors

        except Exception as e:
            logger.error(f"Database error during batch upsert: {str(e)}")
            raise

    def upsert_event(self, event):
        """Insert or update a single calendar event."""
        return self.upsert_events_batch([event])

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
                            description NVARCHAR(MAX),
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
                                CONSTRAINT FK_calendar_event_calendar_category_event FOREIGN KEY (event_id) REFERENCES calendar_event(event_id) ON DELETE CASCADE,
                                CONSTRAINT FK_calendar_event_calendar_category_category FOREIGN KEY (category_id) REFERENCES calendar_category(category_id)
                            )

                            -- Add indexes for better query performance
                            CREATE INDEX IX_calendar_category_name ON calendar_category(name)
                            CREATE INDEX IX_calendar_event_calendar_category_event_id ON calendar_event_calendar_category(event_id)
                            CREATE INDEX IX_calendar_event_calendar_category_category_id ON calendar_event_calendar_category(category_id)
                        END
                    """)

                    # If not exists (SELECT * FROM sys.indexes WHERE name = 'IX_calendar_event_event_id' AND object_id = OBJECT_ID('calendar_event'))
                    # BEGIN
                    #     CREATE NONCLUSTERED INDEX IX_calendar_event_event_id ON calendar_event(event_id);
                    # END

                    conn.commit()
                    logger.info("Tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise

    def drop_tables(self):
        """Drop all tables in the correct order."""
        with pyodbc.connect(self.connection_string) as conn:
            with conn.cursor() as cursor:
                logger.info("Dropping tables...")
                cursor.execute("""
                    DROP TABLE IF EXISTS [dbo].[calendar_event_calendar_category];
                    DROP TABLE IF EXISTS [dbo].[calendar_category];
                    DROP TABLE IF EXISTS [dbo].[calendar_event];
                """)
                conn.commit()
                logger.info("Tables dropped successfully")

    def __del__(self):
        """Cleanup connections when the object is destroyed."""
        while not self.connection_pool.empty():
            try:
                conn = self.connection_pool.get_nowait()
                conn.close()
            except:
                pass 

    def get_events_by_date_range(self, start_date, end_date):
        """Get all events within a date range."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            event_id,
                            user_email,
                            user_name,
                            subject,
                            description,
                            start_date,
                            end_date,
                            last_modified,
                            is_deleted
                        FROM calendar_event WITH (NOLOCK)
                        WHERE start_date >= ? AND end_date <= ?
                        ORDER BY start_date
                    """, [start_date, end_date])
                    
                    events = []
                    for row in cursor.fetchall():
                        events.append({
                            'event_id': row[0],
                            'user_email': row[1],
                            'user_name': row[2],
                            'subject': row[3],
                            'description': row[4],
                            'start_date': row[5],
                            'end_date': row[6],
                            'last_modified': row[7],
                            'is_deleted': row[8]
                        })
                    
                    return events
        except Exception as e:
            logger.error(f"Database error while getting events by date range: {str(e)}")
            raise

    def get_event_categories(self, event_id):
        """Get all categories for a specific event."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT c.category_id, c.name
                        FROM calendar_category c WITH (NOLOCK)
                        JOIN calendar_event_calendar_category ec WITH (NOLOCK) 
                            ON c.category_id = ec.category_id
                        WHERE ec.event_id = ?
                    """, [event_id])
                    
                    return [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Database error while getting event categories: {str(e)}")
            raise 