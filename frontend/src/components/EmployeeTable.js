import { useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "./ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "./ui/select";
import { Pencil, Trash2, Plus } from "lucide-react";
import { formatCurrency } from "../lib/calculations";
import { toast } from "sonner";

const TRADE_TYPE = {
  Électricien: "CCQ",
  Frigoriste: "CCQ",
  Admin: "Standard",
};

const empty = { name: "", trade: "Électricien", base_hourly_rate: 48, base_monthly_salary: 0, active_hours_per_week: 40 };

function EmployeeForm({ open, onOpenChange, initial, onSubmit }) {
  const [form, setForm] = useState(initial || empty);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const submit = () => {
    if (!form.name.trim()) return toast.error("Le nom est requis");
    const type = TRADE_TYPE[form.trade];
    onSubmit({
      name: form.name.trim(),
      type,
      trade: form.trade,
      base_hourly_rate: Number(form.base_hourly_rate) || 0,
      base_monthly_salary: type === "Standard" ? Number(form.base_monthly_salary) || 0 : 0,
      active_hours_per_week: Number(form.active_hours_per_week) || 40,
    });
  };

  const isStandard = TRADE_TYPE[form.trade] === "Standard";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-none border border-[#09090B] sm:max-w-md" data-testid="employee-form-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading uppercase tracking-tight">
            {initial ? "Modifier l'employé" : "Nouvel employé"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#52525B]">Nom complet</Label>
            <Input
              data-testid="employee-name-input"
              className="mt-1 rounded-none"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#52525B]">Métier</Label>
            <Select value={form.trade} onValueChange={(v) => set("trade", v)}>
              <SelectTrigger data-testid="employee-trade-select" className="mt-1 rounded-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Électricien">Électricien (CCQ)</SelectItem>
                <SelectItem value="Frigoriste">Frigoriste (CCQ)</SelectItem>
                <SelectItem value="Admin">Admin / Bureau (Standard)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {isStandard ? (
            <div>
              <Label className="text-xs uppercase tracking-wide text-[#52525B]">Salaire mensuel ($)</Label>
              <Input
                data-testid="employee-monthly-input"
                type="number"
                className="mt-1 rounded-none font-mono-data"
                value={form.base_monthly_salary}
                onChange={(e) => set("base_monthly_salary", e.target.value)}
              />
            </div>
          ) : (
            <div>
              <Label className="text-xs uppercase tracking-wide text-[#52525B]">Taux horaire ($/h)</Label>
              <Input
                data-testid="employee-hourly-input"
                type="number"
                className="mt-1 rounded-none font-mono-data"
                value={form.base_hourly_rate}
                onChange={(e) => set("base_hourly_rate", e.target.value)}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-none" onClick={() => onOpenChange(false)}>
            Annuler
          </Button>
          <Button
            data-testid="employee-save-btn"
            className="rounded-none bg-[#0055FF] hover:bg-[#0055FF]/90"
            onClick={submit}
          >
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function EmployeeTable({ employees, onCreate, onUpdate, onDelete }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const openNew = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (emp) => { setEditing(emp); setDialogOpen(true); };

  const handleSubmit = async (data) => {
    if (editing) {
      await onUpdate(editing.id, data);
      toast.success("Employé mis à jour");
    } else {
      await onCreate(data);
      toast.success("Employé ajouté");
    }
    setDialogOpen(false);
  };

  return (
    <div className="border border-[#D4D4D8] bg-white" data-testid="employee-table">
      <div className="flex items-center justify-between border-b border-[#D4D4D8] p-4">
        <h2 className="font-heading text-sm font-700 uppercase tracking-tight">
          Effectif ({employees.length})
        </h2>
        <Button
          data-testid="add-employee-btn"
          onClick={openNew}
          className="h-8 gap-1.5 rounded-none bg-[#09090B] text-xs uppercase hover:bg-[#09090B]/90"
        >
          <Plus size={14} /> Ajouter
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#D4D4D8] text-[11px] uppercase tracking-wider text-[#52525B]">
              <th className="px-4 py-2 text-left font-600">Nom</th>
              <th className="px-4 py-2 text-left font-600">Métier</th>
              <th className="px-4 py-2 text-left font-600">Type</th>
              <th className="px-4 py-2 text-right font-600">Taux / Salaire</th>
              <th className="px-4 py-2 text-right font-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {employees.map((e) => (
              <tr key={e.id} className="border-b border-[#F4F4F5] hover:bg-[#F4F4F5]" data-testid={`employee-row-${e.id}`}>
                <td className="px-4 py-2.5 font-medium">{e.name}</td>
                <td className="px-4 py-2.5">{e.trade}</td>
                <td className="px-4 py-2.5">
                  <span
                    className="px-1.5 py-0.5 text-[10px] font-600 uppercase text-white"
                    style={{ backgroundColor: e.type === "CCQ" ? "#0055FF" : "#09090B" }}
                  >
                    {e.type}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-mono-data">
                  {e.type === "Standard"
                    ? `${formatCurrency(e.base_monthly_salary)}/mois`
                    : `${e.base_hourly_rate.toFixed(2)} $/h`}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-1">
                    <button
                      data-testid={`edit-employee-${e.id}`}
                      onClick={() => openEdit(e)}
                      className="p-1.5 text-[#52525B] transition-colors hover:text-[#0055FF]"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      data-testid={`delete-employee-${e.id}`}
                      onClick={async () => { await onDelete(e.id); toast.success("Employé supprimé"); }}
                      className="p-1.5 text-[#52525B] transition-colors hover:text-[#FF4500]"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {dialogOpen && (
        <EmployeeForm
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          initial={editing}
          onSubmit={handleSubmit}
        />
      )}
    </div>
  );
}
