select
    ce.user_email,
    ce.user_name,
    CAST(ce.start_date AS DATE) as event_date,
    p.project_name,
    a.activity_name,
     SUM(etm.event_time_minute) as total_minutes,
     CAST(ROUND(SUM(etm.event_time_minute) / 60.0 / 0.25, 0) * 0.25 AS FLOAT) as total_hours
from (  select ce.event_id
        , ce.user_email
        , ce.user_name
        , ce.start_date AT TIME ZONE 'UTC' AT TIME ZONE  CURRENT_TIMEZONE_ID() as start_date
        , ce.end_date AT TIME ZONE 'UTC' AT TIME ZONE  CURRENT_TIMEZONE_ID() as end_date
        , ce.is_deleted
        from [TRACK_TIME_365].[dbo].[calendar_event] ce
        where is_deleted = 0 ) as ce 
cross apply (select event_time_minute = DATEDIFF(MINUTE, ce.start_date, ce.end_date)) as etm
outer
apply ( select project_name = ccp.name
        from  [TRACK_TIME_365].[dbo].[calendar_event_calendar_category] cecc
        join [TRACK_TIME_365].[dbo].[calendar_category] ccp 
            on ccp.category_id = cecc.category_id
            and ccp.is_project = 1
        where ce.event_id = cecc.event_id) as p
outer 
apply ( select activity_name = ccp.name
        from  [TRACK_TIME_365].[dbo].[calendar_event_calendar_category] cecc
        join [TRACK_TIME_365].[dbo].[calendar_category] ccp 
            on ccp.category_id = cecc.category_id
            and ccp.is_activity = 1
        where ce.event_id = cecc.event_id) as a        
where ce.is_deleted = 0
and p.project_name is not null -- only show events with a project
--and ce.event_id = 'AAMkAGU2ZWJiZjY1LWE1ZjktNGI4Ny05MjY4LTNkNGI4ODk4MmI0YwFRAAgI3S93ZRWAAEYAAAAAPbsEQ2mi4Uyidv0zb3k5WwcAtRS72ihN5UiQHQENYlhgbAAAAAABDQAAtRS72ihN5UiQHQENYlhgbAAAAC3-EQAAEA=='
--and CAST(ce.start_date AS DATE) = CAST(GETDATE() AS DATE)
group by
    ce.user_email,
    ce.user_name, 
    CAST(ce.start_date AS DATE),
    p.project_name,
    a.activity_name
order by
    ce.user_email,
    event_date,
    project_name,
    activity_name


    select * from [TRACK_TIME_365].[dbo].[calendar_event]
    where start_date >= '2025-01-15 00:00:00'