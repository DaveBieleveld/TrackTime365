use track_time_365

go

-- SELECT e.[event_id]
--       ,e.[user_email]
--       ,e.[user_name]
--       ,e.[subject]
--       ,e.[start_date]
--       ,e.[end_date]
--       ,e.[start_date_utc]
--       ,e.[end_date_utc]
--       ,e.[description]
--       ,e.[last_modified]
--       ,e.[is_deleted]
--       ,e.[created_at]
--       ,e.[updated_at]
--       ,(
--         SELECT 
--             '[' + STRING_AGG(CONCAT('"', c.name, '"'), ',') + ']'
--         FROM [TRACK_TIME_365].[dbo].[calendar_event_calendar_category] ec2
--         LEFT JOIN [TRACK_TIME_365].[dbo].[calendar_category] c 
--             ON ec2.category_id = c.category_id
--         WHERE ec2.event_id = e.event_id
--     ) as categories
--   FROM [TRACK_TIME_365].[dbo].[calendar_event] e

/*
  DROP TABLE IF EXISTS [TRACK_TIME_365].[dbo].[calendar_event_calendar_category];
  DROP TABLE IF EXISTS [TRACK_TIME_365].[dbo].[calendar_category];
  DROP TABLE IF EXISTS [TRACK_TIME_365].[dbo].[calendar_event];
*/

select 
    e.*,
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

select 
    ce.user_email,
    ce.user_name,
    CAST(ce.start_date AS DATE) as event_date,
    ccp.name as project_name,
    cca.name as activity_name,
    SUM(DATEDIFF(MINUTE, ce.start_date, ce.end_date)) as total_minutes,
    ROUND(SUM(DATEDIFF(MINUTE, ce.start_date, ce.end_date)) / 60.0 / 0.25, 0) * 0.25 as total_hours
from [TRACK_TIME_365].[dbo].[calendar_event] ce
join [TRACK_TIME_365].[dbo].[calendar_event_calendar_category] cecc
    on ce.event_id = cecc.event_id
join [TRACK_TIME_365].[dbo].[calendar_category] ccp 
    on cecc.category_id = ccp.category_id
    and ccp.is_project = 1
left join [TRACK_TIME_365].[dbo].[calendar_category] cca
    on cecc.category_id = cca.category_id 
    and cca.is_activity = 1
where ce.is_deleted = 0
group by
    ce.user_email,
    ce.user_name, 
    CAST(ce.start_date AS DATE),
    ccp.name,
    cca.name
order by
    ce.user_email,
    event_date,
    project_name,
    activity_name


