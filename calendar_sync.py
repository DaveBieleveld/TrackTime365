from O365 import Account, FileSystemTokenBackend, MSGraphProtocol
from datetime import datetime, timezone, timedelta
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
import logging

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
                    
                    # Try tzlocal mapping first as it's more reliable for Windows timezones
                    try:
                        iana_timezones = tzlocal.windows_tz.win_tz.get(windows_timezone)
                        if iana_timezones:
                            iana_timezone = iana_timezones[0]
                            logger.info(f"Mapped Windows timezone '{windows_timezone}' to IANA timezone '{iana_timezone}' using tzlocal for user {user_email}")
                            return iana_timezone
                    except Exception as e:
                        logger.warning(f"Failed to map timezone using tzlocal: {str(e)}")
                        
                    # Fallback to Unicode CLDR mapping
                    try:
                        iana_timezone = self.windows_to_iana(windows_timezone)
                        if iana_timezone:
                            logger.info(f"Mapped Windows timezone '{windows_timezone}' to IANA timezone '{iana_timezone}' using Unicode CLDR for user {user_email}")
                            return iana_timezone
                    except Exception as e:
                        logger.warning(f"Failed to map timezone using CLDR: {str(e)}")
                
                # If conversion fails or no timezone set, use system timezone
                system_timezone = str(get_localzone())
                logger.info(f"Using system timezone {system_timezone} for user {user_email}")
                return system_timezone
            else:
                logger.warning(f"Error getting user timezone: {response.text if hasattr(response, 'text') else 'No response'}, using system timezone")
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

    def process_event(self, event, user_email):
        """Process a single calendar event."""
        try:
            event_id = event.get('id')
            if not event_id:
                logger.error("Event missing ID - skipping")
                return False

            # Extract event details
            event_data = {
                'event_id': event_id,
                'user_email': user_email,
                'user_name': event.get('organizer', {}).get('emailAddress', {}).get('name', ''),
                'subject': event.get('subject', ''),
                'description': event.get('body', {}).get('content', ''),
                'start_date': self._parse_date(event.get('start', {}).get('dateTime')),
                'end_date': self._parse_date(event.get('end', {}).get('dateTime')),
                'last_modified': self._parse_date(event.get('lastModifiedDateTime', datetime.now(timezone.utc).isoformat())),
                'is_deleted': False,
                'categories': event.get('categories', [])
            }

            logger.debug(f"Processing event - Subject: {event_data['subject']}")
            logger.debug(f"Raw categories from API: {event_data['categories']}")

            # Process the event in the database
            try:
                updated = self.db.upsert_event(event_data)
                if updated:
                    logger.info(f"{'Updated' if event_id else 'Inserted new'} event: {event_data['subject']} for user {user_email}")
                else:
                    logger.debug(f"No changes needed for event: {event_data['subject']}")
                return True
            except Exception as e:
                logger.error(f"Database error while processing event {event_data['subject']}: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"Error processing event: {str(e)}")
            return False

    def process_events(self, events, user_email):
        """Process a list of calendar events sequentially."""
        if not events:
            return

        success_count = 0
        total_events = len(events)
        
        for i, event in enumerate(events, 1):
            logger.info(f"Processing event {i} of {total_events}")
            if self.process_event(event, user_email):
                success_count += 1
            # Add a small delay between events to reduce database load
            if i < total_events:  # Don't sleep after the last event
                time.sleep(0.1)
        
        logger.info(f"Successfully processed {success_count} out of {total_events} events")

    def sync_calendar(self, start_date, end_date):
        """Sync calendar events for a user or all users within a date range.
        
        Args:
            start_date (date): Start date for events (inclusive).
            end_date (date): End date for events (inclusive).
            user_email (str, optional): Email of specific user to sync. If None, syncs all users.
        
        Raises:
            ValueError: If end_date is before start_date or if dates are not provided.
        """
        try:
            if not self.authenticate():
                logger.error("Not authenticated with Office 365")
                return

            # Convert datetime to date if needed
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            
            # Validate date range
            if end_date < start_date:
                raise ValueError("End date must be after start date")
            
            # Get users to process
            users = self.get_users()

            if not users:
                logger.error("No users found to process")
                return

            # Process each user's calendar
            for user in users:
                user_email = user.get('mail')
                if not user_email:
                    continue

                user_name = user.get('displayName', user_email)
                logger.info(f"Processing calendar for user: {user_email}")

                try:
                    logger.info(f"Fetching calendar events for {user_email} from {start_date} to {end_date}")

                    # Get calendar events in batches
                    events = self.get_calendar_events_batch(user_email, start_date, end_date)
                    
                    if events:
                        self.process_events(events, user_email)
                    else:
                        logger.info(f"No events found for user {user_email} in the specified time range")

                except Exception as e:
                    logger.error(f"Error processing calendar for user {user_email}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error in sync_calendar: {str(e)}")
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

    def get_calendar_events_batch(self, user_email, start_date, end_date, batch_size=20):
        """
        Get calendar events for a user using batch requests.
        
        Args:
            user_email (str): The email address of the user
            start_date (date): Start date for events (inclusive, starts at 00:00)
            end_date (date): End date for events (exclusive, ends at 00:00 the next day)
            batch_size (int): Number of events to retrieve per batch request
            
        Returns:
            list: List of calendar events, or None if there was an API error
        """
        # Get user's timezone
        user_tz = ZoneInfo(self.get_user_timezone(user_email))
        
        # Convert dates to datetime with explicit boundaries in user's timezone
        start_time = datetime.combine(start_date, datetime.min.time(), tzinfo=user_tz)
        end_time = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=user_tz)
        
        # Convert times to UTC for the API request
        start_time_utc = start_time.astimezone(timezone.utc)
        end_time_utc = end_time.astimezone(timezone.utc)
        
        start_time_str = start_time_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_time_str = end_time_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        logger.info(f"Fetching calendar events for {user_email} from {start_date} to {end_date}")
        logger.debug(f"Using UTC time range: {start_time_utc} to {end_time_utc}")
        logger.debug(f"User timezone: {user_tz}")

        select_fields = "id,subject,body,start,end,categories,extensions,importance,organizer,recurrence,reminderMinutesBeforeStart,responseRequested,responseStatus,sensitivity,showAs,type"
        base_url = f"/users/{user_email}/calendar/calendarView?$select={select_fields}&startDateTime={start_time_str}&endDateTime={end_time_str}&$orderby=start/dateTime"
        
        all_events = []
        skip = 0
        has_more = True
        
        while has_more:
            # Make a single request instead of a batch
            request = {
                'id': '1',
                'method': 'GET',
                'url': f"{base_url}&$skip={skip}&$top={batch_size}",
                'headers': {
                    'Accept': 'application/json',
                    'Prefer': 'outlook.timezone="W. Europe Standard Time"'
                }
            }
            
            # Create proper batch payload with just one request
            batch_payload = {'requests': [request]}
            
            # Make batch request
            responses = self._make_batch_request(batch_payload)
            logger.debug(f"Batch response: {responses}")
            
            if not responses:
                logger.error("No response from batch request - API error")
                return None  # Indicate an actual error occurred

            try:
                events_in_batch = []
                response = responses[0]  # Only one response since we only made one request
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
                    skip += batch_size
                    logger.info(f"Retrieved {len(events_in_batch)} events in current batch")
                    
                    # Add a small delay between batches to reduce database load
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Error processing batch response: {str(e)}")
                return None  # Indicate an actual error occurred

        total_events = len(all_events)
        if total_events == 0:
            logger.info(f"No events found for user {user_email} in the specified time range")
        else:
            logger.info(f"Retrieved total of {total_events} events for user {user_email}")
        return all_events 

    def _parse_date(self, date_str):
        """Parse date string from the API into a datetime object."""
        if not date_str:
            return None
        try:
            # Remove the trailing Z if present and parse
            date_str = date_str.rstrip('Z')
            return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing date {date_str}: {str(e)}")
            return None 