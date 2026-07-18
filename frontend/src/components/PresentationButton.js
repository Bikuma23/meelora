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
      className={`inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-xs font-600 text-slate-500 hover:bg-slate-50 ${className}`}>
      <Maximize size={13} className="text-[#0E9488]" /> Présentation
    </button>
  );
}
