import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import type { Entity } from '../lib/api';

interface TreeNode {
  entity: Entity;
  children: TreeNode[];
}

interface EntityTreeProps {
  entities: Entity[];
  onSelect: (id: string) => void;
  selectedId?: string;
}

const TYPE_BADGE_COLORS: Record<string, string> = {
  BV: 'bg-blue-100 text-blue-700',
  GmbH: 'bg-green-100 text-green-700',
  SAS: 'bg-purple-100 text-purple-700',
  Ltd: 'bg-amber-100 text-amber-700',
};

function buildTree(entities: Entity[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  for (const entity of entities) {
    map.set(entity.id, { entity, children: [] });
  }

  for (const entity of entities) {
    const node = map.get(entity.id)!;
    if (entity.parent_id && map.has(entity.parent_id)) {
      map.get(entity.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  return roots;
}

function TreeNodeRow({
  node,
  depth,
  onSelect,
  selectedId,
  expandedIds,
  toggleExpanded,
}: {
  node: TreeNode;
  depth: number;
  onSelect: (id: string) => void;
  selectedId?: string;
  expandedIds: Set<string>;
  toggleExpanded: (id: string) => void;
}) {
  const hasChildren = node.children.length > 0;
  const isExpanded = expandedIds.has(node.entity.id);
  const isSelected = selectedId === node.entity.id;
  const badgeColor = TYPE_BADGE_COLORS[node.entity.entity_type] ?? 'bg-gray-100 text-gray-700';

  return (
    <>
      <div
        onClick={() => onSelect(node.entity.id)}
        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm cursor-pointer transition-colors ${
          isSelected
            ? 'bg-blue-50 ring-1 ring-blue-200'
            : 'hover:bg-gray-50'
        }`}
        style={{ paddingLeft: `${depth * 24 + 12}px` }}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              toggleExpanded(node.entity.id);
            }}
            className="rounded p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}

        <span className="font-medium text-gray-900">{node.entity.name}</span>

        <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${badgeColor}`}>
          {node.entity.entity_type}
        </span>

        <span className="text-xs text-gray-500">{node.entity.country_code}</span>
        <span className="text-xs text-gray-400">{node.entity.currency}</span>
      </div>

      {isExpanded &&
        node.children.map((child) => (
          <TreeNodeRow
            key={child.entity.id}
            node={child}
            depth={depth + 1}
            onSelect={onSelect}
            selectedId={selectedId}
            expandedIds={expandedIds}
            toggleExpanded={toggleExpanded}
          />
        ))}
    </>
  );
}

export default function EntityTree({ entities, onSelect, selectedId }: EntityTreeProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const roots = useMemo(() => buildTree(entities), [entities]);

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (entities.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center text-sm text-gray-500">
        No entities yet. Click "Add Entity" to create one.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-2 space-y-0.5">
      {roots.map((root) => (
        <TreeNodeRow
          key={root.entity.id}
          node={root}
          depth={0}
          onSelect={onSelect}
          selectedId={selectedId}
          expandedIds={expandedIds}
          toggleExpanded={toggleExpanded}
        />
      ))}
    </div>
  );
}
