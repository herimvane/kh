import { ArrowLeftOutlined } from "@ant-design/icons";
import { Alert, App as AntApp, Button, Card, Progress, Radio, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { evaluationsApi, type AppEvaluation } from "../api/evaluations";


export default function EvaluationAppPage({ evaluationId, onBack }: { evaluationId: number; onBack: () => void }) {
  const { message } = AntApp.useApp();
  const [data, setData] = useState<AppEvaluation | null>(null);
  const [choices, setChoices] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const result = await evaluationsApi.appEvaluation(evaluationId);
      setData(result);
      const initialChoices: Record<number, number> = {};
      Object.entries(result.current_choices || {}).forEach(([taskId, optionId]) => {
        initialChoices[Number(taskId)] = optionId;
      });
      setChoices(initialChoices);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => void load(), [evaluationId]);

  const tasks = useMemo(() => data?.task_groups.flatMap((group) => group.tasks) || [], [data]);
  const completed = tasks.filter((task) => choices[task.id]).length;
  const remaining = tasks.length - completed;
  const progressPercent = tasks.length ? Math.round((completed / tasks.length) * 100) : 0;
  const isRevising = Boolean(data?.reopened);
  const readOnly = Boolean(data?.submitted && !data.reopened);
  const scoreTone = (name: string) => {
    if (name.includes("不称职")) return "danger";
    if (name.includes("基本")) return "warning";
    if (name.includes("优秀")) return "primary";
    return "success";
  };
  const limitKey = (task: AppEvaluation["task_groups"][number]["tasks"][number], optionId: number) =>
    `${task.task_type}:${task.limit_key_rule}:${optionId}`;
  const optionNames = useMemo(() => {
    const names: Record<number, string> = {};
    data?.task_groups.forEach((group) => group.options.forEach((option) => { names[option.id] = option.name; }));
    return names;
  }, [data]);
  const countSelections = (values: Record<number, number>) => {
    const counts: Record<string, number> = {};
    tasks.forEach((task) => {
      const optionId = values[task.id];
      if (!optionId) return;
      const key = limitKey(task, optionId);
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  };
  const selectionCounts = useMemo(() => countSelections(choices), [choices, tasks]);
  const findLimitViolations = (values: Record<number, number>) => {
    if (!data) return [];
    const counts = countSelections(values);
    return Object.entries(data.limit_map).flatMap(([key, limit]) => {
      const count = counts[key] || 0;
      if (count <= limit) return [];
      const keyParts = key.split(":");
      const optionId = Number(keyParts[keyParts.length - 1]);
      return [{ key, optionId, optionName: optionNames[optionId] || "该评分项", count, limit, excess: count - limit }];
    });
  };
  const limitViolations = useMemo(() => findLimitViolations(choices), [choices, data, optionNames, tasks]);
  const submitDisabled = !data || readOnly || tasks.length === 0 || completed < tasks.length || limitViolations.length > 0;
  const groupLimitStats = (group: AppEvaluation["task_groups"][number]) => {
    if (!data || !group.tasks.length) return [];
    const referenceTask = group.tasks[0];
    return group.options.flatMap((option) => {
      const key = limitKey(referenceTask, option.id);
      const limit = data.limit_map[key];
      if (limit === undefined) return [];
      const count = selectionCounts[key] || 0;
      return [{ key, name: option.name, count, limit, exceeded: count > limit }];
    });
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const result = await evaluationsApi.submitAppEvaluation(evaluationId, choices);
      message.success(result.message);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "评分提交失败，请检查后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  const navigateToGroup = (index: number) => {
    const target = document.getElementById(`evaluation-group-${index}`);
    if (!target) return;
    target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  };

  if (loading || !data) return <Card loading />;
  if (!data.evaluation) return <Alert type="info" message="当前没有开放中的考核。" showIcon />;

  return (
    <div className="evaluation-page">
      <Button className="evaluation-back" type="link" icon={<ArrowLeftOutlined />} onClick={onBack}>返回我的考核</Button>
      <section className="evaluation-overview">
        <div className="evaluation-overview-main">
          <div>
            <Typography.Title level={2}>{data.evaluation.name}评分</Typography.Title>
            <Typography.Text type="secondary">请对每位被评对象完成评价</Typography.Text>
          </div>
          {isRevising
            ? <Tag color="warning">待重新提交</Tag>
            : data.submitted
              ? <Tag color="success">已提交</Tag>
              : <Tag color={remaining ? "processing" : "success"}>{remaining ? `待评 ${remaining} 项` : "已填写"}</Tag>}
        </div>
        <div className="evaluation-progress-line">
          <Progress percent={progressPercent} showInfo={false} status={isRevising ? "active" : completed === tasks.length ? "success" : "active"} />
          <span>已填写 {completed} / {tasks.length}</span>
        </div>
      </section>
      {data.task_groups.length > 1 ? (
        <nav className="evaluation-group-nav" aria-label="评分分组快捷导航">
          <span>快速定位</span>
          <div>
            {data.task_groups.map((group, index) => (
              <Button key={`${group.type}-${group.title}`} type="text" onClick={() => navigateToGroup(index)}>
                {group.title.replace(/^被评对象[：:]\s*/, "")}
              </Button>
            ))}
          </div>
        </nav>
      ) : null}
      {data.task_groups.map((group, groupIndex) => {
        const limitStats = groupLimitStats(group);
        return (
          <Card
            id={`evaluation-group-${groupIndex}`}
            tabIndex={-1}
            key={`${group.type}-${group.title}`}
            className="task-section"
            title={<div className="task-section-title"><strong>{group.title}</strong><span>{group.tasks.length} {group.type === "person" ? "人" : "个"}</span>{limitStats.map((stat) => <em className={stat.exceeded ? "limit-exceeded" : ""} key={stat.key}>{stat.name} {stat.count} / {stat.limit}</em>)}</div>}
            extra={(
              <Space className="quick-fill" wrap size={6}>
                <span>批量设置</span>
                {group.options.map((option) => (
                  <Button
                    key={option.id}
                    size="small"
                    disabled={readOnly}
                    className={`quick-score quick-score-${scoreTone(option.name)}`}
                    onClick={() => {
                      const next = { ...choices };
                      group.tasks.forEach((task) => { next[task.id] = option.id; });
                      const violations = findLimitViolations(next);
                      if (violations.length) {
                        const violation = violations[0];
                        message.warning(`${violation.optionName}最多选择 ${violation.limit} ${group.type === "person" ? "人" : "个部门"}，无法批量设置。`);
                        return;
                      }
                      setChoices(next);
                    }}
                  >
                    {option.name}
                  </Button>
                ))}
              </Space>
            )}
          >
            <div className="task-list">
              {group.tasks.map((task) => (
                <div className="task-row" key={task.id}>
                  <div className="task-person">
                    <strong>{task.target_name}</strong>
                    {task.department_name && task.department_name !== task.target_name ? <><span>·</span><span>{task.department_name}</span></> : null}
                  </div>
                  <Radio.Group className="score-selector" disabled={readOnly} value={choices[task.id]} onChange={(event) => setChoices({ ...choices, [task.id]: event.target.value })}>
                    {group.options.map((option) => {
                      const key = limitKey(task, option.id);
                      const limit = data.limit_map[key];
                      const full = limit !== undefined && (selectionCounts[key] || 0) >= limit && choices[task.id] !== option.id;
                      return <Radio.Button title={full ? `${option.name}名额已满，最多选择 ${limit} ${group.type === "person" ? "人" : "个部门"}` : undefined} disabled={readOnly || full} className={`score-option score-option-${scoreTone(option.name)}`} key={option.id} value={option.id}>{option.name}</Radio.Button>;
                    })}
                  </Radio.Group>
                </div>
              ))}
            </div>
          </Card>
        );
      })}
      <div className="submit-bar">
        <div className="submit-summary">
          <strong className={limitViolations.length ? "submit-error" : ""}>{readOnly ? "评分已提交" : limitViolations.length ? `有 ${limitViolations.length} 项评分数量超出限制` : remaining ? `还有 ${remaining} 项未填写` : isRevising ? "等待重新提交" : "已完成全部评分"}</strong>
          {limitViolations.length ? <span className="submit-error-detail">{limitViolations.map((item) => `${item.optionName}超出 ${item.excess} 人`).join("；")}</span> : null}
          <span>已填写 {completed} / {tasks.length}</span>
        </div>
        <Button type="primary" disabled={submitDisabled} loading={submitting} onClick={submit}>{readOnly ? "评分已提交" : isRevising ? "重新提交评分" : "提交评分"}</Button>
      </div>
    </div>
  );
}
