"""
main.py — Scout Gradio UI entry point.

Three-tab interface:
  Tab 1 — Input   : paste/fetch HTML, optional URL and hint
  Tab 2 — Output  : JSON config + BS4 snippet + download buttons
  Tab 3 — Reasoning Log : raw Claude response
"""

from __future__ import annotations

import json
import logging
import tempfile
import os
from typing import Tuple

import gradio as gr

from scout.parser import parse
from scout.classifier import classify
from scout.reasoner import reason, MODELS, DEFAULT_MODEL
import scout.reasoner as _reasoner_module
from scout.validator import validate
from scout.output import build_output
from scout.storage import init_db, save_run, list_runs, get_run, delete_run
from scout.fetcher import fetch_static, fetch_rendered

init_db()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_scout(
    html: str,
    url: str,
    hint: str,
    model_key: str = DEFAULT_MODEL,
    ollama_model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434/v1",
    use_js_render: bool = False,
    wait_until: str = "networkidle",
) -> Tuple[dict | None, str, str, str]:
    """
    Run the full Scout pipeline.

    Returns
    -------
    config_dict  : dict | None  — for gr.JSON display
    snippet      : str          — Python BS4 code
    reasoning    : str          — raw Claude response
    errors       : str          — accumulated error messages (empty = all good)
    """
    errors: list[str] = []
    html_source = html or ""
    source_url: str | None = url.strip() if url and url.strip() else None

    # ------------------------------------------------------------------
    # Optional: fetch HTML from URL
    # ------------------------------------------------------------------
    if source_url:
        try:
            if use_js_render:
                html_source = fetch_rendered(source_url, wait_until=wait_until)
            else:
                html_source = fetch_static(source_url)
        except Exception as exc:
            errors.append(f"[URL fetch] {exc}")
            # Fall through with whatever HTML was pasted, if any

    if not html_source.strip():
        errors.append("[Input] No HTML provided — paste HTML or supply a valid URL.")
        return None, "", "", "\n".join(errors)

    # ------------------------------------------------------------------
    # Stage 1 — Parse
    # ------------------------------------------------------------------
    blocks: list[dict] = []
    try:
        blocks = parse(html_source)
        logger.info("Stage 1 complete: %d blocks extracted.", len(blocks))
    except Exception as exc:
        errors.append(f"[Stage 1 — Parser] {exc}")
        logger.exception("Parser failed")

    if not blocks:
        errors.append("[Stage 1] No blocks extracted from the HTML.")
        return None, "", "", "\n".join(errors)

    # ------------------------------------------------------------------
    # Stage 2 & 3 — Classify
    # ------------------------------------------------------------------
    classified: list[dict] = []
    try:
        classified = classify(blocks)
        logger.info("Stage 2-3 complete: %d blocks after filtering.", len(classified))
    except Exception as exc:
        errors.append(f"[Stage 2-3 — Classifier] {exc}")
        logger.exception("Classifier failed")
        classified = blocks  # fall back to unclassified blocks

    if not classified:
        errors.append("[Stage 2-3] All blocks were filtered out by the classifier.")
        return None, "", "", "\n".join(errors)

    # ------------------------------------------------------------------
    # Stage 4 — Reason (Claude)
    # ------------------------------------------------------------------
    selectors: list[dict] = []
    try:
        user_hint: str | None = hint.strip() if hint and hint.strip() else None
        selectors = reason(
            classified,
            user_hint,
            model_key=model_key,
            ollama_model=ollama_model,
            ollama_url=ollama_url,
        )
        logger.info("Stage 4 complete: %d selectors generated.", len(selectors))
    except Exception as exc:
        errors.append(f"[Stage 4 — Reasoner] {exc}")
        logger.exception("Reasoner failed")

    raw_claude = _reasoner_module.last_raw_response

    if not selectors:
        errors.append("[Stage 4] Model returned no selectors.")
        return None, "", raw_claude, "\n".join(errors)

    # ------------------------------------------------------------------
    # Stage 5 — Validate
    # ------------------------------------------------------------------
    validated: list[dict] = []
    try:
        validated = validate(selectors, html_source)
        valid_count = sum(1 for s in validated if s.get("valid"))
        logger.info(
            "Stage 5 complete: %d/%d selectors valid.", valid_count, len(validated)
        )
    except Exception as exc:
        errors.append(f"[Stage 5 — Validator] {exc}")
        logger.exception("Validator failed")
        validated = selectors  # fall back without validation flags

    # ------------------------------------------------------------------
    # Stage 6 — Build output
    # ------------------------------------------------------------------
    config_json_str = ""
    snippet = ""
    try:
        config_json_str, snippet = build_output(validated, source_url)
        logger.info("Stage 6 complete: output generated.")
    except Exception as exc:
        errors.append(f"[Stage 6 — Output] {exc}")
        logger.exception("Output builder failed")

    # Parse config JSON back to dict for gr.JSON widget
    config_dict: dict | None = None
    if config_json_str:
        try:
            config_dict = json.loads(config_json_str)
        except json.JSONDecodeError:
            config_dict = {"raw": config_json_str}

    # Persist the run (even partial runs — errors are stored too)
    errors_str = "\n".join(errors)
    try:
        save_run(source_url, model_key, config_json_str, snippet, raw_claude, errors_str)
    except Exception as exc:
        logger.error("Failed to save run to DB: %s", exc)

    return config_dict, snippet, raw_claude, errors_str


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_config(config_dict: dict | None) -> str | None:
    """Write config_dict to a temp file and return its path for gr.File."""
    if not config_dict:
        return None
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(config_dict, fh, indent=2, ensure_ascii=False)
        return fh.name


def download_snippet(snippet: str) -> str | None:
    """Write snippet to a temp file and return its path for gr.File."""
    if not snippet:
        return None
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(snippet)
        return fh.name


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Scout — Scraper Selector Generator") as demo:
    gr.Markdown("# Scout\n_Automated CSS selector & XPath generator for web scraping_")

    # Shared state for download buttons
    _config_state = gr.State(None)
    _snippet_state = gr.State("")

    with gr.Tabs():

        # ------------------------------------------------------------------
        # Tab 1 — Input
        # ------------------------------------------------------------------
        with gr.Tab("Input"):
            html_input = gr.Textbox(
                label="HTML",
                lines=20,
                placeholder="Paste raw HTML here…",
            )
            url_input = gr.Textbox(
                label="URL (optional)",
                placeholder="https://…",
            )
            hint_input = gr.Textbox(
                label="Hint (optional)",
                placeholder="e.g. focus on ecommerce fields, or: I need the author and publish date",
            )
            model_dropdown = gr.Dropdown(
                label="Model",
                choices=list(MODELS.keys()),
                value=DEFAULT_MODEL,
            )
            with gr.Group(visible=False) as ollama_group:
                ollama_model_input = gr.Textbox(
                    label="Ollama model name",
                    placeholder="e.g. llama3.2, mistral, qwen2.5",
                    value="llama3.2",
                )
                ollama_url_input = gr.Textbox(
                    label="Ollama base URL",
                    value="http://localhost:11434/v1",
                )
            with gr.Row():
                js_render_checkbox = gr.Checkbox(
                    label="Use JS rendering (Playwright)",
                    value=False,
                    info="Enable for React/Vue/Angular/Next.js CSR pages. Requires: playwright install chromium",
                )
                wait_until_dropdown = gr.Dropdown(
                    label="Wait until",
                    choices=["networkidle", "load", "domcontentloaded"],
                    value="networkidle",
                    visible=False,
                    info="networkidle: best for SPAs | load: middle ground | domcontentloaded: fastest",
                )
            run_button = gr.Button("Run Scout", variant="primary")

        # ------------------------------------------------------------------
        # Tab 2 — Output
        # ------------------------------------------------------------------
        with gr.Tab("Output"):
            config_output = gr.JSON(label="Scraper Config")
            snippet_output = gr.Code(label="BS4 Snippet", language="python")
            errors_output = gr.Textbox(label="Errors", lines=5, interactive=False)

            with gr.Row():
                download_config_btn = gr.Button("Download Config JSON")
                download_snippet_btn = gr.Button("Download BS4 Snippet")

            config_file = gr.File(label="Config JSON download", visible=False)
            snippet_file = gr.File(label="Snippet download", visible=False)

        # ------------------------------------------------------------------
        # Tab 3 — Reasoning Log
        # ------------------------------------------------------------------
        with gr.Tab("Reasoning Log"):
            reasoning_output = gr.Textbox(
                label="Model Response (raw)",
                lines=20,
                interactive=False,
            )

        # ------------------------------------------------------------------
        # Tab 4 — History
        # ------------------------------------------------------------------
        with gr.Tab("History"):
            history_table = gr.Dataframe(
                label="Past runs",
                headers=["ID", "Generated at", "URL", "Model", "Errors"],
                datatype=["number", "str", "str", "str", "str"],
                interactive=False,
                wrap=True,
            )
            with gr.Row():
                load_id_input = gr.Number(label="Run ID to load", precision=0, minimum=1)
                load_run_btn = gr.Button("Load run")
                refresh_btn = gr.Button("Refresh list")
                delete_id_input = gr.Number(label="Run ID to delete", precision=0, minimum=1)
                delete_run_btn = gr.Button("Delete run")

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------
    def _get_history_rows():
        runs = list_runs()
        return [[r["id"], r["generated_at"], r["source_url"] or "", r["model_key"] or "", r["errors"] or ""] for r in runs]

    def _load_run(run_id):
        if not run_id:
            return None, "", "", "", None, ""
        row = get_run(int(run_id))
        if not row:
            return None, "", f"Run {int(run_id)} not found.", "", None, ""
        config_dict = None
        if row["config_json"]:
            try:
                config_dict = json.loads(row["config_json"])
            except json.JSONDecodeError:
                config_dict = {"raw": row["config_json"]}
        snippet = row["snippet"] or ""
        return config_dict, snippet, row["reasoning"] or "", row["errors"] or "", config_dict, snippet

    def _delete_run(run_id):
        if not run_id:
            return _get_history_rows()
        delete_run(int(run_id))
        return _get_history_rows()

    # Populate history on app load
    demo.load(fn=_get_history_rows, outputs=[history_table])

    # ------------------------------------------------------------------
    # Show/hide Ollama fields based on model selection
    # ------------------------------------------------------------------
    def _toggle_ollama(model_key: str):
        return gr.update(visible=(model_key == "Ollama (local)"))

    model_dropdown.change(
        fn=_toggle_ollama,
        inputs=[model_dropdown],
        outputs=[ollama_group],
    )

    def _toggle_wait_until(use_js: bool):
        return gr.update(visible=use_js)

    js_render_checkbox.change(
        fn=_toggle_wait_until,
        inputs=[js_render_checkbox],
        outputs=[wait_until_dropdown],
    )

    # ------------------------------------------------------------------
    # Wire up Run Scout button
    # ------------------------------------------------------------------
    def _run(html: str, url: str, hint: str, model_key: str, ollama_model: str, ollama_url: str, use_js: bool, wait: str):
        config_dict, snippet, reasoning, errors = run_scout(
            html, url, hint, model_key, ollama_model, ollama_url, use_js, wait
        )
        return config_dict, snippet, reasoning, errors, config_dict, snippet

    run_button.click(
        fn=_run,
        inputs=[html_input, url_input, hint_input, model_dropdown, ollama_model_input, ollama_url_input, js_render_checkbox, wait_until_dropdown],
        outputs=[
            config_output,
            snippet_output,
            reasoning_output,
            errors_output,
            _config_state,
            _snippet_state,
        ],
    ).then(fn=_get_history_rows, outputs=[history_table])

    refresh_btn.click(fn=_get_history_rows, outputs=[history_table])

    load_run_btn.click(
        fn=_load_run,
        inputs=[load_id_input],
        outputs=[config_output, snippet_output, reasoning_output, errors_output, _config_state, _snippet_state],
    )

    delete_run_btn.click(
        fn=_delete_run,
        inputs=[delete_id_input],
        outputs=[history_table],
    )

    # Optionally populate HTML box when URL is entered (on blur / change)
    def _fetch_html_preview(url: str, use_js: bool, wait: str) -> str:
        """Fetch HTML from URL and return it so the HTML box is pre-populated."""
        if not url or not url.strip():
            return ""
        try:
            if use_js:
                return fetch_rendered(url.strip(), wait_until=wait)
            return fetch_static(url.strip())
        except Exception as exc:
            return f"<!-- Error fetching URL: {exc} -->"

    url_input.blur(
        fn=_fetch_html_preview,
        inputs=[url_input, js_render_checkbox, wait_until_dropdown],
        outputs=[html_input],
    )

    # ------------------------------------------------------------------
    # Download buttons
    # ------------------------------------------------------------------
    download_config_btn.click(
        fn=download_config,
        inputs=[_config_state],
        outputs=[config_file],
    ).then(
        fn=lambda: gr.update(visible=True),
        outputs=[config_file],
    )

    download_snippet_btn.click(
        fn=download_snippet,
        inputs=[_snippet_state],
        outputs=[snippet_file],
    ).then(
        fn=lambda: gr.update(visible=True),
        outputs=[snippet_file],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo.launch()
