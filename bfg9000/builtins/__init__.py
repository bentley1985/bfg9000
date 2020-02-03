import importlib
import pkgutil
import warnings

from . import builtin
from .. import exceptions, log, path, safe_str
from ..objutils import memoize


@memoize
def init():
    # Import all the packages in this directory so their hooks get run.
    for _, name, _ in pkgutil.walk_packages(__path__, '.'):
        importlib.import_module(name, __package__)


@builtin.getter('env', name='env', context=('build', 'options'))
def getenv(env):
    return env


@builtin.function(context='*')
def warning(*args):
    warnings.warn(log.format_message(*args))


@builtin.function(context='*')
def info(*args, show_stack=False):
    log.log_message(log.INFO, *args, show_stack=show_stack, stacklevel=1)


@builtin.function(context='*')
def debug(*args, show_stack=True):
    log.log_message(log.DEBUG, *args, show_stack=show_stack, stacklevel=1)


for i in dir(exceptions):
    i = getattr(exceptions, i)
    if isinstance(i, type):
        builtin.function(context='*')(i)

for i in (path.Root, path.InstallRoot, safe_str.safe_str,
          safe_str.safe_format):
    builtin.function(context='*')(i)
builtin.function(context='*', name='Path')(path.Path)
