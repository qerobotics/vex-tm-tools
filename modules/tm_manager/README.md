# Modules - TM Manager

This directory contains modules responsible for interfacing with the VEX Tournament Manager (TM).

## Key Components

-   **`api_client.py`**: A low-level client for making requests to the VEX TM WebSocket and HTTP APIs.
-   **`connector.py`**: Manages the connection to the Tournament Manager, handles authentication, and passes incoming events to the main application's event queue.
-   **`schedule_fetcher.py`**: A component that periodically fetches the match schedule from the TM API to provide data for "upcoming match" displays.
