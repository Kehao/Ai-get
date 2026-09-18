// 设置：工作空间偏好、挖掘默认值、通知与外观语言。
// 外观与语言改动立即生效（本地偏好）；其余字段改动后由「保存更改」统一提交。

import { useEffect, useMemo, useState } from 'react';
import { RotateCcw, Save } from 'lucide-react';

import * as settingsApi from '@/api/settings';
import * as targetsApi from '@/api/targets';
import type { UpdateSettingsPayload, WorkspaceSettings } from '@/api/types';
import Button from '@/components/Button';
import Dropdown from '@/components/Dropdown';
import EmptyState from '@/components/EmptyState';
import SegmentedControl from '@/components/SegmentedControl';
import Spinner from '@/components/Spinner';
import Switch from '@/components/Switch';
import Tag from '@/components/Tag';
import { useToast } from '@/components/Toast';
import { OUTREACH_CHANNELS } from '@/constants/channels';
import { useAsync } from '@/hooks/useAsync';
import { usePreferences } from '@/store/preferences';
import type { Language, ThemeMode } from '@/utils/preferences';

import styles from './SettingsPage.module.less';

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
];

const LANGUAGE_OPTIONS: { value: Language; label: string; available: boolean }[] = [
  { value: 'zh-CN', label: '简体中文', available: true },
  { value: 'en', label: 'English', available: false },
];

/** 草稿与已保存值之间需要提交的字段。 */
const diffSettings = (saved: WorkspaceSettings, draft: WorkspaceSettings): UpdateSettingsPayload => {
  const payload: UpdateSettingsPayload = {};
  if (draft.workspace_name !== saved.workspace_name) {
    payload.workspace_name = draft.workspace_name.trim();
  }
  if (draft.default_channel !== saved.default_channel) {
    payload.default_channel = draft.default_channel;
  }
  if (draft.default_count !== saved.default_count) {
    payload.default_count = draft.default_count;
  }
  if (draft.notify_on_reply !== saved.notify_on_reply) {
    payload.notify_on_reply = draft.notify_on_reply;
  }
  if (draft.notify_weekly_digest !== saved.notify_weekly_digest) {
    payload.notify_weekly_digest = saved.notify_weekly_digest;
  }
  return payload;
};

const SettingsPage = (): JSX.Element => {
  const { showToast } = useToast();
  const { theme, setTheme, language, setLanguage } = usePreferences();

  const settings = useAsync(() => settingsApi.readSettings());
  const countOptions = useAsync(() => targetsApi.readCountOptions());

  const [draft, setDraft] = useState<WorkspaceSettings | null>(null);
  const [saving, setSaving] = useState(false);

  // 首次拿到服务端设置后灌入草稿；之后不再覆盖，避免打断编辑
  useEffect(() => {
    if (settings.data !== null && draft === null) {
      setDraft(settings.data);
    }
  }, [settings.data, draft]);

  const pending = useMemo(
    () => (settings.data === null || draft === null ? {} : diffSettings(settings.data, draft)),
    [settings.data, draft],
  );
  const dirty = Object.keys(pending).length > 0;

  const countItems = useMemo(
    () =>
      (countOptions.data ?? []).map((option) => ({
        key: String(option.value),
        label: `${option.value} 条结果`,
        description: option.is_free ? '免费版可用' : '需要升级套餐',
      })),
    [countOptions.data],
  );

  const handleSave = async (): Promise<void> => {
    if (!dirty) {
      return;
    }
    setSaving(true);
    try {
      const updated = await settingsApi.updateSettings(pending);
      setDraft(updated);
      showToast('设置已保存', 'success');
    } catch (caught) {
      showToast(caught instanceof Error ? caught.message : '保存设置失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = (): void => {
    if (settings.data !== null) {
      setDraft(settings.data);
    }
  };

  if (settings.loading && draft === null) {
    return (
      <div className={styles.loading}>
        <Spinner size={22} />
        <span>正在读取设置…</span>
      </div>
    );
  }

  if (settings.error !== null && draft === null) {
    return (
      <EmptyState
        title="设置不可用"
        description={settings.error}
        action={
          <Button variant="outline" onClick={settings.reload}>
            重试
          </Button>
        }
      />
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>设置</h1>
        <p className={styles.subtitle}>调整工作空间的默认行为与界面偏好。</p>
      </header>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>工作空间</h2>
          <p className={styles.sectionHint}>名称会显示在控制台与导出的报告中</p>
        </div>

        <label className={styles.field}>
          <span className={styles.label}>工作空间名称</span>
          <input
            className={styles.input}
            value={draft?.workspace_name ?? ''}
            maxLength={40}
            placeholder="例如：华东区销售团队"
            onChange={(event) =>
              setDraft((current) => (current === null ? current : { ...current, workspace_name: event.target.value }))
            }
          />
        </label>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>挖掘默认值</h2>
          <p className={styles.sectionHint}>新建潜客列表时预填的条件</p>
        </div>

        <div className={styles.field}>
          <span className={styles.label}>默认触达渠道</span>
          <SegmentedControl
            options={OUTREACH_CHANNELS.map((channel) => ({ value: channel, label: channel }))}
            value={draft?.default_channel ?? OUTREACH_CHANNELS[0]}
            onChange={(channel) =>
              setDraft((current) => (current === null ? current : { ...current, default_channel: channel }))
            }
            ariaLabel="默认触达渠道"
          />
        </div>

        <div className={styles.field}>
          <span className={styles.label}>默认结果数量</span>
          <Dropdown
            align="start"
            panelWidth={200}
            items={countItems}
            onSelect={(key) =>
              setDraft((current) => (current === null ? current : { ...current, default_count: Number(key) }))
            }
            trigger={({ open }) => (
              <button
                type="button"
                className={[styles.select, open ? styles.selectOpen : ''].filter(Boolean).join(' ')}
              >
                {draft?.default_count ?? 25} 条结果
              </button>
            )}
          />
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>通知</h2>
          <p className={styles.sectionHint}>智能体触达过程中的提醒方式</p>
        </div>

        <div className={styles.switchRow}>
          <span className={styles.switchText}>
            <strong>客户回复提醒</strong>
            <small>客户回复邮件或社媒消息时立即通知我</small>
          </span>
          <Switch
            label="客户回复提醒"
            checked={draft?.notify_on_reply ?? false}
            onChange={(checked) =>
              setDraft((current) => (current === null ? current : { ...current, notify_on_reply: checked }))
            }
          />
        </div>

        <div className={styles.switchRow}>
          <span className={styles.switchText}>
            <strong>每周汇总</strong>
            <small>每周一发送上周的挖掘、触达与商机概况</small>
          </span>
          <Switch
            label="每周汇总"
            checked={draft?.notify_weekly_digest ?? false}
            onChange={(checked) =>
              setDraft((current) => (current === null ? current : { ...current, notify_weekly_digest: checked }))
            }
          />
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>外观与语言</h2>
          <p className={styles.sectionHint}>改动立即生效并保存在本机</p>
        </div>

        <div className={styles.field}>
          <span className={styles.label}>主题</span>
          <SegmentedControl
            options={THEME_OPTIONS}
            value={theme}
            onChange={setTheme}
            ariaLabel="主题"
          />
        </div>

        <div className={styles.field}>
          <span className={styles.label}>界面语言</span>
          <div className={styles.languageRow}>
            {LANGUAGE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={[
                  styles.languageChip,
                  language === option.value ? styles.languageChipActive : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => {
                  if (!option.available) {
                    showToast('演示环境暂只提供简体中文界面', 'info');
                    return;
                  }
                  setLanguage(option.value);
                }}
              >
                {option.label}
                {option.available ? null : <Tag tone="neutral">即将支持</Tag>}
              </button>
            ))}
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <span className={styles.footerHint}>
          {dirty ? '有未保存的改动' : '所有改动已保存'}
        </span>
        <div className={styles.footerActions}>
          <Button
            variant="ghost"
            leadingIcon={<RotateCcw size={15} />}
            onClick={handleReset}
            disabled={!dirty || saving}
          >
            还原
          </Button>
          <Button
            variant="primary"
            leadingIcon={<Save size={15} />}
            loading={saving}
            disabled={!dirty}
            onClick={() => void handleSave()}
          >
            保存更改
          </Button>
        </div>
      </footer>
    </div>
  );
};

export default SettingsPage;
