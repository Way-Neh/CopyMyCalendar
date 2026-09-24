#!/usr/bin/env bash
# ==============================================================================
# scripts/build_macos.sh
# Build standalone macOS Application (.app) and Distribution Disk Image (.dmg)
# ==============================================================================
set -euo pipefail

APP_NAME="CalendarSync"
BUNDLE_ID="com.sendtogmail.calendarsync"
VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
BUILD_DIR="${ROOT_DIR}/build"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
DMG_NAME="${APP_NAME}-v${VERSION}-macOS.dmg"
DMG_PATH="${DIST_DIR}/${DMG_NAME}"
STAGING_DIR="${BUILD_DIR}/dmg_staging"

echo "=========================================================="
echo " Building ${APP_NAME} v${VERSION} for macOS"
echo "=========================================================="

cd "${ROOT_DIR}"

# 1. Run automated test suites
echo "==> Running automated tests..."
./venv/bin/python test_sync_engine.py
./venv/bin/python test_outlook_calendar.py
./venv/bin/python test_gui_app.py
echo "==> All test suites passed."

# 2. Ensure ICNS icon exists
if [ ! -f "assets/CalendarSync.icns" ]; then
    echo "==> Generating assets/CalendarSync.icns from assets/app_icon.png..."
    mkdir -p /tmp/CalendarSync.iconset
    sips -s format png -z 16 16     assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_16x16.png
    sips -s format png -z 32 32     assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_16x16@2x.png
    sips -s format png -z 32 32     assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_32x32.png
    sips -s format png -z 64 64     assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_32x32@2x.png
    sips -s format png -z 128 128   assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_128x128.png
    sips -s format png -z 256 256   assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_128x128@2x.png
    sips -s format png -z 256 256   assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_256x256.png
    sips -s format png -z 512 512   assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_256x256@2x.png
    sips -s format png -z 512 512   assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_512x512.png
    sips -s format png -z 1024 1024 assets/app_icon.png --out /tmp/CalendarSync.iconset/icon_512x512@2x.png
    iconutil -c icns /tmp/CalendarSync.iconset -o assets/CalendarSync.icns
    rm -rf /tmp/CalendarSync.iconset
fi

# 3. Clean previous build artifacts
rm -rf "${BUILD_DIR}" "${DIST_DIR}/${APP_NAME}.app" "${DMG_PATH}"

# 4. Build Standalone App with PyInstaller
echo "==> Building ${APP_NAME}.app with PyInstaller..."
./venv/bin/pyinstaller --noconfirm \
  --windowed \
  --name "${APP_NAME}" \
  --icon "assets/CalendarSync.icns" \
  --osx-bundle-identifier "${BUNDLE_ID}" \
  --add-data "config.yaml.example:." \
  --add-data "assets/CalendarSync.icns:assets" \
  --hidden-import "objc" \
  --hidden-import "Foundation" \
  --hidden-import "AppKit" \
  --hidden-import "EventKit" \
  --hidden-import "yaml" \
  --hidden-import "sqlite3" \
  gui_app.py

# 5. Patch Info.plist with native macOS entitlements and permissions
echo "==> Configuring Info.plist..."
PLIST="${APP_BUNDLE}/Contents/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${APP_NAME}" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :NSCalendarsUsageDescription 'CalendarSync requires calendar access to detect and synchronize events between accounts.'" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :NSCalendarsUsageDescription string 'CalendarSync requires calendar access to detect and synchronize events between accounts.'" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :NSCalendarsFullAccessUsageDescription 'CalendarSync requires full calendar access to read source events and mirror sanitized events into your target calendar.'" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :NSCalendarsFullAccessUsageDescription string 'CalendarSync requires full calendar access to read source events and mirror sanitized events into your target calendar.'" "${PLIST}"
/usr/libexec/PlistBuddy -c "Set :NSAppleEventsUsageDescription 'CalendarSync requires permission to communicate with Microsoft Outlook to sync calendar events.'" "${PLIST}" || /usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'CalendarSync requires permission to communicate with Microsoft Outlook to sync calendar events.'" "${PLIST}"

# 6. Apply ad-hoc code signature
echo "==> Code-signing ${APP_NAME}.app (ad-hoc)..."
codesign --force --deep --sign - "${APP_BUNDLE}"

# 7. Create DMG staging folder and drag-and-drop installer
echo "==> Assembling DMG staging environment..."
mkdir -p "${STAGING_DIR}"
cp -R "${APP_BUNDLE}" "${STAGING_DIR}/"
ln -s /Applications "${STAGING_DIR}/Applications"

cat << 'EOF' > "${STAGING_DIR}/INSTALL_INSTRUCTIONS.txt"
==================================================================
 CalendarSync - Privacy-First macOS Calendar Synchronization
==================================================================

1. Drag "CalendarSync.app" into the "Applications" folder.
2. Launch CalendarSync from Applications or Spotlight.
3. If macOS Gatekeeper shows an unrecognized developer warning on first launch:
   - Right-click CalendarSync.app in Applications and select "Open"
   - OR run this command in Terminal:
     xattr -cr /Applications/CalendarSync.app

4. The CalendarSync icon will appear in your macOS Menu Bar.
   Click the icon to select your Source and Target calendars!
==================================================================
EOF

echo "==> Generating disk image ${DMG_NAME}..."
hdiutil create -volname "${APP_NAME} v${VERSION}" \
  -srcfolder "${STAGING_DIR}" \
  -ov -format UDZO \
  "${DMG_PATH}"

rm -rf "${STAGING_DIR}"

echo "=========================================================="
echo " BUILD SUCCESSFUL!"
echo " App Bundle: ${APP_BUNDLE}"
echo " DMG Installer: ${DMG_PATH}"
echo " SHA256: $(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')"
echo "=========================================================="
