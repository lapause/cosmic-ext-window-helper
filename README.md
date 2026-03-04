# COSMIC™ Window Helper

Utility interacting with COSMIC™ Wayland compositor to provide easy scriptable access to toplevel windows, allowing shortcut-triggerable custom actions: run-or-raise, batch hiding or closing...

This tool is born out of the frustration of not being able to use the productivity shortcuts I crafted along the years using `xdotool`, `wmctrl`... after migrating to Pop_OS! 24.04 and COSMIC™ which is Wayland only.

I hope a similar tool will be in time available natively with COSMIC™, or at least coded in Rust to leverage [official COSMIC™ protocols bindings](https://github.com/pop-os/cosmic-protocols). In the meantime, not having fiddled with Rust yet I settled to use Python and leverage [Graham King](https://github.com/grking)'s [python-wayland](https://github.com/grking/python-wayland) library.

### Caveats
- Commands run with a small latency, due to the need to wait for all information to be sent by the compositor each time. An improvement would be to implement a small user service that would keep an up-to-date state of toplevels and listen to commands via socket, with the added benefit of maintaining window focus history for the `cycle` command. I have no time to do this now but will probably in the future.
- [python-wayland](https://github.com/grking/python-wayland) library seemed the best candidate for handling the heavy lifting of interacting with Wayland protocols, however as most of Wayland resources it is only a partial implementation. I've been forced to monkey-patch a few features, hopefully that will not be necessary in the future.


## Installation

The package is available in the [Python Package Index](https://pypi.org/project/cosmic-ext-window-helper/), install with your tool of choice:

```sh
# Using pipx
$ pipx install cosmic-ext-window-helper

# Using uv
$ uv tool install cosmic-ext-window-helper

# Using pip (not recommended, you should use isolated environments)
$ pip install cosmic-ext-window-helper
```


## Usage

### Window properties
Use the command `cosmic-ext-window-helper state` to return current windows information in JSON format. This will allow you to identify `app_id`s and output names you want to target.

```json
[
  {
    "id": "TaLIxAEMU1ONFC0BfP7GUn1MrPhoiBQ3",
    "app_id": "com.system76.CosmicTerm",
    "title": "cosmic-ext-window-helper state \u2014 COSMIC Terminal",
    "is_active": true,
    "is_active_app_id": true,
    "is_maximized": false,
    "is_minimized": false,
    "is_fullscreen": false,
    "is_sticky": false,
    "workspace": {
      "name": "1",
      "is_visible": true,
      "has_focus": true
    },
    "output": {
      "name": "DP-4",
      "has_focus": true
    }
  },
  ...
]
```

- `id`: Window unique ID
- `app_id`: Window class, usually unique by application
- `title`: Current window title
- `is_active`: Does the window has focus?
- `is_active_app_id`: Is the window `app_id` the same as the active window one?
- `is_maximized`: Is the window currently maximized?
- `is_minimized`: Is the window currently minimized?
- `is_fullscreen`: Is the window currently fullscreen?
- `is_sticky`: Is the window currently sticky?
- `workspace.name`: COSMIC™ name of the window workspace, currently a number starting at 1 corresponding to the workspace position (global or per display depending on your configuration)
- `workspace.visible`: Is the window workspace visible?
- `workspace.has_focus`: Does the window workspace also contains the active window?
- `output.name`: COSMIC™ unique name of the window display, usually a combination of display protocol and a number (e.g. `HDMI-1`, `DP-2`...) Predictable while your display connections remain the same.
- `output.has_focus`: Does the window display also contains the active window?

### Query syntax

To be the most flexible, the program commands use a `QUERY` argument to target toplevel windows. The query grammar supports:
- String field tests:
  - Syntax: `FIELD OPERATOR VALUE`
  - Available fields: `id`, `app_id`, `title`, `workspace.name`, `output.name`
  - Available operators: `=` (equal to), `!=` (different than) and `~=` (regex match)
  - Values:
    - must be quoted (single or double quotes)
    - are case sensitive by default. You can suffix the quoted value with 'i' to perform case-insensitive tests.
  - Examples:
    - `"app_id = 'firefox'"`
    - `"title ~= 'work|documents'i"`
    - `"output.name != 'HDMI-1'"`
- Boolean field tests:
  - Syntax: `FIELD`
  - Available fields: `is_active`, `is_active_app_id`, `is_maximized`, `is_minimized`, `is_fullscreen`, `is_sticky`, `workspace.visible`, `workspace.has_focus`, `output.has_focus`
- Negation, logical operators and groups
  - tests can be combined with 'and' and 'or' operators
  - tests can be grouped with braces
  - tests and groups can be negated using a `not` prefix
- Examples:
  - Target all visible windows except the active one or Cosmic terminals:

    `"workspace.is_visible and not (is_active or app_id = 'com.system76.CosmicTerm')"`
  - Target all Cosmic Files windows opened on 'Work' or 'src' directories:

    `"app_id = 'com.system76.CosmicFiles' and title ~= '^(Work|src) —'"`
  - Target all non minimized Firefox windows whose title contains 'python':

    `"app_id = 'firefox' and title ~= 'python'i and not is_minimized"`

And if you need extra logic that cannot be handled by the `QUERY` syntax, you can grab windows info via `state` command, perform your logic in a script/program and then trigger the action on specific identifiers:

```sh
cosmic-ext-window-helper activate "id = '8wQWFOaggZD0M2kU1YhvD1A4pzILPTYM' or id = 'bGppu8cUp91Ly8JCX1yT5ZG756Qmyp1z'"
# or
cosmic-ext-window-helper activate "id ~= '8wQWFOaggZD0M2kU1YhvD1A4pzILPTYM|bGppu8cUp91Ly8JCX1yT5ZG756Qmyp1z'"
```

### Commands

- `cosmic-ext-window-helper state`

  Return current windows information in JSON format

- `cosmic-ext-window-helper list QUERY`

  List toplevel windows like the `state` command, but return only those matching the query. Use it to test your queries.

- `cosmic-ext-window-helper activate QUERY`

  Bring matching toplevel windows into focus. If multiple windows match they will be activated in the reverse order they have been sent by the compositor to try to focus the last one used (no guarantee here, the compositor does not seem to always follow predictable logic).

  This command allows you to set up shortcuts implementing _run-or-raise_ logic. For example, executing:

  ```sh
  cosmic-ext-window-helper activate "app_id='firefox'" || firefox
  ```

  will activate Firefox windows if some exist or start Firefox.

- `cosmic-ext-window-helper close QUERY`

  Close matching toplevel windows. For example, you can set up a shortcut to close at once all the instances of the active application:

  ```sh
  cosmic-ext-window-helper close is_active_app_id
  ```

- `cosmic-ext-window-helper [minimize | maximize | fullscreen | sticky] TOGGLE QUERY`

  Toggle matching toplevel windows state. Usage examples:

  - Minimize all windows in the active window workspace, except the active one (equivalent to the `Hide others` shortcut on macOS):

    ```sh
    cosmic-ext-window-helper minimize true "not is_active and workspace.has_focus"
    ```

  - Restore all minimized windows in visible workspaces:

    ```sh
    cosmic-ext-window-helper minimize false "is_minimized and workspace.is_visible"
    ```

- `cosmic-ext-window-helper move_to QUERY WORKSPACE OUTPUT`

  Move matching toplevel windows to a specific workspace. For example, to move all COSMIC Terminal windows not maximized or fullscreen to the second workspace on your HDMI display:

  ```sh
  cosmic-ext-window-helper move_to "app_id='com.system76.CosmicTerm' and not (is_maximized or is_fullscreen)" 2 HDMI-1
  ```

- `cosmic-ext-window-helper cycle [-t TIMEOUT] QUERY`

  Cycle through matching windows, bringing them one-by-one into focus at each call. Temporary solution until this feature is natively available, at least for active application (expected in [COSMIC™ Epoch 2](https://blog.system76.com/post/cosmic-epoch-2-and-3-roadmap), see [ticket 961](https://github.com/pop-os/cosmic-settings/issues/961)).

  When first called, the program will activate the first non already active matching window and stay
idle for the specified `TIMEOUT` (default: 3s). Any subsequent call within timeout will defer to
the first process which will reset TIMEOUT and activate the next window, allowing looping through matches.

  For example, to cycle through active application windows:

  ```sh
  cosmic-ext-window-helper cycle is_active_app_id
  ```


## Running from source

The project uses [hatch](https://hatch.pypa.io) to setup its environment.

```sh
$ git clone https://github.com/lapause/cosmic-ext-window-helper.git
$ cd cosmic-ext-window-helper
$ hatch env create
$ hatch shell
$ cosmic-ext-window-helper --help
```

To start the program from outside of the project shell, add the project location to the `[projects]` section of your hatch config file (`~/.config/hatch/config.toml`):
```ini
cosmic-ext-window-helper = "/path/to/project/dir"
```
and run commands like this:
```sh
$ hatch -p cosmic-ext-window-helper run cosmic-ext-window-helper --help
```

### Development setup

Configure the `dev` environment in project directory:
```sh
$ hatch env create dev
$ hatch shell dev
```

The following special commands can be used in  `dev` environment:
```sh
# Stay in the loop dispatching events received from the compositor
$ cosmic-ext-window-helper debug

# <in another terminal, while debug is running>
# Open the debugger to view events and requests
$ cosmic-ext-window-helper debugger

# List interfaces made available by the compositor, along with their version
$ cosmic-ext-window-helper interfaces

# Update Wayland protocols from official sources
$ cosmic-ext-window-helper update-protocols
```


## Thanks and acknowledgements

Thanks to [Graham King](https://github.com/grking) for his [python-wayland](https://github.com/grking/python-wayland) library without which this project would not exist.

Thanks to [Michael Murphy](https://github.com/mmstick) at [System76](https://system76.com/) to have taken (and continue to take) time on Reddit to comment on so many posts, without stumbling on a few of those I would'nt have developed this.
