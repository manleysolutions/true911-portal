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
import DeploymentMap from './pages/DeploymentMap';
import Incidents from './pages/Incidents';
import Notifications from './pages/Notifications';
import Overview from './pages/Overview';
import Reports from './pages/Reports';
import Sites from './pages/Sites';
import SyncStatus from './pages/SyncStatus';
import __Layout from './Layout.jsx';


export const PAGES = {
    "Admin": Admin,
    "AuthGate": AuthGate,
    "Containers": Containers,
    "DeploymentMap": DeploymentMap,
    "Incidents": Incidents,
    "Notifications": Notifications,
    "Overview": Overview,
    "Reports": Reports,
    "Sites": Sites,
    "SyncStatus": SyncStatus,
}

export const pagesConfig = {
    mainPage: "AuthGate",
    Pages: PAGES,
    Layout: __Layout,
};