import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { AlertTriangle } from "lucide-react";

export default function ImportErrorsDialog({ open, onOpenChange, errors = [], fileName = "" }) {
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
          <Button data-testid="import-errors-close-btn" onClick={() => onOpenChange(false)} className="bg-[#2563EB] hover:bg-[#2563EB]/90">
            J'ai compris
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
