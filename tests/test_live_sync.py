import unittest
import logging
from datetime import datetime, timedelta, timezone
from calendar_sync import CalendarSync
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestLiveSync(unittest.TestCase):
    def setUp(self):
        self.calendar_sync = CalendarSync()
    
    def tearDown(self):
        pass  # Connection is managed by DatabaseManager

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
        
        # Set up test date range centered on today
        center_date = datetime.now(timezone.utc).date()
        start_date = center_date - timedelta(days=90)
        end_date = center_date + timedelta(days=90)
        
        # Perform calendar sync
        self.assertTrue(self.calendar_sync.sync_calendar(start_date=start_date, end_date=end_date), "Calendar sync failed")
        
        # Verify events were added
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM calendar_event")
            final_count = cursor.fetchone()[0]
            
            # Get the number of events added
            events_added = final_count - self.initial_event_count
            logger.info(f"Added {events_added} new events to the database")
            
            # Get recent events for verification
            cursor.execute("""
                SELECT TOP 5 e.event_id, e.subject, e.user_email, e.start_date, e.end_date,
                    (
                        SELECT STRING_AGG(c.name, ', ')
                        FROM calendar_event_calendar_category ec
                        JOIN calendar_category c ON ec.category_id = c.category_id
                        WHERE ec.event_id = e.event_id
                    ) as categories
                FROM calendar_event e
                ORDER BY e.created_at DESC
            """)
            recent_events = cursor.fetchall()
            
            # Verify event properties
            for event in recent_events:
                event_id, subject, user_email, start_date, end_date, categories = event
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
            event_start = event['start_date']
            event_end = event['end_date']
            
            # Convert to UTC if not already
            if not event_start.tzinfo:
                event_start = event_start.replace(tzinfo=timezone.utc)
            if not event_end.tzinfo:
                event_end = event_end.replace(tzinfo=timezone.utc)
            
            self.assertLessEqual(event_start, end_date, "Event starts after query range")
            self.assertGreaterEqual(event_end, start_date, "Event ends before query range")

    def test_category_query(self):
        """Test querying events by category."""
        # First sync to ensure we have some events
        start_date = datetime.now(timezone.utc).date()
        end_date = start_date + timedelta(days=7)
        self.calendar_sync.sync_calendar(start_date=start_date, end_date=end_date)
        
        # Get all unique categories
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT c.name 
                FROM calendar_category c
                JOIN calendar_event_calendar_category ec ON c.category_id = ec.category_id
            """)
            categories = [row[0] for row in cursor.fetchall()]
        
        # Test each category
        for category in categories:
            events = self.calendar_sync.get_events(category=category)
            self.assertIsNotNone(events, f"Failed to get events for category: {category}")
            
            # Verify all events have the correct category
            for event in events:
                event_categories = self.calendar_sync.db.get_event_categories(event['event_id'])
                category_names = [cat['name'] for cat in event_categories]
                self.assertIn(category, category_names,
                            f"Event missing category: expected {category} in {category_names}")

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

if __name__ == '__main__':
    unittest.main() 