# Models

This directory contains the Python data classes that define the core data structures for the application. These models ensure a consistent and predictable structure for objects that are passed between different modules, serialized to JSON for storage, or used in the API.

## Key Models

-   **`Action`**: Base class for all actions (Audio, Video, Lighting).
-   **`ActionMapping`**: Defines the mapping between events/state changes and the actions they trigger.
-   **`Config`**: Represents the main application configuration from `storage/config.json`.
-   **`Event`**: Represents an event coming from the Tournament Manager or generated internally.
-   **`FieldState`**: Represents the real-time state of a single competition field.
-   **`AuditEntry`**: Represents a log entry for auditing purposes.
