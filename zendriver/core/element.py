from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import pathlib
import secrets
import typing
import urllib.parse
from deprecated import deprecated

from .. import cdp
from . import util
from ._contradict import ContraDict
from .config import PathLike
from .keys import KeyEvents, KeyPressEvent, SpecialKeys

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from .tab import Tab


def create(
    node: cdp.dom.Node, tab: Tab, tree: typing.Optional[cdp.dom.Node] = None
) -> Element:
    """
    factory for Elements
    this is used with Tab.query_selector(_all), since we already have the tree,
    we don't need to fetch it for every single element.

    :param node: cdp dom node representation
    :param tab: the target object to which this element belongs
    :param tree: [Optional] the full node tree to which <node> belongs, enhances performance.
                when not provided, you need to call `await elem.update()` before using .children / .parent
    """

    elem = Element(node, tab, tree)

    return elem


class Element:
    def __init__(self, node: cdp.dom.Node, tab: Tab, tree: cdp.dom.Node | None = None):
        """
        Represents an (HTML) DOM Element

        :param node: cdp dom node representation
        :param tab: the target object to which this element belongs
        """
        if not node:
            raise Exception("node cannot be None")
        self._tab = tab
        # if node.node_name == 'IFRAME':
        #     self._node = node.content_document
        # else:
        self._node = node
        self._tree = tree
        self._remote_object: cdp.runtime.RemoteObject | None = None
        self._attrs = ContraDict(silent=True)
        self._make_attrs()

    @property
    def tag(self) -> str:
        return self.node_name.lower()

    @property
    def tag_name(self) -> str:
        return self.tag

    @property
    def node_id(self) -> cdp.dom.NodeId:
        return self.node.node_id

    @property
    def backend_node_id(self) -> cdp.dom.BackendNodeId:
        return self.node.backend_node_id

    @property
    def node_type(self) -> int:
        return self.node.node_type

    @property
    def node_name(self) -> str:
        return self.node.node_name

    @property
    def local_name(self) -> str:
        return self.node.local_name

    @property
    def node_value(self) -> str:
        return self.node.node_value

    @property
    def parent_id(self) -> cdp.dom.NodeId | None:
        return self.node.parent_id

    @property
    def child_node_count(self) -> int | None:
        return self.node.child_node_count

    @property
    def attributes(self) -> list[str] | None:
        return self.node.attributes

    @property
    def document_url(self) -> str | None:
        return self.node.document_url

    @property
    def base_url(self) -> str | None:
        return self.node.base_url

    @property
    def public_id(self) -> str | None:
        return self.node.public_id

    @property
    def system_id(self) -> str | None:
        return self.node.system_id

    @property
    def internal_subset(self) -> str | None:
        return self.node.internal_subset

    @property
    def xml_version(self) -> str | None:
        return self.node.xml_version

    @property
    def value(self) -> str | None:
        return self.node.value

    @property
    def pseudo_type(self) -> cdp.dom.PseudoType | None:
        return self.node.pseudo_type

    @property
    def pseudo_identifier(self) -> str | None:
        return self.node.pseudo_identifier

    @property
    def shadow_root_type(self) -> cdp.dom.ShadowRootType | None:
        return self.node.shadow_root_type

    @property
    def frame_id(self) -> cdp.page.FrameId | None:
        return self.node.frame_id

    @property
    def content_document(self) -> cdp.dom.Node | None:
        return self.node.content_document

    @property
    def shadow_roots(self) -> list[cdp.dom.Node] | None:
        return self.node.shadow_roots

    @property
    def template_content(self) -> cdp.dom.Node | None:
        return self.node.template_content

    @property
    def pseudo_elements(self) -> list[cdp.dom.Node] | None:
        return self.node.pseudo_elements

    @property
    def imported_document(self) -> cdp.dom.Node | None:
        return self.node.imported_document

    @property
    def distributed_nodes(self) -> list[cdp.dom.BackendNode] | None:
        return self.node.distributed_nodes

    @property
    def is_svg(self) -> bool | None:
        return self.node.is_svg

    @property
    def compatibility_mode(self) -> cdp.dom.CompatibilityMode | None:
        return self.node.compatibility_mode

    @property
    def assigned_slot(self) -> cdp.dom.BackendNode | None:
        return self.node.assigned_slot

    @property
    def tab(self) -> Tab:
        return self._tab

    @deprecated(reason="Use get() instead")
    def __getattr__(self, item: str) -> str | None:
        # if attribute is not found on the element python object
        # check if it may be present in the element attributes (eg, href=, src=, alt=)
        # returns None when attribute is not found
        # instead of raising AttributeError
        x = getattr(self.attrs, item, None)
        if x:
            return x  # type: ignore
        return None

    #     x = getattr(self.node, item, None)
    #
    #     return x

    def get(self, name: str) -> str | None:
        """
        Returns the value of the attribute with the given name, or None if it does not exist.

        For example, if the element has an attribute `href="#"`, you can retrieve it with:
            href = element.get("href")

        :param name: The name of the attribute to retrieve.
        :return: The value of the attribute, or None if it does not exist.
        :rtype: str | None
        """
        try:
            x = getattr(self.attrs, name, None)
            if x:
                return x  # type: ignore
            return None
        except AttributeError:
            return None

    def __setattr__(self, key: str, value: typing.Any) -> None:
        if key[0] != "_":
            if key[1:] not in vars(self).keys():
                # we probably deal with an attribute of
                # the html element, so forward it
                self.attrs.__setattr__(key, value)
                return
        # we probably deal with an attribute of
        # the python object
        super().__setattr__(key, value)

    def __setitem__(self, key: str, value: typing.Any) -> None:
        if key[0] != "_":
            if key[1:] not in vars(self).keys():
                # we probably deal with an attribute of
                # the html element, so forward it
                self.attrs[key] = value

    def __getitem__(self, item: str) -> typing.Any:
        # we probably deal with an attribute of
        # the html element, so forward it
        return self.attrs.get(item, None)

    async def save_to_dom(self) -> None:
        """
        saves element to dom
        :return:
        :rtype:
        """
        self._remote_object = await self._tab.send(
            cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
        )
        await self._tab.send(cdp.dom.set_outer_html(self.node_id, outer_html=str(self)))
        await self.update()

    async def remove_from_dom(self) -> None:
        """removes the element from dom"""
        await self.update()  # ensure we have latest node_id
        if not self.tree:
            raise RuntimeError(
                "could not remove from dom since the element has no tree set"
            )
        node = util.filter_recurse(
            self.tree, lambda node: node.backend_node_id == self.backend_node_id
        )
        if node:
            await self.tab.send(cdp.dom.remove_node(node.node_id))
        # self._tree = util.remove_from_tree(self.tree, self.node)

    async def update(self, _node: cdp.dom.Node | None = None) -> Element:
        """
        updates element to retrieve more properties. for example this enables
        :py:obj:`~children` and :py:obj:`~parent` attributes.

        also resolves js opbject which is stored object in :py:obj:`~remote_object`

        usually you will get element nodes by the usage of

        :py:meth:`Tab.query_selector_all()`

        :py:meth:`Tab.find_elements_by_text()`

        those elements are already updated and you can browse through children directly.

        The reason for a seperate call instead of doing it at initialization,
        is because when you are retrieving 100+ elements this becomes quite expensive.

        therefore, it is not advised to call this method on a bunch of blocks (100+) at the same time.

        :return:
        :rtype:
        """
        if _node:
            doc = _node
            # self._node = _node
            # self._children.clear()
        else:
            doc = await self._tab.send(cdp.dom.get_document(-1, True))
        # if self.node_name != "IFRAME":
        updated_node = util.filter_recurse(
            doc, lambda n: n.backend_node_id == self._node.backend_node_id
        )
        if updated_node:
            logger.debug("node seems changed, and has now been updated.")
            self._node = updated_node
        self._tree = doc

        self._remote_object = await self._tab.send(
            cdp.dom.resolve_node(backend_node_id=self._node.backend_node_id)
        )
        self.attrs.clear()
        self._make_attrs()
        return self

    @property
    def node(self) -> cdp.dom.Node:
        return self._node

    @property
    def tree(self) -> cdp.dom.Node | None:
        return self._tree

    @tree.setter
    def tree(self, tree: cdp.dom.Node) -> None:
        self._tree = tree

    @property
    def attrs(self) -> ContraDict:
        """
        attributes are stored here, however, you can set them directly on the element object as well.
        :return:
        :rtype:
        """
        return self._attrs

    @property
    def parent(self) -> typing.Union[Element, None]:
        """
        get the parent element (node) of current element(node)
        :return:
        :rtype:
        """
        if not self.tree:
            raise RuntimeError("could not get parent since the element has no tree set")
        parent_node = util.filter_recurse(
            self.tree, lambda n: n.node_id == self.parent_id
        )
        if not parent_node:
            return None
        parent_element = create(parent_node, tab=self._tab, tree=self.tree)
        return parent_element

    @property
    def children(self) -> list[Element]:
        """
        returns the elements' children. those children also have a children property
        so you can browse through the entire tree as well.
        :return:
        :rtype:
        """
        _children = []
        if self._node.node_name == "IFRAME":
            # iframes are not exact the same as other nodes
            # the children of iframes are found under
            # the .content_document property, which is of more
            # use than the node itself
            frame = self._node.content_document
            if not frame or not frame.children or not frame.child_node_count:
                return []
            for child in frame.children:
                child_elem = create(child, self._tab, frame)
                if child_elem:
                    _children.append(child_elem)
            # self._node = frame
            return _children
        elif not self.node.child_node_count:
            return []
        if self.node.children:
            for child in self.node.children:
                child_elem = create(child, self._tab, self.tree)
                if child_elem:
                    _children.append(child_elem)
        return _children

    @property
    def remote_object(self) -> cdp.runtime.RemoteObject | None:
        return self._remote_object

    @property
    def object_id(self) -> cdp.runtime.RemoteObjectId | None:
        if not self.remote_object:
            return None
        return self.remote_object.object_id

    async def click(self) -> None:
        """
        Click the element.

        :return:
        :rtype:
        """
        self._remote_object = await self._tab.send(
            cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
        )
        if self._remote_object.object_id is None:
            raise ValueError("could not resolve object id for %s" % self)

        arguments = [cdp.runtime.CallArgument(object_id=self._remote_object.object_id)]
        await self.flash(0.25)
        await self._tab.send(
            cdp.runtime.call_function_on(
                "(el) => el.click()",
                object_id=self._remote_object.object_id,
                arguments=arguments,
                await_promise=True,
                user_gesture=True,
                return_by_value=True,
            )
        )

    async def get_js_attributes(self) -> ContraDict:
        return ContraDict(
            json.loads(
                await self.apply(
                    """
            function (e) {
                let o = {}
                for(let k in e){
                    o[k] = e[k]
                }
                return JSON.stringify(o)
            }
            """
                )
            )
        )

    def __await__(self) -> typing.Any:
        return self.update().__await__()

    def __call__(self, js_method: str) -> typing.Any:
        """
        calling the element object will call a js method on the object
        eg, element.play() in case of a video element, it will call .play()
        :param js_method:
        :return:
        :rtype:
        """
        return self.apply(f"(e) => e['{js_method}']()")

    async def apply(
        self,
        js_function: str,
        return_by_value: bool = True,
        *,
        await_promise: bool = False,
    ) -> typing.Any:
        """
        apply javascript to this element. the given js_function string should accept the js element as parameter,
        and can be a arrow function, or function declaration.
        eg:
            - '(elem) => { elem.value = "blabla"; consolelog(elem); alert(JSON.stringify(elem); } '
            - 'elem => elem.play()'
            - function myFunction(elem) { alert(elem) }

        :param js_function: the js function definition which received this element.
        :param return_by_value:
        :param await_promise: when True, waits for the promise to resolve before returning
        :return:
        :rtype:
        """
        self._remote_object = await self._tab.send(
            cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
        )
        result: typing.Tuple[
            cdp.runtime.RemoteObject, typing.Any
        ] = await self._tab.send(
            cdp.runtime.call_function_on(
                js_function,
                object_id=self._remote_object.object_id,
                arguments=[
                    cdp.runtime.CallArgument(object_id=self._remote_object.object_id)
                ],
                return_by_value=True,
                user_gesture=True,
                await_promise=await_promise,
            )
        )
        if result and result[0]:
            if return_by_value:
                return result[0].value
            return result[0]
        elif result[1]:
            return result[1]

    async def get_position(self, abs: bool = False) -> Position | None:
        if not self._remote_object or not self.parent or not self.object_id:
            self._remote_object = await self._tab.send(
                cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
            )
        try:
            quads = await self.tab.send(
                cdp.dom.get_content_quads(object_id=self._remote_object.object_id)
            )
            if not quads:
                raise Exception("could not find position for %s " % self)
            pos = Position(quads[0])
            if abs:
                scroll_y = (await self.tab.evaluate("window.scrollY")).value  # type: ignore
                scroll_x = (await self.tab.evaluate("window.scrollX")).value  # type: ignore
                abs_x = pos.left + scroll_x + (pos.width / 2)
                abs_y = pos.top + scroll_y + (pos.height / 2)
                pos.abs_x = abs_x
                pos.abs_y = abs_y
            return pos
        except IndexError:
            logger.debug(
                "no content quads for %s. mostly caused by element which is not 'in plain sight'"
                % self
            )
            return None

    async def mouse_click(
        self,
        button: str = "left",
        buttons: typing.Optional[int] = 1,
        modifiers: typing.Optional[int] = 0,
        hold: bool = False,
        _until_event: typing.Optional[type] = None,
    ) -> None:
        """native click (on element) . note: this likely does not work atm, use click() instead

        :param button: str (default = "left")
        :param buttons: which button (default 1 = left)
        :param modifiers: *(Optional)* Bit field representing pressed modifier keys.
                Alt=1, Ctrl=2, Meta/Command=4, Shift=8 (default: 0).
        :param _until_event: internal. event to wait for before returning
        :return:

        """
        position = await self.get_position()
        if not position:
            logger.warning("could not find location for %s, not clicking", self)
            return
        center = position.center
        logger.debug("clicking on location %.2f, %.2f" % center)

        await asyncio.gather(
            self._tab.send(
                cdp.input_.dispatch_mouse_event(
                    "mousePressed",
                    x=center[0],
                    y=center[1],
                    modifiers=modifiers,
                    button=cdp.input_.MouseButton(button),
                    buttons=buttons,
                    click_count=1,
                )
            ),
            self._tab.send(
                cdp.input_.dispatch_mouse_event(
                    "mouseReleased",
                    x=center[0],
                    y=center[1],
                    modifiers=modifiers,
                    button=cdp.input_.MouseButton(button),
                    buttons=buttons,
                    click_count=1,
                )
            ),
        )
        try:
            await self.flash()
        except:  # noqa
            pass

    async def mouse_move(self) -> None:
        """moves mouse (not click), to element position. when an element has an
        hover/mouseover effect, this would trigger it"""
        position = await self.get_position()
        if not position:
            logger.warning("could not find location for %s, not moving mouse", self)
            return
        center = position.center
        logger.debug(
            "mouse move to location %.2f, %.2f where %s is located", *center, self
        )
        await self._tab.send(
            cdp.input_.dispatch_mouse_event("mouseMoved", x=center[0], y=center[1])
        )
        await self._tab.sleep(0.05)
        await self._tab.send(
            cdp.input_.dispatch_mouse_event("mouseReleased", x=center[0], y=center[1])
        )

    async def mouse_drag(
        self,
        destination: typing.Union[Element, typing.Tuple[int, int]],
        relative: bool = False,
        steps: int = 1,
    ) -> None:
        """
        drag an element to another element or target coordinates. dragging of elements should be supported  by the site of course


        :param destination: target Element or coordinates (x,y) to drag to
        :param relative: when True, treats coordinate as relative. for example (-100, 200) will move left 100px and down 200px
        :param steps: move in <steps> points, this could make it look more "natural" (default 1),
               but also a lot slower.
               for very smooth action use 50-100
        :return:
        :rtype:
        """
        start_position = await self.get_position()
        if not start_position:
            logger.warning("could not find location for %s, not dragging", self)
            return
        start_point = start_position.center
        end_point = None
        if isinstance(destination, Element):
            end_position = await destination.get_position()
            if not end_position:
                logger.warning(
                    "could not calculate box model for %s, not dragging", destination
                )
                return
            end_point = end_position.center
        elif isinstance(destination, (tuple, list)):
            if relative:
                end_point = (
                    start_point[0] + destination[0],
                    start_point[1] + destination[1],
                )
            else:
                end_point = destination

        await self._tab.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=start_point[0],
                y=start_point[1],
                button=cdp.input_.MouseButton("left"),
            )
        )

        steps = 1 if (not steps or steps < 1) else steps
        if steps == 1:
            await self._tab.send(
                cdp.input_.dispatch_mouse_event(
                    "mouseMoved",
                    x=end_point[0],
                    y=end_point[1],
                )
            )
        elif steps > 1:
            # probably the worst waay of calculating this. but couldn't think of a better solution today.
            step_size_x = (end_point[0] - start_point[0]) / steps
            step_size_y = (end_point[1] - start_point[1]) / steps
            pathway = [
                (start_point[0] + step_size_x * i, start_point[1] + step_size_y * i)
                for i in range(steps + 1)
            ]

            for point in pathway:
                await self._tab.send(
                    cdp.input_.dispatch_mouse_event(
                        "mouseMoved",
                        x=point[0],
                        y=point[1],
                    )
                )
                await asyncio.sleep(0)

        await self._tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=end_point[0],
                y=end_point[1],
                button=cdp.input_.MouseButton("left"),
            )
        )

    async def scroll_into_view(self) -> None:
        """scrolls element into view"""
        try:
            await self.tab.send(
                cdp.dom.scroll_into_view_if_needed(backend_node_id=self.backend_node_id)
            )
        except Exception as e:
            logger.debug("could not scroll into view: %s", e)
            return

        # await self.apply("""(el) => el.scrollIntoView(false)""")

    async def clear_input(self) -> None:
        """clears an input field"""
        await self.apply('function (element) { element.value = "" } ')

    async def clear_input_by_deleting(self) -> None:
        """
        clears the input of the element by simulating a series of delete key presses.

        this method applies a JavaScript function that simulates pressing the delete key
        repeatedly until the input is empty. it is useful for clearing input fields or text areas
        when :func:`clear_input` does not work (for example, when custom input handling is implemented on the page).
        """
        await self.apply(
            """
                async function clearByDeleting(n, d = 50) {
                    n.focus();
                    n.setSelectionRange(0, 0);
                    while (n.value.length > 0) {
                        n.dispatchEvent(
                            new KeyboardEvent("keydown", {
                                key: "Delete",
                                code: "Delete",
                                keyCode: 46,
                                which: 46,
                                bubbles: !0,
                                cancelable: !0,
                            })
                        );
                        n.value = n.value.slice(1);
                        await new Promise((r) => setTimeout(r, d));
                    }
                    n.dispatchEvent(new Event("input", { bubbles: !0 }));
                }
            """,
            await_promise=True,
        )

    async def send_keys(
        self, text: typing.Union[str, SpecialKeys, typing.List[KeyEvents.Payload]]
    ) -> None:
        """
        send text to an input field, or any other html element.

        hint, if you ever get stuck where using py:meth:`~click`
        does not work, sending the keystroke \\n or \\r\\n or a spacebar work wonders!
        :param text: text to send
        :return: None
        """
        await self.apply("(elem) => elem.focus()")
        cluster_list: typing.List[KeyEvents.Payload]
        if isinstance(text, str):
            cluster_list = KeyEvents.from_text(text, KeyPressEvent.CHAR)
        elif isinstance(text, SpecialKeys):
            cluster_list = KeyEvents(text).to_cdp_events(KeyPressEvent.DOWN_AND_UP)
        else:
            cluster_list = text

        for cluster in cluster_list:
            await self._tab.send(cdp.input_.dispatch_key_event(**cluster))

    async def send_file(self, *file_paths: PathLike) -> None:
        """
        some form input require a file (upload), a full path needs to be provided.
        this method sends 1 or more file(s) to the input field.

        needles to say, but make sure the field accepts multiple files if you want to send more files.
        otherwise the browser might crash.

        example :
        `await fileinputElement.send_file('c:/temp/image.png', 'c:/users/myuser/lol.gif')`

        """
        file_paths_as_str = [str(p) for p in file_paths]
        await self._tab.send(
            cdp.dom.set_file_input_files(
                files=[*file_paths_as_str],
                backend_node_id=self.backend_node_id,
                object_id=self.object_id,
            )
        )

    async def focus(self) -> None:
        """focus the current element. often useful in form (select) fields"""
        await self.apply("(element) => element.focus()")

    async def select_option(self) -> None:
        """
        for form (select) fields. when you have queried the options you can call this method on the option object.
        02/08/2024: fixed the problem where events are not fired when programattically selecting an option.

        calling :func:`option.select_option()` will use that option as selected value.
        does not work in all cases.

        """
        if self.node_name == "OPTION":
            await self.apply(
                """
                (o) => {
                    o.selected = true ;
                    o.dispatchEvent(new Event('change', {view: window,bubbles: true}))
                }
                """
            )

    async def set_value(self, value: str) -> None:
        await self._tab.send(cdp.dom.set_node_value(node_id=self.node_id, value=value))

    async def set_text(self, value: str) -> None:
        if not self.node_type == 3:
            if self.child_node_count == 1:
                child_node = self.children[0]
                if not isinstance(child_node, Element):
                    raise RuntimeError("could only set value of text nodes")
                await child_node.set_text(value)
                await self.update()
                return
            else:
                raise RuntimeError("could only set value of text nodes")
        await self.update()
        await self._tab.send(cdp.dom.set_node_value(node_id=self.node_id, value=value))

    async def get_html(self) -> str:
        return await self._tab.send(
            cdp.dom.get_outer_html(backend_node_id=self.backend_node_id)
        )

    @property
    def text(self) -> str:
        """
        gets the text contents of this element
        note: this includes text in the form of script content, as those are also just 'text nodes'

        :return:
        :rtype:
        """
        text_node = util.filter_recurse(self.node, lambda n: n.node_type == 3)
        if text_node:
            return text_node.node_value
        return ""

    @property
    def text_all(self) -> str:
        """
        gets the text contents of this element, and it's children in a concatenated string
        note: this includes text in the form of script content, as those are also just 'text nodes'
        :return:
        :rtype:
        """
        text_nodes = util.filter_recurse_all(self.node, lambda n: n.node_type == 3)
        return " ".join([n.node_value for n in text_nodes])

    async def query_selector_all(self, selector: str) -> list[Element]:
        """
        like js querySelectorAll()
        """
        await self.update()
        return await self.tab.query_selector_all(selector, _node=self)

    async def query_selector(self, selector: str) -> Element | None:
        """
        like js querySelector()
        """

        await self.update()
        return await self.tab.query_selector(selector, self)

    async def screenshot_b64(
        self,
        format: str = "jpeg",
        scale: typing.Optional[typing.Union[int, float]] = 1,
    ) -> str:
        """
        Takes a screenshot of this element (only) and return the result as a base64 encoded string.
        This is not the same as :py:obj:`Tab.screenshot_b64`, which takes a "regular" screenshot

        When the element is hidden, or has no size, or is otherwise not capturable, a RuntimeError is raised

        :param format: jpeg or png (defaults to jpeg)
        :param scale: the scale of the screenshot, eg: 1 = size as is, 2 = double, 0.5 is half
        :return: screenshot data as base64 encoded
        :rtype: str
        """
        pos = await self.get_position()
        if not pos:
            raise RuntimeError(
                "could not determine position of element. probably because it's not in view, or hidden"
            )
        viewport = pos.to_viewport(float(scale if scale else 1))
        await self.tab.sleep()

        data = await self._tab.send(
            cdp.page.capture_screenshot(
                format, clip=viewport, capture_beyond_viewport=True
            )
        )

        if not data:
            from .connection import ProtocolException

            raise ProtocolException(
                "could not take screenshot. most possible cause is the page has not finished loading yet."
            )

        return data

    async def save_screenshot(
        self,
        filename: typing.Optional[PathLike] = "auto",
        format: str = "jpeg",
        scale: typing.Optional[typing.Union[int, float]] = 1,
    ) -> str:
        """
        Saves a screenshot of this element (only)
        This is not the same as :py:obj:`Tab.save_screenshot`, which saves a "regular" screenshot

        When the element is hidden, or has no size, or is otherwise not capturable, a RuntimeError is raised

        :param filename: uses this as the save path
        :param format: jpeg or png (defaults to jpeg)
        :param scale: the scale of the screenshot, eg: 1 = size as is, 2 = double, 0.5 is half
        :return: the path/filename of saved screenshot
        :rtype: str
        """
        await self.tab.sleep()

        if not filename or filename == "auto":
            parsed = urllib.parse.urlparse(self.tab.target.url)  # type: ignore
            parts = parsed.path.split("/")
            last_part = parts[-1]
            last_part = last_part.rsplit("?", 1)[0]
            dt_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            candidate = f"{parsed.hostname}__{last_part}_{dt_str}"
            ext = ""
            if format.lower() in ["jpg", "jpeg"]:
                ext = ".jpg"
            elif format.lower() in ["png"]:
                ext = ".png"
            path = pathlib.Path(candidate + ext)
        else:
            path = pathlib.Path(filename)

        path.parent.mkdir(parents=True, exist_ok=True)

        data = await self.screenshot_b64(format, scale)

        data_bytes = base64.b64decode(data)
        if not path:
            raise RuntimeError("invalid filename or path: '%s'" % filename)
        path.write_bytes(data_bytes)
        return str(path)

    async def flash(self, duration: typing.Union[float, int] = 0.5) -> None:
        """
        displays for a short time a red dot on the element (only if the element itself is visible)

        :param duration: seconds (default 0.5)
        :return:
        :rtype:
        """
        from .connection import ProtocolException

        if not self._remote_object:
            try:
                self._remote_object = await self.tab.send(
                    cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
                )
            except ProtocolException:
                return
        if not self._remote_object or not self._remote_object.object_id:
            raise ValueError("could not resolve object id for %s" % self)
        pos = await self.get_position()
        if pos is None:
            logger.warning("flash() : could not determine position")
            return

        style = (
            "position:absolute;z-index:99999999;padding:0;margin:0;"
            "left:{:.1f}px; top: {:.1f}px;"
            "opacity:1;"
            "width:16px;height:16px;border-radius:50%;background:red;"
            "animation:show-pointer-ani {:.2f}s ease 1;"
        ).format(
            pos.center[0] - 8,  # -8 to account for drawn circle itself (w,h)
            pos.center[1] - 8,
            duration,
        )
        script = (
            """
            (targetElement) => {{
                var css = document.styleSheets[0];
                for( let css of [...document.styleSheets]) {{
                    try {{
                        css.insertRule(`
                        @keyframes show-pointer-ani {{
                              0% {{ opacity: 1; transform: scale(2, 2);}}
                              25% {{ transform: scale(5,5) }}
                              50% {{ transform: scale(3, 3);}}
                              75%: {{ transform: scale(2,2) }}
                              100% {{ transform: scale(1, 1); opacity: 0;}}
                        }}`,css.cssRules.length);
                        break;
                    }} catch (e) {{
                        console.log(e)
                    }}
                }};
                var _d = document.createElement('div');
                _d.style = `{0:s}`;
                _d.id = `{1:s}`;
                document.body.insertAdjacentElement('afterBegin', _d);

                setTimeout( () => document.getElementById('{1:s}').remove(), {2:d});
            }}
            """.format(
                style,
                secrets.token_hex(8),
                int(duration * 1000),
            )
            .replace("  ", "")
            .replace("\n", "")
        )

        arguments = [cdp.runtime.CallArgument(object_id=self._remote_object.object_id)]
        await self._tab.send(
            cdp.runtime.call_function_on(
                script,
                object_id=self._remote_object.object_id,
                arguments=arguments,
                await_promise=True,
                user_gesture=True,
            )
        )

    async def highlight_overlay(self) -> None:
        """
        highlights the element devtools-style. To remove the highlight,
        call the method again.
        :return:
        :rtype:
        """

        if getattr(self, "_is_highlighted", False):
            del self._is_highlighted
            await self.tab.send(cdp.overlay.hide_highlight())
            await self.tab.send(cdp.dom.disable())
            await self.tab.send(cdp.overlay.disable())
            return
        await self.tab.send(cdp.dom.enable())
        await self.tab.send(cdp.overlay.enable())
        conf = cdp.overlay.HighlightConfig(
            show_info=True, show_extension_lines=True, show_styles=True
        )
        await self.tab.send(
            cdp.overlay.highlight_node(
                highlight_config=conf, backend_node_id=self.backend_node_id
            )
        )
        setattr(self, "_is_highlighted", 1)

    async def record_video(
        self,
        filename: typing.Optional[str] = None,
        folder: typing.Optional[str] = None,
        duration: typing.Optional[typing.Union[int, float]] = None,
    ) -> None:
        """
        experimental option.

        :param filename: the desired filename
        :param folder: the download folder path
        :param duration: record for this many seconds and then download

        on html5 video nodes, you can call this method to start recording of the video.

        when any of the follow happens:

        - video ends
        - calling videoelement('pause')
        - video stops

        the video recorded will be downloaded.

        """
        if self.node_name != "VIDEO":
            raise RuntimeError(
                "record_video can only be called on html5 video elements"
            )
        if not folder:
            directory_path = pathlib.Path.cwd() / "downloads"
        else:
            directory_path = pathlib.Path(folder)

        directory_path.mkdir(exist_ok=True)
        await self._tab.send(
            cdp.browser.set_download_behavior(
                "allow", download_path=str(directory_path)
            )
        )
        await self("pause")
        await self.apply(
            """
            function extractVid(vid) {{

                      var duration = {duration:.1f};
                      var stream = vid.captureStream();
                      var mr = new MediaRecorder(stream, {{audio:true, video:true}})
                      mr.ondataavailable  = function(e) {{
                          vid['_recording'] = false
                          var blob = e.data;
                          f = new File([blob], {{name: {filename}, type:'octet/stream'}});
                          var objectUrl = URL.createObjectURL(f);
                          var link = document.createElement('a');
                          link.setAttribute('href', objectUrl)
                          link.setAttribute('download', {filename})
                          link.style.display = 'none'

                          document.body.appendChild(link)

                          link.click()

                          document.body.removeChild(link)
                       }}

                       mr.start()
                       vid.addEventListener('ended' , (e) => mr.stop())
                       vid.addEventListener('pause' , (e) => mr.stop())
                       vid.addEventListener('abort', (e) => mr.stop())


                       if ( duration ) {{
                            setTimeout(() => {{ vid.pause(); vid.play() }}, duration);
                       }}
                       vid['_recording'] = true
                  ;}}

            """.format(
                filename=f'"{filename}"' if filename else 'document.title + ".mp4"',
                duration=int(duration * 1000) if duration else 0,
            )
        )
        await self("play")
        await self._tab

    async def is_recording(self) -> bool:
        return await self.apply('(vid) => vid["_recording"]')  # type: ignore

    def _make_attrs(self) -> None:
        sav = None
        if self.node.attributes:
            for i, a in enumerate(self.node.attributes):
                if i == 0 or i % 2 == 0:
                    if a == "class":
                        a = "class_"
                    sav = a
                else:
                    if sav:
                        self.attrs[sav] = a

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Element):
            return False

        if other.backend_node_id and self.backend_node_id:
            return other.backend_node_id == self.backend_node_id

        return False

    def __repr__(self) -> str:
        tag_name = self.node.node_name.lower()
        content = ""

        # collect all text from this leaf
        if self.child_node_count:
            if self.child_node_count == 1:
                if self.children:
                    content += str(self.children[0])

            elif self.child_node_count > 1:
                if self.children:
                    for child in self.children:
                        content += str(child)

        if self.node.node_type == 3:  # we could be a text node ourselves
            content += self.node_value

            # return text only, no tag names
            # this makes it look most natural, and compatible with other hml libs

            return content

        attrs = " ".join(
            [f'{k if k != "class_" else "class"}="{v}"' for k, v in self.attrs.items()]
        )
        s = f"<{tag_name} {attrs}>{content}</{tag_name}>"
        return s


class Position(cdp.dom.Quad):
    """helper class for element positioning"""

    def __init__(self, points: list[float]):
        super().__init__(points)
        (
            self.left,
            self.top,
            self.right,
            self.top,
            self.right,
            self.bottom,
            self.left,
            self.bottom,
        ) = points
        self.abs_x: float = 0
        self.abs_y: float = 0
        self.x = self.left
        self.y = self.top
        self.height, self.width = (self.bottom - self.top, self.right - self.left)
        self.center = (
            self.left + (self.width / 2),
            self.top + (self.height / 2),
        )

    def to_viewport(self, scale: float = 1) -> cdp.page.Viewport:
        return cdp.page.Viewport(
            x=self.x, y=self.y, width=self.width, height=self.height, scale=scale
        )

    def __repr__(self) -> str:
        return f"<Position(x={self.left}, y={self.top}, width={self.width}, height={self.height})>"


async def resolve_node(tab: Tab, node_id: cdp.dom.NodeId) -> cdp.dom.Node:
    remote_obj: cdp.runtime.RemoteObject = await tab.send(
        cdp.dom.resolve_node(node_id=node_id)
    )
    if remote_obj.object_id is None:
        raise RuntimeError("could not resolve object")

    node_id = await tab.send(cdp.dom.request_node(remote_obj.object_id))
    node: cdp.dom.Node = await tab.send(cdp.dom.describe_node(node_id))
    return node
