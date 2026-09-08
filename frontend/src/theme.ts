import { type ThemeConfig } from 'antd';

/**
 * ReviewLens 清新明亮主题（对标 Ant Design 官方浅色风格）
 *
 * 设计原则：白底浅灰界面、主色 AntD 蓝（#1677ff）、少渐变少发光、
 * 用边框和轻阴影分层，数据密集区域保持高可读性。
 */
export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    colorInfo: '#1677ff',
    colorSuccess: '#52c41a',
    colorWarning: '#faad14',
    colorError: '#ff4d4f',
    colorBgBase: '#f5f7fa',
    colorBgContainer: '#ffffff',
    colorBorder: '#d9d9d9',
    colorBorderSecondary: '#f0f0f0',
    colorText: '#1f2329',
    colorTextSecondary: '#51565d',
    colorTextTertiary: '#8a9099',
    borderRadius: 8,
    fontFamily:
      "'Inter', 'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    controlHeight: 34,
    boxShadowSecondary: '0 6px 16px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04)',
  },
  components: {
    Layout: {
      headerBg: 'transparent',
      siderBg: 'transparent',
      bodyBg: 'transparent',
    },
    Menu: {
      itemColor: '#4b5563',
      itemHoverColor: '#1677ff',
      itemHoverBg: '#f5f5f5',
      itemSelectedColor: '#1677ff',
      itemSelectedBg: '#e6f4ff',
      itemBorderRadius: 8,
      itemMarginInline: 10,
    },
    Card: {
      colorBgContainer: '#ffffff',
      headerFontSize: 15,
    },
    Table: {
      headerBg: '#fafafa',
      rowHoverBg: '#f0f7ff',
    },
    Modal: {
      contentBg: '#ffffff',
      headerBg: '#ffffff',
    },
    Drawer: {
      colorBgElevated: '#ffffff',
    },
    Tabs: {
      inkBarColor: '#1677ff',
      itemSelectedColor: '#1677ff',
      itemHoverColor: '#4096ff',
    },
    Button: {
      primaryShadow: '0 2px 4px rgba(22, 119, 255, 0.25)',
      defaultBg: '#ffffff',
      defaultBorderColor: '#d9d9d9',
    },
    Select: {
      optionSelectedBg: '#e6f4ff',
    },
    Segmented: {
      itemSelectedBg: '#ffffff',
      trackBg: '#f0f2f5',
    },
    Statistic: {
      contentFontSize: 26,
    },
  },
};
