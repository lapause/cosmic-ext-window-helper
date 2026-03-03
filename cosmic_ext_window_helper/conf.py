import os
import logging

__appname__ = "cosmic-ext-window-helper"
__version__ = "0.1.0"
__description__ = (
    "Utility interacting with COSMIC™ Wayland compositor to provide easy scriptable access "
    "to toplevel windows, allowing shortcut-triggerable custom actions: run-or-raise, batch hiding or closing..."
)
__toplevel_query__ = """TOPLEVEL WINDOWS QUERY SYNTAX
Use `state` command to see what current windows information looks like.

1) string fields tests: FIELD OPERATOR VALUE
   Available fields:
     id:             toplevel unique ID
     app_id:         window class, usually unique by application
     title:          current window title
     workspace.name: currently a number starting at 1 corresponding to the workspace position
                     (global or per display according to your configuration)
     output.name:    unique display name, usually a combination of display protocol and a number
                     Predictable while your display connections remain the same.
   Available operators:
     =   : equal to
     !=  : different than
     ~=  : regex match
   Values:
     - must be quoted (single or double quotes)
     - are case sensitive by default
       you can suffix the quoted value with 'i' to perform case-insensitive tests.
   Examples:
     "app_id = 'firefox'"
     "title ~= 'work|documents'i"
     "output.name != 'HDMI-1'"

2) boolean fields tests: FIELD
   Available fields:
     is_active:           window has focus
     is_active_app_id:    window app_id is the same as the active window one
     is_maximized:        window is currently maximized
     is_minimized:        window is currently minimized
     is_fullscreen:       window is currently fullscreen
     is_sticky:           window is currently sticky
     workspace.visible:   window is in a visible workspace
     workspace.has_focus: workspace the window is in also contains the active window
     output.has_focus:    display the window is in also contains the active window

3) Negation, logical operators and groups
   - tests can be combined with 'and' and 'or' operators
   - tests can be grouped with braces
   - tests and groups can be negated using a 'not' prefix

4) Examples
   - Target all visible windows except the active one or Cosmic terminals:
     "workspace.is_visible and not (is_active or app_id = 'com.system76.CosmicTerm')"
   - Target all Cosmic Files windows opened on 'Work' or 'src' directories:
     "app_id = 'com.system76.CosmicFiles' and title ~= '^(Work|src) —'"
   - Target all non minimized Firefox windows whose title contains 'python':
     "app_id = 'firefox' and title ~= 'python'i and not is_minimized"
"""

logger = logging.getLogger(__appname__)
logger.setLevel(logging.INFO)


def resource_path(path: str = ""):
    """
    Convert a relative path from package root to an absolute path.
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), path))
