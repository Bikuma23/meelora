import { useEffect, useRef, useState } from "react";
import { Building2 } from "lucide-react";
import { api } from "../lib/api";

// Analyse the logo pixels (same-origin blob/dataURL → canvas not tainted) to pick
// a container background that keeps the logo readable, without asking the user for
// multiple versions. Falls back to a safe neutral background on any failure.
function analyzeImage(img) {
  try {
    const S = 40;
    const canvas = document.createElement("canvas");
    canvas.width = S; canvas.height = S;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.clearRect(0, 0, S, S);
    const r = Math.min(S / img.naturalWidth, S / img.naturalHeight) || 1;
    const w = img.naturalWidth * r, h = img.naturalHeight * r;
    ctx.drawImage(img, (S - w) / 2, (S - h) / 2, w, h);
    const data = ctx.getImageData(0, 0, S, S).data;
    let opaque = 0, transparent = 0, lumSum = 0;
    for (let i = 0; i < data.length; i += 4) {
      const a = data[i + 3];
      if (a < 24) { transparent++; continue; }
      opaque++;
      lumSum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    }
    const total = opaque + transparent || 1;
    if (opaque === 0) return { bg: "#F1F5F9" };            // empty → neutral fallback
    const avgLum = lumSum / opaque;                        // 0..255
    const transparencyRatio = transparent / total;
    let bg;
    if (avgLum >= 150) bg = "#0F172A";                     // light/white logo → dark bg
    else if (avgLum <= 110) bg = "#FFFFFF";                // dark logo → light bg
    else bg = "#F1F5F9";                                   // mid contrast → neutral
    // Transparent + mid luminance → prefer neutral to guarantee contrast.
    if (transparencyRatio > 0.6 && avgLum > 110 && avgLum < 150) bg = "#E2E8F0";
    return { bg };
  } catch (e) {
    return { bg: "#F1F5F9" };
  }
}

export function CompanyLogo({ cid, hasLogo, src, name, size = 40, rounded = "rounded-lg", testid = "company-logo", bare = false }) {
  const [url, setUrl] = useState(src || null);
  const [bg, setBg] = useState("#F1F5F9");
  const objRef = useRef(null);

  useEffect(() => {
    if (src !== undefined && src !== null) { setUrl(src); return; }
    let obj = null;
    if (cid && hasLogo) {
      api.getCompanyLogoBlob(cid).then((blob) => { obj = URL.createObjectURL(blob); objRef.current = obj; setUrl(obj); }).catch(() => setUrl(null));
    } else { setUrl(null); }
    return () => { if (obj) URL.revokeObjectURL(obj); };
  }, [cid, hasLogo, src]);

  const dim = { width: size, height: size };
  const onLoad = (e) => { const res = analyzeImage(e.target); if (res) setBg(res.bg); };

  // Bare mode: the logo blends directly into the page — no frame, no background,
  // ratio preserved (object-contain).
  if (bare) {
    if (!url) {
      return (
        <span data-testid={`${testid}-initials`} style={dim} className="flex items-center justify-center text-slate-400">
          {name ? <span className="text-2xl font-800 text-[#063044]">{name.trim().slice(0, 2).toUpperCase()}</span> : <Building2 size={size * 0.5} />}
        </span>
      );
    }
    return (
      <img src={url} alt={name || "logo"} data-testid={`${testid}-img`} draggable={false}
        style={{ maxHeight: size, maxWidth: size * 3.5 }} className="select-none object-contain object-left" />
    );
  }

  if (!url) {
    return (
      <span data-testid={`${testid}-initials`} style={dim}
        className={`flex items-center justify-center ${rounded} bg-slate-100 text-slate-400`}>
        {name ? <span className="text-xs font-800">{name.trim().slice(0, 2).toUpperCase()}</span> : <Building2 size={size * 0.45} />}
      </span>
    );
  }
  return (
    <span data-testid={`${testid}-frame`} style={{ ...dim, backgroundColor: bg }}
      className={`flex items-center justify-center overflow-hidden ${rounded} border border-slate-200/60 p-1 transition-colors`}>
      <img src={url} alt={name || "logo"} onLoad={onLoad} data-testid={`${testid}-img`}
        className="max-h-full max-w-full object-contain" style={{ imageRendering: "auto" }} />
    </span>
  );
}
