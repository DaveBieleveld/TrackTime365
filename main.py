import schedule
import time
from calendar_sync import CalendarSync
from config import SYNC_INTERVAL_MINUTES, logger

def sync_job():
    """Run the calendar sync job."""
    try:
        sync = CalendarSync()
        sync.sync_calendar()
    except Exception as e:
        logger.error(f"Sync job failed: {str(e)}")

def main():
    """Main entry point for the calendar sync application."""
    logger.info("Starting calendar sync application")
    
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