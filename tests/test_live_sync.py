import unittest
import logging
from datetime import datetime, timedelta, timezone
from calendar_sync import CalendarSync
from dotenv import load_dotenv
from django.db import connection
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestLiveCalendarSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load environment variables
        load_dotenv()
        
        # Initialize calendar sync
        cls.calendar_sync = CalendarSync()
        
        # Get initial event count
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM calendar_event")
            cls.initial_event_count = cursor.fetchone()[0]
            logger.info(f"Initial event count: {cls.initial_event_count}")

    def test_authentication(self):
        """Test authentication with Office 365."""
        self.assertTrue(self.calendar_sync.authenticate(), "Failed to authenticate with Office 365")
        logger.info("Successfully authenticated with Office 365")

    def test_get_users(self):
        """Test retrieving users with mailboxes."""
        users = self.calendar_sync.get_users()
        self.assertIsNotNone(users, "Failed to get users")
        self.assertGreater(len(users), 0, "No users found with mailboxes")
        
        # Verify user properties
        for user in users:
            self.assertIn('mail', user, "User missing email address")
            self.assertIn('displayName', user, "User missing display name")
            self.assertIn('id', user, "User missing ID")

    def test_sync_calendar(self):
        """Test live calendar sync with Office 365."""
        # Authenticate with Office 365
        self.assertTrue(self.calendar_sync.authenticate(), "Failed to authenticate with Office 365")
        
        # Perform calendar sync
        self.assertTrue(self.calendar_sync.sync_calendar(), "Calendar sync failed")
        
        # Verify events were added
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM calendar_event")
            final_count = cursor.fetchone()[0]
            
            # Get the number of events added
            events_added = final_count - self.initial_event_count
            logger.info(f"Added {events_added} new events to the database")
            
            # Get recent events for verification
            cursor.execute("""
                SELECT TOP 5 event_id, subject, user_email, start_date_utc, end_date_utc, category 
                FROM calendar_event 
                ORDER BY created_at DESC
            """)
            recent_events = cursor.fetchall()
            
            # Verify event properties
            for event in recent_events:
                event_id, subject, user_email, start_date, end_date, category = event
                self.assertIsNotNone(event_id, "Event ID is missing")
                self.assertIsNotNone(subject, "Event subject is missing")
                self.assertIsNotNone(user_email, "User email is missing")
                self.assertIsNotNone(start_date, "Start date is missing")
                self.assertIsNotNone(end_date, "End date is missing")
                self.assertGreater(end_date, start_date, "End date must be after start date")

    def test_date_range_query(self):
        """Test querying events within a specific date range."""
        # Set up test date range
        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc) + timedelta(days=1)
        
        # Get events in range
        events = self.calendar_sync.get_events(start_date=start_date, end_date=end_date)
        self.assertIsNotNone(events, "Failed to get events in date range")
        
        # Verify event dates are within range
        for event in events:
            # Ensure event dates are timezone-aware by converting to UTC if they aren't already
            event_start = event['start_date_utc'] if isinstance(event['start_date_utc'], datetime) else datetime.fromisoformat(event['start_date_utc']).replace(tzinfo=timezone.utc)
            event_end = event['end_date_utc'] if isinstance(event['end_date_utc'], datetime) else datetime.fromisoformat(event['end_date_utc']).replace(tzinfo=timezone.utc)
            
            self.assertGreaterEqual(event_start, start_date, "Event starts before query range")
            self.assertLessEqual(event_end, end_date, "Event ends after query range")

    def test_category_query(self):
        """Test querying events by category."""
        # First sync to ensure we have some events
        self.calendar_sync.sync_calendar()
        
        # Get all unique categories
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT category FROM calendar_event WHERE category IS NOT NULL")
            categories = [row[0] for row in cursor.fetchall()]
        
        # Test each category
        for category in categories:
            events = self.calendar_sync.get_events(category=category)
            self.assertIsNotNone(events, f"Failed to get events for category: {category}")
            
            # Verify all events have the correct category
            for event in events:
                self.assertEqual(event['category'], category, 
                               f"Event category mismatch: expected {category}, got {event['category']}")

    def test_error_handling(self):
        """Test error handling for invalid queries."""
        # Test invalid date range
        end_date = datetime.now(timezone.utc) - timedelta(days=1)
        start_date = end_date + timedelta(days=1)
        
        with self.assertRaises(ValueError):
            self.calendar_sync.get_events(start_date=start_date, end_date=end_date)
        
        # Test missing parameters
        with self.assertRaises(ValueError):
            self.calendar_sync.get_events()

    @classmethod
    def tearDownClass(cls):
        # No need to close connection as Django manages it
        pass

if __name__ == '__main__':
    unittest.main() 