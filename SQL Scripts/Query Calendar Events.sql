use track_time_365

go

DECLARE @StartDate DATETIME = '2025-01-01'
DECLARE @EndDate DATETIME = '2025-01-31'

select 
    e.event_id,
    e.user_email,
    e.user_name,
    e.subject,
    e.start_date,
    e.end_date,
    e.description,
    e.last_modified,
    e.is_deleted,
    e.created_at,
    e.updated_at,
    (
        SELECT 
            JSON_QUERY((
                SELECT c.name as name
                FROM [TRACK_TIME_365].[dbo].[calendar_event_calendar_category] ec2
                LEFT JOIN [TRACK_TIME_365].[dbo].[calendar_category] c 
                    ON ec2.category_id = c.category_id
                WHERE ec2.event_id = e.event_id
                FOR JSON PATH
            ))
    ) as categories
from [TRACK_TIME_365].[dbo].[calendar_event] e
-- where e.start_date <= @EndDate
-- and e.end_date >= @StartDate
-- and e.is_deleted = 0
order by e.start_date


