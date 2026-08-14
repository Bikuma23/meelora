import { Maximize } from "lucide-react";

export function PresentationButton({ className = "" }) {
  const toggle = () => {
    const el = document.documentElement;
    if (!document.fullscreenElement) {
      try { el.requestFullscreen?.(); } catch (e) { /* ignore */ }
      window.dispatchEvent(new CustomEvent("acct-presentation", { detail: true }));
    } else {
      try { document.exitFullscreen?.(); } catch (e) { /* ignore */ }
      window.dispatchEvent(new CustomEvent("acct-presentation", { detail: false }));
    }
  };
  return (
    <button onClick={toggle} data-testid="presentation-btn" title="Mode plein écran / présentation"
      className={`inline-flex items-center justify-center rounded-full border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50 ${className}`}>
      <Maximize size={15} className="text-[#22C55E]" />
    </button>
  );
}
