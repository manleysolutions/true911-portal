import { useState } from "react";
import { Phone, CheckCircle, Loader2 } from "lucide-react";

export default function CustomerHelpRequestCard({ onRequestHelp, loading }) {
  const [submitted, setSubmitted] = useState(false);

  const handleClick = async () => {
    await onRequestHelp();
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="bg-white rounded-xl border border-emerald-200 p-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 bg-emerald-50 rounded-lg flex items-center justify-center flex-shrink-0">
            <CheckCircle className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-emerald-700">Support Request Submitted</h3>
            <p className="text-xs text-gray-500 mt-1 leading-relaxed">
              We've included the checks already completed so you don't need to repeat anything.
              Our team will follow up shortly.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 bg-gray-50 rounded-lg flex items-center justify-center flex-shrink-0">
          <Phone className="w-5 h-5 text-gray-600" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-800">Talk to a Person</h3>
          <p className="text-xs text-gray-500 mt-1 leading-relaxed mb-3">
            Connect with our support team. We'll include your conversation history
            so you don't have to start over.
          </p>
          <button
            onClick={handleClick}
            disabled={loading}
            className="w-full text-xs font-medium text-white bg-gray-800 hover:bg-gray-900 disabled:bg-gray-400 py-2 rounded-lg transition-colors flex items-center justify-center gap-1.5"
          >
            {loading
              ? <><Loader2 className="w-3 h-3 animate-spin" /> Submitting...</>
              : <><Phone className="w-3 h-3" /> Request Human Help</>
            }
          </button>
        </div>
      </div>
    </div>
  );
}
