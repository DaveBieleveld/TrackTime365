import unittest
from datetime import datetime, timedelta
from calendar_sync import CalendarSync
import logging

class TestBatchOperations(unittest.TestCase):
    def setUp(self):
        self.calendar_sync = CalendarSync()
        logging.basicConfig(level=logging.INFO)

    def test_get_users_batch(self):
        """Test batch retrieval of users"""
        users = self.calendar_sync.get_users_batch()
        self.assertIsNotNone(users)
        self.assertIsInstance(users, list)
        if users:  # If there are users in the system
            self.assertTrue(all('mail' in user for user in users))

    def test_get_calendar_events_batch(self):
        """Test batch retrieval of calendar events"""
        # First get a user
        users = self.calendar_sync.get_users_batch()
        if not users:
            self.skipTest("No users available for testing")

        test_user = users[0]['mail']
        
        # Test with date range
        start_time = datetime.now() - timedelta(days=7)
        end_time = datetime.now() + timedelta(days=7)
        
        events = self.calendar_sync.get_calendar_events_batch(
            test_user,
            start_time=start_time,
            end_time=end_time
        )
        
        self.assertIsNotNone(events)
        self.assertIsInstance(events, list)
        
        # Test without date range
        events_no_range = self.calendar_sync.get_calendar_events_batch(test_user)
        self.assertIsNotNone(events_no_range)
        self.assertIsInstance(events_no_range, list)

if __name__ == '__main__':
    unittest.main() 