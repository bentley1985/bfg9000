import os.path
import re

from . import ar, cc, msvc
from .. import shell
from .hooks import builder
from .utils import check_which
from ..languages import language

language('c', exts=['.c'], link=['c', 'c++', 'objc', 'objc++'])
language('c++', exts=['.cpp', '.cc', '.cp', '.cxx', '.CPP', '.c++', '.C'],
         link=['c++', 'objc++'])
language('objc', exts=['.m'], link=['objc', 'objc++'])
language('objc++', exts=['.mm', '.M'], link=['objc++'])

# XXX: Currently, we tie the linker to a single language, much like the
# compiler. However, linkers can generally take object files made from multiple
# source languages. We should figure out what the correct thing to do here is.


@builder('c', 'c++', 'objc', 'objc++')
class CFamilyBuilder(object):
    __langs = {
        'c'     : ('CC'    , 'cc' ),
        'c++'   : ('CXX'   , 'c++'),
        'objc'  : ('OBJC'  , 'cc' ),
        'objc++': ('OBJCXX', 'c++'),
    }

    def __init__(self, env, lang):
        var, default_cmd = self.__langs[lang]
        low_var = var.lower()
        if env.platform.name == 'windows' and lang in ('c', 'c++'):
            default_cmd = 'cl'
        cmd = env.getvar(var, default_cmd)
        check_which(cmd, kind='{} compiler'.format(lang))

        cflags = (
            shell.split(env.getvar(var + 'FLAGS', '')) +
            shell.split(env.getvar('CPPFLAGS', ''))
        )
        ldflags = shell.split(env.getvar('LDFLAGS', ''))
        ldlibs = shell.split(env.getvar('LDLIBS', ''))

        if re.search(r'cl(\.exe)?$', cmd):
            origin = os.path.dirname(cmd)
            link_cmd = env.getvar(var + '_LINK', os.path.join(origin, 'link'))
            lib_cmd = env.getvar(var + '_LIB', os.path.join(origin, 'lib'))
            check_which(link_cmd, kind='{} linker'.format(lang))
            check_which(lib_cmd, kind='{} static linker'.format(lang))

            self.compiler = msvc.MsvcCompiler(env, lang, low_var, cmd, cflags)
            self.linkers = {
                'executable': msvc.MsvcExecutableLinker(
                    env, lang, low_var, link_cmd, ldflags, ldlibs
                ),
                'shared_library': msvc.MsvcSharedLibraryLinker(
                    env, lang, low_var, link_cmd, ldflags, ldlibs
                ),
                'static_library': msvc.MsvcStaticLinker(
                    env, lang, low_var, lib_cmd
                ),
            }
            self.packages = msvc.MsvcPackageResolver(env, lang)
        else:
            self.compiler = cc.CcCompiler(env, lang, low_var, cmd, cflags)
            self.linkers = {
                'executable': cc.CcExecutableLinker(
                    env, lang, low_var, cmd, ldflags, ldlibs
                ),
                'shared_library': cc.CcSharedLibraryLinker(
                    env, lang, low_var, cmd, ldflags, ldlibs
                ),
                'static_library': ar.ArLinker(env, lang),
            }
            self.packages = cc.CcPackageResolver(env, lang, cmd)
