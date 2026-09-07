# Mac Calendar to Gmail (In-App) Sync Tool

[![macOS](https://img.shields.io/badge/macOS-12.0%2B-black?logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Documentation: Diátaxis](https://img.shields.io/badge/docs-Diátaxis-brightgreen.svg)](https://diataxis.fr/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-performance, privacy-focused Python utility and background service that synchronizes events between calendars directly within the **macOS Calendar (EventKit)** ecosystem—mirroring work/source calendars (e.g. Exchange, iCloud, Outlook) into a Gmail/Google calendar mapped in the macOS Calendar app without leaking meeting descriptions, notes, or attendee lists.

---

## 🧭 Documentation Map (Diátaxis Framework)

This documentation is structured according to the **[Diátaxis documentation framework](https://diataxis.fr/)**, organized into four distinct quadrants:

```
                  PRACTICAL FOCUS
                        ▲
                        │
       Tutorials        │       How-To Guides
   (Learning-oriented)  │     (Problem-oriented)
                        │
◄───────────────────────┼───────────────────────►
                        │
       Explanation      │         Reference
 (Understanding-oriented│   (Information-oriented)
                        │
                        ▼
                THEORETICAL FOCUS
```

| 🎓 **Tutorials** (Learning-Oriented) | 🛠️ **How-To Guides** (Task-Oriented) |
|---|---|
| • [**Getting Started with Calendar Sync**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/tutorials/getting-started.md)<br>_Step-by-step onboarding walkthrough for new users._ | • [**How to Set Up Background Sync**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/how-to/how-to-setup-background-sync.md)<br>_Automate sync via native launchd or Automator._<br>• [**How to Troubleshoot and Audit**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/how-to/how-to-troubleshoot-and-audit.md)<br>_Search across all calendars and diagnose issues._<br>• [**How to Clean and Re-sync**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/how-to/how-to-clean-and-resync.md)<br>_Safely wipe target calendar and rebuild state._<br>• [**How to Use Direct Google API**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/how-to/how-to-use-direct-google-api.md)<br>_Alternative cloud sync with Google Calendar v3 REST API._ |
| 💡 **Explanation** (Understanding-Oriented) | 📖 **Reference** (Information-Oriented) |
| • [**Architecture & Data Flow**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/explanation/architecture-and-data-flow.md)<br>_System design and in-app EventKit bridge._<br>• [**Privacy & Sanitization Model**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/explanation/privacy-model.md)<br>_How data leak prevention is enforced._<br>• [**Diff Engine & Recurrence Handling**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/explanation/diff-and-recurrence-algorithm.md)<br>_SHA-256 fingerprinting & recurring series expansion._ | • [**CLI Reference**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/reference/cli-reference.md)<br>_Complete command-line options and arguments._<br>• [**Configuration Reference (`config.yaml`)**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/reference/configuration-reference.md)<br>_Schema, parameters, and environment variables._<br>• [**SQLite Database Schema**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/reference/database-schema.md)<br>_State store table structures and indexes._<br>• [**Python API Reference**](file:///Users/ap-wayne.tan/DockerProjects/SendtoGMAIL/docs/reference/api-reference.md)<br>_Classes, methods, and interface definitions._ |

---

## ⚡ Quick Start

### 1. Installation

```bash
cd /Users/ap-wayne.tan/DockerProjects/SendtoGMAIL
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration Wizard

```bash
python3 sync.py setup
```

### 3. Run Sync

```bash
# Preview changes
python3 sync.py sync --dry-run

# Run full synchronization
python3 sync.py sync
```

### 4. Enable Background Automation (LaunchAgent)

```bash
python3 sync.py install-service
```

---

## 🧪 Testing

Run the test suite:

```bash
python3 test_sync_engine.py
```

---

## 📄 License

This project is licensed under the MIT License.
