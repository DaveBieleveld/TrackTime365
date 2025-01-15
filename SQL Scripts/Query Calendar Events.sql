use track_time_365

go

select 
    e.event_id,
    e.user_email,
    e.user_name,
    e.subject,
    e.start_date AT TIME ZONE 'UTC' AT TIME ZONE  CURRENT_TIMEZONE_ID(),
    e.end_date AT TIME ZONE 'UTC' AT TIME ZONE  CURRENT_TIMEZONE_ID(),
    e.description,
    e.last_modified,
    e.is_deleted,
    e.created_at,
    e.updated_at,
    (
        SELECT 
            JSON_QUERY((
                SELECT c.name as name
                FROM [TRACK_TIME_365].[dbo].[calendar_event_calendar_category] cecc
                LEFT JOIN [TRACK_TIME_365].[dbo].[calendar_category] c 
                    ON cecc.category_id = c.category_id
                WHERE cecc.event_id = e.event_id
                FOR JSON PATH
            ))
    ) as categories
from [TRACK_TIME_365].[dbo].[calendar_event] e
where CAST(e.start_date AS DATE) = CAST(GETDATE() AS DATE)
and e.is_deleted = 0
order by e.start_date

