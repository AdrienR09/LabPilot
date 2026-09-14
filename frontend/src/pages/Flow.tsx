import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import ReactFlow, {
  Node,
  Edge,
  EdgeProps,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  getBezierPath,
  EdgeLabelRenderer,
  Connection,
  ConnectionMode,
  Panel,
  MarkerType,
  Handle,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Cpu, Microscope, Zap, RefreshCw, Camera, Calculator, GitBranch, RotateCw, Target, Sliders, Clock, Bell, Link2, X, Eye, EyeOff } from 'lucide-react';
import { useLabPilotStore } from '@/store';
import {
  getWorkflowGraph,
  WorkflowGraphDetail,
  getWorkflowBindings,
  setWorkflowBinding,
  WorkflowBindingRole,
} from '@/api';

const getIconForKind = (kind: string) => {
  switch (kind) {
    case 'detector':
      return <Microscope className="h-5 w-5" />;
    case 'motor':
      return <Zap className="h-5 w-5" />;
    default:
      return <Cpu className="h-5 w-5" />;
  }
};

// grey = disconnected, green = connected+idle, amber (pulsing) = busy,
// red = error — driven by the same DashboardInstrument.status the
// Devices page already reads, just not previously surfaced here.
const INSTRUMENT_STATUS_STYLE: Record<string, { dot: string; label: string }> = {
  disconnected: { dot: 'bg-gray-400', label: 'Disconnected' },
  idle: { dot: 'bg-green-500', label: 'Connected' },
  busy: { dot: 'bg-amber-500 animate-pulse', label: 'Busy' },
  error: { dot: 'bg-red-500', label: 'Error' },
};

const InstrumentNode = ({ data }: { data: any }) => {
  const showInstrumentSettings = useLabPilotStore((s) => s.showInstrumentSettings);
  const navigate = useNavigate();
  const statusKey = !data.connected ? 'disconnected' : (data.status || 'idle');
  const status = INSTRUMENT_STATUS_STYLE[statusKey] || INSTRUMENT_STATUS_STYLE.idle;

  return (
    <div
      onDoubleClick={() => {
        showInstrumentSettings(data.id);
        navigate('/devices');
      }}
      title="Double-click to open in Instruments"
      className="px-4 py-3 shadow-lg rounded-lg bg-white dark:bg-gray-800 border-2 border-blue-500 dark:border-blue-400 min-w-[180px] cursor-pointer"
    >
      <div className="flex items-center space-x-2">
        <div className="p-1.5 rounded bg-blue-100 dark:bg-blue-900/30">
          {getIconForKind(data.kind)}
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {data.label}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {data.dimensionality} {data.kind}
          </div>
        </div>
      </div>
      <div className="mt-2 flex items-center" title={data.error || undefined}>
        <div className={`h-2 w-2 rounded-full mr-2 ${status.dot}`}></div>
        <span className="text-xs text-gray-600 dark:text-gray-400">{status.label}</span>
      </div>
      {/* Drag from here to a workflow's port node to bind this instrument
          to that role — the only connectable handle this node has. */}
      <Handle type="source" position={Position.Right} id="instrument-out" />
    </div>
  );
};

// Why this instrument may not fill this role, or null if it may — the
// exact mirror of `instrument_roles.role_refusal` on the backend, which
// re-checks it in PUT .../bindings/{role}. Kept as one function so the
// port's "needs ..." label, the drag validation and the server can never
// drift apart.
//
// Three rules, in the order the backend applies them:
//
//  1. A declared `capability` decides on its own. It is the only exactly
//     knowable requirement — a device either declares `gated_counter` or
//     `configure_gates` does not exist — and a role that names one names
//     no kind, because the same contract is spelled `counter`,
//     `detector` and `generic` by different adapters for the same job.
//  2. A `generic` instrument satisfies any kind. An NI card is an
//     actuator, a detector and a counter depending only on which
//     terminal a workflow asks for, so refusing it is the taxonomy
//     asserting what it cannot know. This rule was missing here, which
//     is why a generic card the backend would happily bind could not be
//     dragged onto any port at all.
//  3. A role with no declared dimensionality (e.g. omniscan.py's
//     "detector") accepts any, rather than comparing a real
//     dimensionality against undefined and refusing everything.
function portRefusal(instrument: any, port: any): string | null {
  if (port.capability && !(instrument.capabilities || []).includes(port.capability)) {
    return `needs a ${port.capability} instrument`;
  }
  if (instrument.kind === 'generic') return null;
  if (port.kind && instrument.kind !== port.kind) {
    return `needs kind ${port.kind}`;
  }
  if (port.dimensionality && instrument.dimensionality !== port.dimensionality) {
    return `needs ${port.dimensionality}`;
  }
  return null;
}

/** What a port asks for, in the words of whichever requirement it
 * declares — a capability where it names one, the kind/dimensionality
 * pair otherwise, and "any instrument" where it constrains nothing. */
function portRequirement(port: any): string {
  if (port.capability) return `a ${port.capability}`;
  const parts = [port.dimensionality, port.kind].filter(Boolean);
  return parts.length ? parts.join(' ') : 'any instrument';
}

// One empty/filled slot inside a workflow's binding box — represents a
// `REQUIRED_INSTRUMENTS` role from a role-based template
// (core/workflow_templates/). Connecting an instrument node to this node's
// target handle binds that role via PUT /api/workflows/{id}/bindings/{role}.
const PortNode = ({ data }: { data: any }) => {
  const bound = Boolean(data.instrumentId);
  return (
    <div
      className={`px-3 py-2 rounded-md min-w-[200px] border-2 ${
        bound
          ? 'border-green-500 dark:border-green-400 bg-green-50 dark:bg-green-900/20'
          : 'border-dashed border-gray-400 dark:border-gray-500 bg-gray-50 dark:bg-gray-800'
      }`}
    >
      <Handle type="target" position={Position.Left} id="port-in" />
      <div className="flex items-center space-x-2">
        <div className="p-1 rounded bg-white dark:bg-gray-700">{getIconForKind(data.kind)}</div>
        <div>
          <div className="text-xs font-semibold text-gray-900 dark:text-white">
            {data.role}
            {data.optional && (
              <span className="ml-1 text-[9px] font-normal text-gray-400 dark:text-gray-500">(optional)</span>
            )}
          </div>
          <div className="text-[10px] text-gray-500 dark:text-gray-400">
            needs {portRequirement(data)}
          </div>
        </div>
      </div>
      <div className="mt-1 flex items-center text-xs">
        {bound ? (
          <>
            <Link2 className="h-3 w-3 text-green-600 dark:text-green-400 mr-1" />
            <span className="text-green-700 dark:text-green-400">{data.instrumentName}</span>
          </>
        ) : (
          <span className="text-gray-400 dark:text-gray-500 italic">Unbound</span>
        )}
      </div>
    </div>
  );
};

// A binding edge (instrument -> role port) with an always-visible "x"
// button at its midpoint to unbind it — pressing Delete/Backspace on a
// selected edge already worked (onEdgesDelete below), but that's not
// discoverable at all; this makes "there's a way to remove this link"
// obvious without needing to know a keyboard shortcut exists.
const BindingEdge = ({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, data,
}: EdgeProps) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition,
  });
  return (
    <>
      <path id={id} className="react-flow__edge-path" d={edgePath} style={style} markerEnd={markerEnd as string} />
      <EdgeLabelRenderer>
        <button
          onClick={(event) => {
            event.stopPropagation();
            data?.onDelete?.();
          }}
          title="Unbind"
          className="nodrag nopan absolute flex items-center justify-center h-5 w-5 rounded-full bg-white dark:bg-gray-700 border border-red-300 dark:border-red-500 text-red-600 dark:text-red-400 shadow hover:bg-red-50 dark:hover:bg-red-900/40"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
        >
          <X className="h-3 w-3" />
        </button>
      </EdgeLabelRenderer>
    </>
  );
};

// The workflow "box" itself — a group node with each role's PortNode as a
// React Flow child (parentNode + extent: 'parent'), matching "a confocal
// scanner box... with two empty nodes inside" directly. Purely a visual
// container; it has no handles of its own. The status pill reflects the
// most recent execution_logs row for this workflow (see GET
// /api/workflows) — refreshed on load/manual refresh, not live (the native
// desktop window is where a run updates live, see workflow_window.py).
const STATUS_PILL_STYLE: Record<string, string> = {
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  cancelled: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
};

const WorkflowBoxNode = ({ data }: { data: any }) => {
  const navigate = useNavigate();
  const statusKey = data.running ? 'running' : data.lastStatus || 'idle';
  const statusLabel = data.running ? 'Running' : data.lastStatus ? data.lastStatus : 'Idle';
  return (
    <div
      onDoubleClick={() => navigate(`/workflows?workflow=${data.workflowId}`)}
      title="Double-click to open in Workflows"
      className="w-full h-full rounded-xl border-2 border-dashed border-indigo-400 dark:border-indigo-500 bg-indigo-50/40 dark:bg-indigo-900/10 cursor-pointer"
    >
      <div className="px-3 py-1.5 flex items-center justify-between border-b border-dashed border-indigo-300 dark:border-indigo-600">
        <span className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{data.label}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium capitalize ${STATUS_PILL_STYLE[statusKey] || 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400'}`}>
          {statusLabel}
        </span>
      </div>
    </div>
  );
};

// Real WorkflowGraph node kinds (core/workflow/nodes.py) — one generic
// renderer, colored/iconed by kind, rather than eight near-identical
// components. This replaces the old unused `WorkflowNode` placeholder that
// was never actually instantiated anywhere.
const WORKFLOW_NODE_STYLE: Record<string, { icon: React.ReactNode; color: string }> = {
  acquire: { icon: <Camera className="h-5 w-5" />, color: 'border-purple-500 dark:border-purple-400 bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400' },
  analyse: { icon: <Calculator className="h-5 w-5" />, color: 'border-amber-500 dark:border-amber-400 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400' },
  branch: { icon: <GitBranch className="h-5 w-5" />, color: 'border-orange-500 dark:border-orange-400 bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400' },
  loop: { icon: <RotateCw className="h-5 w-5" />, color: 'border-teal-500 dark:border-teal-400 bg-teal-100 dark:bg-teal-900/30 text-teal-600 dark:text-teal-400' },
  optimise: { icon: <Target className="h-5 w-5" />, color: 'border-pink-500 dark:border-pink-400 bg-pink-100 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400' },
  set: { icon: <Sliders className="h-5 w-5" />, color: 'border-blue-500 dark:border-blue-400 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' },
  wait: { icon: <Clock className="h-5 w-5" />, color: 'border-gray-500 dark:border-gray-400 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300' },
  notify: { icon: <Bell className="h-5 w-5" />, color: 'border-green-500 dark:border-green-400 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400' },
};

const WorkflowGraphNode = ({ data }: { data: any }) => {
  const style = WORKFLOW_NODE_STYLE[data.kind] || WORKFLOW_NODE_STYLE.wait;
  const [borderColor, ...rest] = style.color.split(' ');
  return (
    <div className={`px-4 py-3 shadow-lg rounded-lg bg-white dark:bg-gray-800 border-2 ${borderColor} min-w-[180px]`}>
      <div className="flex items-center space-x-2">
        <div className={`p-1.5 rounded ${rest.join(' ')}`}>{style.icon}</div>
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">{data.label}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{data.kind}</div>
        </div>
      </div>
    </div>
  );
};

const nodeTypes = {
  instrument: InstrumentNode,
  port: PortNode,
  workflow_box: WorkflowBoxNode,
  ...Object.fromEntries(Object.keys(WORKFLOW_NODE_STYLE).map((kind) => [kind, WorkflowGraphNode])),
};

const edgeTypes = { binding: BindingEdge };

const PORT_ROW_HEIGHT = 74;
const BOX_HEADER_HEIGHT = 40;
const BOX_WIDTH = 260;
const BOX_COLUMN_X = 420;
const BOX_GAP_Y = 40;

/** Builds one workflow "box" group node plus one child PortNode per role,
 * and the binding edges that reflect each role's currently-bound
 * instrument. `boxIndex`/`boxesAbove` stack multiple workflows' boxes
 * vertically in one column so every workflow is visible at once — see
 * loadTopology(), which calls this once per role-based workflow. */
function buildBindingNodesAndEdges(
  workflowId: string,
  workflowName: string,
  roles: WorkflowBindingRole[],
  devices: any[],
  boxTop: number,
  onUnbind: (workflowId: string, role: string) => void,
  status?: { running?: boolean; last_status?: string | null }
): { nodes: Node[]; edges: Edge[]; boxHeight: number } {
  const boxId = `wfbox:${workflowId}`;
  const boxHeight = BOX_HEADER_HEIGHT + roles.length * PORT_ROW_HEIGHT + 16;

  const nodes: Node[] = [
    {
      id: boxId,
      type: 'workflow_box',
      position: { x: BOX_COLUMN_X, y: boxTop },
      style: { width: BOX_WIDTH, height: boxHeight },
      data: { workflowId, label: workflowName, running: status?.running, lastStatus: status?.last_status },
      draggable: true,
      selectable: false,
    },
  ];

  const edges: Edge[] = [];

  roles.forEach((role, i) => {
    const portId = `port:${workflowId}:${role.role}`;
    const boundDevice = role.instrument_id
      ? devices.find((d) => d.id === role.instrument_id)
      : undefined;
    nodes.push({
      id: portId,
      type: 'port',
      parentNode: boxId,
      extent: 'parent',
      position: { x: 16, y: BOX_HEADER_HEIGHT + 8 + i * PORT_ROW_HEIGHT },
      draggable: false,
      data: {
        workflowId,
        role: role.role,
        kind: role.kind,
        dimensionality: role.dimensionality,
        capability: role.capability,
        instrumentId: role.instrument_id,
        instrumentName: boundDevice ? boundDevice.name : role.instrument_id,
        optional: role.optional,
      },
    });
    if (role.instrument_id) {
      edges.push({
        id: `binding:${workflowId}:${role.role}`,
        type: 'binding',
        source: role.instrument_id,
        sourceHandle: 'instrument-out',
        target: portId,
        targetHandle: 'port-in',
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#22c55e' },
        data: { onDelete: () => onUnbind(workflowId, role.role) },
      });
    }
  });

  return { nodes, edges, boxHeight };
}

/** Depth-based left-to-right layout from a node's distance from a root
 * (a node with no incoming edges) — good enough for the modest node counts
 * these workflows have, no layout-library dependency needed. */
function layoutWorkflowGraph(graph: WorkflowGraphDetail): { nodes: Node[]; edges: Edge[] } {
  const nodeIds = Object.keys(graph.nodes);
  const incoming = new Map<string, number>(nodeIds.map((id) => [id, 0]));
  for (const edge of graph.edges) {
    incoming.set(edge.to_node, (incoming.get(edge.to_node) || 0) + 1);
  }

  const depth = new Map<string, number>();
  const queue: string[] = nodeIds.filter((id) => (incoming.get(id) || 0) === 0);
  queue.forEach((id) => depth.set(id, 0));
  const outgoingByNode = new Map<string, string[]>();
  for (const edge of graph.edges) {
    outgoingByNode.set(edge.from_node, [...(outgoingByNode.get(edge.from_node) || []), edge.to_node]);
  }
  while (queue.length > 0) {
    const current = queue.shift()!;
    const d = depth.get(current) || 0;
    for (const next of outgoingByNode.get(current) || []) {
      if (!depth.has(next) || (depth.get(next) as number) < d + 1) {
        depth.set(next, d + 1);
        queue.push(next);
      }
    }
  }
  // Any node never reached (shouldn't happen for an acyclic graph) still gets placed.
  nodeIds.forEach((id) => { if (!depth.has(id)) depth.set(id, 0); });

  const countPerDepth = new Map<number, number>();
  const nodes: Node[] = nodeIds.map((id) => {
    const d = depth.get(id) as number;
    const row = countPerDepth.get(d) || 0;
    countPerDepth.set(d, row + 1);
    const nodeData = graph.nodes[id];
    return {
      id,
      type: WORKFLOW_NODE_STYLE[nodeData.kind] ? nodeData.kind : 'wait',
      position: { x: d * 260 + 50, y: row * 140 + 50 },
      data: { label: nodeData.name || id, kind: nodeData.kind },
    };
  });

  const edges: Edge[] = graph.edges.map((edge, i) => ({
    id: `${edge.from_node}-${edge.to_node}-${i}`,
    source: edge.from_node,
    target: edge.to_node,
    label: edge.label || undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));

  return { nodes, edges };
}

function instrumentNodesFromDevices(devices: any[], x: number): Node[] {
  return (devices || []).map((inst, index) => ({
    id: inst.id,
    type: 'instrument',
    position: { x, y: index * 120 + 50 },
    data: {
      id: inst.id,
      label: inst.name,
      kind: inst.kind || 'detector',
      dimensionality: inst.dimensionality || '0D',
      capabilities: inst.capabilities || [],
      connected: inst.connected || false,
      status: inst.status,
      error: inst.error,
    },
  }));
}

export default function Flow() {
  const { devices, workflows, loadWorkflows, connectDeviceById } = useLabPilotStore();
  const [connectingAll, setConnectingAll] = useState(false);

  const handleConnectAll = async () => {
    const disconnected = devices.filter((d: any) => !d.connected);
    if (disconnected.length === 0) return;
    setConnectingAll(true);
    await Promise.allSettled(disconnected.map((d: any) => connectDeviceById(d.id)));
    setConnectingAll(false);
  };
  const [searchParams] = useSearchParams();
  const workflowId = searchParams.get('workflow');
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [workflowName, setWorkflowName] = useState<string | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [bindingError, setBindingError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // {workflowId: roles[]} for every role-based workflow currently shown —
  // used for the "X/Y roles bound" summary and to look up a port's
  // requirement when validating a drag.
  const [roleMap, setRoleMap] = useState<Record<string, WorkflowBindingRole[]>>({});
  // True only when `?workflow=id` points to a plain, non-role-based node
  // graph (e.g. an AI-authored workflow with no instrument roles) — the
  // one case that still gets an isolated, single-workflow view instead of
  // the always-on merged topology.
  const [isolatedGraph, setIsolatedGraph] = useState(false);
  // An optional, unbound role (e.g. omniscan.py's "scanner" — an
  // alternative to its "actuator"/"detector" pair, not required
  // alongside them) still shows by default so it isn't a surprise the
  // first time — this only declutters once toggled off. A role that IS
  // bound always shows regardless, so hiding this never makes an
  // actually-in-use connection disappear.
  const [showOptionalRoles, setShowOptionalRoles] = useState(true);

  // Shared by both the delete-button on a BindingEdge and the built-in
  // Delete/Backspace-on-selected-edge path (onEdgesDelete below).
  const handleUnbind = useCallback(
    async (targetWorkflowId: string, role: string) => {
      setBindingError(null);
      try {
        await setWorkflowBinding(targetWorkflowId, role, null);
        const portId = `port:${targetWorkflowId}:${role}`;
        setNodes((nds) =>
          nds.map((n) =>
            n.id === portId ? { ...n, data: { ...n.data, instrumentId: null, instrumentName: undefined } } : n
          )
        );
        setEdges((eds) => eds.filter((e) => e.target !== portId));
      } catch (err) {
        setBindingError(err instanceof Error ? err.message : `Failed to unbind role ${role}`);
      }
    },
    [setNodes, setEdges]
  );

  // Devices + every role-based workflow's binding box+ports+edges, merged
  // onto one canvas and always shown — so any workflow's bindings can be
  // inspected/edited without navigating to it individually.
  const loadTopology = async () => {
    setLoading(true);
    setWorkflowError(null);
    setBindingError(null);
    setWorkflowName(null);
    setIsolatedGraph(false);
    try {
      await loadWorkflows();
    } catch {
      // loadWorkflows already records its own error in the store; keep
      // going with whatever workflow list is currently cached there.
    }
    const currentWorkflows = useLabPilotStore.getState().workflows;

    const instrumentNodes = instrumentNodesFromDevices(devices, 50);
    const boxNodes: Node[] = [];
    const boxEdges: Edge[] = [];
    const newRoleMap: Record<string, WorkflowBindingRole[]> = {};
    let boxTop = 40;

    for (const wf of currentWorkflows) {
      try {
        const bindings = await getWorkflowBindings(wf.id);
        if (bindings.roles.length === 0) continue;
        // The summary count ("X/Y roles bound") always reflects every
        // declared role — only which PortNodes actually get drawn is
        // affected by showOptionalRoles, and even then only an optional
        // role that's currently unbound is ever hidden (see
        // showOptionalRoles' own docstring above).
        newRoleMap[wf.id] = bindings.roles;
        const visibleRoles = bindings.roles.filter(
          (r) => showOptionalRoles || !r.optional || r.instrument_id
        );
        const built = buildBindingNodesAndEdges(wf.id, wf.name, visibleRoles, devices, boxTop, handleUnbind, {
          running: wf.running,
          last_status: wf.last_status,
        });
        boxNodes.push(...built.nodes);
        boxEdges.push(...built.edges);
        boxTop += built.boxHeight + BOX_GAP_Y;
      } catch {
        // A workflow whose bindings can't be fetched (e.g. no script file)
        // just doesn't get a box — not fatal to the rest of the canvas.
      }
    }

    setRoleMap(newRoleMap);
    setNodes([...instrumentNodes, ...boxNodes]);
    setEdges(boxEdges);
    setLoading(false);
  };

  const loadIsolatedGraph = async (id: string) => {
    setLoading(true);
    setWorkflowError(null);
    setBindingError(null);
    setIsolatedGraph(true);
    try {
      const graph = await getWorkflowGraph(id);
      setWorkflowName(graph.name);
      const { nodes: wfNodes, edges: wfEdges } = layoutWorkflowGraph(graph);
      setNodes(wfNodes);
      setEdges(wfEdges);
    } catch (err) {
      setWorkflowError(err instanceof Error ? err.message : 'Failed to load workflow graph');
    } finally {
      setLoading(false);
    }
  };

  const loadView = async () => {
    if (workflowId) {
      try {
        const bindings = await getWorkflowBindings(workflowId);
        if (bindings.roles.length > 0) {
          await loadTopology();
          return;
        }
      } catch {
        // Not a role-based workflow (or bindings unavailable) — fall
        // through to the isolated node-graph view below.
      }
      await loadIsolatedGraph(workflowId);
    } else {
      await loadTopology();
    }
  };

  useEffect(() => {
    loadView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, devices, showOptionalRoles]);

  const refresh = () => loadView();

  // A connection is only valid instrument -> port, and only when the
  // instrument satisfies what the role requires — a mismatched drag is
  // refused here rather than silently accepted (the backend re-validates
  // the same thing in PUT .../bindings/{role}; this is just so a bad drag
  // never visually "sticks"). `portRefusal` is that rule, kept in one
  // place so the tooltip and the drag cannot disagree.
  const isValidConnection = useCallback(
    (connection: Connection) => {
      const source = nodes.find((n) => n.id === connection.source);
      const target = nodes.find((n) => n.id === connection.target);
      if (!source || !target || source.type !== 'instrument' || target.type !== 'port') return false;
      return portRefusal(source.data, target.data) === null;
    },
    [nodes]
  );

  const onConnect = useCallback(
    async (params: Connection) => {
      if (!params.source || !params.target) return;
      const portNode = nodes.find((n) => n.id === params.target);
      if (!portNode || portNode.type !== 'port') return;
      const targetWorkflowId = portNode.data.workflowId as string;
      const role = portNode.data.role as string;
      setBindingError(null);
      try {
        await setWorkflowBinding(targetWorkflowId, role, params.source);
        const boundDevice = devices.find((d) => d.id === params.source);
        setNodes((nds) =>
          nds.map((n) =>
            n.id === portNode.id
              ? { ...n, data: { ...n.data, instrumentId: params.source, instrumentName: boundDevice?.name || params.source } }
              : n
          )
        );
        // A port can only hold one binding — drop any previous edge into
        // it before adding the new one.
        setEdges((eds) => addEdge(
          {
            ...params, id: `binding:${targetWorkflowId}:${role}`, type: 'binding',
            sourceHandle: 'instrument-out', targetHandle: 'port-in',
            markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#22c55e' },
            data: { onDelete: () => handleUnbind(targetWorkflowId, role) },
          },
          eds.filter((e) => e.target !== portNode.id)
        ));
      } catch (err) {
        setBindingError(err instanceof Error ? err.message : `Failed to bind role ${role}`);
      }
    },
    [nodes, devices, setNodes, setEdges, handleUnbind]
  );

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      for (const edge of deleted) {
        const portNode = nodes.find((n) => n.id === edge.target);
        if (!portNode || portNode.type !== 'port') continue;
        handleUnbind(portNode.data.workflowId as string, portNode.data.role as string);
      }
    },
    [nodes, handleUnbind]
  );

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              {isolatedGraph ? (workflowName || 'Workflow Graph') : 'Lab Topology'}
            </h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {isolatedGraph
                ? 'Real workflow graph — nodes and edges as actually stored, not a mockup.'
                : Object.keys(roleMap).length > 0
                ? 'Drag an instrument onto a role to bind it — click the x on a connection to unbind it. Every workflow stays visible here so bindings can always be edited.'
                : 'Visual representation of connected instruments'}
            </p>
          </div>
          <div className="flex items-center space-x-2">
            {!isolatedGraph && Object.values(roleMap).some((roles) => roles.some((r) => r.optional)) && (
              <button
                onClick={() => setShowOptionalRoles((v) => !v)}
                title={showOptionalRoles ? 'Hide unused optional roles' : 'Show optional roles'}
                className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                {showOptionalRoles ? <EyeOff className="h-4 w-4 mr-2" /> : <Eye className="h-4 w-4 mr-2" />}
                {showOptionalRoles ? 'Hide Optional Roles' : 'Show Optional Roles'}
              </button>
            )}
            {devices.some((d: any) => !d.connected) && (
              <button
                onClick={handleConnectAll}
                disabled={connectingAll}
                className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
              >
                <Link2 className={`h-4 w-4 mr-2 ${connectingAll ? 'animate-pulse' : ''}`} />
                Connect All
              </button>
            )}
            <button
              onClick={refresh}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </button>
          </div>
        </div>

        {workflowError && (
          <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-400">
            {workflowError}
          </div>
        )}
        {bindingError && (
          <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-400">
            {bindingError}
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow" style={{ height: 'calc(100vh - 200px)' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onEdgesDelete={onEdgesDelete}
            isValidConnection={isValidConnection}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            connectionMode={ConnectionMode.Loose}
            fitView
            className="dark:bg-gray-800"
          >
            <Background className="dark:bg-gray-800" />
            <Controls className="dark:bg-gray-700 dark:text-white" />
            <MiniMap
              className="dark:bg-gray-700"
              nodeColor={(node) => (node.type === 'instrument' ? '#3B82F6' : node.type === 'port' ? '#22c55e' : '#8B5CF6')}
            />
            <Panel position="top-right" className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-lg">
              <div className="text-sm space-y-2">
                {isolatedGraph ? (
                  <span className="text-gray-700 dark:text-gray-300">{loading ? 'Loading…' : `Nodes (${nodes.length})`}</span>
                ) : loading ? (
                  <span className="text-gray-700 dark:text-gray-300">Loading…</span>
                ) : (
                  <>
                    <div className="flex items-center space-x-2">
                      <div className="h-3 w-3 rounded-full bg-blue-500"></div>
                      <span className="text-gray-700 dark:text-gray-300">Instruments ({devices?.length || 0})</span>
                    </div>
                    {Object.keys(roleMap).length > 0 && (
                      <div className="flex items-center space-x-2">
                        <div className="h-3 w-3 rounded-full bg-indigo-500"></div>
                        <span className="text-gray-700 dark:text-gray-300">
                          {Object.keys(roleMap).length} workflow{Object.keys(roleMap).length === 1 ? '' : 's'} ·{' '}
                          {Object.values(roleMap).flat().filter((r) => r.instrument_id).length}/
                          {Object.values(roleMap).flat().length} roles bound
                        </span>
                      </div>
                    )}
                  </>
                )}
              </div>
            </Panel>
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}
