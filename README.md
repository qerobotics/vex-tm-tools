<img width="1632" height="2112" alt="image" src="https://github.com/user-attachments/assets/d12139a6-1964-4fdc-b473-bf3eb4d12af1" /># VEX TM Manager Spotify Sync + Other Tools
## What will this do?
1. Connect to TM Manager via the TM Manager Public API and track match starts, ends, and updates to audience displays using the Field Set Websocket
2. Connect to the Spotify API and play music in time with match starts, from a predefined list stored in a json file
3. Connect to the ATEM Switcher and automatically switch cameras depending on which field is active
4. Connect to a ZerOS lighting board and switch lighting using OSC. Lighting will follow this pattern: Queued field ready, Countdown, Active, Finish, Restart
5. (Hopefully) Control the PTZ Module attatched to the camera using a micro-controller connected to a servo, such as a Raspberry Pi or Arduino (Avi's Idea)

## TM Manager Connection
### Useful Resources
* API Guide: https://docs.google.com/document/d/1LYMOsPlYzZF3SYyTNPe2b3fvlbFc5XvA_Dmd-JH7ieU/edit?tab=t.0
* API Intro: https://kb.roboticseducation.org/hc/en-us/articles/19238156122135-TM-Public-API

### API Key
```
waiting on this
```

## Spotify API
### Useful Resources
* https://developer.spotify.com/documentation/web-api
* https://spotipy.readthedocs.io/en/2.25.1/

Planning on using Spotipy

## ATEM Switching
### Useful Resources
* https://clvlabs.github.io/PyATEMMax/

## ZerOS Lighting Board
### Useful Resources
* FLX S48 Manual: https://support.vikinglighting.co.uk/downloads/FLX%20S%20User%20Manual%20v1.pdf
* https://www.zero88.com/manuals/zeros/setup/triggers/osc
* https://python-osc.readthedocs.io/en/latest/
* Rogue Light Manuals:
* https://www.chauvetprofessional.com/wp-content/uploads/2019/10/Rogue_R2X_wash_UM_Rev2.pdf

Will be using Open Sound Control (OSC)

### Lighting patterns
#### Preset Allocations
1-4. field 1 ready, countdown, active, finish  
5-8. field 2 ready, countdown, active, finish  
9-12. field 3 ready, countdown, match, finish  
13. standby (1 blue on each field, 1 white on stage)  
14. stage (4 white on stage)  
15. light show  

#### Preset Info
ready= 2 red on field about to start match, 1 blue on other 2  
countdown= 2 red on field about to start match, other 2 blue lights flash with countdown  
match= 2 white on field with match, 1 blue on other 2   
finish= all lights flash white, spin around and go back to standby  

## PTZ Module
No clue how we're gonna do this
