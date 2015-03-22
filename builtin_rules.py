import os

from builtins import builtin
from languages import ext2lang
import node

class SourceFile(node.Node):
    def __init__(self, name, lang=None):
        node.Node.__init__(self, name)
        self.lang = lang

class ObjectFile(node.Node):
    def __init__(self, name, lang=None):
        node.Node.__init__(self, name)
        self.lang = lang

class Executable(node.Node):
    pass

class Library(node.Node):
    def __init__(self, name, external=False):
        node.Node.__init__(self, name)
        self.external = external

#####

class Compile(node.Edge):
    def __init__(self, target, file, options=None, deps=None):
        self.file = file
        self.options = options
        node.Edge.__init__(self, target, deps)

class Link(node.Edge):
    def __init__(self, target, files, libs=None, compile_options=None,
                 link_options=None, deps=None):
        self.files = files
        self.libs = [node.nodeify(i, Library, external=True)
                     for i in libs or []]
        self.compile_options = compile_options
        self.link_options = link_options

        node.Edge.__init__(self, target, deps)

class Alias(node.Edge):
    pass

class Command(node.Edge):
    def __init__(self, target, cmd, deps=None):
        self.cmd = cmd
        node.Edge.__init__(self, target, deps)

#####

@builtin
def object_file(name, file, options=None, lang=None, deps=None):
    if lang is None:
        lang = ext2lang.get( os.path.splitext(file)[1] )
    target = ObjectFile(name, lang)
    Compile(target, node.nodeify(file, SourceFile, lang=lang), options, deps)
    return target

@builtin
def object_files(files, lang=None, options=None):
    return [object_file(os.path.splitext(f)[0], file=f, lang=lang,
                        options=options) for f in files]

def _binary(target, files, libs=None, lang=None, compile_options=None,
           link_options=None, deps=None):
    Link(target, object_files(files=files, lang=lang, options=compile_options),
         libs, compile_options, link_options, deps)

@builtin
def executable(name, *args, **kwargs):
    target = Executable(name)
    _binary(target, *args, **kwargs)
    return target

@builtin
def library(name, *args, **kwargs):
    target = Library(name)
    _binary(target, *args, **kwargs)
    return target

@builtin
def alias(name, deps):
    target = node.Node(name)
    Alias(target, deps)
    return target

@builtin
def command(name, cmd, deps=None):
    target = node.Node(name)
    Command(target, cmd, deps)
    return target
