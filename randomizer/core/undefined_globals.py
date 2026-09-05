"""Find global names a module's code loads but nothing ever defines.

A missing import is invisible to every suite this project has. The module
imports, ``compileall`` is happy, and the name is only looked up when the line
runs -- so an import dropped from a GUI callback ships, and the first person to
hover the wrong row gets ``NameError`` in a traceback dialog. That happened to
``permanent_target_surcharged`` in the Shop tooltip.

Reading the bytecode rather than the source is what makes this work inside the
frozen launcher, where the .py files are not there to parse. Every ``LOAD_GLOBAL``
in every code object is checked against the module's own namespace and builtins.
"""

import builtins
import importlib
import pkgutil
import sys

_BUILTINS = frozenset(dir(builtins))
# Names Python emits as globals but always provides itself.
_IMPLICIT = frozenset({'__file__', '__name__', '__doc__', '__spec__',
                       '__package__', '__loader__', '__builtins__',
                       '__annotations__'})


def _code_objects(code):
    yield code
    for constant in code.co_consts:
        if hasattr(constant, 'co_names'):
            yield from _code_objects(constant)


def _global_names(code):
    """Return the global names a module loads, and the ones it later drops.

    A module that decodes a blob into constants and then ``del``s the blob has
    no such attribute by the time this runs, and that is deliberate rather than
    a missing import, so deletions count as definitions.
    """
    import dis

    loads, deleted = set(), set()
    for block in _code_objects(code):
        for instruction in dis.get_instructions(block):
            name = instruction.argval
            if not isinstance(name, str):
                continue
            if instruction.opname in ('LOAD_GLOBAL', 'LOAD_NAME'):
                loads.add(name)
            elif instruction.opname in ('DELETE_GLOBAL', 'DELETE_NAME'):
                deleted.add(name)
    return loads, deleted


def undefined_globals(package_names=('randomizer',)):
    """Return 'module.name' for every global load nothing can satisfy."""
    return scan_undefined_globals(package_names)[0]


def scan_undefined_globals(package_names=('randomizer',)):
    """Return the findings and how many modules were actually read.

    The count is reported alongside the findings because an empty result is
    the same shape whether nothing is wrong or nothing was scanned, and a
    frozen build is exactly where the walk could quietly come back empty.
    """
    modules = {}
    for package_name in package_names:
        package = sys.modules.get(package_name)
        if package is None:
            continue
        modules[package_name] = package
        for info in pkgutil.walk_packages(
            getattr(package, '__path__', ()), package_name + '.'
        ):
            module = sys.modules.get(info.name)
            if module is None:
                # A module nobody has imported yet is exactly where a missing
                # import hides, so import it rather than skip it. Anything
                # that refuses to load is a louder failure than this check.
                try:
                    module = importlib.import_module(info.name)
                except Exception:
                    continue
            modules[info.name] = module
    missing = []
    scanned = 0
    for module_name, module in sorted(modules.items()):
        code = getattr(getattr(module, '__loader__', None), 'get_code', None)
        try:
            module_code = code(module_name) if code is not None else None
        except (ImportError, OSError, TypeError, ValueError):
            module_code = None
        if module_code is None:
            continue
        scanned += 1
        namespace = vars(module)
        loads, deleted = _global_names(module_code)
        for name in sorted(loads):
            if (
                name in namespace or name in _BUILTINS
                or name in _IMPLICIT or name in deleted
            ):
                continue
            missing.append(f'{module_name}.{name}')
    return missing, scanned

