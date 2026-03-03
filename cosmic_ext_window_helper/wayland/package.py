from cosmic_ext_window_helper.conf import resource_path


def get_package_root() -> str:
    """Overridden to store protocols locally."""
    return resource_path()
