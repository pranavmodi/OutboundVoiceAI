🧩 AI Cancellation Backfill Agent — Feature Specification


By Danny Rackow

May 14, 2026
For developers, QA, and PMs — full spec for the Cancellation Backfill Agent built on the MediFlow 360 outbound AI platform.
Version: 1.0 | Date: Thursday, May 14th, 2026 | Owner: Danny Rackow
Companion docs: Product Bible v1.4.1 · Entity & Data Dictionary v1.1
📌 Purpose

This document specifies the Cancellation Backfill Agent — an outbound AI agent that detects eligible appointment cancellations and automatically contacts later-scheduled patients to offer the freed slot. It is scoped to developers building the feature, QA writing test cases, and PMs tracking scope.
This agent must be implemented inside the existing outbound AI platform, not as a standalone service or separate workflow.
🎯 Business Objective

When a patient cancels with sufficient notice, a usable exam slot goes to waste unless staff manually work the phones. This agent automates that outreach — matching the open slot to already-scheduled patients who need the same exam at the same facility, contacting them in controlled waves, and booking the first confirmed responder.
Expected outcomes:
Higher facility slot utilization on canceled appointments
Reduced manual outreach burden on staff
Earlier patient access to scheduled care
All AI outreach operations visible on one admin plane
🔭 Scope

In Scope

Detect appointment cancellations eligible for backfill
Create and manage a backfill campaign per canceled slot
Select and rank matching candidates by defined rules
Contact candidates via SMS and AI calling in configurable waves
Reuse existing outbound AI holiday, quiet-hour, and calling-hour enforcement
Log all actions through the shared outbound AI logging framework
Surface campaigns and settings in the existing outbound AI admin UI
Support per-agent configuration independent of other agents
Out of Scope

Temporary slot holding
Overbooking logic
Travel-time or distance estimation
Prep/instruction compatibility checks beyond CPT matching
Cross-facility substitution
Human scheduler approval gates
⚡ Trigger Rules

A backfill campaign is created when all of the following are true:
Appointment status changes to Canceled
Cancellation timestamp is ≥ 24 hours before exam start datetime
Slot is still available to be reused
No active or completed backfill campaign already exists for the canceled appointment
⚠️ If cancellation occurs inside 24 hours of the exam, the system does nothing. No campaign is created.
Examples:
Exam Time
Canceled At
Gap
Result
May 5 @ 5:00 PM
May 4 @ 2:00 PM
27 hours
✅ Eligible
May 5 @ 5:00 PM
May 5 @ 8:00 AM
9 hours
❌ Not eligible
The 24-hour threshold is configurable per agent settings. Default is 24 hours.
👥 Candidate Selection

Required Match Criteria

A patient is eligible as a candidate if all of the following are true:
Same facility as the canceled appointment
Same CPT code as the canceled appointment
Appointment status is currently scheduled
Patient has valid contact info for the configured outreach channel(s)
Exclusions

Exclude a candidate if any of the following apply:
Exclusion
Reason
Patient has a no-show flag
Reliability risk
Appointment is canceled, completed, or closed
Not reschedulable
Patient already contacted by this campaign
Prevents duplicate outreach
Patient has opted out of SMS
Legal/consent requirement
Patient has no callable phone number
Cannot reach via voice
Patient's current appointment is the same as the canceled slot
No action needed
Patient is suppressed by existing outbound communication rules
Shared suppression enforcement
Ranking

Sort eligible candidates by:
Scheduled appointment date — farthest out first (primary)
Lowest AppointmentId (tie-breaker — confirm with Engineering)
Ranking must be deterministic. Persist RankOrder on each BackfillCandidate row at selection time.
📡 Outreach Strategy

Outreach is wave-based. The system must not contact one patient and wait, and must not blast all candidates at once.
⚠️ No temporary hold exists. The system must never present the slot as guaranteed in any outreach.
Default Wave Pattern

Wave 1
Send SMS to top 3 candidates
Wait 10 minutes
Wave 2 (if slot still open)
AI call top 1–2 non-responders from Wave 1
Send SMS to next 3 candidates
Wait 10 minutes
Wave 3 (if slot still open)
AI call next 1–2 eligible non-responders
Send SMS to next 3 candidates
Wait 10 minutes
Stop Conditions

Stop outreach immediately when any of the following occur:
Slot is filled
Candidate pool exhausted
Max configured waves reached
Campaign manually stopped
Slot is no longer valid
Configurable Defaults

Setting
Default
Minimum cancellation notice hours
24
SMS batch size per wave
3
AI call count per escalation step
1–2
Delay between waves
10 minutes
Max waves
3
All defaults are adjustable via agent settings without code deployment.
💬 Messaging Rules

Because no temporary hold exists, all outreach language must treat availability as conditional.
SMS

Must communicate:
A sooner appointment may be available
Patient should reply if interested
Availability is not guaranteed until confirmed
Example SMS:



We may have an earlier appointment available at [Facility Name] for your same exam.
Reply YES if interested and we will contact you to confirm availability.
Voice / AI Call Script Intent

Identify facility or brand
State a possible earlier appointment may be available
Ask if patient is interested
Capture response
Tell patient a confirmation will follow if slot is still available
Additional Messaging Behavior

Scenario
Behavior
Patient responds after slot is already filled
Send graceful closeout message
Patient declines
Mark Declined, do not retry in same campaign
No response
Allow future wave escalation per configuration
🔒 Response Handling and Single-Winner Enforcement

Because multiple patients may respond simultaneously and no hold exists, booking confirmation must be atomic at the DB/service level.
Response Flow

Patient replies YES or expresses interest via call
System checks whether slot is still open at moment of processing
If open: mark patient as SelectedWinner, reschedule appointment, close campaign immediately
If no longer open: mark candidate as LostSlot, send closeout message if configured
Concurrency Requirement

The appointment update service must enforce a single winner using transaction locking, status checks, row versioning, or an equivalent production-safe method. Exact implementation is an Engineering decision (see Open Implementation Decisions).
⚠️ One patient wins. All simultaneous responders that lose must fail cleanly and receive a closeout message.
🗄️ Data Model

All tables live in tenant_db.
BackfillCampaign

One row per canceled slot being worked.
Field
Type
Nullable
Notes
BackfillCampaignId
int
No
PK
AgentType
varchar
No
CancellationBackfill
CancelledAppointmentId
int
No
FK → Appointments
CancelledPatientId
int
No
FK → Patients
FacilityId
int
No
FK → Facilities
CPTCode
varchar
No
Matched CPT
OpenSlotStartDateTime
datetime
No
Original exam time
CancellationDateTime
datetime
No
When cancellation was recorded
MinNoticeHoursApplied
int
No
Threshold used at creation time
CampaignStatus
varchar
No
See status model
StartedAt
datetime
No
 
EndedAt
datetime
Yes
 
FilledByPatientId
int
Yes
Set on fill
FilledByAppointmentId
int
Yes
Set on fill
ClosedReason
varchar
Yes
 
CreatedBySystemFlag
bit
No
Always true for auto-created
LastWaveNumber
int
Yes
 
LastWaveAt
datetime
Yes
 
BackfillCandidate

One row per patient evaluated under a campaign.
Field
Type
Nullable
Notes
BackfillCandidateId
int
No
PK
BackfillCampaignId
int
No
FK → BackfillCampaign
PatientId
int
No
FK → Patients
AppointmentId
int
No
FK → Appointments
FacilityId
int
No
 
CPTCode
varchar
No
 
ScheduledAppointmentDateTime
datetime
No
Used for ranking
RankOrder
int
No
Persisted at selection time
EligibilityStatus
varchar
No
See candidate status model
ExclusionReason
varchar
Yes
Populated on exclusion
WaveNumberFirstContacted
int
Yes
 
LastContactedAt
datetime
Yes
 
CurrentContactStatus
varchar
Yes
 
InterestedFlag
bit
Yes
 
DeclinedFlag
bit
Yes
 
NoResponseFlag
bit
Yes
 
WonSlotFlag
bit
Yes
 
LostSlotFlag
bit
Yes
 
ResponseDateTime
datetime
Yes
 
BackfillActionLog

One row per communication action taken.
Field
Type
Nullable
Notes
BackfillActionLogId
int
No
PK
BackfillCampaignId
int
No
FK
BackfillCandidateId
int
No
FK
Channel
varchar
No
SMS or Voice
ActionType
varchar
No
 
AttemptedAt
datetime
No
 
Outcome
varchar
Yes
 
ProviderMessageId
varchar
Yes
 
TranscriptId
int
Yes
FK if applicable
TemplateId
int
Yes
 
AgentRunId
varchar
Yes
 
RawResponsePayload
nvarchar(max)
Yes
Store for audit
ℹ️ If the existing outbound AI platform already has a campaign metrics/summary table, reuse it. Do not create a duplicate aggregation table.
📊 Status Model

Campaign Statuses

Status
Meaning
Pending
Created, not yet running
Running
Active wave execution
Filled
Slot assigned to a winner
ClosedNoCandidates
No eligible candidates found at creation
ClosedExhausted
All candidates contacted, none confirmed
ClosedMaxWavesReached
Wave limit hit before fill
ClosedSlotNoLongerAvailable
Slot was filled or canceled by another process
ClosedManually
Admin stopped campaign
ClosedSystemError
Unrecoverable processing failure
Candidate Statuses

Status
Meaning
Eligible
Passed all selection criteria
ExcludedNoShow
Patient has no-show flag
ExcludedInvalidContact
Missing or opted-out contact info
ExcludedAlreadyContacted
Already reached in this campaign
Queued
Selected for next wave
TextSent
SMS dispatched
CallPlaced
AI call initiated
VoicemailLeft
Call resulted in voicemail
NoResponse
No reply within wave window
Interested
Responded affirmatively
Declined
Responded negatively
SelectedWinner
Slot assigned to this patient
LostSlot
Responded but slot already taken
Error
Processing failure on this candidate
ℹ️ Align these to existing outbound agent status conventions if they already exist in the platform.
🔄 Processing Flows

Trigger Flow




Appointment cancellation event fires
  → Evaluate 24-hour eligibility
    → If < 24 hours: exit, no action
  → Check for existing campaign on this appointment
    → If exists: exit
  → Create BackfillCampaign record
  → Query and rank candidates
    → If 0 candidates: close as ClosedNoCandidates
  → Begin wave execution
Candidate Query Flow




SELECT scheduled appointments WHERE:
  FacilityId = canceled.FacilityId
  AND CPTCode = canceled.CPTCode
  AND AppointmentStatus = Scheduled
EXCLUDE:
  no-show patients
  opted-out / missing contact
  same appointment as canceled slot
  suppressed by outbound rules
ORDER BY ScheduledAppointmentDateTime DESC, AppointmentId ASC
PERSIST candidate rows with RankOrder
Wave Execution Flow




For each wave until stop condition:
  1. Select next SMS batch (top N uncontacted)
  2. Dispatch SMS via shared outbound channel
  3. Wait configured delay (respecting business-hour rules)
  4. Escalate: AI call configured count of non-responders
  5. Check stop conditions
  6. Advance wave counter
Response Flow




Inbound SMS/call disposition received
  → Resolve BackfillCampaignId + BackfillCandidateId
  → If patient interested:
      → Atomic check: is slot still open?
        → Yes: assign winner, reschedule appointment, close campaign
        → No: mark LostSlot, send closeout message
  → If patient declined:
      → Mark Declined, no retry this campaign
  → If uninterpretable:
      → Log, optionally send clarification per outbound framework support
🖥️ UI Requirements

Agent Dashboard — Shared Across All Outbound AI Agents

All outbound AI agents — including the Cancellation Backfill Agent — are accessed from a single dashboard. The dashboard is not duplicated per agent.
Top-level layout:
Left sidebar or top tab strip lists all available agents by name (e.g., Cancellation Backfill, Appointment Reminder, Recall Outreach, etc.)
Selecting an agent loads that agent's view in the main panel
Main panel contains three tabs per agent: Campaigns, Settings, Reports
Active agent is visually indicated (highlight, selected state)
Agent-level enable/disable status is visible inline on the agent list without needing to open settings
ℹ️ The dashboard does not navigate away or open a new page per agent. It is a single-page experience with panel switching.
Campaigns Tab

Displays all campaigns for the selected agent.
List view columns:
Column
Notes
Campaign ID
Linkable to detail view
Facility
Display name
CPT Code
 
Canceled Slot Date/Time
The original exam datetime
Status
Color-coded badge (Running = blue, Filled = green, Closed = gray, Error = red)
Started At
 
Ended At
Blank if still running
Filled By
Patient name or ID if filled, blank otherwise
Close Reason
Shown on closed campaigns
Actions
Stop (if Running), View Detail
Filters above the list:
Date range (campaign started at)
Facility (multi-select)
Status (multi-select)
Filled vs. unfilled toggle
CPT code (free text)
Sort: Default is Started At descending. All columns sortable.
Campaign Detail View

Opened from the campaign list. Displays everything that happened for one campaign.
Header

Campaign ID, status badge, facility, CPT code, canceled slot datetime
Started At / Ended At
Filled by (patient name + appointment ID if filled)
Close reason
Manual Stop button (visible only when status = Running)
Candidate List

Table of all candidates evaluated for this campaign, including excluded ones.
Column
Notes
Rank
RankOrder at selection time
Patient
Name + ID
Current Appointment Date
Their scheduled exam date
Eligibility Status
Color-coded (Eligible, Excluded, Winner, Lost, etc.)
Exclusion Reason
Populated for excluded candidates
Wave First Contacted
 
Last Contacted At
 
Response
Interested / Declined / No Response / Won / Lost
Response DateTime
 
Excluded candidates are shown in the list with muted styling, not hidden.
Outreach Timeline

Chronological event log for the campaign. Every action is a row.
Column
Notes
Timestamp
Exact datetime
Event Type
CampaignCreated, CandidatesBuilt, SmsSent, CallPlaced, VoicemailLeft, ResponseReceived, WinnerAssigned, CampaignClosed, etc.
Patient
Name + ID where applicable
Channel
SMS / Voice / System
Wave
Wave number
Outcome
Sent, Delivered, Failed, Interested, Declined, NoResponse, Won, Lost
Provider Message ID
For tracing with SMS/call provider
This timeline is the full audit log. Every system action and patient response is a row. Nothing is omitted.
Transcript Panel

If a voice call has a transcript, a View Transcript link appears on the call row in the timeline
Clicking opens the transcript inline or in a side panel
Transcript includes: patient name, call datetime, duration, full turn-by-turn text
Raw Response Payload

For debugging: expandable section on each log row showing RawResponsePayload from the provider
Collapsed by default, visible to admin users
Settings Tab

All agent-specific settings are editable here without code deployment. Changes take effect on the next campaign created — they do not retroactively affect running campaigns.
⚠️ Changing settings does not affect campaigns already in Running status. The settings applied at campaign creation time are stored on the campaign record.
Agent Toggle

Control
Type
Notes
Agent Enabled
Toggle (On/Off)
Disabling stops new campaigns from being created. Running campaigns complete.
Trigger Settings

Setting
Control
Default
Notes
Minimum Cancellation Notice
Number input (hours)
24
Cancellations with less notice than this are ignored
Wave Settings

Setting
Control
Default
Notes
SMS Batch Size Per Wave
Number input
3
How many patients receive SMS in each wave
Delay Between Waves
Number input (minutes)
10
Wait time between wave completion and next wave start
Maximum Waves
Number input
3
Campaign stops after this many waves regardless of fill status
AI Call Escalation Enabled
Toggle
On
When off, only SMS is used
AI Calls Per Wave
Number input
1
How many non-responders receive an AI call per wave
Hours of Operation

Controls when outbound contact is allowed. Applies to both SMS and voice unless separately configured.
Setting
Control
Default
Notes
Allowed Contact Days
Multi-select (Mon–Sun)
Mon–Fri
Days outreach is permitted
Contact Window Start
Time picker
8:00 AM
No outreach before this time
Contact Window End
Time picker
6:00 PM
No outreach after this time
Timezone
Dropdown
Facility local timezone
Applied per facility if multi-timezone
ℹ️ If a wave is ready to execute outside the contact window, it waits until the window opens. It does not skip — it queues.
Holiday Suppression

Setting
Control
Notes
Use Shared Holiday Calendar
Toggle
On by default. Inherits the platform holiday list.
Agent-Specific Blackout Dates
Date picker (multi-select)
Optional additional dates to suppress outreach for this agent only
Candidate Matching Rules

Setting
Control
Default
Notes
Same Facility Required
Toggle
On
Cannot be disabled in current scope
Same CPT Required
Toggle
On
Cannot be disabled in current scope
Exclude No-Show Patients
Toggle
On
Excludes any patient with a no-show flag
Campaign Behavior

Setting
Control
Default
Notes
Campaign Timeout
Number input (minutes)
TBD Engineering
Auto-close campaign if slot is unfilled after this duration
Late-Response Closeout Message Enabled
Toggle
On
Send closeout SMS to patients who respond after slot is filled
Messaging Templates

Setting
Control
Notes
SMS Template
Dropdown (from shared template library)
Required. Must be set before agent is enabled.
Voice Script Template
Dropdown (from shared template library)
Required if AI Call Escalation is enabled.
Closeout Message Template
Dropdown (from shared template library)
Used when slot is already filled on response
Save button at bottom of Settings tab. Unsaved changes show a banner: "You have unsaved changes."
Reports Tab

Aggregate reporting for the selected agent scoped to the configured date range.
Filters:
Date range
Facility (multi-select)
Status (filled / unfilled / all)
Channel (SMS / Voice / All)
Metrics displayed:
Metric
Description
Campaigns Created
Total campaigns triggered
Campaigns Filled
Count where status = Filled
Fill Rate
Filled / Created %
Avg Time to Fill
From StartedAt to EndedAt on filled campaigns
Total Candidates Contacted
Unique patients reached across all campaigns
SMS Sent
Total SMS dispatched
Calls Placed
Total AI calls initiated
SMS Response Rate
Interested responses / SMS sent %
Voice Response Rate
Interested responses / calls placed %
Fills by Wave
Breakdown of which wave produced the winning response
Campaigns Closed Without Fill
Count and %
Top Close Reasons
Bar breakdown of ClosedReason values
Export to CSV available on all report views.
⚙️ Admin Settings — Full Field Reference

Agent-Specific Settings

Setting
Type
Default
Enabled
bool
false
MinimumCancellationNoticeHours
int
24
SmsBatchSizePerWave
int
3
DelayBetweenWavesMinutes
int
10
MaxWaves
int
3
AiCallEscalationEnabled
bool
true
AiCallQuantityPerWave
int
1
AllowedContactDays
flags/bitmask
Mon–Fri
ContactWindowStartTime
time
08:00
ContactWindowEndTime
time
18:00
ContactWindowTimezone
varchar
Facility local
UseSharedHolidayCalendar
bool
true
AgentBlackoutDates
date[]
empty
SameFacilityRequired
bool
true
SameCptRequired
bool
true
ExcludeNoShowEnabled
bool
true
CampaignTimeoutMinutes
int
TBD Engineering
LateResponseCloseoutEnabled
bool
true
AllowedSmsTemplateId
int
null
AllowedVoiceTemplateId
int
null
CloseoutMessageTemplateId
int
null
Shared Settings Inherited from Platform

Holiday dates, do-not-call windows, opt-out enforcement, logging retention, SMS/voice provider routing.
📋 Functional Requirements

ID
Requirement
FR-1
System creates a campaign only when cancellation occurs ≥ configured notice hours before exam start
FR-2
Candidate matching requires same facility and same CPT code
FR-3
System excludes patients with a no-show flag when exclusion is enabled
FR-4
Eligible candidates are ranked farthest scheduled appointment first
FR-5
System obeys configured contact window, holiday suppression, and shared outbound quiet-hour rules
FR-6
System contacts candidates in configurable waves using SMS and optional AI calls
FR-7
Outreach messaging must not guarantee slot availability
FR-8
Only one patient can be assigned the slot per campaign
FR-9
All agents share a single dashboard UI; agent is selected from a list to view campaigns, settings, and reports
FR-10
All actions are logged through the existing outbound AI logging infrastructure with full audit trail
FR-11
Agent has separate configurable settings adjustable from the UI without code deployment
FR-12
Campaign detail view exposes full chronological audit log including every SMS, call, and patient response
FR-13
All agent settings (hours of operation, wave gap, batch size, templates, etc.) are editable from the Settings tab
🏗️ Non-Functional Requirements

Category
Requirement
Reliability
No duplicate campaigns per canceled slot. Retry-safe — repeated trigger events must not produce duplicate outreach.
Concurrency
Simultaneous inbound responses handled safely; exactly one winner per campaign.
Performance
Candidate build and first wave dispatch begin promptly after qualifying cancellation event. Response processing is near-real-time.
Auditability
Full action trace available for admin review from campaign creation through closure. Every event is a row in the timeline.
Configurability
All agent settings adjustable from UI without code deployment. Changes do not affect in-flight campaigns.
Maintainability
Reuse existing outbound abstractions. No hardcoded business hours, holidays, or message branching outside shared systems.
🔗 Integration Points

System
Usage
Outbound AI orchestrator
Agent registration, wave scheduling, queue management
Holiday/business-hours rules
Shared enforcement — sourced from API/DB, not hardcoded
SMS provider integration
Outbound text dispatch
Voice/AI call provider
Outbound call and response capture
Outbound log store
Campaign and action logging
Outbound admin UI
Single dashboard, agent selection, campaigns, settings, reports
Appointment update service
Atomic reschedule on winner assignment
Transcript/review tooling
Call transcript storage and inline review
✅ Acceptance Criteria

Scenario 1 — Eligible cancellation



Given an appointment is canceled 27 hours before exam time
When the cancellation event is processed
Then a BackfillCampaign record is created with status Pending
Scenario 2 — Ineligible cancellation



Given an appointment is canceled 9 hours before exam time
When the cancellation event is processed
Then no BackfillCampaign is created
Scenario 3 — Candidate selection



Given multiple scheduled patients exist at the same facility with the same CPT code
When the candidate list is built
Then only patients matching facility AND CPT code are included
Scenario 4 — No-show exclusion



Given an otherwise eligible patient has a no-show flag
When the candidate list is built
Then that patient is excluded with ExclusionReason = ExcludedNoShow
Scenario 5 — Candidate ranking



Given multiple eligible candidates with different scheduled appointment dates
When the candidate list is ranked
Then the candidate with the farthest scheduled appointment date appears first
Scenario 6 — Business hours enforcement



Given a campaign wave is ready to execute outside the configured contact window
When wave execution is evaluated
Then outreach is queued and deferred until the contact window opens
Scenario 7 — Single winner enforcement



Given two patients reply YES within milliseconds of each other
When response processing occurs
Then exactly one patient is assigned SelectedWinner
And the other is assigned LostSlot
And the campaign closes immediately
Scenario 8 — Shared UI / agent selection



Given multiple outbound AI agents exist
When an admin opens the outbound AI dashboard
Then all agents are listed in the sidebar
And selecting Cancellation Backfill loads its Campaigns, Settings, and Reports tabs
Scenario 9 — Full audit log



Given a campaign has run and closed
When an admin opens the campaign detail view
Then every SMS sent, call placed, and patient response appears in the timeline
In chronological order with timestamps, outcomes, and provider message IDs
Scenario 10 — Settings saved without deployment



Given an admin changes DelayBetweenWavesMinutes from 10 to 15 in the Settings tab
When the admin saves
Then the next campaign created uses a 15-minute delay between waves
And campaigns already running are not affected
⚠️ Open Implementation Decisions

These are Engineering decisions to resolve during design — not product unknowns.
#
Decision
1
Exact transactional method for single-winner enforcement (row locking, optimistic concurrency, status CAS, etc.)
2
Tie-break behavior when two candidates have the same ScheduledAppointmentDateTime — lowest AppointmentId assumed; confirm
3
Whether late-response closeout SMS is always sent or only when LateResponseCloseoutEnabled = true
4
Exact reuse path for existing transcript and agent-run tables in the outbound platform
5
Whether AI call escalation targets only same-wave non-responders or all prior non-responders across waves
6
CampaignTimeoutMinutes default value
7
Whether contact window is enforced per-facility timezone or a single global timezone
📈 Reporting / KPIs

Track at minimum, rolled up into existing outbound AI reporting:
Campaigns created
Campaigns filled
Fill rate (filled / created %)
Average time to fill
Candidates contacted per campaign
SMS response rate
Voice response rate
Fills by wave number
Campaigns closed without fill
Top closure reasons
🔗 Related Documents

Product Bible v1.4.1 — canonical domain model and platform overview
Entity & Data Dictionary v1.1 — field definitions, DB scope conventions, naming standards
Acceptance Criteria Template — Given/When/Then format reference
📝 Version History

Version
Date
Author
Changes
1.0
Thursday, May 14th, 2026
Danny Rackow
Initial publish
