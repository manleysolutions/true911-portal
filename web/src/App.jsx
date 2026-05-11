import { useEffect } from "react";
import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { pagesConfig } from './pages.config'
import { BrowserRouter as Router, Route, Routes, Navigate, useNavigate } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { toast } from "sonner";

// Public pages — no auth, no sidebar layout
import LandingPage from './pages/public/LandingPage';
import GetStarted from './pages/public/GetStarted';
import Quote from './pages/public/Quote';
import True911Platform from './pages/public/True911Platform';
import Register from './pages/public/Register';
import RegistrationView from './pages/public/RegistrationView';
import RegistrationThanks from './pages/public/RegistrationThanks';
import AuthGate from './pages/AuthGate';

const { Pages, Layout } = pagesConfig;

// ── Route-level permission map ──────────────────────────────────
// Pages that require a specific permission to access.
// If the user lacks the permission, they are redirected to their
// role's default landing page instead of seeing a dead-end screen.
//
// DataEntry-allowed pages use granular permissions (VIEW_CUSTOMERS,
// VIEW_SITES, VIEW_DEVICES, COMMAND_SITE_IMPORT, etc.) so they are
// never accidentally locked behind VIEW_ADMIN.
const PAGE_PERMISSIONS = {
  // Admin-only pages
  Admin:               "VIEW_ADMIN",
  AdminUsers:          "VIEW_ADMIN",
  AdminTenants:        "VIEW_ADMIN",
  AdminImports:        "VIEW_ADMIN",
  AdminDashboard:      "VIEW_ADMIN",
  E911:                "VIEW_ADMIN",
  Notifications:       "MANAGE_NOTIFICATIONS",
  Providers:           "MANAGE_PROVIDERS",
  IntegrationSync:     "MANAGE_INTEGRATIONS",
  OrgSettings:         "VIEW_ADMIN",
  BulkDeploy:          "COMMAND_BULK_IMPORT",
  Install:             "MANAGE_DEVICES",
  OnboardSite:         "MANAGE_DEVICES",
  DeviceAssignment:    "MANAGE_DEVICES",
  ProvisionDeployment: "MANAGE_DEVICES",
  Pr12QuickDeploy:     "MANAGE_DEVICES",
  VolaIntegration:     "MANAGE_DEVICES",
  SupportConsole:      "VIEW_ADMIN",
  SelfHealingConsole:  "VIEW_ADMIN",

  // DataEntry-allowed onboarding pages — granular permissions
  Customers:           "VIEW_CUSTOMERS",
  Sites:               "VIEW_SITES",
  SiteDetail:          "VIEW_SITES",
  Devices:             "VIEW_DEVICES",
  SiteImport:          "COMMAND_SITE_IMPORT",
  SubscriberImport:    "SUBSCRIBER_IMPORT",
  ImportVerification:  "VIEW_IMPORT_VERIFICATION",
  ProvisioningQueue:   "VIEW_PROVISIONING_QUEUE",

  // Phase R3 — internal registration review queue
  Registrations:       "VIEW_REGISTRATIONS",
  RegistrationDetail:  "VIEW_REGISTRATIONS",
};

function getLandingPage(role) {
  const r = (role || "").toLowerCase();
  if (r === "superadmin") return "/Command";
  if (r === "admin") return "/AdminDashboard";
  if (r === "manager") return "/ManagerDashboard";
  if (r === "dataentry") return "/Customers";
  return "/UserDashboard";
}

const LayoutWrapper = ({ children, currentPageName }) => Layout ?
  <Layout currentPageName={currentPageName}>{children}</Layout>
  : <>{children}</>;

function PermissionRedirect({ role }) {
  const navigate = useNavigate();
  useEffect(() => {
    toast.error("You do not have permission to access that page.");
    navigate(getLandingPage(role), { replace: true });
  }, [role, navigate]);
  return null;
}

function ProtectedPage({ pageName, Page }) {
  const { can, user } = useAuth();
  const requiredPermission = PAGE_PERMISSIONS[pageName];

  if (requiredPermission && !can(requiredPermission)) {
    return <PermissionRedirect role={user?.role} />;
  }

  return (
    <LayoutWrapper currentPageName={pageName}>
      <Page />
    </LayoutWrapper>
  );
}

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
          element={<ProtectedPage pageName={path} Page={Page} />}
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
              element={<ProtectedPage pageName={path} Page={Page} />}
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
            <Route path="/true911-platform" element={<True911Platform />} />
            <Route path="/register" element={<Register />} />
            <Route path="/register/:registrationId/thanks" element={<RegistrationThanks />} />
            <Route path="/register/:registrationId" element={<RegistrationView />} />

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
