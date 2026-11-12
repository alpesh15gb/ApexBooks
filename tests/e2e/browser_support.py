"""Shared, isolated browser selection for the web acceptance suites."""
import os
from pathlib import Path


def browser_engine():
    engine = os.environ.get('APEX_BROWSER_ENGINE', 'chromium')
    if engine not in {'chromium', 'firefox', 'webkit'}:
        raise RuntimeError('Unsupported browser engine')
    return engine


def launch_browser(playwright):
    engine = browser_engine()
    channel = os.environ.get('APEX_BROWSER_CHANNEL')
    if channel not in {None, 'chrome', 'msedge'}:
        raise RuntimeError('Unsupported isolated browser channel')
    if channel and engine != 'chromium':
        raise RuntimeError('Chrome/Edge channels require Chromium')
    executable = os.environ.get('APEX_BROWSER_EXECUTABLE')
    if executable and (channel or not Path(executable).is_file()):
        raise RuntimeError('Use an existing matching browser executable without a channel override')
    print(f'BROWSER ENGINE: {channel or engine} (fresh isolated profile)', flush=True)
    options = {'channel': channel} if channel else {}
    if executable:
        options['executable_path'] = str(Path(executable).resolve())
    return getattr(playwright, engine).launch(**options)


def mobile_context_options():
    # Firefox supports narrow viewports and touch, but not is_mobile emulation.
    options = {'viewport': {'width': 390, 'height': 844}, 'has_touch': True}
    if browser_engine() != 'firefox':
        options['is_mobile'] = True
    return options
