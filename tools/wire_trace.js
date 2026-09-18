/**
 * Print what the study widget puts on the wire, without a browser.
 *
 * A DOM stub just complete enough to run the widget's bridge, so the
 * handshake params and message ordering can be inspected directly. Catches
 * the class of defect that source-text assertions cannot: wrong field names,
 * wrong order, missing notifications.
 *
 * Usage:  node tools/wire_trace.js
 */
const fs = require("fs");
const path = require("path");

const widgetPath = path.join(__dirname, "..", "src", "learning_tool", "ui", "study.html");
const script = /<script>([\s\S]*?)<\/script>/.exec(fs.readFileSync(widgetPath, "utf8"))[1];

const sent = [];
let messageListener = null;

function makeEl() {
  return {
    className: "", textContent: "", disabled: false, value: "", type: "", placeholder: "",
    children: [], style: { setProperty() {} },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, focus() {}, setAttribute() {},
  };
}

const root = makeEl();
root.style = { setProperty: (k, v) => sent.push({ cssVariable: k, value: v }), colorScheme: "" };

global.window = {
  parent: { postMessage: (m) => sent.push(m) },
  addEventListener: (type, fn) => { if (type === "message") messageListener = fn; },
  setTimeout: (fn, ms) => setTimeout(fn, ms),
};
global.document = {
  body: { scrollWidth: 400, scrollHeight: 300 },
  documentElement: root,
  getElementById: () => makeEl(),
  createElement: makeEl,
  createTextNode: (t) => ({ text: t }),
};
global.ResizeObserver = function () { this.observe = () => {}; };

eval(script);

const deliver = (m) => messageListener({ data: m });
const show = (label) => {
  console.log(`\n--- ${label} ---`);
  sent.forEach((m) => console.log(JSON.stringify(m)));
};

show("on load");

const first = sent[0];
let failures = 0;
const check = (label, ok) => { console.log(`  ${ok ? "PASS" : "FAIL"}  ${label}`); if (!ok) failures++; };

console.log("\nchecks:");
check("first message is ui/initialize (nothing precedes the handshake)",
  first && first.method === "ui/initialize");
check("params carry appInfo", !!(first && first.params && first.params.appInfo));
check("params carry appCapabilities.availableDisplayModes",
  !!(first && first.params.appCapabilities && first.params.appCapabilities.availableDisplayModes));
check("params omit base-MCP clientInfo/capabilities",
  !!first && !first.params.clientInfo && !first.params.capabilities);

sent.length = 0;
deliver({ jsonrpc: "2.0", id: first.id, result: {
  protocolVersion: "2026-01-26", hostCapabilities: {}, hostInfo: { name: "stub", version: "1" },
  hostContext: { theme: "dark", styles: { variables: { "--background": "#111" } } } } });

setTimeout(() => {
  show("after the initialize result");
  check("sends ui/notifications/initialized (clears the host's loading state)",
    sent.some((m) => m.method === "ui/notifications/initialized"));
  check("applies host style variables",
    sent.some((m) => m.cssVariable === "--background"));
  check("size notification only after the handshake",
    sent.findIndex((m) => m.method === "ui/notifications/size-changed") >
    sent.findIndex((m) => m.method === "ui/notifications/initialized"));
  console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
  process.exit(failures ? 1 : 0);
}, 60);
