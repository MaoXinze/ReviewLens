import type { CSSProperties, ReactNode } from 'react';

/**
 * ReviewLens 自制线性描边图标库
 * 风格：24×24 网格、1.6px 圆角描边、currentColor（随主题色）、fill=none
 * 全部手绘 SVG，非通用图标库，保证品牌一致性。
 */

export interface IconProps {
  size?: number;
  className?: string;
  style?: CSSProperties;
}

function Svg({
  size = 18,
  className,
  style,
  children,
  viewBox = '0 0 24 24',
  strokeWidth = 1.6,
}: IconProps & { children: ReactNode; viewBox?: string; strokeWidth?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/* ---------- 品牌 Logo：透镜 + 数据点 ---------- */
export function ReviewLensLogo({ size = 30 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="rl-logo-grad" x1="4" y1="4" x2="44" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor="#22d3ee" />
          <stop offset="0.5" stopColor="#6366f1" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      {/* 透镜外环 */}
      <circle cx="24" cy="24" r="17" stroke="url(#rl-logo-grad)" strokeWidth="3" />
      <circle cx="24" cy="24" r="17" stroke="url(#rl-logo-grad)" strokeWidth="3" opacity="0.25" strokeDasharray="4 6" transform="rotate(-20 24 24)" />
      {/* 折线数据 */}
      <path
        d="M14 30l5-7 4 4 6-9"
        stroke="url(#rl-logo-grad)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="14" cy="30" r="2.4" fill="#22d3ee" />
      <circle cx="19" cy="23" r="2.4" fill="#6366f1" />
      <circle cx="23" cy="27" r="2.4" fill="#818cf8" />
      <circle cx="29" cy="18" r="2.4" fill="#a78bfa" />
    </svg>
  );
}

/* ---------- 导航图标 ---------- */

/** 体验总览：仪表盘 */
export function IconDashboard(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" />
    </Svg>
  );
}

/** 数据集：数据库 */
export function IconDatabase(props: IconProps) {
  return (
    <Svg {...props}>
      <ellipse cx="12" cy="5.5" rx="8" ry="3" />
      <path d="M4 5.5v13c0 1.66 3.58 3 8 3s8-1.34 8-3v-13" />
      <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" />
    </Svg>
  );
}

/** 评论搜索：放大镜 + 评论点 */
export function IconSearch(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.35-4.35" />
      <path d="M8.5 11a2.5 2.5 0 0 1 2.5-2.5" opacity="0.7" />
    </Svg>
  );
}

/** 审核任务：文档 + 勾 */
export function IconReview(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6z" />
      <path d="M14 3v6h6" />
      <path d="M9 14.5l2 2 4-4" />
    </Svg>
  );
}

/** 体验洞察：趋势上升折线 */
export function IconInsights(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 3v18h18" />
      <path d="M7 14l4-4 3 3 5-6" />
      <path d="M19 7h-3m3 0v3" />
    </Svg>
  );
}

/** 模型中心：芯片 / 神经网络 */
export function IconModel(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 9h6v6H9z" />
      <path d="M10 2v3M14 2v3M10 19v3M14 19v3M2 10h3M2 14h3M19 10h3M19 14h3" />
    </Svg>
  );
}

/** 问题卡：标签 + 卡片 */
export function IconIssue(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 9h10M7 13h6" />
      <path d="M7 17h4" />
    </Svg>
  );
}

/** 告警中心：铃铛 */
export function IconAlert(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </Svg>
  );
}

/** 用户管理：用户组 */
export function IconUsers(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.2 3.3-5 6.5-5s5.7 1.8 6.5 5" />
      <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8" />
      <path d="M17.5 15.3c1.8.7 3.2 2.2 4 4.7" />
    </Svg>
  );
}

/** 个人：用户 */
export function IconUser(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 20.5c1-4 3.9-6 7.5-6s6.5 2 7.5 6" />
    </Svg>
  );
}

/** 通知铃铛（Header） */
export function IconBell(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
      <circle cx="18.5" cy="5.5" r="1.8" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** 折叠菜单 */
export function IconMenu(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  );
}

/** 退出登录 */
export function IconLogout(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8" />
      <path d="M16 8l4 4-4 4M20 12H10" />
    </Svg>
  );
}

/** 设置 */
export function IconSettings(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </Svg>
  );
}

/** 导出下载 */
export function IconDownload(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M7 10l5 5 5-5M12 15V3" />
    </Svg>
  );
}

/** 上传 */
export function IconUpload(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="M17 8l-5-5-5 5M12 3v12" />
    </Svg>
  );
}

/** 数据/查看证据 */
export function IconSpark(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="12" cy="12" r="3.2" />
    </Svg>
  );
}

/** 校验/已通过 */
export function IconCheckCircle(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.5l2.3 2.3 4.7-5" />
    </Svg>
  );
}

/** 关闭/返回（紧凑） */
export function IconX(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

/** 邮箱 */
export function IconMail(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 7l9 6 9-6" />
    </Svg>
  );
}

/** 密码锁 */
export function IconLock(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      <circle cx="12" cy="15.5" r="1.3" fill="currentColor" stroke="none" />
    </Svg>
  );
}

/** 右箭头 */
export function IconArrowRight(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Svg>
  );
}

/** 火箭/洞察（品牌标语用） */
export function IconRocket(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4.5 16.5c-1.5 1.3-2 4-2 4s2.7-.5 4-2" />
      <path d="M12 15l-3-3c.5-3.5 2.5-7 8-9.5.5 5.5-2.5 9-7.5 9.5z" />
      <circle cx="14.8" cy="9.2" r="1.4" />
      <path d="M9 12l-2 4M12 15l1 4" />
    </Svg>
  );
}
