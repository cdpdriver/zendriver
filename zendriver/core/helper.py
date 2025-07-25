"""Helper functions."""

import asyncio
import json
import logging
from typing import Any, Callable


from .parse_evaluation_result import parse_evaluation_result_value
from .raw_bindings_controller import raw_bindings_controller_source

logger = logging.getLogger(__name__)


def evaluation_string(fun: str, *args: Any, **kwargs) -> str:
    """Convert function and arguments to str."""
    _args = ", ".join([json.dumps("undefined" if arg is None else arg) for arg in args])
    expr = f"({fun})({_args})"
    return expr


def init_script(source: str):
    return f"(() => {{\n{source}\n}})();"


class BindingSource:
    def __init__(self, page, browser, execution_context_id):
        self.page = page
        self.browser = browser
        self.execution_context_id = execution_context_id


class PageBinding:
    kController = "__zendriver__binding__controller__"
    kBindingName = "__zendriver__binding__"

    @staticmethod
    def create_init_script():
        source = f"""
        (() => {{
            const module = {{}};
            {raw_bindings_controller_source}
            const property = '{PageBinding.kController}';
            if (!globalThis[property])
                globalThis[property] = new (module.exports.BindingsController())(globalThis, '{PageBinding.kBindingName}');
        }})();
        """
        return init_script(source)

    def __init__(self, name: str, function: Callable, needs_handle: bool):
        self.name = name
        self.function = function
        self.needs_handle = needs_handle
        self.init_script = init_script(
            f"globalThis['{PageBinding.kController}'].addBinding({json.dumps(name)}, {str(needs_handle).lower()})"
        )

        self.cleanup_script = (
            f"globalThis['{PageBinding.kController}'].removeBinding({json.dumps(name)})"
        )

    @staticmethod
    async def dispatch(page, event, browser):
        execution_context_id = event.execution_context_id
        data = json.loads(event.payload)
        name = data["name"]
        seq = data["seq"]
        serialized_args = data["serializedArgs"]
        binding = page.get_binding(name)
        if not binding:
            raise Exception(f'Function "{name}" is not exposed')
        if not isinstance(serialized_args, list):
            raise Exception(
                "serializedArgs is not an array. This can happen when Array.prototype.toJSON is defined incorrectly"
            )
        try:
            if binding.needs_handle:
                try:
                    handle = await page.evaluate(
                        evaluation_string(
                            "arg => globalThis['{}'].takeBindingHandle(arg)".format(
                                PageBinding.kController
                            ),
                            {"name": name, "seq": seq},
                        )
                    )
                except Exception:
                    handle = None
                result = binding.function(
                    BindingSource(
                        page=page,
                        browser=browser,
                        execution_context_id=execution_context_id,
                    ),
                    handle=handle,
                )
            else:
                args = [parse_evaluation_result_value(a) for a in serialized_args]
                result = binding.function(
                    BindingSource(
                        page=page,
                        browser=browser,
                        execution_context_id=execution_context_id,
                    ),
                    *args,
                )

            if asyncio.iscoroutine(result):
                result = await result

            await page.evaluate(
                evaluation_string(
                    "arg => globalThis['{}'].deliverBindingResult(arg)".format(
                        PageBinding.kController
                    ),
                    {"name": name, "seq": seq, "result": result},
                )
            )
        except Exception as error:
            logger.error(error)
            await page.evaluate(
                evaluation_string(
                    "arg => globalThis['{}'].deliverBindingResult(arg)".format(
                        PageBinding.kController
                    ),
                    {"name": name, "seq": seq, "error": str(error)},
                )
            )
