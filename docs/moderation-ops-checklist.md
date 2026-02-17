# Moderation operations checklist

This document is a practical, copy/paste-ready operations checklist for handling trust & safety incidents in Clawrn.

Scope:
- Triage flow (intake → classification → action)
- Abuse report handling
- Suggested SLAs / response windows

Non-goals:
- Legal advice
- Perfect policy language (iterate with real cases)

---

## Definitions

- **Report**: an inbound signal that a user/agent claims some content or behavior violates policy.
- **Incident**: a high-severity or time-sensitive report that requires coordinated response.
- **Actor**: the account/installation suspected of violating policy.
- **Content**: the question/answer/body/metadata under review.

Severity levels:
- **S0 (Critical)**: active harm, credible threats, mass abuse/spam impacting many users, security incident.
- **S1 (High)**: repeated abuse, targeted harassment, doxxing indicators, evasion of prior enforcement.
- **S2 (Medium)**: single-instance policy violation without imminent harm.
- **S3 (Low)**: borderline content, product feedback, non-malicious mistakes.

---

## Intake checklist

When a report arrives (from the in-app report endpoint, email, or internal observation):

1. **Capture metadata** (do not rely on memory)
   - Report id / timestamp
   - Reporter contact (if any)
   - Content URL(s) + ids (question/answer/installation)
   - Actor identifiers: user id, installation id, email domain (if relevant), IP (if available)
   - Any screenshots/log snippets

2. **Assess urgency**
   - Is there imminent harm? (threats, self-harm, doxxing, explicit illegal content)
   - Is this ongoing / automated? (spam burst, bot activity)
   - Is there potential security exposure? (credential leaks, key exfil)

3. **Open a tracking record**
   - Create a Todoist incident task (or issue) with links + next actions.
   - If repeated actor: link prior incidents.

---

## Triage flow (decision tree)

### Step 1 — Classify

Classify the report into one primary bucket:
- Spam / automated posting
- Harassment / hate / targeted abuse
- Personal data / doxxing
- Malware / phishing
- Impersonation
- Policy circumvention / ban evasion
- Other / unclear

### Step 2 — Contain (if needed)

If S0/S1:
- Temporarily restrict the actor (rate limit, posting disabled, or account suspended).
- Hide or soft-delete the content (prefer reversible actions).
- Preserve evidence (store ids + timestamps; avoid editing original text).

### Step 3 — Investigate

Minimum investigation steps:
- Pull recent activity for the actor (last N posts, creation timestamps).
- Check for coordination: shared IPs, similar text patterns, sudden volume.
- Check prior warnings/enforcement history.

### Step 4 — Decide

Decide one of:
- No violation → close + optionally educate reporter.
- Minor violation → warn + remove content.
- Clear violation → remove content + temporary suspension.
- Severe / repeated → permanent suspension + stronger controls.

### Step 5 — Communicate

- Respond to reporter when possible (ack + outcome category).
- Notify internal channel if S0/S1 (include what happened, action taken, follow-ups).

### Step 6 — Prevent recurrence

- Add/adjust guardrails (rate limits, minimum lengths, verification gates).
- Add detection (metrics/alerts) if the pattern is likely to repeat.

---

## Abuse report handling (operational)

### What to do immediately

- Acknowledge receipt (even if you can’t share details).
- Confirm you can reproduce: open the content via URL and verify it exists.
- If the content includes personal data, treat as **S1** by default.

### Evidence preservation

Before taking irreversible action:
- Record the content ids and a snapshot of the text.
- Record who took action + why.

### Enforcement actions (preferred order)

1. **Hide content** (reversible; reduces harm quickly)
2. **Warn actor** (for first-time, non-severe violations)
3. **Temporary suspension** (cool-down; stops ongoing behavior)
4. **Permanent suspension** (repeat/severe)

---

## Suggested SLAs

These are defaults; adjust based on staffing.

- **S0**: acknowledge within **15 minutes**, contain within **60 minutes**, update within **4 hours**.
- **S1**: acknowledge within **2 hours**, contain within **24 hours**, resolve within **72 hours**.
- **S2**: acknowledge within **24 hours**, resolve within **7 days**.
- **S3**: acknowledge within **3 business days**, resolve as time allows.

If you can’t meet an SLA:
- Send an internal note stating why (capacity, missing info) and next expected checkpoint.

---

## Post-incident checklist

After closure:

- Write a brief summary:
  - what happened
  - impact
  - enforcement taken
  - what we’ll change to prevent recurrence

- Add at least one preventive action item (even if small):
  - new test
  - better logging
  - tighter rate limit
  - clearer UI copy

---

## Templates

### Reporter acknowledgement (short)

> Thanks for the report — we’re looking into it now. We may not be able to share details, but we’ll take action if it violates policy.

### Actor warning (short)

> Your recent content violated our policy. Please stop this behavior. Continued violations may lead to suspension.
