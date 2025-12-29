from __future__ import annotations

import asyncio
import logging
import subprocess
import types
import typing
from asyncio import AbstractEventLoop
from pathlib import Path
from typing import Any, Callable, List, Optional, Set, Union

from deprecated import deprecated

import zendriver

from .element import Element

if typing.TYPE_CHECKING:
    from .browser import Browser
    from .config import PathLike
from .. import cdp
from .config import BrowserType, Config

__registered__instances__: Set[Browser] = set()

logger = logging.getLogger(__name__)
T = typing.TypeVar("T")


async def start(
    config: Optional[Config] = None,
    *,
    user_data_dir: Optional[PathLike] = None,
    headless: Optional[bool] = False,
    browser_executable_path: Optional[PathLike] = None,
    browser: BrowserType = "auto",
    browser_args: Optional[List[str]] = None,
    sandbox: Optional[bool] = True,
    lang: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    expert: Optional[bool] = None,
    user_agent: Optional[str] = None,
    **kwargs: Any,
) -> Browser:
    """
    helper function to launch a browser. it accepts several keyword parameters.
    conveniently, you can just call it bare (no parameters) to quickly launch an instance
    with best practice defaults.
    note: this should be called ```await start()```

    :param user_data_dir:

    :param headless:

    :param browser_executable_path:

    :param browser_args: ["--some-chromeparam=somevalue", "some-other-param=someval"]

    :param sandbox: default True, but when set to False it adds --no-sandbox to the params, also
    when using linux under a root user, it adds False automatically (else chrome won't start

    :param lang: language string

    :param port: if you connect to an existing debuggable session, you can specify the port here
                 if both host and port are provided, zendriver will not start a local chrome browser!

    :param host: if you connect to an existing debuggable session, you can specify the host here
                 if both host and port are provided, zendriver will not start a local chrome browser!

    :param expert:  when set to True, enabled "expert" mode.
                    This conveys, the inclusion of parameters: --disable-web-security ----disable-site-isolation-trials,
                    as well as some scripts and patching useful for debugging (for example, ensuring shadow-root is always in "open" mode)

    :param user_agent: if set, this will be used as the user agent for the browser.

    :return:
    """
    if not config:
        config = Config(
            user_data_dir,
            headless,
            browser_executable_path,
            browser,
            browser_args,
            sandbox,
            lang,
            host=host,
            port=port,
            expert=expert,
            user_agent=user_agent,
            **kwargs,
        )
    from .browser import Browser

    return await Browser.create(config)


async def create_from_undetected_chromedriver(driver: Any) -> Browser:
    """
    create a zendriver.Browser instance from a running undetected_chromedriver.Chrome instance.
    """
    from .config import Config

    conf = Config()

    host, port = driver.options.debugger_address.split(":")
    conf.host, conf.port = host, int(port)

    # create zendriver Browser instance
    browser = await start(conf)

    browser._process_pid = driver.browser_pid
    # stop chromedriver binary
    driver.service.stop()
    driver.browser_pid = -1
    driver.user_data_dir = None
    return browser


def get_registered_instances() -> Set[Browser]:
    return __registered__instances__


def free_port() -> int:
    """
    Determines a free port using sockets.
    """
    import socket

    free_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free_socket.bind(("127.0.0.1", 0))
    free_socket.listen(5)
    port: int = free_socket.getsockname()[1]
    free_socket.close()
    return port


def filter_recurse_all(
    doc: T, predicate: Union[Callable[[cdp.dom.Node], bool], Callable[[Element], bool]]
) -> List[T]:
    """
    test each child using predicate(child), and return all children for which predicate(child) == True

    :param doc: the cdp.dom.Node object or :py:class:`zendriver.Element`
    :param predicate: a function which takes a node as first parameter and returns a boolean, where True means include
    :return:
    :rtype:
    """
    if not hasattr(doc, "children"):
        raise TypeError("object should have a .children attribute")
    out = []
    if doc and doc.children:
        for child in doc.children:
            if predicate(child):
                # if predicate is True
                out.append(child)
            if child.shadow_roots is not None:
                out.extend(filter_recurse_all(child.shadow_roots[0], predicate))
            out.extend(filter_recurse_all(child, predicate))

    return out


def filter_recurse(
    doc: cdp.dom.Node, predicate: Callable[[cdp.dom.Node], bool]
) -> cdp.dom.Node | None:
    """
    test each child using predicate(child), and return the first child of which predicate(child) == True

    :param doc: the cdp.dom.Node object or :py:class:`zendriver.Element`
    :param predicate: a function which takes a node as first parameter and returns a boolean, where True means include

    """
    if not hasattr(doc, "children"):
        raise TypeError("object should have a .children attribute")

    if doc and doc.children:
        for child in doc.children:
            if predicate(child):
                # if predicate is True
                return child
            if child.shadow_roots:
                shadow_root_result = filter_recurse(child.shadow_roots[0], predicate)
                if shadow_root_result:
                    return shadow_root_result
            result = filter_recurse(child, predicate)
            if result:
                return result

    return None


def circle(
    x: float, y: float | None = None, radius: int = 10, num: int = 10, dir: int = 0
) -> typing.Generator[typing.Tuple[float, float], None, None]:
    """
    a generator will calculate coordinates around a circle.

    :param x: start x position
    :param y: start y position
    :param radius: size of the circle
    :param num: the amount of points calculated (higher => slower, more cpu, but more detailed)
    :return:
    :rtype:
    """
    import math

    r = radius
    w = num
    if not y:
        y = x
    a = int(x - r * 2)
    b = int(y - r * 2)
    m = (2 * math.pi) / w
    if dir == 0:
        # regular direction
        ran = 0, w + 1, 1
    else:
        # opposite ?
        ran = w + 1, 0, -1

    for i in range(*ran):
        x = a + r * math.sin(m * i)
        y = b + r * math.cos(m * i)

        yield x, y


def remove_from_tree(tree: cdp.dom.Node, node: cdp.dom.Node) -> cdp.dom.Node:
    if not hasattr(tree, "children"):
        raise TypeError("object should have a .children attribute")

    if tree and tree.children:
        for child in tree.children:
            if child.backend_node_id == node.backend_node_id:
                tree.children.remove(child)
            remove_from_tree(child, node)
    return tree


async def html_from_tree(
    tree: Union[cdp.dom.Node, Element], target: zendriver.Tab
) -> str:
    if not hasattr(tree, "children"):
        raise TypeError("object should have a .children attribute")
    out = ""
    if tree and tree.children:
        for child in tree.children:
            if isinstance(child, Element):
                out += await child.get_html()
            elif isinstance(child, cdp.dom.Node):
                out += await target.send(
                    cdp.dom.get_outer_html(backend_node_id=child.backend_node_id)
                )
            else:
                out += child

            if not isinstance(child, str):
                out += await html_from_tree(child, target)
    return out


def compare_target_info(
    info1: cdp.target.TargetInfo | None, info2: cdp.target.TargetInfo
) -> List[typing.Tuple[str, typing.Any, typing.Any]]:
    """
    when logging mode is set to debug, browser object will log when target info
    is changed. To provide more meaningful log messages, this function is called to
    check what has actually changed between the 2 (by simple dict comparison).
    it returns a list of tuples [ ... ( key_which_has_changed, old_value, new_value) ]

    :param info1:
    :param info2:
    :return:
    :rtype:
    """
    d1 = info1.__dict__ if info1 else {}
    d2 = info2.__dict__
    return [(k, v, d2[k]) for (k, v) in d1.items() if d2[k] != v]


@deprecated(
    version="0.5.1", reason="Use asyncio functions directly instead, e.g. asyncio.run"
)
def loop() -> AbstractEventLoop:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def cdp_get_module(domain: Union[str, types.ModuleType]) -> Any:
    """
    get cdp module by given string

    :param domain:
    :return:
    :rtype:
    """
    import importlib

    if isinstance(domain, types.ModuleType):
        # you get what you ask for
        domain_mod = domain
    else:
        try:
            if domain in ("input",):
                domain = "input_"

            #  fallback if someone passes a str
            domain_mod = getattr(cdp, domain)
            if not domain_mod:
                raise AttributeError
        except AttributeError:
            try:
                domain_mod = importlib.import_module(domain)
            except ModuleNotFoundError:
                raise ModuleNotFoundError(
                    "could not find cdp module from input '%s'" % domain
                )
    return domain_mod


def _start_process(
    exe: str | Path, params: List[str], is_posix: bool
) -> subprocess.Popen[bytes]:
    """
    Start a subprocess with the given executable and parameters.

    :param exe: The executable to run.
    :param params: List of parameters to pass to the executable.
    :param is_posix: Boolean indicating if the system is POSIX compliant.

    :return: An instance of `subprocess.Popen`.
    """
    return subprocess.Popen(
        [str(exe)] + params,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=is_posix,
    )


async def _read_process_stderr(process: subprocess.Popen[bytes], n: int = 2**16) -> str:
    """
    Read the given number of bytes from the stderr of the given process.

    Read bytes are automatically decoded to utf-8.
    """

    async def read_stderr() -> bytes:
        if process.stderr is None:
            raise ValueError("Process has no stderr")
        return await asyncio.to_thread(process.stderr.read, n)

    try:
        return (await asyncio.wait_for(read_stderr(), 0.25)).decode("utf-8")
    except asyncio.TimeoutError:
        logger.debug("Timeout reading process stderr")
        return ""
