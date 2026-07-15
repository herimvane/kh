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

export default function PositionsPage() {
  const [rows, setRows] = useState<Position[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<Position | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const { message, modal } = AntApp.useApp();

  const load = async () => {
    setLoading(true);
    try {
      setRows(await masterDataApi.positions());
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(), []);

  const save = async () => {
    const values = await form.validateFields();
    if (editing) await masterDataApi.updatePosition(editing.id, values);
    else await masterDataApi.createPosition(values);
    message.success(editing ? "职位已更新。" : "职位已创建。");
    setOpen(false);
    await load();
  };

  return (
    <>
      <PageTitle title="职位管理" extra={<Button type="primary" onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新增职位</Button>} />
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={tablePagination()}
        columns={[
          { title: "排序", dataIndex: "sort_order", width: 90 },
          { title: "职位名称", dataIndex: "name" },
          {
            title: "操作",
            width: 180,
            render: (_, record) => (
              <Space>
                <Button size="small" onClick={() => { setEditing(record); form.setFieldsValue(record); setOpen(true); }}>编辑</Button>
                <Button size="small" danger onClick={() => confirmDeletion(modal, { title: "删除职位", content: record.name, action: () => masterDataApi.deletePosition(record.id), onSuccess: async (result) => { message.success(result.message); await load(); } })}>删除</Button>
              </Space>
            )
          }
        ]}
      />
      <Modal title={editing ? "编辑职位" : "新增职位"} open={open} onCancel={() => setOpen(false)} onOk={save}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="职位名称" rules={[{ required: true, message: "请输入职位名称。" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

