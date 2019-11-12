import ast
from typing import Dict, List, Optional, Union

from ._cached_property import cached_property
from ._base import BaseReader


class StaticReader(BaseReader):
    @cached_property
    def content(self) -> Optional[Dict[str, Union[List, Dict]]]:
        if not self.call:
            return None

        return dict(
            name=self._find_single_string('name'),
            version=self._find_single_string('version'),
            python_requires=self._find_single_string('python_requires'),

            install_requires=self._find_install_requires(),
            extras_require=self._find_extras_require(),
        )

    @cached_property
    def tree(self) -> tuple:
        return tuple(ast.parse(self.path.read_text(encoding='utf8')).body)

    @cached_property
    def call(self) -> Optional[ast.Call]:
        return self._get_call(self.tree)

    @cached_property
    def body(self) -> tuple:
        return tuple(self._get_body(self.tree))

    @classmethod
    def _get_body(cls, elements):
        for element in elements:
            if isinstance(element, ast.FunctionDef):
                yield from cls._get_body(element.body)
                continue
            if isinstance(element, ast.If):
                yield from cls._get_body(element.body)
            if isinstance(element, ast.Expr):
                yield element.value
                continue
            yield element

    def _get_call(self, elements) -> Optional[ast.Call]:
        for element in self._get_body(elements):
            if not isinstance(element, ast.Call):
                continue
            if not isinstance(element.func, ast.Name):
                continue
            if element.func.id != 'setup':
                continue
            return element
        return None

    def _find_install_requires(self):
        install_requires = []
        value = self._find_in_call(self.call, 'install_requires')
        if value is None:
            kwargs = self._find_call_kwargs(self.call)

            if kwargs is None or not isinstance(kwargs, ast.Name):
                return install_requires

            variable = self._find_variable_in_body(self.body, kwargs.id)
            if not isinstance(variable, (ast.Dict, ast.Call)):
                return install_requires

            if isinstance(variable, ast.Call):
                if not isinstance(variable.func, ast.Name):
                    return install_requires

                if variable.func.id != 'dict':
                    return install_requires

                value = self._find_in_call(variable, 'install_requires')
            else:
                value = self._find_in_dict(variable, 'install_requires')

        if value is None:
            return install_requires

        if isinstance(value, ast.List):
            for el in value.elts:
                install_requires.append(el.s)
        elif isinstance(value, ast.Name):
            variable = self._find_variable_in_body(self.body, value.id)

            if variable is not None and isinstance(variable, ast.List):
                for el in variable.elts:
                    install_requires.append(el.s)

        return install_requires

    def _find_extras_require(self):
        extras_require = {}
        value = self._find_in_call(self.call, 'extras_require')
        if value is None:
            kwargs = self._find_call_kwargs(self.call)

            if kwargs is None or not isinstance(kwargs, ast.Name):
                return extras_require

            variable = self._find_variable_in_body(self.body, kwargs.id)
            if not isinstance(variable, (ast.Dict, ast.Call)):
                return extras_require

            if isinstance(variable, ast.Call):
                if not isinstance(variable.func, ast.Name):
                    return extras_require

                if variable.func.id != 'dict':
                    return extras_require

                value = self._find_in_call(variable, 'extras_require')
            else:
                value = self._find_in_dict(variable, 'extras_require')

        if value is None:
            return extras_require

        if isinstance(value, ast.Dict):
            for key, val in zip(value.keys, value.values):
                if isinstance(val, ast.Name):
                    val = self._find_variable_in_body(self.body, val.id)

                if isinstance(val, ast.List):
                    extras_require[key.s] = [e.s for e in val.elts]
        elif isinstance(value, ast.Name):
            variable = self._find_variable_in_body(self.body, value.id)

            if variable is None or not isinstance(variable, ast.Dict):
                return extras_require

            for key, val in zip(variable.keys, variable.values):
                if isinstance(val, ast.Name):
                    val = self._find_variable_in_body(self.body, val.id)

                if isinstance(val, ast.List):
                    extras_require[key.s] = [e.s for e in val.elts]

        return extras_require

    def _find_single_string(self, name: str):
        value = self._find_in_call(self.call, name)
        if value is None:
            # Trying to find in kwargs
            kwargs = self._find_call_kwargs(self.call)

            if kwargs is None or not isinstance(kwargs, ast.Name):
                return

            variable = self._find_variable_in_body(self.body, kwargs.id)
            if not isinstance(variable, (ast.Dict, ast.Call)):
                return

            if isinstance(variable, ast.Call):
                if not isinstance(variable.func, ast.Name):
                    return

                if variable.func.id != 'dict':
                    return

                value = self._find_in_call(variable, name)
            else:
                value = self._find_in_dict(variable, name)

        if value is None:
            return

        if isinstance(value, ast.Str):
            return value.s
        if isinstance(value, ast.Name):
            variable = self._find_variable_in_body(self.body, value.id)
            if variable is not None and isinstance(variable, ast.Str):
                return variable.s
        return None

    def _find_in_call(self, call, name):
        for keyword in call.keywords:
            if keyword.arg == name:
                return keyword.value
        return None

    def _find_call_kwargs(self, call):
        for keyword in reversed(call.keywords):
            if keyword.arg is None:
                return keyword.value
        return None

    def _find_variable_in_body(self, body, name):
        for elem in body:
            if not isinstance(elem, ast.Assign):
                continue
            for target in elem.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == name:
                    return elem.value
        return None

    def _find_in_dict(self, dict_, name):
        for key, val in zip(dict_.keys, dict_.values):
            if isinstance(key, ast.Str) and key.s == name:
                return val
        return None