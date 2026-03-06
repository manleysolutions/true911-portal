import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export default function ReadinessTrend({ currentScore, previousScore }) {
  if (previousScore == null) return null;

  const delta = currentScore - previousScore;
  const absDelta = Math.abs(delta);

  if (absDelta < 1) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-slate-500 font-medium">
        <Minus className="w-3 h-3" /> Stable
      </span>
    );
  }

  if (delta > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-medium">
        <TrendingUp className="w-3 h-3" /> +{absDelta}%
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-red-400 font-medium">
      <TrendingDown className="w-3 h-3" /> -{absDelta}%
    </span>
  );
}
