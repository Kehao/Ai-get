// 登录页：结构与参考站一致（Google 入口、邮箱密码、忘记密码、注册引导）。
// Google 登录在演示环境不可用，点击后给出明确提示而不是静默失败。

import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';

import { describeError } from '@/api/client';
import Button from '@/components/Button';
import { useToast } from '@/components/Toast';
import { CONSOLE_ENTRY, ROUTES } from '@/constants/routes';
import { useAuth } from '@/store/auth';

import styles from './auth.module.less';

interface LocationState {
  from?: string;
}

const DEMO_EMAIL = 'qiukehao388@126.com';
const DEMO_PASSWORD = 'm831027';

const SignInPage = (): JSX.Element => {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = (location.state as LocationState | null)?.from ?? CONSOLE_ENTRY;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (submitting) {
      return;
    }

    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      showToast('登录成功，正在进入工作台', 'success');
      navigate(redirectTo, { replace: true });
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

        <h1 className={styles.title}>登录</h1>
        <p className={styles.subtitle}>登录您的 Ai-get 账户</p>

        <Button
          variant="outline"
          size="lg"
          block
          leadingIcon={<span aria-hidden>G</span>}
          onClick={() => showToast('演示环境未接入 Google 登录，请使用邮箱登录', 'info')}
        >
          使用 Google 登录
        </Button>

        <div className={styles.divider}>
          <span>或</span>
        </div>

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
            <span className={styles.labelRow}>
              <span className={styles.label}>密码</span>
              <Link className={styles.link} to={ROUTES.signIn}>
                忘记密码？
              </Link>
            </span>
            <span className={styles.passwordWrapper}>
              <input
                className={styles.input}
                type={passwordVisible ? 'text' : 'password'}
                required
                minLength={6}
                autoComplete="current-password"
                placeholder="请输入密码"
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

          <Button type="submit" variant="primary" size="lg" block loading={submitting}>
            使用邮箱登录
          </Button>
        </form>

        <p className={styles.footer}>
          还没有账户？ <Link className={styles.link} to={ROUTES.signUp}>注册</Link>
        </p>

        <p className={styles.notice}>
          继续登录，即表示同意我们的 <Link className={styles.link} to={ROUTES.terms}>服务条款</Link> 和{' '}
          <Link className={styles.link} to={ROUTES.privacy}>隐私政策</Link>。
        </p>

        <p className={styles.demoHint}>
          演示账号已预填：{DEMO_EMAIL}
        </p>
      </div>
    </div>
  );
};

export default SignInPage;
