import argparse
import json
import logging
import os
import signal
import sys
from typing import Type, Any
from parsimonious.exceptions import ParseError
from cosmic_ext_window_helper import Helper, Toplevel
from cosmic_ext_window_helper.conf import logger, __version__, __appname__, __description__, __toplevel_query__
from cosmic_ext_window_helper.exceptions import HelperError


class CLI(object):
    """CLI usage of cosmic-ext-window-helper."""
    info_handler: logging.StreamHandler
    error_handler: logging.StreamHandler
    parser: argparse.ArgumentParser
    commands: argparse._SubParsersAction
    helper: Helper
    cycling_toplevels: list[Toplevel]

    def __init__(self):
        self.cycling_toplevels = []

        sys.excepthook = self.exception_handler
        self._init_logs_handlers()
        self._init_args_parser()

    def _init_logs_handlers(self) -> None:
        """Configure log output in CLI usage."""
        self.info_handler = logging.StreamHandler(sys.stdout)
        self.info_handler.setLevel(logging.INFO)
        self.info_handler.addFilter(lambda x: x.levelno < logging.WARNING)
        self.error_handler = logging.StreamHandler()
        self.error_handler.setLevel(logging.WARNING)
        logger.addHandler(self.info_handler)
        logger.addHandler(self.error_handler)

    def _init_args_parser(self) -> None:
        """Configure arguments parsing."""
        self.parser = argparse.ArgumentParser(
            prog=__appname__,
            add_help=False,
            description=__description__,
            exit_on_error=False
        )
        self.commands = self.parser.add_subparsers(
            dest="action",
            metavar="COMMAND",
            required=True,
            help=(
                "Command to execute. Access detailed command usage by passing `-h` or `--help` after it."
            )
        )

        self.commands.add_parser(
            "state",
            help="List current toplevel windows state in JSON format.",
            description="List current toplevel windows state in JSON format."
        )
        self._add_toplevel_command(
            name="list",
            has_flag=False,
            info="List toplevel windows matching a query.",
            description="Return a JSON list. Use this command to test query matches."
        )

        self._add_toplevel_command(
            name="activate",
            has_flag=False,
            info="Bring toplevel windows into focus.",
            description=(
                "If multiple windows match your query, they will be given focus in the order the program "
                "has received them from Wayland compositor.\n"
                "Sadly it does not seem that this order currently follows any specific logic "
                "(like focus history)."
            )
        )
        self._add_toplevel_command(
            name="close",
            has_flag=False,
            info="Close toplevel windows."
        )

        self._add_toplevel_command(
            name="minimize",
            has_flag=True,
            info="Minimize toplevel windows or restore their initial state."
        )
        self._add_toplevel_command(
            name="maximize",
            has_flag=True,
            info="Maximize toplevel windows or restore their initial state."
        )
        self._add_toplevel_command(
            name="fullscreen",
            has_flag=True,
            info="Make toplevel windows fullscreen or restore their initial state."
        )
        self._add_toplevel_command(
            name="sticky",
            has_flag=True,
            info="Make toplevel windows sticky or restore their initial state."
        )

        move = self._add_toplevel_command(
            name="move_to",
            has_flag=False,
            info="Move toplevel windows to a specific workspace."
        )
        move.add_argument(
            "workspace",
            metavar="WORKSPACE",
            help="Name of the workspace to move windows to."
        )
        move.add_argument(
            "output",
            metavar="OUTPUT",
            help="Name of the output to move windows to."
        )

        cycle = self._add_toplevel_command(
            name="cycle",
            has_flag=False,
            info="Cycle through matching toplevel windows, bringing them one-by-one into focus at each call.",
            description=(
                "Temporary solution until this feature is natively available (expected in COSMIC™ Epoch 2).\n"
                "When first called, the program will activate the first non already active matching window and stay\n"
                "idle for the specified TIMEOUT (default: 3s). Any subsequent call within timeout will defer to\n"
                "the first process which will reset TIMEOUT and activate the next window, looping through matches."
            )
        )
        cycle.add_argument(
            "-t", "--timeout",
            metavar="TIMEOUT",
            default=3,
            type=int,
            help="Time to wait for signal from another instance."
        )

        # Development commands definitions
        self.commands.add_parser("debug", add_help=False)
        self.commands.add_parser("debugger", add_help=False)
        self.commands.add_parser("interfaces", add_help=False)
        self.commands.add_parser("update-protocols", add_help=False)

        # Global arguments
        help_group = self.parser.add_argument_group("Info arguments")
        help_group.add_argument(
            "-h", "--help",
            action="help",
            help="Display program usage."
        )
        help_group.add_argument(
            "-V",
            "--version",
            action="version",
            version=__version__,
            help="Display program version."
        )

    def _add_toplevel_command(
        self, name: str,  has_flag: bool, info: str, description: str = ""
    ) -> argparse.ArgumentParser:
        """Mutualize common configuration of commands targeting toplevels."""
        command = self.commands.add_parser(
            name,
            help=info,
            description=(info + ("\n" + description if description else "")),
            epilog=(__toplevel_query__),
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        if has_flag:
            command.add_argument(
                "toggle",
                metavar="TOGGLE",
                choices=["true", "false"],
                help="'true' or 'false' depending on whether you want to toggle the state on or off."
            )
        command.add_argument(
            "query",
            metavar="QUERY",
            help="Toplevel windows query, see full syntax below."
        )
        command.add_argument(
            "--log",
            metavar="LOGFILE",
            help=argparse.SUPPRESS
        )
        return command

    def run(self) -> None:
        """CLI entrypoint."""
        try:
            args = self.parser.parse_args(sys.argv[1:])
        except argparse.ArgumentError:
            self.parser.print_help()
            sys.exit(1)

        # Registering logfile if enabled
        if hasattr(args, "log") and args.log:
            if (
                (os.path.exists(args.log) and not os.access(args.log, os.W_OK)) or
                (not os.path.exists(args.log) and not os.access(os.path.dirname(args.log), os.W_OK))
            ):
                logger.error(f"You don't have permission to write on {args.log}")
                sys.exit(1)
            logfile = logging.FileHandler(args.log)
            logfile.setLevel(logging.INFO)
            logger.addHandler(logfile)

        # Handling actions not needing standard connection with compositor
        match args.action:
            case "cycle":
                if os.path.exists(self._pidfile()):
                    with open(self._pidfile()) as f:
                        pid = int(f.read().strip())
                    os.popen(f"kill -USR1 {pid}")
                    sys.exit(0)
            case "debug":
                logger.info("Listening to events from Wayland...")
                logger.info(
                    f"Execute `{__appname__} debugger` in another terminal to monitor them")
                logger.info("Press <Ctrl-C> to stop execution.")
                self.helper = Helper(debug=True)
            case "debugger":
                Helper.debugger()
            case "update-protocols":
                Helper.update_protocols()

        # Handling standard actions
        self.helper = Helper()
        if hasattr(args, "query"):
            try:
                toplevels = self.helper.match_toplevels(args.query)
            except ParseError as e:
                raise HelperError("Invalid query syntax.") from e
            if not toplevels:
                logger.error("No match found in current toplevel windows.")
                sys.exit(10)
        match args.action:
            case "state" | "list":
                print(json.dumps(self.helper.state(toplevels if args.action == "list" else None), indent=2))
            case "activate" | "close":
                toplevels.reverse()
                for toplevel in toplevels:
                    getattr(toplevel, args.action)()
            case "cycle":
                active = next((x for x in toplevels if x.is_active), None)
                self.cycling_toplevels = [x for x in toplevels if not x.is_active]
                if active is not None:
                    if not self.cycling_toplevels:
                        sys.exit(0)
                    self.cycling_toplevels.append(active)

                def signal_handler(sig_num, curr_stack_frame):
                    pass

                signal.signal(signal.SIGUSR1, signal_handler)
                with open(self._pidfile(), "w") as f:
                    f.write(str(os.getpid()))
                while True:
                    toplevel = self.cycling_toplevels.pop(0)
                    self.cycling_toplevels.append(toplevel)
                    toplevel.activate()
                    sig = signal.sigtimedwait([signal.SIGUSR1], args.timeout)
                    if sig is None:
                        if os.path.exists(self._pidfile()):
                            os.remove(self._pidfile())
                        break
            case "minimize" | "maximize" | "fullscreen" | "sticky":
                for toplevel in toplevels:
                    getattr(toplevel, args.action)(self.to_bool(args.toggle))
            case "move_to":
                output = next((
                    x for x in Helper.outputs.values()
                    if x.name == args.output
                ), None)
                if output is None:
                    raise HelperError(f"No output matches name '{args.output}'.")
                workspaces = [
                    x for x in Helper.workspaces.values()
                    if x.name == args.workspace
                ]
                if not workspaces:
                    raise HelperError(f"No workspace matches name '{args.workspace}'.")
                workspace = next((
                    x for x in workspaces
                    if x.output.name == args.output
                ), None)
                if not workspace:
                    raise HelperError(
                        f"No workspace matches name '{args.workspace}' on '{args.output}' output.")
                for toplevel in toplevels:
                    toplevel.move_to(workspace, output)
            case "interfaces":
                Helper.interfaces.sort()
                for interface in Helper.interfaces:
                    print(interface)

    @staticmethod
    def exception_handler(tp: Type[Exception], e: Exception, traceback) -> None:
        """Global exception handling for CLI usage."""
        if isinstance(e, HelperError):
            msg = e.msg + "\n"
            if hasattr(e, "details") and e.details:
                msg += e.details + "\n"
            sys.stderr.write(msg)
            sys.exit(e.exit_code)
        else:
            sys.__excepthook__(tp, e, traceback)

    @staticmethod
    def to_bool(v: Any) -> bool:
        return True if v in ["true", "True", "1"] else False

    @staticmethod
    def _pidfile() -> str:
        if not hasattr(CLI._pidfile, "file"):
            xrd = os.environ.get("XDG_RUNTIME_DIR")
            if xrd is None:
                raise HelperError("Unable to access XDG_RUNTIME_DIR environment var.")
            CLI._pidfile.file = os.path.sep.join([xrd, "cosmic-ext-window-helper-cycle.pid"])
        return CLI._pidfile.file


def main():
    try:
        CLI().run()
    except KeyboardInterrupt:
        raise SystemExit("Aborted.") from None
