import {
  AuditOutlined,
  BarChartOutlined,
  DownloadOutlined
} from "@ant-design/icons";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  TreeSelect,
  Typography
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";

import {
  evaluationsApi,
  type Evaluation,
  type EvaluationConfig,
  type EvaluationScoreDepartment,
  type EvaluationScorePerson,
  type EvaluationStatsResponse,
  type ReviewSubmissionDetailResponse
} from "../api/evaluations";
import { masterDataApi, type DepartmentChoice, type Position, type ReviewerUser } from "../api/masterData";
import { buildDepartmentTree, confirmDeletion, DepartmentMultiTreeSelect, PageTitle, tablePagination } from "./routeShared";

export default function EvaluationsPage() {
  const [rows, setRows] = useState<Evaluation[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Evaluation | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [archiveDeleteTarget, setArchiveDeleteTarget] = useState<Evaluation | null>(null);
  const [deletingArchive, setDeletingArchive] = useState(false);
  const [form] = Form.useForm();
  const [copyForm] = Form.useForm();
  const [archiveDeleteForm] = Form.useForm<{ admin_password: string }>();
  const { message, modal } = AntApp.useApp();

  const load = async () => {
    setLoading(true);
    try {
      setRows(await evaluationsApi.list());
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(), []);

  const save = async () => {
    const values = await form.validateFields();
    try {
      await evaluationsApi.create(values);
      message.success("考核已创建。");
      setOpen(false);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "创建考核失败。");
    }
  };

  const runAction = async (action: () => Promise<{ message: string }>) => {
    try {
      const result = await action();
      message.success(result.message);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "操作失败，请稍后重试。");
    }
  };

  const openConfig = (record: Evaluation) => {
    setSelected(record);
    setConfigOpen(true);
  };

  const deleteEvaluation = (record: Evaluation) => {
    if (!record.archived) {
      confirmDeletion(modal, {
        title: "删除考核",
        content: record.name,
        action: () => evaluationsApi.delete(record.id),
        onSuccess: async (result) => { message.success(result.message); await load(); }
      });
      return;
    }

    archiveDeleteForm.resetFields();
    setArchiveDeleteTarget(record);
  };

  const deleteArchivedEvaluation = async () => {
    if (!archiveDeleteTarget) return;
    const values = await archiveDeleteForm.validateFields();
    setDeletingArchive(true);
    try {
      const result = await evaluationsApi.delete(archiveDeleteTarget.id, values.admin_password);
      message.success(result.message);
      setArchiveDeleteTarget(null);
      archiveDeleteForm.resetFields();
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "管理员密码验证失败。");
    } finally {
      setDeletingArchive(false);
    }
  };

  return (
    <>
      <PageTitle
        title="考核管理"
        extra={
          <Space>
            <Button onClick={() => modal.info({ title: "操作审计", width: 900, content: <AuditPreview /> })}>操作审计</Button>
            <Button type="primary" onClick={() => { form.resetFields(); setOpen(true); }}>新增考核</Button>
          </Space>
        }
      />
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={tablePagination()}
        columns={[
          { title: "年度", dataIndex: "year", width: 100 },
          { title: "年内批次", dataIndex: "sequence", width: 110, render: (value) => `第 ${value} 批` },
          { title: "名称", dataIndex: "name" },
          { title: "任务进度", render: (_, record) => `${record.submitted_tasks} / ${record.total_tasks}` },
          { title: "状态", render: (_, record) => <Space><Tag color={record.is_open ? "success" : "default"}>{record.is_open ? "开放" : "未开放"}</Tag>{record.archived ? <Tag color="blue">已归档</Tag> : null}</Space> },
          {
            title: "操作",
            width: 640,
            render: (_, record) => (
              <Space wrap>
                <Button size="small" onClick={() => openConfig(record)}>配置/详情</Button>
                <Button size="small" disabled={record.archived} onClick={() => modal.confirm({ title: record.tasks_generated ? "重新生成任务" : "生成任务", content: record.tasks_generated ? "会覆盖现有任务和评分。" : "将按当前规则生成任务。", onOk: () => runAction(() => evaluationsApi.generateTasks(record.id, record.tasks_generated)) })}>
                  {record.tasks_generated ? "重新生成" : "生成任务"}
                </Button>
                <Button
                  size="small"
                  danger
                  disabled={record.archived || !record.tasks_generated}
                  onClick={() => modal.confirm({
                    title: "清空考核任务",
                    content: "将删除本次考核的全部已生成任务、已提交评分和重新修改记录，并关闭考核。",
                    okText: "确认清空",
                    cancelText: "取消",
                    okButtonProps: { danger: true },
                    onOk: () => runAction(() => evaluationsApi.clearTasks(record.id, true))
                  })}
                >
                  清空任务
                </Button>
                <Button size="small" disabled={record.archived} onClick={() => runAction(() => evaluationsApi.toggleOpen(record.id))}>{record.is_open ? "关闭" : "开放"}</Button>
                <Button size="small" disabled={record.archived} onClick={() => modal.confirm({ title: "归档统计", content: "归档会固化当前分数和规则快照。", onOk: () => runAction(() => evaluationsApi.archive(record.id, true)) })}>归档</Button>
                <Button
                  size="small"
                  onClick={async () => {
                    copyForm.resetFields();
                    const preview = await evaluationsApi.copyPreview(record.id);
                    modal.confirm({
                      title: "复制考核",
                      width: 520,
                      okText: "复制为草稿",
                      content: (
                        <Form form={copyForm} layout="vertical">
                          <Form.Item name="year" label="新年度" rules={[{ required: true, message: "请输入年度。" }]}><InputNumber min={2000} max={2100} style={{ width: "100%" }} /></Form.Item>
                          <Form.Item name="name" label="名称"><Input /></Form.Item>
                          {preview.missing.length ? <Alert type="warning" showIcon message={`将自动跳过 ${preview.missing.length} 项已删除数据`} description={<span>复制后请检查考核配置。涉及：{preview.missing.map((item) => item.name).join("、")}。</span>} style={{ marginBottom: 16 }} /> : null}
                        </Form>
                      ),
                      onOk: async () => {
                        const values = await copyForm.validateFields();
                        try {
                          const result = await evaluationsApi.copy(record.id, values);
                          message.success(result.message, 5);
                          await load();
                        } catch (error) {
                          message.error(error instanceof Error ? error.message : "复制考核失败。");
                          throw error;
                        }
                      }
                    });
                  }}
                >
                  复制
                </Button>
                <Button
                  size="small"
                  danger
                  onClick={() => deleteEvaluation(record)}
                >
                  删除
                </Button>
              </Space>
            )
          }
        ]}
      />
      <Modal title="新增考核" open={open} onCancel={() => setOpen(false)} onOk={save}>
        <Form form={form} layout="vertical">
          <Form.Item name="year" label="年度" rules={[{ required: true, message: "请输入年度。" }]}><InputNumber min={2000} max={2100} style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="sequence" label="年内批次"><InputNumber min={1} precision={0} placeholder="留空则自动顺延" style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="name" label="考核名称"><Input placeholder="留空自动生成，如 2026-02" /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="删除已归档考核"
        width={460}
        open={Boolean(archiveDeleteTarget)}
        forceRender
        confirmLoading={deletingArchive}
        okText="验证并删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        onCancel={() => { if (!deletingArchive) setArchiveDeleteTarget(null); }}
        onOk={() => void deleteArchivedEvaluation()}
      >
        <Form form={archiveDeleteForm} layout="vertical" requiredMark={false} style={{ marginTop: 16 }}>
          <Alert type="warning" showIcon message="删除后无法恢复，请输入当前管理员密码确认。" style={{ marginBottom: 16 }} />
          <Form.Item name="admin_password" label="管理员密码" rules={[{ required: true, message: "请输入当前管理员密码。" }]}>
            <Input.Password autoComplete="current-password" placeholder="请输入当前管理员密码" onPressEnter={() => void deleteArchivedEvaluation()} />
          </Form.Item>
        </Form>
      </Modal>
      <Drawer
        title={selected ? `${selected.name}（${selected.year} 年第 ${selected.sequence} 批）` : "考核配置"}
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        width="min(1180px, 96vw)"
        destroyOnClose
      >
        {selected ? <EvaluationConfigPanel evaluation={selected} onChanged={async () => { await load(); }} /> : null}
      </Drawer>
    </>
  );
}

function EvaluationConfigPanel({ evaluation, onChanged }: { evaluation: Evaluation; onChanged: () => Promise<void> }) {
  const [config, setConfig] = useState<EvaluationConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const { message } = AntApp.useApp();

  const load = async () => {
    setLoading(true);
    try {
      setConfig(await evaluationsApi.config(evaluation.id));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(), [evaluation.id]);

  const refresh = async (text?: string) => {
    if (text) message.success(text);
    await load();
    await onChanged();
  };

  if (!config) return <Card loading={loading} />;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      {evaluation.archived ? <Alert type="info" showIcon message="归档快照" description="以下规则、提交记录和最终结果已固化，不受当前人员及组织数据变更影响。" /> : null}
      <Tabs
      items={[
        { key: "person", label: "人员考核规则", children: <PersonRulesTab config={config} refresh={refresh} /> },
        { key: "department", label: "部门考核规则", children: <DepartmentRulesTab config={config} refresh={refresh} /> },
        { key: "share", label: "部门得分占比", children: <DepartmentShareTab config={config} refresh={refresh} /> },
        { key: "submissions", label: "评分提交管理", children: <ReviewSubmissionsTab evaluationId={evaluation.id} /> },
        evaluation.archived
          ? { key: "final", label: "最终结果", children: <StatsTab evaluationId={evaluation.id} archived /> }
          : { key: "live", label: "实时统计", children: <StatsTab evaluationId={evaluation.id} archived={false} /> }
      ]}
      />
    </Space>
  );
}

function OptionCheckboxes({ options, value, onChange, disabled = false }: { options: EvaluationConfig["score_options"]; value: number[]; onChange: (value: number[]) => void; disabled?: boolean }) {
  return (
    <Checkbox.Group value={value} onChange={(checked) => onChange(checked.map(Number))}>
      <Space wrap>
        {options.map((option) => <Checkbox disabled={disabled} key={option.id} value={option.id}>{option.name}（{option.value}）</Checkbox>)}
      </Space>
    </Checkbox.Group>
  );
}

function DepartmentScopeSummary({ rule, departmentNames }: { rule: any; departmentNames: Map<number, string> }) {
  if (rule.scope_type === "same_department") return <span>同部门</span>;
  const names = (rule.target_department_ids || [])
    .map((departmentId: number) => departmentNames.get(departmentId))
    .filter(Boolean) as string[];
  if (!names.length && rule.target_department_label) {
    const archivedNames = String(rule.target_department_label).split("、").filter(Boolean);
    const fullText = archivedNames.join("、");
    const summary = archivedNames.length > 2 ? `${archivedNames.slice(0, 2).join("、")}等${archivedNames.length}个部门` : fullText;
    return <Tooltip title={archivedNames.length > 2 ? fullText : undefined}><span className="department-scope-summary">{summary}</span></Tooltip>;
  }
  if (!names.length) return <span>全部</span>;
  const fullText = names.join("、");
  const summary = names.length > 2 ? `${names.slice(0, 2).join("、")}等${names.length}个部门` : fullText;
  return (
    <Tooltip title={names.length > 2 ? fullText : undefined}>
      <span className="department-scope-summary">{summary}</span>
    </Tooltip>
  );
}

function PersonRulesTab({ config, refresh }: { config: EvaluationConfig; refresh: (text?: string) => Promise<void> }) {
  const [optionIds, setOptionIds] = useState(config.person_option_ids);
  const [editingRule, setEditingRule] = useState<any | null>(null);
  const [ruleDrawerOpen, setRuleDrawerOpen] = useState(false);
  const [reviewerUsers, setReviewerUsers] = useState<ReviewerUser[]>([]);
  const [reviewerUsersLoading, setReviewerUsersLoading] = useState(false);
  const [ruleSaving, setRuleSaving] = useState(false);
  const [ruleForm] = Form.useForm();
  const [limitForm] = Form.useForm();
  const { message, modal } = AntApp.useApp();
  const disabled = config.evaluation.archived;
  const scopeType = Form.useWatch("scope_type", ruleForm);
  const reviewerPositionId = Form.useWatch("reviewer_position_id", ruleForm);
  const selectedDepartmentIds = Form.useWatch("target_department_ids", ruleForm) || [];

  const departmentNames = useMemo(
    () => new Map(config.departments.map((department) => [department.id, department.name])),
    [config.departments]
  );

  const loadReviewerUsers = async (positionId?: number) => {
    if (!positionId) {
      setReviewerUsers([]);
      return;
    }
    setReviewerUsersLoading(true);
    try {
      setReviewerUsers(await masterDataApi.reviewerUsers(positionId));
    } catch {
      setReviewerUsers([]);
      message.error("评价人列表加载失败，请重试。");
    } finally {
      setReviewerUsersLoading(false);
    }
  };

  const openNewRule = () => {
    setEditingRule(null);
    setReviewerUsers([]);
    ruleForm.resetFields();
    ruleForm.setFieldsValue({ scope_type: "selected_departments", target_department_ids: [], weight: 1 });
    setRuleDrawerOpen(true);
  };

  const openRuleEditor = (rule: any) => {
    setEditingRule(rule);
    ruleForm.setFieldsValue(rule);
    setRuleDrawerOpen(true);
    void loadReviewerUsers(rule.reviewer_position_id);
  };

  const closeRuleEditor = () => {
    setRuleDrawerOpen(false);
    setEditingRule(null);
    setReviewerUsers([]);
    ruleForm.resetFields();
  };

  const saveRule = async (values: any) => {
    const payload = {
      ...values,
      reviewer_user_id: values.reviewer_user_id || null,
      target_department_ids: values.scope_type === "same_department" ? [] : values.target_department_ids
    };
    setRuleSaving(true);
    try {
      const result = editingRule
        ? await evaluationsApi.updatePersonRule(config.evaluation.id, editingRule.id, payload)
        : await evaluationsApi.createPersonRule(config.evaluation.id, payload);
      closeRuleEditor();
      await refresh(result.message);
    } finally {
      setRuleSaving(false);
    }
  };

  return (
    <Space direction="vertical" size={18} style={{ width: "100%" }}>
      <Card title="人员评分选项">
        <Space direction="vertical" style={{ width: "100%" }}>
          <OptionCheckboxes disabled={disabled} options={config.score_options} value={optionIds} onChange={setOptionIds} />
          <Button disabled={disabled} type="primary" onClick={async () => { const result = await evaluationsApi.savePersonOptions(config.evaluation.id, optionIds); await refresh(result.message); }}>保存人员评分选项</Button>
        </Space>
      </Card>
      <Card title="人员评分限制">
        <Form form={limitForm} layout="inline" disabled={disabled} onFinish={async (values) => { const result = await evaluationsApi.savePersonLimit(config.evaluation.id, values); limitForm.resetFields(); await refresh(result.message); }}>
          <Form.Item name="target_position_id" rules={[{ required: true, message: "请选择被评职位。" }]}><Select placeholder="被评职位" style={{ width: 180 }} options={config.positions.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
          <Form.Item name="score_option_id" rules={[{ required: true, message: "请选择评分项。" }]}><Select placeholder="评分项" style={{ width: 180 }} options={config.score_options.map((o) => ({ value: o.id, label: o.name }))} /></Form.Item>
          <Form.Item name="max_people"><InputNumber min={0} placeholder="最多人数" /></Form.Item>
          <Button type="primary" htmlType="submit">保存限制</Button>
        </Form>
        <Table size="small" rowKey="id" dataSource={config.person_limits} pagination={tablePagination()} columns={[
          { title: "被评职位", dataIndex: "target_position_name" },
          { title: "评分项", dataIndex: "score_option_name" },
          { title: "最多人数", dataIndex: "max_people" },
          { title: "操作", render: (_, row) => <Button danger size="small" disabled={disabled} onClick={() => confirmDeletion(modal, { title: "删除限制", action: () => evaluationsApi.deletePersonLimit(config.evaluation.id, row.id), onSuccess: (result) => refresh(result.message) })}>删除</Button> }
        ]} />
      </Card>
      <Card title="人员考核规则" extra={<Button type="primary" disabled={disabled} onClick={openNewRule}>新增人员规则</Button>}>
        <Table size="small" rowKey="id" dataSource={config.person_rules} pagination={tablePagination()} columns={[
          { title: "评分人职位", dataIndex: "reviewer_position_name" },
          { title: "指定评价人", dataIndex: "reviewer_user_name", render: (v) => v || "-" },
          { title: "被评职位", dataIndex: "target_position_name" },
          { title: "范围", width: 280, render: (_, row) => <DepartmentScopeSummary rule={row} departmentNames={departmentNames} /> },
          { title: "分组", dataIndex: "score_group", render: (v) => v || "-" },
          { title: "权重", dataIndex: "weight" },
          { title: "操作", render: (_, row) => <Space><Button size="small" disabled={disabled} onClick={() => openRuleEditor(row)}>编辑</Button><Button danger size="small" disabled={disabled} onClick={() => confirmDeletion(modal, { title: "删除人员规则", action: () => evaluationsApi.deletePersonRule(config.evaluation.id, row.id), onSuccess: (result) => refresh(result.message) })}>删除</Button></Space> }
        ]} />
      </Card>
      <Drawer
        className="person-rule-drawer"
        title={editingRule ? "编辑人员规则" : "新增人员规则"}
        open={ruleDrawerOpen}
        onClose={closeRuleEditor}
        width="min(720px, 96vw)"
        destroyOnClose
        footer={
          <div className="rule-drawer-footer">
            <Button onClick={closeRuleEditor}>取消</Button>
            <Button type="primary" htmlType="submit" form="person-rule-form" loading={ruleSaving}>{editingRule ? "保存规则" : "新增规则"}</Button>
          </div>
        }
      >
        <Form id="person-rule-form" form={ruleForm} layout="vertical" disabled={disabled} onFinish={saveRule}>
          <section className="rule-form-section" aria-labelledby="reviewer-section-title">
            <h3 id="reviewer-section-title">评价人</h3>
            <p>先选择评分人职位，可按需指定该职位下的某一位评价人。</p>
            <div className="rule-form-grid">
              <Form.Item name="reviewer_position_id" label="评分人职位" rules={[{ required: true, message: "请选择评分人职位。" }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="请选择评分人职位"
                  options={config.positions.map((position) => ({ value: position.id, label: position.name }))}
                  onChange={(positionId) => {
                    ruleForm.setFieldValue("reviewer_user_id", undefined);
                    void loadReviewerUsers(positionId);
                  }}
                />
              </Form.Item>
              <Form.Item name="reviewer_user_id" label="指定评价人" extra={reviewerPositionId ? "留空表示该职位下所有启用人员。" : "请先选择评分人职位。"}>
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  loading={reviewerUsersLoading}
                  disabled={!reviewerPositionId}
                  placeholder={reviewerPositionId ? "可选，指定一位评价人" : "请先选择职位"}
                  notFoundContent={reviewerUsersLoading ? "正在加载..." : "该职位暂无可选人员"}
                  options={reviewerUsers.map((reviewer) => ({
                    value: reviewer.id,
                    label: reviewer.department_name ? `${reviewer.name} · ${reviewer.department_name}` : reviewer.name
                  }))}
                />
              </Form.Item>
            </div>
          </section>

          <section className="rule-form-section" aria-labelledby="target-section-title">
            <h3 id="target-section-title">被评对象</h3>
            <p>设置被评人员职位，并确定评价人与被评对象的部门关系。</p>
            <div className="rule-form-grid">
              <Form.Item name="target_position_id" label="被评人员职位" rules={[{ required: true, message: "请选择被评人员职位。" }]}>
                <Select showSearch optionFilterProp="label" placeholder="请选择被评人员职位" options={config.positions.map((position) => ({ value: position.id, label: position.name }))} />
              </Form.Item>
              <Form.Item name="scope_type" label="评价范围" rules={[{ required: true }]}>
                <Radio.Group
                  className="scope-switch"
                  optionType="button"
                  buttonStyle="solid"
                  options={[{ value: "selected_departments", label: "指定部门" }, { value: "same_department", label: "同部门" }]}
                  onChange={(event) => {
                    if (event.target.value === "same_department") ruleForm.setFieldValue("target_department_ids", []);
                  }}
                />
              </Form.Item>
            </div>
            {scopeType === "selected_departments" ? (
              <Form.Item name="target_department_ids" label="被评部门范围" rules={[{ required: true, message: "请选择被评部门范围。" }]} extra={selectedDepartmentIds.length ? `已选择 ${selectedDepartmentIds.length} 个部门` : "父子部门独立选择，父级右侧可快速选择全部子级。"}>
                <DepartmentMultiTreeSelect departments={config.departments} placeholder="搜索或选择被评部门" />
              </Form.Item>
            ) : (
              <div className="same-department-note">系统将按评价人所在部门自动匹配同部门的被评人员。</div>
            )}
          </section>

          <section className="rule-form-section" aria-labelledby="statistics-section-title">
            <h3 id="statistics-section-title">统计设置</h3>
            <div className="rule-form-grid">
              <Form.Item name="score_group" label="统计分组"><Input placeholder="可选，例如：领导评价" /></Form.Item>
              <Form.Item name="weight" label="权重" rules={[{ required: true, message: "请输入权重。" }]}><InputNumber min={0} max={1} step={0.01} precision={2} style={{ width: "100%" }} /></Form.Item>
            </div>
          </section>
        </Form>
      </Drawer>
    </Space>
  );
}

function DepartmentRulesTab({ config, refresh }: { config: EvaluationConfig; refresh: (text?: string) => Promise<void> }) {
  const [optionIds, setOptionIds] = useState(config.department_option_ids);
  const [editingRule, setEditingRule] = useState<any | null>(null);
  const [ruleForm] = Form.useForm();
  const [limitForm] = Form.useForm();
  const { modal } = AntApp.useApp();
  const disabled = config.evaluation.archived;
  return (
    <Space direction="vertical" size={18} style={{ width: "100%" }}>
      <Card title="部门评分选项">
        <Space direction="vertical" style={{ width: "100%" }}>
          <OptionCheckboxes disabled={disabled} options={config.score_options} value={optionIds} onChange={setOptionIds} />
          <Button disabled={disabled} type="primary" onClick={async () => { const result = await evaluationsApi.saveDepartmentOptions(config.evaluation.id, optionIds); await refresh(result.message); }}>保存部门评分选项</Button>
        </Space>
      </Card>
      <Card title="部门评分限制">
        <Form form={limitForm} layout="inline" disabled={disabled} onFinish={async (values) => { const result = await evaluationsApi.saveDepartmentLimit(config.evaluation.id, values); limitForm.resetFields(); await refresh(result.message); }}>
          <Form.Item name="score_option_id" rules={[{ required: true, message: "请选择评分项。" }]}><Select placeholder="评分项" style={{ width: 180 }} options={config.score_options.map((o) => ({ value: o.id, label: o.name }))} /></Form.Item>
          <Form.Item name="max_count"><InputNumber min={0} placeholder="最多数量" /></Form.Item>
          <Button type="primary" htmlType="submit">保存限制</Button>
        </Form>
        <Table size="small" rowKey="id" dataSource={config.department_limits} pagination={tablePagination()} columns={[
          { title: "评分项", dataIndex: "score_option_name" },
          { title: "最多数量", dataIndex: "max_count" },
          { title: "操作", render: (_, row) => <Button danger size="small" disabled={disabled} onClick={() => confirmDeletion(modal, { title: "删除限制", action: () => evaluationsApi.deleteDepartmentLimit(config.evaluation.id, row.id), onSuccess: (result) => refresh(result.message) })}>删除</Button> }
        ]} />
      </Card>
      <Card title="部门考核规则">
        <Form form={ruleForm} layout="vertical" disabled={disabled} onFinish={async (values) => {
          const payload = { ...values, target_department_ids: values.target_department_ids || (values.target_department_id ? [values.target_department_id] : []) };
          const result = editingRule
            ? await evaluationsApi.updateDepartmentRule(config.evaluation.id, editingRule.id, payload)
            : await evaluationsApi.createDepartmentRule(config.evaluation.id, payload);
          setEditingRule(null);
          ruleForm.resetFields();
          await refresh(result.message);
        }}>
          <div className="form-grid">
            <Form.Item name="reviewer_position_id" label="评分人职位" rules={[{ required: true, message: "请选择评分人职位。" }]}><Select options={config.positions.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
            <Form.Item name="target_department_ids" label="被评部门" rules={[{ required: true, message: "请选择被评部门。" }]}>
              <DepartmentMultiTreeSelect departments={config.departments} placeholder="搜索或选择被评部门" />
            </Form.Item>
            <Form.Item name="weight" label="权重" rules={[{ required: true, message: "请输入权重。" }]}><InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} /></Form.Item>
          </div>
          <Space>
            <Button type="primary" htmlType="submit">{editingRule ? "保存部门规则" : "新增部门规则"}</Button>
            {editingRule ? <Button onClick={() => { setEditingRule(null); ruleForm.resetFields(); }}>取消编辑</Button> : null}
          </Space>
        </Form>
        <Table size="small" rowKey="id" dataSource={config.department_rules} pagination={tablePagination()} columns={[
          { title: "评分人职位", dataIndex: "reviewer_position_name" },
          { title: "被评部门", dataIndex: "target_department_name" },
          { title: "权重", dataIndex: "weight" },
          { title: "操作", render: (_, row) => <Space><Button size="small" disabled={disabled} onClick={() => { setEditingRule(row); ruleForm.setFieldsValue({ ...row, target_department_ids: [row.target_department_id] }); }}>编辑</Button><Button danger size="small" disabled={disabled} onClick={() => confirmDeletion(modal, { title: "删除部门规则", action: () => evaluationsApi.deleteDepartmentRule(config.evaluation.id, row.id), onSuccess: (result) => refresh(result.message) })}>删除</Button></Space> }
        ]} />
      </Card>
    </Space>
  );
}

function DepartmentShareTab({ config, refresh }: { config: EvaluationConfig; refresh: (text?: string) => Promise<void> }) {
  const [shareForm] = Form.useForm();
  const [manualForm] = Form.useForm();
  const { modal } = AntApp.useApp();
  const disabled = config.evaluation.archived;
  const departmentTree = useMemo(() => buildDepartmentTree(config.departments), [config.departments]);
  return (
    <Space direction="vertical" size={18} style={{ width: "100%" }}>
      <Card title="部门得分占比规则">
        <Form form={shareForm} layout="inline" disabled={disabled} onFinish={async (values) => { const result = await evaluationsApi.saveShareRule(config.evaluation.id, values); shareForm.resetFields(); await refresh(result.message); }}>
          <Form.Item name="target_position_id" rules={[{ required: true, message: "请选择适用职位。" }]}><Select placeholder="适用职位" style={{ width: 200 }} options={config.positions.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
          <Form.Item name="weight" rules={[{ required: true, message: "请输入权重。" }]}><InputNumber min={0} max={1} step={0.01} placeholder="权重" /></Form.Item>
          <Button type="primary" htmlType="submit">保存占比</Button>
        </Form>
        <Table size="small" rowKey="id" dataSource={config.share_rules} pagination={tablePagination()} columns={[
          { title: "适用职位", dataIndex: "target_position_name" },
          { title: "权重", dataIndex: "weight" },
          { title: "操作", render: (_, row) => <Button danger size="small" disabled={disabled} onClick={() => confirmDeletion(modal, { title: "删除占比规则", action: () => evaluationsApi.deleteShareRule(config.evaluation.id, row.id), onSuccess: (result) => refresh(result.message) })}>删除</Button> }
        ]} />
      </Card>
      <Card title="手动部门得分">
        <Form form={manualForm} layout="inline" disabled={disabled} onFinish={async (values) => { const result = await evaluationsApi.saveManualScore(config.evaluation.id, values); manualForm.resetFields(); await refresh(result.message); }}>
          <Form.Item name="department_id" rules={[{ required: true, message: "请选择部门。" }]}><TreeSelect placeholder="请选择部门" style={{ width: 220 }} showSearch treeNodeFilterProp="title" treeData={departmentTree} treeDefaultExpandAll /></Form.Item>
          <Form.Item name="score" rules={[{ required: true, message: "请输入得分。" }]}><InputNumber min={0} max={100} placeholder="得分" /></Form.Item>
          <Button type="primary" htmlType="submit">保存得分</Button>
        </Form>
        <Table size="small" rowKey="id" dataSource={config.manual_scores} pagination={tablePagination()} columns={[
          { title: "部门", dataIndex: "department_name" },
          { title: "手动得分", dataIndex: "score" },
          { title: "操作", render: (_, row) => <Button danger size="small" disabled={disabled} onClick={() => confirmDeletion(modal, { title: "删除手动得分", action: () => evaluationsApi.deleteManualScore(config.evaluation.id, row.id), onSuccess: (result) => refresh(result.message) })}>删除</Button> }
        ]} />
      </Card>
    </Space>
  );
}

function ReviewSubmissionsTab({ evaluationId }: { evaluationId: number }) {
  const [data, setData] = useState<any>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState<ReviewSubmissionDetailResponse | null>(null);
  const [detailReviewerId, setDetailReviewerId] = useState<number | null>(null);
  const [detailPassword, setDetailPassword] = useState("");
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const { message } = AntApp.useApp();
  const load = async (nextPage = page) => {
    setLoading(true);
    try {
      setData(await evaluationsApi.reviewSubmissions(evaluationId, nextPage));
      setPage(nextPage);
    } finally {
      setLoading(false);
    }
  };
  const loadDetails = async (reviewerId: number, password: string, page = 1) => {
    setDetailReviewerId(reviewerId);
    setDetailLoading(true);
    try {
      setDetailData(await evaluationsApi.reviewSubmissionDetails(evaluationId, reviewerId, password, page));
    } finally {
      setDetailLoading(false);
    }
  };
  const requestDetails = (reviewerId: number) => {
    setDetailReviewerId(reviewerId);
    setDetailData(null);
    setDetailPassword("");
    setPasswordOpen(true);
  };
  const verifyDetailPassword = async () => {
    if (!detailReviewerId || !detailPassword) {
      message.warning("请输入查看密码。");
      return;
    }
    setPasswordLoading(true);
    try {
      await loadDetails(detailReviewerId, detailPassword);
      setPasswordOpen(false);
      setDetailOpen(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "密码验证失败。");
    } finally {
      setPasswordLoading(false);
    }
  };
  useEffect(() => { setPage(1); void load(1); }, [evaluationId]);
  return (
    <>
      <Table<any>
        loading={loading}
        rowKey="reviewer_id"
        dataSource={data?.items || []}
        pagination={data?.pagination ? {
          current: data.pagination.page,
          pageSize: data.pagination.page_size,
          total: data.pagination.total,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage) => void load(nextPage)
        } : false}
        columns={[
          { title: "评分人", dataIndex: "reviewer_name" },
          { title: "部门", dataIndex: "department_name" },
          { title: "职位", dataIndex: "position_name" },
          { title: "进度", render: (_: unknown, row: any) => `${row.submitted_count} / ${row.task_count}` },
          { title: "状态", dataIndex: "status_label" },
          {
            title: "操作",
            render: (_: unknown, row: any) => (
              <Space wrap>
                <Button size="small" onClick={() => requestDetails(row.reviewer_id)}>查看评分详情</Button>
                <Button size="small" disabled={!row.can_reopen} onClick={async () => { const result = await evaluationsApi.reopenSubmission(evaluationId, row.reviewer_id); message.success(result.message); await load(); }}>允许修改</Button>
                <Button size="small" disabled={!row.can_cancel} onClick={async () => { const result = await evaluationsApi.cancelSubmission(evaluationId, row.reviewer_id); message.success(result.message); await load(); }}>取消允许</Button>
              </Space>
            )
          }
        ]}
      />
      <Modal
        title="验证查看密码"
        open={passwordOpen}
        okText="验证并查看"
        cancelText="取消"
        confirmLoading={passwordLoading}
        onOk={() => void verifyDetailPassword()}
        onCancel={() => { setPasswordOpen(false); setDetailPassword(""); }}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">评分明细属于敏感信息，请输入专用查看密码。</Typography.Paragraph>
        <Input.Password
          autoFocus
          value={detailPassword}
          placeholder="请输入查看密码"
          onChange={(event) => setDetailPassword(event.target.value)}
          onPressEnter={() => void verifyDetailPassword()}
        />
      </Modal>
      <Drawer
        title="评分详情"
        width={860}
        open={detailOpen}
        onClose={() => { setDetailOpen(false); setDetailPassword(""); setDetailData(null); }}
        destroyOnClose
      >
        {detailData ? (
          <>
            <Space size={24} wrap style={{ marginBottom: 20 }}>
              <Typography.Text strong>{detailData.reviewer.full_name}</Typography.Text>
              <Typography.Text type="secondary">{detailData.reviewer.department_name || "未分配部门"}</Typography.Text>
              <Typography.Text type="secondary">{detailData.reviewer.position_name || "未分配职位"}</Typography.Text>
              <Typography.Text type="secondary">已提交 {detailData.pagination.total} 项</Typography.Text>
            </Space>
            <Table
              size="small"
              loading={detailLoading}
              rowKey="id"
              dataSource={detailData.items}
              pagination={{
                current: detailData.pagination.page,
                pageSize: detailData.pagination.page_size,
                total: detailData.pagination.total,
                showSizeChanger: false,
                showTotal: (total) => `共 ${total} 条`,
                onChange: (page) => detailReviewerId && void loadDetails(detailReviewerId, detailPassword, page)
              }}
              columns={[
                { title: "被评对象", dataIndex: "target_name" },
                { title: "类型", dataIndex: "task_type", width: 80, render: (value) => value === "person" ? "人员" : "部门" },
                { title: "评分项", dataIndex: "option_name", width: 110 },
                { title: "分值", dataIndex: "score_value", width: 80 },
                { title: "权重", dataIndex: "weight", width: 80 },
                { title: "加权分", dataIndex: "weighted_score", width: 90, render: (value) => Number(value).toFixed(2) },
                { title: "提交时间", dataIndex: "created_at", width: 170, render: (value) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-" }
              ]}
            />
          </>
        ) : <Card loading={detailLoading} bordered={false} />}
      </Drawer>
    </>
  );
}

function StatsTab({ evaluationId, archived }: { evaluationId: number; archived: boolean }) {
  const [data, setData] = useState<EvaluationStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [peoplePage, setPeoplePage] = useState(1);
  const [exporting, setExporting] = useState<"people" | "departments" | null>(null);
  const { message } = AntApp.useApp();
  const load = async (nextPeoplePage = peoplePage) => {
    setLoading(true);
    try {
      setData(archived ? await evaluationsApi.details(evaluationId, nextPeoplePage) : await evaluationsApi.liveStats(evaluationId, nextPeoplePage));
      setPeoplePage(nextPeoplePage);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { setPeoplePage(1); void load(1); }, [evaluationId, archived]);
  if (!data) return <Card loading={loading} />;
  const people = data.people;
  const exportScores = async (type: "people" | "departments") => {
    setExporting(type);
    try {
      if (type === "people") await evaluationsApi.exportPersonScores(evaluationId, data.evaluation.name);
      else await evaluationsApi.exportDepartmentScores(evaluationId, data.evaluation.name);
      message.success("得分表已导出。");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "导出失败。");
    } finally {
      setExporting(null);
    }
  };
  return (
    <Space direction="vertical" size={18} style={{ width: "100%" }}>
      <Card title={archived ? "人员得分" : "人员当前得分"} extra={archived ? <Button icon={<DownloadOutlined />} loading={exporting === "people"} onClick={() => void exportScores("people")}>导出得分</Button> : null}>
        <Table<EvaluationScorePerson> loading={loading} size="small" rowKey={(row) => `${row.id || row.user_id || row.full_name}`} dataSource={people} pagination={data.people_pagination ? {
          current: data.people_pagination.page,
          pageSize: data.people_pagination.page_size,
          total: data.people_pagination.total,
          showSizeChanger: false,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page) => void load(page)
        } : tablePagination()} columns={[
          { title: "姓名", dataIndex: "full_name" },
          { title: "部门", dataIndex: "department_name" },
          { title: "职位", dataIndex: "position_name" },
          { title: "得分", dataIndex: "final_score", render: (value) => value == null ? "-" : Number(value).toFixed(2) }
        ]} />
      </Card>
      <Card title={archived ? "部门得分" : "部门当前得分"} extra={archived ? <Button icon={<DownloadOutlined />} loading={exporting === "departments"} onClick={() => void exportScores("departments")}>导出得分</Button> : null}>
        <Table<EvaluationScoreDepartment> size="small" rowKey={(row) => `${row.id || row.department_id || row.department_name}`} dataSource={data.departments} pagination={tablePagination()} columns={[
          { title: "部门", dataIndex: "department_name" },
          { title: "得分", dataIndex: "final_score", render: (value) => value == null ? "-" : Number(value).toFixed(2) }
        ]} />
      </Card>
    </Space>
  );
}

type RuleSnapshot = NonNullable<EvaluationStatsResponse["snapshots"]>[number];

function snapshotColumns(type: string): ColumnsType<Record<string, unknown>> {
  const text = (title: string, dataIndex: string) => ({ title, dataIndex, render: (value: unknown) => value == null || value === "" ? "-" : String(value) });
  const weight = { title: "权重", dataIndex: "weight", width: 90, render: (value: unknown) => value == null ? "-" : Number(value).toFixed(2) };
  const columns: Record<string, ColumnsType<Record<string, unknown>>> = {
    person_options: [text("评分项", "name"), text("分值", "value")],
    department_options: [text("评分项", "name"), text("分值", "value")],
    person_limits: [text("被评职位", "target_position"), text("评分项", "option"), text("最多人数", "max_people")],
    department_limits: [text("评分项", "option"), text("最多数量", "max_count")],
    person_rules: [
      text("评分人职位", "reviewer_position"),
      text("指定评价人", "reviewer_user"),
      text("被评职位", "target_position"),
      { title: "范围", dataIndex: "target_departments", render: (value: unknown, row) => row.scope_type === "same_department" ? "同部门" : Array.isArray(value) ? value.join("、") || "-" : "-" },
      text("分组", "score_group"),
      weight
    ],
    department_rules: [text("评分人职位", "reviewer_position"), text("被评部门", "target_department"), weight],
    department_share_rules: [text("适用职位", "target_position"), weight],
    manual_department_scores: [text("部门", "department"), text("手动得分", "score")]
  };
  return columns[type] || [text("配置", "name"), text("值", "value")];
}

function ArchivedRulesSnapshot({ snapshots }: { snapshots: RuleSnapshot[] }) {
  return (
    <Card title="归档规则快照" className="rules-snapshot-card">
      <div className="rules-snapshot-list">
        {snapshots.map((snapshot) => (
          <section className="rules-snapshot-section" key={snapshot.id}>
            <div className="rules-snapshot-heading">
              <Typography.Title level={4}>{snapshot.title}</Typography.Title>
              <span>{snapshot.payload.length} 条</span>
            </div>
            <Table<Record<string, unknown>>
              size="small"
              rowKey={(_, index) => `${snapshot.id}-${index}`}
              dataSource={snapshot.payload}
              columns={snapshotColumns(snapshot.snapshot_type)}
              pagination={snapshot.payload.length > 10 ? tablePagination() : false}
              locale={{ emptyText: "暂无数据" }}
            />
          </section>
        ))}
      </div>
    </Card>
  );
}

function AuditPreview() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    evaluationsApi.audit().then(setData).catch(() => setData({ items: [] }));
  }, []);
  return (
    <Table<any>
      size="small"
      rowKey="id"
      dataSource={data?.items || []}
      pagination={tablePagination()}
      columns={[
        { title: "考核", render: (_: unknown, row: any) => `${row.evaluation_name}（${row.evaluation_year}）` },
        { title: "操作人", dataIndex: "actor_name" },
        { title: "动作", dataIndex: "action" },
        { title: "详情", dataIndex: "detail" },
        { title: "时间", dataIndex: "created_at" }
      ]}
    />
  );
}
