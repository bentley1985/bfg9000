import json
import os

from . import platforms
from .builders import ar
from .builders import cc
from .builders import msvc

class EnvVersionError(RuntimeError):
    pass

class Environment(object):
    version = 2
    envfile = '.bfg_environ'

    bfgfile = 'bfg9000'
    scanfile = 'arachnotron'

    def __init__(self, bfgdir, backend, srcdir, builddir, install_prefix):
        self.bfgpath = os.path.join(bfgdir, self.bfgfile)
        self.scanpath = os.path.join(bfgdir, self.scanfile)
        self.backend = backend

        self.srcdir = srcdir
        self.builddir = builddir
        self.install_prefix = install_prefix

        self.variables = dict(os.environ)
        self.platform = platforms.platform_info(platforms.platform_name())
        self.__init_compilers()

    def __init_compilers(self):
        # TODO: Come up with a more flexible way to initialize the compilers and
        # linkers for each language.
        if self.platform.name == 'windows':
            compiler = msvc.MSVCCompiler(self)
            exe_linker = msvc.MSVCLinker(self, 'executable')
            lib_linker = msvc.MSVCStaticLinker(self)
            dll_linker = msvc.MSVCLinker(self, 'shared_library')
            self.__compilers = {
                'c'  : compiler,
                'c++': compiler,
            }
            self.__linkers = {
                'executable': {
                    'c'  : exe_linker,
                    'c++': exe_linker,
                },
                'static_library': {
                    'c'  : lib_linker,
                    'c++': lib_linker,
                },
                'shared_library': {
                    'c'  : dll_linker,
                    'c++': dll_linker,
                },
            }
        else:
            ar_linker = ar.ArLinker(self)
            self.__compilers = {
                'c'  : cc.CcCompiler(self),
                'c++': cc.CxxCompiler(self),
            }
            self.__linkers = {
                'executable': {
                    'c'  : cc.CcLinker(self, 'executable'),
                    'c++': cc.CxxLinker(self, 'executable'),
                },
                'static_library': {
                    'c'  : ar_linker,
                    'c++': ar_linker,
                },
                'shared_library': {
                    'c'  : cc.CcLinker(self, 'shared_library'),
                    'c++': cc.CxxLinker(self, 'shared_library'),
                },
            }

    def getvar(self, key, default=None):
        return self.variables.get(key, default)

    @property
    def bin_dirs(self):
        return self.getvar('PATH', os.defpath).split(os.pathsep)

    @property
    def bin_exts(self):
        # XXX: Create something to manage host-platform stuff like this?
        # (`platforms.Platform` is for targets.)
        plat = platforms.platform_name()
        if plat == 'windows' or plat == 'cygwin':
            return self.getvar('PATHEXT', '').split(os.pathsep)
        else:
            return ['']

    @property
    def lib_dirs(self):
        return (self.getvar('LIBRARY_PATH', '').split(os.pathsep) +
                self.platform.lib_dirs)

    def compiler(self, lang):
        return self.__compilers[lang]

    def linker(self, lang, mode):
        if isinstance(lang, basestring):
            return self.__linkers[mode][lang]

        if not isinstance(lang, set):
            lang = set(lang)
        # TODO: Be more intelligent about this when we support more languages
        if 'c++' in lang:
            return self.__linkers[mode]['c++']
        return self.__linkers[mode]['c']

    def save(self, path):
        with open(os.path.join(path, self.envfile), 'w') as out:
            json.dump({
                'version': self.version,
                'data': {
                    'bfgpath': self.bfgpath,
                    'scanpath': self.scanpath,
                    'backend': self.backend,
                    'srcdir': self.srcdir,
                    'builddir': self.builddir,
                    'install_prefix': self.install_prefix,
                    'platform': self.platform.name,
                    'variables': self.variables,
                }
            }, out)

    @classmethod
    def load(cls, path):
        with open(os.path.join(path, cls.envfile)) as inp:
            state = json.load(inp)
        if state['version'] > cls.version:
            raise EnvVersionError('saved version exceeds expected version')
        if state['version'] == 1:
            state['data']['scanpath'] = os.path.join(
                state['data']['bfgpath'], cls.scanfile
            )
            state['data']['platform'] = platforms.platform_name()

        env = Environment.__new__(Environment)
        for k, v in state['data'].iteritems():
            if k == 'platform':
                env.platform = platforms.platform_info(v)
            else:
                setattr(env, k, v)
        env.__init_compilers()
        return env
