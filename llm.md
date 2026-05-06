Doubtfire API — LLM Guide
What This Is
Doubtfire (OnTrack) is a feedback-driven Learning Management System (LMS) built with Rails + Grape. Students submit work on tasks, tutors provide feedback, and the system tracks progress toward grade targets. This document is the authoritative reference for navigating the codebase.
***Tech Stack
Layer	Technology
Language	Ruby ~3.4
Framework	Rails ~8.0
API layer	Grape + Grape-Entity + Grape-Swagger
Database	MySQL 2
Web server	Puma
Background jobs	Sidekiq + Sidekiq-Cron + Redis
Auth	Devise, LDAP, SAML 2.0, AAF, LTI 1.3
Plagiarism	MOSS, JPlag, Turn It In (TII)
PDF generation	rails-latex
File processing	RMagick, Ruby-Filemagic, CodeRay, Rubyzip
***Directory Map
app/
  api/           # All Grape API endpoint definitions
    entities/    # Entity presenters (shape of JSON responses)
    admin/       # Admin-only APIs
    submission/  # Portfolio and batch submission APIs
    similarity/  # Plagiarism detection APIs
    tii/         # Turn It In integration APIs
    feedback/    # Feedback chip APIs
    d2l_integration_api/  # Brightspace/D2L integration
  models/        # ActiveRecord models (~93 files)
    comments/    # Polymorphic comment subtypes
    feedback/    # Feedback chip models
    turn_it_in/  # TII model/action objects
    similarity/  # Plagiarism result models
    d2l/         # D2L OAuth tokens and mappings
  sidekiq/       # 28 background job workers
  services/      # Service objects (SessionTracker)
  helpers/       # Auth, file, CSV, grade, LTI helpers
  mailers/       # Email notifications
  controllers/   # Thin Rails controllers (mostly file downloads)
config/
  application.rb    # Auth method, institution, integrations config
  institution.yml   # Institution branding / policy customization
  database.yml      # MySQL connection per environment
  schedule.yml      # Sidekiq-Cron recurring job schedule
  initializers/     # Devise, Sidekiq, Swagger, D2L, TII, MIME, logging
db/migrate/         # All migrations
lib/helpers/        # Shared utility helpers
test/               # Minitest + Factory Bot test suite
***Core Domain Model
Relationships at a glance
TeachingPeriod
  └─ Unit (one course offering)
       ├─ UnitRole (User ↔ Unit with a Role: student | tutor | convenor | admin | auditor)
       ├─ TaskDefinition (task template; belongs to Unit)
       │    ├─ Task (per-student instance; belongs to Project)
       │    │    ├─ TaskComment subtypes (feedback, extension, discussion…)
       │    │    ├─ TaskSubmission (file evidence)
       │    │    ├─ OverseerAssessment (automated result)
       │    │    └─ TaskSimilarity subtypes (MOSS / JPlag / TII)
       │    ├─ LearningOutcome links
       │    ├─ OverseerStep (Docker test steps)
       │    └─ GroupSubmission (for group tasks)
       ├─ Tutorial → TutorialStream
       ├─ GroupSet → Group → GroupMembership → Project
       └─ Project (student enrollment in Unit)
            ├─ User
            ├─ TutorialEnrolment
            ├─ StaffNote / TutorNote
            └─ PortfolioEvidence
Key models
Model	Table / purpose
User	All system users; role field is global default
Role	student, tutor, convenor, admin, auditor
Unit	One course offering per teaching period
UnitRole	Joins User ↔ Unit with a role + optional tutorial
Project	One per (User, Unit); tracks grade target, progress
TaskDefinition	Reusable task template attached to a Unit
Task	Per-student task instance; holds status + extensions
TaskStatus	Enum: not started, ready for feedback, in discussion, resubmit, need help, working on it, fix and resubmit, discuss, demonstrate, complete, time exceeded, won't do
Tutorial	A class session slot (day, time, tutor)
TutorialStream	Logical grouping of tutorials
Group / GroupSet	Group task configuration and membership
GroupSubmission	Group-level submission for a group task definition
AuthToken	JWT-like session tokens with expiry
TeachingPeriod / Break	Academic calendar
Campus	Physical location attached to tutorials
LearningOutcome	Curriculum outcome; linkable to task definitions
OverseerStep	Docker-based automated test step
OverseerAssessment	Result of an automated assessment run
TiiSubmission	Turn It In submission record
FeedbackChip	Reusable feedback template text
MarkingSession	Tutor time-on-task tracking
Webcal	iCalendar feed per user
Comment subtypes (polymorphic, task_comments table)
Subtype	Purpose
TaskComment	Standard tutor/student feedback
AssessmentComment	Automated overseer output
DiscussionComment	Prompt-driven discussion thread
ExtensionComment	Extension request/response
ScormComment	SCORM activity result
TaskStatusComment	Status change record
TaskFeedbackReviewRequestComment	Student requests review
TaskDiscussedComment	Tutor marks as discussed in class
TaskCheckedInComment	Check-in marker
***Authentication & Authorization
Auth methods (configured via DF_AUTH_METHOD env var)
Method	When used
database	Default; username + password in DB via Devise
ldap	Institutional directory
saml	SAML 2.0 SSO (e.g. university IdP)
aaf	Australian Access Federation Rapid Connect
lti	LTI 1.3 deep link
Auth tokens are stored in auth_tokens. Refresh tokens live in secure cookies. AuthenticationHelpers.authenticated? validates the auth_token header/param on every request.
Authorization
RBAC via permissions class method on each model. AuthorisationHelpers module enforces it. Roles are hierarchical: admin > convenor > tutor > student (auditor is read-only). Unit-level roles (UnitRole) override the global role within a specific unit.
***API Layer
APIs live in app/api/. The root is ApiRoot (mounted in config/routes.rb). Each domain gets its own Grape Resource. Swagger docs are auto-generated at /api/swagger_doc.
Base URL pattern
/api/[version]/[resource]
***API Endpoint Reference
Authentication — authentication_api.rb
Method	Path	Description
GET	/auth/method	Returns configured auth method + institution info
POST	/auth	Login with username + password (database auth)
POST	/auth/jwt	SAML/AAF callback — exchanges SAML assertion for API token
POST	/auth/lti	LTI 1.3 authentication
GET	/auth/signout_url	Returns SSO logout redirect URL
DELETE	/auth	Sign out / invalidate token
GET	/auth/scorm	Return SCORM session token
POST	/auth/access-token	Refresh auth token
***Users — users_api.rb
Method	Path	Description
GET	/users	List all users (admin only)
POST	/users	Create a new user
GET	/users/:id	Get user by ID
PUT	/users/:id	Update user profile
GET	/users/:username	Look up user by username
GET	/users/:id/staff_list	Return staff visible to this user
***Units — units_api.rb
Method	Path	Description
GET	/units	List units for current user
POST	/units	Create a new unit
GET	/units/:id	Get unit details
PUT	/units/:id	Update unit
DELETE	/units/:id	Delete unit
POST	/units/:id/rollover	Copy unit to a new teaching period
GET	/units/:id/feedback	Tasks awaiting feedback in this unit
GET	/units/:id/tasks/inbox	Tutor inbox view
GET	/units/:id/tasks/moderation	Moderation queue
GET	/units/:id/tasks/overflow	Overflow marking queue
GET	/units/:id/grades	Download grade CSV
POST	/units/:id/students	Import students from CSV
GET	/units/:id/students	Export student list CSV
***Projects (student enrollments) — projects_api.rb
Method	Path	Description
GET	/projects	List current user's projects
POST	/projects	Enroll a student in a unit
GET	/projects/:id	Get project details
PUT	/projects/:id	Update project (grade target, enrolled status)
PUT	/projects/:id/spec_con	Apply special consideration days
***Task Definitions — task_definitions_api.rb
Method	Path	Description
GET	/units/:unit_id/task_definitions	List task definitions
POST	/units/:unit_id/task_definitions	Create task definition
GET	/units/:unit_id/task_definitions/:id	Get definition
PUT	/units/:unit_id/task_definitions/:id	Update definition
DELETE	/units/:unit_id/task_definitions/:id	Delete definition
POST	/units/:unit_id/task_definitions/csv	Bulk import from CSV
GET	/units/:unit_id/task_definitions/csv	Export definitions as CSV
POST	/units/:unit_id/task_definitions/:id/task_resources	Upload task resources
GET	/units/:unit_id/task_definitions/:id/task_resources	Download task resources
POST	/units/:unit_id/task_definitions/:id/test_parameters	Upload test parameters
***Tasks — tasks_api.rb
Method	Path	Description
GET	/tasks	Get all tasks for a unit (tutor/convenor)
PUT	/projects/:project_id/task_def_id/:task_definition_id	Update task (status, grade, portfolio flag)
GET	/projects/:project_id/task_def_id/:task_definition_id	Get task submission details
GET	/projects/:project_id/refresh_tasks/:task_definition_id	Refresh task status
POST	/tasks/:id/pin	Pin task to tutor inbox
DELETE	/tasks/:id/pin	Unpin task
PUT	/projects/:project_id/task_def_id/:task_definition_id/plan	Set planned submission date
POST	/projects/:project_id/task_def_id/:task_definition_id/submission	Upload task submission files
GET	/projects/:project_id/task_def_id/:task_definition_id/submission	Download submission
POST	/projects/:project_id/task_def_id/:task_definition_id/check_in	Record check-in
GET	/projects/:project_id/task_def_id/:task_definition_id/scorm_results	Get SCORM results
***Task Comments — task_comments_api.rb
Method	Path	Description
GET	/projects/:project_id/task_def_id/:task_definition_id/comments	List all comments for a task
POST	/projects/:project_id/task_def_id/:task_definition_id/comments	Add comment (text or file attachment)
PUT	/projects/:project_id/task_def_id/:task_definition_id/comments/:id	Edit comment
DELETE	/projects/:project_id/task_def_id/:task_definition_id/comments/:id	Delete comment
***Extensions — extension_comments_api.rb
Method	Path	Description
POST	/projects/:project_id/task_def_id/:task_definition_id/request_extension	Student requests extension
PUT	/projects/:project_id/task_def_id/:task_definition_id/assess_extension/:task_comment_id	Tutor approves/denies extension
***Discussion Comments — discussion_comments_api.rb
Method	Path	Description
POST	/projects/:project_id/task_def_id/:task_definition_id/discussion_comments	Start a discussion thread
GET	/projects/:project_id/task_def_id/:task_definition_id/comments/:task_comment_id/discussion_comment/prompt_number/:n	Get prompt for discussion
POST	/...discussion_comment/response	Submit student response
POST	/...discussion_comment/reply	Tutor reply to response
***Tutorials — tutorials_api.rb
Method	Path	Description
GET	/units/:unit_id/tutorials	List tutorials for unit
POST	/units/:unit_id/tutorials	Create tutorial
PUT	/units/:unit_id/tutorials/:id	Update tutorial
DELETE	/units/:unit_id/tutorials/:id	Delete tutorial
***Tutorial Streams — tutorial_streams_api.rb
Method	Path	Description
GET	/units/:unit_id/tutorial_streams	List streams
POST	/units/:unit_id/tutorial_streams	Create stream
PUT	/units/:unit_id/tutorial_streams/:abbrev	Update stream
DELETE	/units/:unit_id/tutorial_streams/:abbrev	Delete stream
***Tutorial Enrolments — tutorial_enrolments_api.rb
Method	Path	Description
GET	/units/:unit_id/tutorial_enrolments	List enrolments for unit
POST	/projects/:project_id/tutorial_enrolments	Enrol student in tutorial
DELETE	/projects/:project_id/tutorial_enrolments/:tutorial_id	Remove enrolment
***Group Sets & Groups — group_sets_api.rb
Method	Path	Description
POST	/units/:unit_id/group_sets	Create group set
PUT	/units/:unit_id/group_sets/:id	Update group set
DELETE	/units/:unit_id/group_sets/:id	Delete group set
GET	/units/:unit_id/group_sets/:id/groups	List groups in a set
POST	/units/:unit_id/group_sets/:id/groups	Create a group
PUT	/units/:unit_id/group_sets/:id/groups/:group_id	Update group
DELETE	/units/:unit_id/group_sets/:id/groups/:group_id	Delete group
GET	/units/:unit_id/group_sets/:id/groups/csv	Export groups as CSV
POST	/units/:unit_id/group_sets/:id/groups/csv	Import groups from CSV
POST	/units/:unit_id/group_sets/:id/groups/:group_id/members	Add member to group
DELETE	/units/:unit_id/group_sets/:id/groups/:group_id/members/:project_id	Remove member
***Learning Outcomes — learning_outcomes_api.rb
Method	Path	Description
GET	/global/outcomes	List global learning outcomes
POST	/global/outcomes	Create outcome
PUT	/global/outcomes/:id	Update outcome
DELETE	/global/outcomes/:id	Delete outcome
GET	/units/:unit_id/outcomes	Outcomes for a unit
GET	/units/:unit_id/task_definitions/:id/outcomes	Outcomes for a task definition
GET/POST	/units/:unit_id/outcomes/csv	CSV import/export
***Unit Roles — unit_roles_api.rb
Method	Path	Description
GET	/unit_roles	List roles for current user
GET	/units/:unit_id/unit_roles	Staff roles in a unit
POST	/units/:unit_id/unit_roles	Add staff to unit
PUT	/units/:unit_id/unit_roles/:id	Update role
DELETE	/units/:unit_id/unit_roles/:id	Remove staff from unit
***Teaching Periods — teaching_periods_api.rb
Method	Path	Description
GET	/teaching_periods	List all teaching periods (public)
GET	/teaching_periods/:id	Get single period
POST	/teaching_periods	Create period (admin)
PUT	/teaching_periods/:id	Update period
DELETE	/teaching_periods/:id	Delete period
***Campuses — campuses_api.rb
Method	Path	Description
GET	/campuses	List all campuses
POST	/campuses	Create campus
PUT	/campuses/:id	Update campus
DELETE	/campuses/:id	Delete campus
***Activity Types — activity_types_api.rb
Method	Path	Description
GET	/activity_types	List activity types
POST	/activity_types	Create activity type
PUT	/activity_types/:id	Update
DELETE	/activity_types/:id	Delete
***Staff & Tutor Notes — staff_notes_api.rb / tutor_notes_api.rb
Method	Path	Description
GET	/projects/:id/staff_notes	Get staff notes for a project
POST	/projects/:id/staff_notes	Add staff note
PUT	/projects/:id/staff_notes/:note_id	Update note
DELETE	/projects/:id/staff_notes/:note_id	Delete note
GET	/projects/:id/tutor_notes	Get tutor notes
POST/PUT/DELETE	/projects/:id/tutor_notes/:note_id	CRUD tutor notes
***Task Prerequisites — task_prerequisites_api.rb
Method	Path	Description
GET	/units/:unit_id/task_definitions/:id/task_prerequisites	List prerequisites for a task
POST	/units/:unit_id/task_definitions/:id/task_prerequisites	Add prerequisite
DELETE	/units/:unit_id/task_definitions/:id/task_prerequisites/:prereq_id	Remove prerequisite
***Discussion Prompts — discussion_prompts_api.rb
Method	Path	Description
GET	/units/:unit_id/task_definitions/:id/discussion_prompts	List prompts
POST	/units/:unit_id/task_definitions/:id/discussion_prompts	Create prompt
PUT	/...discussion_prompts/:prompt_id	Update prompt
DELETE	/...discussion_prompts/:prompt_id	Delete prompt
***Overseer Steps — overseer_steps_api.rb
Method	Path	Description
GET	/units/:unit_id/task_definitions/:id/overseer_steps	List steps
POST	/units/:unit_id/task_definitions/:id/overseer_steps	Create step
PUT/DELETE	/...overseer_steps/:step_id	Update / delete step
***Marking Sessions — marking_sessions_api.rb
Method	Path	Description
GET	/marking_sessions	List sessions for current user
GET	/units/:unit_id/marking_sessions	Sessions within a unit
***Test Attempts — test_attempts_api.rb
Method	Path	Description
POST	/projects/:project_id/task_def_id/:task_definition_id/test_attempts	Log a test attempt
GET	/projects/:project_id/task_def_id/:task_definition_id/test_attempts	Retrieve attempts
***Portfolio — submission/portfolio_api.rb
Method	Path	Description
POST	/projects/:id/portfolio	Trigger portfolio compilation
GET	/projects/:id/portfolio	Download portfolio PDF
POST	/projects/:id/portfolio_evidence	Add evidence to portfolio
DELETE	/projects/:id/portfolio_evidence/:evidence_id	Remove evidence
***Plagiarism / Similarity — similarity/ + tii/
Method	Path	Description
GET	/units/:id/similarity	Get similarity reports for unit
GET	/tasks/:id/similarities	Task-level similarity results
POST	/tii/webhook	Turn It In webhook callback
GET	/tii/eula	Get TII EULA
POST	/tii/eula/accept	Accept TII EULA
***Feedback Chips — feedback/
Method	Path	Description
GET	/feedback/chips	List feedback chips
POST	/feedback/chips	Create chip
PUT	/feedback/chips/:id	Update chip
DELETE	/feedback/chips/:id	Delete chip
GET	/feedback/chip_groups	List grouped chips
POST/PUT/DELETE	/feedback/chip_groups/:id	CRUD chip groups
***Webcal — webcal_api.rb
Method	Path	Description
GET	/webcal	Get webcal config for current user
PUT	/webcal	Update webcal config
DELETE	/webcal	Delete webcal
GET	/webcal/:guid.ics	Serve iCalendar feed (unauthenticated)
***D2L (Brightspace) Integration — d2l_integration_api/
Method	Path	Description
GET	/d2l/auth	Initiate D2L OAuth flow
GET	/d2l/callback	OAuth callback
POST	/d2l/sync/:unit_id	Sync enrollment from D2L
POST	/d2l/grades/:unit_id	Post grades to D2L
GET	/d2l/assessment_mappings/:unit_id	List task → D2L grade item mappings
POST/PUT/DELETE	/d2l/assessment_mappings	CRUD mappings
***Settings — settings_api.rb
Method	Path	Description
GET	/settings	Return app-level settings (institution name, auth method, features)
***Admin — admin/
Method	Path	Description
GET	/admin/users	Admin user management
POST	/admin/users/rollover	Batch rollover students
GET	/admin/overseer_images	List Docker images for automated assessment
POST/PUT/DELETE	/admin/overseer_images	Manage overseer images
***Background Jobs (Sidekiq)
All workers live in app/sidekiq/. Scheduled jobs use config/schedule.yml via sidekiq-cron.
Job	Trigger	Purpose
ImportStudentsJob	Manual / CSV upload	Bulk student import from CSV
ImportStudentsLtiJob	LTI event	Import enrollment from LTI
ImportBatchFeedbackJob	Manual	Bulk feedback import
AcceptSubmissionJob	Task submission	Process uploaded files
AcceptOverseerJobJob	Overseer event	Run Docker-based automated assessment
RefreshModerationFeedbackTimestampsJob	Scheduled	Keep moderation timestamps fresh
ImportGradesCsvJob	Manual	Import grades from CSV
D2lPostGradesJob	Manual / scheduled	Push grades to Brightspace
DownloadPortfoliosJob	Manual	Compile portfolio PDFs
DownloadSubmissionFilesJob	Manual	Package submission files
DownloadSubmissionPdfsJob	Manual	Generate PDF renderings
DownloadMarkingSessionsJob	Manual	Export marking session data
DownloadTaskAssessmentCountsCsvJob	Manual	Task assessment stats CSV
DownloadTaskCompletionCsvJob	Manual	Completion rates CSV
DownloadTasksAwaitingFeedbackCsvJob	Manual	Feedback queue CSV
DownloadUnitTutorTimesSummaryJob	Manual	Tutor time summary CSV
TiiCheckProgressJob	Scheduled	Poll Turn It In for result updates
TiiRegisterWebHookJob	Startup	Register TII webhook
TiiActionJob	Event-driven	Execute queued TII API actions
ArchiveOldUnitsJob	Scheduled	Archive units after teaching period ends
ClearAccessTokensJob	Scheduled	Remove expired auth tokens
LoginDockerJob	Scheduled	Refresh Docker registry credentials
PullDockerImageJob	Scheduled	Keep overseer Docker images current
NotifyTutorNotesJob	Scheduled	Email tutors about pending notes
***Task Status Workflow
not_started
    │
    ▼
working_on_it ──► need_help
    │
    ▼
ready_for_feedback
    │
    ▼
in_discussion ──► discuss ──► demonstrate
    │
    ▼
resubmit / fix_and_resubmit
    │
    ▼
complete
Additional terminal / exceptional states: time_exceeded, won't_do.
Extensions can push due dates out. Special consideration adds extra days to the project.
***Key Conventions
Entity presenters
Every API response shape is defined in app/api/entities/. Grape entities control which fields are exposed and can nest associations. When adding a field to a response, add it here, not in the model.
Permissions pattern
# In a model:
def self.permissions(user, other_entity)
  { create: [...roles...], read: [...], update: [...], delete: [...] }
end
AuthorisationHelpers reads this to gate API actions.
File helpers
FileHelper centralises all file upload/download logic. Task submissions are stored on disk (path configured via DF_STUDENT_WORK_DIR). MimeCheckHelpers validates file types before acceptance.
CSV pattern
Bulk operations (students, task definitions, groups) follow a consistent pattern: GET downloads the current state as CSV; POST with a CSV file imports/updates records.
API response format
Errors follow Grape's standard: { error: "message" }. Success responses are entities or arrays of entities. Pagination is not globally standardised — check individual endpoints.
***Environment Variables (key ones)
Variable	Purpose
DF_AUTH_METHOD	database | ldap | saml | aaf | lti
DF_INSTITUTION_NAME	Displayed institution name
DF_INSTITUTION_EMAIL_DOMAIN	Default email domain for new users
DF_SECRET_KEY_BASE	Rails secret key
DF_STUDENT_WORK_DIR	Root path for uploaded student files
DATABASE_URL / DB_*	MySQL connection
REDIS_URL	Redis for Sidekiq + caching
TII_API_KEY	Turn It In API credentials
D2L_CLIENT_ID / D2L_CLIENT_SECRET	Brightspace OAuth
DF_SAML_*	SAML IdP configuration
DF_AAF_*	AAF Rapid Connect config
DF_LTI_*	LTI 1.3 config
***Running Locally
# Dependencies
bundle install
# Database
rails db:create db:migrate db:seed
# Start Redis (required for Sidekiq)
redis-server
# Start Sidekiq
bundle exec sidekiq
# Start API server
bundle exec rails s
# Tests
bundle exec rails test
Swagger UI available at /api/swagger_doc when the server is running.
Docker Compose is provided for a full local stack: docker-compose up.
***Where to look for things
Question	Where to look
How is X endpoint authorised?	AuthorisationHelpers + model permissions method
What does a JSON response look like?	app/api/entities/*.rb
How does file upload work?	FileHelper + individual submission API
How is email sent?	app/mailers/
What background processing exists?	app/sidekiq/ + config/schedule.yml
How is the DB seeded?	db/seeds.rb
Where are integration credentials set?	config/application.rb + env vars
How does plagiarism work?	app/models/similarity/ + app/api/similarity/ + TII models
How does automated assessment work?	OverseerStep, OverseerAssessment, AcceptOverseerJobJob
How does D2L sync work?	app/helpers/d2l_integration.rb + D2lPostGradesJob
