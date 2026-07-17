import {
  ApartmentOutlined,
  CheckSquareOutlined,
  PieChartOutlined,
  TeamOutlined,
  UserOutlined
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

export default function DashboardPage({ onNavigate }: { onNavigate: (route: "evaluations") => void }) {
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [departmentTotal, setDepartmentTotal] = useState(0);
  const [currentYearTotal, setCurrentYearTotal] = useState(0);
  const [evaluationTotal, setEvaluationTotal] = useState(0);
  const [activeTotal, setActiveTotal] = useState(0);
  const [completedTotal, setCompletedTotal] = useState(0);
  const [allTaskTotal, setAllTaskTotal] = useState(0);
  const [allSubmittedTotal, setAllSubmittedTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    evaluationsApi.dashboard()
      .then((summary) => {
        setEvaluations(summary.latest);
        setUserTotal(summary.user_total);
        setDepartmentTotal(summary.department_total);
        setCurrentYearTotal(summary.current_year_total);
        setEvaluationTotal(summary.evaluation_total);
        setActiveTotal(summary.active_total);
        setCompletedTotal(summary.completed_total);
        setAllTaskTotal(summary.total_tasks);
        setAllSubmittedTotal(summary.submitted_tasks);
      })
      .finally(() => setLoading(false));
  }, []);

  const completionPercent = allTaskTotal ? Math.round((allSubmittedTotal / allTaskTotal) * 100) : 0;
  const latest = [...evaluations]
    .sort((a, b) => b.year - a.year || b.sequence - a.sequence || b.id - a.id)
    .slice(0, 3);
  const latestEvaluation = latest[0] ?? null;
  const latestTotalTasks = latestEvaluation?.total_tasks ?? 0;
  const latestSubmittedTasks = latestEvaluation?.submitted_tasks ?? 0;
  const latestCompletionPercent = latestTotalTasks
    ? Math.round((latestSubmittedTasks / latestTotalTasks) * 100)
    : 0;
  const latestTasksPending = Boolean(latestEvaluation && !latestEvaluation.tasks_generated);
  const donutCircumference = 2 * Math.PI * 72;
  const donutOffset = donutCircumference * (1 - latestCompletionPercent / 100);

  return (
    <div className="dashboard-page">
      <PageTitle title="首页" />
      <div className="metric-grid">
        <MetricCard icon={<TeamOutlined />} tone="blue" title="在岗人数" value={userTotal} suffix="人" delta={`部门 ${departmentTotal} 个`} loading={loading} />
        <MetricCard icon={<CheckSquareOutlined />} tone="green" title="考核计划数" value={evaluationTotal} suffix="个" delta={`本年度 ${currentYearTotal} 个`} loading={loading} />
        <MetricCard icon={<UserOutlined />} tone="orange" title="考核中计划" value={activeTotal} suffix="个" delta={`待提交 ${Math.max(allTaskTotal - allSubmittedTotal, 0)} 项`} loading={loading} />
        <MetricCard icon={<PieChartOutlined />} tone="purple" title="已完成考核" value={completedTotal} suffix="个" delta={`完成率 ${completionPercent}%`} loading={loading} />
      </div>

      <div className="dashboard-main-grid">
        <Card className="panel-card completion-card" title="考核完成情况" extra={<Button size="small">{latestEvaluation?.name ?? "--"}</Button>}>
          <div className="donut-wrap">
            <div
              className={`donut-chart${latestTasksPending ? " is-pending" : ""}`}
            >
              <svg viewBox="0 0 172 172" aria-hidden="true">
                <circle className="donut-ring donut-track" cx="86" cy="86" r="72" />
                {!latestTasksPending ? (
                  <circle
                    className="donut-ring donut-progress"
                    cx="86"
                    cy="86"
                    r="72"
                    strokeDasharray={donutCircumference}
                    strokeDashoffset={donutOffset}
                  />
                ) : null}
              </svg>
              <strong>{latestCompletionPercent}%</strong>
              <span>完成率</span>
            </div>
            <div className="legend-list">
              <DashboardLegend tone="done" label="已完成" value={`${latestSubmittedTasks}项`} percent={latestCompletionPercent} />
              <DashboardLegend tone="active" label="待完成" value={`${Math.max(latestTotalTasks - latestSubmittedTasks, 0)}项`} percent={latestTotalTasks ? Math.max(100 - latestCompletionPercent, 0) : 0} />
              <DashboardLegend tone="pending" label="未生成任务" value={latestEvaluation && !latestEvaluation.tasks_generated ? "1个" : "0个"} percent={latestEvaluation && !latestEvaluation.tasks_generated ? 100 : 0} />
            </div>
          </div>
        </Card>

        <Card className="panel-card latest-card" title="最新考核计划" extra={<Button type="link" onClick={() => onNavigate("evaluations")}>全部</Button>}>
          <div className="latest-list">
            {latest.map((item) => (
              <button className="latest-row" key={item.id} onClick={() => onNavigate("evaluations")}>
                <span className={item.archived ? "status-line done" : item.is_open ? "status-line active" : "status-line pending"} />
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.year} 年 · 第 {item.sequence} 批</small>
                </span>
                <Tag color={item.archived ? "success" : item.is_open ? "processing" : "default"}>{item.archived ? "已完成" : item.is_open ? "考核中" : "未开放"}</Tag>
              </button>
            ))}
            {!latest.length ? <div className="empty-hint">暂无考核计划</div> : null}
          </div>
        </Card>
      </div>

    </div>
  );
}

function MetricCard({ icon, tone, title, value, suffix, delta, loading }: { icon: React.ReactNode; tone: string; title: string; value: number; suffix: string; delta: string; loading: boolean }) {
  return (
    <Card className="metric-card" loading={loading}>
      <span className={`metric-icon metric-${tone}`}>{icon}</span>
      <span className="metric-body">
        <small>{title}</small>
        <strong>{value}<em>{suffix}</em></strong>
        <span>{delta}</span>
      </span>
    </Card>
  );
}

function DashboardLegend({ tone, label, value, percent }: { tone: "done" | "active" | "pending"; label: string; value: string; percent: number }) {
  return (
    <div className="legend-row">
      <i className={`legend-dot-${tone}`} />
      <span>{label}</span>
      <strong>{value}</strong>
      <em>({percent}%)</em>
    </div>
  );
}
