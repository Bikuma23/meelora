import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Pencil, Trash2, ShieldCheck, User as UserIcon } from "lucide-react";
import { toast } from "sonner";

const ROLE_LABEL = { admin: "Administrateur", editor: "Éditeur", user: "Utilisateur" };
const empty = { email: "", name: "", password: "", role: "user" };

function UserForm({ open, onOpenChange, initial, onSubmit }) {
  const { t } = useLang();
  const [f, setF] = useState(empty);
  const [err, setErr] = useState({});
  useEffect(() => { setF(initial ? { email: initial.email, name: initial.name, password: "", role: initial.role } : empty); setErr({}); }, [initial, open]);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const submit = () => {
    const e = {};
    if (!initial && !f.email.trim()) e.email = t("Courriel requis");
    if (!f.name.trim()) e.name = t("Nom requis");
    if (!initial && f.password.length < 6) e.password = t("6 caractères minimum");
    if (initial && f.password && f.password.length < 6) e.password = t("6 caractères minimum");
    setErr(e);
    if (Object.keys(e).length) return;
    if (initial) onSubmit({ name: f.name.trim(), role: f.role, ...(f.password ? { password: f.password } : {}) });
    else onSubmit({ email: f.email.trim(), name: f.name.trim(), password: f.password, role: f.role });
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="user-form-dialog">
        <DialogHeader>
          <DialogTitle>{initial ? `${t("Modifier")} — ${initial.name}` : t("Nouvel utilisateur")}</DialogTitle>
          <DialogDescription className="text-xs">{initial ? t("Laissez le mot de passe vide pour le conserver.") : t("Créez un compte Admin ou Utilisateur.")}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 py-1 sm:grid-cols-2">
          <div className="sm:col-span-2"><Label className="text-[11px] uppercase text-slate-500">{t("Courriel")}</Label>
            <Input data-testid="user-email" type="email" disabled={!!initial} value={f.email} onChange={(e) => set("email", e.target.value)} />
            {err.email && <p className="mt-1 text-[11px] text-red-500">{err.email}</p>}</div>
          <div><Label className="text-[11px] uppercase text-slate-500">{t("Nom")}</Label>
            <Input data-testid="user-name" value={f.name} onChange={(e) => set("name", e.target.value)} />
            {err.name && <p className="mt-1 text-[11px] text-red-500">{err.name}</p>}</div>
          <div><Label className="text-[11px] uppercase text-slate-500">{t("Rôle")}</Label>
            <Select value={f.role} onValueChange={(v) => set("role", v)}>
              <SelectTrigger data-testid="user-role"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="user">{t("Utilisateur (lecture seule)")}</SelectItem><SelectItem value="editor">{t("Éditeur (modifie les données)")}</SelectItem><SelectItem value="admin">{t("Administrateur (accès complet)")}</SelectItem></SelectContent>
            </Select></div>
          <div className="sm:col-span-2"><Label className="text-[11px] uppercase text-slate-500">{initial ? t("Nouveau mot de passe (optionnel)") : t("Mot de passe")}</Label>
            <Input data-testid="user-password" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} />
            {err.password && <p className="mt-1 text-[11px] text-red-500">{err.password}</p>}</div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("Annuler")}</Button>
          <Button data-testid="user-save-btn" className="bg-[#063044] hover:bg-[#063044]/90" onClick={submit}>{t("Enregistrer")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Users() {
  const { user } = useAuth();
  const { t } = useLang();
  const [users, setUsers] = useState([]);
  const [dialog, setDialog] = useState({ open: false, item: null });
  const load = () => api.listUsers().then(setUsers).catch(() => toast.error(t("Accès refusé")));
  useEffect(() => { load(); }, []);

  const submit = async (data) => {
    try {
      if (dialog.item) { await api.updateUser(dialog.item.id, data); toast.success(t("Utilisateur mis à jour")); }
      else { await api.createUser(data); toast.success(t("Utilisateur créé")); }
      setDialog({ open: false, item: null }); load();
    } catch (e) { toast.error(e.response?.data?.detail || t("Erreur")); }
  };
  const del = async (u) => { try { await api.deleteUser(u.id); toast.success(t("Utilisateur supprimé")); load(); } catch (e) { toast.error(e.response?.data?.detail || t("Erreur")); } };

  return (
    <div className="space-y-4" data-testid="users-page">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500"><b className="text-slate-800">{users.length}</b> {t("compte(s) — l'admin gère les accès. Les utilisateurs ne peuvent pas modifier un budget verrouillé.")}</p>
        <Button data-testid="add-user-btn" className="gap-1.5 bg-[#063044] hover:bg-[#063044]/90" onClick={() => setDialog({ open: true, item: null })}><Plus size={16} /> {t("Ajouter")}</Button>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3 text-left font-600">{t("Nom")}</th><th className="px-4 py-3 text-left font-600">{t("Courriel")}</th>
              <th className="px-4 py-3 text-left font-600">{t("Rôle")}</th><th className="px-4 py-3 text-right font-600">{t("Actions")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`user-row-${u.email}`}>
                <td className="px-4 py-2.5 font-600">{u.name}{u.id === user?.id && <span className="ml-2 text-[10px] text-slate-400">{t("(vous)")}</span>}</td>
                <td className="px-4 py-2.5 font-mono-data text-[13px] text-slate-600">{u.email}</td>
                <td className="px-4 py-2.5">
                  <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-700 uppercase ${u.role === "admin" ? "bg-[#063044] text-white" : u.role === "editor" ? "bg-[#0E9488] text-white" : "bg-slate-200 text-slate-600"}`}>
                    {u.role === "admin" ? <ShieldCheck size={11} /> : <UserIcon size={11} />}{t(ROLE_LABEL[u.role])}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-1">
                    <button data-testid={`edit-user-${u.email}`} onClick={() => setDialog({ open: true, item: u })} className="p-1.5 text-slate-400 hover:text-[#063044]"><Pencil size={15} /></button>
                    <button data-testid={`delete-user-${u.email}`} onClick={() => del(u)} className="p-1.5 text-slate-400 hover:text-red-500"><Trash2 size={15} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && <tr><td colSpan={4} className="px-4 py-10 text-center text-sm text-slate-500">{t("Aucun utilisateur.")}</td></tr>}
          </tbody>
        </table>
      </div>
      {dialog.open && <UserForm open={dialog.open} onOpenChange={(v) => setDialog((p) => ({ ...p, open: v }))} initial={dialog.item} onSubmit={submit} />}
    </div>
  );
}
