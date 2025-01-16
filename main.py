import schedule
import time
import argparse
from datetime import datetime, date, timedelta
from calendar_sync import CalendarSync
from config import SYNC_INTERVAL_MINUTES, logger

def sync_job(base_date=None):
    """Run the calendar sync job.
    
    Args:
        base_date (date, optional): Base date to sync calendar events from. If provided,
            uses this as the center of the 180-day window. If not provided, uses current date.
    """
    try:
        sync = CalendarSync()
        # If base_date is provided, use it as center, otherwise use current date
        center_date = base_date or date.today()
        start_date = center_date - timedelta(days=90)
        end_date = center_date + timedelta(days=90)
        
        logger.info(f"Syncing calendar from {start_date} to {end_date}")
        sync.sync_calendar(start_date=start_date, end_date=end_date)
    except Exception as e:
        logger.error(f"Sync job failed: {str(e)}")

def parse_date(date_str):
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("Date must be in YYYY-MM-DD format")

def main():
    """Main entry point for the calendar sync application."""
    parser = argparse.ArgumentParser(description="Calendar sync application")
    parser.add_argument(
        "--date",
        type=parse_date,
        help="Base date for calendar sync in YYYY-MM-DD format. If provided, syncs a 180-day window centered on this date and exits.",
        default=None
    )
    
    args = parser.parse_args()
    
    if args.date:
        # If date is provided, do a single sync and exit
        logger.info(f"Starting one-time calendar sync centered on date: {args.date}")
        sync_job(args.date)
        logger.info("One-time sync completed")
        return
    
    # If no date provided, run continuous sync with current date
    logger.info("Starting continuous calendar sync application")
    
    # Run initial sync
    sync_job()
    
    # Schedule periodic sync
    schedule.every(SYNC_INTERVAL_MINUTES).minutes.do(sync_job)
    
    logger.info(f"Scheduled sync job to run every {SYNC_INTERVAL_MINUTES} minutes")
    
    # Keep the script running
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            # Wait before retrying
            time.sleep(60)

if __name__ == "__main__":
    main() 