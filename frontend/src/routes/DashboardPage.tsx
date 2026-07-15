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
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      evaluationsApi.list(),
      masterDataApi.users("", 1),
      masterDataApi.departments()
    ])
      .then(([evaluationRows, users, departmentRows]) => {
        setEvaluations(evaluationRows);
        setUserTotal(users.pagination.total);
        setDepartments(departmentRows);
      })
      .finally(() => setLoading(false));
  }, []);

  const activeEvaluations = evaluations.filter((item) => item.is_open && !item.archived);
  const completedEvaluations = evaluations.filter((item) => item.archived || (item.total_tasks > 0 && item.submitted_tasks >= item.total_tasks));
  const totalTasks = evaluations.reduce((sum, item) => sum + item.total_tasks, 0);
  const submittedTasks = evaluations.reduce((sum, item) => sum + item.submitted_tasks, 0);
  const completionPercent = totalTasks ? Math.round((submittedTasks / totalTasks) * 100) : 0;
  const currentYear = new Date().getFullYear();
  const latestYear = evaluations.length ? Math.max(...evaluations.map((item) => item.year)) : null;
  const latestYearEvaluations = latestYear === null ? [] : evaluations.filter((item) => item.year === latestYear);
  const latestYearTotalTasks = latestYearEvaluations.reduce((sum, item) => sum + item.total_tasks, 0);
  const latestYearSubmittedTasks = latestYearEvaluations.reduce((sum, item) => sum + item.submitted_tasks, 0);
  const latestYearCompletionPercent = latestYearTotalTasks
    ? Math.round((latestYearSubmittedTasks / latestYearTotalTasks) * 100)
    : 0;
  const latest = [...evaluations].sort((a, b) => b.year - a.year || b.id - a.id).slice(0, 5);

  return (
    <div className="dashboard-page">
      <PageTitle title="首页" />
      <div className="metric-grid">
        <MetricCard icon={<TeamOutlined />} tone="blue" title="在岗人数" value={userTotal} suffix="人" delta={`部门 ${departments.length} 个`} loading={loading} />
        <MetricCard icon={<CheckSquareOutlined />} tone="green" title="考核计划数" value={evaluations.length} suffix="个" delta={`本年度 ${evaluations.filter((item) => item.year === currentYear).length} 个`} loading={loading} />
        <MetricCard icon={<UserOutlined />} tone="orange" title="考核中计划" value={activeEvaluations.length} suffix="个" delta={`待提交 ${Math.max(totalTasks - submittedTasks, 0)} 项`} loading={loading} />
        <MetricCard icon={<PieChartOutlined />} tone="purple" title="已完成考核" value={completedEvaluations.length} suffix="个" delta={`完成率 ${completionPercent}%`} loading={loading} />
      </div>

      <div className="dashboard-main-grid">
        <Card className="panel-card completion-card" title="考核完成情况" extra={<Button size="small">{latestYear ?? "--"}</Button>}>
          <div className="donut-wrap">
            <div className="donut-chart" style={{ "--done": `${latestYearCompletionPercent * 3.6}deg` } as React.CSSProperties}>
              <strong>{latestYearCompletionPercent}%</strong>
              <span>完成率</span>
            </div>
            <div className="legend-list">
              <DashboardLegend color="#2877ff" label="已完成" value={`${latestYearSubmittedTasks}项`} percent={latestYearCompletionPercent} />
              <DashboardLegend color="#29c59a" label="考核中" value={`${Math.max(latestYearTotalTasks - latestYearSubmittedTasks, 0)}项`} percent={Math.max(100 - latestYearCompletionPercent, 0)} />
              <DashboardLegend color="#ff9f2e" label="未开始" value={`${latestYearEvaluations.filter((item) => !item.tasks_generated).length}个`} percent={latestYearEvaluations.length ? Math.round((latestYearEvaluations.filter((item) => !item.tasks_generated).length / latestYearEvaluations.length) * 100) : 0} />
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
                  <small>考核年度：{item.year}</small>
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

function DashboardLegend({ color, label, value, percent }: { color: string; label: string; value: string; percent: number }) {
  return (
    <div className="legend-row">
      <i style={{ background: color }} />
      <span>{label}</span>
      <strong>{value}</strong>
      <em>({percent}%)</em>
    </div>
  );
}
