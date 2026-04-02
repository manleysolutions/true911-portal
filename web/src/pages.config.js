/**
 * pages.config.js - Page routing configuration
 * 
 * This file is AUTO-GENERATED. Do not add imports or modify PAGES manually.
 * Pages are auto-registered when you create files in the ./pages/ folder.
 * 
 * THE ONLY EDITABLE VALUE: mainPage
 * This controls which page is the landing page (shown when users visit the app).
 * 
 * Example file structure:
 * 
 *   import HomePage from './pages/HomePage';
 *   import Dashboard from './pages/Dashboard';
 *   import Settings from './pages/Settings';
 *   
 *   export const PAGES = {
 *       "HomePage": HomePage,
 *       "Dashboard": Dashboard,
 *       "Settings": Settings,
 *   }
 *   
 *   export const pagesConfig = {
 *       mainPage: "HomePage",
 *       Pages: PAGES,
 *   };
 * 
 * Example with Layout (wraps all pages):
 *
 *   import Home from './pages/Home';
 *   import Settings from './pages/Settings';
 *   import __Layout from './Layout.jsx';
 *
 *   export const PAGES = {
 *       "Home": Home,
 *       "Settings": Settings,
 *   }
 *
 *   export const pagesConfig = {
 *       mainPage: "Home",
 *       Pages: PAGES,
 *       Layout: __Layout,
 *   };
 *
 * To change the main page from HomePage to Dashboard, use find_replace:
 *   Old: mainPage: "HomePage",
 *   New: mainPage: "Dashboard",
 *
 * The mainPage value must match a key in the PAGES object exactly.
 */
import Admin from './pages/Admin';
import AdminTenants from './pages/AdminTenants';
import AdminUsers from './pages/AdminUsers';
import AdminImports from './pages/AdminImports';
import AuthGate from './pages/AuthGate';
import BulkDeploy from './pages/BulkDeploy';
import Command from './pages/Command';
import CommandSite from './pages/CommandSite';
import Containers from './pages/Containers';
import Customers from './pages/Customers';
import Devices from './pages/Devices';
import DeploymentMap from './pages/DeploymentMap';
import E911 from './pages/E911';
import Events from './pages/Events';
import Incidents from './pages/Incidents';
import IntegrationSync from './pages/IntegrationSync';
import Lines from './pages/Lines';
import Notifications from './pages/Notifications';
import OnboardingWizard from './pages/OnboardingWizard';
import OperatorView from './pages/OperatorView';
import OrgSettings from './pages/OrgSettings';
import Overview from './pages/Overview';
import Providers from './pages/Providers';
import Recordings from './pages/Recordings';
import Reports from './pages/Reports';
import Samantha from './pages/Samantha';
import Sites from './pages/Sites';
import SyncStatus from './pages/SyncStatus';
import NetworkDashboard from './pages/NetworkDashboard';
import AutoOps from './pages/AutoOps';
import SimManagement from './pages/SimManagement';
import SiteImport from './pages/SiteImport';
import DeviceAssignment from './pages/DeviceAssignment';
import SiteOnboarding from './pages/SiteOnboarding';
import SiteDetail from './pages/SiteDetail';
import ProvisioningQueue from './pages/ProvisioningQueue';
import VolaIntegration from './pages/VolaIntegration';
import Pr12QuickDeploy from './pages/Pr12QuickDeploy';
import ProvisionDeployment from './pages/ProvisionDeployment';
import SubscriberImport from './pages/SubscriberImport';
import ImportVerification from './pages/ImportVerification';
import ManagerDashboard from './pages/ManagerDashboard';
import AdminDashboard from './pages/AdminDashboard';
import UserDashboard from './pages/UserDashboard';
import AutomationDashboard from './pages/AutomationDashboard';
import OnboardSite from './pages/OnboardSite';
import Install from './pages/Install';
import __Layout from './Layout.jsx';


export const PAGES = {
    "Admin": Admin,
    "AdminTenants": AdminTenants,
    "AdminUsers": AdminUsers,
    "AdminImports": AdminImports,
    "AuthGate": AuthGate,
    "BulkDeploy": BulkDeploy,
    "Command": Command,
    "CommandSite": CommandSite,
    "Containers": Containers,
    "Customers": Customers,
    "Devices": Devices,
    "DeploymentMap": DeploymentMap,
    "E911": E911,
    "Events": Events,
    "Incidents": Incidents,
    "IntegrationSync": IntegrationSync,
    "Lines": Lines,
    "Notifications": Notifications,
    "OnboardingWizard": OnboardingWizard,
    "OperatorView": OperatorView,
    "OrgSettings": OrgSettings,
    "Overview": Overview,
    "Providers": Providers,
    "Recordings": Recordings,
    "Reports": Reports,
    "Samantha": Samantha,
    "Sites": Sites,
    "SyncStatus": SyncStatus,
    "NetworkDashboard": NetworkDashboard,
    "AutoOps": AutoOps,
    "SimManagement": SimManagement,
    "SiteImport": SiteImport,
    "DeviceAssignment": DeviceAssignment,
    "SiteOnboarding": SiteOnboarding,
    "SiteDetail": SiteDetail,
    "ProvisioningQueue": ProvisioningQueue,
    "VolaIntegration": VolaIntegration,
    "Pr12QuickDeploy": Pr12QuickDeploy,
    "ProvisionDeployment": ProvisionDeployment,
    "SubscriberImport": SubscriberImport,
    "ImportVerification": ImportVerification,
    "ManagerDashboard": ManagerDashboard,
    "AdminDashboard": AdminDashboard,
    "UserDashboard": UserDashboard,
    "AutomationDashboard": AutomationDashboard,
    "OnboardSite": OnboardSite,
    "Install": Install,
}

export const pagesConfig = {
    mainPage: null,  // Landing page is handled by App.jsx public routes
    Pages: PAGES,
    Layout: __Layout,
};