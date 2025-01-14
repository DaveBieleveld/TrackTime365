import unittest
import logging
import pyodbc
from datetime import datetime, timezone, timedelta
from calendar_sync import CalendarSync
from dotenv import load_dotenv
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestDatabaseSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load environment variables
        load_dotenv()
        
        # Initialize calendar sync
        cls.calendar_sync = CalendarSync()
        
        # Set up database connection
        cls.conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={os.getenv('DB_SERVER')};"
            f"DATABASE={os.getenv('DB_NAME')};"
            f"UID={os.getenv('DB_USER')};"
            f"PWD={os.getenv('DB_PASSWORD')};"
            "TrustServerCertificate=yes;"
        )
        cls.conn = pyodbc.connect(cls.conn_str)
        cls.cursor = cls.conn.cursor()

    def setUp(self):
        # Clear the events table before each test
        self.cursor.execute("DELETE FROM calendar_event")
        self.conn.commit()

    def test_store_single_event(self):
        """Test storing a single calendar event in the database."""
        # Create a test event
        now = datetime.now(timezone.utc)
        event_data = {
            'event_id': 'test_event_001',
            'subject': 'Test Event',
            'description': 'Test Description',
            'start_date': now,
            'end_date': now + timedelta(hours=1),
            'start_date_utc': now,
            'end_date_utc': now + timedelta(hours=1),
            'category': 'Test Category',
            'user_email': 'test@example.com',
            'user_name': 'Test User',
            'last_modified': now,
            'is_deleted': False
        }
        
        # Store the event
        self.calendar_sync.db.upsert_event(event_data)
        
        # Verify the event was stored
        self.cursor.execute("SELECT * FROM calendar_event WHERE event_id = ?", 
                          event_data['event_id'])
        row = self.cursor.fetchone()
        
        self.assertIsNotNone(row, "Event was not found in database")
        self.assertEqual(row.subject, event_data['subject'])
        self.assertEqual(row.description, event_data['description'])
        self.assertEqual(row.category, event_data['category'])
        self.assertEqual(row.user_email, event_data['user_email'])
        self.assertEqual(row.user_name, event_data['user_name'])

    def test_update_existing_event(self):
        """Test updating an existing calendar event in the database."""
        # Create initial event
        now = datetime.now(timezone.utc)
        event_data = {
            'event_id': 'test_event_002',
            'subject': 'Initial Subject',
            'description': 'Initial Description',
            'start_date': now,
            'end_date': now + timedelta(hours=1),
            'start_date_utc': now,
            'end_date_utc': now + timedelta(hours=1),
            'category': 'Initial Category',
            'user_email': 'test@example.com',
            'user_name': 'Test User',
            'last_modified': now,
            'is_deleted': False
        }
        self.calendar_sync.db.upsert_event(event_data)
        
        # Update the event
        event_data['subject'] = 'Updated Subject'
        event_data['description'] = 'Updated Description'
        self.calendar_sync.db.upsert_event(event_data)
        
        # Verify the update
        self.cursor.execute("SELECT * FROM calendar_event WHERE event_id = ?", 
                          event_data['event_id'])
        row = self.cursor.fetchone()
        
        self.assertEqual(row.subject, 'Updated Subject')
        self.assertEqual(row.description, 'Updated Description')

    def test_delete_event(self):
        """Test deleting a calendar event from the database."""
        # Create an event
        now = datetime.now(timezone.utc)
        event_data = {
            'event_id': 'test_event_003',
            'subject': 'Test Event',
            'description': 'Test Description',
            'start_date': now,
            'end_date': now + timedelta(hours=1),
            'start_date_utc': now,
            'end_date_utc': now + timedelta(hours=1),
            'category': 'Test Category',
            'user_email': 'test@example.com',
            'user_name': 'Test User',
            'last_modified': now,
            'is_deleted': False
        }
        self.calendar_sync.db.upsert_event(event_data)
        
        # Delete the event
        self.calendar_sync.db.mark_event_deleted(event_data['event_id'])
        
        # Verify the event is marked as deleted
        self.cursor.execute("SELECT is_deleted FROM calendar_event WHERE event_id = ?", 
                          event_data['event_id'])
        row = self.cursor.fetchone()
        self.assertEqual(row.is_deleted, True)

    def test_bulk_event_sync(self):
        """Test syncing multiple events simultaneously."""
        # Create multiple test events
        now = datetime.now(timezone.utc)
        events = []
        for i in range(5):
            event_data = {
                'event_id': f'test_event_bulk_{i}',
                'subject': f'Bulk Test Event {i}',
                'description': f'Bulk Test Description {i}',
                'start_date': now + timedelta(days=i),
                'end_date': now + timedelta(days=i, hours=1),
                'start_date_utc': now + timedelta(days=i),
                'end_date_utc': now + timedelta(days=i, hours=1),
                'category': 'Bulk Test Category',
                'user_email': 'test@example.com',
                'user_name': 'Test User',
                'last_modified': now,
                'is_deleted': False
            }
            events.append(event_data)
        
        # Store all events
        for event in events:
            self.calendar_sync.db.upsert_event(event)
        
        # Verify all events were stored
        self.cursor.execute("SELECT COUNT(*) as count FROM calendar_event WHERE event_id LIKE 'test_event_bulk_%'")
        count = self.cursor.fetchone().count
        self.assertEqual(count, 5)

    @classmethod
    def tearDownClass(cls):
        try:
            # Clean up all test events
            cls.cursor.execute("""
                DELETE FROM calendar_event 
                WHERE event_id LIKE 'test_event%'
                OR user_email = 'test@example.com'
            """)
            cls.conn.commit()
            print("\nCleaning up test data...")  # Add visual separator
            logger.info("Successfully cleaned up all test events from database")
        except Exception as e:
            logger.error(f"Error cleaning up test events: {str(e)}")
        finally:
            # Clean up database connection
            cls.cursor.close()
            cls.conn.close()
            logger.info("Database connection closed")

if __name__ == '__main__':
    unittest.main() 