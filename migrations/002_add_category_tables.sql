use track_time_365

go

-- Create calendar_category table
CREATE TABLE calendar_category (
    category_id INT IDENTITY(1,1) PRIMARY KEY,
    name NVARCHAR(255) NOT NULL,
    is_project BIT NOT NULL DEFAULT 0,
    is_activity BIT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME NOT NULL DEFAULT GETDATE()
)

-- Create calendar_event_calendar_category junction table
CREATE TABLE calendar_event_calendar_category (
    event_id NVARCHAR(255) NOT NULL,
    category_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_calendar_event_calendar_category PRIMARY KEY (event_id, category_id),
    CONSTRAINT FK_calendar_event_calendar_category_event FOREIGN KEY (event_id) REFERENCES calendar_event(event_id),
    CONSTRAINT FK_calendar_event_calendar_category_category FOREIGN KEY (category_id) REFERENCES calendar_category(category_id)
)

-- Add indexes for better query performance
CREATE INDEX IX_calendar_category_name ON calendar_category(name)
CREATE INDEX IX_calendar_event_calendar_category_event_id ON calendar_event_calendar_category(event_id)
CREATE INDEX IX_calendar_event_calendar_category_category_id ON calendar_event_calendar_category(category_id) 