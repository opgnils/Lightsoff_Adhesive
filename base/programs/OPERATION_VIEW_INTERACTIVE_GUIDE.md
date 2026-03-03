# Dashboard Operation View - Interactive Interface Guide

## New Design Philosophy

The **Operation View** (right panel) is now the primary interactive workspace. Instead of just showing instructions, it displays **interactive selectable lists** where you can directly choose and execute operations.

## How It Works

### Traditional Flow (OLD)
```
Left Menu → Instructions in Operation View → Need to do something elsewhere
```

### New Flow (CURRENT)
```
Left Menu → Interactive List in Operation View → Click to Execute
```

## Example: Running Adhesive Profiles

### Step-by-Step

1. **Navigate to Adhesive Robot**
   - Click on **5 Adhesive Robot** in the left menu
   - Menu expands to show options

2. **Click "Run profile"**
   - The Operation View (right side) **transforms** into an interactive list
   - Shows all available CSV profiles from `adhesive_profiles/` directory

3. **Select and Execute**
   - Click on any profile name in the Operation View
   - Profile execution starts immediately
   - Progress shown in Status Log (bottom-right)

### Visual Layout

```
┌──────────────────┬────────────────────────────────────────────┐
│  Left Menu       │  Operation View (Interactive!)             │
│                  │                                            │
│  ▼ 5 Adhesive    │  Available Adhesive Profiles               │
│    • Manual      │                                            │
│    • Run profile │  Select a profile to execute               │
│    • View hist   │  Connected to 2 device(s)                  │
│    • Emergency   │  Found 3 profile(s)                        │
│                  │                                            │
│                  │  Click on a profile below to start:        │
│                  │                                            │
│                  │  ▸ adh_test_profile.csv      ← CLICKABLE   │
│                  │  ▸ adh_test_nonsync.csv      ← CLICKABLE   │
│                  │  ▸ fast_rampUp.csv           ← CLICKABLE   │
│                  │                                            │
├──────────────────┼────────────────────────────────────────────┤
│  Devices         │  Status Log                                │
│  ● robot1        │  [12:34:56] Starting profile...            │
│  ● robot2        │  [12:34:57] Listener ready on robot1       │
└──────────────────┴────────────────────────────────────────────┘
```

## Operation View Modes

The Operation View now has **two modes**:

### 1. Text Mode (Default)
- Displays static information
- Instructions, status messages, results
- Used for most operations

### 2. List Mode (Interactive)
- Displays selectable list items
- Each item is clickable
- Click triggers the associated action
- Currently used for: **Profile Selection**

## Technical Details

### OperationView Class

```python
class OperationView(Container):
    def show_text(title, body):
        # Display static text content
        
    def show_list(title, description, items, action_callback):
        # Display interactive selectable list
        # When item is clicked, calls action_callback(item_name)
```

### Event Flow

1. User clicks menu item: `"Run profile"`
2. `_do_adhesive_profile()` called
3. Profiles discovered from filesystem
4. Operation View switches to **list mode**:
   ```python
   operation_view.show_list(
       "Available Adhesive Profiles",
       description,
       profiles,
       self._do_run_profile  # Callback
   )
   ```
5. User clicks profile in Operation View
6. Event handler detects `"oplist:profile_name"`
7. Calls `_do_run_profile(profile_name)`
8. Profile executes in background thread
9. Operation View switches back to **text mode** showing progress

## Benefits

✅ **Intuitive**: All interaction happens where you're looking (right panel)  
✅ **Clean**: Left menu stays simple, no nested dropdowns  
✅ **Flexible**: Can be applied to any operation needing selection  
✅ **Visual**: Clear presentation of available options  
✅ **Responsive**: Dashboard stays responsive during execution  

## Other Operations Using This Pattern

The same interactive list approach can be extended to:

- **Component Selection**: Show list of components to choose from
- **Device Selection**: Interactive checkbox list of discovered devices
- **Log File Viewing**: Select which log file to view
- **Crane Positions**: Select target position (coarse/intermediate/fine/target)

## Comparison with App.py

### App.py (CLI)
```python
# Uses Bullet menu for selection
cli = Bullet(
    prompt="\nSelect an adhesive profile:",
    choices=profiles + ["Back"],
    margin=2,
)
choice = cli.launch()
# Execute chosen profile
```

### Dashboard (TUI)
```python
# Uses interactive list in Operation View
operation_view.show_list(
    "Available Adhesive Profiles",
    description,
    profiles,
    self._do_run_profile
)
# User clicks in Operation View
# Profile executes automatically
```

**Result**: Same user experience, better visual presentation!

## Future Enhancements

This pattern opens up possibilities for:

- Multi-select lists (checkboxes for device selection)
- Input fields (for manual adhesive control values)
- Progress bars (profile execution progress)
- Confirmation dialogs (before dangerous operations)
- Tree views (hierarchical data like component positions)

## Usage Summary

### For Profile Execution

1. **Click**: `5 Adhesive Robot` → `Run profile`
2. **See**: List of available CSV profiles in Operation View
3. **Click**: Any profile name
4. **Watch**: Status Log for execution progress
5. **Done**: Profile completes, motors stop (0,0,0)

No external scripts, no dropdown menus on the left, everything happens in the Operation View! 🎯

## Code Structure

### Key Methods

- `OperationView.show_text()`: Display static content
- `OperationView.show_list()`: Display interactive list
- `on_list_view_selected()`: Handle clicks from any ListView
- Event name format: `"oplist:item_name"` for Operation View lists
- Callback pattern: Action method passed as callback to show_list()

### Styling

CSS classes:
- `#operation`: Main container
- `#op-content`: Static text content
- `#op-header`: List mode header
- `#op-list`: Interactive list widget
- `#op-list > ListItem.--highlight`: Selected item highlighting

The Operation View is now a true **workspace**, not just an information panel! 🚀
