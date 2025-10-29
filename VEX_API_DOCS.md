**OAuth Token**

The TM API uses an OAuth 2.0 Client Credentials flow for authorization. This means that you will take your client ID and client secret and use them to call an OAuth server which will validate those credentials and return to you a bearer token. You can then use the bearer token to access the TM API. The bearer token has a short lifetime so your app will need to retrieve a new token periodically.

To obtain the token, POST your `client_id`, `client_secret`, and `grant_type` to `https://auth.vextm.dwabtech.com/oauth2/token` as a form-encoded body. You can also supply `client_id` and `client_secret` using HTTP basic access authorization in the `Authorization` header. The `grant_type` parameter should be set to `client_credentials`. Your preferred programming language likely has an OAuth client library already available.

**Tournament Manager Public API Guide**

If your client ID and secret are valid, the OAuth server will return a JSON response with `access_token`, `token_type`, and `expires_in` fields. The `expires_in` field indicates how long (in seconds) the token is valid for. The `access_token` and `token_type` fields should be used to construct an `Authorization` header for calling the TM API.

Your app should cache the token and reuse it for future API requests until it expires. Do not call the authorization server for a new token each time you want to make an API request.

[Diagram showing the flow for obtaining an access token]

Further details can be found at https://oauth.net/2/grant-types/client-credentials/ if needed.

**Request Signing**

When the Event Partner enables the TM API in Tournament Manager, an API key value is created. Your app will need a way to accept this value from the user, and then your app will need to use this value to sign requests to the TM API. This helps to ensure that your app has been authorized by the Event Partner to access the event.

Each request to the TM API must be signed. Request signing is based on the HTTP request headers. A signature is created by taking the TM API key along with the value of several of the HTTP request headers and then creating a hash-based message authentication code (HMAC) using the SHA256 hash function.

The inclusion of the `x-tm-date` header helps ensure that previous message signatures cannot be reused at a later point in time, and therefore requires that the client making the request has a clock which is synchronized with the TM API server.

**1. Create StringToSign**

[Flow chart step 1: Create StringToSign]
`Date = RFC1123Timestamp()`
`StringToSign = HTTP Verb + "\n" +`
`URI Path and Query string + "\n" +`
`"token": + {BearerToken} + "\n" +`
`"host:" + Host header value + "\n" +`
`"x-tm-date:" + {Date} + "\n"`

**2. Create Signature**

[Flow chart step 2: Create Signature]
`Signature = Hex(HMAC-SHA256({APIKey}, {StringToSign}))`

**3. Add signature header to HTTP request**

[Flow chart step 3: Add signature header to HTTP request]
`RequestHeaders["Host"] = {Host}`
`RequestHeaders["Authorization"] = "Bearer {BearerToken}"`
`RequestHeaders["x-tm-date"] = {Date}`
`RequestHeaders["x-tm-signature"] = {Signature}`

**API Resources**

All API resources are hosted by the TM Web Server. URLs listed below are relative to the web server’s base address, typically `http://{server_IP}` or `http://{server_IP}:8080`. You will likely want to allow your app's users to configure the TM web server address somewhere within your app.

**Event Resource**

| Method | GET |
|---|---|
| URL | /api/event |
| Response format | JSON |
| Example response | { "event": { "name": "Hudsonville HS Over Under Tournament", "code": "RE-VRC-23-2523" } } |

The Event resource returns a JSON object containing basic information about the event. The `code` field is the Robot Events SKU (if configured for the event).

**Division List Resource**

| Method | GET |
|---|---|
| URL | /api/divisions |
| Response format | JSON |
| Example response | { "divisions": [ { "name": "Science", "id": 1 }, { "name": "Technology", "id": 2 }, { "name": "Engineering", "id": 3 }, { "name": "Math", "id": 4 } ] } |

The Division List resource returns a JSON object containing a list of division names and IDs.

**Team List Resource**

| Method | GET |
|---|---|
| URL | /api/teams |
| | or |
| | /api/teams/{division_id} |
| Response format | JSON |
| Example response | { "teams": [ { "number": "10D", "name": "Exothermic Dusk", "shortName": "", "school": "Exothermic Robotics", "sponsors": "", "city": "Redmond", "state": "Washington", "country": "United States", "ageGroup": "HIGH_SCHOOL", "divId": 1, "checkedIn": false }, ... ] } |

The Team List resource returns a JSON object containing a list of teams for the whole event or for just a single division if the `division_id` is provided.

**NOTE:** The `sponsors` and `shortName` fields are not generally used and may be removed in a future update. The `school` field may be renamed to `organization` at some point. Finally, the `city`, `state`, and `country` fields will likely be combined into a `location` field in the near future.

**Match List Resource**

| Method | GET |
|---|---|
| URL | /api/matches/{division_id} |
| Response format | JSON |
| Example response | { "matches": [ { "finalScore": [ 17, 11 ], "matchInfo": { "timeScheduled": 1688306400, "state": "SCORED", "alliances": [ { "teams": [ { "number": "16" }, { "number": "4" } ] }, { "teams": [ { "number": "14" }, { "number": "15" } ] } ], "matchTuple": { "session": 0, "division": 1, "round": "QUAL", "instance": 1, "match": 1 }, "winningAlliance": 0 }, ... ] } |

The Match List resource returns a JSON object containing a list of matches for the specified division. Each match object includes information on the alliances and teams included as well as whether the match is scored and if so, the final score values and winning alliance number.

**Rankings Resource**

| Method | GET |
|---|---|
| URL | /api/rankings/{division_id}/{match_round} |
| Response format | JSON |
| Example response | { "rankings": [ { "rank": 1, "tied": false, "alliance": { "name": "", "teams": [ { "number": "7925S" } ] }, "wins": 10, "losses": 0, "ties": 0, "wp": 26, "ap": 80, "sp": 1027, "avgPoints": 198.39999389648438, "totalPoints": 1984, "highScore": 236, "numMatches": 10, "minNumMatches": true }, ... ] } |

The Rankings resource returns a JSON object containing a list of rankings for the specified division and match round. Not all rankings parameters that are returned are relevant for every game or program type.

**Skills Resource**

| Method | GET |
|---|---|
| URL | /api/skills |
| Response format | JSON |
| Example response | { "skillsRankings": [ { "rank": 1, "tie": false, "number": "1082C", "totalScore": 10, "progHighScore": 10, "progAttempts": 1, "driverHighScore": 0, "driverAttempts": 0 }, ... ] } |

The Skills resource returns a JSON object containing a list of teams who have played in the skills competitions and includes their current rank and high score information. If the `tie` value is `true`, it indicates that the team's rank is shared with at least one other team.

**Field Set List Resource**

| Method | GET |
|---|---|
| URL | /api/fieldsets |
| Response format | JSON |
| Example response | { "fieldsets": [ { "id": 1, "name": "Match Field Set #1" }, { "id": 2, "name": "Match Field Set #2" }, { "id": 3, "name": "Match Field Set #3" } ] } |

The Field Set List endpoint returns a JSON object containing a list of configured field sets including the name and field set ID.

**Field List Resource**

| Method | GET |
|---|---|
| URL | /api/fieldsets/{field_set_id}/fields |
| Response format | JSON |
| Example response | { "fields": [ { "id": 3, "name": "Yellow Field" }, { "id": 4, "name": "Green Field" }, { "id": 5, "name": "Purple Field" } ] } |

The Field List endpoint returns a JSON object containing a list of fields configured within the specified field set, including the name and field ID.

**Field Set Websocket**

| URL | /api/fieldsets/{field_set_id} |
|---|---|
| Protocol | ws:// |
| Message format | JSON |

The Field Set Websocket lets your application receive field set events and issue field set commands.

**Events**

Events are messages that the TM API may send to your client when certain conditions occur.

**Match Assigned to Field**
```json
{
  "type": "fieldMatchAssigned",
  "fieldID": 1,
  "match": {
    "division": 1,
    "session": 0,
    "round": "QUAL",
    "match": 2,
    "instance": 1
  }
}
```

**Field Activated**
```json
{
  "type": "fieldActivated",
  "fieldID": 1
}
```

**Match Started**
```json
{
  "type": "matchStarted",
  "fieldID": 1
}
```

**Match Stopped**
```json
{
  "type": "matchStopped",
  "fieldID": 1
}
```

**Audience Display Changed**
```json
{
  "type": "audienceDisplayChanged",
  "display": "IN_MATCH"
}
```

**Commands**

Commands are messages that your app may send to TM to cause certain actions to happen.

**Start Match**
```json
{
  "cmd": "start"
}
```

**End Match Early**
```json
{
  "cmd": "endEarly"
}
```

**Abort Match**
```json
{
  "cmd": "abort"
}
```

**Reset Timer**
```json
{
  "cmd": "reset"
}
```

**Queue Previous Match**
```json
{
  "cmd": "queuePrevMatch"
}
```

**Queue Next Match**
```json
{
  "cmd": "queueNextMatch"
}
```

**Queue Skills**
```json
{
  "cmd": "queueSkills",
  "skillsID": 1
}
```

**Set Audience Display**
```json
{
  "cmd": "setAudienceDisplay",
  "display": "RANKINGS"
}
```