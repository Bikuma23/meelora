import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Save } from "lucide-react";
import { toast } from "sonner";

const GROUPS = [
  {
    title: "Charges sociales — part employeur",
    fields: [
      { k: "rrq_rate", label: "RRQ (taux)", type: "pct" },
      { k: "rrq_ceiling", label: "RRQ (max. assurable)", type: "money" },
      { k: "rrq_exemption", label: "RRQ (exemption)", type: "money" },
      { k: "ae_rate", label: "AE (taux)", type: "pct" },
      { k: "ae_ceiling", label: "AE (max. assurable)", type: "money" },
      { k: "rqap_rate", label: "RQAP (taux)", type: "pct" },
      { k: "rqap_ceiling", label: "RQAP (max. assurable)", type: "money" },
      { k: "fss_rate", label: "FSS (taux)", type: "pct" },
    ],
  },
  {
    title: "Assurance & REER (employés Réguliers)",
    fields: [
      { k: "assurance_annuelle", label: "Assurance collective ($/an)", type: "money" },
      { k: "reer_rate", label: "REER (taux)", type: "pct" },
    ],
  },
  {
    title: "Convention CCQ",
    fields: [
      { k: "ccq_rate", label: "Avantages sociaux CCQ (taux)", type: "pct" },
      { k: "ccq_electricien_compagnon_rate", label: "Prime électricien compagnon (taux)", type: "pct" },
    ],
  },
  {
    title: "Primes & allocations",
    fields: [
      { k: "prime_garde_cout_unitaire", label: "Coût unitaire d'une garde ($)", type: "money" },
      { k: "prime_garde_nb_annuel", label: "Nombre de gardes / an", type: "int" },
      { k: "prime_halo_rate", label: "Prime HALO (taux)", type: "pct" },
      { k: "prime_chef_equipe_montant", label: "Prime chef d'équipe ($)", type: "money" },
      { k: "alloc_securite_montant", label: "Allocation sécurité ($)", type: "money" },
    ],
  },
];

const toDisplay = (v, type) => (type === "pct" ? +(v * 100).toFixed(4) : v);
const fromDisplay = (v, type) => (type === "pct" ? Number(v) / 100 : Number(v));

export default function HypothesesPage() {
  const [hypo, setHypo] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.getHypotheses().then(setHypo); }, []);

  if (!hypo) return <p className="font-mono-data text-sm text-[#52525B]">Chargement…</p>;

  const setField = (k, v) => setHypo((p) => ({ ...p, [k]: v }));
  const setDept = (i, v) =>
    setHypo((p) => {
      const d = [...p.departments];
      d[i] = { ...d[i], csst: Number(v) / 100 };
      return { ...p, departments: d };
    });

  const save = async () => {
    setSaving(true);
    try {
      await api.updateHypotheses(hypo);
      toast.success("Hypothèses enregistrées");
    } catch {
      toast.error("Erreur d'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="hypotheses-page">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-2xl font-800 uppercase tracking-tight">Hypothèses {hypo.year}</h2>
          <p className="font-mono-data text-xs text-[#52525B]">Taux et paramètres alimentant tous les calculs budgétaires</p>
        </div>
        <Button data-testid="save-hypotheses-btn" onClick={save} disabled={saving} className="gap-1.5 rounded-none bg-[#0055FF] hover:bg-[#0055FF]/90">
          <Save size={16} /> {saving ? "Enregistrement…" : "Enregistrer"}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {GROUPS.map((g) => (
          <div key={g.title} className="border border-[#D4D4D8] bg-white p-5" data-testid={`hypo-group-${g.title}`}>
            <h3 className="mb-3 font-heading text-sm font-700 uppercase tracking-tight">{g.title}</h3>
            <div className="grid grid-cols-2 gap-3">
              {g.fields.map((fld) => (
                <div key={fld.k}>
                  <label className="text-[11px] font-600 uppercase tracking-wide text-[#52525B]">{fld.label}</label>
                  <Input
                    data-testid={`hypo-${fld.k}`}
                    type="number"
                    step={fld.type === "pct" ? "0.01" : "1"}
                    className="mt-1 rounded-none font-mono-data"
                    value={toDisplay(hypo[fld.k], fld.type)}
                    onChange={(e) => setField(fld.k, fromDisplay(e.target.value, fld.type))}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}

        <div className="border border-[#D4D4D8] bg-white p-5 lg:col-span-2" data-testid="hypo-departments">
          <h3 className="mb-3 font-heading text-sm font-700 uppercase tracking-tight">Départements — Taux CSST (%)</h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {hypo.departments.map((d, i) => (
              <div key={d.code} className="flex items-center gap-2 border border-[#F4F4F5] px-2 py-1.5">
                <span className="flex-1 text-[12px]">{d.code}</span>
                <Input
                  data-testid={`hypo-csst-${i}`}
                  type="number"
                  step="0.0001"
                  className="w-24 rounded-none font-mono-data text-xs"
                  value={+(d.csst * 100).toFixed(4)}
                  onChange={(e) => setDept(i, e.target.value)}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
