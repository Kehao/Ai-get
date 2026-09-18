import { Navigate, Outlet, useLocation } from 'react-router-dom';

import Spinner from '@/components/Spinner';
import { ROUTES } from '@/constants/routes';
import { useAuth } from '@/store/auth';

import styles from './RequireAuth.module.less';

/** 控制台访问守卫：未登录时跳转登录页，并记住原目标地址。 */
const RequireAuth = (): JSX.Element => {
  const { user, initializing } = useAuth();
  const location = useLocation();

  if (initializing) {
    return (
      <div className={styles.loading}>
        <Spinner size={22} />
        <span>正在校验登录状态…</span>
      </div>
    );
  }

  if (user === null) {
    return <Navigate to={ROUTES.signIn} state={{ from: location.pathname }} replace />;
  }

  return <Outlet />;
};

export default RequireAuth;
