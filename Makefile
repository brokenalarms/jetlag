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
#   make               — build the Release app into dist/Jetlag.app
#   make build         — build Debug app into build/derived (quick iteration)
#   make archive       — build Release archive (build/Jetlag.xcarchive)
#   make dmg           — package dist/Jetlag.app into dist/Jetlag.dmg
#   make clean         — remove build artifacts and dist/
#
# Code signing:
#   With a "Developer ID Application" certificate in the keychain, the app is
#   exported for Developer ID distribution (macos/ExportOptions.plist). Without
#   one it keeps the archive's local signing: it runs on this Mac but cannot be
#   notarized or handed to anyone else.
#
# Notarization (required for Gatekeeper-free distribution, Developer ID only):
#   After `make dmg`, run:
#     xcrun notarytool submit dist/Jetlag.dmg \
#       --apple-id YOU@example.com --team-id XXXXXXXXXX --password @keychain:AC_PASSWORD
#     xcrun stapler staple dist/Jetlag.dmg

APP_NAME        := Jetlag
SCHEME          := $(APP_NAME)
MACOS_DIR       := macos
BUILD_DIR       := build
DERIVED_DIR     := $(BUILD_DIR)/derived
ARCHIVE         := $(BUILD_DIR)/$(APP_NAME).xcarchive
ARCHIVED_APP    := $(ARCHIVE)/Products/Applications/$(APP_NAME).app
EXPORT_DIR      := $(BUILD_DIR)/export
EXPORT_PLIST    := $(MACOS_DIR)/ExportOptions.plist
DIST_DIR        := dist
DIST_APP        := $(DIST_DIR)/$(APP_NAME).app
DMG_STAGING     := $(BUILD_DIR)/dmg-staging
DMG_PATH        := $(DIST_DIR)/$(APP_NAME).dmg

# A build outside the main checkout must never be able to pass itself off as the
# installed Jetlag — same bundle id, product name and Application Support folder
# would mean shared UserDefaults, a shared Launch Services registration and a
# shared profiles file. Worktrees under .ralph/ therefore build "Jetlag Dev" with
# bundle id com.daniellawrence.Jetlag.dev; the pre-build guard in
# macos/BuildScripts/guard-worktree-identity.sh rejects one that does not.
ifneq (,$(findstring /.ralph/,$(CURDIR)/))
DEV_IDENTITY := JETLAG_BUNDLE_SUFFIX=.dev JETLAG_PRODUCT_SUFFIX=" Dev"
endif

.PHONY: all generate test test-scripts test-macos ralph-verify build archive app dmg clean

all: app

## Generate Xcode project from project.yml (requires: brew install xcodegen)
generate:
	cd $(MACOS_DIR) && xcodegen generate

# Fresh checkouts and worktrees have no venv; bootstrap one so test runs are
# self-contained instead of depending on whichever pytest PATH offers. The
# stamp re-installs deps whenever a requirements file changes.
PYTEST := scripts/.venv/bin/pytest
VENV_STAMP := scripts/.venv/.deps-stamp

$(VENV_STAMP): scripts/requirements.txt scripts/requirements-dev.txt scripts/tests/requirements.txt
	python3 -m venv scripts/.venv
	scripts/.venv/bin/pip install --quiet -r scripts/requirements.txt -r scripts/requirements-dev.txt -r scripts/tests/requirements.txt
	touch $(VENV_STAMP)

## Run script tests (any platform); tests are profile-isolated so they parallelize
# stdin comes from /dev/null: under a supervisor that runs make in its own
# process group on a tmux tty (the ralph loop), any child that reads the
# inherited terminal gets the whole group SIGTTIN-suspended — the suite then
# hangs frozen until the supervisor's timeout, looking like a test hang.
test-scripts: $(VENV_STAMP)
	$(PYTEST) scripts/tests/ -x -n auto --ignore=scripts/tests/test_performance.py < /dev/null

## Run Swift unit tests (macOS only, requires Xcode)
# No xcpretty pipe: when xcpretty is missing the old `| xcpretty || xcodebuild`
# fallback silently ran the entire suite twice.
test-macos: generate
	xcodebuild \
		-scheme $(SCHEME) \
		-configuration Debug \
		-derivedDataPath $(DERIVED_DIR) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		-quiet \
		$(DEV_IDENTITY) \
		test < /dev/null

## Run all tests available on this platform
test: test-scripts
ifeq ($(shell uname),Darwin)
test: test-macos
endif

## Test-based verification for the ralph loop (per-task baseline = the full suite)
ralph-verify: test

## Build Debug app into build/derived (quick iteration)
build: generate
	xcodebuild \
		-scheme $(SCHEME) \
		-configuration Debug \
		-derivedDataPath $(DERIVED_DIR) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		-quiet \
		$(DEV_IDENTITY) \
		build

## Create a Release archive
archive: generate
	xcodebuild \
		-scheme $(SCHEME) \
		-configuration Release \
		-archivePath $(ARCHIVE) \
		-project $(MACOS_DIR)/$(APP_NAME).xcodeproj \
		-quiet \
		archive < /dev/null

## Place the Release app at dist/Jetlag.app
# ditto, not cp -r: it keeps the bundle's symlinks and extended attributes, which
# the code signature covers.
app: archive
	@rm -rf "$(DIST_APP)" "$(EXPORT_DIR)"
	@mkdir -p "$(DIST_DIR)"
	@if security find-identity -v -p codesigning | grep -q "Developer ID Application"; then \
		xcodebuild \
			-exportArchive \
			-archivePath $(ARCHIVE) \
			-exportPath $(EXPORT_DIR) \
			-exportOptionsPlist $(EXPORT_PLIST) \
			-quiet < /dev/null && \
		ditto "$(EXPORT_DIR)/$(APP_NAME).app" "$(DIST_APP)"; \
	else \
		echo "No Developer ID Application certificate in the keychain: keeping the archive's local signing (runs on this Mac only)."; \
		ditto "$(ARCHIVED_APP)" "$(DIST_APP)"; \
	fi
	@codesign --verify --deep --strict "$(DIST_APP)"
	@echo ""
	@echo "App ready: $(DIST_APP)"

## Package dist/Jetlag.app into a DMG
dmg: app
	@echo "Creating DMG..."
	@rm -rf "$(DMG_STAGING)" "$(DMG_PATH)"
	@mkdir -p "$(DMG_STAGING)"
	@ditto "$(DIST_APP)" "$(DMG_STAGING)/$(APP_NAME).app"
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
	rm -rf $(BUILD_DIR) $(DIST_DIR)
	rm -rf $(MACOS_DIR)/$(APP_NAME).xcodeproj
