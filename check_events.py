from database import DatabaseManager
from datetime import datetime, timedelta, timezone
from config import logger

def main():
    db = DatabaseManager()
    
    # Get events for the past week
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    
    events = db.get_events_by_date_range(start_date, end_date)
    
    print(f"\nFound {len(events)} events between {start_date} and {end_date}:")
    print("-" * 80)
    
    for event in events:
        # Get categories for the event
        categories = db.get_event_categories(event['event_id'])
        category_str = ", ".join(categories) if categories else "No categories"
        
        print(f"Event: {event['subject']}")
        print(f"User: {event['user_email']}")
        print(f"Start: {event['start_date']}")
        print(f"End: {event['end_date']}")
        print(f"Categories: {category_str}")
        print("-" * 80)

if __name__ == "__main__":
    main() 