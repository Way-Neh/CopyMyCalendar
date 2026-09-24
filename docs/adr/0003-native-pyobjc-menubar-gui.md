# 3. Native Cocoa/PyObjC Menu Bar Application Over Web/Electron Shells

## Context
Users require a lightweight status bar utility to monitor synchronization status, view live logs, adjust settings, and trigger manual syncs without incurring heavy memory footprints or dependency bloat typical of web-based shells (such as Electron or Tauri).

## Decision
We implement `gui_app.py` using native macOS Cocoa frameworks (`AppKit`, `Foundation`, `NSVisualEffectView`, `NSStatusItem`) via PyObjC bindings.

## Consequences
- **Minimal Footprint**: Low memory and CPU utilization idling in the macOS menu bar.
- **Native Look & Feel**: Follows macOS Human Interface Guidelines (vibrancy, dark mode, SF Symbols, system fonts).
- **Zero Additional Runtimes**: Runs on the existing Python virtual environment without Node.js or web runtimes.
