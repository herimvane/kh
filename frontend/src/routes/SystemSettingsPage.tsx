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

export default function SystemSettingsPage({ systemName, onChanged }: { systemName: string; onChanged: (name: string) => void }) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const { message } = AntApp.useApp();
  useEffect(() => { form.setFieldsValue({ system_name: systemName }); }, [form, systemName]);

  const save = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const result = await settingsApi.update(values.system_name);
      onChanged(result.system_name);
      message.success("系统设置已保存。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "系统设置保存失败。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageTitle title="系统设置" />
      <section className="settings-panel">
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item name="system_name" label="系统名称" rules={[{ required: true, message: "请输入系统名称。" }, { max: 80, message: "系统名称不能超过 80 个字符。" }]}>
            <Input size="large" placeholder="请输入系统名称" />
          </Form.Item>
          <Button type="primary" loading={saving} onClick={() => void save()}>保存设置</Button>
        </Form>
      </section>
    </>
  );
}

