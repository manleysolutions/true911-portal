import { lazy, Suspense } from "react";
import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '@/contexts/AuthContext';

// Public marketing pages are eager (first paint); everything behind login and the
// longer registration flow is split into lazy chunks.
import LandingPage from './pages/public/LandingPage';
import GetStarted from './pages/public/GetStarted';
import Quote from './pages/public/Quote';
import True911Platform from './pages/public/True911Platform';

const AuthenticatedApp = lazy(() => import('./AuthenticatedApp'));
const AuthGate = lazy(() => import('./pages/AuthGate'));
const Register = lazy(() => import('./pages/public/Register'));
const RegistrationView = lazy(() => import('./pages/public/RegistrationView'));
const RegistrationThanks = lazy(() => import('./pages/public/RegistrationThanks'));

function Loading() {
  return (
    <div className="fixed inset-0 flex items-center justify-center" role="status" aria-label="Loading">
      <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <Suspense fallback={<Loading />}>
            <Routes>
              {/* Public routes — no auth required, no sidebar layout */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<AuthGate />} />
              <Route path="/get-started" element={<GetStarted />} />
              <Route path="/quote" element={<Quote />} />
              <Route path="/true911-platform" element={<True911Platform />} />
              <Route path="/register" element={<Register />} />
              <Route path="/register/:registrationId/thanks" element={<RegistrationThanks />} />
              <Route path="/register/:registrationId" element={<RegistrationView />} />

              {/* Authenticated app routes (includes /AuthGate for backwards compat) */}
              <Route path="/*" element={<AuthenticatedApp />} />
            </Routes>
          </Suspense>
        </Router>
        <Toaster />
      </QueryClientProvider>
    </AuthProvider>
  )
}

export default App
