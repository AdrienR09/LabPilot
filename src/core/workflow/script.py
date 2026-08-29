"""Compile a WorkflowGraph into a readable Python script.

One-directional only (graph -> script): this makes a workflow's real
underlying WorkflowGraph legible and editable as a plain .py file (per
node, in topological order), reusing WorkflowGraph.topological_sort()
already used for execution ordering. There is deliberately no script ->
graph parser yet — turning arbitrary hand-edited Python back into
structured nodes reliably is a separate, harder problem; edits made
through the generated script's file view are saved as text only (see
PUT /api/workflows/{id}/script in server.py), not re-parsed into nodes.

The generated code mirrors what WorkflowEngine._execute_* actually does
today (see core/workflow/engine.py) rather than an idealized version, so
it stays an honest reflection of behavior — including nodes whose
execution is still simplified there (branch/loop/optimise).
"""

from __future__ import annotations

from typing import Any

from core.workflow.graph import WorkflowGraph

__all__ = ["graph_to_script"]


def _repr_value(value: Any) -> str:
    """Python source repr for a node field value."""
    return repr(value)


def _node_block(node: dict[str, Any]) -> list[str]:
    """Lines of code for one node, keyed by its `kind`."""
    kind = node.get("kind")
    node_id = node.get("id", "")
    name = node.get("name", node_id)
    var = f"result_{node_id.replace('-', '_')}"
    lines = [f"    # --- {name} ({kind}, id={node_id}) ---"]

    if kind == "acquire":
        lines += [
            f"    device = session.get({_repr_value(node['device'])})",
            "    await device.stage()",
            "    try:",
            f"        {var} = {{'data': await device.read(), 'device': {_repr_value(node['device'])}}}",
            "    finally:",
            "        await device.unstage()",
        ]
    elif kind == "analyse":
        lines += [
            "    # Sandboxed analysis code (see core/workflow/code_sandbox.py):",
            f"    {var} = execute_analysis_code(",
            f"        {_repr_value(node['code'])},",
            f"        inputs={_repr_value(node.get('inputs', []))},",
            "        params={},",
            f"        allowed_imports={_repr_value(node.get('allowed_imports', []))},",
            f"        timeout_s={node.get('timeout_s', 30.0)},",
            "    )",
        ]
    elif kind == "branch":
        lines += [
            f"    # if {node['condition']}: go to {node['true_branch']} else {node['false_branch']}",
            f"    {var} = eval({_repr_value(node['condition'])}, {{}}, node_results)",
        ]
    elif kind == "loop":
        lines += [
            f"    # Repeats its subgraph up to {node.get('max_iterations')} times",
            f"    # (subgraph execution is simplified in the current engine — see engine.py)",
            f"    {var} = {{'iterations': 0}}",
        ]
    elif kind == "optimise":
        lo, hi = node.get("bounds", (0.0, 1.0))
        lines += [
            f"    # Optimises {node['target_param']} on {node['target_device']} via "
            f"{node.get('method', 'bayesian')}, bounds=({lo}, {hi})",
            f"    device = session.get({_repr_value(node['target_device'])})",
            f"    {var} = {{'best_value': None, 'best_params': None}}  # see engine.py: not fully implemented yet",
        ]
    elif kind == "set":
        lines += [f"    device = session.get({_repr_value(node['device'])})"]
        if node.get("value") is not None:
            lines.append(f"    value = {_repr_value(node['value'])}")
        else:
            lines.append(
                f"    value = node_results[{_repr_value(node['from_node'])}]['result'][{_repr_value(node.get('from_key'))}]"
            )
        lines += [
            f"    await device.write({{{_repr_value(node['param'])}: value}})",
            f"    {var} = {{'device': {_repr_value(node['device'])}, 'value': value}}",
        ]
    elif kind == "wait":
        if node.get("duration_s") is not None:
            lines.append(f"    await asyncio.sleep({node['duration_s']})")
        else:
            lines += [
                f"    # Waits for {node['device']}.{node['target_param']} to reach "
                f"{node.get('target_value')} (tolerance {node.get('tolerance', 0.01)}, "
                f"timeout {node.get('timeout_s', 60.0)}s)",
                f"    device = session.get({_repr_value(node['device'])})",
            ]
        lines.append(f"    {var} = {{'waited': True}}")
    elif kind == "notify":
        lines.append(f"    {var} = await send_notification(node={_repr_value(node)})")
    else:
        lines.append(f"    {var} = None  # unknown node kind {kind!r}")

    lines.append(f"    node_results[{_repr_value(node_id)}] = {{'status': 'completed', 'result': {var}}}")
    lines.append("")
    return lines


def graph_to_script(graph: WorkflowGraph) -> str:
    """Render `graph` as a standalone, readable async Python script.

    The result is meant to be read and hand-edited as documentation/audit
    trail of what the workflow does — it is not re-parsed back into a
    WorkflowGraph (see module docstring).
    """
    lines: list[str] = [
        f'"""{graph.name}',
        "",
        f"Generated from WorkflowGraph {graph.id} — do not expect edits here to",
        "change the underlying graph; this is a readable rendering, not the",
        "source of truth. Edit the workflow through the graph tools/UI instead.",
        '"""',
        "",
        "import asyncio",
        "",
        "from core.session import Session",
        "from core.workflow.code_sandbox import execute_analysis_code",
        "",
    ]

    ui_blocks = graph.metadata.get("ui_blocks")
    if ui_blocks:
        # Optional per-instrument UI override, read back by
        # workflow_window.py via ast.literal_eval (never exec/import) — see
        # that module's docstring. A plain module-level constant so this
        # stays hand-editable in the script itself, the same as any other
        # part of a workflow's "primary" .py representation.
        lines += ["", f"UI_BLOCKS = {ui_blocks!r}", ""]

    lines += [
        "",
        "async def run(session: Session) -> dict:",
        "    node_results: dict = {}",
        "",
    ]

    try:
        order = graph.topological_sort()
    except ValueError:
        order = list(graph.nodes.keys())  # cyclic graph — fall back to insertion order

    for node_id in order:
        lines += _node_block(graph.nodes[node_id])

    lines.append("    return node_results")
    lines.append("")
    return "\n".join(lines)
