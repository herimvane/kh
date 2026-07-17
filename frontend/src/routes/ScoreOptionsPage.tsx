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

export default function ScoreOptionsPage({ readOnly = false }: { readOnly?: boolean }) {
  const [rows, setRows] = useState<ScoreOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<ScoreOption | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const { message, modal } = AntApp.useApp();

  const load = async () => {
    setLoading(true);
    try {
      setRows(await masterDataApi.scoreOptions());
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(), []);

  const save = async () => {
    const values = await form.validateFields();
    if (editing) await masterDataApi.updateScoreOption(editing.id, values);
    else await masterDataApi.createScoreOption(values);
    message.success(editing ? "评分选项已更新。" : "评分选项已创建。");
    setOpen(false);
    await load();
  };

  return (
    <>
      <PageTitle title="评分选项" extra={!readOnly ? <Button type="primary" onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新增选项</Button> : undefined} />
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={tablePagination()}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "分值", dataIndex: "value" },
          ...(!readOnly ? [{
            title: "操作",
            width: 180,
            render: (_: unknown, record: ScoreOption) => (
              <Space>
                <Button size="small" onClick={() => { setEditing(record); form.setFieldsValue(record); setOpen(true); }}>编辑</Button>
                <Button size="small" danger onClick={() => confirmDeletion(modal, { title: "删除评分选项", content: record.name, action: () => masterDataApi.deleteScoreOption(record.id), onSuccess: async (result) => { message.success(result.message); await load(); } })}>删除</Button>
              </Space>
            )
          }] : [])
        ]}
      />
      <Modal title={editing ? "编辑评分选项" : "新增评分选项"} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称。" }]}><Input /></Form.Item>
          <Form.Item name="value" label="分值" rules={[{ required: true, message: "请输入分值。" }]}><InputNumber min={0} max={100} style={{ width: "100%" }} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
