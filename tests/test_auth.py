from dotenv import load_dotenv
from calendar_sync import CalendarSync
import sys

def main():
    # Load environment variables
    load_dotenv(override=True)
    
    # Create calendar sync instance
    sync = CalendarSync()
    
    print('Attempting Office 365 authentication...')
    try:
        result = sync.authenticate()
        print('Authentication successful!' if result else 'Authentication failed')
        return 0 if result else 1
    except Exception as e:
        print(f'Error during authentication: {str(e)}')
        return 1

if __name__ == '__main__':
    sys.exit(main()) 