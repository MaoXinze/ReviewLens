import { Space, Typography } from 'antd';
import type { ReactNode } from 'react';

const { Title, Paragraph } = Typography;

interface PageHeaderProps {
  title: string;
  description?: string;
  /** 右侧操作区（按钮 / 筛选等） */
  extra?: ReactNode;
}

/** 统一页头：渐变标题 + 副标题 + 右侧操作区，替代各页面重复的 Title+Paragraph 组合 */
export default function PageHeader({ title, description, extra }: PageHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: 12,
        marginBottom: 20,
      }}
    >
      <div>
        <Title level={3} style={{ margin: 0, lineHeight: 1.3 }}>
          <span className="grad-text">{title}</span>
        </Title>
        {description && (
          <Paragraph type="secondary" style={{ margin: 0, marginTop: 6, maxWidth: 720 }}>
            {description}
          </Paragraph>
        )}
      </div>
      {extra && (
        <Space size={8} wrap style={{ paddingTop: 4 }}>
          {extra}
        </Space>
      )}
    </div>
  );
}
