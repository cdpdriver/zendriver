from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from zendriver import cdp, util
from zendriver.core.element import Element

if TYPE_CHECKING:
    from zendriver.core.tab import Tab


logger = logging.getLogger(__name__)


async def cf_find_interactive_challenge(
    tab: Tab,
) -> tuple[Element | None, Element | None, Element | None]:
    """
    Finds the Cloudflare interactive challenge elements.

    This function scans the DOM for shadow roots and iframes that match the
    signature of a Cloudflare challenge.

    Returns:
        A tuple containing the host element, the shadow root element, and the
        challenge iframe element if found, otherwise (None, None, None).
    """
    logger.debug('Searching for Cloudflare interactive challenge elements...')
    doc = await tab.send(cdp.dom.get_document(-1, True))
    if not doc:
        logger.debug('DOM document not found.')
        return None, None, None

    # Find all nodes that have a "shadow root" (an isolated DOM).
    shadow_host_nodes = util.filter_recurse_all(
        doc,
        lambda n: hasattr(n, 'shadow_roots') and bool(n.shadow_roots),
    )
    logger.debug('Found %d shadow host nodes.', len(shadow_host_nodes))

    # Iterate over each shadow DOM host node.
    for host_node in shadow_host_nodes:
        if not host_node.shadow_roots:
            continue

        # Iterate over each shadow root within the host.
        for shadow_root_node in host_node.shadow_roots:
            # Create an Element object for the shadow root.
            # The "tree" for a shadow root element is the shadow root node itself.
            shadow_root_element = Element(shadow_root_node, tab, shadow_root_node)

            # Check if the shadow root content is the Cloudflare challenge.
            html_content = await shadow_root_element.get_html()
            if 'challenges.cloudflare.com' in html_content:
                logger.debug('Found Cloudflare challenge in a shadow root.')
                # If the shadow root is found, search for the specific iframe within it.
                for child_element in shadow_root_element.children:
                    if 'challenges.cloudflare.com' in await child_element.get_html():
                        # Found! Create the host element and return everything.
                        logger.debug('Found challenge iframe.')
                        host_element = Element(host_node, tab, doc)
                        challenge_iframe = child_element
                        return host_element, shadow_root_element, challenge_iframe

    # If the loops finish without finding anything, return None.
    logger.debug('Cloudflare interactive challenge not found.')
    return None, None, None


async def cf_wait_for_interactive_challenge(
    tab: Tab,
    timeout: float = 5,
) -> tuple[Element | None, Element | None, Element | None]:
    """
    Waits for the Cloudflare challenge iframe to appear and be visible.

    Args:
        timeout: The maximum time in seconds to wait for the elements.

    Returns:
        A tuple containing the host element, shadow root, and iframe element
        if found and visible, otherwise (None, None, None).
    """
    loop = asyncio.get_running_loop()
    start_time = loop.time()

    while loop.time() - start_time < timeout:
        logger.debug('Waiting for challenge elements to appear...')
        (
            host_element,
            shadow_root_element,
            challenge_iframe,
        ) = await cf_find_interactive_challenge(tab)
        if challenge_iframe and 'display: none' not in challenge_iframe.attrs.get(
            'style',
            '',
        ):
            logger.debug('Cloudflare challenge elements found and visible.')
            return host_element, shadow_root_element, challenge_iframe
        await asyncio.sleep(0.5)

    logger.warning(
        'Timeout: Cloudflare challenge elements not found or not visible within %s seconds.',
        timeout,
    )
    return None, None, None


async def cf_is_interactive_challenge_present(tab: Tab, timeout: float = 5) -> bool:
    """
    Checks if a Cloudflare interactive challenge is present and visible on the page.

    Args:
        timeout: The maximum time in seconds to wait for the challenge.

    Returns:
        True if the challenge is present and visible, False otherwise.
    """
    logger.debug(
        'Checking for Cloudflare challenge with a timeout of %s seconds.',
        timeout,
    )
    _, _, challenge_iframe = await cf_wait_for_interactive_challenge(tab, timeout)
    is_present = challenge_iframe is not None
    logger.debug('Challenge present: %s', is_present)
    return is_present


async def verify_cf(
    tab: Tab,
    click_delay: float = 5,
    timeout: float = 15,
    challenge_selector: str | None = None,
    flash_corners: bool = False,
) -> None:
    """
    Finds and solves the Cloudflare checkbox challenge.

    The total time for finding and clicking is governed by `timeout`.

    Args:
        click_delay: The delay in seconds between clicks.
        timeout: The total time in seconds to wait for the challenge and solve it.
        challenge_selector: An optional CSS selector for the challenge input element.
        flash_corners: If True, flash the corners of the challenge element.

    Raises:
        TimeoutError: If the checkbox is not found or solved within the timeout.
    """
    logger.debug('Waiting for Cloudflare checkbox...')
    loop = asyncio.get_running_loop()
    start_time = loop.time()

    (
        host_element,
        shadow_root_element,
        challenge_iframe,
    ) = await cf_wait_for_interactive_challenge(tab, timeout)

    if not challenge_iframe:
        raise TimeoutError(
            f'Cloudflare checkbox not found or not visible within {timeout} seconds.',
        )

    logger.debug('Cloudflare checkbox found, starting clicks.')

    await challenge_iframe.scroll_into_view()

    # To get the element's dimensions, its numeric 'node_id' is needed.
    # This ID is obtained from the underlying node object.
    logger.debug(
        f'Getting box model for challenge iframe (node_id: {challenge_iframe.node.node_id})',
    )
    box_model_result = await tab.send(
        cdp.dom.get_box_model(node_id=challenge_iframe.node.node_id),
    )
    # 'content_quad' is a list of 8 numbers representing the (x, y) coordinates
    # of the four corners of the element's "content-box": [x1, y1, x2, y2, x3, y3, x4, y4].
    content_quad = box_model_result.content

    # Extract only the x coordinates of the 4 corners
    x_coords = content_quad[0::2]
    # Extract only the y coordinates of the 4 corners
    y_coords = content_quad[1::2]

    min_x = min(x_coords)
    max_x = max(x_coords)
    min_y = min(y_coords)
    max_y = max(y_coords)

    click_x = min_x + (max_x - min_x) * 0.15
    click_y = min_y + (max_y - min_y) / 2

    logger.debug(
        f'Checkbox dimensions (content box): width={max_x - min_x}, height={max_y - min_y}',
    )

    if flash_corners:
        logger.debug('Showing flash_point at the 4 corners.')
        corners = list(zip(x_coords, y_coords, strict=False))
        for x_corner, y_corner in corners:
            await tab.flash_point(x=x_corner, y=y_corner, duration=10)

    if not host_element:
        return

    input_element = None
    current_selector = None

    # selector priority
    # 1. challenge_selector
    # 2. input[name=cf-turnstile-response]
    # 3. input[name=cf_challenge_response]

    # sometimes turnstile challenge have inputs 2 and 3.
    # input 2 is default for turnstile challenge.

    current_selector = challenge_selector or 'input[name=cf-turnstile-response]'
    input_element = await host_element.query_selector(current_selector)

    if not input_element and not challenge_selector:
        current_selector = 'input[name=cf_challenge_response]'
        input_element = await host_element.query_selector(current_selector)

    if not input_element:
        return

    checkbox_clicked = False

    async def check_input(
        input_el: Element,
        current_sltr: str,
        host_el: Element,
        ckbx_clckd: bool,
    ) -> bool:
        """Checks if the input element is still present and without a value."""
        if not input_el:
            return False
        try:
            await input_el
            fresh_input = await host_el.query_selector(current_sltr)
        except Exception as e:
            raise Exception(f'Error checking input element: {e}.')
        if (input_el.attrs.get('value') or not fresh_input) and ckbx_clckd:
            # If the input disappears or gets a value, assume it's successfully completed.
            logger.debug('Input element check successful (disappeared or has value).')
            return False
        return True

    while await check_input(
        input_el=input_element,
        current_sltr=current_selector,
        host_el=host_element,
        ckbx_clckd=checkbox_clicked,
    ):
        if loop.time() - start_time >= timeout:
            raise TimeoutError(
                f'Could not solve the checkbox in {timeout} seconds (timeout during clicks).',
            )
        try:
            await tab.mouse_click(click_x, click_y)
            await asyncio.sleep(click_delay)
            checkbox_clicked = True
        except Exception as e:
            if 'could not find position' in str(e) and checkbox_clicked:
                logger.debug('Checkbox disappeared after click. Assuming success.')
                break
            raise Exception(f'Error clicking checkbox: {e}.')

    logger.debug('Checkbox challenge completed. ✔')
    return
