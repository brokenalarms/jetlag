# Jetlag

<div align=center>
  <img src="https://github.com/brokenalarms/jetlag/blob/main/macos/Sources/Assets.xcassets/AppIcon.appiconset/AppIcon.png" width=300>
</div>

Fix timestamps across GoPro, iPhone, drone, and cinema cameras so multi-camera footage lands in the right place in your video editor.

## Components

- **scripts/** — Python CLI tools for timestamp fixing, tagging, file organization, and gyroflow project generation. Work standalone with no knowledge of the app.
- **macos/** — SwiftUI app that reads `media-profiles.yaml`, edits camera profiles, and launches the scripts.
- **web/** — Marketing site (Vite + Tailwind).
