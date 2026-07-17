import { ArrowRightOutlined, EyeOutlined, HistoryOutlined } from "@ant-design/icons";
import { App as AntApp, Button, Card, Empty, Modal, Progress, Space, Table, Tabs, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { evaluationsApi, type MyEvaluation, type MySubmission } from "../api/evaluations";
import { formatDateTime } from "../utils/dateTime";

type Props = {
  onEnter: (evaluationId: number) => void;
};

export default function MyEvaluationsPage({ onEnter }: Props) {
  const { message } = AntApp.useApp();
  const [items, setItems] = useState<MyEvaluation[]>([]);
  const [loading, setLoading] = useState(true);
  const [submission, setSubmission] = useState<MySubmission | null>(null);
  const [submissionOpen, setSubmissionOpen] = useState(false);
  const [submissionLoading, setSubmissionLoading] = useState(false);

  useEffect(() => {
    evaluationsApi.myEvaluations()
      .then((result) => setItems(result.items))
      .catch((error) => message.error(error instanceof Error ? error.message : "考核列表加载失败。"))
      .finally(() => setLoading(false));
  }, [message]);

  const groups = useMemo(() => ({
    pending: items.filter((item) => item.status === "pending"),
    submitted: items.filter((item) => item.status === "submitted"),
    history: items.filter((item) => item.status === "history")
  }), [items]);

  const showSubmission = async (item: MyEvaluation) => {
    setSubmissionOpen(true);
    setSubmission(null);
    setSubmissionLoading(true);
    try {
      setSubmission(await evaluationsApi.appSubmission(item.id));
    } catch (error) {
      setSubmissionOpen(false);
      message.error(error instanceof Error ? error.message : "提交结果加载失败。");
    } finally {
      setSubmissionLoading(false);
    }
  };

  const renderList = (rows: MyEvaluation[], emptyText: string) => rows.length ? (
    <div className="my-evaluation-list">
      {rows.map((item) => {
        const percent = item.task_count ? Math.round((item.completed_count / item.task_count) * 100) : 0;
        const canEnter = item.status === "pending" && item.is_open;
        return (
          <Card key={`${item.archived ? "archive" : "live"}-${item.id}`} className="my-evaluation-card">
            <div className="my-evaluation-card-main">
              <div className="my-evaluation-title">
                <Typography.Title level={4}>{item.name}</Typography.Title>
                <Space size={6} wrap>
                  <Tag>{item.year} 年第 {item.sequence} 批</Tag>
                  <Tag color={item.archived ? "default" : item.is_open ? "processing" : "warning"}>
                    {item.archived ? "已归档" : item.is_open ? "进行中" : "未开放"}
                  </Tag>
                </Space>
              </div>
              <Typography.Text type="secondary">发起部门：{item.owner_department_name}</Typography.Text>
              <div className="my-evaluation-progress">
                <Progress percent={percent} showInfo={false} status={item.submitted ? "success" : "active"} />
                <span>{item.completed_count} / {item.task_count}</span>
              </div>
            </div>
            <div className="my-evaluation-actions">
              {item.status === "pending" ? (
                <Button type="primary" disabled={!canEnter} icon={<ArrowRightOutlined />} onClick={() => onEnter(item.id)}>
                  {item.is_open ? "进入评分" : "等待开放"}
                </Button>
              ) : (
                <Button type="link" icon={item.archived ? <HistoryOutlined /> : <EyeOutlined />} onClick={() => void showSubmission(item)}>
                  查看提交结果
                </Button>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />;

  return (
    <div className="my-evaluations-page">
      <section className="my-evaluations-heading">
        <div>
          <Typography.Title level={2}>我的考核</Typography.Title>
          <Typography.Text type="secondary">选择需要处理的考核，或查看自己已经提交的历史记录。</Typography.Text>
        </div>
        <Tag color={groups.pending.some((item) => item.is_open) ? "processing" : "default"}>
          {groups.pending.filter((item) => item.is_open).length} 个待办
        </Tag>
      </section>
      <Card className="my-evaluations-panel" loading={loading}>
        <Tabs items={[
          { key: "pending", label: `待处理 (${groups.pending.length})`, children: renderList(groups.pending, "当前没有待处理考核") },
          { key: "submitted", label: `已提交 (${groups.submitted.length})`, children: renderList(groups.submitted, "暂无已提交考核") },
          { key: "history", label: `历史考核 (${groups.history.length})`, children: renderList(groups.history, "暂无历史考核") }
        ]} />
      </Card>
      <Modal title={submission?.evaluation.name || "提交结果"} open={submissionOpen} footer={null} width={760} onCancel={() => setSubmissionOpen(false)}>
        {submissionLoading ? <Card loading /> : submission ? (
          <>
            <div className="submission-summary">
              <span>共提交 {submission.task_count} 项</span>
              <span>{submission.submitted_at ? `提交时间：${formatDateTime(submission.submitted_at)}` : ""}</span>
            </div>
            <Table
              rowKey="id"
              size="small"
              dataSource={submission.items}
              pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
              columns={[
                { title: "被评对象", dataIndex: "target_name" },
                { title: "类型", dataIndex: "task_type", width: 110, render: (value) => value === "person" ? "人员" : "部门" },
                { title: "评分项", dataIndex: "option_name", width: 140 }
              ]}
            />
          </>
        ) : null}
      </Modal>
    </div>
  );
}
