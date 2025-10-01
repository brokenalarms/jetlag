-- Photos Spatial Audio Mix Automation
-- Automates changing spatial audio mix to "Cinematic" with 25% intensity
-- Works on selected videos in Photos app

-- Configuration
property targetMix : "Cinematic"
property targetIntensity : 25 -- percentage (0-100)
property delayBetweenActions : 0.5 -- seconds
property maxRetries : 3

-- Global variables for tracking
global videoCount, processedCount, errorCount, skippedCount

-- Main execution
on run
	set videoCount to 0
	set processedCount to 0
	set errorCount to 0
	set skippedCount to 0

	-- Check if Photos is running
	if not (application "Photos" is running) then
		display dialog "Photos app is not running. Please open Photos and select videos to process." buttons {"Cancel"} default button "Cancel"
		return
	end if

	-- Activate Photos
	tell application "Photos" to activate
	delay 1

	-- Get user confirmation
	set confirmResult to display dialog "This script will change the spatial audio mix to '" & targetMix & "' with " & targetIntensity & "% intensity for all selected videos in Photos." & return & return & "Make sure you have selected the videos you want to process." & return & return & "Continue?" buttons {"Cancel", "Start"} default button "Start"

	if button returned of confirmResult is "Cancel" then
		return
	end if

	-- Start processing
	log "Starting spatial audio mix automation..."

	try
		-- Check if we have a selection
		tell application "Photos"
			set selectedItems to selection
			set videoCount to count of selectedItems
		end tell

		if videoCount is 0 then
			display dialog "No items selected in Photos. Please select videos and try again." buttons {"OK"} default button "OK"
			return
		end if

		log "Processing " & videoCount & " selected items..."

		-- Process each video
		processVideos()

		-- Show completion summary
		set summaryMessage to "Processing complete!" & return & return & "Videos processed: " & processedCount & return & "Videos skipped: " & skippedCount & return & "Errors encountered: " & errorCount & return & "Total items: " & videoCount

		display dialog summaryMessage buttons {"OK"} default button "OK"
		log summaryMessage

	on error errMsg number errNum
		display dialog "Error: " & errMsg buttons {"OK"} default button "OK"
		log "Error: " & errMsg
	end try
end run

-- Process all videos in selection
on processVideos()
	tell application "System Events"
		tell process "Photos"
			-- Start with first video (should be selected)
			repeat videoCount times
				set currentVideo to processedCount + errorCount + skippedCount + 1
				log "Processing video " & currentVideo & " of " & videoCount

				try
					-- Process current video
					if processCurrentVideo() then
						set processedCount to processedCount + 1
					else
						set skippedCount to skippedCount + 1
					end if
				on error errMsg
					log "Error processing video " & currentVideo & ": " & errMsg
					set errorCount to errorCount + 1
				end try

				-- Move to next video (unless this is the last one)
				if currentVideo < videoCount then
					moveToNextVideo()
				end if
			end repeat
		end tell
	end tell
end processVideos

-- Process the currently selected video
on processCurrentVideo()
	tell application "System Events"
		tell process "Photos"
			-- Enter edit mode
			log "Entering edit mode..."
			keystroke return
			delay delayBetweenActions * 2

			-- Look for edit interface
			set editingStarted to false
			repeat maxRetries times
				if exists button "Done" of window 1 then
					set editingStarted to true
					exit repeat
				end if
				delay delayBetweenActions
			end repeat

			if not editingStarted then
				log "Could not enter edit mode - skipping video"
				-- Try to exit any partial edit state
				keystroke "escape"
				delay delayBetweenActions
				return false
			end if

			-- Look for audio controls
			log "Looking for audio controls..."
			set audioControlFound to false
			set audioButton to missing value

			-- Try different possible locations for audio controls
			try
				-- Look for "Audio" button or similar
				if exists button "Audio" of window 1 then
					set audioButton to button "Audio" of window 1
					set audioControlFound to true
				else if exists button "Audio Mix" of window 1 then
					set audioButton to button "Audio Mix" of window 1
					set audioControlFound to true
				else
					-- Look for buttons with audio-related accessibility descriptions
					set allButtons to every button of window 1
					repeat with btn in allButtons
						try
							set btnTitle to title of btn
							if btnTitle contains "Audio" or btnTitle contains "Sound" or btnTitle contains "Mix" then
								set audioButton to btn
								set audioControlFound to true
								exit repeat
							end if
						end try
					end repeat
				end if
			end try

			if not audioControlFound then
				log "No audio controls found - video may not support spatial audio"
				exitEditMode()
				return false
			end if

			-- Click audio control
			log "Clicking audio control..."
			click audioButton
			delay delayBetweenActions

			-- Look for spatial audio mix options
			if not setSpatialAudioMix() then
				log "Could not set spatial audio mix"
				exitEditMode()
				return false
			end if

			-- Save changes and exit edit mode
			log "Saving changes..."
			click button "Done" of window 1
			delay delayBetweenActions * 2

			return true
		end tell
	end tell
end processCurrentVideo

-- Set the spatial audio mix and intensity
on setSpatialAudioMix()
	tell application "System Events"
		tell process "Photos"
			-- Look for mix options (could be popup button, menu, or segmented control)
			try
				-- First, look for the current mix display/button
				set mixControl to missing value

				-- Try popup buttons first
				if exists popup button 1 of window 1 then
					repeat with popupBtn in (every popup button of window 1)
						try
							set popupTitle to title of popupBtn
							if popupTitle contains "Standard" or popupTitle contains "Cinematic" or popupTitle contains "Studio" or popupTitle contains "In-Frame" then
								set mixControl to popupBtn
								exit repeat
							end if
						end try
					end repeat
				end if

				-- If no popup found, look for other controls
				if mixControl is missing value then
					-- Look for segmented controls or other UI elements
					-- This may vary depending on Photos version
					log "Looking for alternative mix controls..."

					-- Try clicking on text that shows current mix
					set allStaticTexts to every static text of window 1
					repeat with txt in allStaticTexts
						try
							set txtValue to value of txt
							if txtValue contains "Standard" or txtValue contains "Cinematic" or txtValue contains "Studio" or txtValue contains "In-Frame" then
								click txt
								delay delayBetweenActions
								exit repeat
							end if
						end try
					end repeat
				end if

				-- If we found a popup button, click it to open menu
				if mixControl is not missing value then
					click mixControl
					delay delayBetweenActions

					-- Look for Cinematic option in the menu
					try
						click menu item targetMix of menu 1 of mixControl
						delay delayBetweenActions
						log "Selected " & targetMix & " mix"
					on error
						-- Try alternative approach - look for menu items
						if exists menu item targetMix of menu 1 of popup button 1 of window 1 then
							click menu item targetMix of menu 1 of popup button 1 of window 1
							delay delayBetweenActions
							log "Selected " & targetMix & " mix (alternative method)"
						else
							log "Could not find " & targetMix & " option in menu"
							return false
						end if
					end try
				else
					log "Could not find spatial audio mix controls"
					return false
				end if

				-- Now look for intensity slider (appears after selecting Cinematic)
				delay delayBetweenActions
				if setIntensitySlider() then
					log "Set intensity to " & targetIntensity & "%"
				else
					log "Could not find or set intensity slider"
				end if

				return true

			on error errMsg
				log "Error setting spatial audio mix: " & errMsg
				return false
			end try
		end tell
	end tell
end setSpatialAudioMix

-- Set the intensity slider value
on setIntensitySlider()
	tell application "System Events"
		tell process "Photos"
			try
				-- Look for sliders in the window
				set intensitySlider to missing value

				-- Find slider (may be labeled as Intensity or similar)
				if exists slider 1 of window 1 then
					set intensitySlider to slider 1 of window 1
				else
					-- Look for sliders in groups or other containers
					set allSliders to every slider of window 1
					if (count of allSliders) > 0 then
						set intensitySlider to item 1 of allSliders
					end if
				end if

				if intensitySlider is not missing value then
					-- Set slider to target percentage
					-- Slider value is typically 0-1, so convert percentage
					set sliderValue to targetIntensity / 100
					set value of intensitySlider to sliderValue
					delay delayBetweenActions
					return true
				else
					log "No intensity slider found"
					return false
				end if

			on error errMsg
				log "Error setting intensity slider: " & errMsg
				return false
			end try
		end tell
	end tell
end setIntensitySlider

-- Move to next video in selection
on moveToNextVideo()
	tell application "System Events"
		tell process "Photos"
			-- Use right arrow key to move to next item
			key code 124 -- right arrow
			delay delayBetweenActions
		end tell
	end tell
end moveToNextVideo

-- Exit edit mode safely
on exitEditMode()
	tell application "System Events"
		tell process "Photos"
			try
				if exists button "Done" of window 1 then
					click button "Done" of window 1
				else if exists button "Cancel" of window 1 then
					click button "Cancel" of window 1
				else
					-- Try escape key
					keystroke "escape"
				end if
				delay delayBetweenActions
			end try
		end tell
	end tell
end exitEditMode