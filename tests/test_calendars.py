import os
import logging
from calendar_sync import CalendarSync
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    try:
        # Initialize CalendarSync
        calendar_sync = CalendarSync()
        
        # Authenticate
        logger.info("Attempting Office 365 authentication...")
        auth_result = calendar_sync.authenticate()
        if not auth_result:
            logger.error("Authentication failed!")
            return 1
        logger.info("Authentication successful!")
        
        # Get all users
        logger.info("Getting all users...")
        users = calendar_sync.get_users()
        if not users:
            logger.error("Failed to get users")
            return 1
        
        logger.info(f"Found {len(users)} users")
        
        # Get calendar for each user
        for user in users:
            try:
                user_email = user.get('mail')
                user_name = user.get('displayName', 'Unknown')
                logger.info(f"Getting calendar for user: {user_name} ({user_email})")
                
                calendar = calendar_sync.get_calendar(user_email)
                if not calendar:
                    logger.warning(f"Failed to get calendar for user: {user_name}")
                    continue
                    
                logger.info("Successfully retrieved calendar")
                logger.info(f"Calendar Name: {calendar.get('name', 'Default')}")
                logger.info(f"Calendar ID: {calendar.get('id', 'Unknown')}")
                
                # Get events for the next 7 days
                start = datetime.now()
                end = start + timedelta(days=7)
                
                # Format dates for Graph API
                start_str = start.isoformat() + 'Z'
                end_str = end.isoformat() + 'Z'
                
                # Get events using Graph API
                events_query = f"https://graph.microsoft.com/v1.0/users/{user_email}/calendar/calendarView?startDateTime={start_str}&endDateTime={end_str}&$top=5"
                events_response = calendar_sync.account.connection.get(events_query)
                
                if not events_response:
                    logger.warning(f"Failed to get events for user: {user_name}")
                    continue
                    
                events = events_response.json().get('value', [])
                logger.info(f"Found {len(events)} events in the next 7 days for {user_name}")
                
                # Print some event details
                for event in events:
                    subject = event.get('subject', 'No Subject')
                    start_time = event.get('start', {}).get('dateTime', '')
                    end_time = event.get('end', {}).get('dateTime', '')
                    logger.info(f"Event: {subject} ({start_time} to {end_time})")
                
            except Exception as e:
                logger.error(f"Error processing user {user.get('displayName', 'Unknown')}: {str(e)}")
                continue
        
        return 0
            
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return 1

if __name__ == "__main__":
    exit(main()) 