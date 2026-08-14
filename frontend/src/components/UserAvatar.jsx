import { Avatar, AvatarImage, AvatarFallback } from "./ui/avatar";

const ROLE_COLORS = { admin: "#0F172A", editor: "#64748B", user: "#64748B" };

export function getInitials(name) {
  const p = (name || "").trim().split(/\s+/).filter(Boolean);
  if (p.length >= 2) return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return "U";
}

export function UserAvatar({ userId, name, role = "user", size = 36, showPhoto = true, v, className = "" }) {
  const src = showPhoto && userId
    ? `${process.env.REACT_APP_BACKEND_URL}/api/users/${userId}/avatar${v != null ? `?v=${v}` : ""}`
    : undefined;
  const c = ROLE_COLORS[role] || ROLE_COLORS.user;
  const fs = Math.max(10, Math.round(size * 0.36));
  return (
    <Avatar style={{ height: size, width: size }} className={`shrink-0 border border-[#F3F4F6] ${className}`} data-testid="user-avatar">
      {src && <AvatarImage src={src} alt={name} />}
      <AvatarFallback style={{ backgroundColor: c, fontSize: fs }} className="font-700 text-white">{getInitials(name)}</AvatarFallback>
    </Avatar>
  );
}
