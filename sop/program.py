"""Bounded generated score programs and local parameter fitting."""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from scipy.optimize import differential_evolution

from .scenario import CUMULATIVE_FIELDS, EVENT_FIELDS, Context

STATIC_FIELDS = (
    "X003R", "Q274", "Q275", "G_TOWNSIZE", "Q3", "Q46", "Q55", "Q57",
    "Y003", "I_AUTHORITY", "I_NATIONALISM", "DEFIANCE", "SCEPTICISM", "AUTONOMY", "EQUALITY", "I_DEVOUT",
)
ARGUMENTS = ("x", "event", "cumulative", "previous_choice", "previous_missing", "p")
ALLOWED_NODES = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign, ast.If, ast.Return,
    ast.Name, ast.Load, ast.Store, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp,
    ast.Subscript, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.USub, ast.UAdd,
    ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


def validate_source(source: str) -> tuple[int, tuple[str, ...]]:
    """Accept only one arithmetic score function with literal feature/parameter keys."""
    if len(source) > 4000:
        raise ValueError("Generated program is too long")
    tree = ast.parse(source, mode="exec")
    if len(list(ast.walk(tree))) > 180:
        raise ValueError("Generated program is too complex")
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Generated program must contain one score function")
    function = tree.body[0]
    if function.name != "score" or tuple(arg.arg for arg in function.args.args) != ARGUMENTS:
        raise ValueError("Generated score function has an incompatible interface")
    if function.decorator_list or function.args.defaults or function.args.kwonlyargs or function.args.vararg or function.args.kwarg:
        raise ValueError("Decorators and optional arguments are not allowed")
    known = set(ARGUMENTS)
    parameters: set[int] = set()
    static_fields: set[str] = set()
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def has_signal(node: ast.AST, derived: set[str]) -> bool:
        return any(
            (isinstance(item, ast.Subscript) and isinstance(item.value, ast.Name) and item.value.id in {"x", "event", "cumulative"})
            or (isinstance(item, ast.Name) and item.id in {"previous_choice", "previous_missing"} | derived)
            for item in ast.walk(node)
        )

    def expression(node: ast.AST, local_names: set[str], derived: set[str]) -> None:
        for item in ast.walk(node):
            if not isinstance(item, ALLOWED_NODES):
                raise ValueError(f"Forbidden generated-program syntax: {type(item).__name__}")
            if isinstance(item, ast.Constant):
                if isinstance(item.value, bool) or not isinstance(item.value, (int, float, str)):
                    raise ValueError("Invalid program constant")
                if isinstance(item.value, (int, float)) and (not math.isfinite(float(item.value)) or abs(float(item.value)) > 100):
                    raise ValueError("Program constant exceeds the allowed range")
            if isinstance(item, ast.BinOp) and isinstance(item.op, ast.Mult) and has_signal(item.left, derived) and has_signal(item.right, derived):
                raise ValueError("Products of two input signals are not allowed")
            if isinstance(item, ast.Subscript):
                if not isinstance(item.value, ast.Name) or not isinstance(item.slice, ast.Constant):
                    raise ValueError("Only literal-key input access is allowed")
                container, key = item.value.id, item.slice.value
                if container == "p" and isinstance(key, int) and not isinstance(key, bool) and 0 <= key < 12:
                    parameters.add(key)
                elif container == "x" and key in STATIC_FIELDS:
                    static_fields.add(str(key))
                elif container == "event" and key in EVENT_FIELDS:
                    pass
                elif container == "cumulative" and key in CUMULATIVE_FIELDS:
                    pass
                else:
                    raise ValueError(f"Unknown program field or parameter: {container}[{key!r}]")
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load):
                if item.id not in local_names or item.id.startswith("__"):
                    raise ValueError(f"Unknown program name: {item.id}")
                if item.id in {"x", "event", "cumulative", "p"}:
                    parent = parents.get(item)
                    if not isinstance(parent, ast.Subscript) or parent.value is not item:
                        raise ValueError("Input mappings may only be accessed with literal keys")

    def block(statements: list[ast.stmt], local_names: set[str], derived: set[str]) -> None:
        for statement in statements:
            if isinstance(statement, ast.Assign):
                if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                    raise ValueError("Assignments must target one local variable")
                name = statement.targets[0].id
                if name in ARGUMENTS or name.startswith("__"):
                    raise ValueError("Program may not overwrite an input")
                expression(statement.value, local_names, derived)
                local_names.add(name)
                if has_signal(statement.value, derived):
                    derived.add(name)
            elif isinstance(statement, ast.If):
                expression(statement.test, local_names, derived)
                block(statement.body, set(local_names), set(derived))
                block(statement.orelse, set(local_names), set(derived))
            elif isinstance(statement, ast.Return):
                expression(statement.value, local_names, derived)
            else:
                raise ValueError(f"Forbidden program statement: {type(statement).__name__}")

    block(function.body, known, set())

    def always_returns(statements: list[ast.stmt]) -> bool:
        for statement in statements:
            if isinstance(statement, ast.Return):
                return True
            if isinstance(statement, ast.If) and statement.orelse and always_returns(statement.body) and always_returns(statement.orelse):
                return True
        return False

    if not always_returns(function.body):
        raise ValueError("Every generated-program path must return a score")
    if not parameters or parameters != set(range(max(parameters) + 1)):
        raise ValueError("Program parameters must be contiguous from p[0]")
    return max(parameters) + 1, tuple(sorted(static_fields))


def compile_source(source: str) -> tuple[Callable[..., float], int, tuple[str, ...]]:
    parameter_count, static_fields = validate_source(source)
    namespace: dict[str, Any] = {"__builtins__": {}}
    exec(compile(source, "<reviewer-sop-program>", "exec"), namespace, namespace)
    return namespace["score"], parameter_count, static_fields


def normalizers(profiles: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    return {
        code: (
            min(float(row["standardized_features"][code]) for row in profiles),
            max(float(row["standardized_features"][code]) for row in profiles),
        )
        for code in STATIC_FIELDS
    }


@dataclass
class Program:
    source: str
    params: list[float]
    thresholds: list[float]
    bounds: dict[str, tuple[float, float]]

    def __post_init__(self) -> None:
        self.function, parameter_count, self.static_fields = compile_source(self.source)
        if len(self.params) != parameter_count or len(self.thresholds) != 4:
            raise ValueError("Program parameter shape is invalid")

    def predict(self, profile: dict[str, Any], context: Context, previous: str | None) -> str:
        x = {}
        for code in STATIC_FIELDS:
            lo, hi = self.bounds[code]
            value = float(profile["standardized_features"][code])
            x[code] = 0.5 if hi <= lo else (value - lo) / (hi - lo)
        prior = 0.0 if previous is None else int(previous) / 5.0
        value = float(self.function(x, context.current, context.cumulative, prior, 1.0 if previous is None else 0.0, self.params))
        if not math.isfinite(value):
            raise ValueError("Generated program returned a nonfinite score")
        return str(1 + sum(value > threshold for threshold in sorted(self.thresholds)))

    def payload(self) -> dict[str, Any]:
        return {"source": self.source, "params": self.params, "thresholds": self.thresholds, "normalizers": self.bounds}


def fit_program(
    source: str,
    cases: list[tuple[dict[str, Any], Context, str | None, str]],
    bounds: dict[str, tuple[float, float]],
    seed: int,
) -> tuple[Program, float]:
    _, parameter_count, _ = compile_source(source)
    if not cases:
        raise ValueError("Program fitting requires training decisions")

    def objective(vector: np.ndarray) -> float:
        program = Program(source, vector[:parameter_count].tolist(), vector[parameter_count:].tolist(), bounds)
        errors = []
        for profile, context, previous, target in cases:
            try:
                predicted = int(program.predict(profile, context, previous))
            except (ValueError, TypeError, OverflowError, ZeroDivisionError):
                return 10.0
            errors.append(float(predicted != int(target)) + 0.05 * abs(predicted - int(target)))
        return float(np.mean(errors) + 1e-4 * np.mean(vector[:parameter_count] ** 2))

    optimized = differential_evolution(
        objective,
        [(-4.0, 4.0)] * parameter_count + [(-4.0, 6.0)] * 4,
        maxiter=3,
        popsize=3,
        seed=seed,
        polish=False,
    )
    vector = optimized.x
    return Program(source, vector[:parameter_count].tolist(), vector[parameter_count:].tolist(), bounds), float(optimized.fun)
