import os
import sys

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from datetime import datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

# Set up more verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Check events in the database."""
    try:
        logger.debug("Initializing DatabaseManager")
        db = DatabaseManager()
        
        # Set date range for 2023
        start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2023, 12, 31, tzinfo=timezone.utc)
        
        logger.debug(f"Querying events between {start_date} and {end_date}")
        events = db.get_events_by_date_range(start_date, end_date)
        
        if not events:
            logger.warning("No events found in 2023")
            
            # Try a broader date range to see if we have any events at all
            logger.debug("Trying broader date range")
            all_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            all_end = datetime(2026, 12, 31, tzinfo=timezone.utc)
            all_events = db.get_events_by_date_range(all_start, all_end)
            logger.info(f"Total events in broader range: {len(all_events)}")
            if all_events:
                logger.info("Sample of available dates:")
                dates = sorted(set(event['start_date'].date() for event in all_events))[:5]
                for date in dates:
                    logger.info(f"  - {date}")
        else:
            logger.info(f"Found {len(events)} events between {start_date.date()} and {end_date.date()}")
            
            # Print some details about each event
            local_tz = ZoneInfo("Europe/Amsterdam")
            for event in events:
                # Convert UTC times to local timezone
                local_start = event['start_date'].astimezone(local_tz)
                local_end = event['end_date'].astimezone(local_tz)
                
                logger.info("=" * 80)
                logger.info(f"Event: {event['subject']}")
                logger.info(f"Local Time (Europe/Amsterdam): {local_start.strftime('%Y-%m-%d %H:%M')} to {local_end.strftime('%Y-%m-%d %H:%M')}")
                logger.info(f"UTC: {event['start_date'].strftime('%Y-%m-%d %H:%M')} to {event['end_date'].strftime('%Y-%m-%d %H:%M')}")
                
                # Get categories for the event
                categories = db.get_event_categories(event['event_id'])
                category_names = [cat['name'] for cat in categories]
                logger.info(f"Categories: {', '.join(category_names) if category_names else 'None'}")
                logger.info(f"User: {event['user_name']} ({event['user_email']})")
                if event['description']:
                    logger.info(f"Description: {event['description'][:100]}...")
                logger.info("=" * 80)
                logger.info("")
            
    except Exception as e:
        logger.error(f"Error checking events: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 