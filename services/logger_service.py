import logging
import os

logger = logging.getLogger(__name__)


class ModulePathFormatter(logging.Formatter):
    def format(self, record):
        # Convert the file path to a module-like path
        content_root = os.getcwd()
        relative_path = os.path.relpath(record.pathname, content_root)
        module_path = relative_path.replace(os.sep, ".").rsplit(".py", 1)[0]
        record.module_path = module_path
        return super().format(record)
