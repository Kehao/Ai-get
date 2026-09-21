// 注册页：邮箱密码注册。注册成功后直接签发令牌并进入工作台。

import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';

import { describeError } from '@/api/client';
import Button from '@/components/Button';
import { useToast } from '@/components/Toast';
import { CONSOLE_ENTRY, ROUTES } from '@/constants/routes';
import { useAuth } from '@/store/auth';

import styles from './auth.module.less';

const MIN_PASSWORD_LENGTH = 6;

const SignUpPage = (): JSX.Element => {
  const navigate = useNavigate();
  const { signUp } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const passwordMismatch = confirmPassword !== '' && confirmPassword !== password;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      showToast(`密码至少需要 ${MIN_PASSWORD_LENGTH} 位`, 'error');
      return;
    }
    if (passwordMismatch) {
      showToast('两次输入的密码不一致', 'error');
      return;
    }

    setSubmitting(true);
    try {
      await signUp(email.trim(), password);
      showToast('注册成功，正在进入工作台', 'success');
      navigate(CONSOLE_ENTRY, { replace: true });
    } catch (caught) {
      showToast(describeError(caught), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <Link to={ROUTES.home} className={styles.brand}>
          <span className={styles.brandMark}>A</span>
          <span className={styles.brandName}>Ai-get</span>
        </Link>

        <h1 className={styles.title}>注册</h1>
        <p className={styles.subtitle}>创建 Ai-get 账户，开始用 AI 销售智能体获客</p>

        <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
          <label className={styles.field}>
            <span className={styles.label}>邮箱</span>
            <input
              className={styles.input}
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>密码</span>
            <span className={styles.passwordWrapper}>
              <input
                className={styles.input}
                type={passwordVisible ? 'text' : 'password'}
                required
                minLength={MIN_PASSWORD_LENGTH}
                autoComplete="new-password"
                placeholder={`至少 ${MIN_PASSWORD_LENGTH} 位`}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                type="button"
                className={styles.togglePassword}
                onClick={() => setPasswordVisible((current) => !current)}
                aria-label={passwordVisible ? '隐藏密码' : '显示密码'}
              >
                {passwordVisible ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </span>
          </label>

          <label className={styles.field}>
            <span className={styles.label}>确认密码</span>
            <input
              className={styles.input}
              type={passwordVisible ? 'text' : 'password'}
              required
              autoComplete="new-password"
              placeholder="再次输入密码"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
            {passwordMismatch ? <span className={styles.hintError}>两次输入的密码不一致</span> : null}
          </label>

          <Button type="submit" variant="primary" size="lg" block loading={submitting}>
            创建账户
          </Button>
        </form>

        <p className={styles.footer}>
          已有账户？ <Link className={styles.link} to={ROUTES.signIn}>登录</Link>
        </p>

        <p className={styles.notice}>
          注册并使用 Ai-get，即表示同意我们的 <Link className={styles.link} to={ROUTES.terms}>
            服务条款
          </Link>{' '}
          和 <Link className={styles.link} to={ROUTES.privacy}>隐私政策</Link>。
        </p>

        <p className={styles.demoHint}>演示环境：预置账号 admin@admin.com 可直接登录体验</p>
      </div>
    </div>
  );
};

export default SignUpPage;
