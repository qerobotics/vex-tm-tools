# Timer Action Lists Refactoring

## Summary of Changes

The timer system has been refactored to use globally defined action lists instead of timer-specific actions. This allows timers to switch between different lists of actions without requiring changes to the timer itself.

## Key Changes

### 1. New ActionList Model (`models/timer.py`)
- Added `ActionList` dataclass that represents a reusable list of timed actions
- Contains: `id`, `name`, `description`, `milestones`, and `created_at`
- Action lists are stored separately from timers

### 2. Updated Timer Model (`models/timer.py`)
- Timer now includes `action_list_id` field (optional)
- Legacy `milestones` field is kept for backward compatibility
- When `action_list_id` is set, the timer uses the action list's milestones instead of its own

### 3. Storage
- **New file**: `storage/action_lists.json` - stores all action lists
- **Updated**: `storage/timers_saved.json` - now includes `action_list_id` field for each timer

### 4. Server API Endpoints (`server.py`)
New endpoints for managing action lists:
- `GET /api/action_lists` - Get all action lists
- `POST /api/action_lists` - Create a new action list
- `GET /api/action_lists/<id>` - Get a specific action list
- `PUT /api/action_lists/<id>` - Update an action list
- `DELETE /api/action_lists/<id>` - Delete an action list

Updated timer endpoints:
- Timer creation and update now accept `action_list_id` parameter
- Timer state endpoint checks action list for milestones when applicable

### 5. Timer Execution Logic (`main.py`)
- Timer tick worker now loads action lists and uses them for milestone checking
- If a timer has `action_list_id`, it uses milestones from the action list
- Falls back to timer's own milestones if no action list is specified

### 6. User Interface (`templates/timer_admin.html`)
- Added "Action Lists" tab alongside "Timers" tab
- Action list management UI with create, edit, duplicate, and delete functions
- Timer form now includes action list dropdown selector
- Timers display which action list they're using (if any)
- Action list editor uses the same milestone builder as timer editor

## Usage

### Creating an Action List
1. Go to Timer Administration page
2. Click on "Action Lists" tab
3. Click "Create Action List"
4. Define name, description, and milestones with their actions
5. Save the action list

### Assigning Action List to Timer
1. Create or edit a timer
2. Select an action list from the "Action List" dropdown
3. Save the timer
4. The timer will now use the actions defined in that action list

### Benefits
- **Reusability**: One action list can be used by multiple timers
- **Flexibility**: Switch between different action configurations easily
- **Maintainability**: Update actions in one place, affects all timers using that list
- **Backward Compatible**: Timers without action lists still work with their own milestones

## Migration Notes
- Existing timers are automatically compatible (they use their own milestones)
- No data migration needed - the `action_list_id` field defaults to `null`
- Legacy milestone support maintained for backward compatibility
