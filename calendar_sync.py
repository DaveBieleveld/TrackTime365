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
            # Use the new batch implementation
            return self.get_users_batch()
            
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

    def sync_calendar(self, user_email=None):
        """Sync calendar events for a specific user or all users."""
        try:
            users = []
            if user_email:
                users.append({'mail': user_email})
            else:
                users = self.get_users_batch()
                
            for user in users:
                if not user.get('mail'):
                    continue
                    
                logger.info(f"Syncing calendar for user: {user['mail']}")
                try:
                    events = self.get_calendar_events_batch(user['mail'])
                    if events is None:  # This indicates an actual error occurred
                        logger.error(f"Failed to get events for user {user['mail']} due to API error")
                        continue
                        
                    # Store events in database
                    self.db.store_events(events, user['mail'])
                    logger.info(f"Successfully synced {len(events)} events for user {user['mail']}")
                        
                except Exception as e:
                    logger.error(f"Error syncing calendar for user {user['mail']}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in calendar sync: {str(e)}")
            raise

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

    def _make_batch_request(self, requests):
        """Make a batch request to Microsoft Graph API."""
        try:
            if not self.authenticate():
                logger.error("Not authenticated with Office 365")
                return None

            batch_endpoint = "https://graph.microsoft.com/v1.0/$batch"
            # The requests parameter should be a list, not a dict with 'requests' key
            batch_payload = {"requests": requests} if isinstance(requests, list) else requests

            # Log the request payload for debugging
            logger.debug(f"Batch request payload: {batch_payload}")

            response = self.account.connection.post(batch_endpoint, json=batch_payload)
            if response:
                responses = response.json().get('responses', [])
                logger.debug(f"Batch response: {responses}")
                return responses
            return None

        except Exception as e:
            logger.error(f"Batch request error: {str(e)}")
            return None

    def get_users_batch(self, batch_size=20):
        """Get all users with mailboxes using batch request."""
        if not self.account.is_authenticated:
            raise Exception("Not authenticated")
        
        try:
            all_users = []
            next_link = None
            
            # Initial request URL
            base_url = "https://graph.microsoft.com/v1.0/users?$select=id,displayName,mail,userPrincipalName&$top=999"
            
            while True:
                # Use next_link if available, otherwise use base_url
                current_url = next_link if next_link else base_url
                
                # Make single request instead of batch for the main user list
                response = self.account.connection.get(current_url)
                if not response:
                    logger.error("Failed to get users response")
                    break
                
                response_data = response.json()
                users = response_data.get('value', [])
                filtered_users = [user for user in users if user.get('mail')]
                logger.debug(f"Found {len(filtered_users)} users with mail in this page")
                all_users.extend(filtered_users)
                
                # Check for next page
                next_link = response_data.get('@odata.nextLink')
                if not next_link:
                    break
            
            logger.info(f"Found {len(all_users)} users with mailboxes")
            return all_users
            
        except Exception as e:
            logger.error(f"Error getting users: {str(e)}")
            raise

    def get_calendar_events_batch(self, user_email, start_time=None, end_time=None, batch_size=20):
        """
        Get calendar events for a user using batch requests.
        
        Args:
            user_email (str): The email address of the user
            start_time (datetime): Start time for events (default: 90 days ago)
            end_time (datetime): End time for events (default: 90 days from now)
            batch_size (int): Number of events to retrieve per batch request
            
        Returns:
            list: List of calendar events, or None if there was an API error
        """
        if not start_time:
            start_time = datetime.now(timezone.utc) - timedelta(days=90)
        if not end_time:
            end_time = datetime.now(timezone.utc) + timedelta(days=90)
        
        start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_time_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        logger.info(f"Fetching calendar events for {user_email} from {start_time} to {end_time}")
        
        select_fields = "id,subject,body,start,end,categories,extensions,importance,organizer,recurrence,reminderMinutesBeforeStart,responseRequested,responseStatus,sensitivity,showAs,type"
        base_url = f"/users/{user_email}/calendar/calendarView?$select={select_fields}&startDateTime={start_time_str}&endDateTime={end_time_str}&$orderby=start/dateTime"
        
        all_events = []
        skip = 0
        has_more = True
        
        while has_more:
            batch_requests = []
            for i in range(20):  # Max 20 requests per batch
                request = {
                    'id': str(i + 1),
                    'method': 'GET',
                    'url': f"{base_url}&$skip={skip + i * batch_size}&$top={batch_size}",
                    'headers': {
                        'Accept': 'application/json',
                        'Prefer': 'outlook.timezone="UTC"'
                    }
                }
                batch_requests.append(request)
            
            # Create proper batch payload
            batch_payload = {'requests': batch_requests}
            
            # Make batch request
            responses = self._make_batch_request(batch_payload)
            logger.debug(f"Batch response: {responses}")
            
            if not responses:
                logger.error("No response from batch request - API error")
                return None  # Indicate an actual error occurred
            
            try:
                events_in_batch = []
                for response in responses:
                    if response.get('status') == 200:
                        events = response.get('body', {}).get('value', [])
                        if events:
                            events_in_batch.extend(events)
                            logger.debug(f"Added {len(events)} events from response")
                    else:
                        logger.error(f"Error in batch response: {response}")
                        return None  # Indicate an actual error occurred
                    
                if not events_in_batch:
                    if skip == 0:
                        logger.info(f"No calendar events found for {user_email} in the specified time range")
                    else:
                        logger.debug("No more events to retrieve")
                    has_more = False
                else:
                    all_events.extend(events_in_batch)
                    skip += len(batch_requests) * batch_size
                    logger.info(f"Retrieved {len(events_in_batch)} events in current batch")
                    
            except Exception as e:
                logger.error(f"Error processing batch response: {str(e)}")
                return None  # Indicate an actual error occurred
        
        total_events = len(all_events)
        if total_events == 0:
            logger.info(f"No events found for user {user_email} in the specified time range")
        else:
            logger.info(f"Retrieved total of {total_events} events for user {user_email}")
        return all_events 