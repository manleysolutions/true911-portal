import { Link } from "react-router-dom";
import { ArrowLeft, FileSpreadsheet, Upload, Building2, Cpu, Users, ClipboardCheck, LinkIcon } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { createPageUrl } from "@/utils";

export default function AdminImports() {
  const { can } = useAuth();

  if (!can("VIEW_ADMIN")) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-4xl mb-3">&#128274;</div>
            <div className="text-lg font-semibold text-gray-800">Admin Access Required</div>
            <div className="text-sm text-gray-500 mt-1">This section is only accessible to Admin and SuperAdmin users.</div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-4xl mx-auto">
        <Link to={createPageUrl("Admin")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 mb-4">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Admin
        </Link>

        <div className="flex items-center gap-2 mb-1">
          <Upload className="w-5 h-5 text-red-600" />
          <h1 className="text-2xl font-bold text-gray-900">Import Tools</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">Import sites, systems, devices, and vendors from CSV files.</p>

        <div className="grid gap-4 sm:grid-cols-2">
          {/* Site Import (new multi-system importer) */}
          <Link
            to={createPageUrl("SiteImport")}
            className="bg-white border border-gray-200 rounded-xl p-5 hover:border-red-300 hover:shadow-md transition-all group"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-red-50 rounded-lg flex items-center justify-center group-hover:bg-red-100 transition-colors">
                <Upload className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Site Import</h3>
                <p className="text-xs text-gray-500">Multi-system CSV onboarding</p>
              </div>
            </div>
            <p className="text-xs text-gray-600 mb-3">
              Import sites with systems, devices, vendors, and verification schedules.
              Each row represents one system at one site.
            </p>
            <div className="flex flex-wrap gap-1.5">
              <ImportBadge icon={Building2} label="Sites" />
              <ImportBadge icon={Cpu} label="Devices" />
              <ImportBadge icon={Users} label="Vendors" />
              <ImportBadge icon={ClipboardCheck} label="Verifications" />
            </div>
          </Link>

          {/* Bulk Deploy (legacy site importer) */}
          <Link
            to={createPageUrl("BulkDeploy")}
            className="bg-white border border-gray-200 rounded-xl p-5 hover:border-blue-300 hover:shadow-md transition-all group"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center group-hover:bg-blue-100 transition-colors">
                <FileSpreadsheet className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Bulk Site Import</h3>
                <p className="text-xs text-gray-500">Simple site-only CSV</p>
              </div>
            </div>
            <p className="text-xs text-gray-600 mb-3">
              Quick import of site records with optional template assignment.
              One row per site, no device or vendor data.
            </p>
            <div className="flex flex-wrap gap-1.5">
              <ImportBadge icon={Building2} label="Sites" />
            </div>
          </Link>
          {/* Bulk Device Assignment */}
          <Link
            to={createPageUrl("DeviceAssignment")}
            className="bg-white border border-gray-200 rounded-xl p-5 hover:border-amber-300 hover:shadow-md transition-all group"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-amber-50 rounded-lg flex items-center justify-center group-hover:bg-amber-100 transition-colors">
                <LinkIcon className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Device Assignment</h3>
                <p className="text-xs text-gray-500">Bulk device-to-site mapping</p>
              </div>
            </div>
            <p className="text-xs text-gray-600 mb-3">
              Assign Verizon-synced devices to customer sites in bulk using a CSV worksheet.
              Match by ICCID, IMEI, or MSISDN.
            </p>
            <div className="flex flex-wrap gap-1.5">
              <ImportBadge icon={Cpu} label="Devices" />
              <ImportBadge icon={Building2} label="Sites" />
            </div>
          </Link>
        </div>
      </div>
    </PageWrapper>
  );
}

function ImportBadge({ icon: Icon, label }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium text-gray-600 bg-gray-100 rounded-full">
      <Icon className="w-3 h-3" /> {label}
    </span>
  );
}
