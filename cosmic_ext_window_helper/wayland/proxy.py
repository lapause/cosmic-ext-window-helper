import threading
from collections.abc import Callable
from queue import SimpleQueue
from wayland.proxy import Proxy as OriginalProxy


class Proxy(OriginalProxy):
    _thread_id = threading.current_thread().native_id

    class Event(OriginalProxy.Event):
        def __transform_args(self, packet: bytes, get_fd: Callable) -> dict:
            """
            Overridden to support dynamic object instanciation.
            """
            kwargs = {}
            self.packet = packet
            for arg in self.event_args:
                arg_type = arg["type"]
                enum_type = arg.get("enum")
                packet, value = self.__unpack_argument(
                    packet, arg_type, get_fd, enum_type
                )
                # For new_id args, instanciate and use the corresponding object. Constructor of
                # the custom class must implement 'object_id' named argument and store it in a
                # '_remote_object_id' property (see DynamicObject::__init() below
                # It's hacky but I could not find a better way to do the job without massive code
                # rewrite instead of patching a few methods.
                if arg_type == "new_id" and arg.get("interface"):
                    obj = Proxy().state.new_object(
                        Proxy().scope[arg.get("interface")],
                        object_id=value
                    )
                    kwargs[arg["name"]] = obj
                # Otherwise just use the value as it is
                else:
                    kwargs[arg["name"]] = value
            return kwargs

        def __thread_id(self) -> int:
            """
            Ugly hack to ensure that events related to objects created dynamically
            from compositor messages are bound to the original thread.
            Otherwise they are bound to the thread processing messages and thus never picked up
            by the dispatch loop.
            """
            tid = Proxy()._thread_id
            with self._lock:
                if tid not in self._event_handlers:
                    self._event_handlers[tid] = []
            with Proxy._event_lock:
                if tid not in Proxy._event_queues:
                    Proxy._event_queues[tid] = SimpleQueue()
            return tid

    class DynamicObject(OriginalProxy.DynamicObject):
        def __init__(
            self,
            *,
            pyw_name=None,
            pyw_scope=None,
            pyw_requests=None,
            pyw_events=None,
            pyw_state=None,
            **user_kwargs,
        ):
            """
            Overridden to bypass object_id allocation when creating object received from a
            response.
            """
            self._user_kwargs = user_kwargs

            if pyw_name is None:
                self.__smart_init(**user_kwargs)
                return

            self.__name = pyw_name
            self.__interface = pyw_name
            self.__scope = pyw_scope
            self.__state = pyw_state
            self.__requests = pyw_requests or []
            self.__events = pyw_events or []
            self.__object_id = 0

            # Object ID allocation bypass
            if hasattr(self, "_remote_object_id"):
                self.__state.assign_object_id(self._remote_object_id, self)
            else:
                self.__state.allocate_new_object_id(self)

            if pyw_name == "wl_display":
                self.__setup_display_methods()

            self.events = Proxy.Events()
            self.__bind_requests(self.__requests)
            self.__bind_events(self.__events)
            self.__register_event_handlers()
