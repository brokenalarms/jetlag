# Jetlag

Fix timestamps across GoPro, iPhone, drone, and cinema cameras so multi-camera footage lands in the right place in your video editor — automatically.

## Components

- **scripts/** — Python CLI tools for timestamp fixing, tagging, file organization, and gyroflow project generation. Work standalone with no knowledge of the app.
- **macos/** — SwiftUI app that reads `media-profiles.yaml`, edits camera profiles, and launches the scripts.
- **web/** — Marketing site (Vite + Tailwind).
