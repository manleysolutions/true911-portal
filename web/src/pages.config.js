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
import AuthGate from './pages/AuthGate';
import Containers from './pages/Containers';
import Devices from './pages/Devices';
import DeploymentMap from './pages/DeploymentMap';
import E911 from './pages/E911';
import Events from './pages/Events';
import Incidents from './pages/Incidents';
import Lines from './pages/Lines';
import Notifications from './pages/Notifications';
import OnboardingWizard from './pages/OnboardingWizard';
import Overview from './pages/Overview';
import Providers from './pages/Providers';
import Recordings from './pages/Recordings';
import Reports from './pages/Reports';
import Samantha from './pages/Samantha';
import Sites from './pages/Sites';
import SyncStatus from './pages/SyncStatus';
import __Layout from './Layout.jsx';


export const PAGES = {
    "Admin": Admin,
    "AuthGate": AuthGate,
    "Containers": Containers,
    "Devices": Devices,
    "DeploymentMap": DeploymentMap,
    "E911": E911,
    "Events": Events,
    "Incidents": Incidents,
    "Lines": Lines,
    "Notifications": Notifications,
    "OnboardingWizard": OnboardingWizard,
    "Overview": Overview,
    "Providers": Providers,
    "Recordings": Recordings,
    "Reports": Reports,
    "Samantha": Samantha,
    "Sites": Sites,
    "SyncStatus": SyncStatus,
}

export const pagesConfig = {
    mainPage: "AuthGate",
    Pages: PAGES,
    Layout: __Layout,
};