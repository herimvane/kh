import { App as AntApp, TreeSelect, Typography } from "antd";
import type React from "react";
import { useMemo } from "react";


export const tablePagination = () => ({
  pageSize: 10,
  showSizeChanger: false,
  showTotal: (total: number) => `共 ${total} 条`
});

type DeleteResult = { message: string };

export function confirmDeletion(
  modal: ReturnType<typeof AntApp.useApp>["modal"],
  options: {
    title: string;
    content?: React.ReactNode;
    action: () => Promise<DeleteResult>;
    onSuccess: (result: DeleteResult) => Promise<void> | void;
  }
) {
  modal.confirm({
    title: options.title,
    content: options.content,
    okText: "确认删除",
    cancelText: "取消",
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        const result = await options.action();
        await options.onSuccess(result);
      } catch (error) {
        modal.error({
          title: "无法删除",
          content: error instanceof Error ? error.message : "删除失败，请检查数据引用后重试。",
          okText: "我知道了"
        });
      }
    }
  });
}

type DepartmentTreeNode = {
  title: string;
  value: number;
  key: number;
  disabled?: boolean;
  children: DepartmentTreeNode[];
};

export function buildDepartmentTree(
  departments: Array<{ id: number; name: string; parent_id?: number | null }>,
  disabledIds: ReadonlySet<number> = new Set()
) {
  const nodes = new Map<number, DepartmentTreeNode>();
  departments.forEach((department) => nodes.set(department.id, {
    title: department.name,
    value: department.id,
    key: department.id,
    disabled: disabledIds.has(department.id),
    children: []
  }));
  const roots: DepartmentTreeNode[] = [];
  departments.forEach((department) => {
    const node = nodes.get(department.id)!;
    const parent = department.parent_id ? nodes.get(department.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  });
  return roots;
}

export function DepartmentMultiTreeSelect({
  departments,
  value = [],
  onChange,
  placeholder = "搜索或选择部门"
}: {
  departments: Array<{ id: number; name: string; parent_id?: number | null }>;
  value?: number[];
  onChange?: (value: number[]) => void;
  placeholder?: string;
}) {
  const selected = new Set(value);
  const baseTree = useMemo(() => buildDepartmentTree(departments), [departments]);
  const descendantIds = (node: DepartmentTreeNode): number[] =>
    node.children.flatMap((child) => [child.value, ...descendantIds(child)]);
  const updateDescendants = (node: DepartmentTreeNode, remove: boolean) => {
    const next = new Set(value);
    descendantIds(node).forEach((id) => remove ? next.delete(id) : next.add(id));
    onChange?.(Array.from(next));
  };
  const decorate = (node: DepartmentTreeNode): Record<string, unknown> => {
    const descendants = descendantIds(node);
    const allSelected = descendants.length > 0 && descendants.every((id) => selected.has(id));
    return {
      ...node,
      searchText: node.title,
      labelText: node.title,
      title: (
        <span className="department-tree-title">
          <span>{node.title}</span>
          {descendants.length ? (
            <button
              type="button"
              className="department-tree-branch-action"
              aria-label={`${allSelected ? "清除" : "选择"}${node.title}下的全部子部门`}
              onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); }}
              onClick={(event) => { event.preventDefault(); event.stopPropagation(); updateDescendants(node, allSelected); }}
            >
              {allSelected ? "清子级" : "选子级"}
            </button>
          ) : null}
        </span>
      ),
      children: node.children.map(decorate)
    };
  };
  const normalizeValues = (items: unknown) => Array.isArray(items)
    ? items.map((item) => typeof item === "object" && item !== null && "value" in item ? Number((item as { value: unknown }).value) : Number(item))
    : [];

  return (
    <TreeSelect
      className="department-tree-select"
      value={value}
      onChange={(items) => onChange?.(normalizeValues(items))}
      treeData={baseTree.map(decorate)}
      treeCheckable
      treeCheckStrictly
      showCheckedStrategy={TreeSelect.SHOW_ALL}
      showSearch
      treeNodeFilterProp="searchText"
      treeNodeLabelProp="labelText"
      allowClear
      maxTagCount="responsive"
      maxTagPlaceholder={(values) => `另有 ${values.length} 个部门`}
      placeholder={placeholder}
      treeDefaultExpandAll
    />
  );
}

export function PageTitle({ title, extra }: { title: string; extra?: React.ReactNode }) {
  return (
    <div className="page-heading">
      <div><Typography.Title level={2}>{title}</Typography.Title></div>
      {extra}
    </div>
  );
}
