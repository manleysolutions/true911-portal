import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { pagesConfig } from './pages.config'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';

// Public pages — no auth, no sidebar layout
import LandingPage from './pages/public/LandingPage';
import GetStarted from './pages/public/GetStarted';
import Quote from './pages/public/Quote';
import AuthGate from './pages/AuthGate';

const { Pages, Layout } = pagesConfig;

const LayoutWrapper = ({ children, currentPageName }) => Layout ?
  <Layout currentPageName={currentPageName}>{children}</Layout>
  : <>{children}</>;

const AuthenticatedApp = () => {
  const { isLoadingAuth } = useAuth();

  if (isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <Routes>
      {Object.entries(Pages).map(([path, Page]) => (
        <Route
          key={path}
          path={`/${path}`}
          element={
            <LayoutWrapper currentPageName={path}>
              <Page />
            </LayoutWrapper>
          }
        />
      ))}
      {/* Lowercase aliases — e.g. /admin -> /Admin, /overview -> /Overview */}
      {Object.entries(Pages).map(([path, Page]) => {
        const lower = path.toLowerCase();
        if (lower !== path) {
          return (
            <Route
              key={`lower-${path}`}
              path={`/${lower}`}
              element={
                <LayoutWrapper currentPageName={path}>
                  <Page />
                </LayoutWrapper>
              }
            />
          );
        }
        return null;
      })}
      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};


function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <Routes>
            {/* Public routes — no auth required, no sidebar layout */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<AuthGate />} />
            <Route path="/get-started" element={<GetStarted />} />
            <Route path="/quote" element={<Quote />} />

            {/* Authenticated app routes (includes /AuthGate for backwards compat) */}
            <Route path="/*" element={<AuthenticatedApp />} />
          </Routes>
        </Router>
        <Toaster />
      </QueryClientProvider>
    </AuthProvider>
  )
}

export default App
