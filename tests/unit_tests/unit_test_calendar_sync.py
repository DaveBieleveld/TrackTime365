import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock, call
from calendar_sync import CalendarSync
from database import DatabaseManager
from O365 import Account, MSGraphProtocol

@pytest.fixture
def mock_event():
    """Create a mock calendar event."""
    event = Mock()
    event.object_id = "test_event_1"
    event.subject = "Test Event"
    event.start = Mock()
    event.end = Mock()
    event.start.date.return_value = datetime.now().date()
    event.end.date.return_value = datetime.now().date()
    event.start.datetime = datetime.now()
    event.end.datetime = datetime.now() + timedelta(hours=1)
    event.categories = ["Test Category"]
    event.body = "Test Description"
    event.modified = datetime.now()
    return event

@pytest.fixture
def mock_user():
    """Create a mock Office 365 user."""
    user = Mock()
    user.mail = "test.user@example.com"
    user.display_name = "Test User"
    return user

@pytest.fixture
def mock_db():
    """Create a mock database manager."""
    with patch('database.DatabaseManager') as mock:
        instance = mock.return_value
        instance.initialize_table.return_value = None
        yield instance

@pytest.fixture
def calendar_sync(mock_db):
    """Create a CalendarSync instance with mocked database."""
    with patch('calendar_sync.DatabaseManager', return_value=mock_db):
        sync = CalendarSync()
        return sync

def test_authenticate_success(calendar_sync):
    """Test successful authentication."""
    with patch('calendar_sync.Account', autospec=True) as mock_account_class:
        mock_account_instance = Mock()
        type(mock_account_instance).is_authenticated = property(lambda self: False)
        mock_account_instance.authenticate.return_value = True
        mock_account_class.return_value = mock_account_instance
        calendar_sync.account = mock_account_instance
        result = calendar_sync.authenticate()
        assert result is True
        mock_account_instance.authenticate.assert_called_once_with(scopes=['https://graph.microsoft.com/.default'])

def test_authenticate_failure(calendar_sync):
    """Test failed authentication."""
    with patch('calendar_sync.Account', autospec=True) as mock_account_class:
        mock_account_instance = Mock()
        type(mock_account_instance).is_authenticated = property(lambda self: False)
        mock_account_instance.authenticate.return_value = False
        mock_account_class.return_value = mock_account_instance
        calendar_sync.account = mock_account_instance
        result = calendar_sync.authenticate()
        assert result is False
        mock_account_instance.authenticate.assert_called_once_with(scopes=['https://graph.microsoft.com/.default'])

def test_authenticate_error(calendar_sync):
    """Test authentication error handling."""
    with patch('calendar_sync.Account', autospec=True) as mock_account_class:
        mock_account_instance = Mock()
        type(mock_account_instance).is_authenticated = property(lambda self: False)
        mock_account_instance.authenticate.side_effect = Exception("API Error")
        mock_account_class.return_value = mock_account_instance
        calendar_sync.account = mock_account_instance
        result = calendar_sync.authenticate()
        assert result is False
        mock_account_instance.authenticate.assert_called_once_with(scopes=['https://graph.microsoft.com/.default'])

def test_already_authenticated(calendar_sync):
    """Test when already authenticated."""
    with patch('calendar_sync.Account', autospec=True) as mock_account_class:
        mock_account_instance = Mock()
        type(mock_account_instance).is_authenticated = property(lambda self: True)
        mock_account_class.return_value = mock_account_instance
        calendar_sync.account = mock_account_instance
        result = calendar_sync.authenticate()
        assert result is True
        mock_account_instance.authenticate.assert_not_called()

def test_mark_event_deleted(calendar_sync):
    """Test marking an event as deleted."""
    event_id = "test_event_1"
    with patch.object(calendar_sync.db, 'mark_event_deleted') as mock_delete:
        calendar_sync.db.mark_event_deleted(event_id)
        mock_delete.assert_called_once_with(event_id)

def test_get_events_by_date_range_invalid_dates(calendar_sync):
    """Test retrieving events with end date before start date."""
    start_date = datetime.now()
    end_date = start_date - timedelta(days=1)
    with pytest.raises(ValueError) as exc_info:
        calendar_sync.get_events(start_date=start_date, end_date=end_date)
    assert "End date must be after start date" in str(exc_info.value)

def test_get_events_by_category_empty_result(calendar_sync):
    """Test retrieving events by category when no events exist."""
    with patch.object(calendar_sync.db, 'get_events_by_category') as mock_get:
        mock_get.return_value = []
        events = calendar_sync.get_events(category="NonExistentCategory")
        assert len(events) == 0
        assert isinstance(events, list)

def test_get_users_success(calendar_sync):
    """Test successful retrieval of users."""
    mock_response = Mock()
    mock_response.json.return_value = {
        'value': [
            {'mail': 'user1@example.com', 'displayName': 'User 1', 'id': '1'},
            {'mail': 'user2@example.com', 'displayName': 'User 2', 'id': '2'}
        ]
    }
    
    # Mock authentication state
    type(calendar_sync.account).is_authenticated = property(lambda self: True)
    
    with patch.object(calendar_sync.account.connection, 'get', return_value=mock_response):
        users = calendar_sync.get_users()
        assert len(users) == 2
        assert users[0]['mail'] == 'user1@example.com'
        assert users[1]['displayName'] == 'User 2'

def test_get_users_empty_response(calendar_sync):
    """Test user retrieval with empty response."""
    mock_response = Mock()
    mock_response.json.return_value = {'value': []}
    
    # Mock authentication state
    type(calendar_sync.account).is_authenticated = property(lambda self: True)
    
    with patch.object(calendar_sync.account.connection, 'get', return_value=mock_response):
        users = calendar_sync.get_users()
        assert len(users) == 0
        assert isinstance(users, list)

def test_get_users_error(calendar_sync):
    """Test error handling in user retrieval."""
    # Mock authentication state
    type(calendar_sync.account).is_authenticated = property(lambda self: True)
    
    with patch.object(calendar_sync.account.connection, 'get', side_effect=Exception("API Error")):
        with pytest.raises(Exception) as exc_info:
            calendar_sync.get_users()
        assert "API Error" in str(exc_info.value)

def test_process_event_success(calendar_sync, mock_event):
    """Test successful event processing."""
    user_email = "test@example.com"
    user_name = "Test User"
    
    # Setup proper mock event dates
    now = datetime.now(timezone.utc)
    later = now + timedelta(hours=1)
    
    # Mock the start and end datetime objects
    mock_start = Mock()
    mock_end = Mock()
    mock_start.datetime = now
    mock_end.datetime = later
    
    # Configure comparison methods
    mock_start.__lt__ = lambda self, other: self.datetime < other.datetime
    mock_start.__gt__ = lambda self, other: self.datetime > other.datetime
    mock_start.__le__ = lambda self, other: self.datetime <= other.datetime
    mock_start.__ge__ = lambda self, other: self.datetime >= other.datetime
    mock_end.__lt__ = lambda self, other: self.datetime < other.datetime
    mock_end.__gt__ = lambda self, other: self.datetime > other.datetime
    mock_end.__le__ = lambda self, other: self.datetime <= other.datetime
    mock_end.__ge__ = lambda self, other: self.datetime >= other.datetime
    
    # Assign the mocked datetime objects
    mock_event.start = mock_start
    mock_event.end = mock_end
    
    with patch.object(calendar_sync.db, 'upsert_event') as mock_upsert:
        result = calendar_sync.process_event(mock_event, user_email, user_name)
        assert result is True
        mock_upsert.assert_called_once()

def test_process_event_missing_required_fields(calendar_sync):
    """Test event processing with missing required fields."""
    mock_event = Mock()
    mock_event.object_id = None  # Missing required field
    mock_event.subject = None
    
    result = calendar_sync.process_event(mock_event, "test@example.com", "Test User")
    assert result is False

def test_process_event_invalid_dates(calendar_sync, mock_event):
    """Test event processing with invalid dates."""
    now = datetime.now()
    mock_event.start.datetime = now + timedelta(hours=1)
    mock_event.end.datetime = now  # End before start
    
    result = calendar_sync.process_event(mock_event, "test@example.com", "Test User")
    assert result is False

def test_get_calendar_success(calendar_sync):
    """Test successful calendar retrieval."""
    mock_schedule = Mock()
    mock_calendar = Mock()
    mock_calendar.name = "Test Calendar"
    mock_schedule.get_default_calendar.return_value = mock_calendar
    
    with patch.object(calendar_sync.account, 'schedule', return_value=mock_schedule):
        calendar = calendar_sync.get_calendar("test@example.com")
        assert calendar is not None
        assert calendar.name == "Test Calendar"

def test_get_calendar_no_schedule(calendar_sync):
    """Test calendar retrieval with no schedule."""
    with patch.object(calendar_sync.account, 'schedule', return_value=None):
        calendar = calendar_sync.get_calendar("test@example.com")
        assert calendar is None

def test_get_calendar_no_default_calendar(calendar_sync):
    """Test calendar retrieval with no default calendar."""
    mock_schedule = Mock()
    mock_schedule.get_default_calendar.return_value = None
    
    with patch.object(calendar_sync.account, 'schedule', return_value=mock_schedule):
        calendar = calendar_sync.get_calendar("test@example.com")
        assert calendar is None

def test_get_events_missing_parameters(calendar_sync):
    """Test get_events with missing parameters."""
    with pytest.raises(ValueError) as exc_info:
        calendar_sync.get_events()
    assert "Must provide either date range or category" in str(exc_info.value)

def test_sync_calendar_authentication_failure(calendar_sync):
    """Test calendar sync with authentication failure."""
    center_date = datetime.now(timezone.utc).date()
    start_date = center_date - timedelta(days=90)
    end_date = center_date + timedelta(days=90)
    with patch.object(calendar_sync, 'authenticate', return_value=False):
        result = calendar_sync.sync_calendar(start_date=start_date, end_date=end_date)
        assert result is False

def test_sync_calendar_no_users(calendar_sync):
    """Test calendar sync with no users."""
    center_date = datetime.now(timezone.utc).date()
    start_date = center_date - timedelta(days=90)
    end_date = center_date + timedelta(days=90)
    with patch.object(calendar_sync, 'authenticate', return_value=True), \
         patch.object(calendar_sync, 'get_users', return_value=[]):
        result = calendar_sync.sync_calendar(start_date=start_date, end_date=end_date)
        assert result is False

def test_get_user_timezone_success(calendar_sync):
    """Test successful timezone retrieval."""
    mock_response = Mock()
    mock_response.json.return_value = {'timeZone': 'W. Europe Standard Time'}
    
    with patch.object(calendar_sync.account.connection, 'get', return_value=mock_response):
        timezone = calendar_sync.get_user_timezone("test@example.com")
        assert timezone == 'Europe/Amsterdam' 

def test_category_handling(calendar_sync):
    """Test the handling of categories with the new many-to-many relationship."""
    # Create a mock event with multiple categories
    mock_event = Mock()
    mock_event.object_id = "test_event_001"
    mock_event.subject = "Test Event"
    mock_event.categories = ["Work", "Important", "Meeting"]
    mock_event.start = datetime.now(timezone.utc)
    mock_event.end = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_event.body = "Test description"

    # Process the event
    result = calendar_sync.process_event(mock_event, "test@example.com", "Test User")
    assert result is True

    # Verify categories were stored correctly
    categories = calendar_sync.db.get_event_categories("test_event_001")
    assert len(categories) == 3
    assert "Work" in categories
    assert "Important" in categories
    assert "Meeting" in categories

def test_update_event_categories(calendar_sync):
    """Test updating categories for an existing event."""
    # First create an event with initial categories
    mock_event = Mock()
    mock_event.object_id = "test_event_002"
    mock_event.subject = "Test Event"
    mock_event.categories = ["Initial", "Categories"]
    mock_event.start = datetime.now(timezone.utc)
    mock_event.end = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_event.body = "Test description"

    calendar_sync.process_event(mock_event, "test@example.com", "Test User")

    # Update the event with new categories
    mock_event.categories = ["Updated", "New Category"]
    calendar_sync.process_event(mock_event, "test@example.com", "Test User")

    # Verify categories were updated
    categories = calendar_sync.db.get_event_categories("test_event_002")
    assert len(categories) == 2
    assert "Updated" in categories
    assert "New Category" in categories
    assert "Initial" not in categories

def test_empty_categories(calendar_sync):
    """Test handling of events with no categories."""
    mock_event = Mock()
    mock_event.object_id = "test_event_003"
    mock_event.subject = "Test Event"
    mock_event.categories = []
    mock_event.start = datetime.now(timezone.utc)
    mock_event.end = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_event.body = "Test description"

    calendar_sync.process_event(mock_event, "test@example.com", "Test User")

    # Verify no categories were stored
    categories = calendar_sync.db.get_event_categories("test_event_003")
    assert len(categories) == 0

def test_duplicate_categories(calendar_sync):
    """Test handling of duplicate categories."""
    mock_event = Mock()
    mock_event.object_id = "test_event_004"
    mock_event.subject = "Test Event"
    mock_event.categories = ["Work", "work", "WORK", "Meeting"]  # Different cases of same category
    mock_event.start = datetime.now(timezone.utc)
    mock_event.end = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_event.body = "Test description"

    calendar_sync.process_event(mock_event, "test@example.com", "Test User")

    # Verify duplicates were handled correctly
    categories = calendar_sync.db.get_event_categories("test_event_004")
    assert len(categories) == 2  # Should only have "Work" and "Meeting"
    work_categories = [cat for cat in categories if cat.lower() == "work"]
    assert len(work_categories) == 1  # Should only have one "Work" category 