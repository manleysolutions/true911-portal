import { Sparkles } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";

export default function Samantha() {
  return (
    <PageWrapper>
      <div className="p-6 max-w-3xl mx-auto">
        <div className="text-center py-20">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-purple-100 rounded-2xl mb-4">
            <Sparkles className="w-8 h-8 text-purple-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Samantha AI</h1>
          <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
            AI-assisted onboarding, anomaly detection, and natural language event queries.
            This feature is coming soon.
          </p>
          <div className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-purple-50 border border-purple-200 rounded-xl text-sm text-purple-700 font-medium">
            <Sparkles className="w-4 h-4" />
            Coming Soon
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
