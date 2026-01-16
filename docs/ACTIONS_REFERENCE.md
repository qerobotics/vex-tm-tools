# Actions Reference Guide

This document provides a comprehensive reference for all supported actions in the VEX TM Manager Tools system. Actions can be triggered manually, through timer milestones, or via event mappings.

## Table of Contents
- [Common Action Properties](#common-action-properties)
- [Audio Actions (Spotify)](#audio-actions-spotify)
- [Video Actions (ATEM)](#video-actions-atem)
- [Lighting Actions (OSC/Zeros)](#lighting-actions-osczeros)
- [Message Actions](#message-actions)
- [Action Lists](#action-lists)

---

## Common Action Properties

All actions support the following optional properties:

### delay
**Type**: `number` (seconds)  
**Description**: Delay the execution of the action by the specified number of seconds.

**Example**:
```json
{
  "type": "video",
  "command": "switch",
  "camera_id": "1",
  "delay": 15
}
```
This would delay switching to camera 1 for 15 seconds after the event is triggered.

### priority
**Type**: `number`  
**Default**: `0`  
**Description**: When multiple actions of the same type are triggered, only the highest priority action(s) will be executed.

---

## Audio Actions (Spotify)

Audio actions control Spotify playback through the Spotify Web API.

### Base Structure
```json
{
  "type": "audio",
  "command": "<command_name>",
  "metadata": {}
}
```

### Available Commands

#### 1. Play Track
Play a specific track by URI.

```json
{
  "type": "audio",
  "command": "play",
  "metadata": {
    "track_uri": "spotify:track:3n3Ppam7vgaVa1iaRUc9Lp"
  }
}
```

#### 2. Play Playlist Track
Play a specific track from a playlist by track number.

```json
{
  "type": "audio",
  "command": "play_playlist_track",
  "metadata": {
    "playlist_uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
    "track_number": 5
  }
}
```

**Note**: When triggered via event, the `track_number` can be automatically extracted from the match name (e.g., "Q12" → track 12).

#### 3. Play Playlist
Start playing an entire playlist from the beginning.

```json
{
  "type": "audio",
  "command": "play",
  "metadata": {
    "playlist_uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
  }
}
```

#### 4. Pause
Pause current playback.

```json
{
  "type": "audio",
  "command": "pause"
}
```

#### 5. Resume
Resume paused playback.

```json
{
  "type": "audio",
  "command": "play"
}
```

#### 6. Next Track
Skip to next track.

```json
{
  "type": "audio",
  "command": "next"
}
```

#### 7. Previous Track
Go back to previous track.

```json
{
  "type": "audio",
  "command": "previous"
}
```

#### 8. Set Volume
Set playback volume (0-100).

```json
{
  "type": "audio",
  "command": "volume",
  "metadata": {
    "volume": 75
  }
}
```

#### 9. Seek to Position
Seek to specific position in current track.

```json
{
  "type": "audio",
  "command": "seek",
  "metadata": {
    "position_ms": 30000
  }
}
```

#### 10. Transfer Playback
Transfer playback to a different device.

```json
{
  "type": "audio",
  "command": "transfer",
  "metadata": {
    "device_id": "abc123def456"
  }
}
```

### Example: Match Start Music
Play track 1 from a playlist when a match starts:

```json
{
  "type": "audio",
  "command": "play_playlist_track",
  "metadata": {
    "playlist_uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
    "track_number": 1,
    "position_ms": 0
  }
}
```

---

## Video Actions (ATEM)

Video actions control Blackmagic Design ATEM video switchers.

### Base Structure
```json
{
  "type": "video",
  "command": "<command_name>",
  "camera_id": <input_number>
}
```

### Available Commands

#### 1. Switch Program Input
Switch the program output to a specific camera/input.

```json
{
  "type": "video",
  "command": "switch",
  "camera_id": 1
}
```

**Camera IDs** typically correspond to:
- `1` - Camera 1
- `2` - Camera 2
- `3` - Camera 3
- `4` - Camera 4
- `1000` - Black
- `2001` - Color Bars
- `3010` - Media Player 1
- `6000` - Super Source

#### 2. Fade to Black
Perform a fade to black transition.

```json
{
  "type": "video",
  "command": "fade_to_black"
}
```

**Note**: No `camera_id` required for fade to black.

### Field-to-Camera Mapping

When an action is triggered by a field event and no `camera_id` is specified, the system automatically maps field IDs to camera IDs based on the `field_to_camera` configuration in `config.json`:

```json
{
  "field_to_camera": {
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4
  }
}
```

### Example: Auto-Switch on Field Activation
```json
{
  "type": "video",
  "command": "switch"
}
```
When triggered by a `fieldActivated` event on Field 2, this will automatically switch to camera 2.

### Example: Fade to Black at Match End
```json
{
  "type": "video",
  "command": "fade_to_black"
}
```

---

## Lighting Actions (OSC/Zeros)

Lighting actions control lighting systems via OSC (Open Sound Control) protocol, typically targeting ETC Eos or similar consoles.

### Base Structure
```json
{
  "type": "lighting",
  "command": "go",
  "preset_id": "<preset_number>"
}
```

### Available Commands

#### 1. Go to Cue
Fire a specific cue number.

```json
{
  "type": "lighting",
  "command": "go",
  "target_type": "cue",
  "preset_id": "1"
}
```

#### 2. Fire Playback
Fire a specific playback/fader.

```json
{
  "type": "lighting",
  "command": "go",
  "target_type": "playback",
  "preset_id": "1"
}
```

#### 3. Release Playback
Release a specific playback.

```json
{
  "type": "lighting",
  "command": "release",
  "target_type": "playback",
  "release_id": "1"
}
```

#### 4. Release All
Release all active playbacks.

```json
{
  "type": "lighting",
  "command": "release",
  "target_type": "playback",
  "release_id": "all"
}
```

#### 5. Next Cue
Go to the next cue in the active cuelist.

```json
{
  "type": "lighting",
  "command": "next",
  "target_type": "cue"
}
```

#### 6. Pause
Pause the current cue.

```json
{
  "type": "lighting",
  "command": "pause",
  "target_type": "cue"
}
```

#### 7. Custom OSC Command
Send a custom OSC message.

```json
{
  "type": "lighting",
  "command": "custom",
  "osc_address": "/eos/key/go_0",
  "osc_value": 1.0
}
```

### Delay
Add a delay before executing the lighting action (useful for timing).

```json
{
  "type": "lighting",
  "command": "go",
  "preset_id": "5",
  "delay_s": 2
}
```

### Example: Field Intro Lighting
```json
{
  "type": "lighting",
  "command": "go",
  "target_type": "playback",
  "preset_id": "1"
}
```

### Example: Match Start Sequence
```json
{
  "type": "lighting",
  "command": "go",
  "target_type": "cue",
  "preset_id": "10",
  "delay_s": 3
}
```

---

## Message Actions

Message actions display text messages on timer displays without executing any hardware control.

### Structure
```json
{
  "type": "message",
  "message": "Get Ready!"
}
```

Or in timer milestone format:
```json
{
  "time_remaining": 10,
  "action_type": "message",
  "action_payload": {},
  "message": "10 seconds remaining!"
}
```

### Example: Countdown Messages
```json
{
  "time_remaining": 3,
  "action_type": "message",
  "action_payload": {},
  "message": "Match starting in 3 seconds!"
}
```

---

## Action Lists

Action lists are reusable collections of timed actions that can be assigned to timers. They are stored in `storage/action_lists.json`.

### Action List Structure
```json
{
  "id": "standard-match",
  "name": "Standard Match Actions",
  "description": "Standard actions for a VEX match timer",
  "division_id": null,
  "round": null,
  "instance": null,
  "match_number": null,
  "milestones": [
    {
      "time_remaining": 15,
      "action_type": "audio",
      "action_payload": {
        "command": "play_playlist_track",
        "metadata": {
          "playlist_uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
          "track_number": 1
        }
      },
      "message": "Match starting soon!"
    },
    {
      "time_remaining": 10,
      "action_type": "lighting",
      "action_payload": {
        "command": "go",
        "target_type": "playback",
        "preset_id": "5"
      },
      "message": null
    },
    {
      "time_remaining": 3,
      "action_type": "video",
      "action_payload": {
        "command": "switch",
        "camera_id": 1
      },
      "message": "Match starting in 3 seconds!"
    },
    {
      "time_remaining": 0,
      "action_type": "lighting",
      "action_payload": {
        "command": "go",
        "target_type": "cue",
        "preset_id": "1"
      },
      "message": "Match Started!"
    }
  ]
}
```

### Match Linking

Action lists can be automatically linked to specific matches by setting the match identification fields. When a timer is running with a field_id set, the system will automatically detect the current match on that field and use the appropriate action list.

**Match Linking Fields:**
- `division_id` (number): The division ID from the TM API
- `round` (string): The round type (`"QUAL"`, `"TOP_N"`, etc.)
- `instance` (number): The instance number (usually 1)
- `match_number` (number): The match number within the round

**Example: Action list for Qualification Match #5 in Division 1:**
```json
{
  "id": "quals-5-special",
  "name": "Q5 Special Introduction",
  "description": "Special camera sequence for Q5",
  "division_id": 1,
  "round": "QUAL",
  "instance": 1,
  "match_number": 5,
  "milestones": [
    {
      "time_remaining": 20,
      "action_type": "video",
      "action_payload": {
        "command": "switch",
        "camera_id": 3
      },
      "message": "Special match introduction!"
    }
  ]
}
```

**How Auto-Detection Works:**
1. When a timer starts, if it has a `field_id` but no explicit `action_list_id`, the system queries the TM API for the current match on that field
2. It extracts the match tuple (division, round, instance, match number)
3. It searches all action lists for one with matching `division_id`, `round`, `instance`, and `match_number`
4. If found, those milestones are used instead of the timer's default milestones

**Priority:**
1. Explicit `action_list_id` on timer (highest priority)
2. Auto-detected action list based on current match
3. Timer's own milestones (fallback)

This allows you to:
- Create special sequences for specific matches (finals, featured matches, etc.)
- Automatically switch to the correct action list without manual intervention
- Have field-specific behavior determined by what match is loaded

### Using Action Lists with Timers

When creating or editing a timer, you can assign an action list:

```json
{
  "timer_id": "abc123",
  "name": "Field 1 Match Timer",
  "duration": 120,
  "action_list_id": "standard-match",
  "field_id": "1"
}
```

The timer will execute all milestones from the action list at the specified times.

---

## Event-Based Actions

Actions can also be triggered by events through the `actions.json` file. These are organized by event type and can include field-specific actions, match name patterns, and payload filters.

### Example: Field Activation Actions
```json
{
  "on_event": {
    "fieldActivated": [
      {
        "match_name": "*",
        "fields": {
          "1": [
            {
              "type": "video",
              "command": "switch",
              "camera_id": 1
            },
            {
              "type": "lighting",
              "command": "go",
              "preset_id": "13"
            }
          ],
          "2": [
            {
              "type": "video",
              "command": "switch",
              "camera_id": 2
            },
            {
              "type": "lighting",
              "command": "go",
              "preset_id": "14"
            }
          ]
        }
      }
    ]
  }
}
```

### Example: Match-Specific Actions with Pattern Matching
```json
{
  "on_event": {
    "matchStarted": [
      {
        "match_name": "Q*",
        "fields": {
          "all": [
            {
              "type": "audio",
              "command": "play_playlist_track",
              "metadata": {
                "playlist_uri": "spotify:playlist:QUAL_PLAYLIST_ID"
              }
            }
          ]
        }
      },
      {
        "match_name": "F*",
        "fields": {
          "all": [
            {
              "type": "audio",
              "command": "play_playlist_track",
              "metadata": {
                "playlist_uri": "spotify:playlist:FINALS_PLAYLIST_ID"
              }
            }
          ]
        }
      }
    ]
  }
}
```

### Example: Payload-Filtered Actions
```json
{
  "on_event": {
    "audienceDisplayChanged": [
      {
        "match_name": "*",
        "payload_filter": {
          "display": "IN_MATCH"
        },
        "fields": {
          "all": [
            {
              "type": "lighting",
              "command": "go",
              "preset_id": "20"
            }
          ]
        }
      },
      {
        "match_name": "*",
        "payload_filter": {
          "display": "BLANK"
        },
        "fields": {
          "all": [
            {
              "type": "lighting",
              "command": "go",
              "preset_id": "1"
            }
          ]
        }
      }
    ]
  }
}
```

### Example: Delayed Actions
Actions can include a `delay` field to postpone execution. This is useful for scenarios like switching cameras a few seconds after a match starts:

```json
{
  "on_event": {
    "matchStarted": [
      {
        "match_name": "*",
        "fields": {
          "1": [
            {
              "type": "lighting",
              "preset_id": "15",
              "comment": "Immediately set match lighting"
            },
            {
              "type": "video",
              "camera_id": "1",
              "command": "switch",
              "delay": 15,
              "comment": "Switch to match camera after 15 seconds"
            }
          ]
        }
      }
    ]
  }
}
```

---

## Manual Action Triggering

Actions can be triggered manually through the API:

```bash
curl -X POST http://localhost:5000/api/trigger_action \
  -H "Content-Type: application/json" \
  -d '{
    "type": "video",
    "command": "switch",
    "camera_id": 2
  }'
```

---

## Priority System

When multiple actions of the same type are triggered simultaneously, the priority system determines which action executes:

```json
{
  "type": "lighting",
  "command": "go",
  "preset_id": "1",
  "priority": 10
}
```

Higher priority values take precedence. Default priority is `0`.

---

## Best Practices

1. **Test Actions Individually**: Test each action type independently before combining them in complex sequences.

2. **Use Action Lists for Reusability**: Create action lists for common sequences (match start, match end, field intro) and reuse them across multiple timers.

3. **Field-Specific vs. Global**: Use field-specific actions when different fields need different behavior, use "all" fields for consistent behavior.

4. **Timing Considerations**: 
   - Add delays to lighting actions if they need to sync with other systems
   - Consider the duration of fade to black transitions
   - Account for Spotify API latency when timing music

4. **Error Handling**: Actions that fail (e.g., Spotify unavailable) are logged but don't stop other actions from executing.

5. **Camera ID Documentation**: Maintain a document mapping camera IDs to physical cameras/sources for your specific ATEM setup.

---

## Troubleshooting

### Spotify Actions Not Working
- Check that Spotify credentials are configured in `config.json`
- Verify an active Spotify device is available
- Check that audio is not paused in config

### ATEM Actions Not Working
- Verify ATEM IP address in `config.json`
- Check network connectivity to ATEM
- Confirm video is not paused in config
- Enable debug logging to see detailed ATEM communication

### Lighting Actions Not Working
- Verify OSC target IP and port in `config.json`
- Check that lighting console is listening for OSC
- Confirm lighting is not paused in config
- Test with a simple OSC monitor tool

### Enable Debug Logging
Set debug logging in `main.py` to see detailed action execution:
```python
logging.getLogger("modules.video.atem.controller").setLevel(logging.DEBUG)
logging.getLogger("modules.event_processor").setLevel(logging.DEBUG)
logging.getLogger("modules.audio.spotify.controller").setLevel(logging.DEBUG)
```

---

## Additional Resources

- [PyATEMMax Documentation](PYATEMMAXDOCS.md) - Complete ATEM API reference
- [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api/)
- [OSC Specification](http://opensoundcontrol.org/spec-1_0)
- [Actions JSON Schema](../storage/actions.json) - Full event-based actions configuration
