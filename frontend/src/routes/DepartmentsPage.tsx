import {
  ApartmentOutlined,
  CheckSquareOutlined,
  PieChartOutlined,
  TeamOutlined
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  TreeSelect
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type React from "react";
import { useEffect, useMemo, useState } from "react";

import { evaluationsApi, type Evaluation } from "../api/evaluations";
import {
  masterDataApi,
  type Department,
  type DepartmentChoice,
  type Position,
  type ScoreOption,
  type UserRow
} from "../api/masterData";
import { settingsApi } from "../api/settings";
import { buildDepartmentTree, confirmDeletion, PageTitle, tablePagination } from "./routeShared";

export default function DepartmentsPage() {
  const [rows, setRows] = useState<Department[]>([]);
  const [choices, setChoices] = useState<DepartmentChoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<Department | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const { message, modal } = AntApp.useApp();
  const blockedParentIds = useMemo(() => {
    if (!editing) return new Set<number>();
    const blocked = new Set<number>([editing.id]);
    const childrenByParent = new Map<number, number[]>();
    choices.forEach((department) => {
      if (department.parent_id) {
        const children = childrenByParent.get(department.parent_id) || [];
        children.push(department.id);
        childrenByParent.set(department.parent_id, children);
      }
    });
    const visit = (departmentId: number) => {
      (childrenByParent.get(departmentId) || []).forEach((childId) => {
        if (!blocked.has(childId)) {
          blocked.add(childId);
          visit(childId);
        }
      });
    };
    visit(editing.id);
    return blocked;
  }, [choices, editing]);
  const parentDepartmentTree = useMemo(
    () => buildDepartmentTree(choices, blockedParentIds),
    [choices, blockedParentIds]
  );

  const load = async () => {
    setLoading(true);
    try {
      const [departmentRows, departmentChoices] = await Promise.all([
        masterDataApi.departments(),
        masterDataApi.departmentChoices()
      ]);
      setRows(departmentRows);
      setChoices(departmentChoices);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(), []);

  const save = async () => {
    const values = await form.validateFields();
    if (editing) await masterDataApi.updateDepartment(editing.id, values);
    else await masterDataApi.createDepartment(values);
    message.success(editing ? "部门已更新。" : "部门已创建。");
    setOpen(false);
    setEditing(null);
    form.resetFields();
    await load();
  };

  const columns: ColumnsType<Department> = [
    { title: "排序", dataIndex: "sort_order", width: 90 },
    { title: "部门名称", dataIndex: "name" },
    { title: "上级部门", dataIndex: "parent_name", render: (value) => value || "-" },
    {
      title: "操作",
      width: 180,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => { setEditing(record); form.setFieldsValue(record); setOpen(true); }}>编辑</Button>
          <Button
            size="small"
            danger
            onClick={() => confirmDeletion(modal, { title: "删除部门", content: record.name, action: () => masterDataApi.deleteDepartment(record.id), onSuccess: async (result) => { message.success(result.message); await load(); } })}
          >
            删除
          </Button>
        </Space>
      )
    }
  ];

  return (
    <>
      <PageTitle title="部门管理" extra={<Button type="primary" onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新增部门</Button>} />
      <Table rowKey="id" columns={columns} dataSource={rows} loading={loading} pagination={tablePagination()} />
      <Modal title={editing ? "编辑部门" : "新增部门"} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="部门名称" rules={[{ required: true, message: "请输入部门名称。" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="parent_id" label="上级部门">
            <TreeSelect
              allowClear
              showSearch
              treeNodeFilterProp="title"
              treeData={parentDepartmentTree}
              placeholder="不选则为一级部门"
              treeDefaultExpandAll
            />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
