import { useEffect, useRef, useState } from "react";

// Cellule éditable par double-clic. Enter/blur = enregistrer, Échap = annuler.
// stopPropagation pour ne pas déclencher le clic de la ligne (ouverture du détail).
export function EditableCell({ value, display, canEdit, onSave, step = "0.01", testId }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState("");
  const ref = useRef();
  useEffect(() => {
    if (editing) { setVal(String(value ?? "")); setTimeout(() => { ref.current?.focus(); ref.current?.select(); }, 0); }
  }, [editing, value]);

  const commit = async () => {
    setEditing(false);
    const n = Number(val);
    if (val !== "" && !Number.isNaN(n) && n !== Number(value)) await onSave(n);
  };

  if (!canEdit) return <span className="font-mono-data">{display}</span>;
  if (editing) {
    return (
      <input ref={ref} data-testid={testId ? `${testId}-input` : undefined} type="number" step={step} value={val}
        onChange={(e) => setVal(e.target.value)} onBlur={commit} onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "Escape") setEditing(false); }}
        className="w-24 rounded border border-[#063044] bg-blue-50 px-1.5 py-0.5 text-right font-mono-data text-sm outline-none" />
    );
  }
  return (
    <span data-testid={testId} title="Double-cliquez pour modifier" onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
      className="cursor-text rounded px-1 font-mono-data hover:bg-blue-50 hover:ring-1 hover:ring-blue-200">
      {display}
    </span>
  );
}
