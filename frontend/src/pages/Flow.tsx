import React, { useCallback, useEffect, useState } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  ConnectionMode,
  Panel,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Cpu, Microscope, Zap, RefreshCw } from 'lucide-react';
import { useLabPilotStore } from '@/store';

interface DashboardInstrument {
  id: string;
  name: string;
  adapter_type: string;
  kind: string;
  dimensionality: string;
  connected: boolean;
  tags: string[];
}

interface Workflow {
  id: string;
  name: string;
  description?: string;
  instruments?: string[];
}

const InstrumentNode = ({ data }: { data: any }) => {
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

  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-white dark:bg-gray-800 border-2 border-blue-500 dark:border-blue-400 min-w-[180px]">
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
      {data.connected && (
        <div className="mt-2 flex items-center">
          <div className="h-2 w-2 rounded-full bg-green-500 mr-2"></div>
          <span className="text-xs text-green-600 dark:text-green-400">Connected</span>
        </div>
      )}
    </div>
  );
};

const WorkflowNode = ({ data }: { data: any }) => {
  return (
    <div className="px-4 py-3 shadow-lg rounded-lg bg-white dark:bg-gray-800 border-2 border-purple-500 dark:border-purple-400 min-w-[180px]">
      <div className="flex items-center space-x-2">
        <div className="p-1.5 rounded bg-purple-100 dark:bg-purple-900/30">
          <Cpu className="h-5 w-5 text-purple-600 dark:text-purple-400" />
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {data.label}
          </div>
          {data.description && (
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {data.description}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const nodeTypes = {
  instrument: InstrumentNode,
  workflow: WorkflowNode,
};

export default function Flow() {
  const { devices } = useLabPilotStore();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const generateFlowNodes = () => {
    // Create instrument nodes from store
    const instrumentNodes: Node[] = (devices || []).map((inst, index) => {
      const node: Node = {
        id: inst.id,
        type: 'instrument',
        position: { x: 50, y: index * 120 + 50 },
        data: {
          label: inst.name,
          kind: inst.kind || 'detector',
          dimensionality: inst.dimensionality || '0D',
          connected: inst.connected || false,
        },
      };
      return node;
    });

    setNodes(instrumentNodes);
    setEdges([]);
  };

  useEffect(() => {
    generateFlowNodes();
  }, [devices]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Workflow Flow Chart
            </h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Visual representation of instruments and workflows
            </p>
          </div>
          <button
            onClick={generateFlowNodes}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </button>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow" style={{ height: 'calc(100vh - 200px)' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            connectionMode={ConnectionMode.Loose}
            fitView
            className="dark:bg-gray-800"
          >
            <Background className="dark:bg-gray-800" />
            <Controls className="dark:bg-gray-700 dark:text-white" />
            <MiniMap
              className="dark:bg-gray-700"
              nodeColor={(node) => {
                if (node.type === 'instrument') return '#3B82F6';
                if (node.type === 'workflow') return '#8B5CF6';
                return '#6B7280';
              }}
            />
            <Panel position="top-right" className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-lg">
              <div className="text-sm space-y-2">
                <div className="flex items-center space-x-2">
                  <div className="h-3 w-3 rounded-full bg-blue-500"></div>
                  <span className="text-gray-700 dark:text-gray-300">Instruments ({devices?.length || 0})</span>
                </div>
              </div>
            </Panel>
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}
