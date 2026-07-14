import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { AlertTriangle, Download } from "lucide-react";

export default function ImportErrorsDialog({ open, onOpenChange, errors = [], fileName = "" }) {
  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = [["Ligne Excel", "Élément", "Erreur"], ...errors.map((e) => [e.line ?? "", e.name || "", e.message || ""])];
    const csv = "\uFEFF" + rows.map((r) => r.map(esc).join(";")).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `erreurs_import_${(fileName || "fichier").replace(/\.[^.]+$/, "")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto" data-testid="import-errors-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle size={20} /> Importation annulée — {errors.length} erreur(s)
          </DialogTitle>
          <DialogDescription>
            Aucune donnée n'a été importée. Corrigez les erreurs ci-dessous dans le fichier
            {fileName ? ` « ${fileName} »` : ""} puis réimportez.
          </DialogDescription>
        </DialogHeader>

        <div className="overflow-hidden rounded-xl border border-red-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-red-200 bg-red-50 text-[11px] uppercase tracking-wider text-red-700">
                <th className="w-24 px-3 py-2 text-left font-700">Ligne Excel</th>
                <th className="px-3 py-2 text-left font-700">Élément</th>
                <th className="px-3 py-2 text-left font-700">Erreur</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((er, i) => (
                <tr key={i} className="border-b border-slate-100 last:border-0" data-testid={`import-error-row-${i}`}>
                  <td className="px-3 py-2 font-mono-data font-700 text-red-600">{er.line ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-600">{er.name || "—"}</td>
                  <td className="px-3 py-2 text-slate-800">{er.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <DialogFooter>
          <Button data-testid="import-errors-export-btn" variant="outline" onClick={exportCsv} className="gap-1.5">
            <Download size={15} /> Exporter les erreurs (CSV)
          </Button>
          <Button data-testid="import-errors-close-btn" onClick={() => onOpenChange(false)} className="bg-[#063044] hover:bg-[#063044]/90">
            J'ai compris
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
