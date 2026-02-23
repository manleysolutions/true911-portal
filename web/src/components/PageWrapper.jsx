import { useAuth } from "./AuthContext";
import { createPageUrl } from "@/utils";
import { useEffect } from "react";

export default function PageWrapper({ children, requiredRole }) {
  const { user, ready } = useAuth();

  useEffect(() => {
    if (ready && !user) {
      window.location.href = createPageUrl("AuthGate");
    }
  }, [user, ready]);

  if (!ready) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!user) return null;

  if (requiredRole && user.role !== requiredRole) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="text-4xl mb-3">🔒</div>
          <div className="text-lg font-semibold text-gray-800">Access Restricted</div>
          <div className="text-sm text-gray-500 mt-1">This section requires {requiredRole} access.</div>
        </div>
      </div>
    );
  }

  return children;
}