# 1. Use Local EventKit and AppleScript Over Remote Cloud OAuth APIs

## Context
Enterprise work calendars (e.g. Microsoft 365 Exchange, Corporate Google Workspace) frequently enforce strict administrative tenant policies that block third-party OAuth app consent and prevent external cloud services from accessing mailbox data directly via Graph or Google REST APIs. Furthermore, storing cloud credentials or bearer tokens locally introduces unnecessary security risk and privacy concerns.

## Decision
We access source and target calendars directly through local macOS frameworks (`EventKit` via PyObjC and `NSAppleScript`/Apple Events for Microsoft Outlook).

## Consequences
- **Zero Third-Party Cloud Tokens**: No external API registration or admin consent approval is required.
- **Privacy Enforcement**: Corporate event descriptions, notes, URLs, and attendee lists never leave the local machine and are sanitized before writing to the target calendar.
- **Environment Dependency**: Requires running on macOS with granted Calendar and Automation permissions.
