import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { AppShell, Topbar } from './components/AppShell';
import { FullPageSpinner, Page } from './components/ui';
import { useMe } from './hooks/useMe';
import ApiKeys from './routes/ApiKeys';
import Chat from './routes/Chat';
import History from './routes/History';
import KbDetail from './routes/KbDetail';
import KnowledgeBases from './routes/KnowledgeBases';
import Login from './routes/Login';
import Profile from './routes/Profile';
import Settings from './routes/Settings';
import SharePublic from './routes/SharePublic';

function RequireAuth() {
  const { data: me, isLoading, error } = useMe();
  const location = useLocation();
  if (isLoading) return <FullPageSpinner />;
  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-muted">
        Can't reach the server. Check that it's running, then reload.
      </div>
    );
  }
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <AppShell />;
}

function NotFound() {
  return (
    <>
      <Topbar title="Not found" />
      <Page>
        <div className="text-muted">
          There's nothing at this address. <Link to="/">Go to chat</Link>
        </div>
      </Page>
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/s/:token" element={<SharePublic />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Chat />} />
        <Route path="kbs" element={<KnowledgeBases />} />
        <Route path="kbs/:id" element={<KbDetail />} />
        <Route path="history" element={<History />} />
        <Route path="keys" element={<ApiKeys />} />
        <Route path="settings" element={<Settings />} />
        <Route path="profile" element={<Profile />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
