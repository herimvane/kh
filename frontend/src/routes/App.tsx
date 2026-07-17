import {
  ApartmentOutlined,
  AuditOutlined,
  BarChartOutlined,
  CheckSquareOutlined,
  ControlOutlined,
  DownloadOutlined,
  HomeFilled,
  IdcardOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PieChartOutlined,
  TeamOutlined,
  UserOutlined
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
  Layout,
  Menu,
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
import type React from "react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { changePassword, getCurrentUser, login, logout, type UserSummary } from "../api/auth";
import {
  evaluationsApi,
  type Evaluation,
  type EvaluationConfig,
  type EvaluationScoreDepartment,
  type EvaluationScorePerson,
  type EvaluationStatsResponse,
  type ReviewSubmissionDetailResponse
} from "../api/evaluations";
import {
  masterDataApi,
  type Department,
  type DepartmentChoice,
  type Position,
  type ReviewerUser,
  type ScoreOption,
  type UserRow
} from "../api/masterData";
import { settingsApi } from "../api/settings";

const EvaluationAppPage = lazy(() => import("./EvaluationAppPage"));
const MyEvaluationsPage = lazy(() => import("./MyEvaluationsPage"));
const EvaluationsPage = lazy(() => import("./EvaluationsPage"));
const DashboardPage = lazy(() => import("./DashboardPage"));
const DepartmentsPage = lazy(() => import("./DepartmentsPage"));
const PositionsPage = lazy(() => import("./PositionsPage"));
const UsersPage = lazy(() => import("./UsersPage"));
const ScoreOptionsPage = lazy(() => import("./ScoreOptionsPage"));
const SystemSettingsPage = lazy(() => import("./SystemSettingsPage"));

type LoginFormValues = {
  username: string;
  password: string;
};

type RouteKey = "dashboard" | "departments" | "positions" | "users" | "score-options" | "evaluations" | "settings" | "my-evaluations" | "evaluation-app";

const DEFAULT_SYSTEM_NAME = "人事考核管理系统";

type DepartmentTreeNode = {
  title: string;
  value: number;
  key: number;
  disabled?: boolean;
  children: DepartmentTreeNode[];
};

const tablePagination = () => ({
  pageSize: 10,
  showSizeChanger: false,
  showTotal: (total: number) => `共 ${total} 条`
});

type DeleteResult = { message: string };

function confirmDeletion(
  modal: ReturnType<typeof AntApp.useApp>["modal"],
  options: {
    title: string;
    content?: React.ReactNode;
    action: () => Promise<DeleteResult>;
    onSuccess: (result: DeleteResult) => Promise<void> | void;
  }
) {
  modal.confirm({
    title: options.title,
    content: options.content,
    okText: "确认删除",
    cancelText: "取消",
    okButtonProps: { danger: true },
    onOk: async () => {
      let result: DeleteResult;
      try {
        result = await options.action();
      } catch (error) {
        modal.error({
          title: "无法删除",
          content: error instanceof Error ? error.message : "删除失败，请检查数据引用后重试。",
          okText: "我知道了"
        });
        return;
      }
      await options.onSuccess(result);
    }
  });
}

function buildDepartmentTree(
  departments: Array<{ id: number; name: string; parent_id?: number | null }>,
  disabledIds: ReadonlySet<number> = new Set()
): DepartmentTreeNode[] {
  const nodes = new Map<number, DepartmentTreeNode>();
  departments.forEach((department) => {
    nodes.set(department.id, {
      title: department.name,
      value: department.id,
      key: department.id,
      disabled: disabledIds.has(department.id),
      children: []
    });
  });

  const roots: DepartmentTreeNode[] = [];
  departments.forEach((department) => {
    const node = nodes.get(department.id)!;
    const parent = department.parent_id ? nodes.get(department.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  });
  return roots;
}

type DepartmentMultiTreeProps = {
  departments: Array<{ id: number; name: string; parent_id?: number | null }>;
  value?: number[];
  onChange?: (value: number[]) => void;
  placeholder?: string;
};

function DepartmentMultiTreeSelect({ departments, value = [], onChange, placeholder = "搜索或选择部门" }: DepartmentMultiTreeProps) {
  const selected = new Set(value);
  const baseTree = useMemo(() => buildDepartmentTree(departments), [departments]);

  const descendantIds = (node: DepartmentTreeNode): number[] =>
    node.children.flatMap((child) => [child.value, ...descendantIds(child)]);

  const updateDescendants = (node: DepartmentTreeNode, remove: boolean) => {
    const descendants = descendantIds(node);
    const next = new Set(value);
    descendants.forEach((id) => remove ? next.delete(id) : next.add(id));
    onChange?.(Array.from(next));
  };

  const decorate = (node: DepartmentTreeNode): Record<string, unknown> => {
    const descendants = descendantIds(node);
    const allDescendantsSelected = descendants.length > 0 && descendants.every((id) => selected.has(id));
    return {
      ...node,
      searchText: node.title,
      labelText: node.title,
      title: (
        <span className="department-tree-title">
          <span>{node.title}</span>
          {descendants.length ? (
            <button
              type="button"
              className="department-tree-branch-action"
              aria-label={`${allDescendantsSelected ? "清除" : "选择"}${node.title}下的全部子部门`}
              onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); }}
              onClick={(event) => { event.preventDefault(); event.stopPropagation(); updateDescendants(node, allDescendantsSelected); }}
            >
              {allDescendantsSelected ? "清子级" : "选子级"}
            </button>
          ) : null}
        </span>
      ),
      children: node.children.map(decorate)
    };
  };

  const normalizeValues = (items: unknown) => {
    if (!Array.isArray(items)) return [];
    return items.map((item) => typeof item === "object" && item !== null && "value" in item ? Number((item as { value: unknown }).value) : Number(item));
  };

  return (
    <TreeSelect
      className="department-tree-select"
      value={value}
      onChange={(items) => onChange?.(normalizeValues(items))}
      treeData={baseTree.map(decorate)}
      treeCheckable
      treeCheckStrictly
      showCheckedStrategy={TreeSelect.SHOW_ALL}
      showSearch
      treeNodeFilterProp="searchText"
      treeNodeLabelProp="labelText"
      allowClear
      maxTagCount="responsive"
      maxTagPlaceholder={(values) => `另有 ${values.length} 个部门`}
      placeholder={placeholder}
      treeDefaultExpandAll
    />
  );
}

function routeFromPath(pathname: string, role?: string): RouteKey {
  if (/^\/app\/evaluations\/\d+\/?$/.test(pathname)) return "evaluation-app";
  if (pathname.startsWith("/app/evaluation")) return "my-evaluations";
  if (pathname.includes("/departments")) return "departments";
  if (pathname.includes("/positions")) return "positions";
  if (pathname.includes("/users")) return "users";
  if (pathname.includes("/score-options")) return "score-options";
  if (pathname.includes("/evaluations")) return "evaluations";
  if (pathname.includes("/settings")) return "settings";
  return role === "user" ? "my-evaluations" : "dashboard";
}

function pathFromRoute(route: RouteKey): string {
  const map: Record<RouteKey, string> = {
    dashboard: "/admin",
    departments: "/admin/departments",
    positions: "/admin/positions",
    users: "/admin/users",
    "score-options": "/admin/score-options",
    evaluations: "/admin/evaluations",
    settings: "/admin/settings",
    "my-evaluations": "/app/evaluations",
    "evaluation-app": "/app/evaluations"
  };
  return map[route];
}

export function App() {
  return (
    <AntApp>
      <Root />
    </AntApp>
  );
}

function Root() {
  const { message } = AntApp.useApp();
  const [user, setUser] = useState<UserSummary | null>(null);
  const [booting, setBooting] = useState(true);
  const [route, setRoute] = useState<RouteKey>(() => routeFromPath(window.location.pathname));
  const [siderCollapsed, setSiderCollapsed] = useState(() => window.matchMedia("(max-width: 1024px)").matches);
  const [systemName, setSystemName] = useState(DEFAULT_SYSTEM_NAME);

  useEffect(() => {
    settingsApi.get().then((settings) => setSystemName(settings.system_name)).catch(() => undefined);
    getCurrentUser()
      .then((current) => {
        setUser(current);
        setRoute(routeFromPath(window.location.pathname, current.role));
      })
      .catch(() => setUser(null))
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => { document.title = systemName; }, [systemName]);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 1024px)");
    const syncSider = (event: MediaQueryListEvent) => setSiderCollapsed(event.matches);
    query.addEventListener("change", syncSider);
    return () => query.removeEventListener("change", syncSider);
  }, []);
  useEffect(() => {
    if (!user) return;
    if (user.role === "user" && !window.location.pathname.startsWith("/app/evaluations")) {
      window.history.replaceState(null, "", "/app/evaluations");
      setRoute("my-evaluations");
    } else if (user.role === "admin" && !user.is_super_admin && route === "settings") {
      window.history.replaceState(null, "", "/admin");
      setRoute("dashboard");
    }
  }, [route, user]);
  useEffect(() => {
    const handlePopState = () => setRoute(routeFromPath(window.location.pathname, user?.role));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [user?.role]);

  const navigate = (nextRoute: RouteKey) => {
    setRoute(nextRoute);
    window.history.pushState(null, "", pathFromRoute(nextRoute));
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    window.history.pushState(null, "", "/");
    message.success("已退出登录。");
  };

  const enterEvaluation = (evaluationId: number) => {
    setRoute("evaluation-app");
    window.history.pushState(null, "", `/app/evaluations/${evaluationId}`);
  };

  const selectedEvaluationId = Number(window.location.pathname.match(/^\/app\/evaluations\/(\d+)/)?.[1] || 0);

  if (booting) {
    return <div className="boot-screen">正在加载系统...</div>;
  }

  if (!user) {
    return <LoginPage systemName={systemName} onLogin={setUser} />;
  }

  if (user.role === "user") {
    return (
      <Layout className="app-shell">
        <HeaderBar
          user={user}
          systemName={systemName}
          onLogout={handleLogout}
          forcePasswordChange={user.must_change_password}
          onPasswordChanged={() => setUser((current) => current ? { ...current, must_change_password: false } : current)}
        />
        <main className="user-workspace">
          <Suspense fallback={<div className="boot-screen">正在加载评分工作台...</div>}>
            {route === "evaluation-app" && selectedEvaluationId ? (
              <EvaluationAppPage evaluationId={selectedEvaluationId} onBack={() => navigate("my-evaluations")} />
            ) : (
              <MyEvaluationsPage onEnter={enterEvaluation} />
            )}
          </Suspense>
        </main>
      </Layout>
    );
  }

  return (
    <Layout className="admin-shell">
      <Layout.Sider className="admin-sider" width={232} collapsedWidth={76} collapsed={siderCollapsed} collapsible trigger={null}>
        <Menu
          theme="dark"
          mode="inline"
          inlineCollapsed={siderCollapsed}
          selectedKeys={[route]}
          onClick={(item) => navigate(item.key as RouteKey)}
          items={[
            { key: "dashboard", icon: <HomeFilled />, label: "首页" },
            { key: "departments", icon: <ApartmentOutlined />, label: "部门管理" },
            { key: "users", icon: <TeamOutlined />, label: "人员管理" },
            { key: "positions", icon: <IdcardOutlined />, label: "职位管理" },
            { key: "score-options", icon: <AuditOutlined />, label: "评分选项" },
            { key: "evaluations", icon: <CheckSquareOutlined />, label: "考核管理" },
            ...(user.is_super_admin ? [{ key: "settings", icon: <ControlOutlined />, label: "系统设置" }] : []),
          ]}
        />
      </Layout.Sider>
      <Layout>
        <HeaderBar
          user={user}
          systemName={systemName}
          onLogout={handleLogout}
          admin
          siderCollapsed={siderCollapsed}
          onToggleSider={() => setSiderCollapsed((collapsed) => !collapsed)}
          forcePasswordChange={user.must_change_password}
          onPasswordChanged={() => setUser((current) => current ? { ...current, must_change_password: false } : current)}
        />
        <main className="admin-workspace">
          <Suspense fallback={<div className="boot-screen">正在加载页面...</div>}>
            {route === "dashboard" ? <DashboardPage onNavigate={navigate} /> : null}
            {route === "departments" ? <DepartmentsPage readOnly={!user.is_super_admin} /> : null}
            {route === "positions" ? <PositionsPage readOnly={!user.is_super_admin} /> : null}
            {route === "users" ? <UsersPage readOnly={!user.is_super_admin} /> : null}
            {route === "score-options" ? <ScoreOptionsPage readOnly={!user.is_super_admin} /> : null}
            {route === "evaluations" ? (
              <EvaluationsPage user={user} />
            ) : null}
            {route === "settings" && user.is_super_admin ? <SystemSettingsPage systemName={systemName} onChanged={setSystemName} /> : null}
          </Suspense>
        </main>
      </Layout>
    </Layout>
  );
}

function HeaderBar({
  user,
  systemName,
  onLogout,
  admin = false,
  siderCollapsed = false,
  onToggleSider,
  forcePasswordChange = false,
  onPasswordChanged
}: {
  user: UserSummary;
  systemName: string;
  onLogout: () => void;
  admin?: boolean;
  siderCollapsed?: boolean;
  onToggleSider?: () => void;
  forcePasswordChange?: boolean;
  onPasswordChanged?: () => void;
}) {
  const { message } = AntApp.useApp();
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordForm] = Form.useForm();

  const savePassword = async () => {
    const values = await passwordForm.validateFields();
    setPasswordSaving(true);
    try {
      const result = await changePassword(values.current_password, values.new_password);
      message.success(result.message);
      setPasswordOpen(false);
      passwordForm.resetFields();
      onPasswordChanged?.();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "密码修改失败。");
    } finally {
      setPasswordSaving(false);
    }
  };

  return (
    <>
      <Layout.Header className={admin ? "app-header gov-header" : "app-header"}>
        <div className="header-context">
          {admin ? (
            <Button
              type="text"
              className="header-menu-button"
              icon={siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              aria-label={siderCollapsed ? "展开侧边菜单" : "折叠侧边菜单"}
              title={siderCollapsed ? "展开侧边菜单" : "折叠侧边菜单"}
              onClick={onToggleSider}
            />
          ) : <span className="header-dot" />}
          <span>{admin ? systemName : "我的考核"}</span>
        </div>
        <Space size={12}>
          <span>{user.full_name}</span>
          <Button type="text" icon={<LockOutlined />} onClick={() => setPasswordOpen(true)}>修改密码</Button>
          <Button icon={<LogoutOutlined />} onClick={onLogout}>
            退出
          </Button>
        </Space>
      </Layout.Header>
      <Modal
          title={forcePasswordChange ? "首次登录，请修改密码" : "修改密码"}
          open={forcePasswordChange || passwordOpen}
          okText="确认修改"
          cancelText="取消"
          confirmLoading={passwordSaving}
          onOk={() => void savePassword()}
          cancelButtonProps={{ style: forcePasswordChange ? { display: "none" } : undefined }}
          closable={!forcePasswordChange}
          maskClosable={!forcePasswordChange}
          keyboard={!forcePasswordChange}
          onCancel={() => { if (!forcePasswordChange) { setPasswordOpen(false); passwordForm.resetFields(); } }}
          destroyOnClose
        >
          <Form form={passwordForm} layout="vertical" requiredMark={false}>
            <Form.Item name="current_password" label="当前密码" rules={[{ required: true, message: "请输入当前密码。" }]}>
              <Input.Password autoComplete="current-password" placeholder="请输入当前密码" />
            </Form.Item>
            <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: "请输入新密码。" }, { min: 6, message: "新密码至少需要 6 个字符。" }]}>
              <Input.Password autoComplete="new-password" placeholder="至少 6 个字符" />
            </Form.Item>
            <Form.Item name="confirm_password" label="确认新密码" dependencies={["new_password"]} rules={[{ required: true, message: "请再次输入新密码。" }, ({ getFieldValue }) => ({ validator(_, value) { return !value || value === getFieldValue("new_password") ? Promise.resolve() : Promise.reject(new Error("两次输入的新密码不一致。")); } })]}>
              <Input.Password autoComplete="new-password" placeholder="请再次输入新密码" onPressEnter={() => void savePassword()} />
            </Form.Item>
          </Form>
        </Modal>
    </>
  );
}

function LoginPage({ systemName, onLogin }: { systemName: string; onLogin: (user: UserSummary) => void }) {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (values: LoginFormValues) => {
    setLoading(true);
    setError("");
    try {
      const result = await login(values.username, values.password);
      onLogin(result.user);
      window.history.pushState(null, "", result.redirect_to);
      message.success(`欢迎，${result.user.full_name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout className="login-shell">
      <div className="login-stage">
        <section className="login-visual" aria-hidden="true">
          <div className="login-visual-panel">
            <Typography.Title level={1}>{systemName}</Typography.Title>
            <span className="login-title-rule" />
          </div>
          <div className="login-data-card">
            <div className="login-data-avatar"><UserOutlined /></div>
            <div className="login-data-lines">
              <span />
              <span />
            </div>
            <div className="login-data-chart">
              <i />
              <i />
              <i />
              <i />
            </div>
            <div className="login-data-shield"><UserOutlined /></div>
          </div>
          <span className="login-floating-icon login-floating-users"><TeamOutlined /></span>
          <span className="login-floating-icon login-floating-chart"><BarChartOutlined /></span>
          <span className="login-floating-icon login-floating-star"><CheckSquareOutlined /></span>
        </section>
        <main className="login-main">
          <Card className="login-card" bordered={false}>
            <Typography.Title level={2}>欢迎登录</Typography.Title>
            {error ? <Alert className="login-alert" type="error" message={error} showIcon /> : null}
            <Form<LoginFormValues> layout="vertical" requiredMark={false} onFinish={handleLogin}>
              <Form.Item name="username" rules={[{ required: true, message: "请输入用户名。" }]}>
                <Input size="large" prefix={<UserOutlined />} placeholder="请输入用户名" autoComplete="username" />
              </Form.Item>
              <Form.Item name="password" rules={[{ required: true, message: "请输入密码。" }]}>
                <Input.Password size="large" prefix={<LockOutlined />} placeholder="请输入密码" autoComplete="current-password" />
              </Form.Item>
              <Checkbox className="remember-check">记住我</Checkbox>
              <Button block size="large" type="primary" htmlType="submit" loading={loading}>
                登录
              </Button>
            </Form>
            <div className="login-copyright">© 2026 WENXIANYUN 版权所有</div>
          </Card>
        </main>
      </div>
    </Layout>
  );
}
