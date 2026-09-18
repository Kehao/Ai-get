// 可用的触达渠道。与后端 config.OUTREACH_CHANNELS 保持一致，
// 触达计划、智能体渠道选择与工作空间默认值都引用这里，避免三处各写一份。

export const OUTREACH_CHANNELS: readonly string[] = ['邮件', 'LinkedIn', 'WhatsApp'];
