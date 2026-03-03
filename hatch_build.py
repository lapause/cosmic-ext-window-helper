import sys
import importlib.util
from hatchling.metadata.plugin.interface import MetadataHookInterface


class MetaDataHook(MetadataHookInterface):
    def update(self, metadata):
        spec = importlib.util.spec_from_file_location(
            "cosmic_ext_window_helper.conf",
            "./cosmic_ext_window_helper/conf.py"
        )
        conf = importlib.util.module_from_spec(spec)
        sys.modules["cosmic_ext_window_helper.conf"] = conf
        spec.loader.exec_module(conf)
        metadata["version"] = conf.__version__
        metadata["description"] = conf.__description__
