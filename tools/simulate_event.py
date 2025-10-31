import requests
import argparse
import json

def send_request(url, payload):
    """Helper function to send the request."""
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        try:
            print("Successfully sent event:")
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print("Received a non-JSON response from the server:")
            print(response.text)

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.status_code} {e.response.reason}")
        print(f"Response body: {e.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to the server at {url}.")
        print(f"Please ensure the main application is running. Error: {e}")

def main(event_type, field=None, match_name=None, display=None, round_val=None, base_url="http://localhost:5000"):
    """
    Sends a simulated event to the running application.
    """
    
    # If we are starting a match, we should first assign it to the field
    # to mimic the real flow of the TM.
    if event_type == "matchStarted" and match_name and field:
        print("First, sending fieldMatchAssigned...")
        assign_payload = {
            "type": "fieldMatchAssigned",
            "field": field,
            "payload": {
                "match": {
                    "division": 1, # Hardcoded for simulation
                    "session": 0,
                    "round": round_val or "QUAL",
                    "match": int(''.join(filter(str.isdigit, match_name))),
                    "instance": 1
                }
            }
        }
        send_request(f"{base_url}/api/simulate_event", assign_payload)
        print("-" * 20)

    # Construct the payload for the main event
    payload = {
        "type": event_type,
        "payload": {}
    }

    if field is not None:
        payload["field"] = field

    if (event_type == "fieldMatchAssigned" or event_type == "fieldAssigned") and match_name:
        # The event from TM is fieldMatchAssigned, but we'll allow fieldAssigned for convenience
        payload["type"] = "fieldMatchAssigned"
        payload["payload"]["match"] = {
            "division": 1, # Hardcoded for simulation
            "session": 0,
            "round": round_val or "QUAL",
            "match": int(''.join(filter(str.isdigit, match_name))),
            "instance": 1
        }
    elif event_type == "audienceDisplayChanged" and display:
        payload["payload"]["display"] = display
    elif match_name and event_type not in ["matchStarted", "fieldMatchAssigned", "audienceDisplayChanged"]:
        # For other potential future events that might use a simple match name
        payload["payload"]["match"] = match_name

    print(f"Sending {event_type} event...")
    send_request(f"{base_url}/api/simulate_event", payload)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a VEX TM event.")
    parser.add_argument("event_type", help="The type of event to simulate (e.g., 'matchStarted', 'fieldMatchAssigned', 'audienceDisplayChanged').")
    parser.add_argument("--field", type=int, help="The field ID to associate with the event.")
    parser.add_argument("--match", help="The match name for 'fieldMatchAssigned' or 'matchStarted' (e.g., 'Q21', 'SF1-1').")
    parser.add_argument("--round", dest="round_val", help="The round type (e.g., 'QUAL', 'ROUND_ROBIN', 'FINALS'). Defaults to 'QUAL'.")
    parser.add_argument("--display", help="The display type for 'audienceDisplayChanged' (e.g., 'IN_MATCH', 'RANKINGS').")
    parser.add_argument("--url", default="http://localhost:5000", help="The base URL of the running application.")

    args = parser.parse_args()

    # Basic validation
    if args.event_type != 'audienceDisplayChanged' and args.field is None:
        parser.error(f"Event type '{args.event_type}' requires the --field argument.")

    main(args.event_type, args.field, args.match, args.display, args.round_val, args.url)
