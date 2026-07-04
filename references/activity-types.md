# MVP portal - Activity Types and their per-type fields

Every activity has the common fields (Activity Type, Primary/Additional Technology Area, Title, Description, Private Description, Target Audience, Published Date, Role, Quantity, Activity URL). The list below adds only the fields that differ per Activity Type.

## Blog
Common fields only, plus:
- Number of Views

## Podcast
- Number of sessions
- Livestream views
- On-demand views

## Webinar/Online Training/Video/Livestream
- Number of sessions
- Livestream views
- On-demand views

## Content Feedback and Editing
Common fields only, plus:
- Number of Views

## Online Support
Common fields only, plus:
- Number of Views (people helped, forum-post views, etc.)

## Open Source/Project/Sample code/Tools
Common fields only, plus:
- Number of Views

## Product Feedback
Common fields only.

## Mentorship/Coaching
Role uses a separate enum: Organizer, Mentor, Other.
- Number of sessions

## Speaker/Presenter at Microsoft Event
- Microsoft Event: MLSA Summit, MVP Summit, RD Summit, Build, Ignite, Inspire, Other
- Number of sessions

## Speaker/Presenter at Third-party Event
- In-Person Attendees
- Number of sessions

## User Group Owner
Role uses a separate enum: Organizer, Other.
- Number of Views (or attendees)

---

## Target Audience (multi-select, applies to every type)
- IT Pro
- Developer
- Technical Decision Maker
- Business Decision Maker
- Student
- Other

## Role defaults
- Default across most types: `Author` (or `Contributor` if you weren't the primary creator).
- Mentorship/Coaching: `Organizer | Mentor | Other`.
- User Group Owner: `Organizer | Other`.
