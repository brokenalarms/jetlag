# Jetlag

Fix timestamps across GoPro, iPhone, drone, and cinema cameras so multi-camera footage lands in the right place in your video editor — automatically.

## Components

- **scripts/** — Python CLI tools for timestamp fixing, tagging, file organization, and gyroflow project generation. Work standalone with no knowledge of the app.
- **macos/** — SwiftUI app that reads `media-profiles.yaml`, edits camera profiles, and launches the scripts.
- **web/** — Marketing site (Vite + Tailwind).

## Setup

### Environment Configuration

Some scripts require environment variables for sensitive information (credentials, paths, etc.).

1. **Copy the example file:**

   ```bash
   cp .env.example .env.local
   ```

2. **Edit `.env.local` with your actual values:**

   ```bash
   vim .env.local
   ```

3. **Never commit `.env.local`** — it's already in `.gitignore`
