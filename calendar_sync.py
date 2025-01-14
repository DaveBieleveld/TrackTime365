from O365 import Account, FileSystemTokenBackend, MSGraphProtocol
from datetime import datetime, timedelta, timezone
from config import CLIENT_ID, CLIENT_SECRET, logger
from database import DatabaseManager
import os
import re
from zoneinfo import ZoneInfo
from tzlocal import get_localzone
import tzlocal.windows_tz
import urllib.request
import xml.etree.ElementTree as ET
import functools
import time

class CalendarSync:
    def __init__(self):
        self.db = DatabaseManager()
        self.credentials = (CLIENT_ID, CLIENT_SECRET)
        self.scopes = [
            'https://graph.microsoft.com/.default'  # This will request all configured application permissions
        ]
        
        # Set up token backend with tenant-specific configuration
        token_path = os.path.join(os.path.dirname(__file__), 'o365_token.txt')
        token_backend = FileSystemTokenBackend(token_path=token_path)
        self.protocol = MSGraphProtocol()
        
        # Initialize the Account with application-level auth
        self.account = Account(
            credentials=self.credentials,
            auth_flow_type='credentials',
            tenant_id='thecodecraftfoundry.onmicrosoft.com',  # Use actual tenant ID for client credentials
            token_backend=token_backend,
            protocol=self.protocol
        )
        
        # Rate limit settings
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    def _make_request_with_retry(self, endpoint, params=None):
        """Make a request with retry logic for rate limits."""
        retries = 0
        while retries < self.max_retries:
            try:
                response = self.account.connection.get(endpoint, params=params)
                if response:
                    return response
                elif response.status_code == 429:  # Rate limit exceeded
                    retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                    logger.warning(f"Rate limit exceeded. Waiting {retry_after} seconds before retry.")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                else:
                    logger.error(f"Request failed with status code: {response.status_code}")
                    return None
            except Exception as e:
                logger.error(f"Request failed: {str(e)}")
                return None
        logger.error("Max retries exceeded for request")
        return None

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def windows_to_iana(windows_tz):
        """Convert Windows timezone name to IANA timezone name using Unicode CLDR data.
        Uses caching to avoid repeated HTTP requests."""
        try:
            url = 'https://raw.githubusercontent.com/unicode-org/cldr/master/common/supplemental/windowsZones.xml'
            headers = {'User-Agent': 'Mozilla/5.0'}  # Add user agent to avoid potential blocking
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=5) as response:
                xml_data = response.read().decode('utf-8')
            
            root = ET.fromstring(xml_data)
            # Find all mapZone elements and check their attributes
            for mapping in root.findall(".//mapZone"):
                if mapping.get('other') == windows_tz and mapping.get('territory') == '001':
                    logger.debug(f"Found CLDR mapping for {windows_tz}: {mapping.get('type')}")
                    return mapping.get('type')
            
            logger.debug(f"No CLDR mapping found for {windows_tz}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch timezone mapping from Unicode CLDR: {str(e)}")
            return None

    def authenticate(self):
        """Authenticate with Office 365 using client credentials."""
        try:
            # Check if we have a valid token
            if self.account.is_authenticated:
                logger.info("Already authenticated with Office 365")
                return True

            # Authenticate with client credentials
            result = self.account.authenticate(scopes=self.scopes)
            
            if result:
                logger.info("Successfully authenticated with Office 365")
            else:
                logger.error("Authentication failed")
            return result
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    def get_users(self):
        """Get all users with mailboxes using Microsoft Graph API."""
        if not self.account.is_authenticated:
            raise Exception("Not authenticated")
        
        try:
            # Use Microsoft Graph API to get users with mail
            # Using a simpler query that just gets all users and filters locally
            query = "https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail,userPrincipalName"
            response = self.account.connection.get(query)
            
            if not response:
                raise Exception("Failed to get users")
                
            all_users = response.json().get('value', [])
            # Filter users with mail locally
            users = [user for user in all_users if user.get('mail')]
            logger.info(f"Found {len(users)} users with mailboxes")
            return users
            
        except Exception as e:
            logger.error(f"Error getting users: {str(e)}")
            raise

    def get_user_timezone(self, user_email):
        """Get the timezone setting for a specific user."""
        try:
            if not self.authenticate():
                logger.error("Not authenticated with Office 365")
                return str(get_localzone())  # Return system timezone as fallback

            # Use Microsoft Graph API to get user's mailbox settings
            endpoint = f"https://graph.microsoft.com/v1.0/users/{user_email}/mailboxSettings"
            response = self.account.connection.get(endpoint)
            
            if response:
                windows_timezone = response.json().get('timeZone', None)
                logger.info(f"Retrieved timezone {windows_timezone} for user {user_email}")
                
                if windows_timezone:
                    # Special case for W. Europe Standard Time
                    if windows_timezone == 'W. Europe Standard Time':
                        logger.info(f"Using Europe/Amsterdam for W. Europe Standard Time for user {user_email}")
                        return 'Europe/Amsterdam'
                        
                    try:
                        # First try Unicode CLDR mapping
                        iana_timezone = self.windows_to_iana(windows_timezone)
                        if iana_timezone:
                            logger.info(f"Mapped Windows timezone '{windows_timezone}' to IANA timezone '{iana_timezone}' using Unicode CLDR for user {user_email}")
                            return iana_timezone
                            
                        # Fallback to tzlocal mapping
                        iana_timezones = tzlocal.windows_tz.win_tz.get(windows_timezone)
                        if iana_timezones:
                            iana_timezone = iana_timezones[0]
                            logger.info(f"Mapped Windows timezone '{windows_timezone}' to IANA timezone '{iana_timezone}' using tzlocal for user {user_email}")
                            return iana_timezone
                    except Exception as e:
                        logger.warning(f"Failed to convert Windows timezone '{windows_timezone}' to IANA format: {str(e)}")
                
                # If conversion fails or no timezone set, use system timezone
                system_timezone = str(get_localzone())
                logger.info(f"Using system timezone {system_timezone} for user {user_email}")
                return system_timezone
            else:
                logger.warning(f"Error getting user timezone: {response.text}, using system timezone")
                return str(get_localzone())
                
        except Exception as e:
            logger.warning(f"Error getting user timezone: {str(e)}, using system timezone")
            return str(get_localzone())

    def get_calendar(self, user_email):
        """Get the default calendar for a user."""
        try:
            if not self.authenticate():
                logger.error("Not authenticated with Office 365")
                return None

            # Get the user's schedule
            schedule = self.account.schedule(resource=user_email)
            if not schedule:
                logger.error(f"Could not get schedule for user {user_email}")
                return None

            # Get the default calendar
            calendar = schedule.get_default_calendar()
            if not calendar:
                logger.error(f"Could not get calendar for user {user_email}")
                return None

            logger.info(f"Found calendar: {calendar.name} for user {user_email}")
            return calendar

        except Exception as e:
            logger.error(f"Error getting calendar for user {user_email}: {str(e)}")
            return None

    def process_event(self, event, user_email, user_name):
        """Process a single calendar event."""
        try:
            # Log the raw event data for debugging
            logger.debug(f"Processing event - Subject: {event.get('subject')}")
            logger.debug(f"Raw categories from API: {event.get('categories', [])}")

            # Validate required fields
            if not all([event.get('id'), event.get('subject')]):
                raise AttributeError("Missing required field")

            # Get start and end times (these should already be timezone-aware)
            start_str = event['start']['dateTime']
            end_str = event['end']['dateTime']
            timezone_str = event['start'].get('timeZone', 'UTC')
            
            # Parse the datetime strings and attach the timezone
            try:
                # First parse without timezone
                start_naive = datetime.fromisoformat(start_str)
                end_naive = datetime.fromisoformat(end_str)
                
                # Get the timezone from the event
                event_tz = ZoneInfo(timezone_str)
                
                # Attach event timezone
                start_dt = start_naive.replace(tzinfo=event_tz)
                end_dt = end_naive.replace(tzinfo=event_tz)
                
                # Validate dates
                if end_dt < start_dt:
                    raise ValueError("End date cannot be before start date")

                # Store the original timezone-aware datetimes and their UTC equivalents
                event_data = {
                    'event_id': event['id'],
                    'user_email': user_email,
                    'user_name': user_name,
                    'subject': event['subject'][:255] if event['subject'] else None,
                    'description': event.get('body', {}).get('content', '')[:1000],
                    'start_date': start_dt,  # Original timezone-aware datetime
                    'end_date': end_dt,      # Original timezone-aware datetime
                    'start_date_utc': start_dt.astimezone(timezone.utc),  # Convert to UTC
                    'end_date_utc': end_dt.astimezone(timezone.utc),      # Convert to UTC
                    'timezone': timezone_str,  # Store the original timezone from the event
                    'last_modified': datetime.now(timezone.utc),
                    'is_deleted': False
                }
                
                # Store event in database
                self.db.upsert_event(event_data)
                
                # Handle categories separately
                categories = event.get('categories', [])
                logger.debug(f"Linking categories for event {event['subject']}: {categories}")
                self.db.link_event_categories(event['id'], categories)
                
                # Log the categories after linking
                final_categories = self.db.get_event_categories(event['id'])
                logger.debug(f"Final categories after linking: {final_categories}")
                
                logger.info(f"{'Updated' if event['id'] else 'Inserted new'} event: {event['subject']} for user {user_email}")
                return True
                
            except Exception as e:
                logger.error(f"Error processing event dates: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Error processing event: {str(e)}")
            raise

    def sync_calendar(self):
        """Sync calendar events for all users."""
        try:
            if not self.authenticate():
                logger.error("Failed to authenticate with Office 365")
                return False

            users = self.get_users()
            if not users:
                logger.error("No users found with mailboxes")
                return False

            logger.info(f"Found {len(users)} users with mailboxes")
            total_events_synced = 0

            for user in users:
                try:
                    user_email = user['mail']
                    logger.info(f"Syncing calendar for user: {user_email}")

                    calendar = self.get_calendar(user_email)
                    if not calendar:
                        continue

                    # Get events directly using Microsoft Graph API
                    now = datetime.now(timezone.utc)
                    # Extend the sync window to 180 days before and after
                    start = (now - timedelta(days=180)).replace(microsecond=0).isoformat() + 'Z'
                    end = (now + timedelta(days=180)).replace(microsecond=0).isoformat() + 'Z'

                    # Use Microsoft Graph API to get events with retry logic
                    endpoint = f"https://graph.microsoft.com/v1.0/users/{user_email}/calendar/calendarView"
                    params = {
                        '$select': 'id,subject,body,start,end,categories,extensions,importance,organizer,recurrence,reminderMinutesBeforeStart,responseRequested,responseStatus,sensitivity,showAs,type',
                        'startDateTime': start,
                        'endDateTime': end,
                        '$orderby': 'start/dateTime',
                        '$top': 50  # Limit results per page
                    }
                    
                    all_events = []
                    while True:
                        response = self._make_request_with_retry(endpoint, params=params)
                        if not response:
                            logger.error(f"Failed to get events for user {user_email}")
                            break
                            
                        response_json = response.json()
                        events_page = response_json.get('value', [])
                        all_events.extend(events_page)
                        
                        # Check if there are more pages
                        next_link = response_json.get('@odata.nextLink')
                        if not next_link:
                            break
                            
                        # Update endpoint and params for next page
                        endpoint = next_link
                        params = {}  # Parameters are included in the next_link
                    
                    logger.debug(f"Retrieved {len(all_events)} total events for user {user_email}")
                    
                    # Log all event subjects and dates for debugging
                    for event in all_events:
                        subject = event.get('subject', 'No Subject')
                        start_time = event.get('start', {}).get('dateTime', '')
                        end_time = event.get('end', {}).get('dateTime', '')
                        categories = event.get('categories', [])
                        logger.debug(f"Event from API - Subject: {subject}, Start: {start_time}, End: {end_time}, Categories: {categories}")
                    
                    events_processed = 0
                    for event_data in all_events:
                        try:
                            if self.process_event(event_data, user_email, user['displayName']):
                                events_processed += 1
                        except Exception as e:
                            logger.error(f"Error processing event {event_data.get('subject', 'Unknown')}: {str(e)}")
                            continue
                    
                    logger.info(f"Successfully processed {events_processed} events for user {user_email}")
                    total_events_synced += events_processed
                    
                except Exception as e:
                    logger.error(f"Error syncing calendar for user {user_email}: {str(e)}")
                    continue
            
            logger.info(f"Successfully synced {total_events_synced} events")
            return True

        except Exception as e:
            logger.error(f"Error in sync_calendar: {str(e)}")
            return False

    def get_events(self, start_date=None, end_date=None, category=None, user_email=None):
        """Retrieve events based on filters."""
        try:
            if category:
                return self.db.get_events_by_category(category, user_email)
            elif start_date and end_date:
                if end_date < start_date:
                    raise ValueError("End date must be after start date")
                return self.db.get_events_by_date_range(start_date, end_date, user_email)
            else:
                raise ValueError("Must provide either date range or category")
                
        except Exception as e:
            logger.error(f"Error retrieving events: {str(e)}")
            raise 