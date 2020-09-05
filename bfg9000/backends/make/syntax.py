import re
from collections import namedtuple
from enum import Enum
from io import StringIO

from ... import path
from ... import safe_str
from ... import iterutils
from ...platforms.host import platform_info
from ...tools.common import Command

# XXX: Make currently only supports sh-style shells.
from ...shell import posix as pshell

__all__ = ['Call', 'Entity', 'Function', 'Makefile', 'NamedEntity', 'Pattern',
           'Section', 'Syntax', 'Writer', 'Variable', 'var', 'qvar', 'Silent',
           'path_vars']

Rule = namedtuple('Rule', ['targets', 'deps', 'order_only', 'recipe',
                           'variables', 'phony'])
Include = namedtuple('Include', ['name', 'optional'])

Syntax = Enum('Syntax', ['target', 'dependency', 'function', 'shell', 'clean'])
Section = Enum('Section', ['path', 'command', 'flags', 'other'])

_comment_tmpl = """
# Do not edit this file! It was automatically generated by bfg9000.
# Instead, you should edit the source file that created this:
# {}
""".strip()


class syntax_string(safe_str.safe_string):
    def __init__(self, data, syntax=None, quoted=False):
        self.data = data
        self.syntax = syntax
        self.quoted = quoted

    def __eq__(self, rhs):
        return (type(self) == type(rhs) and self.data == rhs.data and
                self.syntax == rhs.syntax and self.quoted == rhs.quoted)

    def __repr__(self):
        syntax = getattr(self.syntax, 'name', repr(self.syntax))
        return '<{}({!r}, {}, {!r})>'.format(type(self).__name__, self.data,
                                             syntax, self.quoted)


class Writer:
    # For targets and deps, we want to backslash-escape glob characters,
    # whitespace, '#' (comments), and '%' (patterns), plus '~' if it's at the
    # *beginning* of a path. On non-Windows systems, also backslash-escape ':'
    # (which separates targets and deps). Note: '$' is also escaped, but done
    # separately, as it's escaped with a second '$'.
    __extra_escapes = '' if platform_info().family == 'windows' else ':'
    __escape_chars = r'?*\[\]\s#%' + __extra_escapes
    __target_ex = re.compile(r'(\\*)(^~|[' + __escape_chars + '])')
    __dep_ex = re.compile(r'(\\*)(^~|[|' + __escape_chars + '])')

    def __init__(self, stream):
        self.stream = stream

    @classmethod
    def escape_str(cls, string, syntax):
        def repl(match):
            return match.group(1) * 2 + '\\' + match.group(2)

        if '\n' in string:
            raise ValueError('illegal newline')
        result = string.replace('$', '$$')

        if syntax == Syntax.target:
            return cls.__target_ex.sub(repl, result)
        elif syntax == Syntax.dependency:
            return cls.__dep_ex.sub(repl, result)
        elif syntax == Syntax.function:
            return result.replace(',', '$,')
        elif syntax in [Syntax.shell, Syntax.clean]:
            return result

        raise ValueError(
            "unknown syntax '{}'".format(syntax)
        )  # pragma: no cover

    def write_literal(self, string):
        self.stream.write(string)

    def write(self, thing, syntax, shell_quote=pshell.quote_info):
        thing = safe_str.safe_str(thing)
        shelly = syntax in [Syntax.function, Syntax.shell]
        escaped = False

        if isinstance(thing, safe_str.literal):
            escaped = True
            self.write_literal(thing.string)
        elif isinstance(thing, safe_str.shell_literal):
            escaped = True
            self.write_literal(self.escape_str(thing.string, syntax))
        elif isinstance(thing, str):
            if shelly and shell_quote:
                thing, escaped = shell_quote(thing)
            self.write_literal(self.escape_str(thing, syntax))
        elif isinstance(thing, syntax_string):
            out = Writer(StringIO())
            escaped = out.write(thing.data, thing.syntax or syntax,
                                None if thing.quoted else shell_quote)
            result = out.stream.getvalue()
            if thing.quoted:
                result = pshell.wrap_quotes(result)
            self.write_literal(result)
        elif isinstance(thing, safe_str.jbos):
            for i in thing.bits:
                escaped |= self.write(i, syntax, shell_quote)
        elif isinstance(thing, path.BasePath):
            out = Writer(StringIO())
            thing = thing.realize(path_vars, shelly)
            escaped = out.write(thing, syntax, pshell.inner_quote_info)

            thing = out.stream.getvalue()
            if shelly and escaped:
                thing = pshell.wrap_quotes(thing)
            self.write_literal(thing)
        else:
            raise TypeError(type(thing))

        return escaped

    def write_each(self, things, syntax, delim=safe_str.literal(' '),
                   prefix=None, suffix=None, shell_quote=pshell.quote_info):
        for i in iterutils.tween(things, delim, prefix, suffix):
            self.write(i, syntax, shell_quote)

    def write_shell(self, thing, syntax=Syntax.shell):
        if isinstance(thing, Silent):
            self.write_literal('@')
            thing = thing.data

        self.write_each(iterutils.iterate(thing), syntax)


class Entity(safe_str.safe_string_ops):
    def use(self):
        raise NotImplementedError()

    def _safe_str(self):
        return self.use()

    def __str__(self):
        raise NotImplementedError()

    def __repr__(self):
        return repr(self.use())


class NamedEntity(Entity):
    def __init__(self, name):
        self.name = name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, rhs):
        return type(self) == type(rhs) and self.name == rhs.name

    def __ne__(self, rhs):
        return not (self == rhs)


class Pattern(Entity):
    def __init__(self, path):
        if len(re.findall(r'((?<=[^\\])|^)(\\\\)*%', path)) != 1:
            raise ValueError('exactly one % required')
        self.path = path

    def use(self):
        bits = re.split(r'%', self.path)
        return safe_str.join(bits, safe_str.literal('%'))

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, rhs):
        return type(self) == type(rhs) and self.path == rhs.path

    def __ne__(self, rhs):
        return not (self == rhs)


class Variable(NamedEntity):
    def __init__(self, name, quoted=False):
        super().__init__(re.sub(r'[\s:#=]', '_', name))
        self.quoted = quoted

    def use(self):
        fmt = '${}' if len(self.name) == 1 else '$({})'
        if self.quoted:
            fmt = pshell.wrap_quotes(fmt)
        return safe_str.literal(fmt.format(self.name))


def var(v, quoted=False):
    return v if isinstance(v, Variable) else Variable(v, quoted)


def qvar(v):
    return var(v, True)


class Function(NamedEntity):
    def __init__(self, name, *args, quoted=False):
        super().__init__(name)
        self.args = args
        self.quoted = quoted

    def use(self):
        lit = safe_str.literal

        prefix = lit('$(' + self.name)
        suffix = lit(')')
        data = prefix + safe_str.jbos.from_iterable(
            safe_str.safe_str(j)
            for i in iterutils.tween(self.args, lit(','), lit(' '))
            for j in iterutils.tween(iterutils.iterate(i), lit(' '))
        ) + suffix
        return syntax_string(data, Syntax.function, self.quoted)

    def __eq__(self, rhs):
        return super().__eq__(rhs) and self.args == rhs.args


def Call(func, *args):
    return Function('call', var(func).name, *args)


class Silent:
    def __init__(self, data):
        self.data = data


path_vars = {
    path.Root.srcdir  : Variable('srcdir'),
    path.Root.builddir: None,
}
path_vars.update({i: Variable(i.name) for i in path.InstallRoot})

# Only use destdir on platforms that actually support it (e.g. not Windows).
if platform_info().destdir:
    path_vars[path.DestDir.destdir] = Variable('DESTDIR')


class Makefile:
    Section = Section

    def __init__(self, bfgfile, gnu=False):
        self._bfgfile = bfgfile
        self._gnu = gnu

        self._var_table = set()
        self._global_variables = {i: [] for i in Section}
        self._target_variables = []
        self._defines = []

        self._rules = []
        self._targets = set()
        self._includes = []

    def variable(self, name, value, section=Section.other, exist_ok=False):
        name, exists = self._unique_var(name, exist_ok)
        if not exists:
            value = self._convert_args(value)
            self._global_variables[section].append((name, value))
        return name

    def target_variable(self, name, value, exist_ok=False):
        name, exists = self._unique_var(name, exist_ok)
        if not exists:
            value = self._convert_args(value)
            self._target_variables.append((name, value))
        return name

    def define(self, name, value, exist_ok=False):
        name, exists = self._unique_var(name, exist_ok)
        value = [self._convert_args(i) for i in iterutils.iterate(value)]

        if not exists:
            self._defines.append((name, value))
        return name

    def cmd_var(self, cmd):
        name = cmd.command_var.upper()
        return self.variable(name, cmd.command, Section.command, exist_ok=True)

    def has_variable(self, name):
        return var(name) in self._var_table

    def _unique_var(self, name, exist_ok):
        name = var(name)
        exists = self.has_variable(name)
        if exists and not exist_ok:
            raise ValueError('variable {!r} already exists'.format(name))
        self._var_table.add(name)
        return name, exists

    def include(self, name, optional=False):
        self._includes.append(Include(name, optional))

    @staticmethod
    def _target_str(name):
        out = Writer(StringIO())
        out.write(name, Syntax.target)
        return out.stream.getvalue()

    def rule(self, target, deps=None, order_only=None, recipe=None,
             variables=None, phony=False):
        targets = iterutils.listify(target)
        if len(targets) == 0:
            raise ValueError('must have at least one target')
        for i in targets:
            target = self._target_str(i)
            if self.has_rule(target):
                raise ValueError('rule for {!r} already exists'.format(target))
            self._targets.add(target)

        if iterutils.isiterable(recipe):
            recipe = [self._convert_args(i) for i in recipe]

        variables = {var(k): v for k, v in (variables or {}).items()}

        self._rules.append(Rule(
            targets, iterutils.listify(deps), iterutils.listify(order_only),
            recipe, variables, phony
        ))

    def has_rule(self, name):
        return name in self._targets

    def _convert_args(self, args):
        def convert(args):
            if iterutils.isiterable(args):
                return Command.convert_args(args, self.cmd_var)
            return args

        if isinstance(args, Silent):
            return Silent(convert(args.data))
        return convert(args)

    def _write_variable(self, out, name, value, syntax=Syntax.shell,
                        target=None):
        if target:
            out.write(target, Syntax.target)
            out.write_literal(': ')
        out.write_literal(name.name + ' := ')
        out.write_shell(value, syntax)
        out.write_literal('\n')

    def _write_define(self, out, name, value):
        out.write_literal('define ' + name.name + '\n')
        for line in value:
            out.write_shell(line)
            out.write_literal('\n')
        out.write_literal('endef\n\n')

    def _write_rule(self, out, rule):
        if rule.variables:
            for target in rule.targets:
                for name, value in rule.variables.items():
                    self._write_variable(out, name, value, target=target)

        if rule.phony:
            out.write_literal('.PHONY: ')
            out.write_each(rule.targets, Syntax.dependency)
            out.write_literal('\n')

        out.write_each(rule.targets, Syntax.target)
        out.write_literal(':')

        lit = safe_str.literal
        out.write_each(rule.deps, Syntax.dependency, prefix=lit(' '))
        out.write_each(rule.order_only, Syntax.dependency, prefix=lit(' | '))

        if isinstance(rule.recipe, Entity):
            out.write_literal(' ; ')
            out.write_shell(rule.recipe)
        elif rule.recipe is not None:
            for cmd in rule.recipe:
                out.write_literal('\n\t')
                out.write_shell(cmd)
        out.write_literal('\n\n')

    def write(self, out):
        out = Writer(out)
        out.write_literal(_comment_tmpl.format(self._bfgfile) + '\n\n')

        # Don't let make use built-in rules/variables.
        out.write_literal('MAKEFLAGS += --no-builtin-variables\n' if self._gnu
                          else '.SUFFIXES:\n')

        # Necessary for escaping commas in function calls.
        self._write_variable(out, Variable(','), ',')
        out.write_literal('\n')

        for section in Section:
            # The built-in paths don't need shell quoting because they're used
            # by other paths, which *are* quoted.
            syntax = Syntax.clean if section == Section.path else Syntax.shell
            for name, value in self._global_variables[section]:
                self._write_variable(out, name, value, syntax)
            if self._global_variables[section]:
                out.write_literal('\n')

        target = Pattern('%')
        for name, value in self._target_variables:
            self._write_variable(out, name, value, target=target)
        if self._target_variables:
            out.write_literal('\n')

        for name, value in self._defines:
            self._write_define(out, name, value)

        for r in self._rules:
            self._write_rule(out, r)

        for i in self._includes:
            out.write_literal(('-' if i.optional else '') + 'include ')
            out.write(i.name, Syntax.target)
            out.write_literal('\n')
