# Explanation: Architecture & Data Flow

This document explains the conceptual architecture and design rationale behind the in-app macOS Calendar synchronization model.

---

## 1. Why In-App EventKit Syncing?

Standard cloud-to-cloud calendar synchronizers typically require:
- Granting full read/write OAuth tokens to external SaaS cloud servers.
- Exposing webhooks or continuous long-polling connections.
- Risking corporate compliance violations by sending sensitive enterprise calendar data to third-party servers.

The **In-App EventKit** approach takes advantage of macOS as the bridge:
1. macOS Calendar already natively connects to your enterprise account (Exchange, Outlook, iCloud) via system-level enterprise SSO and MDM policies.
2. macOS Calendar also natively connects to your personal Google / Gmail account.
3. This sync tool operates **100% locally** on your Mac via Apple's native `EventKit` framework. No network credentials, passwords, or tokens are ever handled by the sync script, and no data leaves your machine except through Apple's trusted system sync daemons.

---

## 2. High-Level Data Flow

```mermaid
sequenceDiagram
    autonumber
    participant EK as macOS EventKit (EKEventStore)
    participant Engine as Local SyncEngine
    participant DB as SQLite (sync_state.db)
    participant Google as macOS Calendar App (Google Sync)

    Engine->>EK: Query source events in window [T_start, T_end]
    EK-->>Engine: Raw EKEvent instances
    Engine->>DB: Fetch existing mappings & hashes
    DB-->>Engine: Cached mappings
    Engine->>Engine: Sanitize fields & calculate SHA-256 hash
    Engine->>Engine: Compute diff (Create / Update / Delete)
    
    alt Event to Create
        Engine->>EK: Create new EKEvent (sanitized title + time)
        EK-->>Engine: Assigned target_event_id
        Engine->>DB: Store mapping & content_hash
    else Event to Update
        Engine->>EK: Update EKEvent (title / time)
        Engine->>DB: Update mapping & content_hash
    else Event to Delete
        Engine->>EK: Remove EKEvent
        Engine->>DB: Delete mapping record
    end

    Engine->>EK: Commit store changes
    EK->>Google: Background sync to Google servers
```

---

## 3. Lifetime & Concurrency

- **Stateless Execution**: The core sync engine runs as a single discrete process per execution. State is strictly persisted to SQLite.
- **Atomic Commits**: Event modifications use `saveEvent:span:commit:error:` or explicit batch `commit:`, ensuring the macOS calendar database remains consistent even if interrupted.
- **Process Isolation**: When managed by `launchd`, each sync iteration runs in a sandboxed, non-interactive background process with isolated UTF-8 environment settings.
