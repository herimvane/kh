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

export default function UsersPage({ readOnly = false }: { readOnly?: boolean }) {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [departments, setDepartments] = useState<DepartmentChoice[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const { message, modal } = AntApp.useApp();
  const departmentTree = useMemo(() => buildDepartmentTree(departments), [departments]);
  const selectedRole = Form.useWatch("role", form);

  const load = async (nextPage = page, keyword = q, nextDepartmentId = departmentId) => {
    setLoading(true);
    try {
      const [users, departmentChoices, positionRows] = await Promise.all([
        masterDataApi.users(keyword, nextPage, nextDepartmentId),
        masterDataApi.departmentChoices(),
        masterDataApi.positions()
      ]);
      setRows(users.items);
      setTotal(users.pagination.total);
      setPage(users.pagination.page);
      setDepartments(departmentChoices);
      setPositions(positionRows);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(1, ""), []);

  const save = async () => {
    const values = await form.validateFields();
    if (values.role === "admin") {
      values.department_id = null;
      values.position_id = null;
    }
    setSaving(true);
    try {
      if (editing) await masterDataApi.updateUser(editing.id, values);
      else await masterDataApi.createUser(values);
      message.success(editing ? "人员已更新。" : "人员已创建。");
      setOpen(false);
      await load();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "人员保存失败，请稍后重试。";
      if (errorMessage.includes("用户名")) {
        form.setFields([{ name: "username", errors: [errorMessage] }]);
      }
      message.error(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageTitle title="人员管理" extra={!readOnly ? <Button type="primary" onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ role: "user", is_active: true }); setOpen(true); }}>新增人员</Button> : undefined} />
      <Space className="table-toolbar">
        <TreeSelect
          className="user-department-filter"
          allowClear
          showSearch
          treeNodeFilterProp="title"
          treeData={departmentTree}
          value={departmentId ?? undefined}
          placeholder="全部部门"
          treeDefaultExpandAll
          onChange={(value) => { const next = value == null ? null : Number(value); setDepartmentId(next); void load(1, q, next); }}
        />
        <Input.Search placeholder="搜索用户名或姓名" allowClear onSearch={(value) => { setQ(value); void load(1, value, departmentId); }} />
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, total, pageSize: 10, showSizeChanger: false, showTotal: (count) => `共 ${count} 条`, onChange: (next) => void load(next) }}
        columns={[
          { title: "用户名", dataIndex: "username" },
          { title: "姓名", dataIndex: "full_name" },
          { title: "角色", dataIndex: "role", render: (role) => <Tag color={role === "admin" ? "blue" : "green"}>{role === "admin" ? "管理员" : "普通用户"}</Tag> },
          { title: "部门", dataIndex: "department_name", render: (value) => value || "-" },
          { title: "职位", dataIndex: "position_name", render: (value) => value || "-" },
          { title: "管理范围", dataIndex: "admin_scope_department_name", render: (value, record) => record.role === "admin" ? (record.is_super_admin ? "全部部门" : `${value || "-"}及下级`) : "-" },
          { title: "状态", dataIndex: "is_active", render: (active) => <Tag color={active ? "success" : "default"}>{active ? "启用" : "停用"}</Tag> },
          ...(!readOnly ? [{
            title: "操作",
            width: 180,
            render: (_: unknown, record: UserRow) => (
              <Space>
                <Button size="small" onClick={() => {
                  setEditing(record);
                  form.setFieldsValue({
                    ...record,
                    department_id: record.role === "admin" ? undefined : record.department_id,
                    position_id: record.role === "admin" ? undefined : record.position_id
                  });
                  setOpen(true);
                }}>编辑</Button>
                <Button size="small" danger onClick={() => confirmDeletion(modal, { title: "删除人员", content: record.full_name, action: () => masterDataApi.deleteUser(record.id), onSuccess: async (result) => { message.success(result.message); await load(); } })}>删除</Button>
              </Space>
            )
          }] : [])
        ]}
      />
      <Modal title={editing ? "编辑人员" : "新增人员"} open={open} confirmLoading={saving} onCancel={() => setOpen(false)} onOk={save}>
        <Form
          form={form}
          layout="vertical"
          onValuesChange={(changedValues) => {
            if (changedValues.role === "admin") {
              form.setFieldsValue({ department_id: undefined, position_id: undefined });
            } else if (changedValues.role === "user") {
              form.setFieldValue("admin_scope_department_id", undefined);
            }
          }}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名。" }]}><Input /></Form.Item>
          <Form.Item name="full_name" label="姓名" rules={[{ required: true, message: "请输入姓名。" }]}><Input /></Form.Item>
          <Form.Item name="role" label="角色"><Select options={[{ value: "user", label: "普通用户" }, { value: "admin", label: "管理员" }]} /></Form.Item>
          <Form.Item name="is_active" label="状态"><Select options={[{ value: true, label: "启用" }, { value: false, label: "停用" }]} /></Form.Item>
          <Form.Item name="department_id" label="部门">
            <TreeSelect
              allowClear
              disabled={selectedRole === "admin"}
              showSearch
              treeNodeFilterProp="title"
              treeData={departmentTree}
              placeholder={selectedRole === "admin" ? "管理员无需选择" : "请选择部门"}
              treeDefaultExpandAll
            />
          </Form.Item>
          {selectedRole === "admin" ? (
            <Form.Item name="admin_scope_department_id" label="管理员数据范围" extra="不选择部门表示超级管理员，可管理全部数据。">
              <TreeSelect allowClear showSearch treeNodeFilterProp="title" treeData={departmentTree} placeholder="不选择则为超级管理员" treeDefaultExpandAll />
            </Form.Item>
          ) : null}
          <Form.Item name="position_id" label="职位">
            <Select
              allowClear
              disabled={selectedRole === "admin"}
              placeholder={selectedRole === "admin" ? "管理员无需选择" : "请选择职位"}
              options={positions.map((item) => ({ value: item.id, label: item.name }))}
            />
          </Form.Item>
          <Form.Item name="password" label={editing ? "重置密码" : "初始密码"}><Input.Password placeholder={editing ? "留空则不修改；重置后将强制改密" : "默认 password!"} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
