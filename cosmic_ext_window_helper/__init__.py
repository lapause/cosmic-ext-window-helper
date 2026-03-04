import argparse
import os
import re
import sys
from typing import Any
from importlib.util import find_spec
from modshim import shim
from parsimonious.nodes import NodeVisitor
from parsimonious.grammar import Grammar
from cosmic_ext_window_helper.conf import logger, resource_path
from cosmic_ext_window_helper.exceptions import HelperError

shim(lower="wayland.client.package", upper="cosmic_ext_window_helper.wayland.package", mount="wayland.client.package")
shim(lower="wayland.proxy", upper="cosmic_ext_window_helper.wayland.proxy", mount="wayland.proxy")
import wayland  # noqa: E402
from wayland.client import is_wayland  # noqa: E402

__all__ = ["Helper"]


@wayland.client.wayland_class("wl_registry")
class Registry(wayland.wl_registry):
    def on_global(self, name: int, interface: str, version: int) -> None:
        Helper.interfaces.append(f"{interface}@{version}")
        match interface:
            case "wl_output":
                output = self.bind(name, interface, version)
                Helper.outputs[output.object_id] = output
            case "wl_seat":
                Helper.seat = self.bind(name, interface, version)
            case "ext_workspace_manager_v1":
                Helper.workspace_manager = self.bind(name, interface, version)
            case "ext_foreign_toplevel_list_v1":
                self.bind(name, interface, version)
            case "zcosmic_toplevel_info_v1":
                Helper.toplevel_info = self.bind(
                    name, interface, Helper.ZCOSMIC_TOPLEVEL_INFO_V1_VERSION)
            case "zcosmic_toplevel_manager_v1":
                Helper.toplevel_manager = self.bind(
                    name, interface, Helper.ZCOSMIC_TOPLEVEL_MANAGER_V1_VERSION)


@wayland.client.wayland_class("wl_output")
class Output(wayland.wl_output):
    name: str
    done: bool

    def __init__(self):
        super().__init__()
        self.name = None
        self.done = False

    def on_name(self, name: str) -> None:
        self.name = name

    def on_done(self) -> None:
        self.done = True

    @property
    def has_focus(self):
        return Helper.active_toplevel is not None and Helper.active_toplevel.output == self

    def keys(self) -> list:
        return ["name", "has_focus"]

    def __getitem__(self, key) -> Any:
        return getattr(self, key)


@wayland.client.wayland_class("ext_workspace_handle_v1")
class Workspace(wayland.ext_workspace_handle_v1):
    _remote_object_id: int
    name: str
    group: "WorkspaceGroup"
    state: wayland.ext_workspace_handle_v1.state

    def __init__(self, object_id: int = None):
        if object_id:
            self._remote_object_id = object_id
        super().__init__()
        self.name = self.group = self.state = None

    def on_name(self, name) -> None:
        self.name = name

    def on_state(self, state: wayland.ext_workspace_handle_v1.state) -> None:
        self.state = state

    @property
    def is_visible(self) -> bool:
        return self.state == Helper.WORKSPACE_ACTIVE

    @property
    def has_focus(self) -> bool:
        return Helper.active_toplevel is not None and Helper.active_toplevel.workspace == self

    @property
    def output(self) -> Output:
        return self.group.output

    def keys(self) -> list:
        return ["name", "is_visible", "has_focus"]

    def __getitem__(self, key) -> Any:
        return getattr(self, key)


@wayland.client.wayland_class("ext_workspace_group_handle_v1")
class WorkspaceGroup(wayland.ext_workspace_group_handle_v1):
    _remote_object_id: int
    output: Output
    workspaces: dict[Workspace]

    def __init__(self, object_id: int = None):
        if object_id:
            self._remote_object_id = object_id
        super().__init__()
        self.output = None
        self.workspaces = {}

    def on_output_enter(self, output: Output) -> None:
        self.output = output

    def on_workspace_enter(self, workspace: Workspace | int) -> None:
        if isinstance(workspace, int):
            self.workspaces[workspace] = None
        else:
            self.workspaces[workspace.object_id] = workspace
            workspace.group = self


@wayland.client.wayland_class("ext_workspace_manager_v1")
class WorkspaceManager(wayland.ext_workspace_manager_v1):
    done: bool

    def __init__(self):
        super().__init__()
        self.done = False

    def on_workspace_group(self, workspace_group: WorkspaceGroup) -> None:
        Helper.workspaces_groups[workspace_group.object_id] = workspace_group

    def on_workspace(self, workspace: Workspace) -> None:
        Helper.workspaces[workspace.object_id] = workspace

    def on_done(self) -> None:
        self.done = True


@wayland.client.wayland_class("zcosmic_toplevel_info_v1")
class ToplevelInfo(wayland.zcosmic_toplevel_info_v1):
    done: bool

    def __init__(self):
        super().__init__()
        self.done = False

    def on_done(self) -> None:
        self.done = True


@wayland.client.wayland_class("ext_foreign_toplevel_handle_v1")
class ToplevelHandle(wayland.ext_foreign_toplevel_handle_v1):
    _remote_object_id: int
    id: str
    app_id: str
    title: str
    done: bool

    def __init__(self, object_id=None):
        if object_id:
            self._remote_object_id = object_id
        super().__init__()
        self.id = self.app_id = self.title = None
        self.done = False

    def on_identifier(self, identifier: str) -> None:
        self.id = identifier

    def on_app_id(self, app_id: str) -> None:
        self.app_id = app_id

    def on_title(self, title: str) -> None:
        self.title = title

    def on_done(self) -> None:
        self.done = True


@wayland.client.wayland_class("zcosmic_toplevel_handle_v1")
class ToplevelCosmicHandle(wayland.zcosmic_toplevel_handle_v1):
    states: list
    workspace: Workspace

    def __init__(self):
        super().__init__()
        self.states = []
        self.workspace = None

    def on_state(self, state: list) -> None:
        self.states = state

    def on_ext_workspace_enter(self, workspace: Workspace) -> None:
        self.workspace = workspace


@wayland.client.wayland_class("ext_foreign_toplevel_list_v1")
class ToplevelList(wayland.ext_foreign_toplevel_list_v1):
    def on_toplevel(self, toplevel: ToplevelHandle) -> None:
        Helper.toplevels[toplevel.object_id] = Toplevel(toplevel)


class Toplevel:
    handle: ToplevelHandle
    cosmic_handle: ToplevelCosmicHandle

    def __init__(self, handle: ToplevelHandle):
        self.handle = handle
        self.cosmic_handle = Helper.toplevel_info.get_cosmic_toplevel(handle)

    def activate(self) -> None:
        Helper.toplevel_manager.activate(self.cosmic_handle, Helper.seat)

    def close(self) -> None:
        Helper.toplevel_manager.close(self.cosmic_handle)

    def minimize(self, toggle: bool = True) -> None:
        if toggle:
            Helper.toplevel_manager.set_minimized(self.cosmic_handle)
        else:
            Helper.toplevel_manager.unset_minimized(self.cosmic_handle)

    def maximize(self, toggle: bool = True) -> None:
        if toggle:
            Helper.toplevel_manager.set_maximized(self.cosmic_handle)
        else:
            Helper.toplevel_manager.unset_maximized(self.cosmic_handle)

    def fullscreen(self, toggle: bool = True) -> None:
        if toggle:
            Helper.toplevel_manager.set_fullscreen(self.cosmic_handle, self.output)
        else:
            Helper.toplevel_manager.unset_fullscreen(self.cosmic_handle)

    def sticky(self, toggle: bool = True) -> None:
        if toggle:
            Helper.toplevel_manager.set_sticky(self.cosmic_handle)
        else:
            Helper.toplevel_manager.unset_sticky(self.cosmic_handle)

    def move_to(self, workspace: Workspace, output: Output) -> None:
        Helper.toplevel_manager.move_to_ext_workspace(self.cosmic_handle, workspace, output)

    def __getattr__(self, name: str) -> Any:
        match name:
            case "id" | "app_id" | "title":
                return getattr(self.handle, name)
            case "is_active":
                return Helper.TOPLEVEL_ACTIVATED in self.cosmic_handle.states
            case "is_active_app_id":
                return Helper.active_toplevel.app_id == self.app_id
            case "is_maximized":
                return Helper.TOPLEVEL_MAXIMIZED in self.cosmic_handle.states
            case "is_minimized":
                return Helper.TOPLEVEL_MINIMIZED in self.cosmic_handle.states
            case "is_fullscreen":
                return Helper.TOPLEVEL_FULLSCREEN in self.cosmic_handle.states
            case "is_sticky":
                return Helper.TOPLEVEL_STICKY in self.cosmic_handle.states
            case "workspace":
                return self.cosmic_handle.workspace
            case "output":
                return self.cosmic_handle.workspace.output if self.cosmic_handle.workspace else None
            case _:
                return self.__dict__[name]

    def keys(self) -> list:
        return [
            "id", "app_id", "title",
            "is_active", "is_active_app_id",
            "is_maximized", "is_minimized", "is_fullscreen", "is_sticky",
            "workspace", "output"
        ]

    def __getitem__(self, key) -> Any:
        if key == "workspace":
            return dict(self.workspace) if self.workspace else None
        if key == "output":
            return dict(self.output) if self.output else None
        return self.__getattr__(key)


class Helper:
    ZCOSMIC_TOPLEVEL_INFO_V1_VERSION = 3
    ZCOSMIC_TOPLEVEL_MANAGER_V1_VERSION = 4

    WORKSPACE_ACTIVE = 1
    WORKSPACE_URGENT = 2
    WORKSPACE_HIDDEN = 4
    TOPLEVEL_MAXIMIZED = 0
    TOPLEVEL_MINIMIZED = 1
    TOPLEVEL_ACTIVATED = 2
    TOPLEVEL_FULLSCREEN = 3
    TOPLEVEL_STICKY = 4

    interfaces: list[str] = []
    display: wayland.wl_display = None
    registry: Registry = None
    toplevel_info: ToplevelInfo = None
    toplevel_manager: wayland.zcosmic_toplevel_manager_v1 = None
    workspace_manager: WorkspaceManager = None

    outputs: dict[Output] = {}
    seat: wayland.wl_seat = None
    workspaces: dict[Workspace] = {}
    workspaces_groups: dict[WorkspaceGroup] = {}
    toplevels: dict[Toplevel] = {}
    active_toplevel: Toplevel = None

    def __init__(self, debug: bool = False):
        if not is_wayland():
            raise HelperError("Unable to detect Wayland environment.")

        if debug:
            wayland.client.start_debug_server()

        Helper.display = wayland.wl_display()
        Helper.registry = Helper.display.get_registry()
        while (
            True if debug else (
                not Helper.seat or
                not Helper.workspace_manager or
                (Helper.toplevels and not Helper.workspace_manager.done) or
                not Helper.toplevel_info or
                (Helper.toplevels and not Helper.toplevel_info.done) or
                not Helper.toplevel_manager or (
                    Helper.outputs and
                    not all(output.done for output in Helper.outputs.values())
                ) or (
                    Helper.toplevels and
                    not all(toplevel.handle.done for toplevel in Helper.toplevels.values())
                )
            )
        ):
            self.display.dispatch_timeout(0.1)
        for group in Helper.workspaces_groups.values():
            for wid, workspace in group.workspaces.items():
                if workspace is None:
                    group.workspaces[wid] = Helper.workspaces[wid]
                    Helper.workspaces[wid].group = group
            if isinstance(group.output, int):
                group.output = Helper.outputs[group.output]
        for toplevel in Helper.toplevels.values():
            if isinstance(toplevel.cosmic_handle.workspace, int):
                toplevel.cosmic_handle.workspace = Helper.workspaces[toplevel.cosmic_handle.workspace]
        Helper.active_toplevel = next(
            (x for x in self.toplevels.values() if x.is_active), None)

    def match_toplevels(self, query: str) -> list[Toplevel]:
        """
        Return a list of toplevel windows matching a query.
        @see cosmic_ext_window_helper.conf.__toplevel_query__ for detailed query syntax
        """
        grammar = Grammar(
            r"""
            expr           = (str_test / bool_test / block) (lop (str_test / bool_test / block))*
            block          = neg? "(" ws expr ws ")"
            bool_test      = neg? bool_field
            str_test       = neg? str_field op value
            op             = ws ("~=" / "!=" / "=") ws
            str_field      = ~"(app_)?id|title|(output|workspace)\\.name"
            bool_field     = ~"is_(active(_app_id)?|(min|max)imized|fullscreen|sticky)|output\\.has_focus|workspace\\.(is_visible|has_focus)"
            value          = single_quoted / double_quoted
            lop            = ws ("and" / "or") ws
            neg            = ws "not" ws
            ws             = ~"\\s*"
            single_quoted  = ~"'(.*?)(?<!\\\\)'i?"
            double_quoted  = ~'"(.*?)(?<!\\\\)"i?'
            """
        )

        class ExpressionVisitor(NodeVisitor):
            toplevel: Toplevel

            def __init__(self, toplevel: Toplevel):
                self.toplevel = toplevel

            def generic_visit(self, node, children):
                return children or node

            def visit_str_test(self, node, _):
                neg, field, op, value = node.children
                field = field.text
                if field.startswith("output."):
                    if self.toplevel.output:
                        field = self.toplevel.output[field.split(".")[1]]
                    else:
                        field = ""
                elif field.startswith("workspace."):
                    if self.toplevel.workspace:
                        field = self.toplevel.workspace[field.split(".")[1]]
                    else:
                        field = ""
                else:
                    field = self.toplevel[field]
                op = op.text.strip()
                if value.text[-1] == "i":
                    value = value.text[1:-2]
                    re_flags = re.IGNORECASE
                else:
                    re_flags = 0
                    value = value.text[1:-1]
                match op:
                    case "=":
                        res = field == value
                        if re_flags == re.IGNORECASE:
                            res = res | (field.lower() == value.lower())
                    case "!=":
                        res = field != value
                        if re_flags == re.IGNORECASE:
                            res = res & (field.lower() != value.lower())
                    case "~=":
                        res = bool(re.search(re.compile(value, re_flags), field))
                return res if neg.text == "" else not res

            def visit_bool_test(self, node, _):
                neg, field = node.children
                field = field.text
                if field.startswith("output."):
                    if self.toplevel.output:
                        field = self.toplevel.output[field.split(".")[1]]
                    else:
                        field = False
                elif field.startswith("workspace."):
                    if self.toplevel.workspace:
                        field = self.toplevel.workspace[field.split(".")[1]]
                    else:
                        field = False
                else:
                    field = self.toplevel[field]
                return field if neg.text == "" else not field

            def visit_block(self, node, children):
                res = children[3]
                return res if node.children[0].text == "" else not res

            def visit_lop(self, node, _):
                return node.text.strip()

            def visit_expr(self, _, children):
                items = self.reduce(children)
                res = items.pop(0)
                while len(items) >= 2:
                    match items.pop(0):
                        case "or":
                            res = res | items.pop(0)
                        case "and":
                            res = res & items.pop(0)
                return res

            @staticmethod
            def reduce(v: list) -> list:
                return sum(map(ExpressionVisitor.reduce, v), []) if isinstance(v, list) else [v]

        tree = grammar.parse(query)
        return [x for x in Helper.toplevels.values() if ExpressionVisitor(x).visit(tree)]

    def state(self, toplevels: list[Toplevel] = None) -> list[dict]:
        """
        Return a list of dictionnaries describing toplevels state.
        If no toplevels list is provided, information is returned for all current toplevels.
        """
        if toplevels is None:
            toplevels = self.toplevels.values()
        return [dict(x) for x in toplevels]

    @staticmethod
    def debugger() -> None:
        """
        Start python-wayland debugger.
        """
        if find_spec("textual") is None:
            raise HelperError(
                "Dependencies missing, this command needs to be started from `dev` environment.")
        from wayland.client.debug.gui import DebuggerClient  # noqa: PLC0415
        DebuggerClient(socket_name="python-wayland-debug").run()

    @staticmethod
    def update_protocols() -> None:
        """
        Update local Wayland & COSMIC™ protocols data.
        """
        if find_spec("lxml") is None:
            raise HelperError(
                "Dependencies missing, this command needs to be started from `dev` environment.")
        import wayland.parser  # noqa: PLC0415
        from wayland.__main__ import process_protocols  # noqa: F811, PLC0415
        logger.info("Generating Wayland & COSMIC™ protocols data...")
        wayland.parser.REMOTE_PROTOCOL_SOURCES.append({
            "name": "COSMIC™ Protocol Extensions",
            "url": "https://github.com/pop-os/cosmic-protocols",
            "dirs": ["unstable"],
            "ignore": ["cosmic-workspace-unstable-v1.xml"]
        })
        process_protocols(
            wayland.parser.WaylandParser(),
            argparse.Namespace(download=True, minimise=True)
        )
        if os.path.exists(resource_path("__init__.pyi")):
            os.remove(resource_path("__init__.pyi"))
        logger.info("Local protocols.json has been updated, exiting.")
        sys.exit(0)
