# VEX TM Manager Spotify Sync + Other Tools
## Useful Resources: 
* API Guide: https://docs.google.com/document/d/1LYMOsPlYzZF3SYyTNPe2b3fvlbFc5XvA_Dmd-JH7ieU/edit?tab=t.0
* API Intro: https://kb.roboticseducation.org/hc/en-us/articles/19238156122135-TM-Public-API
* FLX S48 Manual: https://support.vikinglighting.co.uk/downloads/FLX%20S%20User%20Manual%20v1.pdf


## What will this do?
1. Connect to TM Manager via the TM Manager Public API and track match starts, ends, and updates to audience displays using the Field Set Websocket
2. Connect to the Spotify API and play music in time with match starts, from a predefined list stored in a json file
3. Connect to the ATEM Switcher and automatically switch cameras depending on which field is active
4. (Hopefully) Connect to a ZerOS lighting board and switch lighting after I reverse-engineer the API through intercepting the traffic between a device with the app installed, and the board, using WireShark. Lighting will follow this pattern: Queued field ready, Countdown, Active, Finish, Restart
5. (Hopefully) Control the PTZ Module attatched to the camera using a micro-controller connected to a servo, such as a Raspberry Pi or Arduino (Avi's Idea)

## TM Manager Connection
### API Key
```
waiting on this
```

## Spotify API
WIP

## ATEM Switching
WIP

## ZerOS Lighting Board
### Open Sound Control (OSC)
WIP

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
