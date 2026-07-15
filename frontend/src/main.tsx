import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";

import { App } from "./routes/App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#3B82F6",
          colorSuccess: "#16A34A",
          colorWarning: "#D97706",
          colorError: "#DC2626",
          colorText: "#111827",
          colorTextSecondary: "#4B5563",
          colorBorder: "#E5E7EB",
          colorBgLayout: "#F8FAFC",
          colorBgContainer: "#FFFFFF",
          borderRadius: 8,
          borderRadiusLG: 10,
          controlHeight: 40,
          controlHeightSM: 32,
          controlHeightLG: 44,
          fontFamily:
            'Roboto, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
          fontSize: 14,
          fontSizeHeading1: 32,
          fontSizeHeading2: 24,
          fontSizeHeading3: 20,
          boxShadow:
            "0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06)"
        },
        components: {
          Button: {
            borderRadius: 8,
            fontWeight: 500,
            primaryShadow: "none"
          },
          Card: {
            borderRadiusLG: 12,
            headerFontSize: 16
          },
          Layout: {
            headerBg: "#FFFFFF",
            siderBg: "#FFFFFF",
            bodyBg: "#F8FAFC"
          },
          Menu: {
            itemBorderRadius: 8,
            itemHeight: 42,
            itemSelectedBg: "#EFF6FF",
            itemSelectedColor: "#2563EB",
            itemColor: "#4B5563",
            itemHoverBg: "#F3F4F6",
            itemHoverColor: "#111827"
          },
          Table: {
            headerBg: "#F9FAFB",
            headerColor: "#374151",
            rowHoverBg: "#F8FAFC"
          },
          Tabs: {
            itemSelectedColor: "#2563EB",
            inkBarColor: "#3B82F6"
          }
        }
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>
);
