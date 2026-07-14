import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Pencil, Trash2, Search, Building2, Info, Upload, Download } from "lucide-react";
import { toast } from "sonner";
import ImportErrorsDialog from "../components/ImportErrorsDialog";

const PL_GROUPS = ["Projets", "Services", "Ventes", "Marketing", "RH", "Administration", "Informatique", "Opération Commun (FGF)"];
const empty = { code: "", description: "", superviseur: "", compte_gl: "", groupe_pl: "Services", gl_boni: "" };

function DeptForm({ open, onOpenChange, initial, onSubmit }) {
  const [f, setF] = useState(empty);
  const [errors, setErrors] = useState({});
  useEffect(() => {
    setF(initial ? { ...initial } : empty);
    setErrors({});
  }, [initial, open]);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  const submit = () => {
    const e = {};
    ["code", "description", "superviseur", "compte_gl", "groupe_pl"].forEach((k) => { if (!String(f[k]).trim()) e[k] = "Requis"; });
    setErrors(e);
    if (Object.keys(e).length) { toast.error("Champs obligatoires manquants"); return; }
    onSubmit({
      code: f.code.trim(), description: f.description.trim(), superviseur: f.superviseur.trim(),
      compte_gl: f.compte_gl.trim(), groupe_pl: f.groupe_pl, gl_boni: (f.gl_boni || "").trim(), csst: initial?.csst ?? 0,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="dept-form-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Building2 size={18} className="text-[#063044]" /> {initial ? "Modifier le département" : "Nouveau département"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <p className="flex items-center gap-1.5 text-xs font-700 uppercase tracking-wide text-slate-500"><Info size={13} /> Identification</p>
          {[["code", "Code"], ["description", "Description"], ["superviseur", "Superviseur"]].map(([k, lbl]) => (
            <div key={k}>
              <Label className="text-xs">{lbl} <span className="text-red-500">*</span></Label>
              <Input data-testid={`dept-${k}`} className="mt-1" value={f[k]} onChange={(e) => set(k, e.target.value)} />
              {errors[k] && <p className="mt-1 text-[11px] text-red-500">{errors[k]}</p>}
            </div>
          ))}
          <p className="flex items-center gap-1.5 pt-1 text-xs font-700 uppercase tracking-wide text-slate-500"><Info size={13} /> Comptabilité</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Compte GL <span className="text-red-500">*</span></Label>
              <Input data-testid="dept-compte_gl" className="mt-1 font-mono-data" value={f.compte_gl} onChange={(e) => set("compte_gl", e.target.value)} />
              {errors.compte_gl && <p className="mt-1 text-[11px] text-red-500">{errors.compte_gl}</p>}
            </div>
            <div>
              <Label className="text-xs">Groupe P&L <span className="text-red-500">*</span></Label>
              <Select value={f.groupe_pl} onValueChange={(v) => set("groupe_pl", v)}>
                <SelectTrigger data-testid="dept-groupe_pl" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>{PL_GROUPS.map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label className="text-xs">Compte GL Boni <span className="text-slate-400">(optionnel)</span></Label>
            <Input data-testid="dept-gl_boni" className="mt-1 font-mono-data" placeholder="Ex. 5006099" value={f.gl_boni} onChange={(e) => set("gl_boni", e.target.value)} />
            <p className="mt-1 text-[11px] text-slate-400">Compte vers lequel le boni et ses charges sociales sont extraits dans l'état des résultats (P&L).</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="dept-save-btn" className="bg-[#063044] hover:bg-[#063044]/90" onClick={submit}>{initial ? "Mettre à jour" : "Créer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Departements() {
  const { user } = useAuth();
  const canEdit = ["admin", "editor"].includes(user?.role);
  const [depts, setDepts] = useState([]);
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState({ open: false, item: null });
  const [importErrors, setImportErrors] = useState({ open: false, errors: [], fileName: "" });

  const load = () => api.listDepartments().then(setDepts);
  useEffect(() => { load(); }, []);
  const fileRef = useRef();

  const onImport = async (ev) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    try {
      const res = await api.importDepartments(file);
      if (res.aborted || res.errors?.length) {
        setImportErrors({ open: true, errors: res.errors || [], fileName: file.name });
        toast.error(`Importation annulée — ${res.errors.length} erreur(s)`);
      } else {
        toast.success(`${res.inserted} département(s) importé(s)`);
        load();
      }
    } catch (e) { toast.error(e.response?.data?.detail || "Import échoué"); }
    finally { ev.target.value = ""; }
  };

  const dlTemplate = async () => {
    try {
      const blob = await api.downloadTemplate("departments");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "modele_departements.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Téléchargement du modèle échoué"); }
  };

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return depts.filter((d) => [d.code, d.description, d.superviseur, d.compte_gl, d.groupe_pl].join(" ").toLowerCase().includes(q));
  }, [depts, query]);

  const submit = async (data) => {
    try {
      if (dialog.item) { await api.updateDepartment(dialog.item.id, data); toast.success("Département mis à jour"); }
      else { await api.createDepartment(data); toast.success("Département créé"); }
      setDialog({ open: false, item: null }); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); }
  };
  const del = async (d) => { await api.deleteDepartment(d.id); toast.success("Supprimé"); load(); };

  return (
    <div className="space-y-4" data-testid="departements-page">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500"><b className="text-slate-800">{filtered.length}</b> / {depts.length} départements</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" className="gap-1.5" data-testid="dept-template-btn" onClick={dlTemplate}><Download size={15} /> Modèle</Button>
          {canEdit && <>
          <input ref={fileRef} type="file" accept=".xlsx" className="hidden" data-testid="dept-import-input" onChange={onImport} />
          <Button variant="outline" className="gap-1.5" data-testid="dept-import-btn" onClick={() => fileRef.current?.click()}><Upload size={15} /> Importer Excel</Button>
          <Button data-testid="add-dept-btn" className="gap-1.5 bg-[#063044] hover:bg-[#063044]/90" onClick={() => setDialog({ open: true, item: null })}>
            <Plus size={16} /> Nouveau département
          </Button>
          </>}
        </div>
      </div>
      <div className="card flex items-center gap-2 px-4 py-2.5">
        <Search size={16} className="text-slate-400" />
        <input data-testid="dept-search" className="w-full bg-transparent text-sm outline-none" placeholder="Rechercher par code, description, superviseur…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3 text-left font-600">Code</th>
              <th className="px-4 py-3 text-left font-600">Description</th>
              <th className="px-4 py-3 text-left font-600">Superviseur</th>
              <th className="px-4 py-3 text-left font-600">Compte GL</th>
              <th className="px-4 py-3 text-left font-600">GL Boni</th>
              <th className="px-4 py-3 text-left font-600">Groupe P&L</th>
              <th className="px-4 py-3 text-right font-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`dept-row-${d.code}`}>
                <td className="px-4 py-3"><span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono-data text-xs font-600">{d.code}</span></td>
                <td className="px-4 py-3 font-600">{d.description}</td>
                <td className="px-4 py-3 text-slate-600">{d.superviseur}</td>
                <td className="px-4 py-3 font-mono-data text-slate-500">{d.compte_gl}</td>
                <td className="px-4 py-3 font-mono-data text-slate-500">{d.gl_boni || "—"}</td>
                <td className="px-4 py-3 text-slate-600">{d.groupe_pl}</td>
                <td className="px-4 py-3">
                  {canEdit ? (
                  <div className="flex justify-end gap-1">
                    <button data-testid={`edit-dept-${d.code}`} onClick={() => setDialog({ open: true, item: d })} className="p-1.5 text-slate-400 hover:text-[#063044]"><Pencil size={15} /></button>
                    <button data-testid={`delete-dept-${d.code}`} onClick={() => del(d)} className="p-1.5 text-slate-400 hover:text-red-500"><Trash2 size={15} /></button>
                  </div>
                  ) : <div className="text-right text-slate-300">—</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {dialog.open && <DeptForm open={dialog.open} onOpenChange={(v) => setDialog((p) => ({ ...p, open: v }))} initial={dialog.item} onSubmit={submit} />}
      <ImportErrorsDialog open={importErrors.open} onOpenChange={(v) => setImportErrors((p) => ({ ...p, open: v }))} errors={importErrors.errors} fileName={importErrors.fileName} />
    </div>
  );
}
