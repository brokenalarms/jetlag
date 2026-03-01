# Jetlag — build system
#
# Prerequisites (install via Homebrew):
#   brew install xcodegen
#
# Usage:
#   make generate      — generate Xcode project from macos/project.yml
#   make test-scripts  — run script tests (works on Linux and macOS)
#   make test-macos    — run Swift unit tests (macOS only, requires Xcode)
#   make test          — run all tests available on this platform
#   make build         — build Debug app into build/
#   make archive       — build Release archive (macos/build/Jetlag.xcarchive)
#   make dmg           — build Release archive and package into build/Jetlag.dmg
#   make clean         — remove build artifacts
#
# Code signing:
#   By default the DMG is built with the Xcode automatic signing identity
#   (suitable for Developer ID distribution when your certificate is in Keychain).
#   To build unsigned (ad-hoc, for local testing only):
#     make dmg SIGNING_IDENTITY=-
#
# Notarization (required for Gatekeeper-free distribution):
#   After `make dmg`, run:
#     xcrun notarytool submit build/Jetlag.dmg \
#       --apple-id YOU@example.com --team-id XXXXXXXXXX --password @keychain:AC_PASSWORD
#     xcrun stapler staple build/Jetlag.dmg

APP_NAME        := Jetlag
SCHEME          := $(APP_NAME)
MACOS_DIR       := macos
BUILD_DIR       := build
DERIVED_DIR     := $(BUILD_DIR)/derived
ARCHIVE         := $(BUILD_DIR)/$(APP_NAME).xcarchive
EXPORT_DIR      := $(BUILD_DIR)/export
APP_PATH        := $(EXPORT_DIR)/$(APP_NAME).app
DMG_STAGING     := $(BUILD_DIR)/dmg-staging
DMG_PATH        := $(BUILD_DIR)/$(APP_NAME).dmg
EXPORT_PLIST    := $(MACOS_DIR)/ExportOptions.plist

.PHONY: all generate test test-scripts test-macos build archive export dmg clean

all: dmg

## Generate Xcode project from project.yml (requires: brew install xcodegen)
generate:
	cd $(MACOS_DIR) && xcodegen generate

## Run script tests (any platform)
test-scripts:
	pytest scripts/tests/ -x --ignore=scripts/tests/test_performance.py

## Run Swift unit tests (macOS only, requires Xcode)
test-macos: generate
	xcodebuild \
		-scheme $(SCHEME) \
		-configuration Debug \
		-derivedDataPath $(DERIVED_DIR) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		test | xcpretty 2>/dev/null || xcodebuild \
		-scheme $(SCHEME) \
		-configuration Debug \
		-derivedDataPath $(DERIVED_DIR) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		test

## Run all tests available on this platform
test: test-scripts
ifeq ($(shell uname),Darwin)
test: test-macos
endif

## Build Debug app into build/derived (quick iteration)
build: generate
	xcodebuild \
		-scheme $(SCHEME) \
		-configuration Debug \
		-derivedDataPath $(DERIVED_DIR) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		build | xcpretty 2>/dev/null || xcodebuild \
		-scheme $(SCHEME) \
		-configuration Debug \
		-derivedDataPath $(DERIVED_DIR) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		build

## Create a Release archive
archive: generate
	xcodebuild \
		-scheme $(SCHEME) \
		-configuration Release \
		-archivePath $(ARCHIVE) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		archive

## Export the app from the archive
export: archive
	xcodebuild \
		-exportArchive \
		-archivePath $(ARCHIVE) \
		-exportPath $(EXPORT_DIR) \
		-exportOptionsPlist $(EXPORT_PLIST)

## Package the exported app into a distributable DMG
dmg: export
	@echo "Creating DMG..."
	@rm -rf "$(DMG_STAGING)" "$(DMG_PATH)"
	@mkdir -p "$(DMG_STAGING)"
	@cp -r "$(APP_PATH)" "$(DMG_STAGING)/"
	@ln -s /Applications "$(DMG_STAGING)/Applications"
	hdiutil create \
		-volname "$(APP_NAME)" \
		-srcfolder "$(DMG_STAGING)" \
		-ov \
		-format UDZO \
		"$(DMG_PATH)"
	@rm -rf "$(DMG_STAGING)"
	@echo ""
	@echo "DMG ready: $(DMG_PATH)"
	@echo ""
	@echo "To notarize for Gatekeeper-free distribution:"
	@echo "  xcrun notarytool submit $(DMG_PATH) --apple-id YOU@example.com --team-id XXXXXXXXXX --password @keychain:AC_PASSWORD"
	@echo "  xcrun stapler staple $(DMG_PATH)"

## Remove all build artifacts
clean:
	rm -rf $(BUILD_DIR)
	rm -rf $(MACOS_DIR)/$(APP_NAME).xcodeproj
