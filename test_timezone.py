from calendar_sync import CalendarSync
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_user_timezones():
    try:
        # Initialize CalendarSync
        calendar_sync = CalendarSync()
        
        # Authenticate
        if not calendar_sync.authenticate():
            logger.error("Failed to authenticate")
            return
            
        # Get all users
        users = calendar_sync.get_users()
        if not users:
            logger.error("No users found")
            return
            
        logger.info(f"Found {len(users)} users")
        
        # Test getting timezone for each user
        for user in users:
            user_email = user['mail']
            display_name = user['displayName']
            
            logger.info(f"\nTesting timezone for user: {display_name} ({user_email})")
            timezone = calendar_sync.get_user_timezone(user_email)
            logger.info(f"User timezone: {timezone}")
            
    except Exception as e:
        logger.error(f"Error testing user timezones: {str(e)}")

if __name__ == "__main__":
    test_user_timezones() 