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
        self.cursor.execute("DELETE FROM calendar_event_calendar_category")
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
            'user_email': 'test@example.com',
            'user_name': 'Test User',
            'last_modified': now,
            'is_deleted': False
        }
        
        # Store the event
        self.calendar_sync.db.upsert_event(event_data)
        
        # Add category after event is created
        category_name = 'Test Category'
        self.calendar_sync.db.get_or_create_category(category_name)
        self.calendar_sync.db.link_event_categories(event_data['event_id'], [category_name])
        
        # Verify the event was stored
        self.cursor.execute("SELECT * FROM calendar_event WHERE event_id = ?", 
                          event_data['event_id'])
        row = self.cursor.fetchone()
        
        self.assertIsNotNone(row, "Event was not found in database")
        self.assertEqual(row.subject, event_data['subject'])
        self.assertEqual(row.description, event_data['description'])
        self.assertEqual(row.user_email, event_data['user_email'])
        self.assertEqual(row.user_name, event_data['user_name'])
        
        # Verify category
        categories = self.calendar_sync.db.get_event_categories(event_data['event_id'])
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]['name'], category_name)

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
            'user_email': 'test@example.com',
            'user_name': 'Test User',
            'last_modified': now,
            'is_deleted': False
        }
        self.calendar_sync.db.upsert_event(event_data)
        
        # Add initial category
        initial_category = 'Initial Category'
        self.calendar_sync.db.get_or_create_category(initial_category)
        self.calendar_sync.db.link_event_categories(event_data['event_id'], [initial_category])
        
        # Update the event
        event_data['subject'] = 'Updated Subject'
        event_data['description'] = 'Updated Description'
        self.calendar_sync.db.upsert_event(event_data)
        
        # Update category
        new_category = 'Updated Category'
        self.calendar_sync.db.get_or_create_category(new_category)
        self.calendar_sync.db.link_event_categories(event_data['event_id'], [new_category])
        
        # Verify the update
        self.cursor.execute("SELECT * FROM calendar_event WHERE event_id = ?", 
                          event_data['event_id'])
        row = self.cursor.fetchone()
        
        self.assertEqual(row.subject, 'Updated Subject')
        self.assertEqual(row.description, 'Updated Description')
        
        # Verify updated category
        categories = self.calendar_sync.db.get_event_categories(event_data['event_id'])
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]['name'], new_category)

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
            'user_email': 'test@example.com',
            'user_name': 'Test User',
            'last_modified': now,
            'is_deleted': False
        }
        self.calendar_sync.db.upsert_event(event_data)
        
        # Add category
        category_name = 'Test Category'
        self.calendar_sync.db.get_or_create_category(category_name)
        self.calendar_sync.db.link_event_categories(event_data['event_id'], [category_name])
        
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
                'user_email': 'test@example.com',
                'user_name': 'Test User',
                'last_modified': now,
                'is_deleted': False
            }
            events.append(event_data)
        
        # Store all events and add categories
        category_name = 'Bulk Test Category'
        self.calendar_sync.db.get_or_create_category(category_name)
        for event in events:
            self.calendar_sync.db.upsert_event(event)
            self.calendar_sync.db.link_event_categories(event['event_id'], [category_name])
        
        # Verify all events were stored
        self.cursor.execute("SELECT COUNT(*) as count FROM calendar_event WHERE event_id LIKE 'test_event_bulk_%'")
        count = self.cursor.fetchone().count
        self.assertEqual(count, 5)
        
        # Verify all events have the category
        for event in events:
            categories = self.calendar_sync.db.get_event_categories(event['event_id'])
            self.assertEqual(len(categories), 1)
            self.assertEqual(categories[0]['name'], category_name)

    @classmethod
    def tearDownClass(cls):
        try:
            # Clean up all test events and their relationships
            cls.cursor.execute("""
                DELETE FROM calendar_event_calendar_category 
                WHERE event_id LIKE 'test_event%'
                OR event_id IN (
                    SELECT event_id FROM calendar_event 
                    WHERE user_email = 'test@example.com'
                )
            """)
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