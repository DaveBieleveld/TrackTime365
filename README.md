# TrackTime365

A Python application that syncs Outlook calendar events from an Office 365 account to a SQL Server database, with support for project and activity tracking.

## Features

- Authenticates with Office 365 using client credentials
- Syncs calendar events to SQL Server database
- Handles event updates and deletions
- Supports querying events by date range and category
- Handles recurring events with a 5-year range (past and future)
- Project and activity time tracking
- Category management with project and activity designations
- Many-to-many relationships between events and categories
- Configurable sync interval
- Comprehensive logging with rotation
- Unit tests for core functionality
- Automatic database table creation
- Time aggregation and reporting capabilities
- Efficient batch operations for users and calendar events
- Robust timezone handling:
  - Windows to IANA timezone conversion
  - Unicode CLDR data integration
  - Local timezone detection and fallback

## Prerequisites

- Python 3.8 or higher
- SQL Server instance
- Office 365 account with appropriate permissions
- ODBC Driver 18 for SQL Server

## Getting Office 365 Credentials

To obtain the `CLIENT_ID` and `CLIENT_SECRET` for Office 365 authentication:

1. Go to the [Azure Portal](https://portal.azure.com)
2. Sign in with your Office 365 administrator account
3. Navigate to "Azure Active Directory" > "App registrations"
4. Click "New registration"
5. Fill in the registration form:
   - Name: "Calendar Sync App" (or your preferred name)
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: Leave blank (we're using client credentials)
6. Click "Register"
7. After registration, note down the following:
   - Application (client) ID: This is your `CLIENT_ID`
   - Directory (tenant) ID: You might need this for troubleshooting

8. Create a client secret:
   - Go to "Certificates & secrets"
   - Click "New client secret"
   - Add a description and choose an expiration
   - Click "Add"
   - **IMPORTANT**: Copy the secret value immediately - this is your `CLIENT_SECRET`
     You won't be able to see it again after leaving the page

9. Configure API permissions:
   - Go to "API permissions"
   - Click "Add a permission"
   - Choose "Microsoft Graph"
   - Select "Application permissions"
   - Search for and select:
     - `Calendars.Read`: Allows reading calendar events
     - `Calendars.Read.All`: Allows reading all calendar events in the organization
     - `User.Read.All`: Required for accessing user mailboxes and listing users
     - `MailboxSettings.Read`: Required for accessing user timezone settings
   - Click "Add permissions"
   - Click "Grant admin consent" and confirm

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd TrackTime365
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

5. Update the `.env` file with your credentials:
```env
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
DB_SERVER=your_server
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password
LOG_LEVEL=INFO
SYNC_INTERVAL_MINUTES=15
LOG_RETENTION_DAYS=7
```

## Usage

1. Start the sync process:
```bash
python main.py
```

The application will:

- Create the required database tables if they don't exist
- Perform an initial sync of calendar events
- Schedule periodic syncs based on the configured interval
- Log activities to the `logs` directory

## Testing

Run the test suite:
```bash
pytest
```

## Project Structure

```
.
├── README.md
├── requirements.txt
├── .env.example
├── main.py
├── config.py
├── database.py
├── calendar_sync.py
├── SQL Scripts/
│   ├── Query Calendar Events.sql
│   ├── drop tables.sql
│   └── enable_cascade_delete.sql
└── tests/
    ├── unit_tests/
    │   └── unit_test_calendar_sync.py
    ├── test_live_sync.py
    ├── test_batch_operations.py
    └── test_database_sync.py
```

## Technical Details

### Database Operations

- Efficient batch processing using temporary tables
- Transaction management with proper rollback handling
- Cascade delete support for related records
- Optimized queries for event retrieval and updates

### Error Handling

- Comprehensive error logging with stack traces
- Transaction rollback on failures
- Automatic retry for transient errors
- Detailed debug logging for troubleshooting

### Timezone Management

- Automatic Windows to IANA timezone conversion
- Handles timezone-aware datetime objects throughout
- Fallback to system timezone when needed
- Proper UTC conversion for database storage

### Testing Coverage

- Unit tests for core functionality
- Live sync integration tests
- Database operation tests
- Batch processing tests
- Error handling verification

## Troubleshooting

1. Authentication Issues:

   - Verify client credentials in `.env`
   - Check Office 365 permissions
   - Review authentication logs

2. Database Issues:

   - Verify connection string
   - Check SQL Server credentials
   - Ensure ODBC driver is installed
   - Review SQL error logs

3. Sync Issues:

   - Check log files for errors
   - Verify network connectivity
   - Check event processing logs
   - Review database transaction logs

## Database Schema

The application uses the following main tables:

- `calendar_event`: Stores event details and metadata
- `calendar_category`: Manages categories (projects/activities)
- `calendar_event_calendar_category`: Handles many-to-many relationships

## Future Improvements

1. Performance Enhancements:

   - Implement connection pooling
   - Add caching layer
   - Optimize batch sizes
   - Add parallel processing

2. Security Enhancements:

   - Add rate limiting
   - Enhance audit logging
   - Strengthen access controls

3. Monitoring:

   - Add performance metrics
   - Implement resource monitoring
   - Add alert mechanisms

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
