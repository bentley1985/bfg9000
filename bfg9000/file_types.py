import os.path

from . import build_inputs
from .languages import ext2lang
from .path import Path

class SourceFile(build_inputs.File):
    def __init__(self, name, source, lang=None):
        build_inputs.File.__init__(self, name, source=source)
        if lang is None:
            lang = ext2lang.get( os.path.splitext(name)[1] )
        self.lang = lang

class HeaderFile(build_inputs.File):
    install_kind = 'data'
    install_root = Path.includedir

class HeaderDirectory(build_inputs.Directory):
    install_root = Path.includedir

class ObjectFile(build_inputs.File):
    def __init__(self, name, source, lang):
        build_inputs.File.__init__(self, name, source)
        self.lang = lang

class Binary(build_inputs.File):
    install_kind = 'program'

class Executable(Binary):
    install_root = Path.bindir

class Library(Binary):
    install_root = Path.libdir

    def __init__(self, name, source):
        Binary.__init__(self, name, source)

class StaticLibrary(Library):
    pass

class SharedLibrary(Library):
    def __init__(self, name, source, dll=None):
        Library.__init__(self, name, source)
        self.dll = dll

    def __iter__(self):
        # This allows a shared lib on Windows to be "flattened" into the
        # import lib and DLL for various functions like default() and install(),
        # which should apply to both by default.
        if self.dll is not None:
            yield self.dll
        yield self

# Used for Windows DLL files, which aren't linked to directly.
class DllLibrary(Library):
    pass
