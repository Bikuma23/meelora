import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Pencil, ShieldCheck, User as UserIcon, Building2, Ban, RotateCcw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { UserAvatar } from "../components/UserAvatar";

const ROLE_LABEL = { admin: "Administrateur", user: "Utilisateur" };
const empty = { email: "", name: "", password: "", role: "user" };

function UserForm({ open, onOpenChange, initial, onSubmit }) {
  const { t } = useLang();
  const [f, setF] = useState(empty);
  const [err, setErr] = useState({});
  useEffect(() => {
    setF(initial ? { email: initial.email, name: initial.name, password: "", role: initial.role === "admin" ? "admin" : "user" } : empty);
    setErr({});
  }, [initial, open]);
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
          <DialogDescription className="text-xs">{initial ? t("Modifiez le profil utilisateur. Laissez le mot de passe vide pour le conserver.") : t("Créez un compte Administrateur ou Utilisateur.")}</DialogDescription>
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
              <SelectContent>
                <SelectItem value="user">{t("Utilisateur")}</SelectItem>
                <SelectItem value="admin">{t("Administrateur")}</SelectItem>
              </SelectContent>
            </Select></div>
          <div className="sm:col-span-2"><Label className="text-[11px] uppercase text-slate-500">{initial ? t("Nouveau mot de passe (optionnel)") : t("Mot de passe")}</Label>
            <Input data-testid="user-password" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} />
            {err.password && <p className="mt-1 text-[11px] text-red-500">{err.password}</p>}</div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("Annuler")}</Button>
          <Button data-testid="user-save-btn" className="bg-[#0F172A] hover:bg-[#0F172A]/90" onClick={submit}>{t("Enregistrer")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AccessDialog({ open, onOpenChange, selectedUser, onSaved }) {
  const { t } = useLang();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});

  useEffect(() => {
    if (!open || !selectedUser) return;
    setLoading(true);
    api.getUserCompanyAccess(selectedUser.id)
      .then((d) => {
        setData(d);
        setValues(Object.fromEntries((d.companies || []).map((c) => [c.company_id, c.access_role || "none"])));
      })
      .catch((e) => toast.error(e.response?.data?.detail || t("Impossible de charger les affectations")))
      .finally(() => setLoading(false));
  }, [open, selectedUser, t]);

  const save = async () => {
    const assignments = Object.entries(values)
      .filter(([, role]) => role === "principal" || role === "collaborator")
      .map(([company_id, access_role]) => ({ company_id, access_role }));
    setSaving(true);
    try {
      const d = await api.replaceUserCompanyAccess(selectedUser.id, assignments);
      setData(d);
      toast.success(t("Affectations mises à jour"));
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || t("Erreur lors de la mise à jour des accès"));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="user-access-dialog">
        <DialogHeader>
          <DialogTitle>{t("Accès sociétés")} — {selectedUser?.name}</DialogTitle>
          <DialogDescription className="text-xs">
            {data?.implicit_all
              ? t("Un administrateur a accès à toutes les sociétés de l'organisation.")
              : t("Définissez les sociétés visibles par cet utilisateur et son niveau de responsabilité.")}
          </DialogDescription>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400"><Loader2 className="mr-2 animate-spin" size={18} /> {t("Chargement...")}</div>
        ) : data?.implicit_all ? (
          <div className="rounded-xl border border-[#A7F3DD] bg-[#A7F3DD]/20 p-4 text-sm text-[#0F172A]">
            <div className="flex items-center gap-2 font-700"><ShieldCheck size={17} className="text-[#22C55E]" /> {t("Accès complet")}</div>
            <p className="mt-1 text-xs text-slate-500">{t("Aucune affectation individuelle n'est requise pour un administrateur.")}</p>
          </div>
        ) : (
          <div className="max-h-[55vh] space-y-2 overflow-auto pr-1">
            {(data?.companies || []).map((c) => (
              <div key={c.company_id} className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 px-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-600 text-[#0F172A]">{c.name}</p>
                  <p className="text-[11px] text-slate-400">{[c.company_code, c.jurisdiction].filter(Boolean).join(" · ") || c.company_id}</p>
                </div>
                <Select value={values[c.company_id] || "none"} onValueChange={(v) => setValues((p) => ({ ...p, [c.company_id]: v }))}>
                  <SelectTrigger className="w-[190px]" data-testid={`access-role-${c.company_id}`}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t("Aucun accès")}</SelectItem>
                    <SelectItem value="collaborator">{t("Collaborateur")}</SelectItem>
                    <SelectItem value="principal">{t("Responsable principal")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ))}
            {(data?.companies || []).length === 0 && <div className="py-10 text-center text-sm text-slate-400">{t("Aucune société active.")}</div>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("Fermer")}</Button>
          {!data?.implicit_all && <Button data-testid="save-user-access" disabled={loading || saving} className="bg-[#0F172A] hover:bg-[#0F172A]/90" onClick={save}>{saving && <Loader2 className="mr-2 animate-spin" size={14} />}{t("Enregistrer les accès")}</Button>}
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
  const [accessDialog, setAccessDialog] = useState({ open: false, item: null });
  const load = () => api.listUsers().then(setUsers).catch(() => toast.error(t("Accès refusé")));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (data) => {
    try {
      if (dialog.item) { await api.updateUser(dialog.item.id, data); toast.success(t("Utilisateur mis à jour")); }
      else { await api.createUser(data); toast.success(t("Utilisateur créé")); }
      setDialog({ open: false, item: null }); load();
    } catch (e) { toast.error(e.response?.data?.detail || t("Erreur")); }
  };

  const toggleStatus = async (u) => {
    try {
      if (u.status === "inactive") {
        await api.updateUser(u.id, { status: "active" });
        toast.success(t("Utilisateur réactivé"));
      } else {
        await api.deactivateUser(u.id);
        toast.success(t("Utilisateur désactivé"));
      }
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t("Erreur")); }
  };

  return (
    <div className="space-y-4" data-testid="users-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-600 text-[#0F172A]">{t("Utilisateurs & accès")}</p>
          <p className="mt-0.5 text-xs text-slate-500"><b className="text-slate-700">{users.length}</b> {t("compte(s) dans votre organisation. Les accès aux sociétés sont gérés individuellement.")}</p>
        </div>
        <Button data-testid="add-user-btn" className="gap-1.5 bg-[#0F172A] hover:bg-[#0F172A]/90" onClick={() => setDialog({ open: true, item: null })}><Plus size={16} /> {t("Ajouter")}</Button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3 text-left font-600">{t("Nom")}</th>
              <th className="px-4 py-3 text-left font-600">{t("Courriel")}</th>
              <th className="px-4 py-3 text-left font-600">{t("Rôle")}</th>
              <th className="px-4 py-3 text-left font-600">{t("Sociétés / Mandats")}</th>
              <th className="px-4 py-3 text-left font-600">{t("Statut")}</th>
              <th className="px-4 py-3 text-right font-600">{t("Actions")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={`border-b border-slate-100 hover:bg-slate-50 ${u.status === "inactive" ? "opacity-55" : ""}`} data-testid={`user-row-${u.email}`}>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <UserAvatar userId={u.id} name={u.name} role={u.role} size={30} />
                    <span className="font-600">{u.name}{u.id === user?.id && <span className="ml-2 text-[10px] text-slate-400">{t("(vous)")}</span>}</span>
                  </div>
                </td>
                <td className="px-4 py-2.5 font-mono-data text-[13px] text-slate-600">{u.email}</td>
                <td className="px-4 py-2.5">
                  <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-700 uppercase ${u.role === "admin" ? "bg-[#0F172A] text-white" : "bg-slate-200 text-slate-600"}`}>
                    {u.role === "admin" ? <ShieldCheck size={11} /> : <UserIcon size={11} />}{t(ROLE_LABEL[u.role] || ROLE_LABEL.user)}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  {u.role === "admin" ? (
                    <span className="text-xs font-600 text-[#22C55E]">{t("Toutes")}</span>
                  ) : (
                    <button disabled={u.status === "inactive"} onClick={() => setAccessDialog({ open: true, item: u })} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-600 text-slate-600 transition hover:border-[#22C55E]/40 hover:bg-[#A7F3DD]/20 hover:text-[#0F172A] disabled:cursor-not-allowed">
                      <Building2 size={13} className="text-[#22C55E]" /> {u.access_count || 0} {t("société(s)")}
                    </button>
                  )}
                </td>
                <td className="px-4 py-2.5"><span className={`inline-flex items-center gap-1.5 text-xs font-600 ${u.status === "inactive" ? "text-slate-400" : "text-[#15803D]"}`}><span className={`h-1.5 w-1.5 rounded-full ${u.status === "inactive" ? "bg-slate-300" : "bg-[#22C55E]"}`} />{u.status === "inactive" ? t("Inactif") : t("Actif")}</span></td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-1">
                    {u.role !== "admin" && u.status !== "inactive" && <button title={t("Gérer les accès")} data-testid={`access-user-${u.email}`} onClick={() => setAccessDialog({ open: true, item: u })} className="p-1.5 text-slate-400 hover:text-[#22C55E]"><Building2 size={15} /></button>}
                    <button title={t("Modifier")} data-testid={`edit-user-${u.email}`} onClick={() => setDialog({ open: true, item: u })} className="p-1.5 text-slate-400 hover:text-[#0F172A]"><Pencil size={15} /></button>
                    {u.id !== user?.id && <button title={u.status === "inactive" ? t("Réactiver") : t("Désactiver")} data-testid={`status-user-${u.email}`} onClick={() => toggleStatus(u)} className={`p-1.5 ${u.status === "inactive" ? "text-slate-400 hover:text-[#22C55E]" : "text-slate-400 hover:text-red-500"}`}>{u.status === "inactive" ? <RotateCcw size={15} /> : <Ban size={15} />}</button>}
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-500">{t("Aucun utilisateur.")}</td></tr>}
          </tbody>
        </table>
      </div>

      {dialog.open && <UserForm open={dialog.open} onOpenChange={(v) => setDialog((p) => ({ ...p, open: v }))} initial={dialog.item} onSubmit={submit} />}
      {accessDialog.open && <AccessDialog open={accessDialog.open} onOpenChange={(v) => setAccessDialog((p) => ({ ...p, open: v }))} selectedUser={accessDialog.item} onSaved={load} />}
    </div>
  );
}
