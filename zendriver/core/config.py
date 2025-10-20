import ctypes
import logging
import os
import pathlib
import secrets
import sys
import tempfile
import zipfile
from typing import Any, Literal

__all__ = [
    'Config',
    'PathLike',
    'find_executable',
    'is_posix',
    'is_root',
    'temp_profile_dir',
]

logger = logging.getLogger(__name__)
is_posix = sys.platform.startswith(('darwin', 'cygwin', 'linux', 'linux2'))

type PathLike = str | pathlib.Path
AUTO = None

BrowserType = Literal['chrome', 'brave', 'auto']


class Config:
    """
    Config object
    """

    def __init__(
        self,
        *,
        user_data_dir: PathLike | None = AUTO,
        headless: bool | None = False,
        browser_executable_path: PathLike | None = AUTO,
        browser: BrowserType = 'auto',
        browser_args: list[str] | None = AUTO,
        sandbox: bool | None = True,
        lang: str | None = None,
        host: str | None = AUTO,
        port: int | None = AUTO,
        expert: bool | None = AUTO,
        browser_connection_timeout: float = 0.25,
        browser_connection_max_tries: int = 10,
        user_agent: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        creates a config object.
        Can be called without any arguments to generate a best-practice config, which is recommended.

        calling the object, eg :  myconfig() , will return the list of arguments which
        are provided to the browser.

        additional arguments can be added using the :py:obj:`~add_argument method`

        Instances of this class are usually not instantiated by end users.

        :param user_data_dir: the data directory to use (must be unique if using multiple browsers)
        :param headless: set to True for headless mode
        :param browser_executable_path: specify browser executable, instead of using autodetect
        :param browser: which browser to use. Can be "chrome", "brave" or "auto". Default is "auto".
        :param browser_args: forwarded to browser executable. eg : ["--some-chromeparam=somevalue", "some-other-param=someval"]
        :param sandbox: disables sandbox
        :param autodiscover_targets: use autodiscovery of targets
        :param lang: language string to use other than the default "en-US,en;q=0.9"
        :param user_agent: custom user-agent string
        :param expert: when set to True, enabled "expert" mode.
               This conveys, the inclusion of parameters: --disable-web-security ----disable-site-isolation-trials,
               as well as some scripts and patching useful for debugging (for example, ensuring shadow-root is always in "open" mode)

        :param kwargs:

        :type user_data_dir: PathLike
        :type headless: bool
        :type browser_executable_path: PathLike
        :type browser: BrowserType
        :type browser_args: list[str]
        :type sandbox: bool
        :type lang: str
        :type user_agent: str
        :type kwargs: dict
        """

        if not browser_args:
            browser_args = []

        # defer creating a temp user data dir until the browser requests it so
        # config can be used/reused as a template for multiple browser instances
        self._user_data_dir: str | None = None
        self._custom_data_dir = False
        if user_data_dir:
            self.user_data_dir = str(user_data_dir)

        if not browser_executable_path:
            browser_executable_path = find_executable(browser)

        self._browser_args = browser_args
        self.browser_executable_path = browser_executable_path
        self.headless = headless
        self.user_agent = user_agent
        self.sandbox = sandbox
        self.host = host
        self.port = port
        self.expert = expert
        self._extensions: list[PathLike] = []

        # when using posix-ish operating system and running as root
        # you must use no_sandbox = True, which in case is corrected here
        if is_posix and is_root() and sandbox:
            logger.info('detected root usage, auto disabling sandbox mode')
            self.sandbox = False

        self.autodiscover_targets = True
        self.lang = lang

        self.browser_connection_timeout = browser_connection_timeout
        self.browser_connection_max_tries = browser_connection_max_tries

        # other keyword args will be accessible by attribute
        self.__dict__.update(kwargs)
        super().__init__()
        self._default_browser_args = [
            '--remote-allow-origins=*',
            '--no-first-run',
            '--no-service-autorun',
            '--no-default-browser-check',
            '--homepage=about:blank',
            '--no-pings',
            '--password-store=basic',
            '--disable-infobars',
            '--disable-breakpad',
            '--disable-component-update',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-background-networking',
            '--disable-dev-shm-usage',
            '--disable-features=IsolateOrigins,DisableLoadExtensionCommandLineSwitch,site-per-process',
            '--disable-session-crashed-bubble',
            '--disable-search-engine-choice-screen',
        ]

    @property
    def browser_args(self) -> list[str]:
        return sorted(self._default_browser_args + self._browser_args)

    @property
    def user_data_dir(self) -> str:
        """
        Get the user data dir or lazily create a new one if unset.

        Returns:
            str: User data directory (used for Chrome profile)
        """
        if not self._user_data_dir:
            self._user_data_dir = temp_profile_dir()
            self._custom_data_dir = False

        return self._user_data_dir

    @user_data_dir.setter
    def user_data_dir(self, path: PathLike) -> None:
        if path:
            self._user_data_dir = str(path)
            self._custom_data_dir = True
        else:
            self._user_data_dir = None
            self._custom_data_dir = False

    @property
    def uses_custom_data_dir(self) -> bool:
        return self._custom_data_dir

    def add_extension(self, extension_path: PathLike) -> None:
        """
        adds an extension to load, you could point extension_path
        to a folder (containing the manifest), or extension file (crx)

        :param extension_path:
        :type extension_path:
        :return:
        :rtype:
        """
        path = pathlib.Path(extension_path)

        if not path.exists():
            raise FileNotFoundError(f'could not find anything here: {path!s}')

        if path.is_file():
            tf = tempfile.mkdtemp(prefix='extension_', suffix=secrets.token_hex(4))
            with zipfile.ZipFile(path, 'r') as z:
                z.extractall(tf)
                self._extensions.append(tf)

        elif path.is_dir():
            for item in path.rglob('manifest.*'):
                path = item.parent
            self._extensions.append(path)

    # def __getattr__(self, item):
    #     if item not in self.__dict__:

    def __call__(self) -> list[str]:
        # the host and port will be added when starting
        # the browser, as by the time it starts, the port
        # is probably already taken
        args = self._default_browser_args.copy()

        args += [f'--user-data-dir={self.user_data_dir}']
        args += ['--disable-features=IsolateOrigins,site-per-process']
        args += ['--disable-session-crashed-bubble']
        if self.expert:
            args += ['--disable-web-security', '--disable-site-isolation-trials']
        if self._browser_args:
            args.extend([arg for arg in self._browser_args if arg not in args])
        if self.headless:
            args.append('--headless=new')
        if self.user_agent:
            args.append(f'--user-agent={self.user_agent}')
        if not self.sandbox:
            args.append('--no-sandbox')
        if self.host:
            args.append(f'--remote-debugging-host={self.host}')
        if self.port:
            args.append(f'--remote-debugging-port={self.port}')
        return args

    def add_argument(self, arg: str) -> None:
        if any(
            x in arg.lower()
            for x in [
                'headless',
                'data-dir',
                'data_dir',
                'no-sandbox',
                'no_sandbox',
                'lang',
            ]
        ):
            raise ValueError(
                f'"{arg}" not allowed. please use one of the attributes of the Config object to set it',
            )
        self._browser_args.append(arg)

    def __repr__(self) -> str:
        s = f'{self.__class__.__name__}'
        for k, v in ({**self.__dict__, **self.__class__.__dict__}).items():
            if k[0] == '_':
                continue
            if not v:
                continue
            if isinstance(v, property):
                v = getattr(self, k)
            if callable(v):
                continue
            s += f'\n\t{k} = {v}'
        return s

    #     d = self.__dict__.copy()
    #     d.pop("browser_args")
    #     d["browser_args"] = self()
    #     return d


def is_root() -> bool:
    """
    helper function to determine if user trying to launch chrome
    under linux as root, which needs some alternative handling
    :return:
    :rtype:
    """
    if sys.platform == 'win32':
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    return os.getuid() == 0


def temp_profile_dir() -> str:
    """generate a temp dir (path)"""
    return os.path.normpath(tempfile.mkdtemp(prefix='uc_'))


def find_binary(candidates: list[pathlib.Path]) -> str | None:
    rv: list[str] = []
    for candidate in candidates:
        if pathlib.Path(candidate).exists() and os.access(candidate, os.X_OK):
            logger.debug('%s is a valid candidate... ', candidate)
            rv.append(str(candidate))
        else:
            logger.debug("%s is not a valid candidate because don't exist or not executable ", candidate)

    winner: str | None = None
    if rv and len(rv) > 1:
        # assuming the shortest path wins
        winner = min(rv, key=len)

    elif len(rv) == 1:
        winner = rv[0]

    return winner


def find_executable(browser: BrowserType = 'auto') -> PathLike:
    """
    Finds the executable for the specified browser and returns its disk path.
    :param browser: The browser to find. Can be "chrome", "brave" or "auto".
    :return: The path to the browser executable.
    """
    browsers_to_try = []
    if browser == 'auto':
        browsers_to_try = ['chrome', 'brave']
    elif browser in {'chrome', 'brave'}:
        browsers_to_try = [browser]
    else:
        msg = "browser must be 'chrome', 'brave' or 'auto'"
        raise ValueError(msg)

    for browser_name in browsers_to_try:
        candidates: list[pathlib.Path] = []
        if browser_name == 'chrome':
            candidates.extend(get_chrome_locations())
        elif browser_name == 'brave':
            candidates.extend(get_brave_locations())

        winner = find_binary(candidates)
        if winner:
            return os.path.normpath(winner)

    msg = (
        'could not find a valid browser binary. please make sure it is installed '
        "or use the keyword argument 'browser_executable_path=/path/to/your/browser' "
    )
    raise FileNotFoundError(msg)


def get_chrome_locations() -> list[pathlib.Path]:
    candidates = []
    if is_posix:
        for item in os.environ['PATH'].split(os.pathsep):
            candidates.extend(
                pathlib.Path(item, subitem)
                for subitem in (
                    'google-chrome',
                    'chromium',
                    'chromium-browser',
                    'chrome',
                    'google-chrome-stable',
                )
            )
        if 'darwin' in sys.platform:
            candidates.extend(
                pathlib.Path(p)
                for p in [
                    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/Applications/Chromium.app/Contents/MacOS/Chromium',
                ]
            )
    else:
        for item2 in map(
            os.environ.get,
            (
                'PROGRAMFILES',
                'PROGRAMFILES(X86)',
                'LOCALAPPDATA',
                'PROGRAMW6432',
            ),
        ):
            if item2 is not None:
                candidates.extend(
                    pathlib.Path(item2, subitem, 'chrome.exe')
                    for subitem in (
                        'Google/Chrome/Application',
                        'Google/Chrome Beta/Application',
                        'Google/Chrome Canary/Application',
                        'Google/Chrome SxS/Application',
                    )
                )

    return candidates


def get_brave_locations() -> list[pathlib.Path]:
    candidates = []
    if is_posix:
        for item in os.environ['PATH'].split(os.pathsep):
            candidates.extend(
                pathlib.Path(item, subitem)
                for subitem in (
                    'brave-browser',
                    'brave',
                )
            )
        if 'darwin' in sys.platform:
            candidates.append(
                '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
            )
    else:
        for item2 in map(
            os.environ.get,
            ('PROGRAMFILES', 'PROGRAMFILES(X86)'),
        ):
            if item2 is not None:
                candidates.extend(
                    pathlib.Path(item2, subitem, 'brave.exe')
                    for subitem in ('BraveSoftware/Brave-Browser/Application',)
                )

    return candidates
