import fnmatch
import itertools
import os
import posixpath
import re
from enum import IntEnum

from .hooks import builtin
from ..iterutils import iterate, listify
from ..backends.make import writer as make
from ..backends.ninja import writer as ninja
from ..backends.make.syntax import Writer, Syntax
from ..build_inputs import build_input
from ..path import Path
from ..platforms import known_platforms

build_input('find_dirs')(lambda build_inputs, env: set())
depfile_name = '.bfg_find_deps'


@builtin
class FindResult(IntEnum):
    include = 0
    not_now = 1
    exclude = 2


def write_depfile(path, output, seen_dirs, makeify=False):
    with open(path, 'w') as f:
        out = Writer(f)
        out.write(output, Syntax.target)
        out.write_literal(':')
        for i in seen_dirs:
            out.write_literal(' ')
            out.write(os.path.abspath(i), Syntax.dependency)
        out.write_literal('\n')
        if makeify:
            for i in seen_dirs:
                out.write(os.path.abspath(i), Syntax.target)
                out.write_literal(':\n')


def _listdir(path):
    dirs, nondirs = [], []
    try:
        names = os.listdir(path)
        for name in names:
            # Use POSIX paths so that the result is platform-agnostic.
            curpath = posixpath.join(path, name)
            if os.path.isdir(curpath):
                dirs.append((name, curpath))
            else:
                nondirs.append((name, curpath))
    except:
        pass
    return dirs, nondirs


def _walk_flat(top):
    yield (top,) + _listdir(top)


def _walk_recursive(top):
    dirs, nondirs = _listdir(top)
    yield top, dirs, nondirs
    for name, path in dirs:
        if not os.path.islink(path):
            for i in _walk_recursive(path):
                yield i


def _filter_from_glob(match_type, match_names, match_extra):
    matches = [re.compile(fnmatch.translate(i)) for i in iterate(match_names)]
    extra = [re.compile(fnmatch.translate(i)) for i in iterate(match_extra)]

    def f(name, path, type):
        if match_type in [type, '*']:
            if any(ex.match(name) for ex in matches):
                return FindResult.include
            elif any(ex.match(name) for ex in extra):
                return FindResult.not_now
        return FindResult.exclude
    return f


def _find_files(paths, filter, flat):
    # "Does the walker choose the path, or the path the walker?" - Garth Nix
    walker = _walk_flat if flat else _walk_recursive

    results, extra_results, seen_dirs = [], [], []

    def do_filter(files, type):
        for name, path in files:
            matched = filter(name, path, type)
            if matched == FindResult.include:
                results.append(path)
            elif matched == FindResult.not_now:
                extra_results.append(path)

    paths = listify(paths)
    do_filter(( (p, p) for p in paths ), 'd')
    for p in paths:
        for base, dirs, files in walker(p):
            seen_dirs.append(base)
            do_filter(dirs, 'd')
            do_filter(files, 'f')

    return results, extra_results, seen_dirs


def find(path='.', name='*', type='*', flat=False):
    return _find_files(path, _filter_from_glob(name, type), flat)[0]


@builtin.globals('env')
def filter_by_platform(env, name, path, type):
    my_plat = set([env.platform.name, env.platform.flavor])
    sub = '|'.join(re.escape(i) for i in known_platforms if i not in my_plat)
    ex = r'(^|/|_)(' + sub + r')(\.[^\.]$|$|/)'
    return FindResult.not_now if re.search(ex, path) else FindResult.include


@builtin.globals('builtins', 'build_inputs', 'env')
def find_files(builtins, build_inputs, env, path='.', name='*', type='*',
               extra=None, filter=filter_by_platform, flat=False, cache=True):
    glob_filter = _filter_from_glob(type, name, extra)
    if filter:
        if filter == filter_by_platform:
            filter = builtins['filter_by_platform']

        def final_filter(name, path, type):
            return max(filter(name, path, type), glob_filter(name, path, type))
    else:
        final_filter = glob_filter

    results, extra_results, seen_dirs = _find_files(path, final_filter, flat)

    for i in itertools.chain(results, extra_results):
        builtins['generic_file'](i)
    if cache:
        build_inputs['find_dirs'].update(seen_dirs)
    return results


@make.post_rule
def make_regenerate_rule(build_inputs, buildfile, env):
    bfg9000 = env.tool('bfg9000')
    bfgcmd = make.cmd_var(bfg9000, buildfile)

    if build_inputs['find_dirs']:
        write_depfile(Path(depfile_name).string(env.path_roots),
                      'Makefile', build_inputs['find_dirs'], makeify=True)
        buildfile.include(depfile_name)

    buildfile.rule(
        target=Path('Makefile'),
        deps=[build_inputs.bfgpath],
        recipe=[bfg9000.regenerate(bfgcmd, Path('.'))]
    )


@ninja.post_rule
def ninja_regenerate_rule(build_inputs, buildfile, env):
    bfg9000 = env.tool('bfg9000')
    bfgcmd = ninja.cmd_var(bfg9000, buildfile)
    depfile = None

    if build_inputs['find_dirs']:
        write_depfile(Path(depfile_name).string(env.path_roots),
                      'build.ninja', build_inputs['find_dirs'])
        depfile = depfile_name

    buildfile.rule(
        name='regenerate',
        command=bfg9000.regenerate(bfgcmd, Path('.')),
        generator=True,
        depfile=depfile,
    )
    buildfile.build(
        output=Path('build.ninja'),
        rule='regenerate',
        implicit=[build_inputs.bfgpath]
    )
