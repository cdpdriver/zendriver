raw_bindings_controller_source = """
var __commonJS = obj => {
  let required = false;
  let result;
  return function __require() {
    if (!required) {
      required = true;
      let fn;
      for (const name in obj) { fn = obj[name]; break; }
      const module = { exports: {} };
      fn(module.exports, module);
      result = module.exports;
    }
    return result;
  }
};
var __export = (target, all) => {for (var name in all) target[name] = all[name];};
var __toESM = mod => ({ ...mod, 'default': mod });
var __toCommonJS = mod => ({ ...mod, __esModule: true });
// packages/injected/src/bindingsController.ts
var bindingsController_exports = {};
__export(bindingsController_exports, {
  BindingsController: () => BindingsController
});
module.exports = __toCommonJS(bindingsController_exports);
// packages/playwright-core/src/utils/isomorphic/utilityScriptSerializers.ts
function isRegExp(obj) {
  try {
    return obj instanceof RegExp || Object.prototype.toString.call(obj) === "[object RegExp]";
  } catch (error) {
    return false;
  }
}
function isDate(obj) {
  try {
    return obj instanceof Date || Object.prototype.toString.call(obj) === "[object Date]";
  } catch (error) {
    return false;
  }
}
function isURL(obj) {
  try {
    return obj instanceof URL || Object.prototype.toString.call(obj) === "[object URL]";
  } catch (error) {
    return false;
  }
}
function isError(obj) {
  var _a;
  try {
    return obj instanceof Error || obj && ((_a = Object.getPrototypeOf(obj)) == null ? void 0 : _a.name) === "Error";
  } catch (error) {
    return false;
  }
}
function isTypedArray(obj, constructor) {
  try {
    return obj instanceof constructor || Object.prototype.toString.call(obj) === `[object ${constructor.name}]`;
  } catch (error) {
    return false;
  }
}
var typedArrayConstructors = {
  i8: Int8Array,
  ui8: Uint8Array,
  ui8c: Uint8ClampedArray,
  i16: Int16Array,
  ui16: Uint16Array,
  i32: Int32Array,
  ui32: Uint32Array,
  // TODO: add Float16Array once it's in baseline
  f32: Float32Array,
  f64: Float64Array,
  bi64: BigInt64Array,
  bui64: BigUint64Array
};
function typedArrayToBase64(array) {
  if ("toBase64" in array)
    return array.toBase64();
  const binary = Array.from(new Uint8Array(array.buffer, array.byteOffset, array.byteLength)).map((b) => String.fromCharCode(b)).join("");
  return btoa(binary);
}
function serializeAsCallArgument(value, handleSerializer) {
  return serialize(value, handleSerializer, { visited: /* @__PURE__ */ new Map(), lastId: 0 });
}
function serialize(value, handleSerializer, visitorInfo) {
  if (value && typeof value === "object") {
    if (typeof globalThis.Window === "function" && value instanceof globalThis.Window)
      return "ref: <Window>";
    if (typeof globalThis.Document === "function" && value instanceof globalThis.Document)
      return "ref: <Document>";
    if (typeof globalThis.Node === "function" && value instanceof globalThis.Node)
      return "ref: <Node>";
  }
  return innerSerialize(value, handleSerializer, visitorInfo);
}
function innerSerialize(value, handleSerializer, visitorInfo) {
  var _a;
  const result = handleSerializer(value);
  if ("fallThrough" in result)
    value = result.fallThrough;
  else
    return result;
  if (typeof value === "symbol")
    return { v: "undefined" };
  if (Object.is(value, void 0))
    return { v: "undefined" };
  if (Object.is(value, null))
    return { v: "null" };
  if (Object.is(value, NaN))
    return { v: "NaN" };
  if (Object.is(value, Infinity))
    return { v: "Infinity" };
  if (Object.is(value, -Infinity))
    return { v: "-Infinity" };
  if (Object.is(value, -0))
    return { v: "-0" };
  if (typeof value === "boolean")
    return value;
  if (typeof value === "number")
    return value;
  if (typeof value === "string")
    return value;
  if (typeof value === "bigint")
    return { bi: value.toString() };
  if (isError(value)) {
    let stack;
    if ((_a = value.stack) == null ? void 0 : _a.startsWith(value.name + ": " + value.message)) {
      stack = value.stack;
    } else {
      stack = `${value.name}: ${value.message}
${value.stack}`;
    }
    return { e: { n: value.name, m: value.message, s: stack } };
  }
  if (isDate(value))
    return { d: value.toJSON() };
  if (isURL(value))
    return { u: value.toJSON() };
  if (isRegExp(value))
    return { r: { p: value.source, f: value.flags } };
  for (const [k, ctor] of Object.entries(typedArrayConstructors)) {
    if (isTypedArray(value, ctor))
      return { ta: { b: typedArrayToBase64(value), k } };
  }
  const id = visitorInfo.visited.get(value);
  if (id)
    return { ref: id };
  if (Array.isArray(value)) {
    const a = [];
    const id2 = ++visitorInfo.lastId;
    visitorInfo.visited.set(value, id2);
    for (let i = 0; i < value.length; ++i)
      a.push(serialize(value[i], handleSerializer, visitorInfo));
    return { a, id: id2 };
  }
  if (typeof value === "object") {
    const o = [];
    const id2 = ++visitorInfo.lastId;
    visitorInfo.visited.set(value, id2);
    for (const name of Object.keys(value)) {
      let item;
      try {
        item = value[name];
      } catch (e) {
        continue;
      }
      if (name === "toJSON" && typeof item === "function")
        o.push({ k: name, v: { o: [], id: 0 } });
      else
        o.push({ k: name, v: serialize(item, handleSerializer, visitorInfo) });
    }
    let jsonWrapper;
    try {
      if (o.length === 0 && value.toJSON && typeof value.toJSON === "function")
        jsonWrapper = { value: value.toJSON() };
    } catch (e) {
    }
    if (jsonWrapper)
      return innerSerialize(jsonWrapper.value, handleSerializer, visitorInfo);
    return { o, id: id2 };
  }
}
// packages/injected/src/bindingsController.ts
var BindingsController = class {
  // eslint-disable-next-line no-restricted-globals
  constructor(global, globalBindingName) {
    this._bindings = /* @__PURE__ */ new Map();
    this._global = global;
    this._globalBindingName = globalBindingName;
  }
  addBinding(bindingName, needsHandle) {
    const data = {
      callbacks: /* @__PURE__ */ new Map(),
      lastSeq: 0,
      handles: /* @__PURE__ */ new Map(),
      removed: false
    };
    this._bindings.set(bindingName, data);
    this._global[bindingName] = (...args) => {
      if (data.removed)
        throw new Error(`binding "${bindingName}" has been removed`);
      if (needsHandle && args.slice(1).some((arg) => arg !== void 0))
        throw new Error(`exposeBindingHandle supports a single argument, ${args.length} received`);
      const seq = ++data.lastSeq;
      const promise = new Promise((resolve, reject) => data.callbacks.set(seq, { resolve, reject }));
      let payload;
      if (needsHandle) {
        data.handles.set(seq, args[0]);
        payload = { name: bindingName, seq };
      } else {
        const serializedArgs = [];
        for (let i = 0; i < args.length; i++) {
          serializedArgs[i] = serializeAsCallArgument(args[i], (v) => {
            return { fallThrough: v };
          });
        }
        payload = { name: bindingName, seq, serializedArgs };
      }
      this._global[this._globalBindingName](JSON.stringify(payload));
      return promise;
    };
  }
  removeBinding(bindingName) {
    const data = this._bindings.get(bindingName);
    if (data)
      data.removed = true;
    this._bindings.delete(bindingName);
    delete this._global[bindingName];
  }
  takeBindingHandle(arg) {
    const handles = this._bindings.get(arg.name).handles;
    const handle = handles.get(arg.seq);
    handles.delete(arg.seq);
    return handle;
  }
  deliverBindingResult(arg) {
    const callbacks = this._bindings.get(arg.name).callbacks;
    if ("error" in arg)
      callbacks.get(arg.seq).reject(arg.error);
    else
      callbacks.get(arg.seq).resolve(arg.result);
    callbacks.delete(arg.seq);
  }
};

"""
