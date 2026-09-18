"""Tests for the bundled study widget's contract (spec 09).

The widget is a browser document with no build step and no JavaScript test
dependency (spec 02 fixes the dev extra), so these tests lock the parts of
its source that the MCP Apps contract and the specs make normative.
"""

from __future__ import annotations

import re

import pytest

from learning_tool.server import load_widget_html

PROTOCOL_VERSION = "2026-01-26"


@pytest.fixture(scope="module")
def widget() -> str:
    """Return the widget HTML as served by the resource."""
    return load_widget_html()


def test_is_a_single_self_contained_document(widget: str) -> None:
    """All CSS and JavaScript are inline; nothing is fetched."""
    assert "<style>" in widget and "<script>" in widget
    assert "http://" not in widget and "https://" not in widget
    assert not re.search(r"<link[^>]+href=", widget)
    assert not re.search(r"<script[^>]+src=", widget)


def test_initialize_handshake_declares_the_protocol_and_capabilities(
    widget: str,
) -> None:
    """The widget opens with ui/initialize at the pinned protocol version."""
    assert f'"{PROTOCOL_VERSION}"' in widget
    assert 'request("ui/initialize"' in widget
    assert 'appCapabilities: { availableDisplayModes: ["inline"] }' in widget
    assert "appInfo: APP_INFO" in widget
    assert "clientInfo" not in widget, "the extension takes appInfo, not clientInfo"
    assert "capabilities: {}" not in widget


def test_initialized_notification_follows_the_handshake(widget: str) -> None:
    """The initialized notification is sent from the success path only."""
    success_path = widget.split('request("ui/initialize"', 1)[1]
    ordered = success_path.split('notify("ui/notifications/initialized"', 1)
    assert len(ordered) == 2
    assert "applyHostContext(result && result.hostContext);" in ordered[0]
    assert "observeSize();" in ordered[1]


def test_nothing_is_sent_before_the_handshake_completes(widget: str) -> None:
    """ui/initialize must be the first message on the wire.

    Traffic before initialization is a protocol violation, and a host may
    ignore everything that follows it.
    """
    assert "var ready = false;" in widget
    assert "function notifySize() {\n    if (!ready) {\n      return;\n    }" in widget
    assert "ready = true;" in widget
    assert widget.index("ready = true;") > widget.index(
        'notify("ui/notifications/initialized"'
    )


def test_initialize_is_retried_until_the_host_answers(widget: str) -> None:
    """The spec fixes no ordering between the host listener and app load."""
    assert "var MAX_INITIALIZE_ATTEMPTS = 12;" in widget
    assert "var INITIALIZE_RETRY_MS = 400;" in widget
    assert "window.setTimeout(initialize, INITIALIZE_RETRY_MS);" in widget
    assert "initializeAttempts += 1;" in widget
    assert (
        "if (initialized) {\n        return;\n      }\n      initialized = true;"
        in widget
    )


def test_host_silence_is_reported_rather_than_waited_on_forever(widget: str) -> None:
    """A host that never answers produces a message, not an endless wait."""
    assert '"The host did not answer the initialize handshake after " +' in widget
    assert (
        "if (initialized) {\n        return;\n      }\n      state.status =" in widget
    )


def test_initialization_failure_is_rendered_in_the_status_area(widget: str) -> None:
    """A failed handshake shows a message instead of dying silently."""
    assert 'state.status = "Could not connect to the host: " + error.message;' in widget
    assert "initializeAttempts < MAX_INITIALIZE_ATTEMPTS" in widget


def test_incoming_messages_require_json_rpc_two(widget: str) -> None:
    """Anything not declaring JSON-RPC 2.0 is ignored."""
    assert 'if (!message || message.jsonrpc !== "2.0") {' in widget
    assert 'post({ jsonrpc: "2.0", id: id, method: method, params: params });' in widget


def test_pending_requests_resolve_or_reject_by_id(widget: str) -> None:
    """Responses are matched to their request and errors reject."""
    assert "pending.set(id, { resolve: resolve, reject: reject });" in widget
    assert "pending.delete(message.id);" in widget
    assert "entry.reject(new Error(message.error.message" in widget


def test_all_linked_tool_notifications_are_handled(widget: str) -> None:
    """Input, result, cancellation, and host-context changes each dispatch."""
    for method in (
        "ui/notifications/tool-input",
        "ui/notifications/tool-result",
        "ui/notifications/tool-cancelled",
        "ui/notifications/host-context-changed",
    ):
        assert f'"{method}":' in widget


def test_tool_results_prefer_structured_content_then_parsed_text(widget: str) -> None:
    """Payload extraction follows the documented precedence."""
    extractor = widget.split("function extractPayload(result) {", 1)[1]
    body = extractor.split("function loadQueue", 1)[0]
    assert body.index("result.structuredContent") < body.index(
        "JSON.parse(parts[i].text)"
    )


def test_error_results_and_malformed_payloads_show_status_text(widget: str) -> None:
    """A bad result never kills the widget silently."""
    handler = widget.split("function handleToolResult(result) {", 1)[1]
    body = handler.split("function callTool", 1)[0]
    assert "if (result && result.isError) {" in body
    assert "state.status = errorText(result);" in body
    assert 'state.status = "Could not read the study items: " + error.message;' in body
    assert 'throw new Error("The due-items payload could not be read.");' in widget


def test_host_teardown_request_is_answered(widget: str) -> None:
    """The host must get a response before it tears the resource down."""
    assert '"ui/notifications/request-teardown": function () {' in widget
    assert '"ui/resource-teardown": function () {' in widget
    assert (
        'post({ jsonrpc: "2.0", id: message.id, result: responder(message.params || {}) });'
        in widget
    )


def test_cancellation_shows_a_cancelled_status(widget: str) -> None:
    """A cancelled linked call is reported, not left hanging."""
    assert 'state.status = "The study request was cancelled.";' in widget


def test_only_the_two_allowed_tools_are_called(widget: str) -> None:
    """The widget never reaches the destructive tools."""
    called = set(re.findall(r'callTool\(\s*"([a-z_]+)"', widget))

    assert called == {"submit_response", "get_due_items"}
    assert "delete_document" not in widget
    assert "reset_progress" not in widget


def test_size_changes_are_notified_and_deduplicated(widget: str) -> None:
    """Unchanged dimensions send nothing; renders and resizes trigger a check."""
    assert "if (width === lastSize.width && height === lastSize.height) {" in widget
    assert (
        'notify("ui/notifications/size-changed", { width: width, height: height });'
        in widget
    )
    assert "new ResizeObserver(notifySize).observe(document.body);" in widget
    assert widget.count("notifySize();") >= 3
    assert "document.body.scrollWidth" in widget
    assert "document.body.scrollHeight" in widget


def test_host_style_variables_and_theme_are_applied_to_the_root(widget: str) -> None:
    """Host theming lands on the document root as custom properties."""
    assert "var styles = context.styles || {};" in widget
    assert "var variables = styles.variables || context.styleVariables;" in widget
    assert (
        "document.documentElement.style.setProperty(name, String(variables[key]));"
        in widget
    )
    assert 'var name = key.indexOf("--") === 0 ? key : "--" + key;' in widget
    assert "document.documentElement.style.colorScheme = context.theme;" in widget


def test_stylesheet_defines_light_and_dark_fallbacks_for_every_variable(
    widget: str,
) -> None:
    """The widget renders correctly before or without host theming."""
    style = widget.split("<style>", 1)[1].split("</style>", 1)[0]
    light = style.split(":root {", 1)[1].split("}", 1)[0]
    dark = style.split(':root:not([data-theme="light"]) {', 1)[1].split("}", 1)[0]

    declared = set(re.findall(r"(--[a-z-]+):", light))
    themed = set(re.findall(r"(--[a-z-]+):", dark))
    used = set(re.findall(r"var\((--[a-z-]+)\)", style))

    assert used <= declared
    assert {
        "--background",
        "--background-secondary",
        "--text-primary",
        "--text-secondary",
        "--border",
        "--success-background",
        "--success-text",
        "--danger-background",
        "--danger-text",
        "--font-family",
        "--radius",
    } <= declared
    assert themed and themed <= declared


def test_an_explicit_host_theme_overrides_the_operating_system(widget: str) -> None:
    """A host theme must win in both directions, or colors mix across palettes.

    Without this, a dark-mode OS keeps its near-white text while the host
    supplies a white background, and controls become invisible.
    """
    style = widget.split("<style>", 1)[1].split("</style>", 1)[0]
    dark_media = style.split(':root:not([data-theme="light"]) {', 1)[1].split("}", 1)[0]
    dark_explicit = style.split(':root[data-theme="dark"] {', 1)[1].split("}", 1)[0]

    assert set(re.findall(r"(--[a-z-]+):", dark_media)) == set(
        re.findall(r"(--[a-z-]+):", dark_explicit)
    )
    assert "--text-primary" in dark_explicit
    assert "--background" in dark_explicit


def test_every_color_is_defined_outside_a_media_or_theme_block(widget: str) -> None:
    """No variable may get its only definition inside a conditional block."""
    style = widget.split("<style>", 1)[1].split("</style>", 1)[0]
    base = set(
        re.findall(r"(--[a-z-]+):", style.split(":root {", 1)[1].split("}", 1)[0])
    )

    for block_start in (
        ':root:not([data-theme="light"]) {',
        ':root[data-theme="dark"] {',
    ):
        block = style.split(block_start, 1)[1].split("}", 1)[0]
        assert set(re.findall(r"(--[a-z-]+):", block)) <= base


def test_flashcards_reveal_before_grading(widget: str) -> None:
    """The back and the grading buttons appear only once revealed."""
    card = widget.split("function flashcardCard(item) {", 1)[1].split(
        "function quizCard", 1
    )[0]

    assert "if (!state.revealed) {" in card
    assert 'actionButton("Show answer"' in card
    assert 'actionButton("I got it", function () {\n      submit("correct");' in card
    assert (
        'actionButton("I missed it", function () {\n      submit("incorrect");' in card
    )
    assert "card.appendChild(confidencePicker());" in card


def test_quiz_rendering_covers_both_question_types(widget: str) -> None:
    """Options submit their exact text; short answers submit typed text."""
    card = widget.split("function quizCard(item) {", 1)[1].split(
        "function caughtUpCard", 1
    )[0]

    assert 'if (item.question_type === "multiple_choice") {' in card
    assert "submit(option);" in card
    assert 'if (event.key === "Enter") {' in card
    assert card.count("if (input.value.trim()) {") == 2


def test_confidence_picker_offers_an_unset_placeholder(widget: str) -> None:
    """An unset picker sends no confidence argument at all."""
    assert 'var CONFIDENCE_LEVELS = ["guessed", "unsure", "confident"];' in widget
    assert 'placeholder.value = "";' in widget
    assert (
        "if (state.confidence) {\n      args.confidence = state.confidence;\n    }"
        in widget
    )


def test_submission_is_guarded_disabled_and_advances_the_queue(widget: str) -> None:
    """In-flight calls block further submissions and disable the controls."""
    submit = widget.split("function submit(answer) {", 1)[1].split(
        "function refresh", 1
    )[0]

    assert "if (state.busy || !item || state.documentId === null) {" in submit
    assert "button.disabled = state.busy;" in widget
    assert 'state.flash = { kind: "ok", text: "Correct!" };' in submit
    assert 'text: "Incorrect \u2014 answer: " + item.answer' in submit
    assert 'state.flash = { kind: "bad", text: "Marked for review." };' in submit
    assert "state.index += 1;" in submit
    assert "state.revealed = false;" in submit


def test_a_failed_submission_flashes_and_stays_on_the_item(widget: str) -> None:
    """Errors do not advance the queue."""
    failure = widget.split("function submit(answer) {", 1)[1].split(
        "}, function (error) {", 1
    )[1]
    handler = failure.split("});", 1)[0]

    assert 'state.flash = { kind: "bad", text: error.message };' in handler
    assert "state.index" not in handler


def test_exhausted_queue_offers_a_refresh(widget: str) -> None:
    """The all-caught-up card re-calls get_due_items."""
    card = widget.split("function caughtUpCard() {", 1)[1].split(
        "function progressFooter", 1
    )[0]

    assert '"All caught up."' in card
    assert 'actionButton("Refresh due items", refresh)' in card
    assert 'callTool("get_due_items", { document_id: state.documentId })' in widget


def test_progress_footer_lists_the_four_buckets(widget: str) -> None:
    """Whenever progress exists, the four counts are shown."""
    footer = widget.split("function progressFooter() {", 1)[1].split(
        "function render", 1
    )[0]

    assert '["mastered", state.progress.mastered]' in footer
    assert '["in progress", state.progress.in_progress]' in footer
    assert '["to review", state.progress.to_review]' in footer
    assert '["remaining", state.progress.remaining]' in footer
    assert "if (state.progress) {" in widget


def test_the_heading_and_queue_position_come_from_state(widget: str) -> None:
    """Rendering is a full redraw of title, position, and item."""
    render = widget.split("function render() {", 1)[1]

    assert 'app.textContent = "";' in render
    assert 'element("h1", null, state.title || "Study session")' in render
    assert (
        '"Item " + (state.index + 1) + " of " + state.queue.length + " due"' in render
    )
    assert '"No items due"' in render


def test_status_progression_before_data_arrives(widget: str) -> None:
    """The status line walks from connecting to waiting for items."""
    assert 'status: "Connecting to host\u2026"' in widget
    assert 'state.status = "Waiting for due items\u2026";' in widget
    assert "if (state.status) {" in widget
