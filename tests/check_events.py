from database import DatabaseManager
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Check events in the database."""
    try:
        db = DatabaseManager()
        
        # Get events from the last 7 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        events = db.get_events_by_date_range(start_date, end_date)
        
        logger.info(f"Found {len(events)} events in the last 7 days")
        
        # Print some details about each event
        for event in events:
            logger.info(f"Event: {event['subject']} from {event['start_date']} to {event['end_date']}")
            logger.info(f"  UTC: {event['start_date_utc']} to {event['end_date_utc']}")
            logger.info(f"  Categories: {', '.join(event['categories']) if event['categories'] else 'None'}")
            logger.info(f"  User: {event['user_name']} ({event['user_email']})")
            logger.info(f"  Description: {event['description'][:100] if event['description'] else 'None'}")
            logger.info("-" * 80)
            
    except Exception as e:
        logger.error(f"Error checking events: {str(e)}")

if __name__ == "__main__":
    main() 