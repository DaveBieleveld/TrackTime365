USE TRACK_TIME_365
GO

-- Drop existing foreign key constraint
IF EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_calendar_event_calendar_category_event')
BEGIN
    ALTER TABLE [dbo].[calendar_event_calendar_category]
    DROP CONSTRAINT FK_calendar_event_calendar_category_event
END

-- Recreate the foreign key with CASCADE DELETE
ALTER TABLE [dbo].[calendar_event_calendar_category]
ADD CONSTRAINT FK_calendar_event_calendar_category_event
FOREIGN KEY (event_id) 
REFERENCES [dbo].[calendar_event](event_id)
ON DELETE CASCADE; 